# cpu-o3: Pin E-Stride victim arms; document classifier

- **Date:** 2026-08-15 03:00   ·   **Branch:** vp

## Goal
Follow-up to the E-Stride table core commit (`10501c4560`), addressing
two Important findings from its fidelity/design review: (1)
`EStrideClassifier`'s latency-band fields were undocumented, and
`fastInst` in particular collides in name (but not meaning) with
`EVtageClassifier::fastInst`, creating a silent-miswiring hazard for a
future wrapper author; (2) `EStrideTable.VictimPassOrderAndInstallState`
exercised the aging branch but pinned neither which way aging targets
nor the pass-2 `AllocatedUZeroVictim` claim path, leaving that outcome
with zero test coverage.

## Summary of changes
`estride_table.hh`: documented `notLlcMiss`/`notL2Miss`/`notL1Miss` as
CVP's latency-band predicates (proxied at < 150 / < 60 / < 12 cycles
from the memory-serve level) with their expected monotonicity for a
real load, and gave `fastInst` a doc comment stating it is CVP's
MFASTINST (actual latency < 3, mypredictor.cc:14, cc:153/186) and
explicitly calling out that this is NOT the same predicate as
`EVtageClassifier::fastInst` ("genuine IntAlu", feeding a latency == 1
check) despite the shared field name -- a wrapper must never forward
one straight into the other.

`estride_table.test.cc`: extended `VictimPassOrderAndInstallState` to
(a) assert the aging hit lands on the LAST-probed way specifically
(`occupants[2]`, since both victim passes start at the forced way 0
and scan in order, so `(0 + 2) % 3 == 2`), not just "some" way; (b)
age that same entry down to `u == 0` over two more forced-pass aging
calls, then assert the next allocation attempt returns
`AllocatedUZeroVictim` (previously uncovered anywhere in the suite)
and that `key0`'s newly-installed entry shows the expected
just-installed state (`conf == 1`, `u == 0`, `notFirstOcc == false`,
`stride == 0`, `lastValue` matching the actual value passed to that
`train()` call). Also added an `ASSERT_LT` iteration bound inside the
occupant-search loop so a future hash-formula change fails the test
loudly instead of hanging it (a deferred minor from the original
commit's occupant-search rewrite).

Covering test: rebuilt `estride_table.test.opt` and ran the full
binary -- 21/21 pass (20 `EStrideTable` including the extended
`VictimPassOrderAndInstallState`, 1 `EStrideArbiter`). Confirmed the
`.hh` doc-comment change forces `estride_table.cc` to recompile (as
expected for a header touch) and that the binary still links and
passes afterward. Rebuilt `gem5.opt` at the end -- links cleanly.

## Files changed
- `src/cpu/o3/vp/estride_table.hh` — doc comments only: documents
  `notLlcMiss`/`notL2Miss`/`notL1Miss` and disambiguates `fastInst`
  from `EVtageClassifier::fastInst`. No behavior change.
- `src/cpu/o3/vp/estride_table.test.cc` — extends
  `VictimPassOrderAndInstallState` with the aging-target pin, the
  `AllocatedUZeroVictim` coverage, and the search loop's iteration
  bound. No other test changed.
