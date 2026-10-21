# doc: Add the E-Stride + EVES implementation plan

- **Date:** 2026-08-15 00:45   ·   **Branch:** vp

## Goal
Task-by-task implementation plan for the committed E-Stride design
spec (2026-08-14-estride-design.md): five tasks from the framework
in-flight counter facility through the EvesVP SimObject to the
probe/190 evaluation, with full code blocks, GTest suites, and
bit-identity gates inline so task implementers need no session
context.

## Summary of changes
Task 1: per-PC in-flight occurrence counters in BaseValuePredictor
(header-only VpInflightMap + GTests, VpInflightCounted DynInst flag,
rename/ROB/CPU wiring, notifyRenamed superseded by notifyRenamedInst,
identity-gate harness + comparator captured at the pre-change HEAD).
Task 2: params-free EStrideTable core + pure eves_arbiter.hh with the
verbatim CVP rules and a ~20-test GTest suite pinning every spec arm.
Task 3: EvesVP SimObject, Python/SConscript/sim_opts plumbing,
directed routing smokes, identity re-gate. Task 4: vpstride/vpstorm
microbenches (gem5-infra). Task 5: probe-16 -> 190 evaluation.

## Files changed
- `docs/superpowers/plans/2026-08-15-estride-eves.md` — the plan.
