---
type: finding
status: current
updated: 2026-10-21
sources:
  - "[[2026-10-08-tool-call-windows]]"
  - "[[2026-10-14-event-windows]]"
tags: [context-switch, kernel, cold-start]
---

# A context switch's cost is around it, not in the scheduler

> [!warning] Provisional finding
> Findings are working hypotheses from a few sweeps and windows, and they
> change as new runs arrive. Check the evidence and its caveats before
> relying on this; challenge it when new data disagrees
> ([[SCHEMA#Findings are provisional]]).

**Claim:** the scheduler path itself is cheap (median ~1.8K instructions,
~1.7K cycles, 0.45% of cycles in framework-52684). What makes blocks with a
switch slow is the kernel work that leads to the switch and the cold state
the next task finds; and the size of the effect depends on **who** runs
around it, not on the switch. Confidence: medium (three to five windows,
two of them before the L2 TLB fix).

## Evidence

- framework-52684: blocks with a switch run at IPC 0.60 vs 1.00 without,
  with 30.5% kernel instructions vs 10.4%, yet the scheduler path is 2.1% of
  their instructions. During a tool's process churn the scheduler path runs
  the same instruction count but takes 4,705 cycles instead of 1,650: same
  code, cold ([[2026-10-08-tool-call-windows]]).
- At 100K-instruction blocks, process-switch blocks drop to IPC 0.28 (L2
  MPKI 48.9) against 0.86 (7.9) without; at 1M the drop is diluted (0.62 vs
  0.91) ([[stats-blocks]]).
- Per cause ([[2026-10-14-event-windows]]): jq's `bison <-> m4` pipe
  hand-offs *raise* IPC 20%; short-lived shells (76–93% kernel mode) and
  exits/forks cost 36–54%; redis `within opencode` −44% but `within docker`
  +13%.
- Recovery is fast: −31% in the event block, −7% in the next (redis).
- Exec blocks are the worst (IPC ~0.5).

## Implications (interpretation)

- Per-cause analysis is necessary; "context switches per M instructions"
  alone does not predict cost ([[context-switch-classification]]).
- What matters for design is the cold start of short-lived processes and
  of OpenCode's own threads (front end, L2, TLBs), which ties into
  [[agentic-front-end-bound]].
- The single vCPU inflates switch counts against a multi-core deployment
  ([[task-tracer#Known limits]]).
