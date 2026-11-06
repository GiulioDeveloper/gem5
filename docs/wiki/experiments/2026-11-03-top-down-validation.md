---
type: experiment
status: open
updated: 2026-11-03
sources:
  - runs/topdown/
  - "[[top-down-accounting]]"
tags: [top-down, validation, front-end]
---

# Top-down accounting: merge, fixes and first windows

**Question:** does the top-down accounting from gem5 PR #2392 (branch
`topdown-pr2392`) work on `gfdev`, and what does it say about SPEC vs
agentic windows? It is a prerequisite for the perfect L1I / L2 / TLB
sweeps ([[2026-11-02-perfect-l2]], [[2026-11-03-perfect-l1i]]).

**Answer so far:** on 400M windows of median checkpoints, agentic
(rubocop) is more front-end bound than SPEC (cppcheck), 0.41 vs 0.31, all
in fetch latency; L1I misses are about 8 points of it. After fixes the
accounting works: no timing change, Level 1 sums to
1, nothing negative, Level 2/3 sum to their parents, and gem5's formulas
match an offline recomputation from the raw counters. On five 30M windows,
**front-end bound is 47-54% for SPEC int (llvm, stockfish) and for agentic
alike**, so Level 1 does not separate them. Most of the SPEC front-end
latency comes from fetch waiting out L1I *hits*, which makes the front-end
fractions a property of the fetch model as much as of the workload. One
window per workload: provisional.

## Setup

- Code: `gfdev` (`f15bdb37f0`) + merge of `topdown-pr2392` + fixes
  ([[top-down-accounting]]); committed 2026-11-04.
- `runs/topdown/validate.sh`: 3 SPEC (`spec-window.sh`) and 2 agentic
  (`o3-window.sh`) windows, 1 settle + 5M warm-up + 30M detailed in 5M
  blocks; plus the jq-2598 2M + 5M window of
  `runs/perfect-l1i/validate/baseline` for a perturbation check.
- Outputs: `runs/topdown/merged/` (as merged, upstream formulas),
  `runs/topdown/fixed/` (fixed). Tables: `runs/topdown/td_table.py
  --formulas pr|fixed` (sums the counters over blocks, then applies the
  formulas), `runs/topdown/{pr,fixed}.csv`.

## Results

**Perturbation:** against the pre-merge baseline, both builds differ only in
the 5 host stats × 5 blocks (`runs/topdown/perturb_diff.py`).

**Non-perturbation, final code (2026-11-04):** the pre-merge `gfdev`
(`f15bdb37f0`, built in a worktree) and the merged tree (back-end split
removed) on rubocop-13560, gin-2121, 727.cppcheck_r and 723.llvm_r, 5M +
20M in 1M blocks: **0 differing simulated values**, 20 blocks each, no
reference stat missing; the merge only adds 27 top-down stats. Host time
+1.0 to +3.6%. `runs/topdown/nonperturb.sh`, outputs
`runs/topdown/nonperturb/{ref,new}/`.

**Fixed formulas** (fractions of slots; UPC = committed micro-ops per
cycle):

| window | FE | lat. | resteer | bw. | BS | BE | serialize | memory | core | RET | UPC | idle % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 723.llvm_r | 0.535 | 0.308 | 0.013 | 0.227 | 0.108 | 0.167 | 0.001 | 0.062 | 0.105 | 0.190 | 1.52 | 1.8 |
| 706.stockfish_r | 0.490 | 0.264 | 0.008 | 0.226 | 0.151 | 0.136 | 0.001 | 0.045 | 0.090 | 0.223 | 1.78 | 0.1 |
| 710.omnetpp_r | 0.334 | 0.197 | 0.008 | 0.138 | 0.176 | 0.365 | 0.000 | 0.169 | 0.197 | 0.125 | 1.00 | 0.3 |
| jq-2598 | 0.467 | 0.288 | 0.028 | 0.179 | 0.094 | 0.278 | 0.095 | 0.056 | 0.126 | 0.160 | 1.28 | 5.0 |
| gin-2121 | 0.494 | 0.333 | 0.046 | 0.161 | 0.137 | 0.231 | 0.018 | 0.075 | 0.137 | 0.138 | 1.11 | 10.9 |

Memory bound, split: omnetpp L2 0.103 / DRAM 0.053; the others are mostly
DRAM (0.029-0.044).

**Upstream formulas** on the same windows: identical Level 1 (within
0.005); memory bound about twice as high (llvm 0.133, gin 0.180, jq 0.116)
because any load in the LQ counted as a stall; DRAM reported as `l3Bound`.

**Fetch stage** (`fetch.status`, % of cycles): `icacheWaitResponse` 30.9
llvm, 28.3 stockfish, 22.2 omnetpp, 25.2 jq, 24.0 gin, while stockfish's
L1I miss rate is 0.05%.

| per 1000 cycles | llvm | stockfish | omnetpp | jq | gin |
|---|---|---|---|---|---|
| decode redirects | 0.42 | 0.06 | 0.02 | 0.72 | 1.93 |
| execute mispredicts | 7.7 | 11.9 | 12.5 | 7.2 | 9.7 |
| memory-order violations | 2.2 | 1.2 | 0.05 | 1.5 | 2.6 |

### 400M windows (added 2026-11-03)

The 30M SPEC picks (llvm, stockfish) are at the front-end-heavy end of
SPEC, so the user asked for longer windows on representative checkpoints:
727.cppcheck_r and rubocop-13560, each near its suite's median IPC and L1I
MPKI in [[2026-10-14-baseline-sweep]]. 1 settle + 50M warm-up + 400M
detailed, 1M blocks, compressed stats; each also with `--perfect-l1i`
(2-cycle reads, the default) and `--perfect-l1i --perfect-l1i-cycles 1`.
`runs/topdown/long.sh`, `long-lat1.sh`; outputs `runs/topdown/long/`,
table `runs/topdown/long.csv`.

| run | FE | lat. | resteer | bw. | BS | BE | memory | DRAM | core | RET | UPC | idle % | L1I MPKI | icWait % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cppcheck | 0.313 | 0.124 | 0.000 | 0.189 | 0.002 | 0.545 | 0.397 | 0.327 | 0.146 | 0.140 | 1.12 | 0.1 | 0.01 | 12.8 |
| cppcheck, perfect L1I | 0.312 | 0.123 | 0.000 | 0.188 | 0.002 | 0.546 | 0.398 | 0.328 | 0.147 | 0.139 | 1.12 | 0.0 | 0 | 12.7 |
| cppcheck, perfect L1I 1 cycle | 0.196 | 0.041 | 0.000 | 0.155 | 0.004 | 0.652 | 0.535 | 0.444 | 0.115 | 0.148 | 1.18 | 0.0 | 0 | 0.0 |
| rubocop | 0.407 | 0.277 | 0.037 | 0.130 | 0.053 | 0.411 | 0.164 | 0.106 | 0.194 | 0.129 | 1.03 | 9.1 | 1.68 | 16.3 |
| rubocop, perfect L1I | 0.327 | 0.182 | 0.008 | 0.145 | 0.063 | 0.468 | 0.179 | 0.115 | 0.232 | 0.143 | 1.14 | 0.6 | 0 | 14.5 |
| rubocop, perfect L1I 1 cycle | 0.247 | 0.099 | 0.005 | 0.148 | 0.077 | 0.529 | 0.213 | 0.136 | 0.254 | 0.147 | 1.18 | 0.6 | 0 | 0.6 |

Serialize bound: rubocop 0.053-0.061, cppcheck 0.001.

## Conclusions

- **On the 400M representative windows agentic is more front-end bound
  than SPEC** (0.41 vs 0.31), entirely in fetch latency (0.28 vs 0.12);
  SPEC's front-end share is mostly bandwidth. This agrees with the user's
  hardware measurements in ordering (OpenCode ~25% vs SPEC26 ~19% FE),
  not in level.
- **L1I misses are about 8 points of rubocop's front-end bound**
  (perfect L1I: 0.41 → 0.33; resteers 0.037 → 0.008; idle cycles 9.1% →
  0.6%, so the idle cycles were nearly all I-cache misses) and nothing on
  cppcheck. The freed slots mostly move to back-end bound, not retiring
  (UPC +10%).
- **L1I hit latency costs both about the same** (1-cycle reads: −0.12
  cppcheck, −0.08 rubocop): a constant of the fetch model, which waits for
  each line, not a source of the agentic difference.
- cppcheck is DRAM bound (0.33 of slots); rubocop splits memory and core.
- The 30M llvm/stockfish windows overstated SPEC front-end bound by
  benchmark choice; one or two SPEC benchmarks do not represent the suite.

- The merged code works and is safe to use in sweeps (no timing change).
- (30M windows) What separates agentic from SPEC int here is not the size of front-end
  bound but its make-up: more resteers (0.028-0.046 vs 0.008-0.013), more
  decode redirects (BTB misses), idle cycles (5-11% vs ≤ 2%), and on jq a
  large serialize-bound share (0.095; rename in `SerializeStall` 9.5% of
  cycles). Interpretation, one window each.
- (30M windows) Front-end bound has a large structural part in this config: a 6-wide
  front end into 8-wide rename (bandwidth) and fetch serialised on L1I hit
  latency (latency). This weakens reading [[agentic-front-end-bound]] off
  Level 1 alone; the comparison has to go to Level 2/3 or to the perfect
  L1I/L2 sweeps.

## Decisions

- Keep the upstream convention that only the fetch-to-rename refill (5
  cycles) after a squash is bad speculation; report resteers separately
  rather than moving them.
- Count slots at rename and cap front-end bubbles by free ROB/IQ entries.
- Merge left uncommitted for review with the user, then committed on
  2026-11-04 (with the other session's viewer work) so test runs carry the
  counters, with the caveat that the top-down results are still under
  review; the counters were first checked not to perturb other results.

## Open

- Is fetch waiting on L1I hits a model artifact (a real V2 pipelines fetch)?
  It inflates every front-end number, SPEC included. Measured 2026-11-06:
  1.00 wait cycle per line on hits, 21-30% of cycles; likely an artifact
  ([[2026-11-05-front-end-width#Why fetch delivers nothing in most cycles (2026-11-06)]]).
- What makes jq serialise (barriers, system-register writes, ISBs)?
- Bad speculation splits by event count; squashes from commit (traps,
  interrupts) are frequent on agentic windows and have no category.
- Level-of-agreement with hardware: retiring is far lower here (8-wide
  slots), bad speculation too (0.002 cppcheck, 0.05 rubocop vs ~0.10-0.16
  on hardware).
- Run it over the sweep: the relaunched perfect L1I/L2 sweeps will carry
  these counters.
