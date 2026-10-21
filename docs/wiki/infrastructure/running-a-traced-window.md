---
type: howto
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
tags: [howto, tracer, o3]
---

# How to run a traced window

Prerequisites: `scons build/ARM/gem5.opt -j$(nproc)` ([[building]]), `gdb`
on the host (an x86 gdb reads the aarch64 vmlinux), and the agentic
`COMMON` arguments from [[checkpoints]]. `TASK` is a checkpoint name without
`agentic-`; `CPT=$AGENTIC/checkpoints/agentic-$TASK/cpt.0`.

## 1. Event trace only, atomic (fast)

```sh
./build/ARM/gem5.opt --outdir=runs/trace-$TASK configs/garfield/arm/virt_run.py \
  --restore-dir $CPT $COMMON --atomic-only --atomic-max-insts 2000000000 --task-trace
```

or `run_scripts/tasktrace/atomic.sh $TASK 2000000000`. About 1.7 MIPS.

## 2. Detailed O3 window with stats blocks

```sh
./build/ARM/gem5.opt --outdir=runs/o3-$TASK "--stats-file=stats.txt?desc=False" \
  configs/garfield/arm/virt_run.py --restore-dir $CPT $COMMON \
  --settle-insts <S> --warmup-insts 20000000 \
  --detailed-insts <N> --stats-interval-insts 200000 \
  --tail-insts 100000000 --task-trace
```

or `run_scripts/tasktrace/o3-window.sh $TASK <S> 20000000 <N> 200000`. About
95–200 KIPS. SPEC: `run_scripts/tasktrace/spec-window.sh 714.cpython_r 1
20000000 200000000 200000` (no OpenCode, so the trace is the schedule only).

## 3. Analyse and view

```sh
python3 analysis_scripts/tasktrace/trace_analysis.py runs/o3-$TASK
python3 analysis_scripts/tasktrace/trace_view.py runs/o3-$TASK
python3 analysis_scripts/tasktrace/window_view.py runs/o3-$TASK
```

([[trace-analysis]], [[viewers]]).

## Placing the window on an event

1. Run step 1 long enough to cover the event.
2. Read its instruction count from `analysis/tools.csv` or `processes.csv`.
3. Restore with `--settle-insts` **hundreds of millions** before it and a
   region long enough for the whole event, plus `--tail-insts`.
4. Locate the event again **in the O3 trace**: events move between atomic
   and O3 runs ([[window-placement]]).

To cover a whole round, run atomic until the next `RPOINT_REPLAY_ROUND`
marker appears in `board.terminal`, then SIGINT (the trace is flushed).
