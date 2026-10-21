---
type: experiment
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - runs/sweep/20261014-154546-nofdp/compare-20261014-110051/
tags: [sweep, fdp, front-end]
---

# FDP off, checkpoint by checkpoint

## Question

What is the decoupled front end with fetch-directed prefetching worth, and
how much of the front-end miss picture does it shape?

## Setup

The [[2026-10-14-baseline-sweep]] windows with `EXTRA=--disable-fdp`
(decoupled front end and the L1I FDP prefetcher off; the tagged L1I
prefetcher stays). `runs/sweep/20261014-154546-nofdp`, 3 h at 10 in
parallel, 53/53. Paired by checkpoint with `sweep_compare.py`
(`compare-20261014-110051/`).

## Results

FDP off against FDP on, median [quartiles]:

| metric | SPEC | agentic |
|---|---|---|
| IPC | −0.2% [−4.0, 0.0] | **−2.8%** [−4.3, −1.6] |
| fetch rate | −0.2% | −3.7% |
| L1I MPKI | +104% (0.010 → 0.022) | +132% (1.74 → 4.03) |
| I-cache stall cycles | +0.9% | +54% |
| iTLB MPKI | −85% (0.16 → 0.02) | **−92% (37 → 2.9)** |
| L2 MPKI | −0.7% | −23% (7.7 → 5.7) |
| BTB-miss mispredicts | +1.7% | +6.6% |

- Agentic range: −2.6% (gson, lombok) to +11.7% (micropython) for FDP.
- SPEC gains are the large-code runs: cpython +23.6%, gem5 +20.7%, llvm
  +7.8%; nothing on most.
- Without FDP, `btb.misses` is meaningful (fmt-3901: 42.4M in 400M
  instructions; [[btb-miss-stat-zero-decoupled]]).

## Conclusions

- [[fdp-value]]: worth ~2.8% on agentic, recovering about half the L1I
  misses.
- [[fdp-inflates-itlb-misses]]: ~92% of agentic iTLB misses with FDP are
  prefetch lookups; a quarter of the L2 misses are prefetch traffic.
- Without FDP agentic iTLB MPKI is still ~140× SPEC's.
