# cpu-o3: Cover value-file gen-repair paths in tests

- **Date:** 2026-07-25 15:49   ·   **Branch:** rbdev

## Goal
Close the test-coverage gaps and two cosmetic findings raised in the Task 1
review of `MrnValueFileTables` (`src/cpu/o3/mem_rename_valuefile.{hh,cc}`,
see `.superpowers/sdd/task-1-brief.md`): one existing test passed for the
wrong reason, three code paths had no direct coverage, and two comments/
edge cases needed small fixes. No public API or behavior changes.

## Summary of changes
`GenMismatchAfterReallocation` was reworked: with the original 2-way SLC
table, all PCs used (`0x100`/`0x200`/`0x300+8i`, all ≡0 mod 4) collided
into one set, so the load's SLC entry was capacity-evicted before its
value-file cell's generation ever moved — the test's `bound == false`
therefore came from a plain SLC miss, not the generation check at
`loadRename` (`mem_rename_valuefile.cc:186`). The test now uses a
test-local `MrnVfConfig` (`slcAssoc = 4`) and picks thief-store PCs outside
the load's SLC set, asserts the load stays bound through each of the first
three thefts (proving its SLC entry survives), and only the fourth theft —
which reallocates its specific cell — flips it to unbound. A mutation
check (temporarily dropping the generation comparison) confirmed the
reworked test now fails without it, where it previously passed regardless.

Three new tests cover previously-unexercised branches:
- `StoreRenameRepairsStolenCell`: a store deposits, all four VF cells are
  stolen (including its own), and it deposits again — exercises the
  repair branch (`mem_rename_valuefile.cc:161`), verifying it gets a
  genuinely fresh cell and that a later bind+consume sees the new
  deposit's pointer, not the reallocated-away cell's stale contents.
- `ProbeDeadChannelSelfBinds`: a store publishes then has its cell stolen;
  a load probing that address gets `scHitDeadChannel = true` and falls
  through to `SelfBound` instead of rebinding onto a dead channel.
- `RebindClearsSelfBound`: a self-bound load's `loadDataResolved` accepts
  a value; a store then publishes the same address and the load rebinds
  onto it — `loadDataResolved` must now reject a further writeback
  (`selfBound` was cleared by the rebind), while an unrelated, freshly
  self-bound load is unaffected.

Two cosmetic fixes: `confMax()` (`mem_rename_valuefile.hh`) now clamps the
shift to 31 before `1u << shift`, mirroring `confMaxFromBits` in
`mem_rename_predictor.cc` — avoids UB for `confBits >= 32` (unreachable
today, since Task 3's SimObject will bound the params, but the class
itself made no such promise). The `log2OfGranularity` comment
(`mem_rename_valuefile.cc:25`) previously claimed it "falls back to 0 for
non-power-of-two" input; the code actually floors to the next lower power
of two for any input, only landing on 0 for inputs of 0 or 1 — the comment
now says so. No behavior change in either case.

All 13 tests pass (`mem_rename_valuefile.test.opt`); the 9 untouched tests
are byte-for-byte unchanged.

## Files changed
- `src/cpu/o3/mem_rename_valuefile.test.cc` — reworked `GenMismatchAfterReallocation`; added `StoreRenameRepairsStolenCell`, `ProbeDeadChannelSelfBinds`, `RebindClearsSelfBound`.
- `src/cpu/o3/mem_rename_valuefile.hh` — `confMax()` clamps the shift amount.
- `src/cpu/o3/mem_rename_valuefile.cc` — corrected the `log2OfGranularity` doc comment.
