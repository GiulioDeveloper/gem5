---
type: entity
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - src/arch/arm/linux/task_tracer.cc
tags: [tracer, kernel, simobject, agentic]
---

# The guest task tracer (`LinuxTaskTracer`)

**What it is:** a C++ SimObject (`gem5::ArmISA::LinuxTaskTracer`) that, in a
restored Linux guest, records every context switch, fork, exec, exit and
rename, plus OpenCode's file reads and writes (and so its tool calls), each
stamped with the tick, the global committed-instruction count and the
user-mode count. It does **not perturb the simulation** (byte-identical
`stats.txt` with and without it) and needs no guest change or recapture.
Output format: [[trace-format]]. Analysis: [[trace-analysis]]. How to run
it: [[running-a-traced-window]].

## Pieces

| file | role |
|---|---|
| `src/arch/arm/linux/task_tracer.{hh,cc}` | the tracer |
| `src/arch/arm/ArmLinuxTaskTracer.py` | SimObject and parameters (struct offsets as `Param.Unsigned`) |
| `src/arch/arm/SConscript` | registers it and the `TaskTracer` debug flag |
| `src/cpu/base.hh` + commit code of simple, O3, Minor, KVM CPUs | `BaseCPU::userInsts()`, the never-reset user-mode counter behind `uinsts` |
| `configs/garfield/arm/kernel_layout.py` | struct offsets from the guest vmlinux via gdb |
| `configs/garfield/arm/task_trace.py` | `--task-trace*` flags; builds and attaches the tracer |

Flags: `--task-trace` (attach, write `<outdir>/tasktrace.jsonl`),
`--task-trace-process NAME` (whose `write()`/`read()` are recorded, default
`opencode`), `--task-trace-slide HEX` (expected KASLR slide; default from
`provenance.json`; the run stops if the derived one differs). Without
`--task-trace` the drivers behave exactly as before.

## How it works

**PC events on kernel functions.** A gem5 PC event fires when the hooked
instruction is about to commit (O3 services them in commit, the simple CPUs
before execution), so never on the wrong path, with the function's
arguments in `x0..x2`. PC events live in `System` and follow the thread
across `m5.switchCpus`, so tracing is continuous from atomic to O3 and back.

| hook | event |
|---|---|
| `__schedule` | remembers tick and count; the next `switch` reports the scheduler's cost |
| `__switch_to(prev, next)` | `switch` |
| `wake_up_new_task(p)` | `fork` |
| `__arm64_sys_execve(at)` | remembers filename and argv from `pt_regs` |
| `perf_event_comm(task, exec)` | `exec` (with the remembered path) or `rename` |
| `do_exit(code)` | `exit` |
| `vfs_write` / `vfs_read` | `write` (with payload) / `read` (path, size, offset; no data) for the traced process; `write` to `cgroup.procs` by anyone |

At start-up it walks `init_task.tasks` and each thread ring and writes a
`snapshot` of every task alive at the restore. `current` is `SP_EL0` (at
EL1).

**Non-obvious choices** (each found the hard way):
- Execs come from `perf_event_comm`, because `begin_new_exec` contains an
  *inlined* `__set_task_comm`; the out-of-line symbol only sees `prctl`
  renames. Pending execs are keyed by `task_struct` address (a non-leader
  thread that execs takes its leader's pid). Failed exec attempts (PATH
  probing) never appear.
- `vfs_read` is out of line in this kernel (`read()` and `pread()` both
  call it); `readv` and io_uring are not seen.
- File paths are rebuilt from the dentry chain to the root of the file's
  filesystem; mounts are not crossed (`/14/statm` for procfs).

**Reading guest memory without the MMU.** gem5's functional translation
updates TLB state and stats, which changed O3 IPC and thousands of stats
([[functional-translation-perturbs]]). The tracer walks the guest's stage-1
tables in software (EL1&0, 4 KiB granule, `TTBR0/1_EL1` by VA bit 63, start
level from `TCR_EL1.T0SZ/T1SZ`) and reads through `System::physProxy`.
Kernel addresses always translate through `swapper_pg_dir`, because a
restore at EL0 has `TTBR1_EL1` on KPTI's trampoline table. A failed read is
recorded as `null`, never fatal.

**KASLR slide** (method of RPoint's `landing.py`): `TTBR1_EL1` holds the
physical address of `swapper_pg_dir` (at EL1) or `tramp_pg_dir` (at EL0);
each candidate gives an image base; the one whose `init_task.comm` reads
`swapper/0` wins; `slide = pa_text + kimage_voffset − link(_text)`. Works on
all 27 local checkpoints, including the five with no landing label.

**Struct offsets** come from gdb on the vmlinux
(`&((struct T *)0)->field`), run by `kernel_layout.py`. The kernel has
reduced debug info (`-femit-struct-debug-baseonly`): `task_struct`, `file`,
`dentry`, `qstr`, `pt_regs` have layouts; `mm_struct`, `linux_binprm`,
`path` and the cgroup structs do not. Hence exec paths from syscall
arguments, no cgroup names, and two assumed layouts (`struct path` dentry
at +8, `list_head.next` at 0). A missing field is fatal rather than
guessed.

## Why not an existing gem5 feature

`enable_context_switch_stats_dump`, `Exec`/`ExecSymbol`, `function_trace`,
probe points, the remote GDB stub, m5ops, ftrace/eBPF in the guest, and the
QEMU capture logs were all checked against the source; each fails one of:
tick and instruction stamps, task names, no effect on the measurement, no
recapture. Details: [[gem5-tracing-under-kaslr]] and the old guide
([[legacy-log/agentic/task-tracing-guide#5.6 Why not an existing gem5 feature]]).

## Extending

- **Another hook:** find the symbol (`nm <vmlinux>`) and check it is not
  inlined at the call sites you need (no aarch64 disassembler on the host:
  decode the callers' `bl` targets from the ELF bytes); add a handler,
  register it in `startup()` with `add("symbol", &LinuxTaskTracer::fn)`, read
  `int_reg::X0..`, write with `begin()/writeTask()/end()`. New struct fields
  go into `OFFSETS` in `kernel_layout.py` and as `Param.Unsigned` in
  `ArmLinuxTaskTracer.py` (names must match). Read memory only through
  `readVirt`/`readU64`/`readString`, then rerun the no-perturbation check
  ([[validation-checks]]).
- **Another kernel:** needs only its vmlinux (slide and offsets are
  derived); the hooked symbols must exist. **Another workload:** the
  process labels work for any Linux guest; only tool-call parsing is
  OpenCode-specific (`--task-trace-process`).
- **Debugging:** `--debug-flags=TaskTracer` (before the config script)
  prints the slide, every hook address and every `vfs_write`. "KASLR slide …
  disagrees" means checkpoint and metadata do not belong together; "cannot
  derive the KASLR slide" almost always means `--kernel` is not the guest's
  kernel.

## Known limits

- One vCPU: switches are inflated against a multi-core machine.
- User/kernel split is per time slice, in instructions, not cycles.
- The scheduler cost covers `__schedule` → `__switch_to` only.
- No cgroup or container names; no command lines for processes that
  predate the checkpoint (recording `mm->arg_start..arg_end` would fix it).
- The task running at the restore is not recorded until it is switched
  out (a window with no switch has one `not recorded` slice).
- No end record: the tools end the trace at the last stats block.
