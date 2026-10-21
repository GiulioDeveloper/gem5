# doc: Add VTAGE research report

- **Date:** 2026-08-04 14:40   ·   **Branch:** vp

## Goal
Second campaign record of the VP chapter: the VTAGE implementation on
the framework, the mechanisms it required, and the five-way Stage-IV
evaluation.

## Summary of changes
Report + four house-style figures + the per-checkpoint CSV backing
every table. Headlines: VTAGE geomean 1.0194 loads-only (double
LVP/MRN's gain) with 6.3x fewer wrongs at 99.92% accuracy; the
all-insts scope repaired (1.0171, beating lvp_all on 150/190); the
loser signature inverted (coverage now discriminates, flush volume no
longer does; zero losers beyond 5%, five beyond 1%); 37 of LVP's 71
losers rescued; the vpr_r.2.3 specimen isolating the scheduling-
side-effect class (-9.6% at 269 wrongs); the vphist isolation proof
(99.66% coverage where LVP is exactly 0); worst-case anatomy; the
five pre-evaluation review catches as the measurement-integrity
record. Next Steps include the history-length study prompted by the
provider-correct distribution (flat tail at L=64, 11% share --
truncated-series signature; distribution CSV shipped in figs/).

## Files changed
- `docs/research-log/VP/2026-08-04-vtage.md` — the report (covers
  a36364ad8d..e2379e0b32 + gem5-infra fc9536d).
- `docs/research-log/VP/figs/vtage_suite_{speedup,coverage,accuracy}.*`,
  `figs/vtage_allinsts_losers_dumbbell.*` — four charts + numbers.
- `docs/research-log/VP/figs/vtage_report_per_checkpoint.csv` —
  per-checkpoint five-way data behind the tables.
- `docs/research-log/VP/figs/vtage_provider_distribution.csv` — the
  provider-correct distribution behind Next Step 2.
