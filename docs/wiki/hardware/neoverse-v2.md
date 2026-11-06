---
type: entity
status: current
updated: 2026-11-05
sources:
  - configs/garfield/arm/neoverse_v2.py
  - configs/garfield/arm/cache_hierarchy.py
  - configs/garfield/arm/sim_opts.py
tags: [core, config, neoverse-v2, o3]
---

# The Neoverse V2 model

**What it is:** the gem5 O3 (`ArmO3CPU`) configuration every agentic and
SPEC run uses, `configs/garfield/arm/neoverse_v2.py`: a fork-owned copy of
upstream `configs/common/cores/arm/neoverse_v2.py` (copied 2026-06-27 for
Garfield), modelled on public Neoverse V2 / Graviton4 descriptions. Local
changes against upstream: LRU replacement in the L1s (was RRIP), BOP
prefetcher moved from L1D to L2, L1 TLBs connected to the L2 TLB
([[l2-tlb-disconnected]]), and the limit-study variants below. The config
file is authoritative; numbers in older reports that disagree with it are
wrong ([[garfield-overview]]).

## Core

| | value |
|---|---|
| clock | 3 GHz (`--clk-freq`, default) |
| fetch / decode / rename / dispatch / issue / writeback / commit width | 6 / 6 / 8 / 8 / 8 / 8 / 8 (fetch and decode count micro-ops, not instructions: [[2026-11-05-front-end-width]]) |
| ROB | **320** entries |
| LQ / SQ | 175 / 80 |
| physical int / FP registers | 213 / 188 |
| issue queues | 9 (`Neoverse_V2_IQ0..8`): 4 × 22, 2 × 28, 3 × 16 entries |
| memory dependence | StoreSets (LFST 1024, SSIT 1024) |
| trap latency | 13 cycles |

## Front end

- **Decoupled front end** (`decoupledFrontEnd = True`): a BAC stage runs
  ahead of fetch filling a 32-entry FTQ with 64-byte fetch targets
  (`fetchTargetWidth`), and the BTB *detects* branches
  (`requiresBTBHit = True`). See [[decoupled-front-end]] and [[btb]].
- **Branch prediction:** TAGE-SC-L 64 KB, taken-only history, RAS 31
  entries, BTB 12K entries 6-way with 18-bit tags (`NeoverseV2_BTB`,
  `SimpleBTB`).

## Memory hierarchy

Private per core (`NeoverseV2CacheHierarchy`, a classic
`PrivateL1PrivateL2CacheHierarchy`; [[memory-system]]):

| level | size | assoc | latency (tag/data/response) | MSHRs | replacement | prefetchers |
|---|---|---|---|---|---|---|
| L1I | 64 KiB | 8 | 2/2/2 | 12 | LRU | FDP (fetch-directed, from the FTQ) + tagged (degree 2) |
| L1D | 64 KiB | 8 | 4/4/4 | 12 | LRU | Stride (degree 8) + SMS |
| L2 | 2 MiB | 8 | 11/11/11 | 96 | BRRIP | BOP (degree 1) |
| MMU cache | 8 KiB | 4 | 1/1/1 | 20 | LRU | – |
| memory | one DDR5-6400 DIMM (`--mem-type`, two 32-bit subchannels as two controllers, 64 B interleaved), 16 GiB | | | | | |

There is no L3. The MMU cache sits in front of the L2 for page-table
walks. Values checked against a baseline sweep's `config.ini`
(2026-10-29). The indirect predictor is `SimpleIndirectPredictor`, 256
sets × 2 ways. TLBs: [[tlb-hierarchy]] (48-entry L1 iTLB and dTLB, 2,048-entry
8-way shared L2 TLB, zero-latency L2 hits).

## Switches (`sim_opts.py`, shared by `virt_run.py`, `fs_run.py`, `se_run.py`)

| flag | effect |
|---|---|
| `--disable-fdp` | decoupled front end and the FDP prefetcher off (the tagged L1I prefetcher stays) |
| `--disable-l1d-prefetch`, `--disable-l2-prefetch` | detach those prefetchers |
| `--infinite-btb` | [[infinite-btb-model]] instead of the 12K BTB |
| `--infinite-tlb` | [[infinite-l2-tlb]] instead of the 2K L2 TLB |
| `--perfect-tlb` | every demand TLB miss of the O3 core is served by a zero-time functional walk (`ArmMMU.perfect_tlb`), so translations always hit, cold and post-`TLBI` misses included; prefetch translations still drop on a miss; counted in `mmu.perfectWalks`; exclusive with `--infinite-tlb`. See [[2026-11-02-perfect-l2]] |
| `--cache-scale N` (1, 2, 4, 8, 16) | multiplies the L1I, L1D and L2 sizes by N (more sets; associativity and latencies unchanged); first used in [[2026-10-23-rubocop-15g-cache-btb-tlb]] |
| `--perfect-l2` (`--perfect-l2-cycles N`, default 11) | no L2 and no per-core L2 crossbar: the L1s and MMU cache sit on a membus timed like the L2 crossbar, in front of a `SimpleMemory` of N core cycles, so every L1 miss costs an L2 hit, cold misses included; replaces `--mem-type`. See [[2026-11-02-perfect-l2]] |
| `--perfect-l1i` (`--perfect-l1i-cycles N`, default 2) | O3 fetch reads every fetch block functionally and delivers it after N cycles (`perfectICache`), so the L1I always hits, cold misses included; the caches see no instruction traffic, so data gets the whole L2; the FDP prefetcher is detached, the decoupled front end stays on; counted in `fetch.perfectICacheReads`. See [[2026-11-03-perfect-l1i]] |
| `--front-end-width N` | sets `fetchWidth` and `decodeWidth` to N micro-ops (default 6). gem5 cracks at fetch, so at 6 rename (8) never fills. See [[2026-11-05-front-end-width]] |
| `--clk-freq`, `--mem-type`, `--mem-size` | clock, DRAM preset, guest RAM (must match the checkpoint) |
| `--progress-interval` | heartbeat with IPC and KIPS; always use `10kHz` on restores |

The Garfield mechanisms (`--ghost-exec`, `--use-mrn`, `--use-vp`, ...) are
still in the code, off by default ([[garfield-overview]]).
