---
type: howto
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
tags: [viewer, visualization]
---

# Viewers: schedule timeline and window metrics

Both write a compact `*.view.json` and a self-contained HTML page into
`<run>/analysis/`; `--fragment` omits the `<!doctype html>` wrapper. Labels
and tool calls come from [[trace-analysis]], so all tools agree.

## Schedule timeline: `trace_view.py`

```sh
python3 analysis_scripts/tasktrace/trace_view.py <run> [-o out.html] [--fragment]
```

`schedule.html` shows a whole-run strip (drag to select), a tool-call track
(faint pending, solid running → completed, tick at the log line), the CPU
track, one lane per process name or process with exec ▲, fork ●, exit |,
tool I/O ■ and cgroup-move ◆ marks; colouring by process, launch tree or
place (top ten groups, kernel and idle grey; click a legend entry to hide
it); an instruction or simulated-ms axis; and the same data as tables.
With `uinsts`, each bar's darker bottom band is its kernel-mode share (a
proportion, not a position) and the dark end is the scheduler path. *Open
view.json* loads any run's `schedule.view.json` of the current `version`
(3).

## Window metrics: `window_view.py`

```sh
python3 analysis_scripts/tasktrace/window_view.py <run> [-o out.html] \
    [--metric KEY=STAT[/insts|/cycles]] [--fragment]
```

Needs [[stats-blocks]]; works without a trace (metrics only). Purpose:
how the core behaves around scheduling points.

- **One bar chart per metric** on a shared instruction axis, a bar per
  block as wide as its instructions. Groups: throughput, front end, bad
  speculation, memory, back end; Garfield counters and top-down L1 when the
  build has them. `--metric` adds any stat raw, per 1000 instructions or as
  a share of cycles. `window_view.METRICS` defines every metric the sweep
  tools use.
- **Dashed line = the window value from summed stats**, not the mean of the
  bars ([[aggregating-metrics]]: window IPC 0.956 vs mean bar 1.21 on
  framework-52684).
- **Schedule on the same axis**: CPU strip, tool calls, event row; event
  lines through every chart; blocks shaded by who ran most of them.
  Kernel-thread switches are hollow squares with dashed lines.
- **Step through events** of one kind and cause with ◀ ▶; a URL like
  `#kind=switch_process&cause=opencode%20-%3E%20docker&n=3&ctx=12` opens on
  one.
- **Around events**: per metric, mean and 25–75th percentile at block
  offsets −K..+K against the window value, optionally only isolated events.
- **Narrow blocks**: under 2 px a column shows mean (solid) and max (faint);
  *Clip outliers* caps near the 98th percentile.

> [!conflict] "BTB misses" row
> `window_view.py`'s `btb_mpki` row uses `btb.misses`, which is always 0 in
> decoupled mode ([[btb-miss-stat-zero-decoupled]]). The sweep's
> `btb_mispred_pki` and `trace_analysis.py`'s `btb_mpki` use
> `mispredictDueToBTBMiss` and are correct. Not changed yet: [[questions]].

Across checkpoints: [[sweeps]].
