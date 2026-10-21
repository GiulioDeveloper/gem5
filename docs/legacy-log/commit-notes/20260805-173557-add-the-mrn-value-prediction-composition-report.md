# doc: Add the MRN + value-prediction composition report

- **Date:** 2026-08-05 21:30   ·   **Branch:** vp

## Goal
Close the chapter's composition question with exact accounting: are
MRN and a VTAGE-class value predictor additive?

## Summary of changes
New report docs/research-log/VP/2026-08-05-mrn-vp-composition.md.
Verdict: subsumption. Exact disjoint commit-site counters over 190
checkpoints x 4 arms (MRN alone, VP alone, both ladder orders): MRN
alone optimizes 3.97% of committed uops (4.48% of insts) at 1.0093
(reproducing the MRN chapter's 1.0092 on the current binary); VP
alone 18.88% at 1.0171; both stacks cover more committed insts
(19.35%/19.36%) and run slower (1.0152/1.0139). Overlap 88.2%; the
VP-first flip isolates MRN's unique residual (52.9M, 0.49pp) and
still loses -- the strongest-form verdict. vpr_r.0.4 documented as
the cleanest scheduling-side-effect specimen (-30% with all accuracy
metrics flat). Two figures (4-bar composition lead, MRN per-workload
speedup + committed coverage) + numbers CSVs + per-checkpoint
datasets in figs/.

## Files changed
- `docs/research-log/VP/2026-08-05-mrn-vp-composition.md` — the
  report.
- `docs/research-log/VP/figs/mrn_composition*`,
  `figs/mrn_workload_*`, `figs/committed_optimized.csv`,
  `figs/ladder_flip_threeway.csv` — figures and datasets.
