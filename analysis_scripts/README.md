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
| `window_view.py <run>` + `window_view.html` | the trace and the stats blocks | `analysis/window.html`, `window.view.json` | per-block uarch metrics of a detailed window with the trace's events on the same axis. `METRICS` here defines every metric the sweep tools use |
| `sweep_summary.py <sweep> [--pdf]` + `sweep_view.html` | every run of a sweep | `<sweep>/summary/`: `sweep.csv`, `sweep.html`, violins | one row per checkpoint: window value and block-to-block variation of each metric, switch rates; SPEC against agentic |
| `sweep_compare.py A B [C ...] [--pdf]` | two or more sweeps | `B/compare-<A>/` (or `-o`): CSV, HTML, violins | the same checkpoints across configurations, paired; change against the first sweep |
| `landing_summary.py <landing run> <checkpoints>` | a `landing-all.sh` run and the checkpoints' `provenance.json` | stdout | whether each restore lands where its checkpoint label says |

The sweep scripts run `trace_analysis`, `trace_view` and `window_view` on
each finished run and `sweep_summary` (and `sweep_compare`) at the end, so
these are needed by hand only to regenerate outputs after changing a
script.
