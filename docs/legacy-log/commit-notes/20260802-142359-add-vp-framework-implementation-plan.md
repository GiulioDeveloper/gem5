# doc: Add VP framework implementation plan

- **Date:** 2026-08-02 14:05   ·   **Branch:** vp

## Goal
Turn the approved VP design spec into an executable, subagent-driven
implementation plan with complete code for every task.

## Summary of changes
Six tasks: (1) params-free LVP core (vpKey + LvpTable + GTests), (2)
mechanical SquashReason generalization + IEW inclusive-squash extraction
with the squashDueToValueMispredict sibling, (3) SimObject layer
(BaseValuePredictor/LastValueVP, DynInst Vp state, valuePred param), (4)
pipeline integration (rename consume behind the MRN->VP->execute ladder,
LSQ + IEW verify/train sites, ROB/CPU squash accounting, --use-vp CLI),
(5) Stage-III microbenchmarks (vpchase self-loop pointer chase, vpalu
invariant multiply chain) in gem5-infra, (6) Stage-IV 190-checkpoint
SPEC26 sweep. Code blocks are grounded in verbatim excerpts scouted from
the current tree (rename/LSQ/IEW/ROB integration anchors, MRN wrapper
and GTest idioms, sim_opts factory pattern).

## Files changed
- `docs/superpowers/plans/2026-08-02-vp-framework-lvp.md` — the plan
  (new).
