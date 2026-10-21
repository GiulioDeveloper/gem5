---
type: entity
status: current
updated: 2026-10-21
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
| fetch / decode / rename / dispatch / issue / writeback / commit width | 6 / 6 / 8 / 8 / 8 / 8 / 8 |
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

| level | size | assoc | latency (tag/data/response) | prefetchers |
|---|---|---|---|---|
| L1I | 64 KiB | 8 | 2/2/2 | FDP (fetch-directed, from the FTQ) + tagged (virtual addresses) |
| L1D | 64 KiB | 8 | 4/4/4 | Stride (degree 8) + SMS |
| L2 | 2 MiB | 8 | 11/11/11 | BOP |
| memory | single-channel DDR5-6400 (`--mem-type`), 16 GiB | | | |

There is no L3. An 8 KiB MMU cache sits in front of the L2 for page-table
walks. TLBs: [[tlb-hierarchy]] (48-entry L1 iTLB and dTLB, 2,048-entry
8-way shared L2 TLB, zero-latency L2 hits).

## Switches (`sim_opts.py`, shared by `virt_run.py`, `fs_run.py`, `se_run.py`)

| flag | effect |
|---|---|
| `--disable-fdp` | decoupled front end and the FDP prefetcher off (the tagged L1I prefetcher stays) |
| `--disable-l1d-prefetch`, `--disable-l2-prefetch` | detach those prefetchers |
| `--infinite-btb` | [[infinite-btb-model]] instead of the 12K BTB |
| `--infinite-tlb` | [[infinite-l2-tlb]] instead of the 2K L2 TLB |
| `--clk-freq`, `--mem-type`, `--mem-size` | clock, DRAM preset, guest RAM (must match the checkpoint) |
| `--progress-interval` | heartbeat with IPC and KIPS; always use `10kHz` on restores |

The Garfield mechanisms (`--ghost-exec`, `--use-mrn`, `--use-vp`, ...) are
still in the code, off by default ([[garfield-overview]]).
