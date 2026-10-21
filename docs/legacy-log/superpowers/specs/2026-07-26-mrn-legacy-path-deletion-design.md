# MRN Legacy-Path Deletion — Design

**Date:** 2026-07-26 · **Branch:** rbdev · **Status:** approved (user, in-session)

Consolidate `MemRenamePredictor` onto the value-file rendezvous model as the
single mechanism, deleting the legacy value-snapshot path and the
`lsq_forward` correlator. Empirically de-risked by the composition study
(research log, Key Results 6–7: zero net contribution in every corner of the
fallback-reach × threshold space).

## Removed

- **Files:** `src/cpu/o3/mem_rename_predictor.cc` (MrnTables implementation),
  `src/cpu/o3/mem_rename_predictor.test.cc`. SConscript: their
  `Source`/`GTest` entries and the `MrnCorrelation` enum registration.
- **mem_rename_predictor.hh:** `MrnTables`, `MrnConfig`, `MrnPrediction`;
  legacy wrapper methods (predict/peek/commitStore/commitLoad/trainForward/
  predictProducerPC/peekProducerPC and the legacy note* families); flags
  `_useValueFile`, `_useStoreSet`, `_enableValueForwarding`,
  `_predictIntLoadsOnly`, `_trainOnSnapshot`, `_aliasRequireCurrentProducer`,
  `_valueForwardOnUnconsumed` (+ accessors). `valueFileEnabled()` disappears;
  guards collapse to predictor-present.
- **Pipeline hooks:** rename's legacy mode branch, the legacy fallthrough
  (predict/peek/snapshot) and the legacy forward block; `tryMemRenameAlias`
  (+ rename.hh decl, abandon counters, staleness gate); commit-stage
  commitStore/commitLoad training (incl. the dead `isSpGp` knob); LSQ
  `findYoungestStoreByPC` (unit + LSQ wrapper + decls) and the forward-site
  correlator train/coverage/confirm block; ROB/CPU correlator-accuracy squash
  blocks. `mrnVerifyAlias` stays minus legacy-table confidence/staleness
  calls; shared wrapper methods keep their names but become stats-only where
  they touched legacy tables.
- **DynInst:** `MrnSnapValid`/`_mrnSnapValue`, `MrnProducerPredicted/
  Confirmed/Resolved`/`_mrnPredStorePC`, `MrnAliasStale` (+ accessors).
- **Params:** `mrnCorrelation` (enum deleted incl. store_set stub),
  `enableValueForwarding`, `trainOnRenameSnapshot`, `trainAtCommit`,
  `aliasRequireCurrentProducer`, `predictIntLoadsOnly`, `storeTableEntries`,
  `storeTableAssoc`, `loadTableEntries`, `loadTableAssoc`,
  `valueFileEntries`, `valueForwardConfThreshold`, `valueForwardOnUnconsumed`.
- **CLI:** `--mrn-correlation`, `--mrn-no-value-forward`,
  `--mrn-store-entries`, `--mrn-load-entries`, `--mrn-train-commit-value`,
  `--mrn-alias-allow-stale`, `--mrn-allow-nonint`,
  `--mrn-value-conf-threshold`, `--mrn-value-on-unconsumed`.
- **Stats (pure legacy only):** `storesTrained`, `loadsTrained`,
  `predictLookups`, `bindingsLearned`, `producerCoverage*`,
  `producerPredict*` (4), `aliasProducerCurrent/Stale`,
  `aliasNoInflightStore`, `aliasStoreDataNotInt`, `aliasProducerUnusable`,
  `aliasStaleRejected`, `aliasOutcomeByStaleness`.

## Remains

Everything `value_file`, plus shared enforcement with stable stat keys:
`predictionsMade`, `forwardsValue/forwardsAlias`,
`predictionsCorrect/mispredicts`, `squashedInsts`, `aliasVerify*`,
`predictionsSquashedValue/Alias` (+ `MrnSquashReason`). DynInst keeps
`Mrned`/`MrnResolved`, `_mrnPath`/`_mrnPredVal`,
`_mrnAliasProducer`/`_mrnProducerSeq`, all `MrnVf*`. Params: `numThreads`,
conf family (`confBits/Threshold/Inc/Dec`, `resetConfOnMispredict`),
`enableProducerAliasing`, `vf*`. CLI: `--use-mrn` (= the model),
`--mrn-alias`, `--mrn-conf-bits/threshold`, `--mrn-vf-no-producer-value`,
`--mrn-vf-no-last-value`. **Baseline MRN spelling becomes:**
`--use-mrn --mrn-alias --mrn-conf-threshold 14`.

## Verification (all must pass before commit)

1. Value-file unit tests 13/13 (sole remaining test binary); clean -Werror
   build.
2. Bit-identity, surviving stats + IPC: gcc 721.2.0 checkpoint and SE hello
   under baseline-MRN (new spelling) vs the pre-deletion th14 runs; no-MRN
   gcc run vs recorded baseline.
3. `mrnrec`/`mrncomm` functional gates unchanged.
4. Removal completeness: repo greps clean for MrnTables, MrnConfig,
   MrnPrediction, mrnCorrelation, lsq_forward, store_set (MRN context),
   trainForward, findYoungestStoreByPC, and every deleted param/flag name.
5. Extensive independent review of the full diff before commit.

## Documentation

`docs/garfield/mrn-ideas.md`: closure note on superseded legacy sections.
Research-log report untouched (historical). Commit-note per convention.
