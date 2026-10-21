---
type: method
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [methodology, statistics]
---

# Aggregating per-block metrics

**Rule:** aggregate raw counts, never average ratios. IPC over a group of
blocks is Σ instructions / Σ cycles; MPKI is Σ misses / Σ instructions × 1000;
occupancy-style averages are cycle-weighted. The window value in
`window_view.py` and `sweep_summary.py` is computed this way.

- **The mean of block ratios is biased.** With equal-instruction blocks,
  window IPC is the *harmonic* mean of block IPCs; low-IPC blocks take most
  of the cycles. framework-52684: window IPC 0.956, arithmetic mean of
  block IPCs 1.21.
- In Python:
  ```python
  import sys; sys.path.insert(0, "analysis_scripts/tasktrace")
  import trace_analysis as ta
  blocks = ta.load_blocks(Path(run))   # raw counts per block; missing stat = 0
  ```
- **Coefficient of variation** (population std / mean over blocks) is the
  within-window variability metric of [[sweeps]]. It is unstable when the
  mean is near zero (a window with two switches; 729.abc_r's L1I MPKI of
  0.006 gives CV > 10): read CV panels beside the values.
- **Across checkpoints:** report medians and quartiles of per-checkpoint
  window values, or of paired per-checkpoint changes
  ([[comparing-configurations]]). One window is one window, not a
  whole-checkpoint average.
- **Event-aligned averages** (`aligned.csv`, the window view's "around
  events") count a block once per event and need a control: a metric shift
  near an event is not evidence of an effect
  ([[metric-shift-is-not-event-effect]]).
- Report agentic numbers **with and without the replay driver's launch
  tree** where it matters ([[replay-polling-in-measurement]]).
