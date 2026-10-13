/*
 * LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
 */

#ifndef __ARCH_ARM_LINUX_TASK_TRACER_HH__
#define __ARCH_ARM_LINUX_TASK_TRACER_HH__

#include <cstdint>
#include <memory>
#include <ostream>
#include <string>
#include <unordered_map>
#include <vector>

#include "base/loader/symtab.hh"
#include "base/output.hh"
#include "base/types.hh"
#include "cpu/pc_event.hh"
#include "params/ArmLinuxTaskTracer.hh"
#include "sim/sim_object.hh"

namespace gem5
{

class System;
class ThreadContext;

namespace ArmISA
{

/**
 * Traces an AArch64 Linux guest's scheduling and process lifecycle.
 *
 * Read-only PC events on kernel functions (at link address plus the KASLR
 * slide) record context switches, forks, execs, renames, exits, the
 * payload of one chosen process's write() calls and the metadata of its
 * read() calls, and writes to chosen files (by default cgroup.procs) from
 * any process. At start-up it records every process and thread alive in
 * the guest. Each event is one JSON object per line, stamped with the
 * tick and the global committed instruction count, so the trace lines up
 * with any instruction-based region of the run.
 *
 * Guest strings are byte strings: bytes >= 0x80 are written as \u00XX, so
 * a reader recovers the original bytes with s.encode("latin-1").
 */
class LinuxTaskTracer : public SimObject
{
  public:
    PARAMS(ArmLinuxTaskTracer);
    LinuxTaskTracer(const Params &p);
    ~LinuxTaskTracer() override;

    void startup() override;

  private:
    /** A PC event that forwards to a tracer member function. */
    class Hook : public PCEvent
    {
      public:
        using Handler = void (LinuxTaskTracer::*)(ThreadContext *);

        Hook(LinuxTaskTracer *tracer, PCEventScope *scope,
             const std::string &desc, Addr pc, Handler handler);

        void process(ThreadContext *tc) override;

      private:
        LinuxTaskTracer *tracer;
        Handler handler;
    };

    /** The fields of one task_struct the trace reports. */
    struct Task
    {
        bool valid = false;
        int32_t pid = -1;
        int32_t tgid = -1;
        int32_t ppid = -1;
        Addr mm = 0;
        /** Namespace set (task_struct.nsproxy): same value, same
         *  container. An opaque identifier within one run. */
        Addr ns = 0;
        /** Cgroup set (task_struct.cgroups): same value, same cgroups. */
        Addr cg = 0;
        /** PF_KTHREAD: a kernel thread. */
        bool kthread = false;
        /** Thread name (task_struct.comm). */
        std::string comm;
        /** Process name: the thread-group leader's comm. */
        std::string process;
    };

    /** An execve() seen at syscall entry, not yet known to succeed. */
    struct ExecAttempt
    {
        std::string path;
        std::vector<std::string> argv;
    };

    /** The guest kernel's KASLR slide, read from the restored state. */
    Addr deriveSlide(const loader::SymbolTable &link,
                     Addr &swapper_pa) const;

    /** Every process and thread alive now, as one `snapshot` event. */
    void snapshot(ThreadContext *tc, Addr init_task);

    /** Guest VA -> PA by walking the guest's own page tables. */
    bool translate(ThreadContext *tc, Addr va, Addr &pa) const;
    /** Read guest virtual memory without touching the simulated MMU. */
    bool readVirt(ThreadContext *tc, Addr va, void *p, size_t size) const;
    bool readU64(ThreadContext *tc, Addr addr, uint64_t &v) const;
    std::string readString(ThreadContext *tc, Addr addr, size_t max) const;

    Task readTask(ThreadContext *tc, Addr task) const;
    /** The task running on tc; valid only while tc is in the kernel. */
    Task currentTask(ThreadContext *tc) const;

    void scheduleEnter(ThreadContext *tc);
    void switchTo(ThreadContext *tc);
    void wakeUpNewTask(ThreadContext *tc);
    void execve(ThreadContext *tc);
    void execveat(ThreadContext *tc);
    void perfEventComm(ThreadContext *tc);
    void doExit(ThreadContext *tc);
    void vfsWrite(ThreadContext *tc);
    void vfsRead(ThreadContext *tc);

    /** A file's name and its path up to its filesystem's root. */
    void filePath(ThreadContext *tc, Addr file, std::string &name,
                  std::string &path) const;

    void recordExecAttempt(ThreadContext *tc, Addr filename, Addr argv);

    /** Start a JSON line with the fields every event carries. */
    std::ostream &begin(const char *event);
    /** Close and flush the JSON line begin() opened. */
    void end();
    void writeTask(const char *key, const Task &task);
    void writeTaskValue(const Task &task);

    System *system;
    /** Physical address of swapper_pg_dir, the kernel's own page table.
     *  Kernel addresses are translated through it rather than TTBR1_EL1,
     *  which at EL0 under KPTI points at the trampoline table, where the
     *  kernel is not mapped. */
    Addr kernelPgd = 0;
    std::vector<std::unique_ptr<Hook>> hooks;
    OutputStream *out = nullptr;
    /** Where the scheduler's current __schedule() call started. */
    struct SchedEntry
    {
        Tick tick;
        Counter insts;
    };
    /** Open __schedule() calls, by hardware context. */
    std::unordered_map<ContextID, SchedEntry> schedEntry;
    /** Pending execve() attempts, by the calling task_struct. */
    std::unordered_map<Addr, ExecAttempt> execAttempts;
};

} // namespace ArmISA
} // namespace gem5

#endif // __ARCH_ARM_LINUX_TASK_TRACER_HH__
