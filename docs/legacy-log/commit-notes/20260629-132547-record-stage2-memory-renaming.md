# cpu-o3: Add Garfield Stage 2 memory renaming (MRN)

- **Date:** 2026-06-29 13:25   ·   **Branch:** stage2-mrn (merged to rbdev)

## Goal

Stage 2 of the Garfield plan (see `docs/garfield/README.md`): implement **real
memory renaming** (Tyson & Austin, MICRO-30) as a standalone speculative
feature — predict a load's value from stable store→load communication, forward
it at rename, verify at writeback, and recover by a full squash on a mispredict.
This is *not* ghosting: it changes timing and is a genuine speculation with its
own recovery cost. Mode **B** (value forwarding) is implemented now; the code is
structured so mode **C** (producer-register aliasing) drops in next. Gated by
`--use-mrn`, **off by default**.

## Commits in this feature (on stage2-mrn → rbdev)

1. `cpu-o3: Add MemRenamePredictor (Stage 2 MRN)` — `MemRenamePredictor`
   SimObject wrapping a plain-int `MrnTables` core (store cache + separate value
   file + load cache, set-associative + LRU, confidence counter with SP/GP
   doubling); 5 GTests for the core.
2. `cpu-o3,configs: Wire MemRenamePredictor (inert)` — `Mrned` flag +
   `mrnPredVal` on DynInst; predictor pointer held by rename/IEW/commit (IEW
   exposes it to the LSQ); `--use-mrn` + `--mrn-*` knobs. Attached-but-inert ==
   baseline.
3. `cpu-o3: Train MemRenamePredictor on committed mem ops` — stores deposit
   their value at writeback (`writebackStores`, committed-only); loads train
   confidence at commit; `storesTrained`/`loadsTrained` stats. Training-only ==
   baseline timing.
4. `cpu-o3: Forward and verify memory-renamed loads` — predict + inject at
   rename (value → renamed integer physreg + scoreboard ready, for early
   dependent wakeup); verify at writeback (compare the true register value;
   mismatch → reset confidence + `squashDueToMemOrder` inclusive); MRN debug
   flag + `predictionsMade`/`mispredicts` stats.

## Files

`src/cpu/o3/mem_rename_predictor.{hh,cc}` + `_sim.cc` + `.test.cc` +
`MemRenamePredictor.py` (new predictor), `dyn_inst.hh` (Mrned flag + mrnPredVal),
`BaseO3CPU.py` (memRenamePredictor param), `rename.{hh,cc}` (predict + inject),
`lsq_unit.cc` (store deposit + load verify/squash), `commit.cc` (load train),
`iew.{hh,cc}` (predictor pointer + public `squashDueToMemOrder`), `SConscript`
(sources, GTest, MRN flag), `configs/garfield/arm/se_run.py` (--use-mrn + knobs).

## Validation

- **knob-off ≡ pre-MRN baseline**: every simulated stat byte-identical for
  mrncomm, mrnrec, and ptrchase (vs the pre-Stage-2 binary). The feature is
  truly inert when disabled.
- **Correctness keystone (off vs on)**: identical `checksum=` and identical
  committed-inst count on ALL six workloads below. Speculation + verify + squash
  never perturbs architectural state.
- **No crash on FP/vector**: matmul and stream (FP) run cleanly — the inject is
  restricted to integer destinations (the `RegVal` `setReg` path panics on full
  vector registers).
- **Unit test**: `mem_rename_predictor.test` (5 cases) passes.

## Measurement (ROI core cycles, off vs on; confBits=4, threshold=8)

| Workload | off cyc | on cyc | speedup | coverage (fwd/loads) | mispredicts |
|---|---|---|---|---|---|
| mrncomm (stable store→load) | 10,018,820 | 4,019,227 | **2.49×** | 1999969 / 2000560 | 0 |
| mrnrec (changing recurrence) | 18,018,622 | 18,955,773 | 0.95× | 1562476 / 2000553 | 62,499 |
| ptrchase (pointer chase) | 3,033,989 | 3,034,770 | 1.00× | 2 | 2 |
| branchsort | 1,252,405 | 1,253,336 | 1.00× | 2 | 2 |
| matmul (FP) | 8,474,616 | 8,472,598 | 1.00× | 12 | 1 |
| stream (FP) | 11,172,379 | 11,271,576 | 0.99× | 12 | 1 |

## Finding

Mode B delivers a large win exactly where its assumption holds — a **stable**
store→load value. mrncomm's serial store→load chain pipelines for a **2.49×**
speedup at 100% accuracy (0 mispredicts): the load value is forwarded at rename,
so dependents never wait on the L1 access while the load still executes and
verifies in the background.

Where the communicated value **changes** every iteration (mrnrec), B forwards a
stale snapshot. 96% of forwards still verify correct (the recurrence partly
serializes execution), but the 4% that miss cost 62,499 full squashes — a net
**5% slowdown**, because the load value is not on mrnrec's critical path (the
multiply recurrence is): the correct forwards save nothing while the mispredicts
pay recovery. This is the precise limitation that motivates **mode C** (alias
the load to the in-flight producer register instead of snapshotting a committed
value) and confidence tuning.

Workloads with no stable store→load reuse (ptrchase, branchsort, matmul, stream)
draw essentially zero predictions — the predictor correctly stays silent, so
there is no false speedup and no harm.

## Out of scope (Stage 2, deliberately)

Mode C (producer-register aliasing — the value-file / load-cache split is already
in place for it); selective replay (full squash only, by design); an SP/GP and
confidence-threshold tuning sweep; ghosting of MRN-ed loads onto the cheap
backend (Stage 3 integration); value prediction (Stage 3).
