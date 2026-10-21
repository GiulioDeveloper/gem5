# cpu-o3,configs: Decouple value-snapshot path confidence and reach

- **Date:** 2026-07-26 04:20   ·   **Branch:** rbdev

## Goal
Two knobs to study how the legacy value-snapshot path composes with the
value-file rendezvous model: its own confidence threshold, and whether it
may serve loads the model bound but consumed nothing for.

## Summary of changes
valueForwardConfThreshold (0 = inherit confThreshold) gives the snapshot
path an independent strictness -- previously --mrn-conf-threshold set both
paths, so composition runs silently ran the snapshot path at the value-file
model's threshold. valueForwardOnUnconsumed extends the snapshot path's
fallthrough from "no value-file binding at all" to "value-file consumed
nothing" -- covering dead-channel and below-confidence loads that neither
path currently serves. Defaults preserve existing behavior exactly
(verified: default-config run byte-identical to the recorded smoke; old
lsq_forward mode untouched; 13/13 + 7/7 unit tests).

## Files changed
- `src/cpu/o3/MemRenamePredictor.py` — the two params.
- `src/cpu/o3/mem_rename_predictor.hh` — member + accessor.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — snapshot-path tables take the decoupled threshold; init.
- `src/cpu/o3/rename.cc` — fallthrough condition: nothing-consumed + (unbound or knob).
- `configs/garfield/arm/sim_opts.py` — --mrn-value-conf-threshold, --mrn-value-on-unconsumed.
