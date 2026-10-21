---
type: concept
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/infinite-btb]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - configs/garfield/arm/neoverse_v2.py
  - src/cpu/o3/bac.cc
tags: [front-end, fdp, btb, prefetch]
---

# Decoupled front end and FDP

**What it is:** in the [[neoverse-v2]] config the O3 front end is
decoupled. A **BAC** stage (`src/cpu/o3/bac.cc`) runs ahead of fetch and
fills a **fetch target queue** (FTQ, 32 entries of up to 64 bytes); fetch
consumes the targets; the **fetch-directed prefetcher** (FDP, on the L1I)
prefetches the lines of queued targets. Worth about +2.8% IPC on agentic
windows and nothing on most SPEC ([[fdp-value]]).

## The BTB detects branches

BAC has no instruction bytes yet. To find branches it walks each target in
`minInstSize` (4-byte) steps asking the BTB whether a branch is there
(`bpu->BTBValid`); on a hit it takes the branch's `StaticInst` from the BTB
and predicts it. **A branch that misses in the BTB is not detected at all**:
the fetch target runs past it, fetch meets it at predecode with no
prediction (a not-taken placeholder, `bac.cc:858`), and if it was taken the
mistake surfaces later as a mispredict. So the BTB does two jobs here,
detection and target supply, which is why BTB capacity matters so much
more for agentic code ([[btb]], [[btb-tlb-limits]]).

Consequences for measurement:
- `btb.misses` is always 0 in decoupled mode ([[btb-miss-stat-zero-decoupled]]).
- An undetected taken branch sends fetch and FDP down the fall-through path.
  The infinite-BTB runs cut L1I misses by a third and L2 misses by a sixth
  as a side effect, which fits this (not verified).

## FDP and the iTLB

FDP translates its prefetch targets through the same L1 iTLB as demand
fetch. A prefetch translation that misses is **counted as an iTLB miss and
then dropped** (`PrefetchTLBMiss`, no walk, no fill;
`src/arch/arm/mmu.cc:1723`). So with FDP on, iTLB MPKI is mostly FDP's own
lookups: agentic iTLB MPKI is 37 with FDP and 2.9 without
([[fdp-inflates-itlb-misses]]). A larger L2 TLB lets more prefetch
translations hit, so TLB studies partly act through FDP
([[infinite-l2-tlb]]).

## Turning it off

`--disable-fdp` turns off both the decoupled front end and the FDP
prefetcher (the tagged L1I prefetcher stays); the BTB then sees every
branch through `lookup` and `btb.misses` is meaningful
([[2026-10-14-fdp-off-sweep]]).
