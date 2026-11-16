---
type: experiment
status: open
updated: 2026-11-13
sources:
  - runs/metric-why/deep_stats.py
  - runs/metric-why/deep_stats.csv
  - runs/metric-why/pl1d_corr.py
  - runs/metric-why/pl1d_corr.csv
  - runs/sweep/20261104-1115-base/
  - runs/sweep/20261104-1115-nofdp/
  - runs/sweep/20261106-2004-pl1d/
  - runs/sweep/20261105-1143-spec-fe6/
tags: [analysis, l1d, l1i, fdp, memory, mlp]
---

# Miss counts vs miss cost: FDP off and perfect L1D

Miss counts (MPKI) do not predict these two results; the cycles that the
misses expose do. **FDP off** more than doubles the L1I misses but adds
only 2.3 extra misses per 1,000 instructions. The misses it adds are the
short ones, and about 78% of the extra fetch-stall cycles overlap with
cycles the back end could not use anyway: net −2.8% IPC (median).
**Perfect L1D** helps agentic far more than its L1D MPKI suggests. The
median agentic L1D miss takes twice as long as SPEC's (88 vs 44 cycles),
because three times as many go on to miss in the L2 (26% vs 8%), and
little of that latency overlaps. The "similar to SPEC" L1D MPKI is a
comparison of medians. SPEC is bimodal: half its benchmarks barely miss,
and the rest miss more than agentic, but with high memory-level
parallelism. All numbers are from existing 1B agentic and 200M SPEC
sweeps. No SPEC perfect-L1D run exists, so the SPEC side is inferred, not
measured.

## Question

Two things from the 1B sweeps looked inconsistent:
1. `--disable-fdp` raises agentic L1I MPKI 1.65 → 3.92 (+138%) yet costs
   only 2.8% IPC ([[2026-11-03-perfect-l1i]], [[fdp-value]]).
2. `--perfect-l1d` gives agentic +43% IPC ([[2026-11-06-perfect-l1d]]),
   although its L1D MPKI (15.4) is close to SPEC's (12.2).

## Setup

No new simulation. Raw counters summed over all stats blocks of each run
(`runs/metric-why/deep_stats.py`, output `deep_stats.csv`), from
`runs/sweep/20261104-1115-{base,nofdp}`, `20261106-2004-pl1d` (27 agentic
tasks, 1B instructions each) and `20261105-1143-spec-fe6` (26 SPEC
SimPoints, 200M, same machine: width 6, 2-cycle L1I, FDP on). Per-task
correlations: `runs/metric-why/pl1d_corr.py` (`pl1d_corr.csv`). Medians
over tasks unless stated. Definitions:

- **primary miss**: an L1D/L1I demand miss that allocates an MSHR
  (`demandMshrMisses`); the others merge into an outstanding MSHR.
- **primary latency**: `demandMshrMissLatency / demandMshrMisses`, in
  cycles (333 ticks).
- **summed miss latency**: `demandMshrMissLatency` per 1,000 instructions,
  the cycles of miss latency to be hidden or exposed.
- **in flight**: summed latency / `numCycles`, the mean number of primary
  demand misses outstanding (Little's law). An average over all cycles,
  not MLP during miss cycles.
- **L2-miss load stall**: `topDown.loadStallL2Miss / topDown.cycles`
  ([[top-down-accounting]]).

## Results

### FDP off (agentic, paired by task)

Per 1,000 instructions, median of base, of nofdp, and of the per-task
difference:

| | FDP on | FDP off | paired Δ |
|---|---|---|---|
| cycles | 987 | 1030 | +28 |
| L1I demand misses | 1.65 | 3.92 | +1.97 |
| L1I primary misses | 0.72 | 2.39 | +1.53 |
| L1I primary latency (cycles) | 112 | 56 | −47 |
| L1I summed miss latency | 82 | 160 | +68 |
| fetch I-cache stall cycles | 217 | 340 | +131 |
| L2 instruction misses | 0.21 | 0.29 | +0.07 |

Top-down change, in cycle-equivalents (slots / 6) per 1,000 instructions,
paired median: front-end bound **+48** (all of it fetch latency), back-end
bound **−12** (memory −7, core −4), bad speculation −3, retiring 0.

- **Few extra misses in absolute terms:** +2 per 1,000 instructions, at
  about **13 cycles of runtime each** (median of Δcycles / Δmisses).
- **The extra misses are cheap ones.** With FDP on, the misses left have a
  112-cycle primary latency (FDP misses the hard ones, many from DRAM).
  Without FDP the average falls to 56 cycles: most added misses hit in the
  L2 (L2 instruction misses rise only 0.07 per 1,000).
- **Most extra stall cycles are hidden.** Fetch waits 131 more cycles per
  1,000 instructions, and runtime grows by 28: 78% of the extra wait
  overlaps with cycles the back end could not use (back-end bound is
  37% of slots), or is absorbed by the fetch queue.
- **Turning FDP off also removes FDP's costs.** Back-end bound falls by 12
  cycle-equivalents, memory-bound by 7. Consistent with the L2 space FDP
  occupies (about 20% of L2 lines,
  [[2026-11-03-perfect-l1i#How much of the L2 holds instructions (2026-11-09)]])
  and its prefetch traffic. Interpretation: this offset is not separated
  from the overlap effect.
- `--disable-fdp` turns off the whole decoupled front end, not just the
  prefetcher, so this is not the prefetcher alone.

### L1D: agentic vs SPEC (baseline machine)

| per 1,000 instructions | agentic median [q1, q3] | SPEC median [q1, q3] |
|---|---|---|
| L1D demand misses | 15.4 [10.0, 18.2] | 12.2 [4.3, 39.2] |
| L1D primary misses | 6.7 [5.0, 8.9] | 4.8 [2.1, 20.8] |
| L1D primary latency (cycles) | **88** [77, 100] | **44** [28, 85] |
| L2 miss rate of L1D demand requests | **26%** | **8.5%** |
| L2 data demand misses | 1.47 [0.80, 2.21] | 0.40 [0.05, 1.71] |
| summed L1D miss latency (cycles) | 680 [335, 892] | 296 [81, 1090] |
| primary misses in flight (mean) | 0.68 [0.39, 0.74] | 0.46 [0.15, 1.10] |
| L2-miss load stall (% cycles) | 19.0 [13.4, 23.7] | 9.1 [1.2, 26.5] |
| L1D prefetches reaching the L2 | 8.4 | 15.2 |
| dTLB misses | 7.4 | 1.5 |

- **SPEC is bimodal; agentic is not.** Eleven SPEC benchmarks spend fewer
  than 200 cycles of miss latency per 1,000 instructions (gmsh, cpython,
  ntest, …, femflow). Seven spend more than agentic's third quartile
  (892): abc, zstd, vpr, omnetpp, lbm, cactus, fotonik3d. Every agentic task
  sits between 100 and 1,052. The suite mean is higher for SPEC (817 vs
  634); only the median is lower.
- **SPEC's heavy missers overlap their misses; agentic does not.**
  omnetpp: 121 misses per 1,000 instructions but 28-cycle primary latency
  (L2 hits), 2.1 in flight. lbm and fotonik3d: 3.1 and 3.4 in flight
  (streaming, prefetchable). Agentic: at most 1.0 in flight (third quartile
  0.74), with most of the latency from DRAM.
- **Agentic's L1D prefetchers do less:** they send about half as many
  prefetches to the L2 as SPEC's, while the agentic misses are longer.

### What predicts the perfect-L1D gain (27 agentic tasks)

Pearson r of base metrics with the per-task pl1d IPC gain and with cycles
saved per 1,000 instructions (`pl1d_corr.py`):

| base metric | r (gain) | r (cycles saved) |
|---|---|---|
| L2-miss load stall | **+0.93** | **+0.96** |
| summed L1D miss latency | +0.90 | +0.93 |
| L1D primary misses | +0.89 | +0.86 |
| L2 data misses | +0.84 | +0.88 |
| L1D demand misses (MPKI) | +0.84 | +0.78 |
| L1D primary latency | +0.31 | +0.35 |
| barriers (`commit.membars`) | −0.65 | −0.54 |
| atomics served (`perfectDCacheAtomics`) | −0.49 | −0.34 |

- **Exposed share:** cycles saved / summed L1D miss latency is 0.51
  (0.34–0.65): about half of agentic's L1D miss latency is on the
  critical path.
- **Barriers and atomics are not the cause.** Agentic runs about 2
  barriers per 1,000 instructions against SPEC's 0.005 (`commit.membars`,
  matching rename's serializing count), and 0.5–4 atomics. But the tasks
  with the most (preact 8.6, lombok 10.2, gson-2134 11.1 barriers) gain
  least (+8.6%, +11.9%, +23.9%). Interpretation: those windows are
  dominated by a barrier-heavy loop (polling or JVM code) that misses
  little.
- **L2 relief is a small part:** under pl1d the L2 instruction misses fall
  0.21 → 0.13 and walker L2 misses 0.20 → 0.10 per 1,000 instructions. At
  about 290 cycles each that is roughly 50 of the 282 cycles saved (an
  upper bound: it assumes every one was exposed). DRAM latency is unchanged
  (258 → 250 cycles), so bandwidth is not the limit.

### Top-down memory-bound vs the cycles a perfect L1D saves

By suite **mean** of top-down shares, SPEC is more memory-bound than
agentic: past-L2 (`td_mem_ext`) 9.8% vs 8.1%, memory-bound 13.0% vs
12.0% (`summary/sweep.csv` of `base` and `spec-fe6`). By median it is
the reverse (3.4% vs 8.7%). SPEC's mean comes from five benchmarks with
23–49% past-L2 slots (fotonik3d, cactus, lbm, vpr, roms); 13 of 26 are
under 2.5%. Agentic tasks all lie between about 5% and 13%.

Where the agentic pl1d savings come from, in cycles per 1,000
instructions (share × cycles per 1,000 instructions, base minus pl1d,
mean over 27 tasks, total 310):

| bucket | cycles saved | share of saving |
|---|---|---|
| back end: memory | 120 | 39% |
| back end: core | 114 | 37% |
| front end | 46 | 15% |
| back end: serialize | 22 | 7% |
| bad speculation | 8 | 3% |
| retiring | −1 | 0% |

- **Top-down memory-bound underestimates agentic's memory cost by
  about 3×.** Taking it at face value (speedup 1/(1 − memory-bound)) gives
  a geomean of +13.8% for agentic and +17.2% for SPEC. Agentic measured
  +43.2%.
- **Core bound holds as much of the saving as memory bound.** Cycles that
  issue 1 or 2 micro-ops count as core bound even with a DRAM miss
  outstanding ([[top-down-accounting]]). Interpretation, not verified:
  agentic code keeps issuing a trickle of independent work while waiting
  on a miss, so its miss cycles land in core bound. SPEC's streaming
  kernels may issue nothing and land in memory bound.
- **Whether SPEC's top-down shares are equally low is unknown.** No SPEC
  perfect-L1D run exists. If they are accurate, SPEC would gain about
  +17% (geomean, a few benchmarks near 2×). If they are as low as
  agentic's, it would gain more than agentic. Either way, "agentic gains
  more than SPEC" is **not established**.

> [!superseded] by [[2026-11-12-spec-400m-sweeps]] (2026-11-13)
> The SPEC 400M perfect-L1D sweep gives +46.6% geomean against agentic's
> +43.2%: SPEC does not gain less. Memory-bound holds 51% of SPEC's
> saving (agentic 39%), so the top-down underestimate is general, not
> agentic-specific. The per-miss picture above (longer, less overlapped
> agentic misses) still holds; it explains a uniform gain across agentic
> tasks, not a larger one than SPEC's.

## Conclusions

- **Read miss cost, not miss count.** The metric to compare suites is
  summed miss latency together with in-flight misses, or the top-down
  L2-miss load stall. MPKI ranks the agentic tasks' pl1d gain less well
  than either (r 0.84 against 0.93).
- **FDP's value is limited by overlap, not coverage.** It removes many
  misses, but they are short ones, mostly hidden behind back-end stalls,
  and it pays some of that back in L2 pollution. This refines
  [[fdp-value]].
- **Agentic is a latency-bound data workload:** moderate miss counts,
  frequent L2 misses, low overlap. Interpretation, not verified: pointer
  chasing in interpreters, JITs and GC heaps. It fits the low prefetch
  activity and the low in-flight count.
- **Top-down memory-bound is not a measure of memory cost:** only 39%
  (agentic) and 51% (SPEC, [[2026-11-12-spec-400m-sweeps]]) of the
  perfect-L1D saving come out of it; core bound holds about a third in
  both. Compare suites on a limit study, not on top-down shares.
- **Agentic does not gain more from a perfect L1D than SPEC** (+43% vs
  +47% geomean). The difference is the shape: every agentic task is
  moderately data-latency bound, while SPEC's gain sits in a few heavy
  benchmarks.
- Perfect L1D here means every data access is a 4-cycle hit, DRAM misses
  included. It is a bound on the whole data hierarchy, not the L1D alone.

## Decisions

- 2026-11-12: compared suites on summed counters per run (Little's law
  for in-flight misses) rather than adding new stats; no MLP-during-miss
  counter exists.

## Open

- **SPEC perfect-L1D sweep**: done, [[2026-11-12-spec-400m-sweeps]].
  The prediction (large gains on the heavy missers, little elsewhere)
  held in shape, but the heavy missers gain so much that the SPEC
  geomean exceeds agentic's. SPEC's exposed share is not computed yet.
- **True MLP:** a counter of cycles with at least one demand miss
  outstanding would give MLP during miss cycles, not the all-cycle
  average used here.
- **Split FDP-off's front-end loss from its L2 relief:** a run with FDP's
  prefetches kept but the fetch-directed lookahead off, or the reverse.
- Is the low agentic overlap a dependence chain (pointer chasing) or a
  window limit (ROB, LQ, 12 L1D MSHRs)? ROB-full and LSQ-full dispatch
  stalls are under 0.3% of cycles (median, base), but IQ-full stalls are
  19% (SPEC 8%): instructions waiting on missing loads may fill the IQ
  first. Not checked per load.
