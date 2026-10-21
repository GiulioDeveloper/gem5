---
type: method
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [methodology, context-switch, analysis]
---

# Classifying context switches

**Rule** (`trace_analysis.py`, since 2026-10-16):

| kind | when |
|---|---|
| `switch_kernel` | either side is a kernel thread or the idle task |
| `switch_thread` | user → user with the same `tgid` |
| `switch_process` | user → user with different `tgid`, **or** a kernel thread / idle → a user task of a different process than the user task the kernel run interrupted (marked `via`, cause e.g. `opencode -> cc1plus (via kernel)`) |

So per-kind counts can sum to more than the number of switches;
`switches.csv` stays one row per switch record by its own cause. Causes are
by process name: `within <process>` for thread switches, `<a> -> <b>`
otherwise, with `kernel` and `idle`.

## Why not `same_mm`

The tracer's `same_mm` (prev and next share a non-NULL `mm`) is the
**address space**, which differs from the process in two cases:
- an exiting process's thread switching to a sibling: `prev.mm` is already
  NULL (`exit_mm`), so `same_mm` is false although it is a thread switch
  (mostly Go threads of exiting `docker inspect`, and `git`);
- a `vfork`/`CLONE_VM` child (CPython `subprocess`, Bun `spawn`) borrows its
  parent's `mm` until it execs: `same_mm` true although it is a process
  switch (the child carries the parent's name until the exec:
  `python3 -> python3`).

And a kernel thread borrows the previous task's address space (lazy TLB),
so `opencode -> rcu_preempt -> cc1plus` changes process and address space at
the second switch: it used to be two kernel switches and no process switch.

## History of the rule (numbers before a date use the older rule)

- before 2026-10-15: thread vs process by `same_mm`. Switching to `tgid`
  moved 4.9% of agentic process switches (4,547 → 4,322 in the first
  sweep's 27 windows).
- before 2026-10-16: process changes through a kernel thread were not
  counted; adding them adds 420 process switches (+9%); the median agentic
  rate goes 0.37 → 0.40 per M instructions.
- Both sweeps were reanalysed under the current rule without rerunning
  gem5. Only the switch columns changed.

What the switches look like: [[switch-cost-is-around-the-switch]].
