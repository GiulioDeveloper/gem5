---
type: meta
status: current
updated: 2026-10-21
---

# Log

Append-only timeline of the wiki: ingests, experiments, queries, lint
passes, publishes, restructures. Newest last. Format: [[SCHEMA#log.md format]].

## [2026-10-21] restructure | Pass 1: knowledge base scaffold

Decided with the user: the knowledge moves to an LLM-maintained wiki
([[raw/llm-wiki]]). The current project is CPU architecture for agentic
workloads; Garfield is kept as a reference.

- Moved `docs/{research-log,garfield,superpowers,agentic,commit-notes}` to
  `docs/legacy-log/` (frozen, see [[legacy-log/README]]). Updated the path
  references in `src/`, `configs/`, the READMEs and the skills.
- Created `docs/raw/` (immutable sources) and the wiki: [[SCHEMA]],
  [[index]], this log, [[publish]], stubs for [[overview]] and [[questions]].
- Moved the gem5 technical material out of `CLAUDE.md` into `gem5/` pages
  ([[gem5-overview]] and nine others). The Anaconda build section, dropped
  from CLAUDE.md in a5b74be687, was restored from 99aeb0d7f6 into
  [[building]].
- CLAUDE.md is now a short project summary plus how to use the wiki.
- Commit notes are discontinued: commit messages and this log are the
  record. The `git-commit` and `git-pull` skills were updated to match.
- Added `docs/tools/wiki_lint.py`.
- Publish target: HTML artifacts, registered in [[publish]].

## [2026-10-21] ingest | Pass 2: the agentic material

Ingested the agentic legacy notebooks, the tracing guide, the
infinite-BTB/TLB design notes and the configs. Added a raw snapshot of the
checkpoint archive's README
([[raw/external/2026-10-21-agentic-checkpoints-README]]).

- **Workloads:** [[agentic-suite]], [[spec-cpu-2026]], [[opencode-harness]].
- **Hardware:** [[neoverse-v2]] (from the config file, which is
  authoritative), [[decoupled-front-end]], [[btb]], [[tlb-hierarchy]],
  [[infinite-btb-model]], [[infinite-l2-tlb]].
- **Infrastructure** (the tracing guide split up): [[checkpoints]],
  [[task-tracer]], [[trace-format]], [[trace-analysis]], [[stats-blocks]],
  [[viewers]], [[sweeps]], [[run-and-analysis-scripts]],
  [[running-a-traced-window]].
- **Experiments:** [[2026-10-08-tool-call-windows]],
  [[2026-10-14-event-windows]], [[2026-10-14-baseline-sweep]],
  [[2026-10-14-fdp-off-sweep]], [[2026-10-16-btb-tlb-limit-study]].
- **Findings:** [[agentic-front-end-bound]], [[btb-tlb-limits]],
  [[fdp-value]], [[agentic-ipc-variability]],
  [[switch-cost-is-around-the-switch]], [[tool-call-runup-is-cold]] (draft).
- **Methodology:** [[window-placement]], [[warmup-and-skip]],
  [[aggregating-metrics]], [[comparing-configurations]],
  [[validation-checks]], [[instruction-counts]],
  [[context-switch-classification]].
- **Pitfalls:** ten pages, from [[l2-tlb-disconnected]] to
  [[gem5-tracing-under-kaslr]].
- Wrote [[overview]] (the current thesis) and [[questions]].
- Conflicts flagged: the SPEC suite size against Garfield
  ([[spec-cpu-2026]]), and `window_view.py`'s BTB-miss row ([[viewers]]).
  The ROB size is 320, from the config ([[neoverse-v2]]).
- Repointed the code comments and help text (`infinite_btb.hh`,
  `BranchPredictor.py`, `sim_opts.py`, `neoverse_v2.py`, `smart_sweep.sh`)
  and the `run_scripts` and `analysis_scripts` READMEs to wiki pages.
- [[building]]: replaced the restored Anaconda section with a short note
  (the user said it is no longer an issue).

## [2026-10-21] restructure | Findings marked provisional

At the user's request, findings are flagged as volatile working hypotheses
so that agents do not take them as truth. Added the rule
[[SCHEMA#Findings are provisional]], a *Provisional finding* callout on every
`findings/` page, a note on the Findings section of [[index]] and on the
thesis in [[overview]], and a working rule in `CLAUDE.md`.

## [2026-10-21] ingest | Pass 3: Garfield as reference

Ingested the Garfield north-star README, `mrn-ideas.md`, the three MRN and
five VP reports (key ideas, methodology, key results), and the Stage 1/2,
restore, watchdog and FDP-fix commit notes.

- [[garfield-overview]]: the idea, what each stage produced, the code still
  in the tree (all off by default), the Garfield-era methodology.
- Per stage: [[ghost-execution]], [[memory-renaming]], [[value-prediction]].
- [[garfield-lessons]]: what transfers (measuring, trusting the simulator,
  O3 facts, FS restore mechanics).
- New shared pitfalls: [[o3-wrong-path-counting]], [[simulation-hangs]].
  [[checkpoints]] links the restore mechanics.
- Conflicts flagged on [[garfield-overview]]:
  - The reports' ROB sizes (512, 256) are wrong. The config has had 320
    entries since its first commit (360b14ca7f).
  - The README's status ("Next: Stage 1", FFT benchmark set) is stale.
  - `mrn-ideas.md` mixes eras.
  - All Garfield O3 runs predate the L2 TLB fix.
- Lint now warns about backticks inside wikilinks (Obsidian matches the raw
  heading text).

## [2026-10-21] publish | Task tracer guide and design pages

The first outputs registered in [[publish]], both HTML artifacts built from
the wiki:
- `tracer-guide`, for users: setup, commands, flags, window placement,
  analysis outputs, viewers, sweeps, trace format, reading the numbers,
  checks, debugging, limits.
- `tracer-design`, for collaborators: the problem, why gem5's tools do not
  fit, the hooks, reading memory without the MMU, KASLR and offsets,
  instruction counts, validation, what it has shown (marked provisional),
  limits, extending.

The source HTML is in `docs/wiki/_publish/`.

## [2026-10-22] query | Is OpenCode's JIT runtime the problem?

The user asked whether OpenCode's JIT causes most context switches and
whether JIT-compiled TypeScript is known to be slow on the core.
Re-analysed the baseline sweep traces:
[[2026-10-22-opencode-thread-breakdown]]. OpenCode runs 42.5% of the
instructions and causes 14% of the switches (`JITWorker` 7.2% and ~8.5%);
the Docker polling of the replay driver causes over half. Updated
[[opencode-harness]], [[replay-polling-in-measurement]], [[questions]].

## [2026-10-23] ingest | PC trace for footprint and branch studies

At the user's request (no gem5 changes): `analysis_scripts/tasktrace/pc_trace.py`
reduces gem5's Exec trace to one line per committed instruction (address
only when not PC+4, plus the mnemonic) with task markers joined by tick
from the task tracer; `run_scripts/tasktrace/pc-trace.sh` streams the Exec
trace through a named pipe so only the reduced file is stored. Validated on
gin-2121 (2M instructions): exact PC-for-PC expansion, tracer counts match,
138 KB vs 30 MB. Found that the full `Exec` flag set includes
`ExecFaulting`, which adds instructions that did not commit. New page
[[pc-trace]]; updated [[run-and-analysis-scripts]], [[index]] and the two
script READMEs.

## [2026-10-23] fix | PC trace joins tasks by PC, works on O3

`pc_trace.py` now places task markers at each committed instruction at
`__switch_to`'s slid address instead of by tick: O3's Exec lines carry the
fetch tick (4–99 ns before the tracer's commit tick in the check), which
would misplace markers. `pc-trace.sh` gained `O3="SETTLE WARMUP DETAILED"`.
Checked on atomic (unchanged result) and on an O3 window (exact PC stream;
slice count equal to the tracer's without NOPs). Updated [[pc-trace]].

## [2026-10-23] experiment | PC-trace smoke test on rubocop (O3)

`pc-trace.sh` gained `GEM5_OPTS` (default: stats without descriptions).
Smoke test on rubocop-13560, 1 + 1M + 20M O3 instructions in 1M blocks:
181K instructions/s, 2.7 GB peak, 0.041 bytes per instruction of PC trace,
62/62 switches joined, 61/61 slices equal to the tracer's count without
NOPs. Planning numbers for a 15G run are in [[pc-trace]].

## [2026-10-23] ingest | Stats as a values-only table

`analysis_scripts/tasktrace/stats_table.py` converts `stats.txt` to
`stats.tsv.zst` (names once, one row of values per dump; checked, then the
text deleted): 637 MB → 8.5 MB on a sweep window. `trace_analysis.py`,
`window_view.py` and the sweep tools read either form (outputs identical on
fmt-3901); `pc-trace.sh` converts at the end of each run. Updated
[[stats-blocks]], [[pc-trace]], [[run-and-analysis-scripts]].

## [2026-10-25] experiment | rubocop 15G: caches ×1/×4/×8 × infinite BTB+TLB

Six 15G-instruction O3 runs of rubocop-13560 with PC traces and 200K
blocks (new `--cache-scale` in `sim_opts.py`). All runs hit a guest stall
at tick ≈ 4.6228e12; the two ×8 runs finished before it, `normal` and
`infbtbtlb` were stopped. Stall parts moved to `<run>/stall/`. The
configurations do different work over the same instructions (the Ruby test
run grows from 3% to 16%), so per-process comparison is the main result:
×8 caches +12–25% IPC, infinite BTB+TLB +2–11%, additive. New
[[2026-10-23-rubocop-15g-cache-btb-tlb]]; updated [[btb-tlb-limits]],
[[comparing-configurations]], [[neoverse-v2]], [[pc-trace]], [[questions]].
`trace_analysis.load_blocks` now streams the stats dumps (a 75K-block run
does not fit in memory as dicts).

## [2026-10-25] ingest | Guest stall: TRNG HVC into the EL2 hyp stub

From the stall's PC trace: `crng_reseed` (timer-driven kworker) →
`arch_get_random_seed_longs` → SMCCC TRNG over HVC → the kernel's hyp stub
at EL2 (`0x41068000`), which loops at its current-EL sync vector forever.
New pitfall [[guest-trng-hvc-stall]]; linked from [[simulation-hangs]].

## [2026-10-26] experiment | Instruction footprint per process (rubocop 15G)

New `analysis_scripts/tasktrace/pc_footprint.py` (+ `pc_footprint.cc`):
one pass over a PC trace for distinct instructions/lines/pages, LRU stack
distances (private and shared) at the L1I/L2 sizes, and distinct branches
by type, per process name with execs placed exactly. On cache8x: OpenCode
has ~10 MB of code but fits an 8 MB L2; the rest fits 512K–2M; docker and
git misses are cold. New [[2026-10-26-rubocop-instruction-footprint]];
updated [[pc-trace]], [[run-and-analysis-scripts]], [[questions]],
[[index]].

## [2026-10-26] experiment | Footprint per PID and aggregated by name

`pc_footprint.py` now reports three views: per PID (`instances.csv`), per
name with each process separate, and per name with same-name processes
sharing addresses. On rubocop cache8x the aggregation barely shrinks
docker's and git's code (overlap 0.98–0.99): runs load at randomized
addresses, so cross-run sharing needs load addresses. Updated
[[2026-10-26-rubocop-instruction-footprint]], [[pc-trace]].

## [2026-10-27] experiment | Footprint per thread, repeat distance per PC

`pc_footprint.py` now also reports per thread (each thread's user and
kernel code on its own), with the repeat distance per instruction address
next to the one per line, and writes `report.html` (new
`pc_footprint_report.py`), a per-thread page for every future pass. On
rubocop cache8x (944 threads): OpenCode's main thread holds 7.0 MB of its
9.5 MB and repeats much sooner than the interpreters (median 68
instructions vs ~500) but has a longer tail. Updated
[[2026-10-26-rubocop-instruction-footprint]], [[pc-trace]],
[[run-and-analysis-scripts]].

## [2026-10-27] infra | Footprint report: user/kernel split, process filter

`report.html` (`pc_footprint_report.py`) now splits each thread's
instructions and code size between user and kernel mode, can count user
code only or kernel code only against the cache sizes, and hides
processes by name. Updated [[pc-trace]].

## [2026-10-27] infra | Footprint pass: NOP counting for atomic traces

Checked `pc_footprint.py` on five other traces. On the atomic core the
tracer's instruction count includes NOPs (O3's does not), so the pass,
which always left them out, would place execs early on atomic traces.
It now keeps both counts and uses the one the first switch matches. O3
results (all rubocop runs) are unchanged. Updated [[pc-trace]].

## [2026-10-27] infra | Long-run tools in analysis_scripts

The rubocop-15G scripts that are not specific to that study are now
tracked tools in `analysis_scripts/tasktrace/`: `split_stall.sh` (moves a
trailing guest stall aside, found from the data), `check_pc_slices.sh`
(PC trace against the task trace, slice by slice), `compare_runs.sh`
(per-run analysis, common region through the sweep tools, process views)
and `process_views.py` (harness / tools / replay driver / other / kernel,
per process, over whole slices and with 1/3/6 blocks trimmed at each
switch; clock from config.ini). Tested on copies of the rubocop smoke run;
`process_views.py` reproduces the dashboard's numbers on the six 15G runs
(0.1% apart in the whole-slice IPC: 333 ticks per cycle from config.ini
instead of 333.33). New [[long-runs]]; updated [[run-and-analysis-scripts]],
`analysis_scripts/README.md`.

## [2026-10-27] experiment | rubocop 15G: harness vs tools, cost around switches

Added the per-process views, the harness-vs-tools comparison and the
switch-exclusion bound to [[2026-10-23-rubocop-15g-cache-btb-tlb]], with
the dashboard's link and where its source is kept.

## [2026-10-27] publish | Long Runs Guide

New output `long-runs-guide` (https://claude.ai/artifact/Q59pV5tfkzizJsRkw87vGH),
built from [[long-runs]] and the pages listed in [[publish]].


## [2026-10-27] fix | Long-run guest hang marked as open

The user asked to treat the hang of long runs as something to
investigate, not a settled cause. [[guest-trng-hvc-stall]] is now
`status: open` with a provisional warning: the hang is observed, while the
RNG-reseed / TRNG-HVC mechanism is a hypothesis from one checkpoint's PC
trace. Cutting the hang off is a workaround. Updated [[long-runs]],
[[2026-10-23-rubocop-15g-cache-btb-tlb]], [[questions]], and the Long Runs
Guide.

## [2026-10-28] tool | Geometric means in the multi-sweep comparison

The user asked for the five-way comparison to report standard
computer-architecture summaries: the baseline as an absolute value, every
other configuration as the geometric mean of per-checkpoint ratios.
`sweep_compare.py` (three or more sweeps) now writes
`compare_multi_geomean.csv`, and the page has a geomean table per suite
with the geomean IPC speedups in its summary strip. Its "Change against A"
mode became "Ratio to A (×)", and so did `violins_multi_change`. Zeros have
no ratio and are left out (counted); a mean over fewer than half the
checkpoints is left empty. Regenerated `runs/sweep/20261019-compare-5way/`
and `runs/sweep/20261020-skip100M/compare-5way/`; the per-checkpoint data
is unchanged. Agentic inf-BTB+TLB is 1.069× (1.075× after the skip). At the user's request the page's
tables and strip show each geomean ratio as a percentage change against
the baseline (one decimal); the CSV keeps the ratios.
Updated [[2026-10-16-btb-tlb-limit-study]], [[sweeps]],
[[comparing-configurations]], [[aggregating-metrics]],
`analysis_scripts/README.md`.

## [2026-10-28] query | iTLB misses above L1I misses around bash and cat

The user asked why iTLB misses exceed L1I misses near 11.5G instructions of
the rubocop 15G `normal` run, and whether gem5's L1I is VIPT. Over
11.3–11.7G, `itb.misses` = `inserts` + `prefetchFaults` (39.1 = 5.9 +
33.0 PKI). FDP prefetch translations dominate, and dominate most in the
short-lived tools (bash 64 of 71). Completed instruction walks (0.2–0.4
PKI) are below the L1I miss rate. Fetch translates first and accesses a
physically indexed, physically tagged L1I, and TLB hits are free. Updated
[[fdp-inflates-itlb-misses]] and [[tlb-hierarchy]].

## [2026-10-28] lint | Stats blocks vs schedule and trace (rubocop 15G `normal`)

Checked that the window view's stats blocks line up with the guest
schedule and the PC trace. All 67,338 blocks (main and stall) match
`intervals.csv` exactly: block numbers, contiguous ticks and instructions,
`simTicks`, `simInsts` and `numInstsNotNOP` equal the interval deltas.
Of 23,894 tracer events inside the blocks, all but one fall in the same
block by instruction count and by tick; the exception is a switch whose
instruction is the last of its block and commits at the dump tick.
Recounting the 13.6G-instruction PC trace per block gives the same
non-NOP count in every block, the same NOP-inclusive and user counts up
to NOPs at block boundaries, and its 20,215 task markers sit exactly at
the tracer's instruction counts, ticks and PIDs. The window page's
segments are the switches one for one. Found that `numCycles` leaves out
WFI time, which breaks the miss-latency conversion:
[[numcycles-excludes-wfi]].

## [2026-10-29] query | Baseline core configuration table

The user asked for a summary table of the baseline core for a recap
presentation. Checked [[neoverse-v2]] against the baseline sweep's
`config.ini` (gin-2121): all values match. Added MSHRs, replacement
policies, prefetcher degrees, the MMU cache geometry, the DDR5
subchannels and the indirect predictor to [[neoverse-v2]].

## [2026-10-29] tool | Slice categories in the sweep pages

The user asked for the sweep and comparison pages to switch between all
slices, the harness, its tools, its own git and the rest (replay infra,
other), with the time share of each as violins on top. The user chose
these definitions:
- Slices are cut at context switches.
- Cycles come from ticks.
- Events are shared out by instruction overlap.
- Kernel and idle go in "other".

`sweep_summary.py` writes per-category values and shares (`sweep_slices.csv`).
`sweep_compare.py` writes them per sweep and geomeans per category over the
windows where it ran. `sweep_view.html` has the slice switch and the share
violins. `window_view.block_metrics` now also returns each block's start
tick. All five limit-study summaries (full and skip 100M) and both five-way
comparisons were regenerated with `runs/sweep/resummarise-slices.sh`.
Whole-window values and geomeans are byte-identical to the previous ones.
Results are in [[2026-10-16-btb-tlb-limit-study]]: harness +9.0% with both
limits (TLB +5.3%), tools +4.6%, git +2.3%. Updated [[sweeps]] and
`analysis_scripts/README.md`.

## [2026-10-30] tool | Per-process split under the slice categories

`sweep_summary.py` now sums each agentic window's slices per process (tgid)
first, and then sums the processes per category. A category's value is its
processes' values weighted by each metric's denominator. The category
values are unchanged: `sweep.csv`, `sweep_slices.csv` and `sweep.view.json`
are byte-identical on the baseline sweep. The new `sweep_processes.csv`
keeps every process (509 rows over the 27 baseline windows); the pages
still show categories only. Per-category event counts remain an estimate,
prorated from the 200K-instruction blocks by instruction overlap.
Regenerated all ten summaries with `runs/sweep/resummarise-slices.sh`.
Updated [[sweeps]] and `analysis_scripts/README.md`.

## [2026-10-30] tool | Edge blocks and scheduling metrics in the sweep pages

`sweep_summary.py`:
- New scheduling metrics: switch frequency (kHz), mean time between
  switches (µs), and scheduler instructions (Σ `sched_insts` ÷
  instructions, counted for the category switched out of).
- Edge settings k = 1, 3, 5: drop the stats blocks within k − 1 of a block
  holding a switch, then recompute every metric (window, categories,
  processes) over the rest.
- A kept block lies in one slice, so nothing is prorated.
- An all-blocks mask reproduces every window value exactly.
- New `sweep_edges.csv`; `sweep_processes.csv` gains `edge_blocks`.

`sweep_compare.py` carries the settings and their geomeans
(`compare_multi_geomean_edges.csv`). `sweep_view.html` has a 0/1/3/5
switch and a kept-instructions hint.

All ten summaries and both five-way comparisons were regenerated.

Result in [[2026-10-16-btb-tlb-limit-study]]: the agentic gain from both
limits falls from +6.9% to +3.7% at k = 5 (harness +9.0% → +5.0%, replay
infra +5.1% → +0.6%). Updated [[sweeps]] and `analysis_scripts/README.md`.

## [2026-10-30] experiment | Footprint per bin: window length vs program

`pc_footprint.py`/`.cc` now also count each thread's distinct code and
branches per bin of 100M, 500M and 1G instructions, cut by the thread's
own instructions or by run windows (`thread_bins.csv`); `report.html` can
show the bins instead of the whole stream and plots footprint growth
against the bin size. It also fixes the report's "All numbers" table,
which never rendered (wrong default sort key). Checked against a
brute-force count on a 20M prefix; the earlier outputs are unchanged. On
rubocop cache8x, OpenCode's main thread touches 2.4 MB per 100M of its
own work and 4.9 MB per 1G, against 7.0 MB over the whole stream; docker
uses its full 1.2 MB in each short life. Republished
https://claude.ai/artifact/WggFB79GWaW6x7nUsun7So. Updated
[[2026-10-26-rubocop-instruction-footprint]], [[pc-trace]].

## [2026-11-02] infrastructure | Footprint pass: cache sizes as a parameter

`pc_footprint.py --caches LEVEL:SIZE,...` sets the cache sizes for the LRU
hit rates and footprint multiples (default: the Neoverse V2 L1I and L2 at
×1/×4/×8, as before). The pass saves them in `caches.json`; the summary
tables and `report.html` follow the list (any number of levels). Checked
with a three-level list on `runs/traced-test/rubocop-smoke`; the rubocop
cache8x outputs are unchanged apart from the summary's number rounding and
the PID tables' extra largest-size columns. Updated [[pc-trace]].

## [2026-11-02] fix | Stats compression flag for every launcher

`COMPRESS_STATS=1` makes the launchers replace a run's `stats.txt` by the
checked `stats.tsv.zst` table when gem5 exits, through the new
`run_scripts/compress-stats.sh` (the step `pc-trace.sh` already ran, now
shared). `run_agent.sh`, `run_spec.sh`, `atomic.sh`, `o3-window.sh`,
`spec-window.sh` and both sweeps honour it (the sweeps record it in
`sweep.conf`); `pc-trace.sh` keeps it on by default. Off by default
elsewhere, so `o3-window.sh` no longer converts unconditionally. The
launchers keep gem5's exit status. Checked on a synthetic `stats.txt`
(off, on, `KEEP_STATS`, no stats file). Updated
[[run-and-analysis-scripts]], [[sweeps]], [[stats-blocks]].

## [2026-11-02] fix | PC trace option for windows and sweeps

`PC_TRACE=1` makes `o3-window.sh`, `spec-window.sh`, `sweep.sh` and
`smart_sweep.sh` also record the compact, zstd-compressed PC trace
(`pc_trace.zst`). The named-pipe and reducer setup moved from `pc-trace.sh`
into `run_scripts/tasktrace/pc-trace-lib.sh`, which all of them source; it
also releases a reducer left waiting when gem5 dies before opening the pipe.
`PC_TRACE_LEVEL` sets the zstd level. The sweeps record the flag in
`sweep.conf`. Checked with a fake trace (normal and gem5-died cases) and a
real gin-2121 O3 window with `PC_TRACE=1 COMPRESS_STATS=1`. Updated
[[pc-trace]], [[run-and-analysis-scripts]], [[sweeps]].

## [2026-11-02] fix | O3 switch ticks before their fetch, explained

The reducer's "switch ticks before their Exec tick" warning now has a cause
on [[pc-trace]]: O3 commit services PC events after it commits an
instruction and advances its PC, so the `__switch_to` hook fires when the
`bl` into it commits; when `__switch_to` is fetched late (a front-end miss),
that is before its fetch tick, which O3 Exec prints. Read from the code; the
per-configuration counts (68 baseline … 1 with inf BTB+TLB and ×8 caches)
fit it. The join is unaffected; rechecked on o3-check (`verify`),
rubocop-smoke and the 15G `normal` run (20,213 slices, 0 different).
`pc_trace.py`'s docstrings say "next to commit" instead of "commits". Also
corrected the direction of the O3 tick offset on [[pc-trace]] (the tracer's
tick is the later one). Updated [[long-runs]].

## [2026-11-02] publish | Rebuilt the three guides; compression page

New page [[run-output-compression]] (`COMPRESS_STATS`, `PC_TRACE`, sizes,
readers, checks), in [[index]] and as a source of tracer-guide and
long-runs-guide. Rebuilt and republished all three outputs at their URLs
(registry in [[publish]]): tracer-guide (compression switches, sweep slice
categories, scheduling metrics, edge blocks, geometric means, WFI cycles),
tracer-design (the replay driver's and OpenCode's shares of switches and
instructions), long-runs-guide (compression on other launchers, the switch
tick explanation, footprint bins and `--caches`, geomeans, the stats-block
cross-check).

## [2026-11-02] fix | Old run outputs moved to runs/old-tests

`runs/` now holds only `sweep/`, `rubocop-15G/`, `venv/` and
`old-tests/`. Everything else (the early `tasktrace/` runs, `traced-test/`,
`analysis/`, `btb/`, `tlbflush/`, screenshots, old sweep logs, the
2026-11-02 `PC_TRACE` test window) moved into `runs/old-tests/`, kept
rather than deleted. Paths updated in [[2026-10-08-tool-call-windows]],
[[2026-10-14-event-windows]], [[2026-10-22-opencode-thread-breakdown]] and
[[pc-trace]]; older log entries keep the paths of their time. The
launchers still write new runs to `runs/tasktrace/<stamp>` by default.

## [2026-11-02] experiment | Perfect-L2 switch, validated

New switch `--perfect-l2` (`--perfect-l2-cycles`, default 11) in
`sim_opts.py` and `cache_hierarchy.py`. It removes the L2 and the per-core
L2 crossbar; the L1s and MMU cache sit on a memory bus with the L2
crossbar's timing, in front of a fixed-latency `SimpleMemory` at the L2
hit latency. Decided with the user: build the perfect L2 as a
fixed-latency memory under the L1s rather than a zero-latency DRAM under
the L2, and stop after validation for now. A shared crossbar in front of
the memory bus panicked the snoop filter (double request), so the L1s
connect to the bus directly. Validated on jq-2598 (5M): restore into
`SimpleMemory` works, results are deterministic, and L1 misses take about
17–21 cycles. New page [[2026-11-02-perfect-l2]]; updated
[[neoverse-v2]] and [[index]]. The 1B sweep is still to do.

## [2026-11-02] experiment | Perfect-TLB switch, validated

New switch `--perfect-tlb`: `ArmMMU.perfect_tlb` makes `MMU::getTE` serve
a timing translation's TLB miss with a functional table walk, which fills
the TLBs and takes no time; counted in the new stat `mmu.perfectWalks`.
Decided with the user: prefetch translations still drop on a miss, so FDP
reach does not mix into the TLB effect. Validated on the perfect-L2
window (jq-2598, 5M): switch-off run identical to the earlier baseline,
deterministic, no timed walks and no MMU cache traffic; +2.6% IPC alone,
+45% together with `--perfect-l2`. Added to [[2026-11-02-perfect-l2]];
updated [[neoverse-v2]], [[tlb-hierarchy]] and [[index]].

## [2026-11-02] query | Why carbon-2752 loses with the infinite BTB

Investigated the one agentic window that loses with `--infinite-btb`
(−0.9% full, −1.8% after the 100M skip). The front end improves as
elsewhere and stale BTB entries are negligible. Up to ~180M instructions,
and in every process whose work matches (docker, git, `JITWorker`), the BTB
run is faster. After that the clocked replay lays out the work differently:
git snapshots start 41M instructions earlier, the main OpenCode thread runs
a data-heavier stretch (dTLB +28%), and the JIT thread compiles 4× more.
Probably a work-mix effect, not a real loss. A PC-matched check is still
open. Added to [[2026-10-16-btb-tlb-limit-study]].

## [2026-11-03] experiment | Perfect-L1I switch, validated

New switch `--perfect-l1i` (`--perfect-l1i-cycles`, default 2, the L1I
hit latency) in `sim_opts.py`. It sets the new O3 params `perfectICache`
and `perfectICacheLatency`: `Fetch::sendPerfectICacheRead` reads the fetch
block with `sendFunctional` and delivers it to `processCacheCompletion`
after N cycles. The new stat is `fetch.perfectICacheReads`, and
`isDrained` waits for reads in flight. Decided with the user: the caches
see no instruction traffic, so data gets the whole L2; a shadow timed
request was set aside. The FDP prefetcher is detached (the decoupled front
end stays). Validated on jq-2598 (5M): switch-off baseline unchanged,
deterministic, no L1I accesses; IPC +11.2%, with L2 accesses −56% and L1D
miss latency 84 → 75 cycles. Fetch still waits about one cycle per line.
New page [[2026-11-03-perfect-l1i]]; updated [[neoverse-v2]] and [[index]].

## [2026-11-03] fix | smart_sweep: host-wide memory gate and per-run caps

`smart_sweep.sh` now counts every `gem5.opt` on the host in its launch
gate, other users' included (the machine is shared). It reads the task
from `--restore-dir`, and past `RAMP_MIN` (10) minutes it takes a run's
own `VmHWM` as its peak. It holds launches while memory pressure is above
`PSI_MAX` (10%). Each run goes in its own systemd user scope, capped at
need + max(need/4, 2 GB), with no swap. A run that outgrows its cap is
OOM-killed alone and marked failed "out of memory", and its cap goes into
`PEAKS`. The per-UID `STATE` directory is gone. Decided with the user:
improve the smart sweep now; Slurm (configs drafted in `runs/slurm/`) is
set aside for now.
Tested with 1M + 2M windows: jq-2598 completes under its cap, with
compression, analysis and summary. babel-15649 given a 2.5 GB cap against
its ~6 GB footprint is killed 16 s into the restore, with nothing else
touched. Its sweep marks it failed and records the cap.
Updated [[sweeps]], [[sweep-memory-exhaustion]], [[index]] and
`run_scripts/README.md`.

## [2026-11-03] fix | Existing runs converted to stats tables

Freed disk space by converting every `stats.txt` under `runs/` to its
checked `stats.tsv.zst` table with the new `runs/compress-existing.sh`
(dry run by default). The user asked for this and approved a one-sweep
pilot first. 352 files, ~121 GB → 1.8 GB, 0 failures; `runs/` 122 GB →
9.0 GB. Pilot check: `sweep_summary.py` outputs for
`runs/sweep/20261014-110051` are identical from either form.
Updated [[run-output-compression]].

## [2026-11-03] fix | Peaks file tracked in git

At the user's request, the smart sweep's peak-RSS table moved from
`runs/sweep/mem_peaks.tsv` (gitignored) to
`run_scripts/tasktrace/mem_peaks.tsv` (tracked), so the other user's clone
gets it on merge. Rows now hold task, peak MB, date and the run that set
it. OOM-killed runs are marked `oom-cap`, and the rows stay sorted for
clean diffs. Its lock moved to `$LOCK.peaks` in `/tmp`, and `sweep.conf`'s
`-dirty` check ignores the file. The 20 existing rows were carried over
(dated 2026-10-20, their runs not recorded). The old file is left in
place, unused. Updated [[sweeps]], [[sweep-memory-exhaustion]] and
`run_scripts/README.md`.
