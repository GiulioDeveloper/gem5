# doc: Add MRN squash-reduction research report

- **Date:** 2026-07-27 14:23   ·   **Branch:** rbdev

## Goal
Record the squash-reduction campaign as a permanent research-log report: the
store-write-invalidation refutation, the address-instability findings, the
stability gate's design iterations, the worst-10 probe, the 190-checkpoint
gate sweep, and the off-by-default decision — so future work (especially
criticality-aware penalization) starts from a verified record instead of
session memory.

## Summary of changes
New paper-style report under docs/research-log/MRN/ with two house-style
figures (PNG + PDF + numbers-CSV each). Every number was independently
re-derived from the run trees before writing; two session-memory corrections
landed in the process (store-write ceiling is 0.055%, not 0.1%; the windowed
vpr.2.0 regression run no longer exists on disk and is cited to its
commit-note record). Eight Key Results in descending importance: suite wash
(+0.02%) -> off by default; +0.77% on the worst-10 with vpr.0.2 rescued;
sqlite.2.1 -10.6% schedule-criticality cost; invalidation refuted (0.055%
ceiling, 42:1 collateral); 80.2%-vs-23.7% address-instability separator;
flush-recovery arithmetic closure; the regime-stability discovery (StoreSet
training poisoning); the earning-test trade. Next steps ranked:
criticality-fused penalization first.

## Files changed
- `docs/research-log/MRN/2026-07-27-squash-reduction-stability-gate.md` —
  the report (Key Idea / Mechanism / Methodology / 8 Key Results / Next
  Steps / References; commits covered: 8443e4ab93, ac44caae2e).
- `docs/research-log/MRN/figs/scurve_gate_vs_th14.{png,pdf}` +
  `scurve_gate_vs_th14_numbers.csv` — lead figure: per-checkpoint gate-vs-
  baseline-MRN S-curve, tails annotated.
- `docs/research-log/MRN/figs/worst10_gate.{png,pdf}` +
  `worst10_gate_numbers.csv` — dumbbell chart: worst-10 checkpoints plus
  the sqlite outlier, baseline MRN vs gated, both vs no-MRN.
