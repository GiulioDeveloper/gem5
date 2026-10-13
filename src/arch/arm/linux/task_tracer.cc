/*
 * LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
 */

#include "arch/arm/linux/task_tracer.hh"

#include <algorithm>
#include <cstdio>

#include "arch/arm/page_size.hh"
#include "arch/arm/regs/int.hh"
#include "arch/arm/regs/misc.hh"
#include "arch/arm/regs/misc_types.hh"
#include "base/loader/object_file.hh"
#include "base/loader/symtab.hh"
#include "base/bitfield.hh"
#include "base/logging.hh"
#include "base/trace.hh"
#include "cpu/base.hh"
#include "cpu/thread_context.hh"
#include "debug/TaskTracer.hh"
#include "sim/byteswap.hh"
#include "sim/cur_tick.hh"
#include "sim/system.hh"

namespace gem5
{

namespace ArmISA
{

namespace
{

/** Write s as a JSON string literal, escaping every byte >= 0x80. */
void
jsonString(std::ostream &os, const std::string &s)
{
    os << '"';
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') {
            os << '\\' << c;
        } else if (c < 0x20 || c >= 0x7f) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\u%04x", c);
            os << buf;
        } else {
            os << c;
        }
    }
    os << '"';
}

} // anonymous namespace

LinuxTaskTracer::Hook::Hook(LinuxTaskTracer *_tracer, PCEventScope *scope,
                            const std::string &desc, Addr pc,
                            Handler _handler)
    : PCEvent(scope, desc, pc), tracer(_tracer), handler(_handler)
{}

void
LinuxTaskTracer::Hook::process(ThreadContext *tc)
{
    // Called when the hooked function's first instruction is next to
    // commit (O3: in commit, never on the wrong path; simple CPUs: before
    // executing it). Registers and memory are architectural state, so the
    // C arguments are in x0..x7. Handlers only read; they never change PC.
    (tracer->*handler)(tc);
}

LinuxTaskTracer::LinuxTaskTracer(const Params &p)
    : SimObject(p), system(p.system)
{}

LinuxTaskTracer::~LinuxTaskTracer()
{
    if (out)
        simout.close(out);
}

void
LinuxTaskTracer::startup()
{
    SimObject::startup();

    out = simout.create(params().output);
    fatal_if(!out, "%s: cannot create %s", name(), params().output);

    std::unique_ptr<loader::ObjectFile> obj(
        loader::createObjectFile(params().vmlinux));
    fatal_if(!obj, "%s: cannot load vmlinux %s", name(), params().vmlinux);
    // The vmlinux carries link-time addresses; the guest runs relocated.
    const Addr slide = deriveSlide(obj->symtab(), kernelPgd);
    fatal_if(params().kaslr_slide != MaxAddr && params().kaslr_slide != slide,
             "%s: KASLR slide %#x derived from guest memory disagrees with "
             "the given %#x", name(), slide, params().kaslr_slide);
    auto symtab = obj->symtab().offset(slide);

    auto add = [&](const char *symbol, Hook::Handler handler) {
        auto it = symtab->find(symbol);
        fatal_if(it == symtab->end(), "%s: kernel symbol %s not found",
                 name(), symbol);
        hooks.emplace_back(new Hook(this, system, symbol, it->address(),
                                    handler));
        DPRINTF(TaskTracer, "hook %s at %#x\n", symbol, it->address());
    };
    add("__schedule", &LinuxTaskTracer::scheduleEnter);
    add("__switch_to", &LinuxTaskTracer::switchTo);
    add("wake_up_new_task", &LinuxTaskTracer::wakeUpNewTask);
    add("__arm64_sys_execve", &LinuxTaskTracer::execve);
    add("__arm64_sys_execveat", &LinuxTaskTracer::execveat);
    add("perf_event_comm", &LinuxTaskTracer::perfEventComm);
    add("do_exit", &LinuxTaskTracer::doExit);
    if (!params().write_process.empty() || !params().write_files.empty())
        add("vfs_write", &LinuxTaskTracer::vfsWrite);
    if (!params().read_process.empty())
        add("vfs_read", &LinuxTaskTracer::vfsRead);

    begin("start") << ",\"kaslr_slide\":" << slide;
    end();
    if (params().snapshot) {
        auto it = symtab->find("init_task");
        fatal_if(it == symtab->end(), "%s: kernel symbol init_task not "
                 "found", name());
        snapshot(system->threads[0], it->address());
    }
}

void
LinuxTaskTracer::snapshot(ThreadContext *tc, Addr init_task)
{
    // Thread-group leaders are linked through task_struct.tasks, starting
    // at init_task; each leader's threads through thread_node, a ring that
    // also holds the list head in its signal_struct. That node is not a
    // task (and signal_struct has no layout in a reduced-debug-info
    // kernel), so ring members whose tgid differs from the leader's are
    // skipped. Both walks are bounded in case a list is being modified.
    const auto &p = params();
    std::ostream &os = begin("snapshot");
    os << ",\"tasks\":[";
    size_t n = 0;
    auto emit = [&](const Task &t) {
        if (n++)
            os << ',';
        writeTaskValue(t);
    };
    const Addr head = init_task + p.task_tasks;
    Addr node = head;
    for (unsigned i = 0; i < 65536; i++) {
        const Addr leader = node - p.task_tasks;
        const Task lt = readTask(tc, leader);
        if (lt.valid) {
            emit(lt);
            const Addr ring = leader + p.task_thread_node;
            uint64_t cur;
            if (readU64(tc, ring + p.list_next, cur)) {
                for (unsigned j = 0; j < 8192 && cur && cur != ring; j++) {
                    const Task tt = readTask(tc, cur - p.task_thread_node);
                    if (tt.valid && tt.tgid == lt.tgid && tt.pid != lt.pid)
                        emit(tt);
                    if (!readU64(tc, cur + p.list_next, cur))
                        break;
                }
            }
        }
        uint64_t next;
        if (!readU64(tc, node + p.list_next, next) || !next || next == head)
            break;
        node = next;
    }
    os << "],\"count\":" << n;
    end();
}

Addr
LinuxTaskTracer::deriveSlide(const loader::SymbolTable &link,
                             Addr &swapper_pa) const
{
    // The method of RPoint's landing labeller, applied to the restored
    // state. TTBR1_EL1 holds the physical address of swapper_pg_dir (in
    // the kernel) or tramp_pg_dir (at EL0 under KPTI); both sit at fixed
    // offsets in the physically contiguous kernel image, which gives the
    // image's physical base. The candidate whose init_task is named
    // "swapper/0" is right; kimage_voffset (image VA - PA) then gives the
    // slide.
    auto sym = [&](const char *name) {
        auto it = link.find(name);
        fatal_if(it == link.end(), "%s: kernel symbol %s not found",
                 this->name(), name);
        return it->address();
    };
    auto readPhys = [&](Addr pa, void *p, size_t size) {
        return system->isMemAddr(pa) &&
               system->physProxy.tryReadBlob(pa, p, size);
    };
    ThreadContext *tc = system->threads[0];
    const Addr pgdir = tc->readMiscRegNoEffect(MISCREG_TTBR1_EL1) &
                       mask(48) & ~mask(12);
    const Addr text = sym("_text");
    const auto &p = params();
    for (const char *candidate : {"swapper_pg_dir", "tramp_pg_dir"}) {
        // The image is physically contiguous, so a symbol's offset from
        // _text is the same in link VAs and in guest PAs.
        const Addr pa_text = pgdir - (sym(candidate) - text);
        std::string comm(p.task_comm_len, '\0');
        if (!readPhys(pa_text + (sym("init_task") - text) + p.task_comm,
                      comm.data(), comm.size())) {
            continue;
        }
        comm.resize(strnlen(comm.data(), comm.size()));
        uint64_t voffset;
        if (comm != "swapper/0" ||
            !readPhys(pa_text + (sym("kimage_voffset") - text), &voffset,
                      sizeof(voffset))) {
            continue;
        }
        const Addr slide = pa_text + letoh(voffset) - text;
        swapper_pa = pa_text + (sym("swapper_pg_dir") - text);
        DPRINTF(TaskTracer, "TTBR1 is %s; image at PA %#x; slide %#x\n",
                candidate, pa_text, slide);
        return slide;
    }
    fatal("%s: cannot derive the KASLR slide: TTBR1_EL1 (%#x) points at "
          "neither swapper_pg_dir nor tramp_pg_dir of %s", name(), pgdir,
          p.vmlinux);
}

bool
LinuxTaskTracer::translate(ThreadContext *tc, Addr va, Addr &pa) const
{
    // A software walk of the EL1&0 stage-1 tables (4 KiB granule) that
    // reads descriptors from physical memory. It deliberately bypasses the
    // MMU: a functional translation there still makes a timing-visible
    // first TLB lookup (MMU::getTE), which updates replacement state and
    // can fill the L1 TLB from the L2, so the tracer would perturb the very
    // run it traces. Permissions are not checked, so user addresses are
    // readable from EL1 regardless of PAN.
    const TCR tcr = tc->readMiscRegNoEffect(MISCREG_TCR_EL1);
    const bool upper = bits(va, 63);
    // TG0 encodes 4 KiB as 0b00, TG1 as 0b10.
    if ((upper ? tcr.tg1 : tcr.tg0) != (upper ? 2 : 0))
        return false;
    const unsigned va_bits = 64 - (upper ? tcr.t1sz : tcr.t0sz);
    if (va_bits < 25 || va_bits > 48 ||
        (va >> va_bits) != (upper ? mask(64 - va_bits) : 0)) {
        return false;
    }
    const Addr v = va & mask(va_bits);
    // TTBR.BADDR, dropping the ASID and CnP. Kernel addresses go through
    // swapper_pg_dir (see kernelPgd).
    Addr table = upper && kernelPgd ? kernelPgd
        : tc->readMiscRegNoEffect(upper ? MISCREG_TTBR1_EL1
                                        : MISCREG_TTBR0_EL1)
          & mask(48) & ~1ULL;
    // Each level resolves 9 VA bits above the 12-bit page offset, so a
    // 48-bit VA starts at level 0 and a 39-bit VA at level 1.
    const unsigned levels = (va_bits - 12 + 8) / 9;
    for (unsigned level = 4 - levels; level <= 3; level++) {
        const unsigned shift = 12 + 9 * (3 - level);
        const Addr entry = table + ((v >> shift) & mask(9)) * 8;
        uint64_t desc;
        if (!system->isMemAddr(entry) ||
            !system->physProxy.tryReadBlob(entry, &desc, sizeof(desc))) {
            return false;
        }
        desc = letoh(desc);
        const Addr out = desc & mask(48);
        const unsigned type = desc & 3;
        if (level == 3) {
            if (type != 3)
                return false;
            pa = (out & ~mask(12)) | (va & mask(12));
            return true;
        }
        // Above level 3: 0b11 is a next-level table, 0b01 a block (1 GiB at
        // level 1, 2 MiB at level 2; the kernel's linear map uses these).
        if (type == 3) {
            table = out & ~mask(12);
        } else if (type == 1 && level >= 1) {
            pa = (out & ~mask(shift)) | (va & mask(shift));
            return true;
        } else {
            return false;
        }
    }
    return false;
}

bool
LinuxTaskTracer::readVirt(ThreadContext *tc, Addr va, void *p,
                          size_t size) const
{
    auto *dst = static_cast<uint8_t *>(p);
    while (size) {
        const size_t chunk = std::min<size_t>(size,
                                              PageBytes - va % PageBytes);
        Addr pa;
        if (!translate(tc, va, pa) || !system->isMemAddr(pa) ||
            !system->physProxy.tryReadBlob(pa, dst, chunk)) {
            return false;
        }
        va += chunk;
        dst += chunk;
        size -= chunk;
    }
    return true;
}

bool
LinuxTaskTracer::readU64(ThreadContext *tc, Addr addr, uint64_t &v) const
{
    if (!readVirt(tc, addr, &v, sizeof(v)))
        return false;
    v = letoh(v);
    return true;
}

std::string
LinuxTaskTracer::readString(ThreadContext *tc, Addr addr, size_t max) const
{
    std::string s;
    char buf[PageBytes];
    while (s.size() < max) {
        // Never read across a page boundary in one go: the next page may
        // be unmapped even though the string ends before it.
        size_t chunk = std::min<size_t>(max - s.size(),
                                        PageBytes - addr % PageBytes);
        if (!readVirt(tc, addr, buf, chunk))
            break;
        size_t len = strnlen(buf, chunk);
        s.append(buf, len);
        if (len < chunk)
            break;
        addr += chunk;
    }
    return s;
}

LinuxTaskTracer::Task
LinuxTaskTracer::readTask(ThreadContext *tc, Addr task) const
{
    const auto &p = params();
    Task t;
    if (!task)
        return t;

    int32_t ids[2];
    uint32_t flags;
    uint64_t mm, leader, parent, ns, cg;
    if (!readVirt(tc, task + p.task_pid, &ids[0], sizeof(ids[0])) ||
        !readVirt(tc, task + p.task_tgid, &ids[1], sizeof(ids[1])) ||
        !readVirt(tc, task + p.task_flags, &flags, sizeof(flags)) ||
        !readU64(tc, task + p.task_mm, mm) ||
        !readU64(tc, task + p.task_group_leader, leader) ||
        !readU64(tc, task + p.task_real_parent, parent) ||
        !readU64(tc, task + p.task_nsproxy, ns) ||
        !readU64(tc, task + p.task_cgroups, cg)) {
        return t;
    }
    t.pid = letoh(ids[0]);
    t.tgid = letoh(ids[1]);
    t.mm = mm;
    t.ns = ns;
    t.cg = cg;
    // PF_KTHREAD (include/linux/sched.h), unchanged since Linux 2.6.
    t.kthread = letoh(flags) & 0x00200000;
    t.comm = readString(tc, task + p.task_comm, p.task_comm_len);
    // Threads have their own comm (e.g. "JITWorker"); the process is named
    // by its thread-group leader's comm (e.g. "opencode").
    t.process = leader == task
        ? t.comm
        : readString(tc, leader + p.task_comm, p.task_comm_len);
    int32_t ppid;
    if (parent && readVirt(tc, parent + p.task_tgid, &ppid, sizeof(ppid)))
        t.ppid = letoh(ppid);
    t.valid = true;
    return t;
}

LinuxTaskTracer::Task
LinuxTaskTracer::currentTask(ThreadContext *tc) const
{
    // In the arm64 kernel, SP_EL0 holds `current` while at EL1.
    return readTask(tc, tc->getReg(int_reg::Sp0));
}

std::ostream &
LinuxTaskTracer::begin(const char *event)
{
    // Both counts exclude the hooked instruction itself (it has not
    // committed yet). They follow totalInsts(): O3 leaves NOPs out, the
    // simple CPUs count them. Checked against an O3 Exec trace: counts
    // between events match it exactly. On O3, `tick` is the commit-time
    // tick; Exec prints the fetch tick instead.
    std::ostream &os = *out->stream();
    os << "{\"tick\":" << curTick()
       << ",\"insts\":" << BaseCPU::totalNumSimulatedInsts()
       << ",\"uinsts\":" << BaseCPU::totalNumSimulatedUserInsts()
       << ",\"event\":\"" << event << '"';
    return os;
}

void
LinuxTaskTracer::end()
{
    // Flush per event: a run that dies keeps its trace up to the end.
    *out->stream() << "}\n" << std::flush;
}

void
LinuxTaskTracer::writeTask(const char *key, const Task &task)
{
    *out->stream() << ",\"" << key << "\":";
    writeTaskValue(task);
}

void
LinuxTaskTracer::writeTaskValue(const Task &task)
{
    std::ostream &os = *out->stream();
    if (!task.valid) {
        os << "null";
        return;
    }
    os << "{\"pid\":" << task.pid << ",\"tgid\":" << task.tgid
       << ",\"ppid\":" << task.ppid << ",\"comm\":";
    jsonString(os, task.comm);
    os << ",\"process\":";
    jsonString(os, task.process);
    // ns and cg are kernel pointers used as identifiers; written as hex
    // strings because JSON readers in JavaScript lose 64-bit integers.
    char ids[64];
    std::snprintf(ids, sizeof(ids), ",\"ns\":\"%#llx\",\"cg\":\"%#llx\"",
                  (unsigned long long)task.ns, (unsigned long long)task.cg);
    os << ",\"kernel_thread\":" << (task.mm ? "false" : "true")
       << ",\"kthread\":" << (task.kthread ? "true" : "false") << ids
       << '}';
}

void
LinuxTaskTracer::scheduleEnter(ThreadContext *tc)
{
    // __schedule(unsigned int sched_mode) is the scheduler proper: every
    // path that can switch tasks (schedule(), preemption, idle) goes through
    // it, and it runs only kernel code with interrupts off until it reaches
    // __switch_to. Remember where it started so the switch can report what
    // picking the next task cost. A call that keeps the same task never
    // reaches __switch_to; its entry is simply overwritten by the next one.
    schedEntry[tc->contextId()] =
        {curTick(), BaseCPU::totalNumSimulatedInsts()};
}

void
LinuxTaskTracer::switchTo(ThreadContext *tc)
{
    // __switch_to(struct task_struct *prev, struct task_struct *next)
    Task prev = readTask(tc, tc->getReg(int_reg::X0));
    Task next = readTask(tc, tc->getReg(int_reg::X1));
    std::ostream &os = begin("switch");
    os << ",\"same_mm\":"
       << (prev.mm && prev.mm == next.mm ? "true" : "false");
    auto entry = schedEntry.find(tc->contextId());
    if (entry != schedEntry.end()) {
        os << ",\"sched_insts\":"
           << BaseCPU::totalNumSimulatedInsts() - entry->second.insts
           << ",\"sched_ticks\":" << curTick() - entry->second.tick;
        schedEntry.erase(entry);
    }
    writeTask("prev", prev);
    writeTask("next", next);
    end();
}

void
LinuxTaskTracer::wakeUpNewTask(ThreadContext *tc)
{
    // wake_up_new_task(struct task_struct *p), called by the forking task.
    Task child = readTask(tc, tc->getReg(int_reg::X0));
    Task parent = currentTask(tc);
    begin("fork");
    writeTask("parent", parent);
    writeTask("child", child);
    end();
}

void
LinuxTaskTracer::execve(ThreadContext *tc)
{
    // __arm64_sys_execve(const struct pt_regs *regs):
    // regs[0] = filename, regs[1] = argv.
    Addr regs = tc->getReg(int_reg::X0) + params().pt_regs_regs;
    uint64_t filename, argv;
    if (readU64(tc, regs, filename) &&
        readU64(tc, regs + 8, argv)) {
        recordExecAttempt(tc, filename, argv);
    }
}

void
LinuxTaskTracer::execveat(ThreadContext *tc)
{
    // __arm64_sys_execveat(const struct pt_regs *regs):
    // regs[0] = dirfd, regs[1] = filename, regs[2] = argv.
    Addr regs = tc->getReg(int_reg::X0) + params().pt_regs_regs;
    uint64_t filename, argv;
    if (readU64(tc, regs + 8, filename) &&
        readU64(tc, regs + 16, argv)) {
        recordExecAttempt(tc, filename, argv);
    }
}

void
LinuxTaskTracer::recordExecAttempt(ThreadContext *tc, Addr filename,
                                   Addr argv)
{
    // Only remembered here: the exec is reported by perfEventComm(), which
    // the kernel reaches only once the new image is committed, so failed
    // attempts (e.g. PATH probing) never appear in the trace. Keyed by the
    // task_struct rather than the pid: a non-leader thread that execs takes
    // over its leader's pid (de_thread), but keeps its task_struct.
    const auto &p = params();
    Addr cur = tc->getReg(int_reg::Sp0);
    ExecAttempt attempt;
    attempt.path = readString(tc, filename, p.max_string_bytes);
    for (unsigned i = 0; argv && i < p.max_argv; i++) {
        uint64_t arg;
        if (!readVirt(tc, argv + 8 * i, &arg, sizeof(arg)))
            break;
        arg = letoh(arg);
        if (!arg)
            break;
        attempt.argv.push_back(
            readString(tc, arg, p.max_string_bytes));
    }
    execAttempts[cur] = std::move(attempt);
}

void
LinuxTaskTracer::perfEventComm(ThreadContext *tc)
{
    // perf_event_comm(struct task_struct *task, bool exec) is the one
    // out-of-line call on every comm change: __set_task_comm ends with it,
    // and begin_new_exec ends its inlined copy of __set_task_comm with it.
    // Hooking __set_task_comm itself misses every exec. By this point the
    // task already carries its new name.
    Addr addr = tc->getReg(int_reg::X0);
    Task task = readTask(tc, addr);
    bool exec = tc->getReg(int_reg::X1) & 1;
    std::ostream &os = begin(exec ? "exec" : "rename");
    writeTask("task", task);
    if (exec) {
        auto it = execAttempts.find(addr);
        if (it != execAttempts.end()) {
            os << ",\"path\":";
            jsonString(os, it->second.path);
            os << ",\"argv\":[";
            for (size_t i = 0; i < it->second.argv.size(); i++) {
                if (i)
                    os << ',';
                jsonString(os, it->second.argv[i]);
            }
            os << ']';
            execAttempts.erase(it);
        }
    }
    end();
}

void
LinuxTaskTracer::doExit(ThreadContext *tc)
{
    // do_exit(long code), on the exiting task.
    Addr addr = tc->getReg(int_reg::Sp0);
    Task task = readTask(tc, addr);
    execAttempts.erase(addr);
    begin("exit") << ",\"code\":"
                  << static_cast<int64_t>(tc->getReg(int_reg::X0));
    writeTask("task", task);
    end();
}

void
LinuxTaskTracer::filePath(ThreadContext *tc, Addr file, std::string &name,
                          std::string &path) const
{
    // The dentry's own name, and the names of its ancestors up to the root
    // of its filesystem (inside a container that is the container's root;
    // mount points are not crossed). Anonymous files such as eventfds have
    // a dentry that is its own parent; their path is just the name.
    const auto &p = params();
    name.clear();
    path.clear();
    uint64_t dentry, fname;
    if (!readU64(tc, file + p.file_f_path + p.path_dentry, dentry) ||
        !readU64(tc, dentry + p.dentry_d_name + p.qstr_name, fname)) {
        return;
    }
    name = readString(tc, fname, 256);
    std::vector<std::string> parts{name};
    Addr d = dentry;
    for (int depth = 0; depth < 64; depth++) {
        uint64_t parent, pname;
        if (!readU64(tc, d + p.dentry_d_parent, parent) || !parent ||
            parent == d ||
            !readU64(tc, parent + p.dentry_d_name + p.qstr_name, pname)) {
            break;
        }
        const std::string n = readString(tc, pname, 256);
        uint64_t grand;
        // The root dentry is its own parent and is named "/".
        if (!readU64(tc, parent + p.dentry_d_parent, grand) ||
            grand == parent) {
            path = "/";
            break;
        }
        parts.push_back(n);
        d = parent;
    }
    for (auto it = parts.rbegin(); it != parts.rend(); ++it) {
        if (!path.empty() && path.back() != '/')
            path += '/';
        path += *it;
    }
}

void
LinuxTaskTracer::vfsWrite(ThreadContext *tc)
{
    // vfs_write(struct file *file, const char __user *buf, size_t count,
    //           loff_t *pos)
    const auto &p = params();
    Task task = currentTask(tc);
    Addr filp = tc->getReg(int_reg::X0);
    Addr buf = tc->getReg(int_reg::X1);
    size_t count = tc->getReg(int_reg::X2);
    DPRINTF(TaskTracer, "vfs_write by %d/%s/%s count %d\n", task.pid,
            task.process, task.comm, count);
    if (!task.valid)
        return;

    std::string name, path;
    if (!p.write_process.empty() && task.process == p.write_process) {
        // The traced process: every write, if it matches the prefix.
        const std::string &prefix = p.write_prefix;
        if (count < prefix.size())
            return;
        std::string head(prefix.size(), '\0');
        if (!readVirt(tc, buf, head.data(), head.size()) || head != prefix)
            return;
        filePath(tc, filp, name, path);
    } else {
        // Any other process: only writes to the chosen file names.
        if (p.write_files.empty())
            return;
        filePath(tc, filp, name, path);
        if (std::find(p.write_files.begin(), p.write_files.end(), name) ==
            p.write_files.end()) {
            return;
        }
    }

    // buf is a user address of the calling task, which is current, so
    // TTBR0_EL1 still maps it; the software walk ignores PAN.
    size_t len = std::min<size_t>(count, p.max_write_bytes);
    std::string data(len, '\0');
    bool ok = readVirt(tc, buf, data.data(), len);

    std::ostream &os = begin("write");
    writeTask("task", task);
    os << ",\"file\":";
    jsonString(os, name);
    os << ",\"path\":";
    jsonString(os, path);
    os << ",\"count\":" << count << ",\"truncated\":"
       << (len < count ? "true" : "false") << ",\"data\":";
    if (ok)
        jsonString(os, data);
    else
        os << "null";
    end();
}

void
LinuxTaskTracer::vfsRead(ThreadContext *tc)
{
    // vfs_read(struct file *file, char __user *buf, size_t count,
    //          loff_t *pos), at entry: the data is not read yet, so only
    // the file, the size asked for and the offset are recorded.
    const auto &p = params();
    Task task = currentTask(tc);
    if (!task.valid || task.process != p.read_process)
        return;
    std::string name, path;
    filePath(tc, tc->getReg(int_reg::X0), name, path);
    const size_t count = tc->getReg(int_reg::X2);
    const Addr pos_ptr = tc->getReg(int_reg::X3);
    uint64_t pos = 0;
    const bool has_pos = pos_ptr && readU64(tc, pos_ptr, pos);

    std::ostream &os = begin("read");
    writeTask("task", task);
    os << ",\"file\":";
    jsonString(os, name);
    os << ",\"path\":";
    jsonString(os, path);
    os << ",\"count\":" << count << ",\"pos\":";
    if (has_pos)
        os << static_cast<int64_t>(pos);
    else
        os << "null";
    end();
}

} // namespace ArmISA
} // namespace gem5
