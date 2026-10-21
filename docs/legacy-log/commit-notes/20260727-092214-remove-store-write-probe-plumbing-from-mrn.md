# cpu-o3: Remove store-write probe plumbing from MRN

- **Date:** 2026-07-27 09:22   ·   **Branch:** rbdev

## Goal
The squash-reduction investigation refuted store-write invalidation (0.1%
catchable ceiling), and the 190-checkpoint sweep of the surviving stability
gate settled its default (off: +0.02% suite geomean is a wash, and the gate
costs sqlite.2.1 -10.6%). Delete the probe-only machinery that supported the
refuted avenue, keeping the gate and its address-instability inputs intact.

## Summary of changes
Deleted the store-write observation apparatus end to end: the load-address
monitor table (LmEntry, lmFind/lmAllocate, lmEntries/lmAssoc config+params),
the per-cell storeWriteSeq stamp, the storeWriteProbe / cellStoreWrittenBefore
API and its wrappers, the per-store probe call in the LSQ, the verify-site
store-write classifier, and six stats (lmStoreProbes/Hits, lvWrong/Correct x
StoreWritten/NoStore). Kept: the whole stability gate (strikes, earning test,
hysteresis re-enable, lvStabilityTarget param + --mrn-lv-stability-target,
lvStrikes/lvProbationSuppressed stats) and the address-stability tracking
that feeds it (lastLine/lineKnown/addrChanged, cellAddrChanged, the
lvWrong/CorrectAddrChanged/AddrSame split -- gate observability). Comments
saying the address tracking is "probe-only, never consulted" were corrected:
the gate consults it. Two store-write unit tests deleted; 17/17 remain green.

Verified: clean build; new binary is bit-identical on 750.sealcrypto_r.0.2
both gate-on (vs the mrn_lvgate_sweep run) and gate-off (all 3,483 shared
stats vs the pre-deletion th14 reference) -- the deleted code was pure
observation.

## Files changed
- `src/cpu/o3/mem_rename_valuefile.hh` — drop lm config/table/API decls and
  VfCell::storeWriteSeq; correct addr-tracking comments to name the gate.
- `src/cpu/o3/mem_rename_valuefile.cc` — drop lm table impl, publish sites,
  storeWriteProbe/cellStoreWrittenBefore, storeWriteSeq clear.
- `src/cpu/o3/mem_rename_predictor.hh` — drop vfStoreWriteProbe /
  vfCellStoreWritten / vfNoteLastValueStoreClass wrappers and six stat decls.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — drop lm params from the config
  init and the six ADD_STATs; reword lvWrongAddrChanged description.
- `src/cpu/o3/lsq_unit.cc` — drop the per-store monitor probe and the
  store-write classifier locals/calls at the verify site.
- `src/cpu/o3/MemRenamePredictor.py` — drop lmEntries/lmAssoc params.
- `src/cpu/o3/mem_rename_valuefile.test.cc` — drop the two store-write
  observation tests.
