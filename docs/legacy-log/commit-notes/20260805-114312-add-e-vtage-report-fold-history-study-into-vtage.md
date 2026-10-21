# doc: Add E-VTAGE report; fold history study into VTAGE

- **Date:** 2026-08-05 05:30   ·   **Branch:** vp

## Goal
Publish the EVES Stage-1 record: the E-VTAGE report (VTAGE dense-64
as baseline, ten results, six figures) and the VTAGE report's
history-series amendment that establishes that baseline.

## Summary of changes
VTAGE report: new result 3 (density-beats-reach: probe 1.0571 for
the within-64 7-component series vs 1.0493/1.0382 for reach-to-128
and 1.0422 default; 190-scale 1.0212/1.0181; vpr_r.2.0 +26.5%
reversal), history-series methodology entry, 09c01d45f2 in commits,
the completed next step retired, vtage_hist_series figure + probe
CSV. E-VTAGE report (2026-08-05-evtage.md): headline 1.0238
all-insts (+0.55% over the iso-history control, 122/190; SPECfp
+0.89pp), workload tornado (19/26 ahead; flightdm +6.9%), the
selectivity ledger (all-insts coverage down 41.5->37.9% with wrongs
-28%), accuracy preserved, exact commit-gated committed coverage
17.98% of uops / 20.29% of insts (verify-site overcount measured
+5.4%; the rerun also proved counter/FDP-fix/ladder-param inertness
by 190/190 IPC bit-identity), the marian scope-flip specimen, the
tagged-base confound, the FDP infinite-loop fix, and the
measurement-integrity record. MRN-composition results deliberately
excluded (second report).

## Files changed
- `docs/research-log/VP/2026-08-04-vtage.md` — history-series
  amendment.
- `docs/research-log/VP/2026-08-05-evtage.md` — the E-VTAGE report.
- `docs/research-log/VP/figs/*` — six E-VTAGE charts + the
  history-series chart (PNG+PDF+numbers CSVs), per-checkpoint and
  per-workload datasets.
