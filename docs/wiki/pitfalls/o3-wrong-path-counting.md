---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/VP/2026-08-03-last-value-predictor]]"
  - "[[legacy-log/research-log/VP/2026-08-15-eves-estride-composition]]"
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
tags: [o3, wrong-path, stats, counters]
---

# O3 counters include wrong-path work unless taken at commit

**The trap:** gem5's O3 executes down wrong paths, and most stats and
training hooks outside commit see those instructions. Three forms seen on
this fork:

- **The doomed window.** Between a squash being signalled and its victims
  being flag-marked (~2 cycles), doomed instructions still pass
  verify/train gates. In Garfield's VP this silently inflated
  `predictionsCorrect` (in the reproducer every "correct" was doomed),
  polluted tables, and at threshold 0 closed a squash/refetch livelock that
  the ROB-head watchdog caught. Fix: a per-thread pending-squash low-water
  mark in IEW gating the VP verify/train sites; a `fatal_if` forbids VP with
  a configured `squashWidth` (multi-cycle ROB walks reopen the window)
  ([[value-prediction]]).
- **Verify-site vs commit-site counts.** Verify-site coverage read 3–5% high
  from wrong-path corrects; the commit-site counters
  (`committedVpPredicted`, `committedMrned`) are exact because a wrong
  resolution squashes before commit.
- **Structure fills from the wrong path.** 31% of InfiniteBTB first-time
  inserts in one window were wrong-path (`updateBTBAtSquash`); walker
  requests include squashed ones ([[infinite-btb-model]],
  [[walk-requests-vs-completed]]). `bac.noHistByType` counts wrong-path and
  repeated fetches.

**What to do:** prefer counts at commit, or check a stat against a commit
trace (`--debug-flags=Exec...`) on a short window before trusting it; when a
mechanism trains outside commit, make sure doomed instructions are excluded.
The [[task-tracer]] is safe by construction: PC events fire at commit.
