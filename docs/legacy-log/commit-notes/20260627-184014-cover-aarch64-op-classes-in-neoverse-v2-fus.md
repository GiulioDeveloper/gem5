# configs: Cover AArch64 op classes in Neoverse V2 FUs

- **Date:** 2026-06-27 18:40   ·   **Branch:** rbdev

## Goal
After the `FloatMultAcc` fix, ensure no other AArch64 instruction can stall the
O3 pipeline the same way. An audit found the upstream Neoverse V2 FUs covered only
36 of gem5's 88 op classes.

## Summary of changes
Add the missing AArch64 op classes to the FP and load/store units: NEON/SVE
integer & FP reductions, dot product, vector extract, SVE divide/predicate, the
BFloat16 family, the crypto extensions (AES/SHA/SM4/CRC), and
FloatMemRead/FloatMemWrite/InstPrefetch. Coverage is now 68/88; the remaining 20
are RISC-V-vector and SME (Matrix*) op classes, which AArch64 does not emit.
Latencies are approximate; the deadlock detector is the real safety net for any
op class still missed.

## Files changed
- `configs/garfield/arm/neoverse_v2.py` — broaden FP and load/store op-class
  coverage from 36 to 68 of 88.
