# cpu-o3,doc: Close VP final-review findings

- **Date:** 2026-08-02 18:20   ·   **Branch:** vp

## Goal
Close the seven minor findings from the whole-branch final review
(verdicts approve/approve/approve) before the Stage-IV SPEC26 sweep,
so the sweep binary carries the hardened guard and the thrash signal.

## Summary of changes
Code: IEW constructor now fatal_ifs on valuePred + a set squashWidth
(the doomed-window guard's clear requires single-cycle victim marking
-- fail loudly instead of silently reopening the shadow-train hole);
LvpTrainOutcome gains Evicted (valid-entry displacement) with an
evictions stat in LastValueVP and GTest pins; wrongFlushedByLevel's
description now states the loads-only identity qualification. Spec
amendments: verifyResult documented as the fourth pipeline-facing
operation; full eligibility exclusion list; clamped-decrement
semantics in the LVP section; eligibleLoads/eligibleNonLoads stat
shape. 15/15 GTests; full build.

## Files changed
- `src/cpu/o3/iew.cc` — squashWidth precondition fatal_if.
- `src/cpu/o3/vp/lvp_table.{hh,cc}` — Evicted train outcome.
- `src/cpu/o3/vp/last_value.{hh,cc}` — evictions stat.
- `src/cpu/o3/vp/lvp_table.test.cc` — Evicted pins in the two
  eviction tests.
- `src/cpu/o3/vp/base.cc` — wrongFlushedByLevel identity note.
- `docs/superpowers/specs/2026-08-02-vp-framework-design.md` — four
  conformance amendments.
