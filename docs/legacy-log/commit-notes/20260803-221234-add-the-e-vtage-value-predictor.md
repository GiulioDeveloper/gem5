# cpu-o3,configs: Add the E-VTAGE value predictor

- **Date:** 2026-08-05 06:30   ·   **Branch:** vp

## Goal
EVES Stage-1 Task 2: the classifier context and the EVtageVP
SimObject that put the per-class policy on the pipeline.

## Summary of changes
Framework: VpClassifierInfo/VpInstClass built at the train/verify
paths (MemSrcLevel with stlf->fast, OpClass buckets, integer
non-flag source count -- NZCV sources are CCRegClass and excluded --
indirect-call predicate), threaded through trainImpl and the
classifier-aware corrective punish; per-thread renamed-instruction
hook declared for the burst guard. EVtageVP wraps EVtageTables
(single RNG stream; positional config verified across all 11
fields), 17-stat surface incl. the none-provider bucket and pending
set/consumed/dropped, --use-vp evtage + --evtage-{burst-guard,
hist-lengths,conf-threshold}. Review round: corrected the BL
classification declaration (gem5 defaults flag-less branches to
IntAluOp, so an eligible BL takes the Alu seed-to-7 arm -- symmetric
across the A/B, declared deviation from CVP's deterministic-false
arm), added a fatal_if on nonzero burstGuardWindow until the rename
hook is wired (unwired, it would silently suppress every prediction),
stripped a gitignored citation and session jargon. Gates: dual
bit-identity (LVP smoke + VTAGE FS checkpoint, value-identical),
vphist correlation intact (0.994), hostile branchsort at threshold 1
(1886 wrongs, identity exact, checksum == baseline; the threshold-7
zero-wrong null recorded), baseline inert, 54/54+32/32+15/15+20/20.

## Files changed
- `src/cpu/o3/vp/vp_types.hh`, `base.{hh,cc}` — classifier context +
  threading + rename-count hook.
- `src/cpu/o3/vp/evtage.{hh,cc}` — the SimObject wrapper + stats +
  burst-guard construction guard.
- `src/cpu/o3/vp/last_value.{hh,cc}`, `vtage.{hh,cc}` — mechanical
  signature migration (bit-identity proven).
- `src/cpu/o3/vp/ValuePredictor.py`, `SConscript`,
  `configs/garfield/arm/sim_opts.py` — registration + CLI.
