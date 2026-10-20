# Infinite L2 TLB: a 1M-entry shared TLB for limit studies

`--infinite-tlb` replaces the Neoverse V2 core's shared L2 TLB (2,048
entries, 8-way) with a 1M-entry, 16-way one. Capacity and conflict misses
disappear; compulsory misses and misses after TLB invalidations remain.
The question it answers: *how much do page walks cost?* Companion to
[`infinite-btb.md`](infinite-btb.md).

## 1. Why enlarging the L2 TLB is enough

- **An L2 TLB hit costs no time in this configuration.** On an L1 iTLB or
  dTLB miss, `TLB::multiLookup` (`src/arch/arm/tlb.cc:208`) looks up the
  next level (`l2_shared`) synchronously, in the same call. A hit is copied
  into the L1 and the translation completes with no added latency (commit
  `054bb4126c`: "Connecting L2 TLB (no latency)"). Only an L2 miss starts a
  page-table walk, which has real latency and whose descriptor reads go
  through the cache hierarchy.
- So **an unbounded L2 TLB is effectively a perfect TLB**, apart from
  compulsory and post-invalidation misses. The L1 TLBs (48 entries) stay
  as they are, since their misses are free.

## 2. Why it is the stock `ArmTLB` and not a new class

Unlike a BTB, a TLB is needed for correctness: a stale entry produces a
wrong physical address. The TLB must keep honouring every `TLBI` (by VA,
ASID, VMID or range, and full flushes) with the architectural matching
rules. `TLB::flush(const TLBIOp&)` (`tlb.cc:308`) already does this. A
from-scratch hash-map TLB would have to reimplement it, along with the
multiple page sizes. Reusing `ArmTLB` keeps that risk at zero.

Cost of a 1M-entry `ArmTLB`:

| Operation | Cost | Note |
|---|---|---|
| Lookup | O(assoc) per observed page size | same as today (`TLBSetAssociative`, `src/arch/arm/pagetable.hh:210`) |
| Insert | O(assoc) | `invalidatePrev` only clears a one-entry lookup cache (`tlb.cc:95`) |
| `TLBI` | O(size): a scan of the whole table | fmt-3901 has 1,230 TLBIs in 400M instructions, so about 1.2G entry checks per run |
| Memory | about 170 MB more per run | peak RSS 3.53 GB vs. 3.36 GB on fmt-3901 |

Simulation speed was unchanged in the sanity check (§4).

## 3. Configuration

- `configs/garfield/arm/neoverse_v2.py`: `NeoverseV2_InfiniteL2TLB(ArmTLB)`
  with `entry_type="unified"`, `size = 1 << 20`, `assoc = 16` (65,536
  sets), and `partial_levels=["L2"]` as in the baseline, so it also caches
  partial (level-2 walk) translations.
- `configs/garfield/arm/sim_opts.py`: `--infinite-tlb` sets
  `cpu.mmu.l2_shared` in `apply_core_knobs`. The L1 TLBs' `next_level`
  proxies resolve to the new object. The banner shows `L2TLB=1M`.

## 4. Measuring walks: requests vs. completed walks

`mmu.walker.walks` counts walk **requests**, not completed walks. The
`walks_pki` metric of the sweep tools (`trace_analysis.py`) uses it. Many
requests never become a walk: requests squashed before starting (wrong
path) and requests coalesced or retried for a page that is already being
walked. Likewise, an L2 TLB "miss" is counted on every non-functional
lookup that misses (`tlb.cc:180`). The completed walks are
`walker.requestOrigin_Completed::{Data,Inst}`, and they match the L2 TLB
`inserts` closely.

**Sanity check (2026-10-16):** fmt-3901, 1-instruction settle, 5M warm-up,
20M measured instructions
(`runs/btb/20261016-tlbcheck-fmt-3901/{baseline,inftlb}`).

| | Baseline | Infinite L2 TLB |
|---|---|---|
| Walk requests (`walker.walks`) | 55,244 | 45,937 |
| …squashed before starting | 21,166 | 15,631 |
| **Completed walks** | **13,064** | **9,500 (−27%)** |
| L2 TLB inserts | 13,557 | 9,792 |
| `TLBI`s in the window | 0 | 0 |
| Walked pages: 4 KiB / 2 MiB | 13,043 / 21 | 9,488 / 12 |
| IPC | 1.035 | 1.038 (+0.3%) |
| Peak RSS / wall time | 3.36 GB / 2:05 | 3.53 GB / 2:05 |

- The TLBs start empty at the restore. In a 25M-instruction window the
  remaining 9.5K completed walks are compulsory, and they dominate, which
  is why IPC barely moves. The 400M sweep window measures the steady state.
- **The guest uses 4 KiB pages almost exclusively** (2 MiB walks are
  0.1%). Huge pages are not hiding anything here.
- `walks_pki` overstates completed walks about 4× in this window. That
  matters for absolute statements; comparisons between configurations or
  suites use the same metric on both sides.

## 5. Assumptions and decisions

| # | Decision / assumption | Consequence / check |
|---|---|---|
| 1 | Enlarge `l2_shared`; keep the L1 TLBs | Valid because L2 hits are free here. If an L2 latency is modelled later, this becomes "infinite L2 with that latency", not a perfect TLB. |
| 2 | Stock `ArmTLB` | All TLBIs are honoured exactly; no new correctness risk. |
| 3 | 1M entries, 16-way | Far above the footprint (a 20M window touches about 10–13K pages). Conflict misses in a 65,536-set table are negligible but not provably zero. Check: `l2_shared.inserts` close to completed walks. |
| 4 | Keep `partial_levels=["L2"]` | Same walk-cache behaviour as the baseline. |
| 5 | Measure with completed walks, not `walker.walks` | See §4. |
| 6 | The larger L2 TLB also helps the FDP prefetcher | A prefetch translation that misses the TLB is dropped without a walk (`PrefetchTLBMiss`, `src/arch/arm/mmu.cc:1723`). With an unbounded L2 more instruction prefetches go through, so part of the gain may come through FDP. The infinite-TLB sweep alone cannot separate the two effects; a `--disable-fdp --infinite-tlb` run would. |

## 6. Results

Full sweeps (2026-10-19, `runs/sweep/20261019-compare-5way/`), median
against the FDP baseline. Agentic: IPC **+3.1%** with the infinite L2 TLB
alone, **+6.4%** together with the infinite BTB; completed page walks
0.62 → 0.15 per 1K instructions (−76%); walk requests −44%; iTLB MPKI −27%
(more FDP prefetch translations hit); fetch rate +3.4%. SPEC: median +0.0%,
with 734.vpr_r +3.9% and 721.gcc_r +3.6% the only notable gains. Details
in the research log
[`2026-10-16-infinite-btb.md`](../research-log/agentic/2026-10-16-infinite-btb.md).
