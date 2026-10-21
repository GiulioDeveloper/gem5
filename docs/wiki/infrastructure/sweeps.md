---
type: howto
status: current
updated: 2026-10-21
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

## Comparisons: `sweep_compare.py`

```sh
sweep_compare.py A B [C ...] [--labels ...] [-o OUT] [--pdf]
```

Pairs runs by suite and checkpoint (A is the baseline). Two sweeps write
`B/compare-<A>/compare.{csv,html}` (A, B, B − A, B / A − 1 per metric and
checkpoint, violins of change or difference, median IPC change per suite).
Up to 8 write `compare_multi.{csv,html}` (default `<A>/compare-multi/`).
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
