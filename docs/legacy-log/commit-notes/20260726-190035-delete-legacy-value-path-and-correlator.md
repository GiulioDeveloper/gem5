# cpu-o3,configs: Delete legacy value path and correlator

- **Date:** 2026-07-26 16:40   ·   **Branch:** rbdev

## Goal
Consolidate MemRenamePredictor onto the value-file rendezvous model as the
single mechanism. De-risked by the composition study (research log, Key
Results 6-7): the legacy path contributed zero net in every corner of the
fallback-reach x threshold space.

## Summary of changes
Full amputation per docs/superpowers/specs/2026-07-26-mrn-legacy-path-
deletion-design.md: MrnTables core + unit tests deleted outright; the
lsq_forward correlator, tryMemRenameAlias + findYoungestStoreByPC + the
staleness gate, commit-time training hooks, correlator-accuracy DynInst
state and squash accounting, the mrnCorrelation enum (incl. the store_set
stub), 13 legacy params, 9 CLI flags, and 18 pure-legacy stats all removed.
Shared enforcement stats keep their names; --use-mrn now selects the model
(baseline MRN = --use-mrn --mrn-alias --mrn-conf-threshold 14). +72/-1676
across 19 files.

Verification: clean -Werror build; value-file unit tests 13/13; BIT-EXACT
identity on every shared stat key vs pre-deletion runs for gcc 721.2.0
(baseline-MRN 3,373 keys; no-MRN 3,322 keys), SE hello, and mrnrec/mrncomm
(all dump blocks); independent adversarial review applied (stale comments,
formatting).

Known override: configs/garfield/arm/virt_run.py still names deleted params.
It is deliberately untouched -- user instruction, actively developed on a
separate machine, and its --use-mrn path was already broken before this
change (references a param that never existed on this branch).

## Files changed
- `src/cpu/o3/mem_rename_predictor.{cc,test.cc}` — DELETED.
- `src/cpu/o3/mem_rename_predictor.hh` — MrnTables/MrnConfig/MrnPrediction, legacy wrappers, flags, stats removed; wrapper now owns vfTables only.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — ctor + stat registrations pruned to the surviving set.
- `src/cpu/o3/MemRenamePredictor.py` — rewritten: model params + conf family + consumption modes only.
- `src/cpu/o3/rename.{cc,hh}` — legacy mode branch, snapshot fallthrough, legacy forward block, tryMemRenameAlias removed; model is unconditional.
- `src/cpu/o3/lsq_unit.{cc,hh}`, `lsq.{cc,hh}` — store-value deposit, forward-site correlator training, producer-accuracy resolution, findYoungestStoreByPC removed; guards simplified.
- `src/cpu/o3/commit.cc` — commit-time load training removed (aliased-load arch_phys redirect kept).
- `src/cpu/o3/rob.cc`, `cpu.cc` — correlator-accuracy squash blocks removed.
- `src/cpu/o3/dyn_inst.hh` — snapshot/correlator-accuracy/staleness state removed.
- `src/cpu/o3/SConscript` — sources, GTest, enum registration pruned.
- `configs/garfield/arm/sim_opts.py` — 9 dead flags removed; make_mrn + banner on the new surface.
- `docs/garfield/mrn-ideas.md` — closure note; legacy sections marked historical.
