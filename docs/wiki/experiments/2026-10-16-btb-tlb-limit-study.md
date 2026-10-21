---
type: experiment
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
  - "[[legacy-log/garfield/infinite-btb]]"
  - "[[legacy-log/garfield/infinite-tlb]]"
  - runs/sweep/20261019-compare-5way/
  - runs/sweep/20261020-skip100M/
tags: [sweep, btb, tlb, limit-study, front-end]
---

# Limit study: infinite BTB, infinite L2 TLB, both

## Question

How much performance do BTB misses and page walks cost the agentic
workloads, and do the two add up? Ceiling for capacity, conflict and
aliasing only (compulsory misses remain).

## Setup

- Models: [[infinite-btb-model]] (`--infinite-btb`), [[infinite-l2-tlb]]
  (`--infinite-tlb`).
- Five sweeps of the 53 baseline windows (SPEC 200M, agentic 400M, 20M
  warm-up): FDP (the [[2026-10-14-baseline-sweep]]), no-FDP
  ([[2026-10-14-fdp-off-sweep]]), inf-BTB, inf-TLB, inf-BTB+TLB
  (`runs/sweep/20261016-172546-{infbtb,inftlb,infbtb-inftlb}`), 53/53 each,
  the last three with `smart_sweep.sh` after OOM kills
  ([[sweep-memory-exhaustion]]).
- Five-way comparison `runs/sweep/20261019-compare-5way/`; re-summarised
  skipping the first 100M of each window in
  `runs/sweep/20261020-skip100M/` ([[warmup-and-skip]]).
- Single-window checks first: gin-2121 (10M + 40M), fmt-3901 (the sweep
  window), plus model validation ([[infinite-btb-model#Validation (2026-10-16)]],
  [[infinite-l2-tlb]]).

## Results

**Single windows.** gin-2121: InfiniteBTB IPC 1.008 → 1.044 (+3.6%),
BTB-miss mispredicts 1.54 → 0.30 PKI (−80%), undetected unconditional
branches −67%. fmt-3901 (400M): +3.0% (1.049 → 1.080), BTB-miss mispredicts
−83.5%, all mispredicts −13.7%, L1I MPKI −33%, iTLB MPKI −32%, L2 MPKI
−17%, fetch rate +1.9%. Baseline rerun bit-identical.

**Sweeps, median change against FDP** (agentic n=27 / SPEC n=26):

| | no-FDP | inf-BTB | inf-TLB | inf-BTB+TLB |
|---|---|---|---|---|
| **IPC, agentic** | −2.8% | **+3.1%** | **+3.1%** | **+6.4%** |
| IPC, SPEC | −0.2% | +0.1% | +0.0% | +0.1% |
| fetch rate, agentic | −3.7% | +1.7% | +3.4% | +5.8% |
| BTB-miss mispredicts, agentic | +6.6% | −74.9% | +0.2% | −75.0% |
| all branch mispredicts, agentic | +1.5% | −13.0% | −0.2% | −13.2% |
| L1I MPKI, agentic | +132% | −33.5% | +0.3% | −36.6% |
| iTLB MPKI, agentic | −92.4% | −25.4% | −26.7% | −40.3% |
| walk requests, agentic | −2.9% | −4.7% | −44.0% | −47.7% |
| L2 MPKI, agentic | −22.9% | −16.3% | −1.5% | −17.6% |

- With both limits **every agentic task gains** (+0.3% to +13.2%; IQR
  +4.8% to +9.9%); SPEC moves 0.1%.
- BTB part: largest nushell +5.5%, prometheus +5.1%, jq +4.8%; carbon −0.9%.
- TLB part: completed walks 0.62 → 0.15 PKI (−76%), the rest are first
  touches; iTLB MPKI −27% because more FDP prefetch translations hit;
  largest nushell +7.7%, prometheus +7.6%, redis +6.7%; smallest preact
  +0.3%.
- Combined top: redis +13.2%, rubocop +11.9%, framework +11.6%.
- SPEC outliers are the large-code benchmarks: gcc +10.3% with both (+5.9%
  BTB, +3.6% TLB), vpr +4.2%, ns3 +3.6%, llvm +2.4% (BTB). **714.cpython_r
  −3.4% with the infinite BTB** (not investigated).

**Skipping the first 100M** (120M effective warm-up, 300M measured for
agentic), agentic median, full → skip:

| | no-FDP | inf-BTB | inf-TLB | inf-BTB+TLB |
|---|---|---|---|---|
| IPC | −2.8 → −2.9% | +3.1 → +3.0% | +3.1 → +3.3% | **+6.4 → +7.5%** |
| fetch rate | −3.7 → −3.8% | +1.7 → +1.9% | +3.4 → +3.5% | +5.8 → +6.4% |
| BTB-miss mispredicts | +6.6 → +6.5% | −74.9 → −76.6% | 0 | −75.0 → −78.0% |
| all branch mispredicts | +1.5 → +1.2% | −13.0 → −13.6% | 0 | −13.2 → −15.5% |
| completed walks | 0 | 0 → +1% | −79.3 → −81.5% | −78.6 → −80.2% |
| L2 MPKI | −22.9% | −16.3 → −17.4% | −1.5 → −1.0% | −17.6 → −19.2% |

Combined after the skip: IQR +4.8% to +9.4%, max +15.4%; more than the sum
of the singles (6.3%). Baseline IPC 0.991 → 0.997.

Memory: nushell-13831 22.2 GB peak, docusaurus ~11 GB, others 2.5–6 GB.

## Conclusions

- [[btb-tlb-limits]]: each limit is worth ~3% on agentic and nothing on
  SPEC; together 6.4–7.5%, at least additive.
- The BTB gain also cuts L1I (−34%) and L2 (−16%) misses: fewer
  fall-through fetches past undetected branches (plausible, not verified;
  [[decoupled-front-end]]).
- Part of the TLB gain acts through FDP prefetch translations
  ([[fdp-inflates-itlb-misses]]).
- Longer O3 warm-up matters mainly for the combined limit
  ([[warmup-and-skip]]).

## Decisions

1. Hash-map BTB, not a huge `SimpleBTB` (speed); stock `ArmTLB` enlarged,
   not a new TLB (correctness under TLBIs).
2. Per-ASID BTB tables plus one kernel table; ASID through a generic MMU
   hook; `ignoreAsidLsb` for KPTI.
3. BTB misses measured with `mispredictDueToBTBMiss`
   ([[btb-miss-stat-zero-decoupled]]); walks with completed walks
   ([[walk-requests-vs-completed]]).
4. `smart_sweep.sh` for concurrent sweeps.
5. A 100M skip as extra warm-up, without re-simulating.

## Open

- 714.cpython_r −3.4% with the infinite BTB.
- Pass-1/pass-2 oracle to remove compulsory BTB misses.
- `--disable-fdp --infinite-tlb` to separate the TLB and FDP effects.
- More tasks / checkpoints per task to see how the ceiling varies.
- `window_view.py`'s `btb_mpki` row.
(All in [[questions]].)
