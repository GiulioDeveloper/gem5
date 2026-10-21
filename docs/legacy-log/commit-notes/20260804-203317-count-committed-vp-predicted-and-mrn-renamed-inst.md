# cpu-o3: Count committed VP-predicted and MRN-renamed insts

- **Date:** 2026-08-04 21:00   ·   **Branch:** vp

## Goal
The VP framework's predictionsCorrect is verify-site counted: a
verified-correct prediction can still ride an older instruction's
wrong path and never commit. For "how many committed instructions did
the technique actually optimize" (the report-grade number), count at
commit.

## Summary of changes
Two scalar counters in O3 commit's stat group, incremented on
successful commitHead: committedVpPredicted (inst consumed a correct
value prediction) and committedMrned (load was correctly
memory-renamed). Committed implies correct for both: a wrong
resolution squashes its instruction inclusively before commit. The
MRN->VP rename ladder makes the two mutually exclusive per
instruction, so their sum counts insts optimized by either technique.
Verified on 707.ntest_r.0.3 vtage_all: stats value-identical to the
pre-change run modulo the two new lines; committedVpPredicted
10,601,541 vs predictionsCorrect 10,928,627 (3.0% wrong-path
residual, now measured).

## Files changed
- `src/cpu/o3/commit.hh` — the two Scalars with the
  committed-implies-correct rationale.
- `src/cpu/o3/commit.cc` — ADD_STATs + increments at the successful
  commitHead site.
