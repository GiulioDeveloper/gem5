# doc: Add value-file rendezvous implementation plan

- **Date:** 2026-07-25 13:05   ·   **Branch:** rbdev

## Goal
Executable implementation plan for the value-file rendezvous predictor spec
(docs/superpowers/specs/2026-07-25-mrn-valuefile-rendezvous-design.md),
written for subagent-driven execution with per-task review.

## Summary of changes
Five tasks: (1) params-free MrnValueFileTables core + 10 GTest unit tests +
SConscript registration; (2) params/enum/stats/wrapper + sim_opts CLI
plumbing; (3) DynInst carry fields + rename-stage deposit and consume;
(4) LSQ publish/probe/last-value + consumed and shadow confidence training +
squash accounting; (5) controller-run experiments (microbenchmarks via the
conda-forge aarch64 cross toolchain, then the gcc checkpoint matrix). The
plan pins every integration point to verified file:line anchors and carries
the complete unit-test code and consumption-decision code inline.

## Files changed
- `docs/superpowers/plans/2026-07-25-mrn-valuefile-rendezvous.md` — the plan.
