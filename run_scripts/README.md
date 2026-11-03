<!-- LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD -->

# run_scripts: launching simulations

Wrappers around `build/ARM/gem5.opt` and the restore configs in
`configs/garfield/arm/` (`virt_run.py` for the agentic checkpoints,
`fs_run.py` for SPEC CPU 2026). Run them from the repository root. Each
writes to a fresh directory under `runs/` (gitignored). The scripts that
read finished runs are in [`analysis_scripts/`](../analysis_scripts/README.md).

Checkpoints are read from `CKPTS` (default `/home/snapshots/gem5-ckpts`):
`$CKPTS/rpoint_ckpts/agentic/` (images, kernel, bootloader, checkpoints) and
`$CKPTS/fs_ckpts/spec26/` (`ckpts/`, `restore_resources/`). A task name is
an agentic checkpoint name without the `agentic-` prefix, e.g. `gin-2121`.

Extra arguments after the positional ones go to `virt_run.py` / `fs_run.py`
unchanged (e.g. `--disable-fdp`, `--infinite-btb`, `--infinite-tlb`).

Stats compression: with `COMPRESS_STATS=1`, every launcher below (except
`o3-pair.sh`, which diffs the text, and `landing-all.sh`, which reads only
the task trace) replaces the run's `stats.txt` by the values-only table
`stats.tsv.zst` when gem5 exits, through `compress-stats.sh` (every value is
checked; `stats.txt` is kept on a mismatch, and `KEEP_STATS=1` keeps it
anyway). The sweeps pass it to every run and record it in `sweep.conf`.
`pc-trace.sh` compresses by default (`COMPRESS_STATS=0` turns it off). The
analysis scripts read either form.

PC trace: with `PC_TRACE=1`, `o3-window.sh`, `spec-window.sh` and the sweeps
also record the compact PC trace that `pc-trace.sh` records
(`pc_trace.zst`, zstd-compressed as it is written; `PC_TRACE_LEVEL` sets the
level, default 9). The setup is shared in `tasktrace/pc-trace-lib.sh`. The
whole run is traced, settle and warm-up included.

## Plain restores

| script | purpose | output |
|---|---|---|
| `run_agent.sh [args]` | detailed restore of gin-2121 cpt.0 with no tracer and no stats blocks: 10M warm-up, 50M measured. The quickest way to try a config flag | `runs/<stamp>/` |
| `run_spec.sh [bench] [inv] [simpoint] [warmup] [detailed]` | the same for one SPEC SimPoint checkpoint (default 777.zstd_r, 10M + 50M) | `runs/<stamp>-spec-<bench>-<inv>-<sp>/` |

## Traced runs (`tasktrace/`)

The wiki describes these in detail: `docs/wiki/infrastructure/`
(`running-a-traced-window.md`, `sweeps.md`, `run-and-analysis-scripts.md`).

| script | purpose | when to use |
|---|---|---|
| `atomic.sh [task] [max-insts] [args]` | atomic-only restore with the task tracer (`GEM5_OPTS` passes gem5 options, e.g. `--debug-flags=TaskTracer`) | tracer development; finding where in a task something happens before paying for O3 |
| `o3-window.sh TASK SETTLE WARMUP DETAILED INTERVAL [args]` | one agentic window: SETTLE atomic instructions, WARMUP unmeasured O3, DETAILED measured O3 in INTERVAL-instruction stats blocks, with the tracer (`OUTDIR` overrides the output directory) | studying one window; comparing two configs on one window (run it twice, the second with the flag appended) |
| `spec-window.sh BENCH SETTLE WARMUP DETAILED INTERVAL [TAG] [args]` | the same for a SPEC checkpoint | |
| `sweep.sh [BASE]` | `o3-window.sh` / `spec-window.sh` over every local checkpoint, analysis of each run, then `sweep_summary.py` (and `sweep_compare.py` against `BASELINE`). `EXTRA` adds flags to every run; resumes an interrupted `BASE` | one sweep on its own |
| `smart_sweep.sh [BASE]` | `sweep.sh` with memory-aware launching: each run starts only when there is memory for its expected peak, counting every gem5 on the host (other users' too), and runs in its own memory-capped scope so an overrun kills only that run. Peaks per task are in `tasktrace/mem_peaks.tsv` (tracked; commit it after a sweep) | several sweeps at once, or any sweep that includes the heavy tasks (docusaurus-9897, nushell-13831) |
| `o3-pair.sh [task] [warmup] [detailed]` | restores the same window twice, without and with `--task-trace`, and diffs `stats.txt`; `PAIR_ON_ARGS=` runs the plain config twice (determinism check) | after any change to the tracer, to show it does not perturb the simulation |
| `pc-trace.sh TASK MAX_INSTS [args]` | atomic restore with gem5's Exec trace streamed through a named pipe into `analysis_scripts/tasktrace/pc_trace.py`; stores only the compact PC trace, joined with the task trace | instruction footprint, branch and repeat-distance studies |
| `landing-all.sh [insts] [parallel]` | restores every local checkpoint briefly on the atomic core with the tracer and checks the first switch and KASLR slide against the checkpoint's landing label (summarized by `analysis_scripts/tasktrace/landing_summary.py`) | when checkpoints are added or regenerated, or the tracer's slide or task reading changes |

Comparing configurations: run a sweep with `EXTRA="<flags>"` and
`BASELINE=<earlier sweep>`; see `docs/wiki/infrastructure/sweeps.md`. There is no
per-feature comparison script.
