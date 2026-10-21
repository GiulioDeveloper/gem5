# cpu-o3: Measure correlator producer-PC accuracy

- **Date:** 2026-07-22 01:30   ·   **Branch:** rbdev

## Goal
Isolate whether the aliasing correlator's loadPC->storePC prediction is itself
correct, separate from the downstream physreg-liveness question that
aliasVerifyCorrect/aliasMispredicts fold in.

## Summary of changes
At the LSQ store->load forward -- ground truth, the load actually forwarded
from a known store PC -- score the correlator's CURRENT binding against that
store before trainForward updates it. New const peekProducerPC reads the
binding without touching LRU (zero behaviour change). Three stats:
producerPredictCorrect / Wrong / Untrained; accuracy = correct/(correct+wrong).

Result on 721.gcc_r.2.0 (10M/50M): the correlator is 99.6% accurate (357,271
of 358,614 with-binding forwards). But aliasing only fires on 1,702 loads --
a 200x gap. The correlator is near-perfect; the loss is entirely downstream
(the store not yet in the SQ at rename, and the stale rename-map physreg
lookup). Do not improve the correlator; fix value delivery.

## Files changed
- `src/cpu/o3/mem_rename_predictor.hh` — `peekProducerPC` (const, no LRU); `noteProducerPredict`; three stats.
- `src/cpu/o3/mem_rename_predictor.cc` — const `fwdFind` + `peekProducerPC` implementations.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — register the three stats.
- `src/cpu/o3/lsq_unit.cc` — score the binding against the true producer at the LSQ forward.
