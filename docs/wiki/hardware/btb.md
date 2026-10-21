---
type: concept
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/infinite-btb]]"
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
  - src/cpu/pred/simple_btb.cc
tags: [btb, front-end, branch-prediction]
---

# The BTB in this core

**Baseline:** `NeoverseV2_BTB`, a `SimpleBTB` of 12K entries, 6-way, 18-bit
tags, LRU (`configs/garfield/arm/neoverse_v2.py`). In the
[[decoupled-front-end]] it both detects branches and supplies targets, so
its misses are expensive. Agentic windows have 1.13 BTB-miss mispredicts per
1000 instructions against 0.005 for SPEC ([[2026-10-14-baseline-sweep]]),
and removing capacity and aliasing misses is worth about +3% IPC
([[btb-tlb-limits]]).

## Facts about gem5's BTB that matter

- **Entries are installed only for taken branches** (`updateBTB`, at commit
  or at squash). A never-taken conditional branch stays out, and BAC falls
  through it, which is correct.
- **No process separation.** `tid` in `SimpleBTB`'s key is the SMT slot
  (always 0), not a process; all address spaces share and alias entries.
  The [[infinite-btb-model]] keys by ASID.
- **Branches to PC+4** (kernel Spectre-BHB loop `b`, some `br`) are never
  inserted: falling through is the right target.
- **Wrong-path inserts:** with `updateBTBAtSquash=True` a branch that
  resolves taken on a wrong path is inserted too (31% of the inserts in one
  2M-instruction gin window).
- **`SimpleBTB` evictions** were never counted upstream. Fixed on this fork
  (`simple_btb.cc`): the check must look at the set *before*
  `AssociativeCache::findVictim`, which invalidates the victim it returns. A
  short gin window evicts on about 28% of BTB updates. Runs before
  2026-10-16 read 0 evictions.
- `SimpleBTB::update` always allocates a victim even when the branch sits
  in another way, so a target update can leave a duplicate. Not changed:
  it would alter baseline results.

## Measuring BTB misses

Use **`branchPred.mispredictDueToBTBMiss_0`** (the sweep's
`btb_mispred_pki`, `trace_analysis.py`'s `btb_mpki`): mispredicts caused by
a missed taken branch. In decoupled mode `btb.misses` is 0
([[btb-miss-stat-zero-decoupled]]). Also useful: `branchPred.BTBMispredicted`
(taken branches that missed, at update), and `bac.noHistByType` (every
fetched branch without a prediction, wrong path and repeats included; its
unconditional types are the costly misses).
