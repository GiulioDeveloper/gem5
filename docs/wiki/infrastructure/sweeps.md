---
type: howto
status: current
updated: 2026-10-30
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - run_scripts/tasktrace/sweep.sh
  - run_scripts/tasktrace/smart_sweep.sh
tags: [sweep, comparison, methodology]
---

# Sweeps: every checkpoint, one configuration

**What it is:** `run_scripts/tasktrace/sweep.sh [BASE]` runs one detailed
window per local checkpoint, every SPEC benchmark (`spec-window.sh`, 200M
detailed) and every agentic task (`o3-window.sh`, 400M), each after 1
atomic instruction and 20M of O3 warm-up, in 200K-instruction
[[stats-blocks]] with the [[task-tracer]], into
`runs/sweep/<stamp>/{spec,agentic}/<name>/`. Each finished run is analysed
by [[trace-analysis]] and the [[viewers]] and marked `done` (or `failed`
with its block count). `progress.log` lists finished runs, `sweep.conf`
the parameters, flags and commit. Rerunning with the same `BASE` resumes.

```sh
nohup run_scripts/tasktrace/smart_sweep.sh > runs/sweep.log 2>&1 &
```

Environment: `PAR` (runs in parallel), `SETTLE`, `WARM`, `IVL`, `SPEC_DET`,
`AGENTIC_DET`, `ONLY="<name> ..."`, `PY` (an interpreter with matplotlib for
PDFs, e.g. `runs/venv/bin/python`), `EXTRA` (flags for every run),
`BASELINE` (a sweep to compare against at the end).

## Use `smart_sweep.sh`

Same arguments and outputs as `sweep.sh`, with memory-aware launching. A
run holds 2.5–22 GB, and unguarded parallel sweeps got the whole terminal
scope OOM-killed ([[sweep-memory-exhaustion]]). Each launch, under a lock
shared by all smart sweeps (`LOCK`): wait until
`MemAvailable − (memory still to come from running runs) ≥ need +
RESERVE_GB` (default 8), start, register in `STATE`, hold the lock
`STAGGER` s (default 60). *need* = the task's measured peak RSS +15% +0.5 GB
from `PEAKS` (`runs/sweep/mem_peaks.tsv`, updated by every run from gem5's
`VmHWM`), or 2 GB + 6× the compressed `*.pmem` size for a task never
measured. Launches are logged in `BASE/launch.log`.

## Summaries: `sweep_summary.py`

Runs at the end of a sweep, or by hand on any set of window runs. Per run,
over the window: each metric's **window value** from summed stats, its
**coefficient of variation** over blocks, and context-switch counts, rates
and CVs by kind. Writes `summary/sweep.csv`, `summary/sweep.html` (a violin
per suite per metric, value or CV, linear or log, linked hover) and with
matplotlib `violins*.pdf/png`. `--skip-insts N` leaves out each window's
first N instructions without re-simulating ([[warmup-and-skip]]); write
such summaries elsewhere with `-o`.

**Slice categories (agentic).** Each agentic window is also split by who
runs (2026-10-29): it is cut at every context switch, and each slice goes
to the category of the task switched in.
- **Harness:** OpenCode itself.
- **Tools:** processes under the bash and rg tool wrappers.
- **Harness git:** processes OpenCode starts outside tool calls, which are
  its git snapshots.
- **Replay infra:** the `run.sh` tree and the Docker daemons.
- **Other:** other user processes, kernel threads and idle.

The groups are those of `process_views.py` ([[long-runs#Process views]]),
with git split out and the kernel folded into "other".

Per category, the summary records the share of the window's simulated time
and of its instructions, and every metric over that category's slices.
The slices are summed per process (tgid) first, and the processes are then
summed per category (2026-10-30). A category's value is therefore its
processes' values averaged with each metric's own denominator as the
weight: instructions for MPKI, cycles for IPC and stall fractions. Every
process is kept.
Cycles are the slices' ticks over the clock period, so IPC is exact. Event
counts are an estimate: they're shared out from the 200K-instruction blocks
by instruction overlap. A short slice therefore partly inherits its block's
other slices' events, and stall cycles are split by instructions, not
time. Idle WFI time
counts in "other" ([[numcycles-excludes-wfi]]). A category with under 1M
instructions in a window has shares but no values.

The page opens with violins of each category's time share (or instruction
share) and has a slice switch for every panel and table. SPEC always shows
the whole window. `summary/sweep_slices.csv` has one row per agentic run
and category, and `summary/sweep_processes.csv` one row per agentic run and
process: category, tgid, name, shares, instructions and every metric. The
pages show categories only. Whole-window values are unchanged by the split: checked
against the previous summary, all 53 rows are identical.

**Scheduling metrics** (2026-10-30), from the switch events:
- **Switch frequency:** switches per millisecond of simulated time, in kHz.
- **Time between switches:** the mean, in µs.
- **Scheduler instructions:** Σ `sched_insts` ÷ instructions. This is the
  direct cost from `__schedule` to `__switch_to` only
  ([[task-tracer]]), without the switch's tail or the trap that led to it.

Per category, frequency and gap use the category's own time; for frequency
that's switches into the category, which makes the gap its mean slice
length. Scheduler instructions count for the category switched *out of*,
whose context they run in.

**Edge blocks** (2026-10-30), for the indirect cost of a switch:
- At setting k = 1, 3 or 5, every block within k − 1 of a block holding a
  switch is dropped. That's the first and last k blocks of every thread
  run. Every metric is then recomputed over the rest: whole window,
  categories and processes.
- A kept block holds no switch, so it belongs whole to one slice, and the
  category values at k ≥ 1 involve no prorating.
- Switch metrics and time shares stay whole-window.
- The pages have a 0/1/3/5 switch and say how much of the instructions
  each setting keeps. `summary/sweep_edges.csv` has every run, setting and
  category; `sweep_processes.csv` has an `edge_blocks` column.
- In the 27 baseline agentic windows, k = 1, 3, 5 keep 72–95%, 54–88% and
  42–84% of the instructions.
- The difference from k = 0 is not purely the switch's cold-start cost.
  The dropped stretches are also the switch-heavy phases (docker CLI
  ping-pong, short tool processes), so a work-mix difference rides along.

## Comparisons: `sweep_compare.py`

```sh
sweep_compare.py A B [C ...] [--labels ...] [-o OUT] [--pdf]
```

Pairs runs by suite and checkpoint (A is the baseline). Two sweeps write
`B/compare-<A>/compare.{csv,html}` (A, B, B − A, B / A − 1 per metric and
checkpoint, violins of change or difference, median IPC change per suite).
Up to 8 write `compare_multi.{csv,html}` (default `<A>/compare-multi/`):
violins of the values, the ratio to A (×) or the difference from A, and,
per suite, a table of geometric means (also `compare_multi_geomean.csv`):
A's window values, and each other sweep's per-checkpoint ratio to A (for
IPC, the speedup), shown on the page as a change (ratio − 1: 1.075× is
+7.5%) and kept as ratios in the CSV. A checkpoint with a zero in either sweep has no ratio
and is left out of that mean (counted on the page). That understates a
drop to zero. A mean over fewer than half the checkpoints is left empty
(for example SPEC switch rates, zero in most windows).
With slice categories in the summaries, the comparison pages have the
same slice switch and open with the time shares per sweep. The geometric
means follow the selected category, and `compare_multi_slices.csv` and
`compare_multi_geomean_slices.csv` hold the per-category values and means. A category's geometric means are over the checkpoints where it ran in the baseline (at least 1M instructions), n in the table.
With edge settings in the summaries, every view and geometric mean is also
available at each setting, and `compare_multi_geomean_edges.csv` has the
means at k = 0, 1, 3, 5, per suite and per category. The geometric-mean table shows one suite at a time (an Agentic/SPEC
switch); the violins show both. A category with under 1M kept instructions
in a window has no value. So at high k, a category that runs only in short
bursts can drop out of a checkpoint (json-4237's harness at k = 3 and 5).

Summaries written before 2026-10-29 have no categories; rerun
`sweep_summary.py` first. `runs/sweep/resummarise-slices.sh` does this for
the limit-study sweeps.
Accepts sweep directories or summary directories. Mismatched window
settings, missing checkpoints and unequal windows are listed on the page.

Configuration sweeps:

```sh
for v in "infbtb:--infinite-btb" "inftlb:--infinite-tlb"; do
  PAR=4 EXTRA="${v#*:}" BASELINE=runs/sweep/<fdp> \
    nohup run_scripts/tasktrace/smart_sweep.sh runs/sweep/<stamp>-${v%%:*} \
    > runs/sweep/<stamp>-${v%%:*}.log 2>&1 < /dev/null &
done
```

Resuming a sweep with different `EXTRA` is refused. How to read the
comparison: [[comparing-configurations]].

## Known sweeps

| sweep | what | page |
|---|---|---|
| `runs/sweep/20261014-110051` | baseline (FDP on) | [[2026-10-14-baseline-sweep]] |
| `runs/sweep/20261014-154546-nofdp` | `--disable-fdp` | [[2026-10-14-fdp-off-sweep]] |
| `runs/sweep/20261016-172546-{infbtb,inftlb,infbtb-inftlb}` | limit studies | [[2026-10-16-btb-tlb-limit-study]] |
| `runs/sweep/20261019-compare-5way/` | five-way comparison | same |
| `runs/sweep/20261020-skip100M/` | the five re-summarised skipping 100M | same |
