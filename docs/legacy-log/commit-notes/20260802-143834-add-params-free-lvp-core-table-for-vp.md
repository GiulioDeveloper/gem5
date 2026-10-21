# cpu-o3: Add params-free LVP core table for VP

- **Date:** 2026-08-02 15:20   ·   **Branch:** vp

## Goal
First implementation task of the Value Prediction chapter: the
params-free Last-Value Predictor core, unit-tested in isolation before
any SimObject/pipeline wiring exists (the MrnValueFileTables pattern).

## Summary of changes
New src/cpu/o3/vp/ directory. LvpTable: set-associative, LRU,
full-tag VPT with saturating confidence (reset-or-decrement on
mismatch, knobbed); vpKey folds (PC, micro-PC) so cracked micro-ops do
not ping-pong one entry. 14 GTests including three mutation-driven
pinning tests from review (eviction allocates unconfident; decrement
floors at zero -- an unguarded decrement would wrap unsigned and go
permanently confident; allocation refreshes LRU recency) and a
constructor guard fixing shift-UB for confBits >= 32 (member-init ran
before fatal_if could fire). Also stages the chapter kickoff material:
Rahul's rough plan (vp_spec.md) and the VTAGE/EVES/LVP papers.

## Files changed
- `src/cpu/o3/vp/vp_key.hh` — (PC, micro-PC) -> lookup key folding.
- `src/cpu/o3/vp/lvp_table.{hh,cc}` — the params-free VPT core.
- `src/cpu/o3/vp/lvp_table.test.cc` — 14 GTests.
- `src/cpu/o3/vp/SConscript` — Source + GTest registration (SimObject
  and DebugFlag lines arrive with the framework task).
- `src/cpu/o3/vp/vp_spec.md`, `src/cpu/o3/vp/papers/*.pdf` — chapter
  kickoff material (design plan + anchor papers).
