# cpu-o3: Attribute MRN loads to serving memory level

- **Date:** 2026-07-27 23:41   ·   **Branch:** rbdev

## Goal
Ground the criticality question empirically: which memory level serves the
loads MRN forwards, and what does a wrong forward cost as a function of that
level? This is the measurement basis for the planned flush-weighted ledger
gate (penalty proportional to realized flush cost).

## Summary of changes
Per-load service-level attribution riding gem5's existing Request::depth
(incremented by every classic cache on a miss): 0 = L1D hit, 1 = L2 hit,
>= 2 = memory; loads fully satisfied by store-to-load forwarding are stamped
STLF at the forward site (they never reach the caches). Level is stored on
the DynInst at writeback and consumed at the MRN verify sites. Four stats:
loadLevelAll (every completed load, the reference distribution),
vfConsumedLevelCorrect/Wrong (consumed forwards by verify outcome), and
vfWrongFlushedByLevel (flushed instructions per wrong, by level; sums to
squashedInsts by construction). Documented caveat: an MSHR-coalesced
secondary miss keeps its own descent depth, so secondaries behind a memory
fetch count as L2.

Verified: stats-only, bit-identical on 750.sealcrypto_r.0.2 (3,483 shared
stats vs the th14 reference). 14-checkpoint probe findings: correct forwards
are 97.5% STLF+L1D (Rahul's stack-load hypothesis confirmed; the win is
scheduling, not latency); wrong forwards are 4.5x enriched beyond L1D; flush
cost scales 61/190/298 insts per wrong for L1D/L2/mem (1 : 3.1 : 4.9);
sqlite.2.1's wrongs are 100% L1D at 53 insts each (cheapest population --
the ledger gate should not reproduce its -10.6% cliff).

## Files changed
- `src/cpu/o3/dyn_inst.hh` — MemSrcLevel enum + _memSrcLevel field and
  accessors on DynInst.
- `src/cpu/o3/lsq_unit.cc` — STLF stamp at the full-forward site; depth->
  level derivation + loadLevelAll at writeback; consumed-level and
  wrong-flush notes at the value and alias verify sites.
- `src/cpu/o3/mem_rename_predictor.hh` — noteLoadLevel /
  vfNoteConsumedLevel / vfNoteWrongFlushed wrappers + vector stat decls.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — ADD_STATs, init(5),
  stlf/l1d/l2/mem/unknown subnames.
