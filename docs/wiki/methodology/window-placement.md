---
type: method
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [methodology, windows, determinism]
---

# Placing a detailed window

**Rule:** find the event on the atomic core first, then restore with a
generous settle margin and locate the event again in the O3 trace itself.
Never reuse atomic instruction positions as O3 phase boundaries.

- **Restores are deterministic per core type**: two atomic runs give
  identical traces, and two O3 runs of the same window give identical
  stats ([[validation-checks]]).
- **Atomic and O3 are different schedules.** The replay driver's polling
  and the guest timers follow *simulated time*, so a faster or slower core
  moves events: by a few million instructions (gin-2121's first `read`) up
  to ~130M (framework-52684's `bash` call), and "over a hundred million" in
  general. QEMU capture logs are no guide either: after restore the guest
  follows simulated time.
- **Settle margin:** hundreds of millions of instructions before the
  event, and a region long enough to hold the whole call. A window that
  ends first misses the `completed` state; add `--tail-insts` to see it
  finish.
- **Two configurations of one window** (e.g. with and without a limit
  study) share instruction counts but not timing: interrupts and switches
  land differently, so per-block streams differ. Compare whole windows,
  across many checkpoints ([[comparing-configurations]]).
- **Rounds:** each `RPOINT_REPLAY_ROUND` holds one model response and its
  tool calls, billions of instructions apart. The progress line's "total
  committed" counts micro-ops and runs about 12% above the instruction count
  the trace uses ([[instruction-counts]]).
- **What the sweeps do instead:** one fixed window per checkpoint right
  after the restore (1 atomic instruction, 20M warm-up, 400M agentic / 200M
  SPEC). The checkpoints were placed at random offsets over the agent loop,
  so this samples the loop without choosing events ([[agentic-suite]]).
  Warm-up length: [[warmup-and-skip]].
