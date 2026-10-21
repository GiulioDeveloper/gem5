# configs: Add missing FloatMultAcc FU to Neoverse V2

- **Date:** 2026-06-27 18:34   ·   **Branch:** rbdev

## Goal
Fix indefinite O3 pipeline stalls on FP workloads. The `NeoverseV2_FP` functional
unit (copied from upstream) omitted the scalar `FloatMultAcc` op class, so no FU
could execute a fused multiply-add: any `fmadd` could never issue and the pipeline
livelocked. Compilers emit `fmadd` pervasively (libm sin/cos, FFT butterflies,
`x / 2^k`), so essentially all FP-heavy SE workloads hung.

## Summary of changes
Add `OpDesc(opClass="FloatMultAcc", opLat=4)` to the FP pool. The config is loaded
at runtime, so no rebuild is needed.

## Files changed
- `configs/garfield/arm/neoverse_v2.py` — add the `FloatMultAcc` OpDesc to the FP
  functional unit.
