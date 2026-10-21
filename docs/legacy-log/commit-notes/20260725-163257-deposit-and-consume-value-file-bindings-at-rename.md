# cpu-o3: Deposit and consume value-file bindings at rename

- **Date:** 2026-07-25 16:32   ·   **Branch:** rbdev

## Goal
Task 3 of the value-file rendezvous predictor build-out: give `DynInst`
the carry fields the value-file model needs across pipeline stages, and
wire the store-deposit / load-lookup events (design doc §4 E1/E2) into
`Rename::renameInsts`, per `.superpowers/sdd/task-3-brief.md`. Task 4
will read the carried `{vfIdx, gen}` reference and the shadow-pointer
fields back from the LSQ.

## Summary
`dyn_inst.hh`: added the `MrnVfEligible` flag (after
`MrnProducerResolved`) and a public `MrnVfMode` enum (`MrnVfNone/
MrnVfAlias/MrnVfProducerValue/MrnVfLastValue/MrnVfShadowValue/
MrnVfShadowPtr`) next to the existing `MrnPath` enum. New fields
`_mrnVfIdx`/`_mrnVfGen` (the carried `{vfIdx, gen}` reference),
`_mrnVfMode`, and `_mrnVfShadowVal`, placed after `_mrnPredStorePC`,
with accessors (`mrnVfRef`/`setMrnVfRef`, `mrnVfMode`/`setMrnVfMode`,
`mrnVfEligible`/`setMrnVfEligible`, `mrnVfShadowVal`/
`setMrnVfShadowVal`) following the file's existing `_mrnXxx` naming and
placement conventions. A below-confidence pointer prediction
(`MrnVfShadowPtr`) reuses the existing `_mrnAliasProducer` field rather
than adding a new one: `_mrnPath` is left at `MrnNone`, so
`renameDestRegs`' destination surgery (keyed on `mrnAliased()`) does not
fire and the unconsumed pointer is inert until the LSQ reads it back at
writeback purely to train confidence -- documented on both the field
and the accessor. `mem_rename_valuefile.hh` (for `MrnVfRef`) is
directly includable from `dyn_inst.hh`: it only pulls in
`base/types.hh`/`cpu/inst_seq.hh`/`cpu/reg_class.hh`, all already
transitively included, so no include cycle.

`rename.cc`: extended the MRN block in `renameInsts` (previously gated
on `inst->isLoad()` only, so stores never entered it). When
`memRenamePred->valueFileEnabled()`, a simple integer-data store
(`isStore() && !isAtomic() && numSrcRegs() > 0`, last source flattened
to `IntRegClass`) deposits its just-renamed data physreg -- plus the
value, if the scoreboard already shows it ready -- via `vfStoreRename`
and carries the returned `{vfIdx, gen}` on the store's `DynInst`. A
simple single-integer-dest load (`isLoad() && numDestRegs() == 1`)
marks itself `mrnVfEligible`, looks its PC up via `vfLoadRename`, and
resolves the cell per the design doc §5 priority order: alias when the
producer isn't ready and aliasing is enabled; forward the producer's
value when it's already ready and `vfForwardProducerValue`; forward the
self-bound last value when only `valueValid` and `vfForwardLastValue`;
otherwise (below confidence) snapshot what would have fired into the
shadow fields for confidence training and count it via
`vfNoteBelowConf()` (the wrapper contract from Task 2: `vfLoadRename`
itself does not count this). The old correlator-driven alias path
(`tryMemRenameAlias`) is never called while the model is selected; the
old value-snapshot path (`predict`/`peek`) still runs for an eligible
load, but only when the model produced no binding at all
(`!cr.bound`) and `valueForwardingEnabled()`, preserving the
single-writer rule. When `valueFileEnabled()` is false, the original
`if (memRenamePred && inst->isLoad() && ...)` block is untouched
verbatim in an `else` arm, so legacy behavior is byte-identical.

Consumed aliases set the same fields the old alias path sets
(`setMrnAliasProducer`/`setMrnProducerSeq`/`setMrnPath(MrnAlias)`), so
`renameDestRegs`' existing surgery and the post-`renameDestRegs`
`noteForwarded`/`noteForwardAlias` bookkeeping fire unchanged; the
local `vf_alias` flag is folded into that block's guard
(`mrnAliased || vf_alias`) so the same code serves both alias sources,
and is also folded (redundantly, deliberately) into the old-path
fallback guard so the single-writer invariant is spelled out in code
rather than left implicit in `!cr.bound`. Consumed producer-value/
last-value predictions are forwarded into the renamed destination in a
new block after `renameDestRegs`, mirroring the old value path's
forward mechanics, and record `vfNotePredictMade` with the resolved
`VfMode`.

## Verification
- `scons build/ARM/gem5.opt`: clean, no warnings from the changed
  files (`-Werror` build).
- `mem_rename_valuefile.test.opt`: 13/13 pass (unaffected core logic).
- `mem_rename_predictor.test.opt`: 7/7 pass (unaffected).
- `se_run.py --use-mrn --mrn-alias --max-insts 2000000` (old
  correlator-alias mode, `valueFileEnabled() == false`): completes;
  `predictionsMade=5`, `forwardsAlias=5` -- the untouched old path
  still fires exactly as before.
- `se_run.py --use-mrn --mrn-correlation value-file --max-insts
  2000000`: completes; `vfDepositsPtr=1951`, `vfDepositsWithValue=843`
  (store deposits are happening); `vfPredictMade` is all-zero as
  expected -- confidence can only rise once Task 4 wires the LSQ probe
  (E3/E4), so nothing is confident enough to consume yet.

## Files changed
- `src/cpu/o3/dyn_inst.hh` -- `MrnVfEligible` flag, `MrnVfMode` enum, `_mrnVfIdx/_mrnVfGen/_mrnVfMode/_mrnVfShadowVal` fields and accessors.
- `src/cpu/o3/rename.cc` -- value-file store deposit and load lookup/decision in `renameInsts`, gated so the pre-existing correlator/value path is untouched when the model is not selected.
