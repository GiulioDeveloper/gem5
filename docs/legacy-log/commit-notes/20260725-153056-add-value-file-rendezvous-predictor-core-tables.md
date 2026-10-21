# cpu-o3: Add value-file rendezvous predictor core tables

- **Date:** 2026-07-25 15:30   ·   **Branch:** rbdev

## Goal
Task 1 of the value-file rendezvous MRN model (Tyson & Austin memory
renaming, concrete tables from Reinman et al. ICS 1999 §2.3): a
self-contained, params-free core class owning the Value File, Store/Load
Cache, and Store Cache, plus its unit tests. Later tasks wire this into the
SimObject wrapper, rename stage, and LSQ, consuming this API verbatim.

## Summary of changes
Add `MrnValueFileTables` (`src/cpu/o3/mem_rename_valuefile.{hh,cc}`), built
purely from `MrnVfConfig` so it is unit-testable without SimObject/params
machinery, mirroring the `MrnTables`/`mem_rename_predictor.{hh,cc}` pattern:
set-associative Store/Load Cache and Store Cache with modulo indexing and
LRU-within-set, and a global-LRU Value File (not set-associative). Each
value-file cell carries a generation counter bumped only on LRU
reallocation, so stale `{index, generation}` references from the SLC/SC
read as dead rather than silently reading another owner's cell.
`PhysRegIdPtr` is stored and returned opaquely; the core never dereferences
it.

Implements the five dataflow events from the design spec: `storeRename`
(deposit + clear-stale-value), `loadRename` (bound/confident lookup),
`storeAddrResolved` (SC publish, program-order guarded), `loadAddrResolved`
(rebind / self-bind probe), `loadDataResolved` (self-bound last-value
write), and `trainVerify` (confidence training, ref-checked against the
load's current binding).

10 unit tests (GTest, plain `TEST` macros) cover cold lookup, deposit ->
bind -> train -> consume, stale-value clearing on redeposit, rebind
resetting confidence, self-bind/last-value and `AlreadySelfBound`,
generation mismatch after cell reallocation, the SC program-order overwrite
guard, a stale-ref publish being suppressed, wrong training resetting
confidence plus a stale `usedRef` training being a no-op, and same-binding
re-probes keeping confidence. All 10 pass; `gem5.opt` links.

The GTest binary needed `reg_class.cc`, `base/debug.cc`, and `sim/bufval.cc`
appended to its source list to resolve `RegClassOps`/`InvalidReg` link
symbols pulled in transitively by `cpu/reg_class.hh` (same pattern as
`src/arch/arm/SConscript`'s `aapcs64.test`); the header itself needed no
changes to satisfy the link.

## Files changed
- `src/cpu/o3/mem_rename_valuefile.hh` — new: `MrnVfConfig`, `MrnVfRef`, `MrnVfCellRead`, `MrnVfProbeResult`, and the `MrnValueFileTables` core class declaration.
- `src/cpu/o3/mem_rename_valuefile.cc` — new: implementation of the five events plus the SLC/SC/VF find/allocate helpers.
- `src/cpu/o3/mem_rename_valuefile.test.cc` — new: 10 GTest cases covering the core semantics.
- `src/cpu/o3/SConscript` — register the new `Source` and `GTest` (with the extra link-only sources).
