---
type: method
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
  - "[[legacy-log/research-log/MRN/2026-07-26-value-file-rendezvous]]"
tags: [methodology, comparison, statistics]
---

# Comparing two configurations

**Rule:** run a full sweep of each configuration with identical window
settings, pair runs by checkpoint, and report the **median per-checkpoint
change** (B / A − 1) per suite with its quartiles, plus the outliers.
`sweep_compare.py` does this ([[sweeps]]).

- **Pairing works because restores are deterministic**: the same
  checkpoint and settings give the same instruction window in both sweeps.
  Inside a window the streams differ per block (timing moves interrupts and
  switches), so compare whole windows, never blocks
  ([[window-placement]]).
- **Single windows mislead.** gin-2121 alone showed +3.6% for the infinite
  BTB; the agentic suite median was +3.1%, with a range of −0.9% (carbon) to +5.5%
  (nushell). Garfield saw a single-checkpoint +9.35% shrink tenfold at suite
  scale ([[garfield-lessons]]).
- **Read every suite separately.** The agentic and SPEC suites react to
  front-end changes very differently ([[agentic-front-end-bound]]).
- **Check which metric moved, and why**: a limit study's gain can act
  through another structure (the infinite L2 TLB helps FDP's prefetch
  translations; the infinite BTB cuts L1I misses). Run the cross
  configuration (e.g. `--disable-fdp --infinite-tlb`) before attributing.
- **Warm-up must suit the configuration**: unbounded structures need more
  ([[warmup-and-skip]]).
- **Additivity** is a claim to test, not assume: two limits gave
  3.0% + 3.3% individually and 7.5% together after a 100M skip
  ([[btb-tlb-limits]]).
- Coverage of a mechanism is not speedup ([[garfield-lessons]]).
