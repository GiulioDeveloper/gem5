# doc: Add VTAGE implementation plan

- **Date:** 2026-08-03 15:05   ·   **Branch:** vp

## Goal
Executable five-task plan for the VTAGE spec, grounded in three tree
scouts (BAC/fetch history choke points, the commit-train hook with
its physreg-liveness proof, gem5 TAGE fold/index/tag arithmetic and
the tree's RNG API).

## Summary of changes
Tasks: (1) params-free VtageTables core + VpHistory helper + GTests
with an injectable RNG; (2) framework generalization -- lookup
context, predict-result token channel, trainAtCommit/usesHistory
knobs, DynInst snapshot+token -- gated on LVP bit-identity; (3)
pipeline wiring: BAC stamp/update, per-initiator history restores,
Commit::commitHead train hook, verify-site corrective reset with
train-site gating; (4) VtageVP SimObject + CLI + smoke matrix incl.
the hostile confThreshold-1 run with predictionsWrong > 0 as a pass
criterion; (5) vphist microbenchmark (branch-correlated values,
if-conversion guarded) and the Stage-IV sweep in both scopes reusing
existing baselines. Scout briefs preserved in .superpowers/sdd/ as
required per-task reading.

## Files changed
- `docs/superpowers/plans/2026-08-03-vtage.md` — the plan (new).
