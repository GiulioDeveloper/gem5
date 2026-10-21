# doc: Add last-value predictor research report

- **Date:** 2026-08-04 10:20   ·   **Branch:** vp

## Goal
Permanent research-log record of the VP framework + LVP campaign:
mechanism, the doomed-window finding, Stage-III proof, and the
190-checkpoint Stage-IV results in both scopes.

## Summary of changes
Report with four house-style figures (PNG+PDF+numbers-CSV each).
Headline: loads-only LVP geomean 1.0093/190 -- statistically
identical to MRN's finalized 1.0092 from a single PC-indexed table;
all-insts scope is a net loss at the default config (1.0053, 123/45
worse/better vs loads-only) with high variance both ways; loser
anatomy shows mispredict volume, not accuracy or per-flush cost, is
the only winner/loser discriminator (loads-only tail: zero
checkpoints beyond -3%); the 89 all-insts losers were break-even at
loads-only and 32 flipped from winners; a pure scheduling-side-effect
loser class exists (ocio_r.2.0: -2.6% at 12 wrongs, accuracy 1.0).
Suite split per official SPEC CPU2026 docs (115 int / 75 fp
checkpoints; suite-neutral gains). Charts: suite box-whiskers for
speedup (geomean diamonds) / coverage / accuracy (arith means,
zoomed), plus the all-insts loser dumbbell (worst 40 of 89 plotted,
all 89 in the CSV).

## Files changed
- `docs/research-log/VP/2026-08-03-last-value-predictor.md` — the
  report (covers commits 155b5c6358..420d6d3ba8 + gem5-infra
  68ceab3).
- `docs/research-log/VP/figs/lvp_suite_{speedup,coverage,accuracy}.*`
  — suite box-whisker charts + numbers CSVs.
- `docs/research-log/VP/figs/lvp_allinsts_losers_dumbbell.*` — the
  loser transition chart + full 89-row CSV.
