# Guest task and tool-call tracing for agentic restores

**Started:** 2026-10-08 · **Branch:** `gfdev`

A running record of what was built to see context switches, process names and
OpenCode tool calls inside restored agentic RPoint checkpoints, and why each
choice was made. Newest entries last.

How to use the result: [`docs/agentic/task-tracing-guide.md`](../../agentic/task-tracing-guide.md).

---

## Where things are

Run outputs are kept under `runs/tasktrace/` (gitignored), one folder per
run; earlier development runs were deleted on 2026-10-08. The ones this log
cites:

| folder | what |
|---|---|
| `20261008-113444-gin-2121-o3pair-perturbed` | O3 pair with the first, MMU-based tracer: stats differ (decision 8) |
| `20261008-113559-gin-2121-o3pair-determinism` | O3 pair without tracer: identical, so gem5 is deterministic |
| `20261008-120444-gin-2121-atomic-5G` | 5G atomic instructions of gin cpt.0: the first tool calls (read, edit) |
| `20261008-120610-gin-2121-o3interval-test` | interval and tail mechanics check (decision 9) |
| `20261008-125928-gin-2121-o3window-read` | 420M O3 instructions across gin's first tool call, 1M blocks |
| `20261008-163105-gin-2121-o3pair-final` | O3 pair with the current tracer: identical |
| `20261008-163105-landing-all` | landing check over all 27 local checkpoints, current tracer |
| `20261008-163520-framework-52684-atomic-400M` | 400M atomic instructions starting inside a fenced `rg` |
| `20261008-163520-framework-52684-o3window-20M` | 20M O3 instructions from the same restore, 100K blocks |
| `20261008-183432-framework-52684-atomic` | atomic run to the `ROUND 3` marker (6.47G instructions); found the round-2 `bash` call |
| `20261009-141720-framework-52684-o3window` | the O3 window across that call with the user/kernel split and scheduler cost (decision 14); superseded the 20261008-194138 run, which has no split |

Run helpers live in `run_scripts/tasktrace/` (untracked, next to
`run_agent.sh`).

## Goal

The agentic checkpoints (`gem5-ckpts/rpoint_ckpts/agentic/`, 27 tasks locally,
`cpt.0` each) are an OpenCode agent replayed model-free inside an Ubuntu guest.
We expect the costs to sit in short, fragmented tool calls and frequent context
switches. To compare microarchitectural behaviour around those events against
steady state we need, inside the gem5 run:

- every context switch, fork, exec, exit and rename, with the task names involved;
- every OpenCode tool call (name, input, start and end);
- each stamped with the simulated tick **and** a global committed-instruction count.

Everything lives in this repository. The gem5-infra repository is not touched;
we only read the checkpoint copy (`provenance.json` for the KASLR slide) and the
guest vmlinux.

## Facts the design rests on

- **KASLR.** The guest kernel runs with KASLR. Every checkpoint's
  `provenance.json` carries `landing.kaslr_slide`; `link address + slide` is the
  runtime address. Checked by symbolizing five EL1 landing PCs, which resolve to
  sensible places (`arch_counter_get_cntvct+0x14`, `futex_wake+0x84`,
  `step_into+0x90`, ...).
- **gem5's own context-switch hook cannot be used.**
  `enable_context_switch_stats_dump` (`src/arch/arm/linux/fs_workload.cc`) hooks
  the unslid `__switch_to`, relies on `task_struct_*` helper symbols the stock
  kernel does not export, and dumps the whole stats tree on every switch.
- **PC events are the right mechanism.** They fire when the instruction at the
  address commits (O3 `commit.cc`, simple CPUs `base.cc`), so never on wrong-path
  instructions; they live in `System` and move across `m5.switchCpus`
  (`System::replaceThreadContext`).
- **The restored kernel symbol table may be empty** (it is unserialized from the
  checkpoint), so the tracer loads its own copy from the vmlinux.
- **OpenCode logs every completed tool call.** The harness is launched as
  `opencode run --format json` with stdout redirected to
  `/tmp/agentic-benchmark-opencode.log` (framework
  `runtime/tool-server/entrypoint.py`). Each event is one JSON line; completed
  `tool_use` events carry tool name, input and `time.start/end`. In-process tools
  (read, edit, grep, glob, write, todowrite) never fork; only `bash` and `rg` run
  as separate processes, via `fence-exec.sh` (`bash.fence-real`, `rg.fence-real`).

## Decision log

### 1. The guest kernel has reduced debug info

The vmlinux was compiled with `-femit-struct-debug-baseonly`
(`CONFIG_DEBUG_INFO_REDUCED`). Only structs whose defining header matches a
compilation unit's base name have a full layout. Present: `task_struct`, `file`,
`dentry`, `qstr`, `pt_regs`. Absent: `mm_struct`, `linux_binprm`, `path`,
`css_set`, `cgroup`, `kernfs_node`.

Consequences for the design:

- **Exec path and argv** cannot come from `mm_struct` (exe_file, arg_start) or
  `linux_binprm`. Instead hook the syscall entry `__arm64_sys_execve` /
  `__arm64_sys_execveat`: the `pt_regs` argument holds the user pointers to the
  filename and argv, which are readable there because the calling task is current.
  An attempt is confirmed by `__set_task_comm(task, name, exec=true)`, which
  `begin_new_exec` calls only on success (`execvp` PATH probing produces failed
  attempts that must not be recorded as execs).
- **Cgroup names are dropped.** Tool vs harness is decided by process ancestry
  instead (descendants of `bash.fence-real` / `rg.fence-real`).
- **`struct path` layout is assumed** (`{ vfsmount *mnt; dentry *dentry; }`,
  so `dentry` at +8). It has been this since 2.6 and is the only assumed offset.
- `task_struct.mm` is used only as a pointer value: NULL means kernel thread, and
  equal `mm` across a switch means a thread switch rather than a process switch.

### 2. Offsets come from gdb, not a DWARF parser

`gdb -batch` on the x86 host reads the aarch64 vmlinux and evaluates
`&((struct T *)0)->field` in about half a second, following anonymous unions
and nested members. That replaces a hand-written `readelf` walk. Values for this
kernel (6.8.12):

| field | offset |
|---|---|
| `task_struct.pid` / `tgid` | 1144 / 1148 |
| `task_struct.comm` (16 bytes) | 1632 |
| `task_struct.group_leader` | 1208 |
| `task_struct.real_parent` | 1160 |
| `task_struct.mm` | 1016 |
| `file.f_path` | 152 |
| `dentry.d_name` / `qstr.name` | 32 / 8 |

### 3. Guest memory is read by a software page walk, not through the MMU

*First version (superseded, see 8):* reads went through
`TranslatingPortProxy`, with user addresses translated as EL0
(`ArmISA::MMU::UserMode`) to get past PAN.

*Current version:* the tracer walks the guest's own stage-1 tables (EL1&0,
4 KiB granule, `TTBR0/1_EL1` chosen by VA bit 63, `TCR_EL1.T0SZ/T1SZ` for the
start level) and reads the descriptors and the data from physical memory via
`System::physProxy`. Permissions are not checked, so user memory is readable
from the kernel-side hooks regardless of PAN. Every read is `tryReadBlob`
behind `System::isMemAddr`; a failed read is recorded (`null` or empty
string), never `fatal`.

### 4. Where the code lives

| file | role |
|---|---|
| `src/cpu/base.hh`, O3 `cpu.cc`, simple, Minor, KVM commit code | never-reset user-mode instruction counter behind `uinsts` (decision 14) |
| `configs/garfield/arm/kernel_layout.py` | struct offsets from the vmlinux via gdb (also a CLI printing JSON) |
| `src/arch/arm/ArmLinuxTaskTracer.py` | SimObject declaration and parameters |
| `src/arch/arm/linux/task_tracer.{hh,cc}` | the tracer (`gem5::ArmISA::LinuxTaskTracer`) |
| `src/arch/arm/SConscript` | registers the source, SimObject and the `TaskTracer` debug flag |
| `configs/garfield/arm/task_trace.py` | `--task-trace*` flags; reads the slide and layout, attaches the tracer to the board |
| `configs/garfield/arm/virt_run.py` | calls `task_trace.add_args` / `task_trace.attach`; `--stats-interval-insts`, `--tail-insts` (decision 9) |
| `configs/garfield/arm/trace_analysis.py` | host-side analysis of a traced run (decision 10) |
| `run_scripts/tasktrace/*` (untracked) | run helpers: `atomic.sh` (atomic-only traced restore), `o3-window.sh` (fast-forward + detailed window with stats intervals), `o3-pair.sh` (no-perturbation check), `landing-all.sh` + `landing_summary.py` (landing check over every checkpoint). Outputs go to `runs/tasktrace/<stamp>-<task>-<kind>/` |

`virt_run.py` behaves exactly as before unless `--task-trace` is given.

### 5. How the hooks work

Each hook is a `PCEvent` at `symbol + slide` that calls a member function and
never changes the PC. On O3 the event is serviced at commit once the PC of the
next instruction to commit equals the hook address, so the architectural
registers are those at function entry: the arguments are in `x0..x2`.

| hook | arguments used | event written |
|---|---|---|
| `__schedule` | none (tick and instruction count remembered) | none; the next `switch` carries `sched_insts`, `sched_ticks` (decision 14) |
| `__switch_to` | x0 prev, x1 next task | `switch` (prev, next, `same_mm`, scheduler cost) |
| `wake_up_new_task` | x0 child; parent = current | `fork` |
| `__arm64_sys_execve(at)` | `pt_regs` → user filename, argv | none; remembered per pid |
| `perf_event_comm` | x0 task (new name already set), x1 exec flag | `exec` (with remembered path and argv) or `rename` |
| `do_exit` | x0 exit code; task = current | `exit` |
| `vfs_write` | x0 file, x1 user buffer, x2 count | `write` (file name + payload), only for threads of the chosen process (`opencode`) |

`current` is read from `SP_EL0`, which the arm64 kernel uses for it while at EL1.

Every event row carries `tick` and `insts`. `insts` is
`BaseCPU::totalNumSimulatedInsts()`: the sum over all CPUs of committed
instructions since the restore. It keeps counting across the atomic→O3
switch and is not affected by `m5.stats.reset()`.

### 6. Output format

One JSON object per line in `<outdir>/tasktrace.jsonl`, flushed per event so a
crashed run keeps its trace. A task is
`{pid, tgid, ppid, comm, process, kernel_thread}`, where `comm` is the thread
name and `process` the thread-group leader's name. Guest strings are byte
strings: bytes outside printable ASCII are written as `\u00XX`, so a reader
recovers the original bytes with `s.encode("latin-1")`.

### 7. Where the KASLR slide comes from

*First version:* `landing.kaslr_slide` from the checkpoint's
`provenance.json`, which five of the 27 local `cpt.0` checkpoints lack
(axios-5892, bat-2835, gson-2134, lombok-3479, rubocop-13560).

*Current version:* the tracer derives the slide from the restored state in
`startup()`, by the same method as RPoint's `landing.py`. `TTBR1_EL1` holds
the physical address of `swapper_pg_dir` (in the kernel) or `tramp_pg_dir`
(at EL0, KPTI). Both sit at fixed offsets in the physically contiguous kernel
image, so each candidate gives an image base; the one whose `init_task.comm`
reads `swapper/0` is right, and `kimage_voffset` (image VA − PA) then gives
`slide = pa_text + kimage_voffset − link(_text)`. If a slide is given
(`--task-trace-slide`, or the provenance value, which `task_trace.py` passes
when present) and the derived one differs, the run stops.

Checked: gin-2121 (EL0 landing, via `tramp_pg_dir`) and fmt-3901 (EL1
landing, via `swapper_pg_dir`) derive exactly their recorded slides;
axios-5892, which has no label, derives `0x5d6eb0600000` and landed on the
idle task (pid 0), which is probably why it was never labelled.

### 8. Two bugs found by the first runs (2026-10-08)

**Execs were missing: `__set_task_comm` is inlined into `begin_new_exec`.**
The 300M-instruction run showed pid 1748 forked as `python3` and exiting as
`docker`, but no `exec` event. With no aarch64 disassembler on the host, the
`bl` targets of `begin_new_exec` were decoded straight from the vmlinux bytes:
it calls `strrchr`, `_raw_spin_lock`, `strscpy_pad`, `_raw_spin_unlock`,
`perf_event_comm` — an inlined `__set_task_comm` — and never the out-of-line
symbol, which only serves `prctl(PR_SET_NAME)`. Both paths end with the
out-of-line `perf_event_comm(task, exec)`, called after the new name is
stored, so the hook moved there. Pending execve attempts are now keyed by the
`task_struct` address instead of the pid, because a non-leader thread that
execs takes over its leader's pid (`de_thread`) but keeps its task_struct.

**The tracer perturbed O3 timing: gem5's functional translation is not
side-effect free.** `run_scripts/tasktrace/o3-pair.sh` restores the same checkpoint
twice (1M warmup + 5M detailed) and diffs `stats.txt`. Two runs without the
tracer are identical; with the first tracer IPC moved 0.635 → 0.649 and 5377
stats lines differed (TLB, walker, caches, branch predictor ...). Cause:
`ArmISA::MMU::getTE` does its first TLB lookup with `functional = false` even
for a functional translation, so a `TranslatingPortProxy` read updates TLB
replacement state and stats, and on an L1 miss can insert the entry from the
L2 TLB (`TLB::multiLookup`). Fixing that in the MMU would change every
SE-mode result in this fork (SE syscall emulation translates functionally all
the time), so the tracer stopped using the MMU instead (decision 3). After the
change the pair is byte-identical apart from host-time stats (IPC 0.635 both).

### 9. Per-interval microarchitecture counters (M2)

No new C++: gem5 already has every counter needed, including
`commitStats0.numUserInsts` for the user/kernel split. `virt_run.py` gained:

- `--stats-interval-insts N`: the detailed region runs in N-instruction
  chunks, each followed by `m5.stats.dump(); m5.stats.reset()`, so
  `stats.txt` holds one block per interval. `intervals.csv` records each
  block's absolute tick range and its range of the *global* instruction count
  (sum over the atomic and O3 cores of `get_total_instructions()`), the same
  count the trace stamps on its events, so blocks and events join exactly.
- `--tail-insts M`: after the detailed region, switch back to the atomic core
  and run M more instructions with the tracer still on, to see events that
  complete after the region (a tool call it cut in half). gem5's exit dump
  adds one extra stats block for the tail; it has no `intervals.csv` row and
  the analysis ignores it.

Checked on gin `cpt.0` (1M warmup, 5M detailed in 1M blocks, 2M tail): total
detailed IPC 0.635, identical to the run without intervals, so chunking does
not perturb timing. Size: with `--stats-file=stats.txt?desc=False` a block of
this config is about 320 KB, so 100k-instruction blocks over a 50M region
cost about 160 MB per checkpoint; 250k–1M blocks are cheaper.

### 10. Analysis script (M3)

`configs/garfield/arm/trace_analysis.py <outdir>` (host Python, stdlib only;
this host has no pandas or matplotlib) writes `<outdir>/analysis/`:

- `processes.csv`: per process: names over its life (e.g. `python3|docker`,
  fork then exec), exec path and argv, role, instructions it ran, switch-ins.
- `writes.csv`: the traced process's writes.
- `tools.csv`: one row per OpenCode tool call (decision 11): tool, input
  (file path or command), the instruction count of each state change
  (`pending`, `running`, `completed`/`error`, and the JSON log line), the
  call's own guest timestamps, and the share of the running→completed span
  taken by each role. Tool starts and ends also become `tool_start` /
  `tool_end` events for `blocks.csv` and `aligned.csv`.
- `blocks.csv`: per stats interval: IPC, user fraction, L1I/L1D/L2 MPKI,
  conditional-branch and BTB-caused mispredicts per kilo-instruction,
  iTLB/dTLB misses and walks per kilo-instruction, the dominant process and
  role, the instruction share per role, and the events inside it.
- `aligned.csv`: per event kind, every metric averaged over the intervals at
  offsets −K..+K from the interval holding the event, next to the mean over
  all intervals.
- `summary.md`: event counts per million instructions and per simulated ms,
  instruction share per role, top processes.

Running time per task comes from the switch events: between two switches the
CPU belongs to the previous switch's `next` task. Roles: `harness` (the
`opencode` process), `harness-child` (anything else it started), `tool`
(`bash.fence-real` / `rg.fence-real` and descendants), `plumbing`
(docker / containerd / runc), `kernel`, `idle`, `other` (e.g. the replay
driver). Ancestry comes from `ppid` in every task record plus fork events.

### 11. Tool calls come from OpenCode's SQLite write-ahead log

The planned signal, OpenCode's `--format json` event stream, works but only
marks a call's *end*: one line per finished call, written to
`/tmp/agentic-benchmark-opencode.log`. Recording every write of the
`opencode` process (decision 5) showed a better one. OpenCode keeps its
session in SQLite with WAL journaling (`opencode.db-wal`); every message
part is a row, and each state change of a tool part
(`pending` → `running` → `completed` | `error`) rewrites that row, i.e. one
`write()` of the 4 KiB page holding it (plus a 24-byte frame header). The
rows are plain JSON, e.g.

    {"type":"tool","tool":"read","callID":"4c6f…","state":{"status":"running",
     "input":{"filePath":"/testbed/render/reader.go"},"time":{"start":1787140806197}}}

so the trace gives each transition at an exact instruction count and tick.
A WAL page also carries other rows, some stale, so a state counts from its
first appearance. Rows are parsed as brace-balanced JSON objects (nested
objects such as `"display":{"type":"file",…}` defeat simpler cut-offs); a
row cut short by the page end is read with field regexes instead. The
finished state carries the call's guest-clock `time.start/end` (ms; the
guest runs under `faketime`, pinned to 2026-08-19 12:00:00 at start).
Other writes of the process are eventfd wake-ups (8 bytes) and OpenCode's
own text log (`opencode.log`).

### 12. Interactive schedule view

`configs/garfield/arm/trace_view.py <outdir>` turns a trace into a compact
view model (`analysis/schedule.view.json`: running segments with both
instruction and tick bounds, processes with roles and exec command lines,
fork/exec/exit/rename marks, tool calls) and writes a self-contained
`analysis/schedule.html` from the template `trace_view.html`. The page shows
a whole-run overview strip with a brush, a tool-call track, a CPU track
coloured by role, and one lane per process name (or per process), with
hover details, zoom/pan, an instruction or simulated-ms axis, and the same
data as tables. It can open any other `schedule.view.json`, so one page
serves every future run. Roles and tool calls come from
`trace_analysis.py`, so both tools agree. `--fragment` drops the HTML
wrapper for hosts that add their own.

Building it exposed a role bug, now fixed in `trace_analysis.py`: kernel
threads were recognised by a null `mm`, but an exiting user process drops
its `mm` before its last switch, so dying `docker inspect` processes were
counted as kernel. Kernel threads are now kthreadd (pid 2) and its children.
On the 5G gin trace this moves the kernel share from 3.5% to 0.2% and
Docker plumbing from 17.4% to 19.0%.

### 13. Containers, cgroups, a process snapshot, fence entries and reads

Motivated by two views of a "tool call" (the framework's, where only fenced
subprocesses are tools, and the CPU's, where every change of execution
context matters whoever causes it), the tracer gained:

- **`ns`, `cg`, `kthread` on every task**: the `nsproxy` and `cgroups`
  pointers as opaque identities (same value = same container / same cgroup
  set; hex strings so JavaScript readers keep them exact) and the
  `PF_KTHREAD` flag, which replaces the "child of kthreadd" rule.
- **A start-up `snapshot`** of every process and thread, walking
  `init_task.tasks` and each leader's `thread_node` ring. The ring also
  holds a list head inside `signal_struct`, which has no layout here; ring
  members whose tgid differs from the leader's are skipped. Kernel
  addresses now always translate through `swapper_pg_dir`: at an EL0
  landing `TTBR1_EL1` points at KPTI's trampoline table, which does not map
  the kernel, and the snapshot runs exactly then.
- **Writes to `cgroup.procs` by any process** (`write_files`), to catch the
  tools fence moving a task.
- **A `vfs_read` hook** for the traced process: path, size, offset, no data
  (at entry the buffer is still empty). `read()` and `pread()` both call the
  out-of-line `vfs_read` in this kernel (checked from the `bl` targets).
- **Full file paths** for reads and writes, from the dentry chain up to the
  root of the file's filesystem (mounts are not crossed).

New offsets: `task_struct.flags/tasks/thread_node/nsproxy/cgroups`,
`dentry.d_parent`; `list_head.next` is assumed at 0 like `path.dentry` at 8.

The analysis replaced the "plumbing" role with `replay` (user processes on
the guest host: the replay driver and its `docker inspect`, `watch_rounds.sh`,
`sleep`), `daemon` (dockerd, containerd and shims, systemd services) and
`framework` (other processes inside the containers); added containers
(`containers.csv`), context switches by cause (`switches.csv`), reads
(`reads.csv`), every summary with and without replay, a fence verdict, and
per tool call an observed `kind` (in-process, or the fenced processes that
ran during it) and its own file I/O (`io_insts`). The viewer shows role and
container, tool-file I/O and cgroup-move marks, and can hide replay lanes.

### 14. User/kernel split and the scheduler's cost (2026-10-09)

Motivated by a viewer observation: one OpenCode thread follows another with
no kernel segment between them. That is correct for Linux (system calls,
interrupts and the scheduler run on the current task, under its pid; only
kernel threads have their own), but it hides how much of each time slice is
kernel work. Two additions:

- **`uinsts` on every event**: the global count of user-mode instructions,
  from a never-reset counter in `BaseCPU` (`userInsts()`), incremented in the
  simple, O3, Minor and KVM CPUs. `insts - uinsts` is kernel mode.
  *Bug found while validating:* the first version incremented next to the
  `numUserInsts` stat, but O3's `totalInsts()` (our `insts`) leaves out NOPs
  and instruction prefetches ("to match the old model") while that stat
  counts them, so kernel work came out negative for pure user slices (-1% to
  -3%) and the stat could not be mixed with `insts`. The O3 increment moved
  to `CPU::instDone`, the place `numInst` is counted. After the fix no slice
  has negative kernel work and, over whole slices, the trace's kernel share
  matches gem5's stats (e.g. 54.1% against 54.2% for a long `rg` slice).
- **A hook on `__schedule`** (kernel function every task switch goes
  through; kernel mode only, interrupts off). The `switch` event now carries
  `sched_insts` and `sched_ticks` from `__schedule` entry to `__switch_to`:
  the scheduler's direct cost, without what led to the switch.

The analysis splits slices, processes, roles, tool calls and switch causes
into user and kernel instructions, and the viewer shows each bar's kernel
share and scheduler tail. The order inside a slice is not recorded, so
ranges that cut a slice assume an even spread; the per-interval check
against gem5's stats (mean absolute difference 0.05) reflects that.

**No perturbation:** O3 pair, framework-52684, 1M warmup + 60M detailed, 107
switches: identical stats, IPC 0.854 both ways. The full 400M window repeats
the previous run's cycle count exactly (439,252,297; IPC 0.911) with the new
hook and counters.

## Validation

### 2026-10-08 — first run, gin-2121 cpt.0, atomic, 20M instructions

`run_scripts/tasktrace/atomic.sh gin-2121 20000000` (about 30 s at 1.7 MIPS).

- **Landing check passed.** The first `switch` has `prev` = `JITWorker`, pid
  1308, tgid 1235, process `opencode`: exactly the checkpoint's recorded
  landing. This checks the slide, the hook addresses and the struct offsets
  at once.
- 6 switches in 20M instructions (7.4 ms simulated): 5 between `opencode`
  threads (`same_mm` true), 1 to the kernel thread `rcu_preempt`. No fork,
  exec or tool write in this short window (the dump is 0.29 s into the agent
  loop).

### 2026-10-08 — after the fixes

- **No perturbation:** `run_scripts/tasktrace/o3-pair.sh gin-2121 1000000 5000000`
  → `IDENTICAL stats`, IPC 0.635 with and without the tracer.
- **Landing check on O3:** the first `switch` again has `prev` = `JITWorker`
  pid 1308 / tgid 1235 / `opencode`.
- **Execs:** 300M atomic instructions of gin `cpt.0` show the replay driver
  (python3, pid 617) running `/usr/bin/docker docker inspect eed93…` about
  every 220M instructions, and `watch_rounds.sh` running `/usr/bin/sleep
  sleep 0.2`; path and argv are recorded.
- **Determinism:** two atomic runs of the same window produce the same 398
  switches.
- **Tool-call writes: not yet observed.** In the first 680M instructions
  (~0.25 s guest time, still inside round 1) `vfs_write` is called only by
  `docker` and `dockerd`; `opencode` has not written. A 2.5G-instruction run
  is checking whether it writes once round 1's tool calls complete.

### 2026-10-08 — 2.5G atomic instructions of gin cpt.0 (first analysis)

`runs/tasktrace-gin-2121-atomic-20261008-113441` (deleted in the 2026-10-08 clean-up; superseded by the 5G run below) (run with the earlier,
MMU-based reads; atomic, so the perturbation does not matter for counting).
2.49G instructions, 934 ms simulated; the guest printed
`RPOINT_REPLAY_ROUND 2` near the end.

| event | count | per M insts | per ms |
|---|---|---|---|
| switch, thread (same mm) | 2385 | 0.96 | 2.56 |
| switch, process | 595 | 0.24 | 0.64 |
| switch, to/from kernel thread | 838 | 0.34 | 0.90 |
| fork (process / thread) | 19 / 62 | 0.01 / 0.02 | 0.02 / 0.07 |
| exec / exit | 19 / 78 | 0.01 / 0.03 | 0.02 / 0.08 |

Instruction share: harness 79.3%, plumbing 17.1%, kernel 2.0%, other 1.6%.

**Finding: 17% of the instructions are the replay driver polling Docker.**
The replay driver (python3, pid 617) runs `docker inspect <container>` about
every 220M instructions (~80 ms simulated). Each is a fresh Go process that
runs ~40M instructions with ~160 switch-ins before exiting: exactly the
short-lived-process behaviour we want to study, but produced by the benchmark
harness rather than by the agent. Any per-role or per-window statistic must
separate it, and it is worth checking whether the live (recorded) run had the
same poller and at what rate, since time-based polling inflates under a slow
simulated clock.

Source of the poller (framework copy in the v21 image,
`infrastructure/deterministic_replay/sweagent_driver.py`, which
`OpencodeReplayDriver` subclasses): `next_output()` waits for OpenCode's
next staged output (its next model request). Each time it finds none, it
runs `_orchestrator_running()`, i.e. `docker inspect <orchestrator
container>`, parses `State.Running` from the JSON, and sleeps
`_POLL_SECONDS = 0.05`. It exists only in the model-free replay (the live
run talked to a real model), and in the guest it shares the single vCPU with
OpenCode. Each poll forks the Docker CLI (a Go binary: runtime start, five
threads, an API call to `dockerd` over its socket), about 40M instructions.

**Finding: OpenCode does write, but not its JSON event lines (yet).** Its
threads (`Bun`, `HTTP`, `opencode`) called `vfs_write` 23 times, none starting
with `{"type":`. The write hook now records every write of the `opencode`
process (file name and payload) instead of matching a prefix, so the next run
shows what they are.

### 2026-10-08 — O3 with intervals (gin cpt.0, 5 × 1M)

Per-interval IPC 0.58, 0.76, 0.86, 0.45, 0.74 (all `opencode`, 98% user).
L1 iTLB misses are ~220 per kilo-instruction in every block (48-entry iTLB,
~17% miss rate on OpenCode's JIT code).

**Finding (fork configuration bug; fixed 2026-10-13, see the last entry):**
the L2 TLB is disconnected. `NeoverseMMU` (`configs/garfield/arm/neoverse_v2.py`)
overrides `itb` and `dtb` without `next_level=Parent.l2_shared`, which the
base `ArmMMU` sets (`src/arch/arm/ArmMMU.py`). In `config.ini` both L1 TLBs
have `next_level=Null`, and `mmu.l2_shared.accesses` is 0. Every L1 TLB miss
therefore goes straight to a page walk (34k walks per 1M instructions here).
This affects every Garfield O3 result, not only this study, so it is left
unchanged pending the user's decision; TLB-related numbers from this config
overstate the cost of TLB misses.

### 2026-10-08 — landing check on all 27 local checkpoints

`run_scripts/tasktrace/landing-all.sh` restores the first local checkpoint of every
task on the atomic core with the tracer, and `run_scripts/tasktrace/landing_summary.py`
compares the first switch's outgoing task and the derived slide with the
checkpoint's landing label (3M instructions each; 40M for the seven that had
not switched yet, all inside compilers, linkers or JIT code).

- **All 22 labelled checkpoints match** (pid, thread name, slide). Landings
  cover OpenCode's own threads, `git`, `compile`, `ld`, `cc1plus`,
  `rg.fence-real`, `find`, `python`, `chrome` and `docker`.
- One needed a rule: core-11870 landed while pid 1924 (`git`) was inside an
  `execve`; 229k instructions after the restore the trace records the exec
  that renames it to `false`, then the switch. The check accepts a rename by
  an exec recorded before the first switch.
- The five unlabelled checkpoints derive a slide and switch away from the
  idle task (axios-5892, bat-2835), `javac`'s `VM Thread` (gson-2134,
  lombok-3479) and OpenCode's `Bun Pool 0` (rubocop-13560).
- fastlane-20958 has only `cpt.1` locally; the scripts use the first `cpt.N`.

### 2026-10-08 — 5G atomic instructions of gin cpt.0: first tool calls

`runs/tasktrace/20261008-120444-gin-2121-atomic-5G` (current tracer). 5.0G
instructions, ~1.9 s simulated; the guest printed `RPOINT_REPLAY_ROUND 2`
and `3`. OpenCode's own log shows it initialising (`message=initialized`
at faketime 12:00:04.649) inside this window: although the dump was placed
0.29 s after `ROUND 1`, the harness was still starting its session.

| tool | input | pending | running | completed | logged | running→completed | guest time |
|---|---|---|---|---|---|---|---|
| `read` | `/testbed/render/reader.go` | 3052.3M | 3084.2M | 3255.1M | 3304.9M | 171M insts, 63.0 ms sim | 59 ms |
| `edit` | `/testbed/render/reader.go` | 4400.9M | 4539.3M | 4761.9M | 4805.2M | 223M insts, 78.8 ms sim | 45 ms |

During the `read`, OpenCode ran 75% of the instructions, `docker inspect`
(the replay driver's poller) 22%, the kernel 2%. During the `edit`: 80% /
17% / 2%.

Caveat on durations: the atomic CPU commits one instruction per cycle, so
simulated milliseconds here are not comparable with the live run's (4 ms
median per call on Graviton3); instruction counts are the meaningful unit.
Even so, 171M instructions for reading one 45-line file is large: it
includes OpenCode serialising and persisting the part on each state change
(three WAL page writes per change) and its JS runtime, not just the read.

Instruction share over the whole 5G: harness 76.3%, plumbing 17.4%, kernel
3.5%, other 1.7%, harness-child (snapshot `git`) 1.2%.

By thread (`tools.csv`, `run_top_threads`), the `read` span was OpenCode's
main JS thread 54%, `docker inspect` 23%, OpenCode's `JITWorker` threads 21%;
the `edit` span 73% / 18% / 8%. A fifth of the first tool call goes to JIT
compilation, consistent with cold code on the first use of a tool path.

### 2026-10-08 — first O3 window across a tool call (gin cpt.0)

`run_scripts/tasktrace/o3-window.sh gin-2121 2950000000 20000000 420000000 1000000`:
2.95G atomic instructions to just before the first tool call, 20M warmup,
then 420M O3 instructions in 1M-instruction stats blocks with the tracer on
(`runs/tasktrace/20261008-125928-gin-2121-o3window-read`). About 95k
instructions/s on O3; ~1.5 h in total. Region IPC 0.768.

The `read` tool call lands where the atomic run predicted (pending at
3051.3M, running 3081.9M, completed 3261.4M; 179M instructions running →
completed, 76% OpenCode, 23% `docker inspect`). The O3 timing moves events
by a few million instructions, not more.

Aggregates (summed instructions over summed cycles; MPKI = misses per 1000
instructions); "harness-only" = blocks where OpenCode ran at least 95% of the
instructions:

| intervals | n | IPC | L1I MPKI | L2 MPKI | cond. br MPKI | L1 iTLB MPKI |
|---|---|---|---|---|---|---|
| all | 420 | 0.77 | 4.1 | 12.8 | 6.7 | 107 |
| harness-only | 288 | 0.79 | 4.2 | 13.0 | 7.0 | 108 |
| ≥50% docker plumbing | 92 | 0.81 | 2.8 | 9.5 | 5.0 | 82 |
| harness: before tool pending | 67 | 0.69 | 6.6 | 14.8 | 10.2 | 175 |
| harness: pending→running | 29 | 0.66 | 7.6 | 16.9 | 10.2 | 200 |
| harness: running→completed | 127 | 0.81 | 3.2 | 13.1 | 5.3 | 80 |
| harness: after completed | 62 | 1.00 | 1.6 | 8.6 | 5.5 | 40 |
| blocks with a process switch | 58 | 0.62 | 5.9 | 17.6 | 7.9 | 149 |
| blocks with no switch | 253 | 0.91 | 2.6 | 9.7 | 5.4 | 69 |
| blocks with an exec | 4 | 0.50 | 8.2 | 20.0 | 12.2 | 169 |

Readings, with their limits:

- **The run-up to a tool call is the cold part of the harness.** While
  OpenCode handles the model response and prepares the call (before
  `pending`, and `pending`→`running`), IPC is 0.66–0.69 with twice the L1I
  and branch MPKI and 2–5× the iTLB misses of the steady part that follows.
  After the call completes the same process runs at IPC 1.00. This is
  consistent with code that is new to the run (first use of the tool path,
  JIT compilation) and matches the atomic run's 21% `JITWorker` share.
- **1M-instruction intervals that contain a process switch run at IPC 0.62
  against 0.91 for intervals without any switch**, with 2.3× the L1I MPKI,
  1.8× the L2 MPKI and 2.1× the iTLB MPKI. An interval holds ~1M
  instructions, so this mixes the switch itself, the new process's cold
  start and whatever phase caused the switch; finer intervals are needed to
  separate them.
- **Execs are the most expensive events** (IPC 0.50, n=4: all `docker
  inspect`, `sleep`, and `git` starting up).

Caveats: one checkpoint and one tool call; iTLB numbers are inflated by the
disconnected L2 TLB (decision 8 / the config finding above); interval
averages include the replay driver's polling, which is not agent work.
`virt_run.py` now flushes `intervals.csv` after every interval.

### 2026-10-08 — the container/cgroup/snapshot/read changes

- **No perturbation:** O3 pair (gin cpt.0, 1M warmup + 5M) with all new
  features → `IDENTICAL stats`, IPC 0.635.
- **Landing, all 27 local checkpoints, 3M atomic instructions each:** the 17
  that switch in the window match as before; the 5 that do not (inside
  `ld`, `cc1plus`, `rg.fence-real`, OpenCode) now match through the
  snapshot, which holds the landing task under its recorded name: **22 of 22
  in one pass.**
- **Snapshot (gin cpt.0):** 140 tasks. The OpenCode container holds the tool
  server (`python`, 1005) → `faketime` (1231, previously unnamed) →
  `opencode` (1235); a second container holds the orchestrator's `python`
  (1081); everything else is on the host. In framework-52684 the chain is
  `rg.fence-real` ← `opencode` ← `faketime` ← `python` ← `containerd-shim`
  (host).
- **The tools fence is not effective in the replay guest.** framework-52684
  landed inside a fenced `rg`: `rg.fence-real` has the same cgroup set as
  OpenCode, and no `cgroup.procs` write occurs in 400M instructions, so
  `fence-exec.sh` fell through (the fence mount is absent). Tool vs harness
  must rest on the `*.fence-real` names. `rg.fence-real` is a direct child of
  `opencode`, not of a `bash` tool, so OpenCode's own search tools spawn it.
- **Reads:** in framework-52684 OpenCode reads `/proc/self/statm` (shown as
  `/24/statm`, procfs relative to its mount) every ~10–25M instructions.
- **framework-52684, 400M atomic:** harness 71.0%, replay 21.6%, fenced
  tool 5.1%, harness children 1.5%, daemons 0.7%. Without replay, the
  harness is 90.5% and the tool 6.5%. Context switches: 53.6% between
  OpenCode's threads, 26.0% between the replay's Docker CLI threads.
- **Short O3 window, framework-52684:** restore, 2M warmup, 20M detailed in
  100K-instruction blocks (a few minutes). Region IPC 0.77. Aggregated over
  blocks: fenced `rg` (≥95% of a block) IPC 1.14, L2 MPKI 1.0; OpenCode IPC
  0.76, L2 MPKI 12.0; replay IPC 0.67; blocks containing a process switch
  (n=5) IPC 0.28, L2 MPKI 48.9; blocks without any switch (n=182) IPC 0.86,
  L2 MPKI 7.9. At 100K-instruction resolution the switch penalty is much
  sharper than at 1M (0.62 vs 0.91 in the gin window).

### 2026-10-08 — framework-52684: atomic round, then O3 across a `bash` tool call

Runs: `20261008-183432-framework-52684-atomic` (to the `ROUND 3` marker plus
2 minutes, 6.47G instructions) and `20261008-194138-framework-52684-o3window`
(`o3-window.sh framework-52684 4330000000 20000000 400000000 250000`, 400M
O3 instructions in 250K blocks, region IPC 0.911).

**Round structure.** The checkpoint restores inside `ROUND 1`. The terminal
prints `ROUND 2` at ~3.56G and `ROUND 3` at ~6.4G instructions. Round 1 is the
agent's start-up: OpenCode logs `initialized` at 3.16G and the first
`opencode.db-wal` writes begin at 3.50G, just before `ROUND 2`. Each later
round holds one model response and its tool call(s), so a whole round needs
the run to reach the next marker. (The progress line's "total committed" is
`totalOps()`, micro-ops, and runs ~12% above the instruction count the tracer
and the final stats use. Not a bug.)

**Tool calls found (atomic).** Round 2's call is `bash`: `ls /testbed && head
-20 /testbed/composer.json`. pending 3.681G, running 3.718G, completed 4.741G,
logged 4.825G. 1.02G instructions from running to completed (46 ms by the
guest clock) for a two-command shell line: harness 77%, replay poller 21%,
tool processes 1.2%. Process chain: `bash` (exec 4.406G), `basename`, then
`bash.fence-real`, `ls`, `head`, spanning only ~70M instructions. `grep`
pending at 6.36G (round 3). The fence is again not effective (no cgroup.procs
write).

**O3 window.** The same events land ~130M instructions later on O3 (bash exec
at 4.540G, `head` at 4.565G): the replay poller and timers are tied to
simulated time, so atomic positions only locate a call to within a few
hundred million instructions. Detailed (instruction-weighted):

| phase | blocks | IPC | L1I MPKI | L2 MPKI | br MPKI | iTLB MPKI |
|---|---|---|---|---|---|---|
| before the tool, harness only | 571 | 1.10 | 1.8 | 6.8 | 2.5 | 43 |
| tool processes span (4.540–4.573G) | 136 | 0.78 | 3.2 | 12.0 | 5.1 | 68 |
| blocks with any tool process | 54 | 0.59 | 5.0 | 14.3 | 8.7 | 102 |
| after the tool, harness only | 487 | 0.90 | 2.6 | 11.1 | 4.4 | 57 |
| blocks with a process switch | 82 | 0.50 | 7.9 | 23.6 | 10.7 | 188 |
| blocks with an exec | 8 | 0.59 | 6.7 | 17.0 | 11.6 | 69 |
| blocks with no event | 1355 | 1.01 | 1.8 | 8.0 | 3.2 | 44 |

The fork/exec chain of the tool is the slow part: each `exec` block runs at
IPC 0.4–0.7 and L2 MPKI 15–65 right after a fork/switch (`bash`, `basename`,
`bash.fence-real`, `ls`, `head`), recovering to ~0.7–0.9 within 1M
instructions. After the tool the harness stays slower than before it (0.90
against 1.10, L2 MPKI 11.1 against 6.8) for the remaining ~150M instructions
of the window, consistent with cache and TLB state displaced by the tool
processes and the next harness phase (not separated here).

Limits: one call, one checkpoint; the window ends (4.744G) before the call's
`completed` state, so `tool_end` is not in this O3 trace (use `--tail-insts`
and a longer window to catch it); iTLB figures still carry the disconnected
L2 TLB.

### 2026-10-09: framework-52684, user/kernel split across the `bash` call

`20261009-141720-framework-52684-o3window` (same restore, window and 250K
blocks as the 2026-10-08 O3 window; the core clock is 3 GHz, 333.3 ticks per
cycle, so cycles below are `ticks / 333.3`).

**Mode split.** Over the whole 4.74G-instruction trace, 85.5% user mode and
14.5% kernel mode. By role: harness 6.5% kernel, replay driver 43%, tool
processes 63%, harness children (`git`) 85%, kernel threads 100%. Slices
that end a context switch spend 14.5% in kernel mode on average (switches
within the harness 7.3%, within the replay driver 29%, replay to daemon 55%).

**Direct cost of a context switch** (676 switches in the O3 region): the
scheduler path (`__schedule` to `__switch_to`) takes a median of 1,815
instructions and 1,720 cycles (mean 2,945, p90 5,912; IPC 0.61), about
0.45% of the region's cycles and 2.3% of the kernel instructions executed
in the slices. During the tool's process churn (30 switches between 4.540G
and 4.573G) the path has the same instruction count (median 2,124 against
1,815) but takes 4,705 cycles against 1,650: the same code, cold. Switches
between OpenCode and the replay driver cost more (median 3.0k to 3.3k
instructions, mean 1.4 to 1.5 µs).

**Reading.** The scheduler itself is cheap. What makes switches expensive
is around it: intervals containing a switch run at IPC 0.60 against 1.00
without, with 30.5% of their instructions in kernel mode against 10.4%, yet
the scheduler path is only 2.1% of those intervals' instructions. So most of
the cost of a switch is the kernel work that causes it and the cold state
the next task finds, not the scheduling decision. Pure-harness intervals
have 1.7% (before the tool) and 2.0% (after) kernel mode; during the tool
span the figure is 30.4% (fork, exec, exit and page faults of `bash`, `ls`,
`head`).

Limits: one call in one checkpoint; the split is in instructions (a cycle
split by mode would need an exception entry/exit hook); the scheduler path
excludes the system call or interrupt that caused the switch and the next
task's first moments; the window still ends before the call's `completed`
state.

### 2026-10-13: Exec cross-check of the counters; L2 TLB connected

**Exec cross-check.** A short O3 window of framework-52684 (1M warm-up,
16.2M detailed) was rerun with
`--debug-flags=ExecEnable,ExecUser,ExecKernel,ExecMacro` between ticks
215.30G and 216.08G (828,936 committed instructions, 15 switches; output in
the session scratchpad, not kept). Classifying each line as kernel or user
by its PC alone, and locating the commits of `__schedule` and
`__switch_to`, the trace's `insts`, `uinsts` and `sched_insts` deltas match
the Exec trace exactly over all 14 intervals between switches (NOPs, 17,454
of them, excluded on the Exec side as O3's `totalInsts()` does). Event
ticks are 10–150 ns later than the Exec stamps: O3 Exec prints the tick at
which the instruction was fetched (`src/cpu/o3/fetch.cc`), the tracer the
tick at commit. Side note: the atomic CPU counts NOPs in `totalInsts()`, O3
does not, so the global count changes basis slightly across a core switch.

**L2 TLB connected.** `NeoverseMMU` now sets `next_level=Parent.l2_shared`
on `itb` and `dtb` (user's change). Every O3 run cited above predates it:
their iTLB/dTLB miss and page-walk figures, and to a lesser degree their
IPC, are not comparable with runs from now on.
