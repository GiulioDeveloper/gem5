# doc: Add VP framework + last-value predictor design spec

- **Date:** 2026-08-02 13:10   ·   **Branch:** vp

## Goal
Open the Value Prediction chapter (third Garfield stage: branches →
memory renaming → value prediction) with an approved written design for
the algorithm-agnostic VP framework and the Last-Value Predictor that
proves it.

## Summary of changes
Design spec distilled from Rahul's rough plan (src/cpu/o3/vp/vp_spec.md)
and the design review. Key decisions: prefetcher-style SimObject
hierarchy with params-free GTest-able table cores; integer-only scalar
dests first; predict-at-rename / train-at-writeback / inclusive
verify-squash via a new IEW::squashDueToValueMispredict sibling entry
sharing squashDueToMemOrder's extracted body, with the squash-reason
enum generalized MrnSquashReason -> SquashReason plus a ValuePred
enumerator (mechanical renames only; MRN algorithm code untouched);
MRN → VP → execute priority ladder;
--use-vp <type> selection flag; conservative confidence defaults
(4-bit, threshold 15, reset-on-wrong); pinned stat counting sites for
coverage/accuracy; four deliverable stages ending in the 190-checkpoint
SPEC26 sweep.

## Files changed
- `docs/superpowers/specs/2026-08-02-vp-framework-design.md` — the
  design spec (new).
