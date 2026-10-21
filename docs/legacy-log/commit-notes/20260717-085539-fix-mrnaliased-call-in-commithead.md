# cpu-o3: Fix mrnAliased() call in commitHead

- **Date:** 2026-07-17 08:55   ·   **Branch:** rbdev

## Goal
Make the branch compile again. commitHead() called a member that does not
exist, so any build of this tree failed.

## Summary of changes
8c90fd3333 ("cpu-o3: Map MRN-aliased load to producer at commit") added a call
to `head_inst->isMrnAliased()`. The accessor on DynInst is `mrnAliased()`
(dyn_inst.hh:446); `isMrnAliased` appears nowhere else in src/. One-word fix,
no behaviour change.

## Files changed
- `src/cpu/o3/commit.cc` — call `mrnAliased()` instead of the non-existent `isMrnAliased()` in commitHead().
