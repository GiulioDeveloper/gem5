---
type: experiment
status: open
updated: 2026-11-06
sources:
  - src/cpu/o3/fetch.cc
  - src/cpu/o3/decode.cc
  - configs/garfield/arm/neoverse_v2.py
  - configs/garfield/arm/sim_opts.py
  - runs/topdown/long/
  - runs/front-end-width/
tags: [front-end, width, top-down, baseline]
---

# Front-end width: fetch and decode at 8 micro-ops

**Question:** the [[neoverse-v2]] config has fetch and decode 6 wide and
rename to commit 8 wide. gem5 cracks macro-ops into micro-ops at fetch, so
that 6 is a cap on *micro-ops*, and rename can never get more than 6 a
cycle. How much does this cap cost SPEC and agentic, and should the
baseline be 8 wide?

**Status:** the claim checks out in the code; the switch is built and
validated; sweeps `runs/sweep/20261105-1143-{fe8,spec-fe6,spec-fe8}`
running since 2026-11-05 (behind the perfect-* sweeps on the memory gate).
Interim results from 12 runs per suite (2026-11-06) under Results.

## The claim, checked

- **Fetch counts micro-ops.** `Fetch::fetch` builds a `DynInst` per
  micro-op (`curMacroop->fetchMicroop`) and increments `numInst` for each;
  the loop stops at `numInst < fetchWidth` (`src/cpu/o3/fetch.cc`).
  `fetch.nisnDist` is a histogram of micro-ops fetched per cycle.
- **Fetch to decode and decode to rename move micro-ops**, at most
  `decodeWidth` a cycle (`fetch.cc`, `insts_to_decode < decodeWidth`;
  `decode.cc`, `toRenameIndex < decodeWidth`).
- So rename sees at most 6 micro-ops a cycle. Its 8 slots can never all be
  filled from the front end, and the top-down accounting
  ([[top-down-accounting]]) charges the 2 missing slots of every cycle
  with a full delivery to `fetchBandwidth`.

**On real V2** (Arm Hot Chips 2023; [jia.je microbenchmarks](https://jia.je/hardware/2024/11/07/arm-neoverse-v2/)):
the decoders take 6 *instructions* a cycle, the 1536-entry MOP cache
delivers 8 MOPs a cycle, and rename/dispatch takes 8 MOPs. Measured: about
8 IPC from the MOP cache, about 6 from the L1I. So:
- a real V2 is 8 wide end to end only on MOP-cache hits;
- on the decode path it is 6 *instructions*, which crack into more than 6
  MOPs. Our 6-micro-op cap is narrower than that (by the ops/inst ratio,
  1.07 rubocop, 1.16 cppcheck);
- gem5 has no MOP cache. 8 wide everywhere is therefore an *upper* bound
  on a real V2 front end (every fetch a MOP-cache hit), 6 a lower bound.

**How often the cap binds** (400M windows of
[[2026-11-03-top-down-validation]], `fetch.nisnDist`):

| window | cycles fetching 0 | fetching 6 (cap) | fetched µops/cycle | UPC | FE bound | of which bandwidth |
|---|---|---|---|---|---|---|
| 727.cppcheck_r | 69.6% | 11.2% | 1.13 | 1.12 | 0.41 | 0.24 |
| rubocop-13560 | 67.3% | 15.1% | 1.47 | 1.03 | 0.39 | 0.14 |
| rubocop, perfect L1I 1 cycle | 61.5% | 17.7% | 1.71 | 1.18 | 0.27 | 0.16 |

(Values here are means of per-block top-down fractions, so they differ a
little from the summed-counter table on that page.)

Fetch is idle two thirds of the time and at the cap 11-18%. The cap is
real but is not the main front-end limit: most lost slots are cycles with
nothing fetched (the fetch model waiting on L1I hits, `icacheWaitResponse`,
and misses). Expectation: a few percent IPC, more on SPEC, whose front-end
share is mostly bandwidth. The bandwidth fraction itself should shrink a
lot, because the 2 structural slots per full cycle go away.

## Setup

- **Switch:** `--front-end-width N` (`sim_opts.py`) sets `fetchWidth` and
  `decodeWidth` together; the default leaves the config's 6. The banner
  prints a `core` line with both widths. Other widths are already 8;
  `fetchQueueSize` (32) and the 64-byte fetch target are wide enough.
- **Validation:** `runs/front-end-width/validate.sh`, rubocop-13560, 2M +
  10M, with no flag, `6` and `8`. No flag and `6` must be identical.
- **Sweeps:** `runs/front-end-width/launch.sh`, smart sweeps sharing the
  gate with the perfect-* sweeps:
  - agentic, width 8: 27 × 1B, same settings as
    [[2026-11-03-perfect-l1i]]; paired with `runs/sweep/20261104-1115-base`
    (same commit, `5889fe1205`);
  - SPEC, widths 6 and 8: 26 × 200M each (no SPEC sweep on the top-down
    code exists yet).

## Results

**Validation** (`runs/front-end-width/validate/`): no flag and
`--front-end-width 6` give identical simulated stats (0 differing values);
at 8, `config.ini` has `fetchWidth=decodeWidth=8` and `fetch.nisnDist`
reaches 8. On rubocop-13560 the two widths diverge in schedule after about
3M instructions (opencode switched in 8 times at 6, 4 at 8:
[[window-placement]]), so the 12M window IPC (0.74 vs 1.02) is mostly
different work. Over the first 3M, before the divergence, width 8 takes
3.0% less time. Smoke test only.

**Sweeps, interim (2026-11-06, 12 finished runs per suite;
`runs/front-end-width/interim.py`, top-down slot-weighted over blocks;
deltas are width 8 minus 6, paired per checkpoint, medians):**

| suite | IPC gain | range | FE bound | bandwidth | latency | bad spec. | BE bound | retiring |
|---|---|---|---|---|---|---|---|---|
| agentic (1B) | +1.1% | −1.7 to +5.2% | −0.040 | −0.047 | +0.008 | +0.008 | +0.032 | +0.002 |
| SPEC (200M) | +2.2% | −1.2 to +5.4% | −0.051 | −0.066 | +0.010 | +0.011 | +0.030 | +0.005 |

Reading (provisional): the bandwidth share falls as expected (cppcheck
−0.16), but the freed slots go mostly to back-end bound, not retiring, so
IPC moves 1-2%. SPEC gains about twice as much as agentic, so 6 wide
understates the agentic/SPEC front-end gap by about a point of IPC. The two
agentic losses (carbon, fastlane) are likely full-system schedule
variation. Final numbers when the sweeps finish.

**Sweeps, setup note:** `sweep.conf` says `5889fe1205-dirty`: the only
uncommitted code change is the `--front-end-width` switch itself, whose
default path is identical to the base sweep's.

## Why fetch delivers nothing in most cycles (2026-11-06)

`runs/front-end-width/zero_fetch.py` splits the cycles with 0 micro-ops
fetched (`fetch.nisnDist::0`) by `fetch.status`: waiting for the L1I
(`icacheWaitResponse`), squash/trap/ITLB, and the rest, which are cycles
fetch was running but the fetch queue was full (back-pressure). *Floor*
is the zero share needed anyway if every active cycle delivered a full 6
(1 − fetched per cycle / 6). Width 6, medians, % of cycles:

| suite | UPC | zero | L1I wait | back-pressure | squash/other | floor | decode blocked |
|---|---|---|---|---|---|---|---|
| agentic (27, base sweep) | 1.17 | 60 | 21 | 36 | 3 | 72 | 39 |
| SPEC (12, `spec-fe6`) | 1.50 | 51 | 30 | 17 | 1 | 64 | 19 |

(The 70% above is from the two 400M windows; the sweep medians are lower.)

- **Zero cycles are mostly a consequence of low IPC.** The zero share is
  below the floor in every run: at ~1.2 µops/cycle a 6-wide fetch must
  idle most cycles. Back-pressure (decode blocked behind rename, behind a
  full ROB/IQ/LSQ) is the largest part on agentic; cactus is 88%.
- **The L1I wait is hit latency.** Fetch waits 1.00 cycle per cache line on
  cppcheck and ntest (L1I miss rate ~0), 1.17-1.29 on agentic (gin,
  rubocop: ~1.6 misses per 1000 cycles). SPEC waits more because it
  crosses more lines per cycle (166-319 vs 127-191 per 1000 cycles).
- **Likely a model artifact.** Fetch issues an L1I request when it
  reaches a new line and only pipelines the next sequential line, so each
  taken branch to a new line leaves a bubble. A real V2 issues accesses
  ahead from the FTQ, which here is full 74-97% of cycles. The fetch queue
  hides much of it; the 1-cycle perfect L1I of
  [[2026-11-03-top-down-validation]] shows the rest (FE bound −0.12
  cppcheck, −0.08 rubocop). It taxes high-IPC SPEC more than agentic.
- Proposed: issue L1I accesses for queued fetch targets ahead of fetch
  (`Fetch::pipelineIcacheAccesses`), as a baseline fix. Not started.

## Decision to make

Whether 8 becomes the baseline. If the bandwidth cap is a large share of
SPEC's front-end bound, the 6-wide baseline understates the agentic/SPEC
gap in front-end latency and the [[agentic-front-end-bound]] reading
should be redone at 8. The perfect-* sweeps ran at 6; switching the
baseline means either rerunning them or keeping 6 as the limit-study
baseline and reporting width separately.

## Open

- A MOP-cache model (8 wide on hits, 6 instructions on misses) would sit
  between the two bounds; not planned.
- The larger front-end loss is fetch idling on L1I hits
  ([[2026-11-03-top-down-validation#Open]]), independent of width.
