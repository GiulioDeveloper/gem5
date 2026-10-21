# cpu-o3: Break down alias attempts by abandon reason

- **Date:** 2026-07-22 11:20   ·   **Branch:** rbdev

## Goal
Explain how producerPredictMade (correlator predictions made at rename)
collapses to the far smaller forwardsAlias (loads actually aliased). Every
prediction that is counted but never aliased exits tryMemRenameAlias via one
of four `return false` paths between predictProducerPC and setMrnPath; none
of them were counted, so the 400x gap was invisible.

## Summary of changes
Add one counter at each of the four abandon paths in tryMemRenameAlias:
- aliasNoInflightStore -- no usable in-flight store with the predicted PC.
- aliasStoreDataNotInt -- the located store's data source reg is not integer.
- aliasProducerUnusable -- the producer physreg is invalid/fixed/dead.
- aliasStaleRejected  -- the producer is stale and aliasRequireCurrentProducer
  refuses the alias.
Together with forwardsAlias these partition producerPredictMade exactly.

Measured on 721.gcc_r.2.0 (10M/50M, alias-only): made 608,142 =
aliasNoInflightStore 238,629 (39.2%) + aliasStaleRejected 367,700 (60.5%) +
aliasStoreDataNotInt 111 + aliasProducerUnusable 0 + forwardsAlias 1,702
(0.28%). Sum matches made exactly; aliasStaleRejected == aliasProducerStale
and forwardsAlias == aliasProducerCurrent, as expected with the current-
producer gate on. The scheme acts on 0.28% of its predictions: 60% are
refused as stale (the value-delivery defect) and 39% have no in-flight store.

## Files changed
- `src/cpu/o3/mem_rename_predictor.hh` — four note methods + four scalar stats, with the partition identity documented.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — register the four stats.
- `src/cpu/o3/rename.cc` — count each abandon path in tryMemRenameAlias.
