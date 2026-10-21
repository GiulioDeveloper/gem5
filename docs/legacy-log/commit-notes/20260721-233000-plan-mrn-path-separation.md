# doc: Plan MRN path separation

- **Date:** 2026-07-21 23:30   ·   **Branch:** rbdev

## Goal
Implementation plan for the approved MRN path-separation spec.

## Summary of changes
Three tasks: (1) atomic C++ core separation -- two bool params replace
mrnMode/unified(), decoupled rename.cc triggers, per-path training gating;
(2) CLI driver flags; (3) verification suite including the independence proof
(alias-only run must show forwardsValue==0, forwardsAlias>0).

## Files changed
- `docs/superpowers/plans/2026-07-21-mrn-path-separation.md` — the implementation plan.
