# doc: Add E-VTAGE implementation plan

- **Date:** 2026-08-04 23:20   ·   **Branch:** vp

## Goal
Three-task executable plan for the E-VTAGE spec: forked params-free
core with the verbatim policy rules, the classifier-context framework
extension + SimObject/CLI, and the probe-gated 190 A/B.

## Summary of changes
Task 1: EVtageTables fork (policies diverge too much for
subclassing) with tests-first coverage of every transcribed formula
and the pinned delivered-wrong endpoint. Task 2: VpClassifierInfo
threading (level/opclass/operand/indirect-call mappings), rename-count
hook for the burst guard, EVtageVP + --use-vp evtage, smoke additions
-- gated on LVP AND VTAGE bit-identity. Task 3: 16-checkpoint probe
vs committed vtage, promotion to 190 both scopes unless clearly
negative. The spec's formulas are transcription law; spec-vs-brief
disputes escalate.

## Files changed
- `docs/superpowers/plans/2026-08-04-evtage.md` — the plan (new).
