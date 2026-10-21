---
type: garfield
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/mrn-ideas]]"
  - "[[legacy-log/research-log/MRN/2026-07-26-value-file-rendezvous]]"
  - "[[legacy-log/research-log/MRN/2026-07-27-squash-reduction-stability-gate]]"
  - "[[legacy-log/research-log/MRN/2026-07-28-cost-side-criticality-closure]]"
  - "[[legacy-log/commit-notes/20260629-132547-record-stage2-memory-renaming]]"
tags: [garfield, mrn, speculation, o3, lsq]
---

# Garfield Stage 2: memory renaming (MRN)

**What it is:** a load-value speculation mechanism in O3 (`--use-mrn`): at
rename, a load whose value can be predicted from an identifiable producer
(a store to the same address, or its own previous value) gets that value
in its destination physreg so dependents proceed; the load still executes,
is verified at writeback, and a mismatch squashes inclusively. Final
design: **value-file rendezvous** (after Tyson & Austin, MICRO-30 1997;
tables per Reinman et al., ICS 1999). Final configuration
`--use-mrn --mrn-alias --mrn-conf-threshold 14`, all gates off: **geomean
1.0092** over 190 SPEC CPU 2026 checkpoints. Chapter closed 2026-07-28;
later found to be 88% subsumed by value prediction ([[value-prediction]]).

## How it got there (each step a lesson)

1. **First version** (value forwarding from a store/load/value-file table
   set, trained at commit): 2.49× on a stable store→load microbenchmark,
   0.95× on a changing recurrence; suite geomean 0.985 (a net loss).
2. **Training on the wrong value.** Commit-time training compared against a
   value file the producing store had already updated *after* the
   prediction, so changing recurrences trained "match" while every forward
   was wrong (43% of matches were wrong on gcc). Fix: train on the
   rename-time snapshot → suite break-even (1.0001).
3. **A 99.6%-accurate predictor delivering ~0.5% of its value.** The store
   PC correlator was right, but the alias read the store's data register
   from the *current* rename map (stale 99.5% of the time), and the
   same-iteration producer is **never** in the store queue at the load's
   rename: a store enters the SQ at dispatch, `renameToIEWDelay` (2 cycles)
   after its rename.
4. **Rendezvous instead of search:** the store deposits its data physreg (and
   value if ready) into a per-static-store cell at its own in-order rename;
   the load reads the cell at its rename. Changing-recurrence microbenchmark
   +125%; suite **1.0092** at threshold 14 (1,140-run threshold sweep). Most
   of the benefit came from **last-value forwards**, not store→load.
5. **Legacy path deleted** after a 2×2 composition study showed zero net
   contribution in every corner.
6. **Squash reduction** (2026-07-27): store-write invalidation refuted
   (0.055% of wrong forwards see a prior store write: staleness comes from
   the load's own address moving). An address-instability strike gate
   rescued the worst losers (+0.77% on the worst ten) but was a wash at
   suite level because 708.sqlite_r.2.1 lost 10.6%: its wrong-dense loads
   are schedule-critical. Ships off.
7. **Cost-side criticality closed** (2026-07-28): 97.5% of correct consumed
   forwards are served by store-to-load forwarding or L1D, so MRN's benefit
   is **dataflow-height collapse (scheduling), not latency hiding**. Flush
   cost by serving level 61 / 187 / 299 instructions (L1D / L2 / memory).
   A flush-weighted ledger cannot separate critical bindings from churners
   because the two populations are inverted on the cost-benefit plane.

## Facts that outlive MRN

- Stores enter the SQ `renameToIEWDelay` after rename: nothing at a load's
  rename can see a same-iteration producer.
- A mechanism whose forwarding regime oscillates **poisons StoreSet
  training** (−18% on vpr in one gate iteration): mechanisms must behave the
  same across regimes.
- `squashedInsts` charges the whole younger window to a mispredict,
  double-counting branch recovery: an upper bound on cost (~108–154
  instructions per mispredict measured).
- Per-binding accuracy cannot see schedule criticality.
- A gem5 FS run with an inert-by-default mechanism must be bit-identical to
  the baseline before measuring ([[validation-checks]]).

More in [[garfield-lessons]].
