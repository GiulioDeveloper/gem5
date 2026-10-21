# cpu-o3: Correlator producer-PC accuracy metric

- **Date:** 2026-07-22 02:30   ·   **Branch:** rbdev

## Goal
Measure the correlator's producer-PC prediction as an ACCURACY (denominator =
predictions MADE), distinct from the earlier COVERAGE metric (denominator =
true LSQ forwards). Coverage asks "of real forwards, how many does the table
capture"; accuracy asks "of predictions the table made, how many pan out".

## Summary of changes
Snapshot the predicted store PC on the load at rename (when predictProducerPC
returns a binding) and count producerPredictMade. At the LSQ forward, confirm
if the load actually forwarded from the predicted store. At writeback resolve
correct/wrong (guarded by a new MrnProducerResolved flag). Predictions whose
load is squashed before writeback are counted separately at the two squash
sites (ROB::doSquash, CPU::squashInstIt) as producerPredictSquashed, so
accuracy can be computed either way -- incl. squashed (correct/made) or excl.
(correct/(correct+wrong)) -- with made == correct+wrong+squashed exactly. The
earlier coverage stats are renamed producerCoverage* for clarity.

Result on 721.gcc_r.2.0 (10M/50M, alias-only): accuracy 58.6% (356,462 /
608,142) vs coverage 99.6%. The gap is not squashes (13,555) but wrong
(238,125): predictions where the load never forwarded from the predicted store
(it read from cache, or forwarded elsewhere). The correlator names the right
store WHEN a forward happens, but ~40% of predictions never see that forward.
The identity made==correct+wrong+squashed holds exactly.

## Files changed
- `src/cpu/o3/dyn_inst.hh` — MrnProducerPredicted/Confirmed/Resolved flags + predicted-storePC snapshot.
- `src/cpu/o3/mem_rename_predictor.hh` — rename coverage stats/method; add accuracy stats + noteProducerPredictMade/Outcome/Squashed.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — register the renamed coverage and new accuracy stats.
- `src/cpu/o3/rename.cc` — snapshot the predicted store PC and count made.
- `src/cpu/o3/lsq_unit.cc` — confirm at the forward; resolve correct/wrong at writeback.
- `src/cpu/o3/rob.cc`, `src/cpu/o3/cpu.cc` — count squashed-before-validation at the two squash sites.
