# cpu-o3: Add top-down accounting from gem5 PR #2392

- **Date:** 2026-10-13 15:07   ·   **Branch:** topdown-pr2392

## Goal
Bring upstream gem5 PR #2392 (Top-Down Methodology for O3, by Osman
Yaşar and David Schall; open, not merged upstream) into the fork, so the
O3 core reports Level 1-3 top-down slot breakdowns.

## Summary of changes
- The PR's two commits squashed onto gfdev with merge conflicts
  resolved: both sides' stats kept; the fork's `fetch.status` vector kept
  instead of the PR's per-reason fetch cycle scalars; the fork's
  `issuedInstType` name kept.
- Adds `TopDownStats` (tdm.cc/hh) and the counters it reads: rename fetch,
  refill and store-stall bubbles, IQ executed-per-cycle and load-stall
  cycles by miss level, commit's committed-instruction count.
- Does not build on its own in this fork and `tdaCycles` is never
  incremented per cycle; both are fixed by the next commit.

## Files changed
- `src/cpu/o3/BaseO3CPU.py` — subtractIdleCycles parameter
- `src/cpu/o3/SConscript` — builds tdm.cc
- `src/cpu/o3/commit.cc` — committedInst counter
- `src/cpu/o3/commit.hh` — committedInst counter
- `src/cpu/o3/cpu.cc` — tdaCycles stat, topDownStats member, idle-cycle hook into rename
- `src/cpu/o3/cpu.hh` — tdaCycles stat, topDownStats member, idle-cycle hook into rename
- `src/cpu/o3/decode.hh` — accessors used by the top-down stats
- `src/cpu/o3/dyn_inst.cc` — PR comments out the instcount assert (restored in the next commit)
- `src/cpu/o3/fetch.cc` — fetchBubbles/fetchBubblesMax counters
- `src/cpu/o3/fetch.hh` — fetchBubbles/fetchBubblesMax counters
- `src/cpu/o3/fu_pool.hh` — accessors used by the top-down stats
- `src/cpu/o3/iew.hh` — accessors used by the top-down stats
- `src/cpu/o3/inst_queue.cc` — executed-per-cycle counts, load-stall cycles by cache miss level, getStats()
- `src/cpu/o3/inst_queue.hh` — executed-per-cycle counts, load-stall cycles by cache miss level, getStats()
- `src/cpu/o3/lsq.cc` — anyCacheLevelMisses() over in-flight loads
- `src/cpu/o3/lsq.hh` — anyCacheLevelMisses() over in-flight loads
- `src/cpu/o3/rename.cc` — fetch/refill bubble and store-stall counters, refill window after squashes
- `src/cpu/o3/rename.hh` — fetch/refill bubble and store-stall counters, refill window after squashes
- `src/cpu/o3/tdm.cc` — new: TopDownStats groups and L1/L2/L3 formulas
- `src/cpu/o3/tdm.hh` — new: TopDownStats groups and L1/L2/L3 formulas
