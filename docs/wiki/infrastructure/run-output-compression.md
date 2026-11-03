---
type: howto
status: current
updated: 2026-11-03
sources:
  - run_scripts/compress-stats.sh
  - run_scripts/tasktrace/pc-trace-lib.sh
  - analysis_scripts/tasktrace/stats_table.py
  - analysis_scripts/tasktrace/pc_trace.py
  - "[[stats-blocks]]"
  - "[[pc-trace]]"
  - "[[long-runs]]"
tags: [compression, stats, pc-trace, runs, workflow]
---

# Run output compression: stats table and PC trace

**What it is:** two switches that keep a run's two big outputs small, with
every value checked and every reader working unchanged.
`COMPRESS_STATS=1` replaces `stats.txt` by a values-only zstd table
(`stats.tsv.zst`, 54–83× smaller) when gem5 exits. `PC_TRACE=1` records the
committed-instruction stream as a compact zstd PC trace (`pc_trace.zst`,
~0.04 bytes per instruction) instead of gem5's Exec trace, which is never
stored. Both are environment variables, read by the launchers in
`run_scripts/` and passed down by the sweeps.

```sh
COMPRESS_STATS=1 PC_TRACE=1 run_scripts/tasktrace/o3-window.sh gin-2121 1 20000000 400000000 200000
COMPRESS_STATS=1 PC_TRACE=1 nohup run_scripts/tasktrace/smart_sweep.sh > runs/sweep.log 2>&1 &
```

## What each output becomes

| output | without | with the switch | size (source) |
|---|---|---|---|
| stats | `stats.txt`, text, one block per dump | `stats.tsv.zst`: stat names once, one row of values per dump (`COMPRESS_STATS=1`) | 637 MB → 8.5 MB on a 2,000-block sweep window (75×); 20–22 GB → 0.23–0.28 GB on the 15G rubocop runs (80–83×) ([[stats-blocks]], [[long-runs]]) |
| instruction stream | not recorded (an Exec trace would be ~15 bytes per instruction gzipped) | `pc_trace.zst`: PC only after a jump, the mnemonic, a task marker per switch (`PC_TRACE=1`) | 0.035–0.041 bytes per instruction on O3; 0.37–0.54 GB per 15G run ([[pc-trace]]) |
| task trace | `tasktrace.jsonl`, plain | unchanged | ~2.5 KB per M instructions; ~23 MB per 15G run |

## Switches, per launcher

| launcher | `COMPRESS_STATS` | `PC_TRACE` |
|---|---|---|
| `o3-window.sh`, `spec-window.sh` | off by default | off by default |
| `sweep.sh`, `smart_sweep.sh` | off by default; passed to every run and recorded in `sweep.conf` | same |
| `pc-trace.sh` | **on** by default (`COMPRESS_STATS=0` turns it off) | always (that is its purpose) |
| `run_agent.sh`, `run_spec.sh`, `atomic.sh` | off by default | not available |
| `o3-pair.sh` (diffs the stats text), `landing-all.sh` (no stats used) | ignored | not available |

Related variables: `KEEP_STATS=1` keeps `stats.txt` next to the table;
`PC_TRACE_LEVEL` sets the trace's zstd level (default 9; higher is smaller
but slower, and the reducer must keep up with gem5); `PY` selects the
interpreter (Python 3.14+ for the built-in `compression.zstd`). Every
launcher still exits with gem5's status (or the reducer's, when gem5
succeeded and the reducer failed).

## How it works

- **Stats** (`run_scripts/compress-stats.sh`, the shared end-of-run step):
  runs `stats_table.py`, which writes the table, re-reads both files, and
  deletes `stats.txt` only when every value matches; on a mismatch it keeps
  the text and says so in the run log. The full text exists on disk until
  the run ends, so the disk must hold it for the duration of the run.
  Format and readers: [[stats-blocks]] (values-only table).
- **PC trace** (`run_scripts/tasktrace/pc-trace-lib.sh`, sourced by
  `pc-trace.sh`, `o3-window.sh` and `spec-window.sh`): gem5 writes its
  Exec trace (lean flags) into a named pipe in the run directory, and
  `pc_trace.py reduce` reads it, joins it with the task trace by
  `__switch_to` passes, and writes `pc_trace.zst`. The whole run is traced,
  settle and warm-up included: gem5's debug output cannot be switched on at
  an instruction count. If gem5 dies before opening the pipe, the library
  releases the waiting reducer instead of hanging the run (or a sweep).
  Format, join and validation: [[pc-trace]].

## Converting existing runs

`runs/compress-existing.sh [TREE...]` (gitignored, in `runs/`) applies the
same `stats_table.py` step to every `stats.txt` under the given trees
(default `runs/sweep`, `runs/old-tests`, `runs/perfect-l2`,
`runs/perfect-l1i`). It is a dry run unless `APPLY=1`; `JOBS` (default 4)
conversions run in parallel at `nice 19` and idle I/O priority, and files
modified in the last `MIN_AGE` (30) minutes are skipped so a live run is
never touched. Results go to `runs/compress-existing.log` (`OK`/`FAIL` per
file). Throughput: about 4.5 GB of text per wall-clock minute with 4 jobs.

On 2026-11-03 every existing run was converted: 352 files, ~121 GB of
text → 1.8 GB of tables (73–234× per file), 0 failures, ~27 minutes;
`runs/` went from 122 GB to 9.0 GB. `stats.txt` no longer exists for any
of these runs, including the five `o3-pair` directories in
`runs/old-tests/tasktrace` (their `stats.diff` was kept).

## Reading compressed runs

- `stats_table.dumps(run)` reads `stats.txt` if present, otherwise
  `stats.tsv.zst`; `trace_analysis.py`, `window_view.py`, the sweep tools
  and `process_views.py` use it, so they work on either form.
  `compare_runs.sh` and `split_stall.sh` need the table.
- `pc_footprint.py`, `split_stall.sh` and `check_pc_slices.sh` read
  `pc_trace.zst` (only that name).
- gem5's own gzip stats (`--stats-file=stats.txt.gz`) are **not**
  supported by the readers (`stats_table.stats_path` does not look for
  them); use the table.

## Validation

- Stats table: identical outputs of `trace_analysis.py`, `window_view.py`
  and `sweep_summary.py` from either form on fmt-3901; every 15G run
  converted and checked ([[stats-blocks]], [[long-runs]]).
- `compress-stats.sh`, 2026-11-02: synthetic `stats.txt` with the switch
  off, on, with `KEEP_STATS=1` and with no stats file; a launcher still
  returns gem5's status.
- `PC_TRACE=1` on `o3-window.sh`, 2026-11-02 (gin-2121, 200K warm-up, 1M
  detailed, with `COMPRESS_STATS=1`): exit 0, 1.22M instructions in a 77 KB
  trace, stats converted and checked. That window had no switch; the join
  itself is the one validated in [[pc-trace#Validation (2026-10-23, gin-2121 cpt.0)]].
- Retro-conversion, 2026-11-03: `sweep_summary.py` on
  `runs/sweep/20261014-110051` rebuilt from the tables gives byte-identical
  `sweep.csv`, `sweep_slices.csv`, `sweep_edges.csv`,
  `sweep_processes.csv`, `sweep.view.json` and `sweep.html` to the summary
  built from the text on 2026-11-02.
- Not measured yet: the speed cost of `PC_TRACE=1` on O3 windows (on the
  atomic core tracing runs at about a third of the plain speed).
