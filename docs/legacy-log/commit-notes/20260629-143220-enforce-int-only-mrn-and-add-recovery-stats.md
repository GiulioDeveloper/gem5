# cpu-o3: Enforce int-only MRN forwarding; add recovery stats

- **Date:** 2026-06-29 14:32   ·   **Branch:** rbdev

## Goal

Harden Stage 2 MRN per review: (1) make the integer-destination-only
restriction on mode-B value forwarding an explicit, enforced invariant that
fails loudly if relaxed (rather than a silent inline guard), and (2)
instrument the predictor comprehensively — including the recovery cost of
misprediction flushes, which the original four stats did not capture.

## Summary of changes

- **Int-only enforcement.** `predictIntLoadsOnly` (default flipped False→True)
  now gates forwarding: integer destinations forward; non-integer destinations
  are skipped when the flag is set (default), or **panic** when it is relaxed.
  Mode B forwards a scalar `RegVal` and `PhysRegFile::setReg(RegVal)` panics on
  full vector registers, so a wide forward must fail loudly, never corrupt
  state. `se_run.py` gains `--mrn-allow-nonint` to relax it (which then panics
  on the first non-integer forward).
- **Comprehensive stats.** Added `predictLookups` (loads considered at
  rename — the coverage base), `predictionsCorrect` (forwards verified correct
  at writeback), and `squashedInsts` (instructions discarded by MRN flushes =
  the load plus every younger in-flight inst — the recovery cost / wasted
  work). `predictionsMade` now counts at the actual inject site, not inside
  `predict()`. New CPU accessor `getCurrentInstSeq()` sizes each flush
  (next-to-assign seqNum − the squashed load's seqNum).

## Validation

- **mrncomm ON unchanged**: 2.49x (10.0M→4.0M cyc), checksum 1515870810,
  coverage 1999969/2001430 (99.9%), 0 mispredicts, 0 squashedInsts. knob-off
  byte-identical to the pre-MRN baseline.
- **mrnrec ON**: the explicit stats correct a crude T5 derivation — verified
  accuracy is **0%** (`predictionsCorrect`=0, `mispredicts`=62499), and the
  flush cost is **12,374,802 squashed insts** (~198 per flush ≈ the full
  192-entry ROB window). This is the precise recovery cost that makes mode B a
  net loss on changing-value communication.
- GTest (`mem_rename_predictor.test`, the `MrnTables` core, unchanged) passes.

## Files changed

- `src/cpu/o3/MemRenamePredictor.py` — `predictIntLoadsOnly` default True + doc.
- `src/cpu/o3/mem_rename_predictor.hh` — int-only accessor + member; `predict`
  counts lookups; `mispredict(loadPC, squashedInsts)`; `noteForwarded` /
  `noteCorrect`; three new stats.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — init the flag; register new stats.
- `src/cpu/o3/rename.cc` — integer gate with panic-on-relax; `noteForwarded`.
- `src/cpu/o3/lsq_unit.cc` — `noteCorrect` on match; flush size on mismatch.
- `src/cpu/o3/cpu.hh` — `getCurrentInstSeq()` accessor.
- `configs/garfield/arm/se_run.py` — `--mrn-allow-nonint` knob.
