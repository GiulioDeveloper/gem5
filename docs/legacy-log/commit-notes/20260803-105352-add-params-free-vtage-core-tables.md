# cpu-o3,doc: Add params-free VTAGE core tables

- **Date:** 2026-08-03 17:40   ·   **Branch:** vp

## Goal
VTAGE Task 1: the params-free core (VtageTables + the VpHistory
snapshot helper), unit-tested in isolation before any SimObject or
pipeline wiring, per the VTAGE design spec.

## Summary of changes
Seven banks (tagless 8K base + 6x1K tagged, histories 2..64, tags
12+rank), on-demand TAGE-style folds from 64-bit history snapshots
(FoldedHistory/gindex/gtag/F transcribed from gem5 TAGE), FPC
confidence with an injectable RNG, biased-rank provider tokens with
geometry asserts, commit-side train (token-directed, stale-token
recompute, val-overwrite only at c==0, u=correct, allocation with
u-aging) and the verify-site correctiveReset (c=0/u=0 only,
tag-checked). Review round (fold-fidelity + mutation lenses) found
the uPC fold arithmetically inert for hashed tables -- (upc << 48)
never reaches <=18-bit masked indices/tags -- fixed by mixing the uop
number into the hashed low bits (HPCA'14's own recipe; spec's Predict
step 1 amended accordingly) with a RED/GREEN separation test, plus
six mutation-survivor pins (VT0 corrective reset, saturation hold,
stale-tag train recompute, oldest-fold-bit and bank-shift golden
vectors, u-clear-on-wrong) and mojibake cleanup. 25/25 GTests;
lvp_table 15/15 untouched.

## Files changed
- `src/cpu/o3/vp/vp_history.hh` — params-free GHR/path snapshot
  helper (shift/target/restore).
- `src/cpu/o3/vp/vtage_tables.{hh,cc}` — the VTAGE core.
- `src/cpu/o3/vp/vtage_tables.test.cc` — 25 GTests, injectable RNG.
- `src/cpu/o3/vp/SConscript` — Source + GTest registration.
- `docs/superpowers/specs/2026-08-03-vtage-design.md` — uPC-mixing
  amendment to Predict step 1.
