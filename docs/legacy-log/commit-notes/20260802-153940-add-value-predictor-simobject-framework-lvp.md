# cpu-o3: Add value-predictor SimObject framework + LVP

- **Date:** 2026-08-02 16:20   ·   **Branch:** vp

## Goal
The algorithm-agnostic VP framework layer: an abstract SimObject base
carrying the pipeline API, eligibility/scope filtering, and the base
stat contract, plus the Last-Value Predictor as its first concrete
algorithm. After this commit gem5 carries a NULL-defaulted valuePred
param but no pipeline stage consumes it -- behavior is unchanged.

## Summary of changes
BaseValuePredictor (abstract SimObject): predict() at rename (inScope
filter: single scalar integer non-fixed dest, non-serializing/
barrier/atomic/store-conditional, loads-only unless widened), train()
at writeback for every in-scope instruction, verifyResult() +
notifySquashed() outcome accounting, reserved notifyPipelineSquash()
hook for VTAGE-class predictors. Stats pin the spec's counting sites:
eligible at train, made at rename, coverage/accuracy formulas,
service-level vectors for predicted loads. LastValueVP wraps the
params-free LvpTable with table-level stats. DynInst gains
VpPredicted/VpResolved flags and _vpPredVal. One deviation from the
plan: isMemBarrier() does not exist in this tree; the barrier
exclusion uses isReadBarrier() || isWriteBarrier() (AArch64 dmb sets
both). Review: two lenses, approve/approve, zero findings.

## Files changed
- `src/cpu/o3/vp/ValuePredictor.py` — SimObject declarations
  (abstract base + LastValueVP).
- `src/cpu/o3/vp/base.{hh,cc}` — the framework base class.
- `src/cpu/o3/vp/last_value.{hh,cc}` — the LVP SimObject wrapper.
- `src/cpu/o3/vp/SConscript` — SimObject/Source/DebugFlag('ValuePred')
  registration added.
- `src/cpu/o3/dyn_inst.hh` — VpPredicted/VpResolved flags, accessors,
  _vpPredVal.
- `src/cpu/o3/BaseO3CPU.py` — valuePred param (NULL disables VP).
