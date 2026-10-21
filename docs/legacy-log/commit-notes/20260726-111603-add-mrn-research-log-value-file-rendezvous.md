# doc: Add MRN research log, value-file rendezvous report

- **Date:** 2026-07-26 02:30   ·   **Branch:** rbdev

## Goal
Start the docs/research-log/ space and record the value-file rendezvous
project end-to-end for posterity, organized like a paper: key idea,
mechanism, evaluation methodology, key results, open directions.

## Summary of changes
New report docs/research-log/MRN/2026-07-26-value-file-rendezvous.md:
mechanism (VF/SLC/SC structures, store/load algorithms, deviations from
Tyson & Austin MICRO'97 and Reinman et al. ICS'99), files + commit hashes
covered, methodology (190 SPEC26 Rate checkpoints, 10M/50M, threshold grid),
and nine enumerated insights led by the first net-positive MRN geomean
(+0.92% at threshold 14) and the last-value dominance finding, connected to
Constable (ISCA'24), including the legacy-path composition study (2x2 over
fallback reach x snapshot-path threshold: the legacy path adds zero net
and is de-risked for deletion). S-curve chart + numbers CSV copied into
docs/research-log/MRN/figs/ so the tracked tree is self-contained.

## Files changed
- `docs/research-log/MRN/2026-07-26-value-file-rendezvous.md` — the report.
- `docs/research-log/MRN/figs/scurve_mrn_th14.{png,pdf}` — S-curve chart.
- `docs/research-log/MRN/figs/scurve_mrn_th14_numbers.csv` — chart numbers.
