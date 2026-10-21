---
type: entity
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/infinite-tlb]]"
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
  - configs/garfield/arm/neoverse_v2.py
tags: [tlb, limit-study]
---

# Infinite L2 TLB: 1M-entry shared TLB

**What it is:** `--infinite-tlb` replaces the 2,048-entry 8-way shared L2
TLB with a 1M-entry 16-way one (`NeoverseV2_InfiniteL2TLB`, 65,536 sets,
`partial_levels=["L2"]` as in the baseline); the banner shows `L2TLB=1M`.
Capacity and conflict misses disappear; compulsory and post-invalidation
misses remain. Because L2 TLB hits are free in this config
([[tlb-hierarchy]]), it is effectively a perfect TLB. Result: +3.1% IPC on
the median agentic window, completed walks −76% ([[btb-tlb-limits]]).

## Why the stock `ArmTLB`

Unlike a BTB, a TLB matters for correctness: a stale entry gives a wrong
physical address. `ArmTLB` already honours every `TLBI` (by VA, ASID, VMID,
range, full) and every page size, so a hash-map rewrite would only add risk.
Cost: lookups and inserts O(assoc) as before; a `TLBI` scans the whole
table (fmt-3901: 1,230 TLBIs in 400M instructions, about 1.2G entry
checks); about 170 MB more memory per run. Simulation speed unchanged.

## Decisions

| decision | consequence |
|---|---|
| enlarge `l2_shared`, keep the 48-entry L1s | valid only while L2 hits are free; with a modelled L2 latency it becomes "infinite L2 with that latency" |
| 1M entries, 16-way | far above the footprint (a 20M window touches 10–13K pages); conflicts negligible but not provably zero. Check `l2_shared.inserts` ≈ completed walks |
| measure **completed walks**, not `walker.walks` | [[walk-requests-vs-completed]] |
| it also helps FDP | prefetch translations that miss are dropped, so more of them now go through; the TLB gain is partly an FDP gain. `--disable-fdp --infinite-tlb` would separate them ([[questions]]) |

## Validation (2026-10-16, fmt-3901, 5M warm-up + 20M)

| | baseline | infinite L2 TLB |
|---|---|---|
| walk requests | 55,244 | 45,937 |
| … squashed before starting | 21,166 | 15,631 |
| **completed walks** | 13,064 | 9,500 (−27%) |
| L2 TLB inserts | 13,557 | 9,792 |
| IPC | 1.035 | 1.038 |
| peak RSS | 3.36 GB | 3.53 GB |

In so short a window the TLBs start empty and compulsory walks dominate;
the 400M sweep window shows the steady state (−76% completed walks).
