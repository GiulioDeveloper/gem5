---
type: howto
status: current
updated: 2026-11-02
sources:
  - run_scripts/tasktrace/pc-trace.sh
  - analysis_scripts/tasktrace/stats_table.py
  - analysis_scripts/tasktrace/split_stall.sh
  - analysis_scripts/tasktrace/check_pc_slices.sh
  - analysis_scripts/tasktrace/compare_runs.sh
  - analysis_scripts/tasktrace/process_views.py
  - "[[2026-10-23-rubocop-15g-cache-btb-tlb]]"
tags: [long-run, pc-trace, stats, compression, workflow]
---

# Long runs: billions of detailed instructions, compacted and analysed

A **long run** is a traced detailed window of several billion instructions
(15G in [[2026-10-23-rubocop-15g-cache-btb-tlb]]) instead of the 400M of a
sweep window. It covers whole agent rounds, tool calls and their tests, so
it can be split per process and per phase. Raw, its outputs do not fit on
disk (20 GB of stats text and tens of GB of Exec trace per run); the
workflow below keeps each run under 1 GB and every step checks itself.

## 1. Launch

```sh
OUTDIR=runs/<study>/<config> O3="1 20000000 15000000000" \
    run_scripts/tasktrace/pc-trace.sh rubocop-13560 0 \
    --stats-interval-insts 200000 [config flags]
```

`pc-trace.sh` ([[pc-trace]]) restores the checkpoint with the
[[task-tracer]] on, runs settle / warm-up / detailed (`O3=`), and streams
gem5's Exec trace through a named pipe into `pc_trace.py`, which keeps
only the compact PC trace. Stats are dumped in 200K-instruction blocks
([[stats-blocks]]). Several configurations at once: start them with
`setsid nohup` and stagger the starts by a minute or two so the restores
do not ramp memory at the same time (`runs/rubocop-15G/launch.sh` is the
example).

Measured on the six 15G rubocop runs:

| | |
|---|---|
| speed | 124–176K instructions/s detailed; ~22K/s inside a guest stall |
| wall time | 30–33 h for 15G without the stall; 40 h+ with it |
| gem5 memory | grows from ~3 GB to ~8.6 GB per run (the guest touches more memory) |
| outputs per run | PC trace 0.37–0.54 GB, stats table 0.23–0.28 GB, task trace ~23 MB |

To stop a run early, send SIGTERM to the gem5 process, not to the
launcher: the launcher then closes the PC trace and converts the stats as
usual (how `normal` and `infbtbtlb` were stopped; both converted and
checked).

## 2. Compact (automatic)

The same two compactions are available to every launcher and sweep:
[[run-output-compression]].


- **Stats → `stats.tsv.zst`.** At the end of the run the launcher calls
  `stats_table.py`: the stat names once, then one row of values per block,
  zstd-compressed. It re-reads both files, compares every value and only
  then deletes `stats.txt` (`checked` in the run log; `KEEP_STATS=1` keeps
  the text too). 20–22 GB → 0.25–0.28 GB (80–83×) on the 15G runs. All the
  readers (`trace_analysis`, `window_view`, the sweep tools) take either
  form through `stats_table.dumps(run)`.
- **Exec trace → `pc_trace.zst`.** Never stored whole: one short line per
  committed instruction (the PC only after a jump), the mnemonic, and a task
  marker at every context switch, ~0.035 bytes per instruction. The format
  and its validation: [[pc-trace]].

## 3. Cut off a guest stall

Four of the six 15G rubocop runs hung at the same simulated time, about
4.6 s after the restore: the guest stops switching tasks and spins until
the run ends. The likely cause is the kernel's first RNG reseed calling a
firmware service gem5 does not provide ([[guest-trng-hvc-stall]]), but
that is **a hypothesis still to investigate**, on one checkpoint only: we
do not yet know which checkpoints hang, when, or how to prevent it.
Cutting the hang off is a workaround so the useful part of a run can be
analysed. Move the stall out of the run before analysing it:

```sh
analysis_scripts/tasktrace/split_stall.sh <run>
```

The stall is found from the data: the run went on for more than
`STALL_MIN` ticks (default 0.1 s simulated) after the task trace's last
event. Blocks that start before it stay; the rest of `intervals.csv` and
`stats.tsv.zst` go to `<run>/stall/`, and the PC trace is cut at its last
task marker. The originals are deleted only when blocks, stats rows and
PC-trace instructions add up exactly (`stall/SPLIT.txt`). A run with no
stall is left alone. It needs the stats table (and refuses while a
`stats.txt` is present, which the readers would prefer).

## 4. Check

- **PC trace against the task trace:**
  `analysis_scripts/tasktrace/check_pc_slices.sh <run>` counts the
  instructions between every two task markers and compares them with the
  tracer's count between the same switches (O3 leaves NOPs out of it).
  Every slice should match; ~10 min per 15G instructions.
- **Stats against the trace:** `trace_analysis.py` prints the mean
  difference between gem5's user-mode share and the trace's per block
  (~0.05 is normal: the trace spreads a slice's user instructions evenly).
- `pc_footprint.py` checks the instruction count at every task marker as
  it goes ([[pc-trace#Footprint, hit rates and branches]]).

## 5. Analyse

| step | command | output |
|---|---|---|
| one run | `trace_analysis.py <run>`, `window_view.py <run>` | `<run>/analysis/`: blocks, who ran when, the window page ([[trace-analysis]], [[viewers]]) |
| several configurations of one checkpoint | `compare_runs.sh OUT RUN RUN ...` | the per-run analysis of each run, a common region (the first N blocks of every run) through `sweep_summary`/`sweep_compare` in `OUT/compare/`, and the process views below |
| per process, around switches | `process_views.py RUN ... -o OUT.csv` | IPC, user/kernel split and miss rates per group and process, in four views, with a summary against the first run |
| code footprint | `pc_footprint.py <run>` | per process and thread: code size, LRU hit rates, repeat distance, branches ([[pc-trace]]) |

Every script is in `analysis_scripts/tasktrace/` and runs from the repo
root; `trace_analysis.py` streams the stats, so a 75,000-block run needs
little memory.

### Process views

`process_views.py` cuts each run at every switch and gives each slice to
the task that ran. Groups:

- **harness**: OpenCode (every thread) and the processes it starts itself
  outside tool calls (its git snapshots);
- **tools**: processes under `bash.fence-real` or `rg.fence-real`, the
  wrappers of OpenCode's tool calls;
- **driver**: the host replay driver (`run.sh`) and the Docker daemons,
  kept apart from the harness;
- **other** user processes; **kernel** threads and idle.

Four views of each: **all** (every slice whole, IPC and user/kernel split
exact from the trace), and **skip1 / skip3 / skip6**, which drop 1, 3 or 6
blocks at both ends of each run of a process (after the switch in and
before the switch out). The trimmed views show how much of a process's
cost sits next to its switches ([[switch-cost-is-around-the-switch]]). A
group row is the sum of its processes, so it trims at switches between its
own processes too.

## Pitfalls

- **Same instructions, different work.** A faster configuration gets
  further into the session in the same instruction count, so whole-region
  metrics mix the uarch effect with a change of work (on rubocop the tools'
  share grew from 3.6% to 19.5% of instructions between the slowest and
  the fastest configuration). Compare per process
  ([[comparing-configurations]]).
- **Window IPC, not mean block IPC.** Sum instructions and cycles over
  blocks ([[aggregating-metrics]]).
- The PC trace reducer's "switch ticks before their Exec tick" warning
  (1–68 per 15G run) is expected on O3 and does not affect the join: the
  switch event fires when the call into `__switch_to` commits, which can be
  before a late fetch of `__switch_to` ([[pc-trace#How the join works: by PC]]).
