---
type: experiment
status: open
updated: 2026-11-13
sources:
  - runs/microbench-tma/
  - src/cpu/o3/tdm.cc
  - src/cpu/o3/rename.cc
  - "[[top-down-accounting]]"
  - https://github.com/VerticalResearchGroup/microbench
tags: [top-down, validation, microbenchmark, back-end]
---

# Top-down accounting on microbenchmarks with a known answer

**Question:** does the top-down tree ([[top-down-accounting]]) give the
right answer on kernels whose bottleneck is known by construction, in
particular the split of back-end bound into memory and core?

**Answer so far:** the pure cases are right (DRAM chase, multiply chain,
streaming stores, random branch). Three problems showed up:

1. **A bug, fixed the same day:** rename stalls on physical registers or a
   full SQ were counted as front-end bound (up to 0.45 of slots on these
   kernels; see [[#The fix]]).
2. **A property of the paper's method:** work that overlaps a miss moves
   memory bound into core bound. A kernel whose time is set entirely by L2
   latency reports memory 0.08, core 0.54.
3. **A fetch-model effect:** a tight dependent loop is front-end bound
   (0.80) because fetch waits on an L1I hit after every taken branch
   ([[2026-11-03-perfect-l1i]]).

One run per kernel, SE mode. The Results tables are from before the fix
(outputs kept in `out/pf-off-before-fix/` and `kernels/before-fix/`);
[[#The fix]] has the numbers after it.

## Setup

- Code: `gfdev` at `387f75040f`, `build/ARM/gem5.opt`.
- Machine: `configs/garfield/arm/se_run.py` (Neoverse V2, SE mode), data
  prefetchers off (`--disable-l1d-prefetch --disable-l2-prefetch`).
- Region of interest: each binary runs its kernel once as warm-up, then
  once between `m5 resetstats` and `m5 dumpstats`. The first stats block
  is the region.
- Compiler: `aarch64-linux-gnu-gcc` 15.2, static binaries.

**VRG suite** (`runs/microbench-tma/`): 12 of the Vertical Research Group
microbenchmarks, sources in `src/`, built by `build.sh` (`-O3`,
`-fno-ipa-pure-const`; `-fno-if-conversion` on the `CC*` ones), run by
`run.sh`, read by `td_micro.py`. Outputs `out/pf-off/`.

**Split kernels** (`runs/microbench-tma/kernels/`): `kern.c`, hand-written
assembly loops, built and run by `build_run.sh`, read by `report.py`.
Outputs `out/{base,fe8}/`, tables `report-{base,fe8}.txt`.

| kernel | loop body | ground truth |
|---|---|---|
| `chaseI<K>-<lvl>` | pointer chase + K adds independent of the load | time is flat in K while the chase sets it: memory |
| `chaseD<K>-<lvl>` | pointer chase + K adds dependent on the loaded pointer | core share = (cycles − chase-only cycles) / cycles |
| `mlp8-<lvl>` | 8 independent chases | memory |
| `store-<lvl>` | one store per line, sequential | store |
| `mul` | 8 dependent multiplies | core |
| `alu64` | 64 independent adds | retiring |

Levels: `L1` 16 KiB, `L2` 512 KiB, `MEM` 6 MiB (the L2 is 2 MiB). The chase
is one random cycle over all lines. Two front ends: `base` (fetch/decode 6
wide, L1I hit 4 cycles) and `fe8` (`--front-end-width 8 --l1i-cycles 1`).

## Results

Fractions as `tdm.cc` reports them (Level 2/3 scaled into slots).

### VRG suite (`out/pf-off`, base front end)

| bench | expected | top-down | reading |
|---|---|---|---|
| ED1 | core | core 0.90 | as expected |
| CCh | branch mispredicts | bad speculation 0.39, all branch | as expected |
| MD | memory, L1 | memory 0.51 (L1 0.46) | as expected |
| ML2 | memory, L2 | memory 0.58 (L2 0.57) | as expected |
| MM | memory, DRAM | memory 0.84 (L2 0.80) | correct: the list is exactly 2 MiB and fits the L2 (65,440 L2 hits, 102 misses) |
| CCa | retiring | core 0.75 | correct: GCC made the body a dependent add chain |
| STL2 | store | core 0.72 | correct: the IQ fills (19K `iqFullEvents`), the SQ never does |
| MIP | fetch latency | core 0.92 | test broken: the warm-up loads the code into the L1I (4 misses) |
| M_Dyn | machine clears | FE 0.54, 1 violation | not a test: the store-set predictor learns the pattern |
| EM5 | core | **FE 0.80**, BE 0 | fetch waits on the L1I in 40% of cycles (8,207 of 20,522); rename is never blocked |

### Split kernels, `fe8`

| kernel | cycles/iter | FE | BE | memory | core | ground truth |
|---|---|---|---|---|---|---|
| chaseI0-MEM | 212.4 | 0.00 | 1.00 | 0.98 | 0.02 | memory |
| mlp8-MEM | 227.4 | 0.00 | 0.99 | 0.95 | 0.04 | memory |
| mul | 32.0 | 0.02 | 0.94 | 0.00 | 0.94 | core |
| store-MEM | 34.0 | 0.06 | 0.93 | 0.87 (store) | 0.06 | store |
| chaseD8-L2 | 39.0 | 0.02 | 0.95 | 0.51 | 0.44 | core 0.41 |
| chaseD32-L2 | 87.0 | 0.03 | 0.93 | 0.22 | 0.70 | core 0.74 |
| chaseD128-L2 | 279.0 | 0.03 | 0.91 | 0.07 | 0.84 | core 0.92 |
| chaseD32-MEM | 279.9 | 0.01 | 0.98 | 0.75 | 0.23 | core 0.24 |
| chaseI0-L2 | 23.0 | 0.01 | 0.98 | 0.84 | 0.13 | memory |
| chaseI8-L2 | 23.0 | **0.22** | 0.72 | 0.47 | 0.25 | memory |
| chaseI32-L2 | 23.0 | **0.19** | 0.62 | **0.08** | **0.54** | memory |
| chaseI32-MEM | 212.6 | 0.02 | 0.96 | 0.87 | 0.09 | memory |

`base` gives the same picture with more front-end bound
(`report-base.txt`). `chaseD128-MEM` has no region of interest in `base`.

### The register and SQ leak

| kernel | config | rename `Unblocking` cycles | full events | FE bound |
|---|---|---|---|---|
| store-MEM | base | 2.20M | 2.19M `SQFullEvents` | 0.167 |
| store-L2 | base | 175K | 175K `SQFullEvents` | 0.455 |
| chaseI8-L2 | base | 660K | 638K `fullRegistersEvents` | 0.360 |
| chaseI8-L2 | fe8 | 685K | 669K `fullRegistersEvents` | 0.216 |

Mechanism: `Rename::checkStall` blocks only on a full ROB or IQ, or on LQ
and SQ both full. On a full SQ or no free register, rename retries every
cycle from its skid buffer. `countFrontendBubbles` runs first, sees free
ROB and IQ entries, and charges `8 − skid size` slots to front-end
bandwidth; then rename renames nothing. A full LQ takes the same path (not
exercised here).

### alu64 under `fe8`

27.5 cycles per iteration against 18.0 in `base`. With the faster front end
the IQ fills (440K `iqFullEvents`, 0 in `base`) and then issues 1-2
micro-ops a cycle where it issued 4. Top-down reports core 0.52, which
matches the symptom. Not diagnosed.

## The fix

2026-11-13, `src/cpu/o3/rename.{cc,hh}` (uncommitted): `renameInsts`
counts front-end bubbles after its loop, and counts none when the loop
stopped because an instruction had no LQ entry, no SQ entry or no physical
register, or was a serialize-before. All 12 VRG benches and 48 kernel runs
were rerun (`out/pf-off/`, `kernels/out/`, `kernels/report-*.txt`). Cycle
counts are identical in every run: only the accounting moved.

Front-end bound → back-end bound takes the difference. Runs that changed
by more than 0.01:

| kernel | config | FE before | FE after | memory after | core after |
|---|---|---|---|---|---|
| store-MEM | base | 0.167 | 0.023 | 0.866 | 0.096 |
| store-MEM | fe8 | 0.055 | 0.015 | 0.904 | 0.066 |
| store-L2 | base | 0.455 | 0.208 | 0.135 | 0.532 |
| store-L2 | fe8 | 0.277 | 0.156 | 0.079 | 0.640 |
| chaseI8-MEM | base | 0.281 | 0.011 | 0.945 | 0.037 |
| chaseI8-MEM | fe8 | 0.162 | 0.008 | 0.949 | 0.037 |
| chaseI32-MEM | base | 0.267 | 0.023 | 0.866 | 0.090 |
| chaseI8-L2 | base | 0.360 | 0.104 | 0.545 | 0.291 |
| chaseI8-L2 | fe8 | 0.216 | 0.071 | 0.567 | 0.302 |
| chaseI32-L2 | base | 0.401 | 0.215 | 0.091 | 0.504 |
| chaseI32-L2 | fe8 | 0.190 | 0.171 | 0.083 | 0.555 |
| chaseI8-L1 | base | 0.614 | 0.399 | 0.000 | 0.371 |
| chaseI8-L1 | fe8 | 0.385 | 0.271 | 0.000 | 0.500 |
| M_Dyn (VRG) | base | 0.544 | 0.428 | 0.079 | 0.203 |

The other 46 runs are unchanged to three decimals or nearly (largest
other move 0.007).

**What is left.** `store-L2` (`fe8`) still has front-end bound 0.156.
Rename is idle in 33,864 of 267,541 cycles (12.7%) while fetch waits on
the L1I in 620: after rename drains its skid buffer it has nothing until
decode and fetch restart. This restart lag is counted as fetch latency. It
is a different mechanism from the leak and was left alone.

**Agentic sweeps.** They predate the fix. An upper bound on what the leak
put in front-end bound (8 slots per `SQFullEvents`, `LQFullEvents` or
`fullRegistersEvents`; `agentic-bound/leak_bound.py`), median of 27
tasks: 0.076 of slots on `20261104-1115-base` (front-end bound 0.416;
registers in 6.1% of cycles, SQ 0.9%), 0.023 on
`20261106-2004-pl1d-pl1i` (0.513). The exact change needs a rerun.

## Conclusions

- Before the fix, Level 1 was right when rename was blocked on the ROB or
  IQ, and wrong (front end too high, back end too low) when it stalled on
  registers, the SQ or the LQ. After it, what remains in front-end bound
  on those kernels is the restart lag and the 6-wide front end.
- The memory/core split follows serial work well (within 0.08 of the
  ground truth on `chaseD`) and fails on overlapped work, as the paper's
  definition implies. Memory bound is a lower bound.
- `extMemBound` and `storeBound` are exercised and plausible;
  `machineClears` and front-end bound from L1I misses are not tested yet.
- Recorded on [[top-down-accounting#Known problems]].

## Decisions

- 2026-11-13: fix the front-end bubble leak (agreed with the user).
  Implemented the same day, see [[#The fix]].
- 2026-11-13: the user keeps the back-end split as it is for now and will
  mostly ignore it; a redesign may come later.
- 2026-11-13: back-end split, earlier the same day. Agreed
  so far: follow the paper in not forcing Level 2 to add up to back-end
  bound. Under discussion: replacing the "few issued" test by attributing
  each back-end stall of rename to the oldest entry of the resource that
  stalled it.

## Open

- Whether the restart lag after a rename stall should count as front-end
  bound.
- Rerun an agentic sweep to measure the fix there.
- A kernel with a divide chain plus an independent DRAM chase, sized so
  the IQ fills first and so the ROB fills first.
- Kernels for machine clears (store-to-load aliasing) and for L1I misses
  (large code, no warm-up).
- Why alu64 slows down with a faster front end.
