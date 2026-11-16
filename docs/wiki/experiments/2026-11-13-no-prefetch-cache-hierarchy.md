---
type: experiment
status: open
updated: 2026-11-16
sources:
  - runs/no-prefetch/launch.sh
  - runs/no-prefetch/smoke.sh
  - runs/no-prefetch/compare.sh
  - runs/sweep/20261113-1805-fe8-l1i1-nopf/
  - runs/sweep/20261113-1805-spec4-fe8-l1i1-nopf/
  - runs/sweep/20261113-1805-compare-nopf/
  - configs/garfield/arm/cache_hierarchy.py
  - analysis_scripts/tasktrace/window_view.py
tags: [sweep, cache, prefetch, amat, l1i, l1d, l2, spec, agentic]
---

# Cache hierarchy without prefetchers

How the cache hierarchy behaves when nothing is prefetched: where
instruction fetches and data accesses are served from (L1, L2, memory)
and what an access costs on average (AMAT), for SPEC (400M windows) and
agentic (1B windows), at front-end width 8 with a 1-cycle L1I.
Status: both sweeps finished 2026-11-14 (stamp `20261113-1805`, 26/26 and
27/27 runs, no failures). First reading only; nothing below is analysed
past the suite means.

## Question

What do the caches themselves do under SPEC and under the agents, without
prefetchers covering for them: hit rates per level, where the lines come
from, and the access time, split by instruction and data?

## Setup

- **Configuration:** `--front-end-width 8 --l1i-cycles 1
  --disable-prefetch`. `--disable-prefetch` is new
  ([[neoverse-v2]], Switches): it detaches FDP's L1I prefetcher, the L1I
  next-line tagged prefetcher, the L1D Stride+SMS stack and the L2 BOP.
  The decoupled front end (BAC/FTQ) stays on, so the only change against
  the reference is prefetching (the user's choice; `--disable-fdp` would
  also have switched the front end).
- **Sweeps** (`runs/no-prefetch/launch.sh`, 12 runs at a time each):
  `runs/sweep/20261113-1805-fe8-l1i1-nopf` (27 agentic, 1B) and
  `runs/sweep/20261113-1805-spec4-fe8-l1i1-nopf` (26 SPEC, 400M); 20M
  warm-up, 200K blocks, `SETTLE=1`. Commit `9ff7bdd38c-dirty`: the flag
  was not committed when they ran.
- **Reference (prefetchers on):** `runs/sweep/20261110-0949-fe8-l1i1`
  (agentic) and `runs/sweep/20261112-1720-spec4-fe8-l1i1` (SPEC), not
  rerun. They were re-summarised into `runs/no-prefetch/ref/` for the new
  metrics; their own summaries are untouched.
- **Page:** `runs/sweep/20261113-1805-compare-nopf/compare.html`
  (`runs/no-prefetch/compare.sh`), A = prefetchers on, B = off, with the
  new *Cache hierarchy* section ([[sweeps#Cache hierarchy]] has the
  definitions).

> [!conflict] Top-down shares of A and B are not comparable
> The reference sweeps predate the rename fix of 2026-11-13
> ([[top-down-accounting]]): their front-end bound still holds the
> register and SQ stalls. Differences in top-down shares between A and B
> mix that fix with the prefetchers. Cycles, IPC and the cache counters
> are not affected by the fix (the microbenchmark reruns had identical
> cycles, [[2026-11-13-top-down-microbenchmarks]]).

## Smoke test (2026-11-13)

`runs/no-prefetch/smoke.sh`: omnetpp, lbm, gin-2121 and axios-5892, with
and without prefetchers, 2M warm-up + 5M detailed. A functional check,
not a result.

- All 8 runs exit 0; no panic or fatal.
- The no-prefetch `config.ini` has no prefetcher section (the reference
  has 16), the L1I's `prefetcher` is `Null`, `decoupledFrontEnd=true`,
  and the stats have no `pfIssued`.
- L1I and L1D misses rise in every run but lbm's L1I, which has none.

## Results

All numbers: `runs/sweep/20261113-1805-compare-nopf/compare_geomean.csv`
and `compare.view.json`.

**IPC** (geometric mean of per-checkpoint ratios, off / on):

| suite | IPC, prefetchers on | off / on | min | median | max |
|---|---|---|---|---|---|
| SPEC (26) | 1.568 | 0.779 (−22.1%) | 0.286 (736.ocio_r) | 0.900 | 1.144 (734.vpr_r) |
| agentic (27) | 1.055 | 0.820 (−18.1%) | 0.707 (framework-52684) | 0.800 | 0.954 (preact-3763) |

- SPEC is a long tail again: ocio 0.286, roms 0.431, cppcheck 0.486, lbm
  0.490, cactus 0.563, fotonik3d 0.594; half the benchmarks lose under
  10%. Agentic is uniform, 0.71 to 0.95.
- **Three SPEC benchmarks are faster without prefetchers:** vpr +14.4%,
  abc +12.4%, omnetpp +10.8%. Not explained.

**Where accesses are served from, and AMAT** (plain mean over
checkpoints; on → off; definitions of 2026-11-16, [[metric-definitions]];
page rebuilt that day). Accesses are demand accesses of the L1: fetch requests for
a line on the instruction side, loads and stores on the data side.
*In flight*: misses that join a miss or prefetch that cache already has
outstanding for their line and wait for it ([[sweeps#Cache hierarchy]]).

| | SPEC instr. | agentic instr. | SPEC data | agentic data |
|---|---|---|---|---|
| served by L1 | 99.82% → 98.76% | 98.83% → 96.54% | 94.38% → 87.98% | 96.19% → 92.80% |
| L1 in flight | 0.12% → 0.03% | 0.79% → 0.35% | 2.83% → 6.65% | 2.10% → 4.47% |
| served by L2 | 0.05% → 1.18% | 0.29% → 2.54% | 2.37% → 3.54% | 1.07% → 1.29% |
| L2 in flight | 0.00% → 0.00% | 0.00% → 0.00% | 0.10% → 0.00% | 0.06% → 0.00% |
| served by memory | 0.01% → 0.03% | 0.09% → 0.57% | 0.28% → 1.71% | 0.34% → 1.11% |
| ownership only (no data) | | | 0.04% → 0.13% | 0.24% → 0.33% |
| L2 hit rate, that side's requests | 58.6% → 65.4% | 76.2% → 79.1% | 84.8% → 75.6% | 72.9% → 54.2% |
| AMAT (cycles) | 1.06 → 1.27 | 1.77 → 3.11 | 8.77 → 18.95 | 8.43 → 14.42 |
| of it L1 lookup | 1.00 | 1.00 | 4.00 | 4.00 |
| of it L1 in flight | 0.03 → 0.02 | 0.43 → 0.48 | 3.01 → 9.12 | 2.78 → 6.96 |
| of it L2 (way to the L2 and its lookup) | 0.01 → 0.18 | 0.06 → 0.45 | 0.61 → 0.99 | 0.26 → 0.39 |
| of it L2 in flight | 0.00 → 0.00 | 0.00 → 0.00 | 0.16 → 0.00 | 0.13 → 0.00 |
| of it memory (the L2's own wait) | 0.02 → 0.07 | 0.28 → 1.18 | 0.96 → 4.79 | 1.14 → 2.94 |
| of it ownership | | | 0.02 → 0.05 | 0.12 → 0.13 |
| L1D blocked, % of cycles | | | 8.8% → 11.1% | 5.9% → 12.8% |
| of it MSHR target list full | | | 5.9% → 10.1% | 4.1% → 11.1% |

First observations, all provisional:

- **On the data side, waiting on a line already being fetched is the
  largest part of the time past the L1 lookup**, in both suites, with
  and without prefetchers: SPEC 3.01 of 4.77 cycles → 9.12 of 14.95,
  agentic 2.78 of 4.43 → 6.96 of 10.42. More data accesses join an
  outstanding miss than make a new one (agentic without prefetchers:
  4.47% vs 2.73%). Which level those lines come from is not split out.
- **Of the new misses' time, memory is most** wherever the L2 misses at
  all: agentic data 1.14 vs 0.26 cycles (prefetchers on), agentic
  instruction 1.18 vs 0.45 (off).
- **The L1D refuses requests for a large share of the time, more without
  prefetchers** (agentic 5.9% → 12.8% of cycles, SPEC 8.8% → 11.1%),
  mostly on full MSHR target lists (8 accesses per MSHR). The waits of
  the refused accesses are in no cache latency, so data AMAT is
  understated most where the loss is largest: 736.ocio_r is blocked 40%
  → 82% of cycles (IPC ×0.286), cactus 38% → 41% (×0.563), roms 32% →
  24% (×0.431); on the agentic side micropython, framework and axios
  reach 21-25% without prefetchers. Part of the no-prefetch loss is
  therefore this limit of the cache model; how much is open.
- **L2 in flight is small on average but not everywhere.** Without
  prefetchers it is zero (the L1 already merges requests per line);
  with them, data requests joining an outstanding L2 miss or BOP
  prefetch cost 0.16 (SPEC) and 0.13 (agentic) cycles per access, up to
  1.96 of 15.9 in lbm and 1.35 of 18.5 in fotonik3d; on the agentic side
  0.4-0.5 in rubocop, core and carbon.
- **With prefetchers on, agentic instruction fetches wait mostly on
  lines already in flight** (0.43 of the 0.77 cycles past the lookup;
  0.79% of fetches, against 0.38% new misses): with the prefetchers,
  most of these joins are probably onto prefetches, not checked per
  prefetcher. Without prefetchers new misses take over (2.54% L2, 0.57%
  memory).
- **Instruction side separates the suites; data side does not.** SPEC's
  instruction AMAT stays near the 1-cycle hit (1.06, 1.27 without
  prefetchers); agentic pays 1.77 with prefetchers and 3.11 without.
  Data AMAT with prefetchers is about the same (8.77 vs 8.43). In line
  with [[agentic-front-end-bound]] and [[2026-11-12-spec-400m-sweeps]].
- **Without prefetchers SPEC's data AMAT grows more than agentic's**
  (×2.16 vs ×1.71), and its memory share of accesses grows 6.1× (agentic
  3.3×): the data prefetchers do more for SPEC. A few benchmarks carry
  the SPEC mean (data AMAT up to 112 cycles in one).
- Agentic instruction lines missing the L1I are mostly in the L2 (L2 hit
  rate 76-79%); the time is still mostly memory.
- Before 2026-11-16 the page had no in-flight part; the first reading
  (2026-11-14, [[log]]) shared all L1 misses between the L2 and memory
  and said memory was most of the time past the lookup. With the joins
  separated that holds for new misses only.
- Later on 2026-11-16 the L2, memory and ownership parts were redefined
  (ownership requests their own part; memory is the L2's own measured
  wait, L2 the remainder), which moved the numbers of those rows.

## Caveats

- **In-flight waits are not attributed to a level.** An access that
  joins an outstanding miss counts as an L1 miss but makes no L2 request
  (gin-2121: 14.5M of 25.1M L1D misses with prefetchers, 28.2M of 45.0M
  without; `demandMshrHits`/`demandMisses`). They are their own part;
  the line they wait for is counted once, by the miss that started the
  fill (or not at all when a prefetch started it).
- **AMAT does not hold the wait before a blocked cache accepts an
  access**, wrong-path accesses are counted, and loads forwarded from a
  store are absent; how exact each part is, with the checks:
  [[metric-definitions]].
- With prefetchers on, a demand access that waits on an in-flight
  prefetch is a miss with a short latency, and prefetched lines count as
  L1 hits: A's hit rates include the prefetchers' effect by design.
- SPEC is at 400M and agentic at 1B.
- The L1D blocks more without prefetchers: in gin-2121,
  `blockedCycles::no_targets` goes from 60M to 224M cycles (8 targets per
  MSHR). Whether a share of the loss is this limit of the cache model
  rather than the missing prefetch is open.

## Conclusions

None yet.

## Decisions

- 2026-11-13: prefetchers off with the decoupled front end kept; one new
  sweep per suite against the existing `fe8-l1i1` sweeps; AMAT from the
  measured latencies, shown as a stack per cache level; the served-from
  bars may be mostly one colour, with a zoom (all the user's choices).

## Open

- Why vpr, abc and omnetpp speed up without prefetchers.
- Per-benchmark and per-task reading; slice categories for agentic.
- How much of the loss is the L1D blocking on full MSHR target lists
  (now a row per cache on the page; ocio 82% of cycles). A sweep with
  more targets per MSHR, or a per-access wait measured in the LSQ, would
  size it.
- Per-prefetcher arms (L1I only, L1D only, L2 only), if the attribution
  matters.
