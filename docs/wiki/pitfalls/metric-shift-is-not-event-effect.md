---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [methodology, events, analysis]
---

# A metric shift near an event is not the event's effect

**The trap:** event-aligned averages (`aligned.csv`, the window view's
"around events") show what happens near switches, execs or tool calls, but
programs change phase on their own.

**Control case:** 714.cpython_r has no scheduling event in its 200M window,
yet its L1I MPKI steps from 0.34 to 0.50 at 64.8M and stays there: a
program phase change.

**Mixed populations:** "process switches" in jq-2598 average −36% IPC, but
the `bison -> m4` / `m4 -> bison` pipe hand-offs (63 of them) are at +20%
IPC and lower misses, while short-lived shells (`bash.fence-real`, `sed`,
`mkdir`, 76–93% kernel mode) are far worse. The cost depends on who runs
around the switch ([[switch-cost-is-around-the-switch]]).

**What to do:** filter by cause (the window view's cause filter), prefer
isolated events (no other of their kind within ±K blocks), compare against
blocks without events, and check a window with no events before
attributing a shift. Use fine blocks (100–200K instructions) to separate
the switch from the next task's cold start ([[stats-blocks]]).
