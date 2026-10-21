---
type: concept
status: current
updated: 2026-10-21
sources:
  - configs/garfield/arm/neoverse_v2.py
  - "[[legacy-log/garfield/infinite-tlb]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [tlb, mmu, page-walk]
---

# TLB hierarchy and page walks

**Config** (`NeoverseMMU` in `configs/garfield/arm/neoverse_v2.py`):

| TLB | entries | assoc | next level |
|---|---|---|---|
| L1 iTLB | 48 | 12 | `l2_shared` |
| L1 dTLB | 48 | 48 | `l2_shared` |
| shared L2 TLB | 2,048 | 8 | page-table walker (caches partial level-2 translations) |

Walk descriptors are read through an 8 KiB MMU cache and the L2.

## Facts that matter

- **L2 TLB hits cost no time.** On an L1 miss, `TLB::multiLookup`
  (`src/arch/arm/tlb.cc`) looks up `l2_shared` synchronously; a hit is
  copied into the L1 with no added latency. Only an L2 miss starts a walk,
  which has real latency. That is why an unbounded L2 TLB is effectively a
  perfect TLB ([[infinite-l2-tlb]]).
- **Connected only since 2026-10-13.** Before, `NeoverseMMU` overrode
  `itb`/`dtb` without `next_level`, so every L1 miss walked
  ([[l2-tlb-disconnected]]).
- **The guest uses 4 KiB pages almost exclusively** (2 MiB walks are 0.1%
  in fmt-3901). Huge pages hide nothing here.
- **The tracer's functional reads must not touch the TLB** (gem5's
  functional translation updates TLB state): [[functional-translation-perturbs]].
- 16-bit ASIDs: the restore depends on the fork's ASID fix
  ([[restore-silent-failures]]).

## Metrics

| metric | stat | meaning |
|---|---|---|
| `itlb_mpki` / `dtlb_mpki` | L1 TLB misses | with FDP on, iTLB misses are mostly dropped prefetch translations ([[fdp-inflates-itlb-misses]]) |
| `walks_pki` ("Page-walk requests") | `mmu.walker.walks` | **requests**, including squashed and merged ones: about 4× the completed walks |
| `walks_done_pki` (and `_d_`, `_i_`) | `walker.requestOrigin_Completed::{Data,Inst}` | **completed walks**, the demand-side cost; close to `l2_shared.inserts` |

Use completed walks for statements about walk cost:
[[walk-requests-vs-completed]]. Agentic windows: 0.62 completed walks per
1000 instructions (median), mostly data walks (fmt-3901: 0.58 data, 0.09
instruction).
