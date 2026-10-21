# cpu-o3: Add the E-Stride table core and EVES arbiter

- **Date:** 2026-08-15 02:00   ·   **Branch:** vp

## Goal
Second landable seam of the E-Stride + EVES design
(docs/superpowers/specs/2026-08-14-estride-design.md, S3/S5): a
params-free `EStrideTable` core -- a verbatim transcription of
Seznec's CVP-1 2018 EVES submission source (cvp8KB/mypredictor.cc)'s
3-way skewed-associative stride predictor, 48 entries, zero-init with
no valid bit -- plus a pure `evesArbitrate()` helper reproducing the
source's stride-then-VTAGE write-order composition (S5). The core
consumes the prior in-flight-counter facility only as a plain
`unsigned` argument to `lookup()`; it owns nothing from that task.
Both pieces are new, isolated files with no other predictor wired to
them yet -- the `EvesVP` wrapper (a later task) is what actually
drives them from the pipeline.

## Summary of changes
Added `EStrideTable` (`estride_table.hh`/`.cc`): the way-index/tag
hashes (cc:69-87, with the source's dead `j < 0` clamp dropped as
unreachable), `lookup()` (SafeStride- and confidence-gated
extrapolation, `blockedBySafeStride` as a stats-only refinement),
`train()` (SafeStride tick/credit, then the tag-hit one-step-match /
one-step-mismatch / first-occurrence arms, then the tag-miss
allocation-skip / draw-refusal / victim-allocation arms, in the
source's exact order), `confIncrementDraw()`/`bernoulli()`/
`allocationDraw()` (the S3.4 probabilistic ladder, including the
signed stride-regime draw doubling and the small-stride load
throttle), and `allocateVictim()` (two-pass victim search + aging).
The commit-time range check for the stride candidate is implemented
as the declared overflow-free interval test (deviation 8) rather than
the source's UB-prone `abs(2*delta - 1)` expression -- same porting
precedent as `EVtageTables::lowVal()`. Added `eves_arbiter.hh`
(header-only, pure `evesArbitrate()`) exactly as specified: VTAGE
silently overwrites a confident stride's value even below VTAGE
confidence in the verbatim default mode; the ablation
(`overwriteRequiresConfidence`) requires VTAGE confidence to
overwrite; blackout suppresses the whole VTAGE contribution.

Covering test: `estride_table.test.cc`, 21 GTests (20 `EStrideTable` +
1 `EStrideArbiter`) pinning every S3/S4/S5 arm -- gate order and
threshold endpoint, signed extrapolation, the asymmetric range window
(including a huge near-2^63 delta and both `+-2^19` endpoints), the
mismatch-vs-sentinel dispatch on a trained entry, the constant-value
sentinel oscillation, mispredict decay-vs-collapse at the conf == 4
boundary, draw-count structure by signed stride regime (including the
deterministic delivered-correct conjunct and saturation consuming
zero draws), the allocation ladder per class, victim pass order and
aging odds, SafeStride tick/credit/penalty arithmetic including the
32767 pre-check overshoot to 32774 and the no-lower-clamp penalty
stacking, and the arbiter's full flag/mode cross product. All 21
pass; reran the other four VP GTest binaries (`lvp_table` 15,
`vtage_tables` 32, `evtage_tables` 54, `vp_inflight_map` 4) -- all
green, unaffected by this change (no shared state, no wiring yet).
Full `gem5.opt` build links cleanly.

Two test fidelity fixes against the task brief's literal GTest code
(both re-derived from the algorithm reference and the design doc, not
from guessing):
- `VictimPassOrderAndInstallState`'s occupant search as literally
  given (`wayIndex(k, 0) == idx[occupants.size()]`) can never
  terminate: `wayIndex(key, way)` is invariantly `== way (mod
  NumWays)` by construction (`(X * NumWays + way) % NumEntries`), so
  a way-0 index can never equal `idx[1]`/`idx[2]`, which are `== 1`/
  `== 2 (mod 3)` -- an infinite loop, not a subtle behavior gap.
  Rewrote the search to look for each way `w`'s OWN
  `wayIndex(k, w) == idx[w]` and force that occupant's allocation
  start-way draw to `w` via the scripted RNG, so its install actually
  lands on the intended physical slot.
- `SafeStrideBlocksBeforeConfidence` hardcoded the post-penalty value
  as `-1024`, assuming SafeStride was still 0 right before the
  penalty. But SafeStride ticks +1 on every `train()` call
  unconditionally (S3.5), and `warmToConfident()` issues several
  `train()` calls to reach `conf >= ConfThreshold` -- SafeStride is 8
  at that point (confirmed: the actual result was -1016 = 8 - 1024),
  not 0. Changed the test to capture the pre-penalty value and assert
  the post-penalty value is exactly 1024 less, preserving the test's
  actual intent (the crossing behavior) without a brittle hardcoded
  constant.

## Files changed
- `src/cpu/o3/vp/estride_table.hh` — new: `EStrideTable` class,
  `EStrideClassifier`/`EStrideLookup`/`EStridePeek`/
  `EStrideTrainOutcome`/`EStrideAllocClass` public types.
- `src/cpu/o3/vp/estride_table.cc` — new: the table core's
  implementation.
- `src/cpu/o3/vp/eves_arbiter.hh` — new: header-only
  `evesArbitrate()` and its POD in/out structs.
- `src/cpu/o3/vp/estride_table.test.cc` — new: 21 GTests.
- `src/cpu/o3/vp/SConscript` — registers `estride_table.cc` as a
  `Source` and the new `estride_table.test` `GTest`.
