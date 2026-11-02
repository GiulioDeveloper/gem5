---
type: pitfall
status: current
updated: 2026-10-28
sources:
  - src/cpu/o3/cpu.cc
  - analysis_scripts/tasktrace/window_view.py
  - runs/rubocop-15G/normal/stats.tsv.zst
  - runs/sweep/20261014-110051
tags: [stats, cycles, latency, window-view, sweeps]
---

# O3 `numCycles` leaves out WFI time

**The trap:** while the guest sits in WFI, the O3 core is suspended and the
cycles go to `quiesceCycles`, not to `numCycles` (`CPU::activateContext`).
`idleCycles` (no activity but not suspended) *are* in `numCycles`. So
`numCycles` × clock period equals a stats block's ticks only when the block
has no WFI; otherwise ticks / period = `numCycles` + `quiesceCycles`.

**What it breaks:** `window_view.py`'s `miss_latency` converts a latency in
ticks to cycles with `cycles / ticks` of the block, i.e. `numCycles /
ticks`, so in a block with WFI the L1I and L1D miss latencies come out
too small by (`numCycles` + `quiesceCycles`) / `numCycles`. Rubocop 15G
`normal`, block 5052: 0.7M busy cycles, 88M quiesced, L1I miss latency 1.04
cycles against ~200 next to it. The window value is scaled the same way
over the whole window: in the baseline sweep, axios-5892 and bat-2835
(quiesce 2.8× and 2.4× their busy cycles, in ~20 of 2,000 blocks) show L1D
miss latency 31 and 33 cycles against 65–204 for the other agentic
windows ([[2026-10-14-baseline-sweep]]). Sweep summaries reuse
`block_metrics`, so every sweep page and comparison has the same error.

**Not broken, but a definition:** IPC and the per-cycle metrics divide by
`numCycles`, so they describe the core while it runs, not wall time. In
rubocop 15G `normal` 5 of 60,136 blocks hold WFI, 1.35% of the ticks.

**Fix:** convert latencies with the core clock period (`config.ini`, as
`process_views.py` does), not with `numCycles / ticks`. Not applied yet
(2026-10-28).
