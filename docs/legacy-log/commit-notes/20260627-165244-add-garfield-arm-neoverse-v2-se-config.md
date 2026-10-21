# configs: Add garfield ARM Neoverse V2 SE config

- **Date:** 2026-06-27 16:52   ·   **Branch:** rbdev

## Goal
Provide a self-contained syscall-emulation (SE) config for a Neoverse V2-class
out-of-order ARM core — the base machine for the garfield work.

## Summary of changes
Add `configs/garfield/arm/`: an owned copy of the upstream Neoverse V2 core and
caches (tuned with LRU L1 replacement and the BOP prefetcher moved from L1D to
L2), per-core cache wiring with independent prefetcher toggles, and an argparse
SE driver. Verified on `build/ARM/gem5.opt`: the hello smoke test runs to
completion and the prefetch toggles, `--mem-type`, and `--max-insts` all work.

## Files changed
- `configs/garfield/__init__.py` — package init for the garfield config tree.
- `configs/garfield/arm/__init__.py` — package init for the ARM configs.
- `configs/garfield/arm/neoverse_v2.py` — owned Neoverse V2 core + caches
  (LRU L1, BOP moved to L2).
- `configs/garfield/arm/cache_hierarchy.py` — L1I/L1D/L2 (and MMU caches) wiring
  with independent FDP, L1D, and L2 prefetcher toggles.
- `configs/garfield/arm/se_run.py` — SE driver: local ARM binary or hello smoke
  test, configurable cores/clock/DRAM, instruction cap, and prefetch ablation.
