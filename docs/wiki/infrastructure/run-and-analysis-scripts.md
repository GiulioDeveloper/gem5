---
type: howto
status: current
updated: 2026-11-02
sources:
  - run_scripts/README.md
  - analysis_scripts/README.md
tags: [scripts, runs]
---

# Run and analysis scripts

Two tracked folders, mirrored: `run_scripts/` launches gem5 and writes a
fresh directory under `runs/` (gitignored); `analysis_scripts/` reads
finished runs and never runs gem5 (host Python, stdlib only; matplotlib only
for `--pdf`). Run everything from the repo root. Checkpoint root from
`CKPTS` ([[checkpoints]]). A task name is a checkpoint name without
`agentic-`. Extra arguments after the positional ones go to `virt_run.py`
/ `fs_run.py` unchanged. Each folder's `README.md` is the short catalog;
this page is the reference.

## Launchers (`run_scripts/`)

| script | purpose | when |
|---|---|---|
| `run_agent.sh [args]` | gin-2121 cpt.0, 10M warm-up + 50M, no tracer | quickest way to try a config flag |
| `run_spec.sh [bench] [inv] [simpoint] [warmup] [detailed]` | same for one SPEC checkpoint (default 777.zstd_r) | |
| `tasktrace/atomic.sh [task] [max-insts] [args]` | atomic-only traced restore (`GEM5_OPTS` for gem5 options) | tracer work; locating events cheaply |
| `tasktrace/o3-window.sh TASK SETTLE WARMUP DETAILED INTERVAL [args]` | one traced agentic window in stats blocks (`OUTDIR` overrides) | one window; two configs on one window |
| `tasktrace/spec-window.sh BENCH SETTLE WARMUP DETAILED INTERVAL [TAG] [args]` | same for SPEC | |
| `tasktrace/sweep.sh`, `tasktrace/smart_sweep.sh` | every checkpoint ([[sweeps]]) | one config across the suites (prefer smart) |
| `tasktrace/o3-pair.sh [task] [warmup] [detailed]` | same window without and with `--task-trace`, diff `stats.txt`; `PAIR_ON_ARGS=` for a determinism check | after any tracer change |
| `tasktrace/pc-trace.sh TASK MAX_INSTS [args]` | atomic restore (or an O3 window with `O3=`) streaming the Exec trace into `pc_trace.py`, storing only the compact PC trace; converts the stats to a table at the end | footprint, branch and repeat-distance studies ([[pc-trace]]); long runs ([[long-runs]]) |
| `tasktrace/landing-all.sh [insts] [parallel]` | landing check over every checkpoint (`TASKS=` limits) | new checkpoints, slide or task-reading changes |

`compress-stats.sh OUTDIR` is the shared end-of-run step: with
`COMPRESS_STATS=1` it replaces `stats.txt` by the checked `stats.tsv.zst`
table ([[stats-blocks]]; `KEEP_STATS=1` keeps the text too). `run_agent.sh`,
`run_spec.sh`, `atomic.sh`, `o3-window.sh`, `spec-window.sh` and the sweeps
honour it; `pc-trace.sh` has it on by default (`COMPRESS_STATS=0` turns it
off); `o3-pair.sh` (diffs the text) and `landing-all.sh` (no stats used)
ignore it. Each launcher still exits with gem5's status. Overview of both
switches: [[run-output-compression]].

`PC_TRACE=1` makes `o3-window.sh`, `spec-window.sh` and the sweeps also
record the compact PC trace ([[pc-trace]]) through
`tasktrace/pc-trace-lib.sh`, the pipe-and-reducer setup `pc-trace.sh` uses.

How to choose the window numbers: [[running-a-traced-window]].

## Readers (`analysis_scripts/tasktrace/`)

They import each other from that folder, so keep them together.

| script | page |
|---|---|
| `trace_analysis.py <run>` | [[trace-analysis]] |
| `trace_view.py <run>` + `trace_view.html` | [[viewers]] |
| `window_view.py <run>` + `window_view.html` | [[viewers]] |
| `sweep_summary.py <sweep>` + `sweep_view.html`, `sweep_compare.py A B ...` | [[sweeps]] |
| `landing_summary.py <landing run> <checkpoints>` | [[validation-checks]] |
| `pc_trace.py reduce/verify` | [[pc-trace]] |
| `pc_footprint.py <run>` | instruction footprint, LRU hit rates, repeat distance and branches per process, PID and thread from a PC trace, plus the per-thread `report.html` ([[pc-trace#Footprint, hit rates and branches]]) |
| `pc_footprint_report.py <run>/footprint` | rebuilds the per-thread `report.html` from an existing output |
| `stats_table.py <run>/stats.txt` | [[stats-blocks]] |
| `split_stall.sh <run>`, `check_pc_slices.sh <run>` | [[long-runs]] |
| `compare_runs.sh OUT RUN RUN ...`, `process_views.py RUN ... -o OUT.csv` | [[long-runs]] |

The sweep scripts run the per-run tools themselves; run them by hand only
to regenerate outputs after changing a script.

matplotlib is not in the system Python on this host: `python3 -m venv
--without-pip runs/venv && pip --python runs/venv/bin/python install
matplotlib`.
