# cpu-o3: Add VP per-PC in-flight occurrence counters

- **Date:** 2026-08-15 01:00   ·   **Branch:** vp

## Goal
First landable seam of the E-Stride + EVES design
(docs/superpowers/specs/2026-08-14-estride-design.md, S4): a
framework-level per-PC in-flight occurrence counter facility in
`BaseValuePredictor`, opt-in via a new `usesInflightCounts()` knob and
inert (default false) for every predictor that exists today. A later
task's `EvesVP` extrapolator will read `inflightCount(key)` to scale
its stride prediction by the number of same-PC instances already
in flight, replacing CVP-1 EVES's approximate 256-deep ring scan with
an exact counter.

## Summary of changes
Added a header-only `VpInflightMap` (increment/decrement/count/size,
erase-on-zero, `panic_if` on decrement-underflow) with its own GTest
suite (map semantics + an interleaved rename/commit/squash zero-sum
sequence). Added a `VpInflightCounted` DynInst flag. Wired the
exactly-once closure into `BaseValuePredictor`: `notifyRenamedInst()`
increments at rename (in-scope, opted-in predictors only) and
supersedes the previously-unwired `notifyRenamed(ThreadID)` (deleted;
zero callers); `train()` decrements at commit-train; the new
`notifySquashedInFlight()` decrements from the two squash walks
(`ROB::doSquash`, `CPU::squashInstIt`). Added three stats
(inflightIncrements/DecTrain/DecSquash) for the closure identity.
Captured a five-config bit-identity gate (lvp/vtage/evtage/evtage_all/
one MRN+VP config) at the pre-change HEAD and reran it after the
change: all five configs value-identical on every pre-existing stat,
with only the three new counters appearing (at zero), confirming the
new hooks are behaviorally inert until some predictor opts in.

Deviation from the task brief's literal GTest: the underflow-panic
test uses `EXPECT_ANY_THROW` rather than `EXPECT_DEATH`, because
`panic()`/`panic_if()` throw (rather than abort the process) once
linked into a GTest binary via `base/gtest/logging_mock.cc` -- the
same reason `vtage_tables.test.cc` and `evtage_tables.test.cc` already
use `ASSERT_ANY_THROW` for their own fatal_if construction checks.

## Files changed
- `src/cpu/o3/vp/vp_inflight_map.hh` — new header-only exact
  per-key occurrence map (increment/decrement/count/size).
- `src/cpu/o3/vp/vp_inflight_map.test.cc` — new GTest suite for the
  map, including the interleaved rename/commit/squash zero-sum case.
- `src/cpu/o3/vp/base.hh` — `usesInflightCounts()` knob,
  `notifyRenamedInst()`/`notifySquashedInFlight()`/`inflightCount()`
  declarations, `inflight` backing store, three new stats; deletes
  `notifyRenamed(ThreadID)`.
- `src/cpu/o3/vp/base.cc` — implements the three new methods, the
  commit-train decrement in `train()`, and registers the new stats.
- `src/cpu/o3/dyn_inst.hh` — `VpInflightCounted` flag + accessors.
- `src/cpu/o3/rename.cc` — one `notifyRenamedInst()` call after the
  consumption ladder.
- `src/cpu/o3/rob.cc`, `src/cpu/o3/cpu.cc` — one
  `notifySquashedInFlight()` call each, beside the existing VP squash
  notification in the two squash walks.
- `src/cpu/o3/vp/SConscript` — registers the new GTest.
