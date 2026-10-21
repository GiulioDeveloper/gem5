# doc: MRN legacy-path deletion design spec

- **Date:** 2026-07-26 14:05   ·   **Branch:** rbdev

## Goal
Spec the consolidation of MemRenamePredictor onto the value-file rendezvous
model: delete the legacy value-snapshot path and lsq_forward correlator,
de-risked by the composition study (zero net in every corner).

## Summary of changes
Full-amputation scope (user decision): files, pipeline hooks, DynInst state,
params/CLI/stats inventory of what dies and what remains; --use-mrn becomes
the model; baseline MRN respells as --use-mrn --mrn-alias
--mrn-conf-threshold 14. Verification: bit-identity on surviving stats for
gcc/hello/no-MRN, unit tests, grep-clean removal completeness, independent
review before commit.

## Files changed
- `docs/superpowers/specs/2026-07-26-mrn-legacy-path-deletion-design.md` — the spec.
