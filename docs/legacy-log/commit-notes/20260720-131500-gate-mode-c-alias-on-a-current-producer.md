# cpu-o3: Gate mode-C alias on a current producer

- **Date:** 2026-07-20 13:15   ·   **Branch:** rbdev

## Goal
Mode C (producer aliasing) verified at 50.9% per prediction on 721.gcc_r.2.0 --
a coin flip. Find out why, and fix it.

## Summary of changes
`Rename::tryMemRenameAlias` aliased the load to
`renameMap->lookup(store's data arch reg)` -- the CURRENT mapping at the load's
rename -- rather than the physreg the located store actually captured. The
comment at rename.cc:1259 argued the rename map holds "exactly what the
same-iteration store will read". That is a prediction about register LIVENESS,
not memory dataflow, and it only holds while nothing redefines the arch reg in
between.

Measured it before changing anything. New diagnostic counters
(aliasProducerCurrent / aliasProducerStale, and aliasOutcomeByStaleness
bucketing the verify outcome by whether the two agreed), 10M warmup + 50M
detailed:

  agree    -> 100.0% correct, n=155 across gcc+cpython, ZERO errors
  disagree ->  29.9% on 721.gcc_r.2.0, 0.0% on 714.cpython_r.2.3

and disagreement is 96-100% of all alias attempts, so it accounts for
essentially every alias mispredict. The design's stated precondition holds
0.1% of the time on gcc.

So reject the alias when they disagree. This does not lose the prediction: the
caller falls through to the mode-B value snapshot, which verifies far better on
the same loads. Behind `aliasRequireCurrentProducer` (default True) with
`--mrn-alias-allow-stale` to restore the old behaviour, so the pending
190-checkpoint scale-up can A/B with a flag rather than two builds.

A/B on three targets vs the no-MRN baseline (same 10M/50M config as
runs/mrn_ab_50M, so directly comparable; the --mrn-alias-allow-stale arm
reproduces the sweep exactly -- gcc 0.9412, mispredicts 279,810,
aliasMispredicts 33,673):

  708.sqlite_r.2.2   0.9182 -> 0.9385   aliasMispredicts 71,231 -> 187
  714.cpython_r.2.3  0.9781 -> 0.9962   aliasMispredicts 32,263 -> 0
  721.gcc_r.2.0      0.9412 -> 0.9459   aliasMispredicts 33,673 -> 1
  mean speedup       0.9458 -> 0.9602

Coverage went UP, not down (sqlite 19.4% -> 24.1%, cpython 0.9% -> 2.3%), and
accuracy with it (cpython 73.7% -> 96.3%), confirming the mode-B fallback
absorbs the rejected aliases. cpython's squashed-instruction count fell 4.3x
(1.67M -> 0.39M).

MRN is still a net loss on all three. The bottleneck has moved to mode B: an
18% mispredict rate against ~108 instructions squashed per mispredict on gcc,
where alias forwards were only 66K against 1.55M value forwards, so this fix
moves gcc by just 0.5%. Mode-B mispredicts rose slightly everywhere (gcc
+34,088) because mode B inherited loads that were selected for having producer
bindings. Next leads are both mode-B: value-file slots are never invalidated,
and the store/load width comparison is unreconciled.

## Files changed
- `src/cpu/o3/rename.cc` — compare the rename-map lookup against the located store's captured data physreg; reject the alias when they disagree and the param is set.
- `src/cpu/o3/MemRenamePredictor.py` — new `aliasRequireCurrentProducer` param (default True), documented with the measured accuracies.
- `src/cpu/o3/mem_rename_predictor.hh` — store the param and expose it; `noteAliasProducerStaleness()` / `noteAliasOutcomeByStaleness()` plus their three stats.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — init the param; register the diagnostic stats with per-bucket subnames.
- `src/cpu/o3/dyn_inst.hh` — `MrnAliasStale` flag carrying the staleness decision from rename to the verify site.
- `src/cpu/o3/lsq_unit.cc` — bucket the alias verify outcome by that flag on both the correct and mispredict arms.
- `configs/garfield/arm/sim_opts.py` — `--mrn-alias-allow-stale` to restore the pre-gate behaviour.
