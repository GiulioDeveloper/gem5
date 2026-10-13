# Guest task and tool-call tracing: user guide

How to see, inside a gem5 restore of an agentic checkpoint, **which guest
process or thread is running, when context switches, forks, execs and exits
happen, and when each OpenCode tool call starts and ends**, all stamped in
simulated ticks and in committed instructions, and how to line that up with
microarchitectural statistics.

This guide covers using and extending the infrastructure. The reasoning
behind each design choice, the bugs found while building it, and every
validation run are in the research log:
[`docs/research-log/agentic/2026-10-08-task-tracer.md`](../research-log/agentic/2026-10-08-task-tracer.md).

---

## 1. What it gives you

For one restored checkpoint, a run with tracing produces:

| output | what it is |
|---|---|
| `tasktrace.jsonl` | a snapshot of every guest process and thread at the restore, then one JSON line per guest event: context switch, fork, exec (with path and argv), rename, exit, every `write()` (with payload) and `read()` (without data) of OpenCode, and every write to a `cgroup.procs` file |
| `intervals.csv` + `stats.txt` | optional: gem5 stats dumped every N instructions of the detailed region, with each block's tick and instruction range |
| `analysis/*.csv`, `summary.md` | per process, per container, per tool call, per context-switch cause, per stats interval and event-aligned tables (from `trace_analysis.py`) |
| `analysis/schedule.html` | an interactive timeline of the run (from `trace_view.py`) |

Everything lives in this repository. Nothing in gem5-infra is needed beyond
the checkpoint files it produced.

## 2. The pieces

```
              gem5 run (virt_run.py --task-trace ...)
 ┌─────────────────────────────────────────────────────────────┐
 │ task_trace.py ──► kernel_layout.py (gdb on vmlinux)         │
 │      │                                                      │
 │      ▼                                                      │
 │ ArmLinuxTaskTracer (C++ SimObject)                          │
 │   PC events on guest kernel functions ──► tasktrace.jsonl   │
 │ --stats-interval-insts ──► stats.txt blocks + intervals.csv │
 └─────────────────────────────────────────────────────────────┘
                 host Python, after the run
 trace_analysis.py ──► analysis/{processes,writes,tools,blocks,aligned}.csv, summary.md
 trace_view.py     ──► analysis/schedule.html, schedule.view.json
```

| file | role |
|---|---|
| `src/arch/arm/linux/task_tracer.{hh,cc}` | the tracer, `gem5::ArmISA::LinuxTaskTracer` |
| `src/arch/arm/ArmLinuxTaskTracer.py` | its SimObject declaration and parameters |
| `src/cpu/base.hh` and the commit code of the simple, O3, Minor and KVM CPUs | the never-reset user-mode instruction counter (`BaseCPU::userInsts()`) behind `uinsts` |
| `src/arch/arm/SConscript` | registers the source, the SimObject and the `TaskTracer` debug flag |
| `configs/garfield/arm/kernel_layout.py` | reads struct offsets from the guest vmlinux |
| `configs/garfield/arm/task_trace.py` | `--task-trace*` flags; builds the tracer and attaches it to the board |
| `configs/garfield/arm/virt_run.py` | the restore script; also `--stats-interval-insts` and `--tail-insts` |
| `configs/garfield/arm/trace_analysis.py` | host-side analysis (stdlib only) |
| `configs/garfield/arm/trace_view.py`, `trace_view.html` | interactive schedule viewer generator and template |

## 3. Prerequisites

- **A gem5 build with the tracer:** `scons build/ARM/gem5.opt -j$(nproc)`.
- **`gdb` on the host.** `kernel_layout.py` uses it to read the vmlinux's
  debug info (an x86 gdb reads the aarch64 vmlinux fine).
- **The guest's own vmlinux,** with symbols and debug info: for the agentic
  checkpoints, `gem5-ckpts/rpoint_ckpts/agentic/kernel/arm64-linux-kernel-6.8.12-1.0.0`.
  It must be the exact kernel the guest booted; it is already what
  `--kernel` points at.
- **Host Python 3** for the analysis scripts (no third-party packages).

## 4. Running a traced restore

All commands run from the repository root. The variables below are used
throughout:

```sh
AGENTIC=./gem5-ckpts/rpoint_ckpts/agentic
TASK=<task>          # a checkpoint directory name without the agentic- prefix
CPT=$AGENTIC/checkpoints/agentic-$TASK/cpt.0
COMMON="--disk-img $AGENTIC/images/rpoint-ubuntu-24.04-v21.img \
  --kernel $AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0 \
  --bootloader $AGENTIC/bootloader/boot_v2_qemu_virt.arm64 \
  --release kvm-host --progress-interval 10kHz"
```

### 4.1 Event trace only, on the fast atomic core

The quickest way to see what a checkpoint is doing. Atomic runs at about
1.6–1.9 million instructions per second.

```sh
./build/ARM/gem5.opt --outdir=runs/trace-$TASK configs/garfield/arm/virt_run.py \
  --restore-dir $CPT $COMMON \
  --atomic-only --atomic-max-insts 2000000000 \
  --task-trace
```

### 4.2 Detailed O3 window with per-interval stats

Fast-forward on the atomic core (`--settle-insts`), warm up, then simulate a
detailed region on the Neoverse V2 model in fixed-size stats blocks. O3 runs
at about 95–200 thousand instructions per second.

```sh
./build/ARM/gem5.opt --outdir=runs/o3-$TASK "--stats-file=stats.txt?desc=False" \
  configs/garfield/arm/virt_run.py --restore-dir $CPT $COMMON \
  --settle-insts <S> --warmup-insts 20000000 \
  --detailed-insts <N> --stats-interval-insts 1000000 \
  --tail-insts 100000000 \
  --task-trace
```

`?desc=False` drops stat descriptions; a block is then about 320 KB for this
configuration, so the file size is about 320 KB × N / block size.

### 4.3 Flags

| flag | meaning |
|---|---|
| `--task-trace` | attach the tracer; writes `<outdir>/tasktrace.jsonl` |
| `--task-trace-process NAME` | process whose `write()` calls are recorded with file path and payload, and whose `read()` calls are recorded with file path, size and offset (default `opencode`; empty disables both) |
| `--task-trace-slide HEX` | expected KASLR slide; the tracer derives the slide itself and stops if it differs. Default: `landing.kaslr_slide` from `<restore-dir>/provenance.json`, if present |
| `--stats-interval-insts N` | dump and reset stats every N committed instructions of the detailed region and write `intervals.csv`; 0 (default) dumps once |
| `--tail-insts M` | after the detailed region, switch back to the atomic core and run M more instructions, still traced, to catch events that complete after the region (a tool call cut in half) |

Without `--task-trace`, `virt_run.py` behaves exactly as before.

### 4.4 Helper scripts

`run_scripts/tasktrace/` (untracked, next to `run_agent.sh`) wraps the
common runs; each writes to `runs/tasktrace/<stamp>-<task>-<kind>/`. Run
them from the repository root; `<task>` is a checkpoint name without the
`agentic-` prefix.

| script | what it runs |
|---|---|
| `atomic.sh [task] [max-insts] [virt_run args]` | an atomic-only traced restore (4.1); `GEM5_OPTS="--debug-flags=TaskTracer"` passes gem5 options |
| `o3-window.sh TASK SETTLE WARMUP DETAILED INTERVAL [virt_run args]` | a detailed window with stats intervals (4.2), stats without descriptions |
| `o3-pair.sh [task] [warmup] [detailed]` | the no-perturbation check: the same window with and without the tracer, diffing `stats.txt` (section 9). `PAIR_ON_ARGS=` runs the plain configuration twice, a determinism check |
| `landing-all.sh [insts] [parallel]` | the landing check over every local checkpoint (section 9), summarized by `landing_summary.py`; `TASKS="<task> ..."` limits the tasks |

### 4.5 Choosing where to put an O3 window

Detailed simulation is slow, so find the interesting point on the atomic
core first:

1. Run 4.1 long enough to cover the event you care about.
2. Run `trace_analysis.py` (section 7) and read `analysis/tools.csv` or
   `processes.csv` for the instruction count of the event.
3. Restore again with `--settle-insts` set a margin before that count
   (see below) and a detailed region that covers it.

The atomic run is deterministic, but the O3 run is not the same schedule:
the replay driver's polling and guest timers follow simulated time, so
events move, by anything from a few million to over a hundred million
instructions. Use a generous settle margin (hundreds of millions of
instructions early) and a detailed region long enough to hold the whole
call; a window that ends first misses the call's `completed` state, so add
`--tail-insts` to see it finish. Locate events in the O3 trace itself before
choosing phase boundaries; do not reuse the atomic positions.

**Rounds.** The restore starts inside `RPOINT_REPLAY_ROUND 1`, which is the
agent's start-up. The guest prints `RPOINT_REPLAY_ROUND N` on
`<outdir>/board.terminal` (empty until the first marker); each later round
holds one model response and its tool calls. To cover a whole round, run
the atomic core until the next marker appears, then stop (SIGINT keeps the
flushed `tasktrace.jsonl`). Rounds are billions of instructions apart. The progress line's
"total committed" counts micro-ops and runs about 12% above the
instruction count used by the trace.

## 5. How the tracer works

### 5.1 Hooks

`LinuxTaskTracer` places a gem5 **PC event** on the first instruction of a
handful of guest kernel functions. A PC event fires when that instruction is about to
commit (O3 services them in commit, the simple CPUs before execution), so
it never fires on wrong-path instructions, and the function's arguments are
in `x0..x2`. PC events live in `System` and move with the thread across
`m5.switchCpus`, so tracing is continuous from atomic to O3 and back.

| kernel function | arguments read | event written |
|---|---|---|
| `__schedule(mode)` | none; remembers the tick and instruction count | nothing; the next `switch` reports what the scheduler spent (5.4) |
| `__switch_to(prev, next)` | x0, x1 = task_structs | `switch` |
| `wake_up_new_task(p)` | x0 = new task; parent = current | `fork` |
| `__arm64_sys_execve(regs)` / `__arm64_sys_execveat(regs)` | user pointers to filename and argv | nothing yet; remembered for the exec |
| `perf_event_comm(task, exec)` | x0 = task (new name already set), x1 = exec flag | `exec` (with the remembered path and argv) or `rename` |
| `do_exit(code)` | x0 = code; task = current | `exit` |
| `vfs_write(file, buf, count, pos)` | file path via `file->f_path.dentry`, user buffer | `write`: every write of `--task-trace-process`'s threads, and writes to files named in `write_files` (default `cgroup.procs`) by any process |
| `vfs_read(file, buf, count, pos)` | file path, size asked for, offset `*pos` | `read` for `--task-trace-process`'s threads; at entry, so no data |

At start-up, before any hook fires, the tracer also walks the kernel's
process list (`init_task.tasks`) and each process's thread ring
(`thread_node`) and writes one `snapshot` event with every process and
thread alive at the restore. That fills in tasks that never run during a
window, such as sleeping parents and container shims.

Things about these choices that are not obvious:

- **Execs are reported from `perf_event_comm`, not `__set_task_comm`.** In
  this kernel, `begin_new_exec` contains an inlined copy of
  `__set_task_comm`, so the out-of-line function only sees
  `prctl(PR_SET_NAME)` renames. Both paths end in an out-of-line call to
  `perf_event_comm`. Because an exec is only reported once the kernel has
  committed to the new image, failed attempts (PATH probing) never appear.
- **The current task** is read from `SP_EL0`, which the arm64 kernel uses to
  hold `current` while at EL1.
- **`vfs_read` is out of line** in this kernel: both `read()` (`ksys_read`)
  and `pread()` (`ksys_pread64`) call it. It is hooked at entry, where the
  buffer is still empty, so a read event marks *when* and *what*, not the
  data. Calls through other paths (`readv`, io_uring) are not seen.
- **File paths** are rebuilt from the dentry chain up to the root of the
  file's filesystem. Mount points are not crossed, so a file in procfs
  appears as `/14/statm`, and a file in a container's overlay filesystem
  appears relative to the container's root (`/testbed/render/reader.go`).
  Anonymous files keep their bare name (`[eventfd]`, `[timerfd]`).

### 5.2 Reading guest memory without disturbing the simulation

The tracer never uses gem5's MMU. gem5's functional address translation
(`TranslatingPortProxy`) still performs a timing-visible TLB lookup
(`ArmISA::MMU::getTE`), which changes TLB replacement state and statistics
and can fill the L1 TLB from the L2. A tracer built on it measurably
changed O3 IPC and thousands of statistics.

Instead the tracer walks the guest's own stage-1 page tables in software
(EL1&0, 4 KiB granule, `TTBR0/1_EL1` chosen by VA bit 63, start level from
`TCR_EL1.T0SZ/T1SZ`) and reads descriptors and data from physical memory
through `System::physProxy`. Permissions are not checked, so user buffers
are readable from the kernel-side hooks. Kernel addresses are always
translated through `swapper_pg_dir` (located while deriving the slide)
rather than `TTBR1_EL1`: a restore that lands at EL0 has `TTBR1_EL1`
pointing at KPTI's trampoline table, where the kernel is not mapped, and
the start-up snapshot runs exactly then. A failed read is recorded as
`null` or an empty string; it never stops the simulation.

### 5.3 Finding the kernel: KASLR slide and struct offsets

**KASLR slide.** The guest kernel is relocated at boot. The tracer derives
the slide from the restored state in `startup()`, using the method of
RPoint's `landing.py`: `TTBR1_EL1` holds the physical address of
`swapper_pg_dir` (in the kernel) or `tramp_pg_dir` (at EL0, KPTI); each
candidate gives a physical base for the kernel image; the one whose
`init_task.comm` reads `swapper/0` is right; then
`slide = pa_text + kimage_voffset − link(_text)`. Hook addresses are the
vmlinux symbol addresses plus the slide. This works on every local
checkpoint, including the five without a recorded landing label.

**Struct offsets.** The tracer needs the offsets of a few fields of
`task_struct` (`pid`, `tgid`, `comm`, `group_leader`, `real_parent`, `mm`,
`flags`, `tasks`, `thread_node`, `nsproxy`, `cgroups`), `file` (`f_path`),
`dentry` (`d_name`, `d_parent`), `qstr` (`name`) and `pt_regs` (`regs`). `kernel_layout.py`
asks gdb to evaluate `&((struct T *)0)->field` on the vmlinux, which follows
anonymous unions and nested members. Run it by hand to see them:

```sh
python3 configs/garfield/arm/kernel_layout.py $AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0
```

The guest kernel was built with reduced debug info
(`-femit-struct-debug-baseonly`), so only some structs have a layout;
`mm_struct`, `linux_binprm`, `path` and the cgroup structs do not. That is
why exec paths come from the execve syscall arguments rather than
`mm->exe_file`, why there are no cgroup *names* (only cgroup-set
identities, below), and why two layouts are assumed: `struct path` is
`{ mnt; dentry; }` (dentry at +8) and `struct list_head` is
`{ next; prev; }`, both unchanged since Linux 2.6. The kernel-thread flag
`PF_KTHREAD` (`0x00200000`) is a kernel constant, not a layout. A missing field is fatal: a guessed offset would
produce plausible garbage.

### 5.4 Instruction counts

Every event carries `insts` = `BaseCPU::totalNumSimulatedInsts()`: the sum
over all CPUs (atomic and O3) of committed instructions since the restore.
It keeps counting across core switches and is not reset by
`m5.stats.reset()`. `intervals.csv` uses the same count, which is what lets
events and stats blocks be joined.

Every event also carries `uinsts`, the global count of instructions that
committed in **user mode** (EL0), kept by a counter added to `BaseCPU`
(`userInsts()`, incremented next to the `numUserInsts` stat in the simple,
O3, Minor and KVM CPUs; unlike the stat it is never reset). The difference
`insts - uinsts` is the kernel-mode (EL1) work. Both are counted on the
same basis, which matters on O3: its `insts` leaves out NOPs and instruction
prefetches, as gem5's `totalInsts()` always has (the atomic CPU counts
NOPs, so atomic and O3 counts differ slightly in basis; NOPs were about 2%
of instructions in one checked window), while the `commitStats`
`numInsts` and `numUserInsts` stats include them, so those stats must not be
mixed with `insts` (use `numUserInsts / numInsts` for a ratio). Between two events it
splits any stretch of execution into user and kernel instructions.

A `switch` event also carries `sched_insts` and `sched_ticks`: the
instructions and simulated time from the entry of `__schedule()` to
`__switch_to()` on the same CPU. `__schedule()` is the one function every
path that can switch tasks goes through (`schedule()`, preemption, idle),
and it runs only kernel code with interrupts off, so this is the scheduler's
own direct cost: picking the next task and the context switch up to the
register swap. It does not include what led to the switch (the system call
or interrupt that blocked the task, which is the kernel part of the slice
the switch ends) or the first moments of the next task. A `__schedule()`
call that keeps the same task never reaches `__switch_to` and produces no
event. `sched_ticks` is simulated time: meaningful on the detailed CPU, but
on the atomic CPU every instruction takes one cycle, so use `sched_insts`
there.

### 5.5 Determinism and overhead

- Atomic runs of the same checkpoint produce identical traces.
- An O3 run with the tracer has byte-identical `stats.txt` to one without it
  (host-time stats aside).
- Splitting the detailed region into stats intervals does not change its
  timing either (same total IPC).

## 6. The trace file: `tasktrace.jsonl`

One JSON object per line, flushed per line so a crashed run keeps its trace.
Every line has `tick` (gem5 ticks, 1 ps), `insts`, `uinsts` (user-mode
subset of `insts`, 5.4) and `event`. Traces from before `uinsts` existed lack
it; the analysis then skips the user/kernel split.

A **task** object is
`{pid, tgid, ppid, comm, process, kernel_thread, kthread, ns, cg}`:

| field | meaning |
|---|---|
| `pid` | thread id |
| `tgid` | process id |
| `ppid` | `real_parent`'s tgid |
| `comm` | thread name (15 characters at most) |
| `process` | thread-group leader's name |
| `kernel_thread` | `mm == NULL`. Also true for a user process in its last moments after `exit_mm`; use `kthread` instead |
| `kthread` | the `PF_KTHREAD` flag: a kernel thread |
| `ns` | the task's namespace set (`task_struct.nsproxy`), as a hex string. Tasks with the same value share all their namespaces, i.e. are in the same container. `0x0` for a task that has already released its namespaces while exiting |
| `cg` | the task's cgroup set (`task_struct.cgroups`), as a hex string. Same value, same cgroups in every hierarchy |

`ns` and `cg` are kernel pointers used as identifiers: comparable within one
run, meaningless across runs. They are strings because JSON readers in
JavaScript lose 64-bit integers.

| `event` | extra fields |
|---|---|
| `start` | `kaslr_slide` (first line) |
| `snapshot` | `tasks` (every process and thread alive at the restore), `count` (second line) |
| `switch` | `prev`, `next` (tasks), `same_mm` (true for a switch between threads of one process), `sched_insts`, `sched_ticks` (scheduler cost, 5.4; absent if the switch was not preceded by a `__schedule` seen after the restore) |
| `fork` | `parent`, `child`; `child.tgid == parent.tgid` means a new thread |
| `exec` | `task` (with its new name); `path`, `argv` when the execve call was seen after the restore |
| `rename` | `task` (with its new name) |
| `exit` | `task`, `code` |
| `write` | `task`, `file` (the file's own name), `path`, `count`, `truncated`, `data` |
| `read` | `task`, `file`, `path`, `count` (bytes asked for), `pos` (offset, or null for pipes and other streams) |

Guest strings are byte strings: bytes outside printable ASCII are written as
`\u00XX`. Recover the original bytes in Python with `s.encode("latin-1")`.

Examples:

```json
{"tick":209306074077,"insts":1756030,"event":"switch","same_mm":true,
 "prev":{"pid":1308,"tgid":1235,"ppid":1231,"comm":"JITWorker","process":"opencode","kernel_thread":false},
 "next":{"pid":1303,"tgid":1235,"ppid":1231,"comm":"JITWorker","process":"opencode","kernel_thread":false}}
{"tick":...,"insts":69714242,"event":"exec","task":{"pid":1748,...,"comm":"docker",...},
 "path":"/usr/bin/docker","argv":["docker","inspect","eed938611d47..."]}
```

## 7. Analysis: `trace_analysis.py`

```sh
python3 configs/garfield/arm/trace_analysis.py <outdir> [--window K]
```

Writes `<outdir>/analysis/` and prints `summary.md`.

### 7.1 Outputs

| file | contents |
|---|---|
| `summary.md` | event counts per million instructions and per simulated ms, instruction share per role, top processes, tool calls |
| `processes.csv` | per process: names over its life (e.g. `python3\|docker` = fork then exec), role, exec path and argv, instructions run split into user and kernel mode, switch-ins |
| `containers.csv` | one row per container: its label and member processes |
| `switches.csv` | context switches counted by cause (7.4), with the scheduler's cost (instructions p50/p90/mean, simulated ns) and the kernel-mode share of the time slice each switch ended; first row `ALL` |
| `writes.csv` | every recorded write: the traced process's, and `cgroup.procs` writes by any process |
| `reads.csv` | every recorded read of the traced process (path, size, offset) |
| `tools.csv` | one row per OpenCode tool call (7.3) |
| `blocks.csv` | per stats interval: IPC, user fraction (from gem5 stats) and `user_frac_trace` (from the trace), scheduler instructions per kilo-instruction (`sched_pki`), L1I/L1D/L2 MPKI, conditional-branch and BTB-caused mispredicts per kilo-instruction, iTLB/dTLB misses and page walks per kilo-instruction, dominant process and role, instruction share per role, the events inside it |
| `aligned.csv` | per event kind, each metric averaged over the intervals at offsets −K..+K from the interval holding the event, beside the mean over all intervals |

`blocks.csv` and `aligned.csv` need a run with `--stats-interval-insts`.

**Who ran when.** Between two `switch` events the CPU belongs to the first
switch's `next` task (equivalently, to the second switch's `prev`).
Instructions executed in interrupt or kernel context on behalf of a task are
counted to that task: in Linux a system call, page fault or interrupt runs
in the context of whichever task is current, under that task's own pid, and
the scheduler runs on the task that is giving up the CPU. So thread A
followed directly by thread B with no kernel segment between them is the
normal picture. Only kernel threads (`kworker`, `rcu_*`, ...) have pids of
their own, and they are the `kernel` role.

**User and kernel mode.** Each time slice also carries its user-mode
instruction count (`uinsts` difference), so every slice, process, role and
tool call splits into user and kernel instructions (`summary.md`,
`processes.csv`, `tools.csv`: `run_user_insts`, `run_kernel_insts`). The
trace records totals per slice, not where inside it the transitions
happened; where a range cuts a slice, its user instructions are assumed
spread evenly over it. `user_frac_trace` in `blocks.csv` is computed that way
and `summary.md` reports its mean absolute difference from gem5's own
`numUserInsts`-based `user_frac` as a check.

**Event kinds** used in `blocks.csv` / `aligned.csv`: `switch_thread`,
`switch_process`, `switch_kernel`, `fork_thread`, `fork_process`, `exec`,
`exit`, `rename`, `write`, `read`, `fence` (a `cgroup.procs` write),
`tool_start`, `tool_end`.

### 7.2 Roles and containers

Every process gets one role (the first rule that matches):

| role | rule |
|---|---|
| `idle` | pid 0 |
| `kernel` | `kthread` (`PF_KTHREAD`); traces without the flag: kthreadd and its children |
| `harness` | the `opencode` process (all its threads: main JS thread, `JITWorker`, `Bun Pool N`, `HTTP Client`, ...) |
| `tool` | `bash.fence-real` / `rg.fence-real` and their descendants: OpenCode's subprocess tools |
| `harness-child` | anything else OpenCode started, e.g. its snapshot `git` |
| `daemon` | `dockerd`, `containerd*`, `runc`, systemd services and similar |
| `replay` | any other user process on the guest host: the model-free replay driver (`python3`), its `docker inspect` polls, `watch_rounds.sh`, `sleep`, `make`, `uv` |
| `framework` | any other process inside a container: the tool server (`python`), `faketime`, the orchestrator's model proxy |
| `other` | unclassified (only in traces without namespaces) |

A process's role follows its latest name (a fork child is named after its
parent until it execs). Ancestry comes from the snapshot, `ppid` in every
task record, and fork events.

**Containers.** Processes are grouped by `ns`. The group holding pid 1 is
the **guest host**; the one holding `opencode` is the **OpenCode
container** (the SWE-bench task image, where OpenCode, its tools and
`/testbed` live); any other group entered under a `containerd-shim` is a
container named by its identifier (in the replay, the orchestrator
container with the model proxy). Host services that systemd sandboxes into
private namespaces (`systemd-resolved`, ...) count as host.

**The tools fence is not effective in the replay guests.** OpenCode's
`fence-exec.sh` moves `bash`/`rg` into a separate "tools" cgroup before
exec'ing `bash.fence-real`/`rg.fence-real`, but only when
`/benchmark-fence/tools` is mounted. In the replay guests a running
`rg.fence-real` has the same cgroup set as OpenCode, and no `cgroup.procs`
write occurs, so the fence fell through. The `tool` role therefore rests on
the `*.fence-real` names, which `fence-exec.sh` applies either way;
`summary.md` states the fence verdict for every trace.

**Replay processes are not agent work.** The replay driver runs
`docker inspect` on the orchestrator container roughly every 50 ms of guest
time to check it is still running (framework `sweagent_driver.py`,
`_orchestrator_running`); each poll is a fresh Docker CLI process of about
40M instructions. `summary.md` reports role shares with and without
`replay`, and `tools.csv` gives each call's instructions without replay.

### 7.3 Tool calls

OpenCode stores its session in SQLite with write-ahead logging
(`opencode.db-wal`). Every message part is a JSON row, and each state change
of a tool part (`pending` → `running` → `completed` | `error`) is a
`write()` of the 4 KiB page holding that row, which the tracer records. When
a call finishes, OpenCode also prints a `tool_use` JSON line to its event
log (`agentic-benchmark-opencode.log`), recorded as `logged`.

`tools.csv` columns:

| column | meaning |
|---|---|
| `tool`, `input` | tool name; file path or shell command |
| `kind` | `in-process`, or `subprocess (<names>)` when a fenced tool process ran during the call. Observed, not inferred from the tool's name |
| `io`, `io_insts` | the call's own file I/O: the first `read` or `write` of its file by the harness while it runs (for `read`/`edit`-style tools) |
| `run_agent_insts` | running → completed instructions excluding `replay` processes |
| `pending_insts`, `running_insts`, `completed_insts`, `error_insts`, `logged_insts` | instruction count at the first write showing that state |
| `run_insts`, `run_ms` | running → completed, in instructions and simulated ms |
| `start_ms`, `end_ms` | the call's own guest-clock timestamps (ms since the epoch; the guest runs under `faketime` pinned to 2026-08-19 12:00:00) |
| `run_share_<role>` | share of the running span's instructions taken by each role |
| `run_top_threads` | the five threads that ran most during the span |

A page also carries neighbouring rows, some stale, so a state counts from
its first appearance. Rows are parsed as brace-balanced JSON objects; a row
cut short at the page end is read with field regexes instead.

OpenCode's `read`, `edit`, `write` and `todowrite` run inside the
`opencode` process: they create no process, and their file I/O goes through
Bun's thread pool (`Bun Pool N`). An `edit`'s file write appears in
`writes.csv` and as `io_insts` (e.g. a source file under `/testbed`), and a
`read`'s file read in `reads.csv` and as `io_insts`. `bash` runs as a
separate process (`bash.fence-real`), and so does ripgrep
(`rg.fence-real`): it can be a direct child of `opencode`,
so OpenCode's own search tools spawn it too. That is why `kind` is observed
rather than derived from the tool's name.

### 7.4 Two views of "tool call"

- **Framework view:** a tool call is what the model asked for, with the
  start and end OpenCode records (`tools.csv`). In-process tools are harness
  work; only fenced subprocesses are tool execution.
- **CPU view:** what matters is every change of execution context,
  whoever causes it. `switches.csv` counts context switches by cause: `within
  <role>` for a switch between threads of one process, `<role> -> <role>`
  otherwise. In the traces so far, most switches are inside
  OpenCode (its JIT, I/O pool and HTTP threads) or inside the replay
  driver's Docker CLI processes; fenced tools contribute few.

Use the framework view to say what the agent was doing, and the CPU view
(switch, fork and exec events, by cause) as the unit of disruption.

### 7.5 Aggregating stats correctly

`blocks.csv` holds per-interval ratios. To compare groups of intervals,
aggregate the raw counts (sum of instructions over sum of cycles for IPC;
sum of misses over sum of instructions for MPKI) rather than averaging the
ratios, which over-weights short or unusual intervals. In Python:

```python
import sys; sys.path.insert(0, "configs/garfield/arm")
import trace_analysis as ta
blocks = ta.load_blocks(Path(outdir))   # raw counts per interval
```

gem5 leaves a stat out of a block when it stayed at zero; `load_blocks`
treats a missing stat as 0.

## 8. Interactive timeline: `trace_view.py`

```sh
python3 configs/garfield/arm/trace_view.py <outdir> [-o out.html] [--fragment]
```

Writes `<outdir>/analysis/schedule.view.json` (compact view model) and a
self-contained `<outdir>/analysis/schedule.html`. Open the HTML in a
browser; its *Open view.json* button loads any other run's
`schedule.view.json`, so one page serves every run. `--fragment` omits the
`<!doctype html>` wrapper for hosts that add their own.

The page shows:

- a whole-run strip coloured by the role that ran most of each pixel, with
  the tool calls under it; drag on it to select a range;
- a tool-call track (faint: pending, solid: running → completed, tick: the
  JSON log line); click a call to zoom to it;
- a CPU track: which task held the single core;
- one lane per process name (or per process), coloured by role, with exec
  (triangle), fork (dot), exit (bar), tool file I/O (square) and cgroup
  move (diamond) marks;
- *Hide replay* removes the replay driver's lanes and dims its share of the
  CPU track;
- hover details for every bar and mark; scroll to zoom, drag to pan,
  double-click for the whole run; an instruction or simulated-ms axis;
- when the trace has `uinsts`: each bar's **darker bottom band** is the
  kernel-mode share of that time slice (a proportion, not a position: the
  order inside a slice is not recorded), the **dark end** of a bar is the
  scheduler's own path (`__schedule` to the switch), and *Plain* turns both
  off; the header adds kernel-mode and scheduler-path shares;
- the same data as tables (tool calls with how they ran, a scheduler cost
  per kind of switch, processes with role, container and kernel-mode share).

Roles and tool calls come from `trace_analysis.py`, so both tools agree.

## 9. Validation you can repeat

| check | how | expected |
|---|---|---|
| **Landing** | restore each checkpoint with the tracer for a few million atomic instructions; compare the first `switch`'s `prev` task and the derived slide with `provenance.json`'s `landing`; if no switch happens in the window, the landing task must be in the start-up snapshot under its recorded name | same pid and thread name, same slide. A rename by an exec recorded before the first switch is legitimate (a checkpoint can land mid-exec). All 22 labelled local checkpoints match in one 3M-instruction pass |
| **No perturbation** | the same short O3 window (e.g. 1M warmup + 5M detailed) with and without `--task-trace`; diff `stats.txt` ignoring `host*` lines | identical |
| **Determinism** | two atomic runs of the same window | identical traces |
| **Intervals** | the same detailed region with and without `--stats-interval-insts` | same region IPC |
| **User/kernel split** | `summary.md` after a run with `--stats-interval-insts` | `user_frac_trace` agrees with gem5's `user_frac` (small mean absolute difference); user plus kernel instructions equal the span |

The last runs used for these checks are listed in the research log.

## 10. Debugging

- `--debug-flags=TaskTracer` (a gem5 option, so it goes *before* the config
  script) prints the derived slide and image base, every hook address, and
  every `vfs_write` call with the calling thread and size, whether or not
  it is recorded.
- **No `switch` for a while** is normal inside compilers, linkers and JIT
  code; a 4 ms scheduler tick is about 10M instructions at these speeds.
- **The run stops with "KASLR slide … disagrees"**: the expected slide
  (from `provenance.json` or `--task-trace-slide`) does not match the
  restored state, i.e. the checkpoint and its metadata do not belong
  together, or the vmlinux is not the guest's kernel.
- **"cannot derive the KASLR slide"**: `TTBR1_EL1` points at neither
  candidate page directory, almost always because `--kernel` is a different
  kernel from the one the guest booted.
- **`kernel_layout.py` reports unresolved fields**: the vmlinux lacks debug
  info for that struct; see 5.3 before changing the field list.

## 11. Extending

### Another hook

1. Find the function in the vmlinux (`nm <vmlinux> | grep <name>`) and check
   it is not inlined at the call sites you care about. With no aarch64
   disassembler on the host, decode its callers' `bl` targets from the ELF
   bytes; the research log (decision 8) shows how.
2. Add a handler `void myHook(ThreadContext *tc)` to `LinuxTaskTracer`,
   register it in `startup()` with `add("symbol", &LinuxTaskTracer::myHook)`,
   read arguments from `int_reg::X0..`, and write an event with
   `begin("name")`, `writeTask(...)`, `end()`.
3. If it needs new struct fields: add them to `OFFSETS` in
   `kernel_layout.py` and as `Param.Unsigned` in `ArmLinuxTaskTracer.py`
   (the names must match; `task_trace.py` passes the layout through as
   keyword arguments).
4. Read guest memory only through `readVirt` / `readU64` / `readString`,
   never through a `TranslatingPortProxy`, and re-run the no-perturbation
   check.


### Another guest kernel or workload

- A different kernel only needs its own vmlinux: the slide and offsets are
  derived from it. Symbols the tracer hooks must exist (it stops if one is
  missing).
- The analysis's roles are specific to the OpenCode replay (`HARNESS`,
  `TOOL_ROOTS`, `PLUMBING` at the top of `trace_analysis.py`). For another
  workload, change those and the `--task-trace-process` name.

## 12. Known limits and open issues

- **User/kernel split is per time slice.** Totals are exact per slice; where
  the transitions fall inside a slice is not recorded (ranges that cut a
  slice assume an even spread), and the split is in instructions, not
  cycles. Cycles per mode would need a hook on exception entry and return.
- **Scheduler cost is the path from `__schedule` to `__switch_to` only.**
  It leaves out the kernel work that caused the switch (system call,
  interrupt, wake-up) and the first moments of the next task; the kernel
  share of the slice a switch ends is the wider view of that cost.

- **One CPU.** The guest has one vCPU, so switches are inflated relative to
  a multi-core machine and "who ran when" is a single timeline.
- **No cgroup or container names.** Only identities (`ns`, `cg`) are
  available with this kernel's reduced debug info; containers are labelled
  by their members.
- **The tools fence is not active in the replay guests** (7.2), so tool vs
  harness rests on process names.
- **Execs whose syscall entry happened before the restore** have no path or
  argv (only the new name).
- **Reads are recorded without data**, and only through `vfs_read`
  (`read`, `pread`); `readv` and io_uring reads are not seen. Paths do not
  cross mount points.
- **Replay infrastructure in the measurement.** The replay driver's
  `docker inspect` polling is roughly a fifth of instructions in
  the traces so far and shares the vCPU with OpenCode. It is its own role
  (`replay`); report numbers without it as well.
- **L2 TLB connected since 2026-10-13.** `NeoverseMMU`
  (`configs/garfield/arm/neoverse_v2.py`) used to override `itb`/`dtb`
  without `next_level=Parent.l2_shared`, so every L1 TLB miss was a page
  walk. Since 2026-10-13 both point at `l2_shared`. Every O3 run cited in
  the research log predates the fix: their iTLB/dTLB and page-walk figures
  (and, to a lesser degree, IPC) are not comparable with new runs.
- **Interval granularity.** 1M-instruction stats blocks mix a context switch
  with the new task's cold start; 100K-instruction blocks separate them
  much better (blocks with a process switch show a far larger IPC drop
  at 100K than at 1M), at the cost of a larger `stats.txt`.
