---
type: finding
status: current
updated: 2026-10-21
sources:
  - "[[2026-10-14-baseline-sweep]]"
  - "[[raw/external/2026-10-21-agentic-checkpoints-README]]"
tags: [agentic, variability, phases]
---

# Agentic IPC is tight across tasks but unstable inside a window

> [!warning] Provisional finding
> Findings are working hypotheses from a few sweeps and windows, and they
> change as new runs arrive. Check the evidence and its caveats before
> relying on this; challenge it when new data disagrees
> ([[SCHEMA#Findings are provisional]]).

**Claim:** across the 27 agentic tasks the window IPC is narrow (median
0.99, IQR 0.85–1.14), but inside each 400M window it swings much more
than SPEC's (median block-IPC CV 0.36 vs 0.12; fetch-rate CV 0.29 vs 0.09,
200K-instruction blocks). SPEC is the opposite: wide across benchmarks
(0.47–3.17), steady inside.

## Evidence and readings

- [[2026-10-14-baseline-sweep]] for the CVs.
- The archive reports IPC 0.35–1.57 across all 132 checkpoints and up to
  0.86 spread within one task ([[agentic-suite]]): a window is one sample of
  a long, phase-rich loop.
- Within windows the low blocks line up with scheduling events, process
  churn and the cold run-up to tool calls
  ([[tool-call-runup-is-cold]], [[switch-cost-is-around-the-switch]]), but
  not every shift is an event ([[metric-shift-is-not-event-effect]]).

## Consequences

- Use window values from summed stats, not mean block IPC
  ([[aggregating-metrics]]).
- One checkpoint per task may not represent the task; using more of the 5
  dumps is open ([[questions]]).
