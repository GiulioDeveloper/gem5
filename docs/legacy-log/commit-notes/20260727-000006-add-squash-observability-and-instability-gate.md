# cpu-o3,configs: Add squash observability and instability gate

- **Date:** 2026-07-27 00:55   ·   **Branch:** rbdev

## Goal
Instrument the causes of last-value misprediction flushes and provide an
off-by-default gate against address-unstable self-bindings, from the
squash-reduction investigation on the 10 material-loser checkpoints.

## Summary of changes
Probe-only observability (behavior-neutral, verified bit-identical at
defaults): a load-address monitor (loads publish line->cell at execute;
every store's resolved address probes it) classifying last-value verify
outcomes by prior store-write; per-cell line tracking classifying them by
address stability. Findings: store-write-catchable wrongs are 0.1% (store-
write invalidation refuted); address-changed wrongs are 80.2% -- but 23.7%
of CORRECT forwards are also address-changed (address-tolerant value-
stable loads are a large legitimate class).

Gate (lvStabilityTarget, default 0 = off; --mrn-lv-stability-target):
two wrong-with-changed-address strikes within a slow-decay horizon, and a
failing lifetime corrects-per-wrong earning test, disable last-value
consumption for that PC (sticky) until sustained same-line execution.
Sentinel results: material losers +1.09% geomean (vpr.0.2 +4.6%, flushes
2.59M->0.27M); three of four winner guard-rails clean. Two coupling
hazards discovered and documented: (1) oscillating forwarding regimes
poison StoreSet training (vpr.2.0 -18% under a windowed variant, cured by
sticky hysteresis); (2) sqlite.2.1 -10.6% under every variant -- its
wrong-dense hot loads are schedule-critical, and suppressing them triples
LSQ order violations regardless of targeting statistics. Gate therefore
ships disabled; enabling it is a per-experiment decision.

## Files changed
- `src/cpu/o3/mem_rename_valuefile.{hh,cc}` — load-address monitor, address tracking, strike/earning/stability gate; 6 new unit tests.
- `src/cpu/o3/mem_rename_valuefile.test.cc` — monitor, classifier, and gate tests (19 total).
- `src/cpu/o3/mem_rename_predictor.hh`, `mem_rename_predictor_sim.cc` — wrappers + 13 observability/gate stats.
- `src/cpu/o3/MemRenamePredictor.py` — lmEntries/lmAssoc/lvStabilityTarget params.
- `src/cpu/o3/rename.cc` — probation-suppressed last-value consumption arm.
- `src/cpu/o3/lsq_unit.cc` — store-write probe; verify-site classifiers.
- `configs/garfield/arm/sim_opts.py` — --mrn-lv-stability-target.
