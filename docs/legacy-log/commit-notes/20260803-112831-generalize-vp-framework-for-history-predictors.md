# cpu-o3: Generalize VP framework for history predictors

- **Date:** 2026-08-03 19:10   ·   **Branch:** vp

## Goal
VTAGE Task 2: the framework API generalization that lets
history-indexed, commit-trained predictors plug in while keeping LVP
bit-identical.

## Summary of changes
New vp_types.hh: VpLookupContext {pc, upc, hist} and VpPredictResult
{value, token}. predictImpl/trainImpl re-signatured over the context;
the base stamps the provider token on every in-scope lookup (so
VpPredicted strictly implies a stamped token -- the guarantee the
verify-site corrective reset relies on). New base virtuals
trainsAtCommit()/usesHistory()/correctiveReset(); per-thread VpHistory
(GHR + path) with notifyControlFlow/snapshotFor/restoreHistory thin
wrappers (dead code until the pipeline wiring task); DynInst gains the
history snapshot + token fields; historyPathBits param (fatal_if
outside [1,16] -- 17..31 silently truncated and >= 32 was shift-UB).
LVP migrated to the new signatures, provably bit-identical: stash-
bisect showed an empty stats diff vs pre-task HEAD (the stale smoke
baseline's 7-line diff predates this task; fresh reference kept at
runs/vp_smoke/b_vp_lvp_task2check). Review round added three
VpHistory GTests (ghr ordering, path fold+mask, snapshot/restore
roundtrip) -> suite now 28/28; 15/15 + 20/20 untouched.

## Files changed
- `src/cpu/o3/vp/vp_types.hh` — context + predict-result types (new).
- `src/cpu/o3/vp/base.{hh,cc}` — API re-signature, token stamping,
  knob virtuals, history member + wrappers, pathBits guard.
- `src/cpu/o3/vp/last_value.{hh,cc}` — signature migration,
  bit-identical.
- `src/cpu/o3/vp/vtage_tables.test.cc` — VpHistory test suite.
- `src/cpu/o3/dyn_inst.hh` — _vpHistSnap + _vpToken + accessors.
- `src/cpu/o3/vp/ValuePredictor.py` — historyPathBits param.
