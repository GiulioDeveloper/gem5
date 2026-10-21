# doc: Add MRN cost-side criticality closure report

- **Date:** 2026-07-28 01:48   ·   **Branch:** rbdev

## Goal
Close the MRN optimization chapter with a permanent record of the
criticality exploration: where MRN's loads resolve, the flush-weighted
ledger, its measured impossibility, and the finalized configuration.

## Summary of changes
New research-log report with two house-style figures. Seven Key Results:
correct forwards are 97.5% STLF+L1D (the benefit is scheduling, not
latency); the ledger's b axis is a dial between the count-gate and no-gate
endpoints with no separating point in 128x; root cause measured — the
populations are inverted on the cost-benefit plane (sqlite.2.1's critical
bindings earn ~7-13 corrects per cheap wrong vs churners' up to ~450);
flush cost scales 1 : 3.05 : 4.86 across L1D/L2/mem; ledger-margin
oscillation landmines at b=1/8 (vpr.2.0 -18.6%, conflictingLoads x6.5);
vpr.2.0's congested L1D wrongs flush 196 each; configuration finalized at
th14 with all gates off (suite geomean 1.0092/190). Next steps hand off to
benefit-side schedule-criticality as a new project. mrn-ideas.md gets a
CHAPTER CLOSED banner pointing at the three reports. Also removes the
2026-07-28 stat-cleanup commit-note (not needed for a trivial cleanup —
Rahul's call).

## Files changed
- `docs/research-log/MRN/2026-07-28-cost-side-criticality-closure.md` —
  the report (covers commits 9f037a0d44, 4fed00c084).
- `docs/research-log/MRN/figs/bsweep_dial.{png,pdf,_numbers.csv}` — lead
  figure: the b dial with the two oscillation landmines.
- `docs/research-log/MRN/figs/consumed_levels.{png,pdf,_numbers.csv}` —
  service-level distributions: all loads vs correct vs wrong forwards.
- `docs/garfield/mrn-ideas.md` — CHAPTER CLOSED banner.
- `docs/commit-notes/20260728-014437-*.md` — removed.
