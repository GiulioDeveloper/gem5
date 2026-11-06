<!-- LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD -->

# analysis_scripts: reading finished runs

Host-side Python (standard library only; matplotlib only for the optional
`--pdf` figures, e.g. `runs/venv/bin/python`). They read the run
directories that [`run_scripts/`](../run_scripts/README.md) writes and never
run gem5. Run them from the repository root. The scripts in a folder import
each other from that folder, so keep them together.

## Task traces and stats blocks (`tasktrace/`)

Details, file formats and caveats are in the wiki:
`docs/wiki/infrastructure/` (`trace-analysis.md`, `viewers.md`,
`sweeps.md`) and `docs/wiki/methodology/validation-checks.md`.

| script | reads | writes | purpose |
|---|---|---|---|
| `trace_analysis.py <run> [--window K]` | `tasktrace.jsonl`, `intervals.csv`, `stats.txt` | `<run>/analysis/`: `summary.md` and CSVs (processes, switches, tools, blocks, ...) | what ran: processes, launch trees, context switches by kind and cause, tool calls, per-block stats joined to trace events. Also the library the other scripts import (`load_events`, `Tree`, ...) |
| `trace_view.py <run>` + `trace_view.html` | the trace | `analysis/schedule.html` | interactive schedule: which task ran when |
| `window_view.py <run>` + `window_view.html` | the trace and the stats blocks | `analysis/window.html`, `window.view.json` | per-block uarch metrics of a detailed window with the trace's events on the same axis, and the stacked top-down breakdown (Level 1-3) when the build has it. `METRICS` here defines every metric the sweep tools use; `topdown()` recomputes the top-down shares from gem5's counters |
| `sweep_summary.py <sweep> [--pdf]` | every run of a sweep | `<sweep>/summary/`: `sweep.csv`, `sweep.view.json`, violins | one row per checkpoint: window value and block-to-block variation of each metric, switch rates; SPEC against agentic. Agentic windows are also split into slice categories (harness, tools, harness git, replay infra, other): time shares and per-category values (`sweep_slices.csv`), the same per process (`sweep_processes.csv`); switch frequency and scheduler share; an edge-block setting (drop 1, 3 or 5 stats blocks at each end of every thread run, `sweep_edges.csv`) for the indirect cost of switching, a slice switch on the page |
| `sweep_compare.py A B [C ...] [--pdf]` + `compare_view.html` | two to eight sweeps | `B/compare-<A>/` (two) or `A/compare-multi/` (more), or `-o`: `compare.html`, CSVs, violins | the same checkpoints across configurations, paired against the first sweep. The page leads with the aggregate per suite: every metric in one table (geometric means of A's values and of the others' ratios to A; top-down shares as plain means and differences in percentage points; `compare_geomean.csv`) and the top-down breakdown as a stacked bar per sweep; collapsed below, one metric or the breakdown per checkpoint, and the violins. Slice categories and edge settings apply to every view (`compare_slices.csv`, `compare_geomean_slices.csv`, `compare_geomean_edges.csv`) |
| `pc_trace.py reduce <exec trace> -o <run>/pc_trace.zst --tasktrace <run>/tasktrace.jsonl` (and `verify`) | a gem5 Exec trace (file, pipe or stdin) and the task trace | `pc_trace.zst` | one line per committed instruction (PC only when not PC+4, plus the mnemonic) with task markers; `read_pc_trace()` reads it back. Python 3.14+ |
| `pc_footprint.py <run> [-o OUT] [--limit N]` (+ `pc_footprint.cc`, built on first use with g++) | `pc_trace.zst`, `tasktrace.jsonl`, the guest vmlinux | `<run>/footprint/`: `summary.md`, `report.html`, `footprint.csv`, `instances.csv`, `threads.csv`, `groups.tsv`, `hist.tsv`, `instances.tsv`, `threads.tsv`, `thread_hist.tsv` | per process name (kernel separate), per PID and per thread: distinct instructions, lines and pages, footprint vs L1I/L2 sizes, LRU stack-distance misses (private and shared), repeat distance per instruction and per line (threads), distinct branches by type and taken. ~45 min and 8 GB per 15G instructions |
| `pc_footprint_report.py <run>/footprint [-o HTML]` | `threads.csv`, `thread_hist.tsv` | `report.html` | the per-thread page (rows of small charts, miss ratio curves, sortable table); `pc_footprint.py` writes it at the end of every pass |
| `stats_table.py <run>/stats.txt [--keep]` | `stats.txt` | `stats.tsv.zst` | the stats dumps as a values-only table (names once, a row per dump), checked, then `stats.txt` deleted; 50–75× smaller. `stats_table.dumps(run)` reads either form, and the other scripts use it |
| `split_stall.sh <run>` | a run with `stats.tsv.zst` (and `pc_trace.zst`) | `<run>/stall/`, `stall/SPLIT.txt` | moves a trailing guest stall (no tracer event for `STALL_MIN` ticks before the end) out of the run; deletes the originals only when blocks, rows and instructions add up |
| `check_pc_slices.sh <run>` | `pc_trace.zst`, `tasktrace.jsonl` | stdout | instructions between task markers against the tracer's count between the same switches; exit 1 on a mismatch |
| `compare_runs.sh OUT RUN RUN ...` | long runs of one checkpoint under different configurations | `OUT/`: common-region sweep layout, `compare/`, `process_views.csv` | per-run analysis, the first N blocks of every run through `sweep_summary`/`sweep_compare`, and `process_views.py`; first run = baseline |
| `process_views.py RUN ... -o OUT.csv [--labels]` | `analysis/blocks.csv` (from `trace_analysis.py`), `tasktrace.jsonl`, `config.ini` | `OUT.csv`, IPC summary on stdout | per group (harness, tools, replay driver, other, kernel) and process: time, instruction share, user/kernel split, IPC, MPKIs, over whole slices and with 1/3/6 blocks trimmed at each switch |
| `landing_summary.py <landing run> <checkpoints>` | a `landing-all.sh` run and the checkpoints' `provenance.json` | stdout | whether each restore lands where its checkpoint label says |

The sweep scripts run `trace_analysis`, `trace_view` and `window_view` on
each finished run and `sweep_summary` (and `sweep_compare`) at the end, so
these are needed by hand only to regenerate outputs after changing a
script.
