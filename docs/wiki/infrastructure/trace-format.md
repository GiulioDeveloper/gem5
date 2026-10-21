---
type: howto
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
tags: [tracer, format]
---

# `tasktrace.jsonl` format

One JSON object per line, flushed per line (a crashed run keeps its trace),
written by the [[task-tracer]]. Every line has `tick` (1 ps), `insts`,
`uinsts` and `event`.

- `insts` = `BaseCPU::totalNumSimulatedInsts()`, the global count over all
  CPUs since the restore, the same count `intervals.csv` uses
  ([[stats-blocks]]). `uinsts` is its user-mode (EL0) part. Basis and
  caveats: [[instruction-counts]]. Traces from before 2026-10-09 lack
  `uinsts`.
- Guest strings are byte strings: bytes outside printable ASCII are
  `\u00XX`; recover them with `s.encode("latin-1")`.

## Task object

`{pid, tgid, ppid, comm, process, kernel_thread, kthread, ns, cg}`

| field | meaning |
|---|---|
| `pid` / `tgid` / `ppid` | thread id / process id / `real_parent`'s tgid |
| `comm` | thread name (≤ 15 chars) |
| `process` | thread-group leader's name |
| `kernel_thread` | `mm == NULL`; also true for a user process after `exit_mm`. Use `kthread` |
| `kthread` | the `PF_KTHREAD` flag |
| `ns` | `task_struct.nsproxy` as hex: same value = same namespaces = same container; `0x0` once released while exiting |
| `cg` | `task_struct.cgroups` as hex: same value = same cgroup set |

`ns` and `cg` are kernel pointers used as identities: comparable within a
run only. Strings because JavaScript loses 64-bit integers.

## Events

| `event` | extra fields |
|---|---|
| `start` | `kaslr_slide` (first line) |
| `snapshot` | `tasks` (every task alive at the restore), `count` (second line) |
| `switch` | `prev`, `next`, `same_mm` (address space kept; *not* "same process", see [[context-switch-classification]]), `sched_insts`, `sched_ticks` (absent if no `__schedule` was seen first) |
| `fork` | `parent`, `child` (`child.tgid == parent.tgid` = new thread) |
| `exec` | `task` (new name); `path`, `argv` if the execve was seen after the restore |
| `rename` | `task` |
| `exit` | `task`, `code` |
| `write` | `task`, `file`, `path`, `count`, `truncated`, `data` |
| `read` | `task`, `file`, `path`, `count`, `pos` (null for streams) |

```json
{"tick":209306074077,"insts":1756030,"event":"switch","same_mm":true,
 "prev":{"pid":1308,"tgid":1235,"ppid":1231,"comm":"JITWorker","process":"opencode","kernel_thread":false},
 "next":{"pid":1303,"tgid":1235,"ppid":1231,"comm":"JITWorker","process":"opencode","kernel_thread":false}}
```

`sched_ticks` is meaningful on O3 only; on the atomic core every
instruction is one cycle, so use `sched_insts` there.
