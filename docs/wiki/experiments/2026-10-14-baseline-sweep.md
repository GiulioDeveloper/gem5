---
type: experiment
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - runs/sweep/20261014-110051/summary/
tags: [sweep, agentic, spec, baseline]
---

# Baseline sweep: SPEC CPU 2026 against agentic

## Question

How do the agentic windows differ from SPEC on the same core, metric by
metric, across all local checkpoints?

## Setup

`sweep.sh` over all 53 local checkpoints: 26 SPEC SimPoints (200M
detailed) and 27 agentic tasks (400M), 1 atomic settle instruction, 20M
warm-up, 200K-instruction blocks, FDP and all prefetchers on, L2 TLB
connected. 53/53 complete, 3 h 15 min at 10–12 in parallel.
`runs/sweep/20261014-110051/summary/`. One window per checkpoint, not a
whole-checkpoint average. This sweep is the baseline **A** of every later
comparison.

## Results

| metric (window value, median [IQR]) | SPEC | agentic |
|---|---|---|
| IPC | 1.52 [1.04–2.07] | 0.99 [0.85–1.14] |
| user-mode share | 100% | 81% [72–85%] |
| L1I / iTLB MPKI | 0.01 / 0.15 | 1.74 / 37 |
| BTB-miss / conditional mispredicts PKI | 0.005 / 0.81 | 1.13 / 4.2 |
| L1D miss latency (cycles) | 54 | 112 |
| context switches per M instructions | 0 | 1.6 |
| FDP accuracy / L1I coverage | 0.21 / 0.96 | 0.30 / 0.79 |
| completed page walks PKI | – | 0.62 (fmt-3901: 2.64 walk requests) |
| IPC CV over blocks | 0.12 | 0.36 |
| fetch-rate CV over blocks | 0.09 | 0.29 |

(FDP coverage = FDP-useful / (FDP-useful + L1I demand misses).)

- Front-end misses (L1I, iTLB, BTB) are two orders of magnitude higher on
  agentic, with little overlap; gcc is the only SPEC run near the agentic
  iTLB range.
- SPEC spreads across checkpoints (IPC 0.47 cactus to 3.17 marian); agentic
  is tight across checkpoints but less stable inside a window.
- Even with FDP, agentic I-cache stall cycles are 22% of cycles.
- nushell-13831 peaked at 21 GB of memory.

> [!superseded] Two corrections
> The first report of this table (same day) gave SPEC IPC 1.45
> [1.02–1.99], conditional mispredicts 0.73 and L1D miss latency 52; the
> values above are recomputed from `summary/sweep.csv`. The switch columns
> were regenerated on 2026-10-15/16 under the current classification
> ([[context-switch-classification]]); no other metric changed.

## Conclusions

- [[agentic-front-end-bound]]
- [[agentic-ipc-variability]]
- The agentic iTLB figure is mostly FDP's own translations
  ([[fdp-inflates-itlb-misses]], from [[2026-10-14-fdp-off-sweep]]).
- CVs of near-zero means are meaningless ([[aggregating-metrics]]).
