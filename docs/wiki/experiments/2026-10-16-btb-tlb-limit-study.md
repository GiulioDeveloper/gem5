---
type: experiment
status: current
updated: 2026-10-30
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

**Geometric means** (2026-10-28, `compare_multi_geomean.csv` in both
comparison directories): baseline FDP IPC is the geomean of its window
values; every other entry is the geomean of the per-checkpoint ratio to
FDP. Full window → skip 100M:

| | FDP IPC | no-FDP | inf-BTB | inf-TLB | inf-BTB+TLB |
|---|---|---|---|---|---|
| agentic | 0.995 → 1.003 | 0.969× → 0.971× | 1.028× → 1.028× | 1.036× → 1.039× | **1.069× → 1.075×** |
| SPEC | 1.468 → 1.468 | 0.973× → 0.973× | 1.003× → 1.002× | 1.004× → 1.004× | 1.008× → 1.006× |

They agree with the medians above. SPEC no-FDP is −2.7% by geomean against
a −0.2% median: a few large-code benchmarks lose a lot. In the skip
summary, SPEC BTB-miss mispredicts with the infinite BTB fall to zero in 8
of 26 windows; those have no ratio and are left out, so the 0.19× geomean
understates the drop.

**Per slice category** (2026-10-29, `compare_multi_geomean_slices.csv`;
categories in [[sweeps]]). These are agentic
IPC geomeans over the windows where the category ran (at least 1M
instructions), full window → skip 100M:

| category | n | FDP IPC | no-FDP | inf-BTB | inf-TLB | inf-BTB+TLB |
|---|---|---|---|---|---|---|
| harness (OpenCode) | 21 → 19 | 0.878 → 0.893 | −2.4 → −2.9% | +2.2 → +2.1% | **+5.3 → +5.4%** | **+9.0 → +9.6%** |
| tools | 13 → 11 | 1.039 → 1.079 | −2.7 → −1.4% | +2.3 → +2.2% | +2.0 → +2.5% | +4.6 → +5.0% |
| harness git | 13 → 12 | 0.944 → 0.941 | −3.4 → −3.5% | +2.3 → +2.2% | +0.1 → −0.3% | +2.3 → +2.4% |
| replay infra | 27 | 0.916 → 0.914 | −3.0 → −2.5% | +3.1 → +4.3% | +1.9 → +2.5% | +5.1 → +6.6% |

- The harness gains most, and mostly from the TLB: its completed walks are
  1.69 PKI, against 0.65 for the whole window.
- Its git snapshots gain nothing from the TLB.
- "Other" (IPC 0.20) is left out: its cycles include idle WFI time.

Time shares (baseline, median / mean over 27 windows):
- harness 58% / 41%;
- tools 0% / 25%: zero in most windows, about 75% in 9;
- harness git 0% / 7%;
- replay infra 21% / 21%;
- other 0.6% / 6%.

Most windows are mainly harness or mainly tools, rarely both. axios and
bat spend 74% and 71% of their time idle, with under 1% of the
instructions.

**Away from context switches** (2026-10-30,
`compare_multi_geomean_edges.csv`; edge blocks in [[sweeps]]). These are
agentic IPC geomeans with the first and last k stats blocks of every
thread run dropped (k = 0 is the full window):

| slices | k | FDP IPC | no-FDP | inf-BTB | inf-TLB | inf-BTB+TLB |
|---|---|---|---|---|---|---|
| all | 0 / 1 / 3 / 5 | 0.995 / 1.07 / 1.11 / 1.13 | −3.1 / −2.5 / −2.4 / −2.6% | +2.8 / +1.9 / +1.7 / +1.6% | +3.6 / +3.0 / +2.7 / +2.7% | **+6.9 / +4.9 / +4.1 / +3.7%** |
| harness | 0 / 1 / 3 / 5 | 0.878 / 0.941 / 0.975 / 1.007 | −2.4 / −2.0 / −1.8 / −2.5% | +2.2 / +1.5 / +1.7 / +1.1% | +5.3 / +4.2 / +3.7 / +3.6% | **+9.0 / +6.7 / +5.3 / +5.0%** |
| tools | 0 / 1 / 3 / 5 | 1.04 / 1.08 / 1.12 / 1.15 | −2.7 / −3.1 / −2.8 / −3.5% | +2.3 / +1.4 / +1.8 / +1.5% | +2.0 / +1.5 / +1.6 / +1.1% | +4.6 / +3.3 / +2.9 / +2.7% |
| harness git | 0 / 1 / 3 / 5 | 0.944 / 0.998 / 1.05 / 1.09 | −3.4 / −3.9 / −3.1 / −2.0% | +2.3 / +1.4 / +0.1 / −0.2% | +0.1 / −0.3 / −0.7 / −0.9% | +2.3 / +0.9 / +0.6 / 0.0% |
| replay infra | 0 / 1 / 3 / 5 | 0.916 / 1.01 / 1.03 / 1.06 | −3.0 / −2.4 / −2.1 / −2.2% | +3.1 / +1.4 / +0.8 / +0.6% | +1.9 / +1.5 / +1.2 / +0.8% | +5.1 / +2.0 / +0.8 / +0.6% |

- Baseline IPC rises as blocks near switches are dropped: agentic
  0.995 → 1.13 at k = 5. L1I MPKI falls 1.49 → 0.64 and iTLB MPKI
  34 → 20.
- About half of the limits' agentic gain sits within one block of a
  switch: +6.9% → +3.7% at k = 5. Replay infra's gain almost vanishes,
  while the harness keeps +5%, mostly the TLB.
- So a large BTB and TLB help mostly by surviving context switches, plus
  the harness's own TLB pressure. This is provisional: the dropped
  stretches are also the switch-heavy phases (work mix), and each sweep
  drops the blocks around its own switches.

Switch frequency in the baseline is 4.0 kHz (geomean; 248 µs between
switches). The scheduler path (`__schedule` → `__switch_to`) takes 0.26%
of agentic instructions.

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
