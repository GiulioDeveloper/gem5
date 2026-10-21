# cpu-o3: Wire value-file publish, probe and training in LSQ

- **Date:** 2026-07-25 16:57   ·   **Branch:** rbdev

## Goal
Task 4 of the value-file rendezvous predictor build-out: complete the
dataflow the rendezvous model needs at address resolution and
writeback -- store publish, load probe/rebind, last-value capture,
shadow and consumed-mode confidence training, and squash accounting --
per `.superpowers/sdd/task-4-brief.md`. This closes the loop opened by
Task 3 (deposit/consume at rename): after this commit the model can
actually raise confidence and consume predictions, not just bind at
rename.

## Summary
`lsq_unit.cc`:
- `executeStore`: immediately before `checkViolations`, when
  `valueFileEnabled()` and the store carries a valid `mrnVfRef()` and a
  resolved effective address, publishes `{vfIdx, gen, storeSeq}` into
  the store cache via `vfStoreAddrResolved` (design doc §4 event E3) --
  always using the reference the store carried from its own rename,
  never a re-lookup, so a late-resolving instance still publishes its
  own binding.
- `executeLoad`: inside the existing `effAddrValid()` branch, before
  the early return through `checkViolations`, probes the store cache
  via `vfLoadAddrResolved` (event E4) for every `mrnVfEligible()` load
  when the model is selected. A cache-blocked load re-executes and
  reaches this point twice; documented as idempotent
  (`SameBinding`/`AlreadySelfBound` the second time) rather than
  guarded, since `MrnValueFileTables` already handles repeat probes.
- `writeback`: a new block between the existing producer-PC-prediction
  resolution and the `isMrned()` verify block, gated on
  `valueFileEnabled() && isLoad() && mrnVfEligible()`. Unconditionally
  calls `vfLoadDataResolved` (event E5; a no-op unless the load is
  self-bound, so safe to call for every eligible load) using
  `renamedDestIdx(0)` -- the load's own private execution register,
  which holds the true loaded value under every mode including
  aliasing (renameDestRegs re-points only the *architectural* mapping,
  not the load's own destination). Then switches on `mrnVfMode()`:
  `MrnVfShadowValue`/`MrnVfShadowPtr` (below-confidence, non-consuming)
  compare against the true value and call `vfNoteShadow`/
  `vfTrainVerify` purely to train confidence upward, or
  `vfNoteShadowSkipped` when a shadow-pointer's producer hasn't written
  back yet; consumed modes fall through (`default: break`) since they
  train via their own verify paths.
- The existing value-verify branch (mismatch/match, already firing for
  both the old value path and value-file producer-value/last-value
  forwards since both set `mrnPath(MrnValue)`) now also computes
  `vf_consumed_value`/`vf_mode_index` from `mrnVfMode()` and, alongside
  the existing `mispredict()`/`noteCorrect()` calls, records
  `vfNotePredictOutcome` and `vfTrainVerify` for the value-file modes.
  The old-path calls are left untouched (harmless no-ops on the old
  tables for a value-file load).
- `mrnVerifyAlias` (shared by both the old correlator-alias path and
  value-file `MrnVfAlias`): both the mismatch and match branches now
  additionally record `vfNotePredictOutcome(VfModeAlias, ...)` and
  `vfTrainVerify` when `mrnVfMode() == MrnVfAlias`, alongside the
  existing `aliasMispredict`/`noteAliasCorrect` bookkeeping.

`rob.cc` (`ROB::doSquash`) and `cpu.cc` (`CPU::squashInstIt`): inside
the existing `isMrned() && !mrnResolved()` block, right after
`noteSquashedPrediction`, map the squashed instruction's `mrnVfMode()`
(`MrnVfAlias`/`MrnVfProducerValue`/`MrnVfLastValue`) to the matching
`vfNotePredictSquashed` call. This preserves
`vfPredictMade == Correct + Wrong + Squashed` per mode: a consumed
value-file prediction resolves exactly once, either through the
writeback verify paths above or through this squash path, under the
existing `MrnResolved` discipline -- no new flag was introduced.

Carried over from the Task 3 review: a confident, `ptrValid` binding
whose producer physreg fails the rename-time liveness guards (dead,
fixed-mapping, or non-integer) previously fell through the decision
tree in `rename.cc` as a silent no-op. Added a final `else if
(cr.ptrValid && !ptr_usable)` arm that calls the new
`vfNotePtrUnusable()` note method, backed by a new scalar stat
`vfPtrUnusable` in `MemRenameStats` (`mem_rename_predictor.hh`/
`mem_rename_predictor_sim.cc`), so the case is visible instead of
invisible.

## Verification
- `scons build/ARM/gem5.opt`: clean `-Werror` build.
- `mem_rename_predictor.test.opt`: 7/7 pass.
- `mem_rename_valuefile.test.opt`: 13/13 pass.
- Old-mode regression (`se_run.py --use-mrn --mrn-alias --max-insts
  2000000`, `valueFileEnabled() == false`): `predictionsMade=5`,
  `forwardsAlias=5` (unchanged from Task 3's record); every `vf*` stat,
  including the new `vfPtrUnusable`, is zero.
- New-mode smoke (`se_run.py --use-mrn --mrn-alias --mrn-correlation
  value-file --max-insts 2000000`, hello workload, 5208 committed
  insts): exits 0. Publish/probe/rebind pipeline is live:
  `vfScPublishes=1276`, `vfScPublishSuppressed=7`,
  `vfScProbeHits=407`, `vfScProbeMisses=782`, `vfRebinds=246`,
  `vfSelfBinds=442`, `vfShadowCorrect=172`, `vfShadowWrong=217`,
  `vfShadowSkipped=4`. Consumed predictions fire for the first time:
  `vfPredictMade::lastValue=3` (`vfPredictMade::alias` and
  `::producerValue` are 0 -- not exercised by this tiny workload).
  Identity closes exactly: `vfPredictMade::lastValue (3) ==
  vfPredictCorrect::lastValue (2) + vfPredictWrong::lastValue (0) +
  vfPredictSquashed::lastValue (1)`. Cross-checked against the reused
  verify path: the old-style `predictionsCorrect` (2) and `mispredicts`
  (0) stats moved in lockstep with `vfPredictCorrect`/`vfPredictWrong`,
  confirming the same verify call resolved both.

## Files changed
- `src/cpu/o3/lsq_unit.cc` -- store publish (`executeStore`), load probe (`executeLoad`), last-value capture + shadow training (`writeback`), consumed-mode training hooks in the value-verify branch and `mrnVerifyAlias`.
- `src/cpu/o3/rob.cc` -- per-mode squash accounting in `ROB::doSquash`.
- `src/cpu/o3/cpu.cc` -- per-mode squash accounting in `CPU::squashInstIt`.
- `src/cpu/o3/mem_rename_predictor.hh` -- `vfNotePtrUnusable()` method and `vfPtrUnusable` stat declaration.
- `src/cpu/o3/mem_rename_predictor_sim.cc` -- `vfPtrUnusable` stat registration.
- `src/cpu/o3/rename.cc` -- call `vfNotePtrUnusable()` for the confident-but-unusable-pointer case.
