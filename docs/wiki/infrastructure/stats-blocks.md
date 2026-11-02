---
type: howto
status: current
updated: 2026-10-28
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

- **Checked end to end** (rubocop 15G `normal`, 2026-10-28): every
  block's `simInsts` and `numInstsNotNOP` equal its `intervals.csv`
  instruction range, `simTicks` its tick range, and a recount of the PC
  trace gives the same instructions per block. The counts leave out NOPs
  (`commitStats0.numInsts` and `numUserInsts` include them).
- **`numCycles` leaves out WFI time**, so ticks / period ≠ `numCycles` in
  a block with WFI ([[numcycles-excludes-wfi]]).
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

## Values-only table: `stats.tsv.zst`

`analysis_scripts/tasktrace/stats_table.py <run>/stats.txt` rewrites the
dumps as a TSV with the stat names once (header row) and one row of values
per dump, compressed with zstd. A stat a dump leaves out is written as 0;
the percentage columns of distributions are dropped (they follow from the
counts). It checks every value against the text file and then deletes
`stats.txt` (`--keep` to keep it). `stats_table.dumps(run)` reads either
form, and `trace_analysis.py`, `window_view.py` and the sweep tools use it,
so they work unchanged on converted runs.

| run | `stats.txt` (no descriptions) | `stats.tsv.zst` |
|---|---|---|
| fmt-3901 sweep window, 2,000 blocks, 4,618 stats | 637 MB | **8.5 MB** (75×), converted in 22 s, 110 MB of memory |
| rubocop smoke test, 20 blocks | 6.6 MB | 0.12 MB (54×) |

Checked on fmt-3901: `trace_analysis.py`, `window_view.py` and
`sweep_summary.py` produce identical outputs from either form (apart from
the run path). `pc-trace.sh` converts at the end of every run.

How to combine blocks into window values: [[aggregating-metrics]].
