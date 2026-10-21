---
type: howto
status: current
updated: 2026-10-21
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
| `tasktrace/landing-all.sh [insts] [parallel]` | landing check over every checkpoint (`TASKS=` limits) | new checkpoints, slide or task-reading changes |

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

The sweep scripts run the per-run tools themselves; run them by hand only
to regenerate outputs after changing a script.

matplotlib is not in the system Python on this host: `python3 -m venv
--without-pip runs/venv && pip --python runs/venv/bin/python install
matplotlib`.
