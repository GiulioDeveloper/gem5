# cpu-o3,doc: Close VTAGE final-review findings

- **Date:** 2026-08-04 01:50   ·   **Branch:** vp

## Goal
Close the five whole-branch final-review findings before the VTAGE
Stage-IV sweep -- most importantly the second-generation uPC aliasing
defect, which would have silently distorted the sweep's headline
numbers on the cracked-load population VTAGE targets.

## Summary of changes
The Task-1 uPC amendment (XOR of the raw uop number) merely moved the
alias: it toggles PC-delta bit 0, merging (pc, uop 1) with (pc +/- 4,
uop 0) in every component's index and tag (verified 100k/100k). The
formula becomes concatenation -- (((pc ^ (upc << 48)) >> 2) << 2) |
(upc & 3) -- placing the uop residue in the vacated low bits with the
PC-delta bits untouched; spec Predict step 1 re-amended with the
why (any XOR of raw upc recreates the alias at a power-of-two PC
distance). GoldenTokens re-pinned; new MicroOpDoesNotAliasNeighborPc
test proven non-vacuous by defect replay; a combo-test collision
constant re-derived after the formula change. Merge hygiene: the 12
session-review jargon fragments stripped from shared-file comments;
the 9 tracked-code citations of gitignored evidence files repointed
to tracked sources (design spec, HPCA-20 2014, gem5's tage_base) or
inlined (the commit-hook physreg-liveness argument). Two spec
amendments: VpLookupContext's nested VpHistSnapshot shape, and the
framework-level (base-class) home of historyRestores/
correctiveResetStale with the LVP identity claim qualified to
behavior + pre-existing stat values. Validation: 29/29 + 15/15 +
20/20; smoke a-j all pass with a-g bit-identical; vphist correlation
proof intact on the new formula (coverage 0.9966, accuracy 1.0,
tagged providers dominant).

## Files changed
- `src/cpu/o3/vp/vtage_tables.{hh,cc}` — concatenation formula +
  comment; citation repointing.
- `src/cpu/o3/vp/vtage_tables.test.cc` — neighbor-alias test, golden
  re-pins, combo-test re-derivation.
- `src/cpu/o3/vp/vtage.hh` — citation repointing.
- `src/cpu/o3/{fetch,bac}.{cc,hh}`, `commit.{hh,cc}`, `iew.hh`,
  `lsq_unit.cc` — review-jargon comment cleanup; inlined liveness
  argument.
- `docs/superpowers/specs/2026-08-03-vtage-design.md` — Predict
  step 1, VpLookupContext shape, statistics-home amendments.
