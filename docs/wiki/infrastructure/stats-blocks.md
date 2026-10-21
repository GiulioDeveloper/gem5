---
type: howto
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - configs/garfield/arm/virt_run.py
tags: [stats, intervals]
---

# Stats blocks: `--stats-interval-insts`

**What it is:** `virt_run.py` and `fs_run.py` run the detailed region in
N-instruction chunks, each followed by `m5.stats.dump(); m5.stats.reset()`,
so `stats.txt` holds one block per interval, and write `intervals.csv`
(flushed per interval) with each block's tick range and range of the
**global** instruction count, the same count the [[task-tracer]] stamps
on events. Blocks and events therefore join exactly. `0` (default) dumps
once.

- **Chunking does not change timing**: the same region with and without
  intervals has the same IPC ([[validation-checks]]).
- **Size:** with `--stats-file=stats.txt?desc=False` (drops descriptions) a
  block of this config is about 320 KB, so file size ≈ 320 KB × region /
  block size. 200K blocks over 400M instructions are the sweep default.
- **Granularity matters.** 1M blocks mix a context switch with the new
  task's cold start; at 100K the IPC drop of a block holding a process
  switch is much sharper (framework-52684: 0.28 vs 0.86 at 100K; gin: 0.62
  vs 0.91 at 1M).
- With `--tail-insts`, gem5's exit dump adds one extra block for the tail,
  with no `intervals.csv` row; the tools ignore it.
- gem5 leaves a stat out of a block when it stayed at zero;
  `trace_analysis.load_blocks` treats a missing stat as 0.
- Live-value stats (e.g. `InfiniteBTB` `entries`) are not reset between
  blocks; counters are ([[infinite-btb-model]]).

How to combine blocks into window values: [[aggregating-metrics]].
