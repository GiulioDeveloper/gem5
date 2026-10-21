# cpu-o3,configs: Add the VTAGE value predictor

- **Date:** 2026-08-03 23:30   ·   **Branch:** vp

## Goal
VTAGE Task 4: the VtageVP SimObject that brings the history wiring to
life, plus CLI and the full smoke validation.

## Summary of changes
VtageVP wraps VtageTables (params marshalled positionally -- order
verified against the struct in review; RNG adapted from
Random::genRandom() to the core's injectable double() in [0,1),
global-seed deterministic). trainsAtCommit + usesHistory both true;
stats: per-component provider vectors (sized 1 + numTagged after
review caught a hardcoded 7 that would index out of bounds at the
legal numTagged=7), allocations/aging, corrective resets, token-stale
recomputes, FPC fired/suppressed (exact split via the additive
read-only peekProvider core query). CLI: --use-vp vtage +
--vtage-conf-threshold. Smoke matrix extended to ten runs: VTAGE on
vpchase behaves as designed (VT0-dominant, ~zero wrongs); the hostile
run needed a workload substitution discovered and proven during
implementation -- ptrchase cannot produce VTAGE wrongs (its committed
values are a pairwise-distinct Sattolo cycle; LVP's wrongs there come
from the verify-site + refetch double-train that commit-only training
correctly lacks) -- branchsort all-insts at threshold 1 exercises the
corrective-reset arm for real: 51,962 wrongs with correctiveResets
matching exactly, identity exact, checksum equal to the no-VP
baseline, historyRestores::missed zero throughout. The MRN+VTAGE
ladder run shows the expected signature (MRN claims the loads,
VTAGE trains at commit via token-less recomputes).

## Files changed
- `src/cpu/o3/vp/vtage.{hh,cc}` — the SimObject wrapper + stats.
- `src/cpu/o3/vp/vtage_tables.{hh,cc}` — additive peekProvider query;
  indent fix.
- `src/cpu/o3/vp/ValuePredictor.py`, `SConscript` — VtageVP params +
  registration.
- `configs/garfield/arm/sim_opts.py` — --use-vp vtage,
  --vtage-conf-threshold.
