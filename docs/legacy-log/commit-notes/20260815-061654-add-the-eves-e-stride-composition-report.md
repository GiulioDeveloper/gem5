# doc: Add the EVES E-Stride composition report

- **Date:** 2026-08-15 15:25   ·   **Branch:** vp

## Goal
Record the EVES Stage 2 chapter verdict for posterity: the E-Stride
composition, ported source-verbatim and evaluated over 190 SPEC CPU
2026 checkpoints in both arbitration modes, does not improve on
E-VTAGE alone. evtage_all (1.0238) stays the canonical chapter best.

## Summary of changes
New research-log report (9 results, 2 figures + numbers CSVs +
datasets): geomeans 1.0165 (confidence-gated) / 0.9812 (verbatim
overwrite) vs base; the verbatim mode's loss dominated by the
port-widened no-confidence-check overwrite (stockfish family at
0.45-0.51 of control; 4.34M VTAGE-side wrong deliveries vs the
control's 649k total); the confidence-gated mode adds +2.64pp of
committed coverage at 99.18% stride accuracy and still nets -0.7% --
the chapter's sharpest coverage-is-not-speedup result. Microbench
mechanism proofs, the in-flight-counter closure evidence, and the
probe-set suite-balance caution are recorded. Also corrects the
EvesVP commit note's stat-count arithmetic (28 scalars + vector +
histogram, previously misstated).

## Files changed
- `docs/research-log/VP/2026-08-15-eves-estride-composition.md` — the
  report.
- `docs/research-log/VP/figs/eves_workload_ratio_covcommit.{png,pdf}`
  + `_numbers.csv` — lead figure: per-workload EVES/E-VTAGE ratios +
  committed coverage.
- `docs/research-log/VP/figs/eves_geomean_ladder.{png,pdf}` +
  `_numbers.csv` — the three 190-checkpoint geomeans.
- `docs/research-log/VP/figs/eves_190.csv`,
  `figs/eves_workload_rollup.csv` — datasets behind the figures.
- `docs/commit-notes/20260815-024230-add-the-eves-value-predictor.md`
  — stat-count arithmetic corrected.
