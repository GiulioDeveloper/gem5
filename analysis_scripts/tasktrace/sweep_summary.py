# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
"""Cross-checkpoint summary of a detailed-window sweep: every metric of
every checkpoint, the data sweep_compare.py compares.

Usage:
    python3 analysis_scripts/tasktrace/sweep_summary.py runs/sweep/<ts> [--pdf]
    python3 analysis_scripts/tasktrace/sweep_summary.py \
        runs/tasktrace/*o3window*

Each path is a run directory (one with intervals.csv) or a directory
holding run directories, as run_scripts/tasktrace/sweep.sh lays them out
(<base>/spec/<bench>, <base>/agentic/<task>). For every run it takes, over
the detailed window:

- each metric's window value, computed from the stats summed over all
  blocks as window_view.py does (so window IPC is not the mean of the
  block IPCs);
- each metric's coefficient of variation over the window's stats blocks
  (population std / mean of the block values; blocks hold equal
  instruction counts, so they are unweighted);
- context switches from the task trace, by kind (process, thread, kernel
  thread): the count, the rate per million instructions and the CV of the
  per-block count; switch frequency (per millisecond of simulated time),
  the mean time between switches, and the scheduler's share of the
  instructions (SCHED).

For agentic runs it also splits the window by who runs (slice
categories, CATEGORIES below). The window is cut at every context switch
into scheduling slices, and each slice goes to the category of the task
switched in. Per category: its share of the window's simulated time
(ticks) and of its instructions, and every metric's value over its slices
alone. The slices are first summed per process (tgid) and the processes
then summed per category, so a category's value is the mean of its
processes' values weighted by each metric's denominator (instructions,
cycles, accesses). Cycles are the slices' ticks over the core clock
period, so IPC is exact; event counts (misses, stalls, ...) come from the stats blocks,
shared out by each slice's instruction overlap with each block, so a
short slice partly inherits its block's other slices' events. Idle (WFI)
time is in the "other" slices' cycles. Categories with fewer than
MIN_CAT_INSTS instructions in a window have shares but no metric values.

Edge settings (EDGES), for the indirect cost of a context switch: at
setting k, the stats blocks within k - 1 of a block holding a switch are
dropped (the first and last k blocks of every thread run), and every
metric is recomputed over the rest, for the whole window, each category
and each process; a kept block holds no switch, so it goes to one slice
whole and nothing is shared out. Switch metrics and time shares stay
those of the whole window.

Writes <out>/sweep.csv (one row per run), sweep_slices.csv (one row per
agentic run and category), sweep_processes.csv (one row per agentic run
and process, every process kept, at every edge setting), sweep_edges.csv
(one row per run, edge setting and category) and sweep.view.json (all
of it, for sweep_compare.py). There is no page for a single sweep:
compare it against a baseline with sweep_compare.py. --pdf also writes
violins.pdf/.png and violins_cv.pdf/.png with matplotlib. The output
directory defaults to <first path>/summary.
"""

import argparse
import bisect
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import process_views as pv  # noqa: E402
import trace_analysis as ta  # noqa: E402
import window_view as wv  # noqa: E402


# Metrics shown, in order (keys of window_view.METRICS).
KEYS = ("ipc", "user_share", "fetch_rate",
        "l1i_mpki", "itlb_mpki", "icache_stall",
        "br_mpki", "btb_mispred_pki", "squashed",
        "l1d_mpki", "l2_mpki", "dtlb_mpki", "walks_pki", "walks_done_pki",
        "walks_done_d_pki", "walks_done_i_pki", "l1d_lat",
        "rob_full", "iq_full", "lsq_full") + tuple(wv.td_keys())
SWITCHES = (("switches", "Context switches", None),
            ("switch_process", "Process switches", "switch_process"),
            ("switch_thread", "Thread switches", "switch_thread"),
            ("switch_kernel", "Kernel-thread switches", "switch_kernel"))
SUITES = ("spec", "agentic")

# Slice categories of agentic runs: (key, label, description). The groups
# of process_views.entity, with OpenCode's own child processes split out
# of the harness and kernel threads folded into "other".
CATEGORIES = (
    ("harness", "Harness", "OpenCode itself, all its threads"),
    ("tools", "Tools", "processes started by OpenCode's tool calls, under "
     "the bash and rg tool wrappers (bash.fence-real, rg.fence-real)"),
    ("git", "Harness git", "processes OpenCode starts itself outside tool "
     "calls: its git snapshots, with their fork children before the exec"),
    ("infra", "Replay infra", "the replay driver (the run.sh tree: docker "
     "CLI, python3, watch_rounds.sh) and the Docker daemons"),
    ("other", "Other", "every other user process, kernel threads and "
     "idle"),
)
MIN_CAT_INSTS = 1e6
# Stats blocks dropped at each end of every thread run (edge blocks), for
# the indirect cost of a context switch; 0, the whole window, is the row.
EDGES = (1, 3, 5)
# Scheduling metrics from the switch events themselves: (key, label, unit,
# description). They and the switch rates are the same at every edge
# setting.
SCHED = (
    ("switch_khz", "Switch frequency", "kHz",
     "context switches per millisecond of simulated time; per slice "
     "category, switches into it per millisecond of its own time"),
    ("switch_gap", "Time between switches", "µs",
     "mean simulated time between two context switches; per slice "
     "category, the mean time one of its slices runs"),
    ("sched_share", "Scheduler instructions", "% insts",
     "instructions from __schedule to __switch_to: the scheduler's direct "
     "cost, without the switch's tail or the trap that led to it; per "
     "slice category, of the switches out of it"),
)
SCHED_KEYS = ([k for k, _, _ in SWITCHES] + [k + "_n" for k, _, _ in SWITCHES]
              + [k for k, _, _, _ in SCHED])
PS_PER_US = 1e6     # gem5 ticks are picoseconds
FORMULAS = {m[0]: m[5][1] for m in wv.METRICS}


def run_dirs(paths):
    """(suite, name, dir) of every run under the given paths."""
    out = []
    for p in paths:
        if (p / "intervals.csv").exists():
            cands = [p]
        else:
            cands = sorted(d.parent for d in p.glob("*/intervals.csv"))
            cands += sorted(d.parent for d in p.glob("*/*/intervals.csv"))
        for d in cands:
            suite = d.parent.name if d.parent.name in SUITES else None
            # runs/tasktrace names: <date>-<time>-<checkpoint>-<tag>
            m = re.match(r"\d{8}-\d{6}-(.+?)(-o3window.*)?$", d.name)
            name = m.group(1) if m else d.name
            if suite is None:
                suite = "spec" if re.match(r"\d{3}\.", name) else "agentic"
            out.append((suite, name, d))
    return out


def r4(x):
    return None if x is None else wv.round4(x)


def cv(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    if mean == 0:
        return None
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    return math.sqrt(var) / abs(mean)


def category(task, tree, oc):
    """Slice category of a task (CATEGORIES)."""
    g, p = pv.entity(task, tree, oc)
    if g == "harness":
        return "harness" if p == "opencode" else "git"
    return {"tools": "tools", "driver": "infra"}.get(g, "other")


def new_acc():
    return {"insts": 0, "ticks": 0, "stats": defaultdict(float),
            "sw": Counter(), "names": Counter()}


def sched_values(n, ticks, sched_insts, insts):
    """SCHED values of n switches over ticks and insts."""
    return {"switch_khz": r4(n / (ticks / PS_PER_US / 1e3)) if ticks else None,
            "switch_gap": r4(ticks / PS_PER_US / n) if n else None,
            "sched_share": r4(sched_insts / insts) if insts else None}


def acc_values(a, keys, period):
    """Metric values, switch rates and SCHED values of accumulated
    slices."""
    b = {"insts": a["insts"], "ticks": a["ticks"],
         "cycles": a["ticks"] / period}
    out = {}
    for k in keys:
        try:
            out[k] = r4(FORMULAS[k](
                lambda n, st=a["stats"]: st.get(n, 0.0), b))
        except ZeroDivisionError:
            out[k] = None
    for k, _, _ in SWITCHES:
        out[k + "_n"] = a["sw"][k]
        out[k] = r4(a["sw"][k] / (a["insts"] / 1e6)) if a["insts"] else None
    out.update(sched_values(a["sw"]["switches"], a["ticks"],
                            a["sw"]["sched_insts"], a["insts"]))
    return out


def add_piece(a, task, insts, ticks, stats, scale):
    a["insts"] += insts
    a["ticks"] += ticks
    a["names"][task["process"]] += insts
    for n, v in stats.items():
        a["stats"][n] += v * scale


def by_category(procs):
    """Per-process accumulators summed per slice category."""
    acc = {c: new_acc() for c, _, _ in CATEGORIES}
    for (c, _), a in procs.items():
        t = acc[c]
        t["insts"] += a["insts"]
        t["ticks"] += a["ticks"]
        for n, v in a["stats"].items():
            t["stats"][n] += v
        t["sw"].update(a["sw"])
    return acc


def proc_rows(procs, keys, period, ticks, insts):
    return [{"category": c, "tgid": tgid,
             "process": a["names"].most_common(1)[0][0]
             if a["names"] else "",
             "time_share": r4(a["ticks"] / ticks),
             "insts_share": r4(a["insts"] / insts),
             "insts": a["insts"], **acc_values(a, keys, period)}
            for (c, tgid), a in sorted(procs.items(),
                                       key=lambda kv: -kv[1]["insts"])]


def slice_metrics(d, blocks, events, tree, keys, masks):
    """Slice categories of an agentic window (see the module docstring):
    {"cat": {category: {metric: value over its slices}},
     "share": {category: {"time": share of ticks, "insts": share of
               instructions}},
     "procs": [per-process rows],
     "edge": {k: {"cat": ..., "procs": ...}}}, the "edge" entries over the
    blocks kept in masks[k]; None when the trace has no switch before the
    window."""
    lo, hi = blocks[0]["s"], blocks[-1]["e"]
    sw = [e for e in events if e["event"] == "switch"]
    before = [e for e in sw if e["insts"] <= lo]
    if not before:
        return None
    period = pv.clock_period(d)
    oc = {t for t, ns in tree.names.items() if ns[-1] == "opencode"}
    key = lambda t: (category(t, tree, oc), t["tgid"])  # noqa: E731
    # Cut points (instruction, tick, task switched in), window ends included.
    cuts = ([(lo, blocks[0]["t0"], before[-1]["next"])]
            + [(e["insts"], e["tick"], e["next"]) for e in sw
               if lo < e["insts"] < hi]
            + [(hi, blocks[-1]["t0"] + blocks[-1]["ticks"], None)])
    starts = [b["s"] for b in blocks]
    # Slices accumulate per process (category, tgid); categories sum them.
    procs = defaultdict(new_acc)
    for (s, ts, task), (e, te, _) in zip(cuts, cuts[1:]):
        if e <= s:
            continue
        a = procs[key(task)]
        add_piece(a, task, e - s, te - ts, {}, 0)
        i = bisect.bisect_right(starts, s) - 1
        while i < len(blocks) and blocks[i]["s"] < e:
            b = blocks[i]
            ov = min(e, b["e"]) - max(s, b["s"])
            if ov > 0:
                for n, v in b["stats"].items():
                    a["stats"][n] += v * ov / b["insts"]
            i += 1
    # A switch counts for the process it switches to; the scheduler's
    # instructions run in the one it switches out of.
    for e in sw:
        if lo <= e["insts"] < hi:
            a = procs[key(e["next"])]
            a["sw"]["switches"] += 1
            for k in ta.event_kinds(e, tree):
                a["sw"][k] += 1
            procs[key(e["prev"])]["sw"]["sched_insts"] += e.get(
                "sched_insts", 0)
    acc = by_category(procs)
    insts = sum(a["insts"] for a in acc.values()) or 1
    ticks = sum(a["ticks"] for a in acc.values()) or 1
    out = {"cat": {}, "share": {}, "edge": {},
           "procs": proc_rows(procs, keys, period, ticks, insts)}
    for c, a in acc.items():
        out["share"][c] = {"time": r4(a["ticks"] / ticks),
                           "insts": r4(a["insts"] / insts)}
        out["cat"][c] = (acc_values(a, keys, period)
                         if a["insts"] >= MIN_CAT_INSTS else {})
    # Edge settings: a kept block holds no switch, so it lies in one slice
    # and goes to that slice's process whole. Switch and SCHED values stay
    # those of the whole window.
    cut_at = [c[0] for c in cuts]
    whole = {(p["category"], p["tgid"]): p for p in out["procs"]}
    for k, keep in masks.items():
        pk = defaultdict(new_acc)
        for b, kept in zip(blocks, keep):
            if kept:
                task = cuts[bisect.bisect_right(cut_at, b["s"]) - 1][2]
                add_piece(pk[key(task)], task, b["insts"], b["ticks"],
                          b["stats"], 1)
        cat = {}
        for c, a in by_category(pk).items():
            v = (acc_values(a, keys, period)
                 if a["insts"] >= MIN_CAT_INSTS else {})
            v.update({x: out["cat"][c].get(x) for x in SCHED_KEYS})
            full = acc[c]["insts"]
            v["kept"] = r4(a["insts"] / full) if full else None
            cat[c] = v
        rows = proc_rows(pk, keys, period, ticks, insts)
        for r in rows:
            r.update({x: whole[r["category"], r["tgid"]].get(x)
                      for x in SCHED_KEYS})
        out["edge"][k] = {"cat": cat, "procs": rows}
    return out


def edge_masks(blocks, switches):
    """{k: kept flag per block} for k in EDGES: the blocks within k - 1 of
    a block holding a context switch are dropped, i.e. the first and last k
    blocks of every thread run."""
    starts = [b["s"] for b in blocks]
    hit = {bisect.bisect_right(starts, x) - 1 for x in switches}
    masks = {}
    for k in EDGES:
        keep = [True] * len(blocks)
        for j in hit:
            for i in range(max(0, j - k + 1), min(len(blocks), j + k)):
                keep[i] = False
        masks[k] = keep
    return masks


def window_values(blocks, keep, keys, by):
    """Each metric's value and CV over the kept blocks, as block_metrics
    computes the window's (core cycles, stats summed)."""
    kept = [b for b, f in zip(blocks, keep) if f]
    total = {x: sum(b[x] for b in kept) for x in ("insts", "cycles",
                                                   "ticks")}
    summed = defaultdict(float)
    for b in kept:
        for n, v in b["stats"].items():
            summed[n] += v
    out = {}
    for k in keys:
        try:
            out[k] = r4(FORMULAS[k](lambda n: summed.get(n, 0.0), total))
        except ZeroDivisionError:
            out[k] = None
        out[k + "_cv"] = r4(cv([v for v, f in zip(by[k]["v"], keep) if f]))
    return out


def summarize(suite, name, d, skip_insts=0):
    blocks, metrics, _ = wv.block_metrics(d, [], skip_insts)
    if not blocks:
        return None, None
    by = {m["key"]: m for m in metrics}
    keys = [k for k in KEYS if k in by]
    lo, hi = blocks[0]["s"], blocks[-1]["e"]
    minsts = (hi - lo) / 1e6
    row = {"suite": suite, "name": name, "insts": hi - lo,
           "blocks": len(blocks), "dir": str(d)}
    for k in KEYS:
        m = by.get(k)
        row[k] = m["whole"] if m else None
        row[k + "_cv"] = r4(cv(m["v"])) if m else None
    trace = d / "tasktrace.jsonl"
    if trace.exists():
        events = ta.load_events(trace)
        tree = ta.Tree(events)
        starts = [b["s"] for b in blocks]
        per_block = {k: [0] * len(blocks) for k, _, _ in SWITCHES}
        inside = [e for e in events
                  if e["event"] == "switch" and lo <= e["insts"] < hi]
        for e in inside:
            b = bisect.bisect_right(starts, e["insts"]) - 1
            per_block["switches"][b] += 1
            # a kernel run ending in another process is both a
            # kernel-thread and a process switch
            for k in ta.event_kinds(e, tree):
                per_block[k][b] += 1
        for k, _, _ in SWITCHES:
            n = sum(per_block[k])
            row[k + "_n"] = n
            row[k] = wv.round4(n / minsts)
            row[k + "_cv"] = r4(cv(per_block[k]))
        row.update(sched_values(len(inside), sum(b["ticks"] for b in blocks),
                                sum(e.get("sched_insts", 0) for e in inside),
                                hi - lo))
        masks = edge_masks(blocks, [e["insts"] for e in inside])
        row["edge"] = {}
        for k, keep in masks.items():
            v = window_values(blocks, keep, keys, by)
            v.update({x: row[x] for x in SCHED_KEYS})
            v.update({x + "_cv": row.get(x + "_cv") for x in SCHED_KEYS})
            v["kept"] = r4(sum(b["insts"] for b, f in zip(blocks, keep) if f)
                           / (hi - lo))
            row["edge"][str(k)] = v
        if suite == "agentic":
            sl = slice_metrics(d, blocks, events, tree, keys, masks)
            if sl:
                row["cat"], row["share"] = sl["cat"], sl["share"]
                row["procs"] = [dict(p, edge=0) for p in sl["procs"]]
                for k, e in sl["edge"].items():
                    row["edge"][str(k)]["cat"] = e["cat"]
                    row["procs"] += [dict(p, edge=k) for p in e["procs"]]
    return row, {m["key"]: m for m in metrics if m["key"] in KEYS}


# Violin figures: (row-key suffix, file suffix, title, unit of a metric
# definition, scale applied to the values).
VIOLINS = (
    ("", "", "Window value per checkpoint",
     lambda d: d["unit"], lambda d: 100 if d["unit"].startswith("%") else 1),
    ("_cv", "_cv", "Coefficient of variation over the window's stats blocks",
     lambda d: "CV", lambda d: 1),
)


def write_pdfs(rows, defs, out, views):
    # top-down parts below Level 1 are in the CSVs and the page only
    defs = [d for d in defs if d.get("level", 1) == 1]
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"spec": "#2a78d6", "agentic": "#eb6834"}
    for suffix, fsuffix, title, unit_of, scale_of in views:
        n = len(defs)
        cols = 5
        nrows = math.ceil(n / cols)
        fig, axes = plt.subplots(nrows, cols, figsize=(cols * 3.0,
                                                       nrows * 3.0))
        for ax, dfn in zip(axes.flat, defs):
            key = dfn["key"] + suffix
            # "%" units are stored as fractions.
            scale = scale_of(dfn)
            data = [[r[key] * scale for r in rows
                     if r["suite"] == s and r.get(key) is not None]
                    for s in SUITES]
            pos = [i for i, xs in enumerate(data) if len(xs) > 1]
            if pos:
                parts = ax.violinplot([data[i] for i in pos], positions=pos,
                                      showmedians=True, widths=0.8)
                for body, i in zip(parts["bodies"], pos):
                    body.set_facecolor(colors[SUITES[i]])
                    body.set_alpha(0.35)
                for k in ("cmedians", "cmins", "cmaxes", "cbars"):
                    parts[k].set_color("#4a535c")
                    parts[k].set_linewidth(0.8)
            for i, xs in enumerate(data):
                jit = [i + 0.12 * math.sin(j * 2.399) for j in range(len(xs))]
                ax.scatter(jit, xs, s=7, color=colors[SUITES[i]], zorder=3)
            ax.set_xticks(range(len(SUITES)))
            ax.set_xticklabels([f"{s}\n(n={len(xs)})"
                                for s, xs in zip(SUITES, data)], fontsize=8)
            ax.set_xlim(-0.6, len(SUITES) - 0.4)
            ax.set_title(f"{dfn['label']} ({unit_of(dfn)})", fontsize=9)
            ax.tick_params(axis="y", labelsize=8)
            ax.grid(axis="y", color="#e9ecef", linewidth=0.6)
            ax.set_axisbelow(True)
        for ax in list(axes.flat)[n:]:
            ax.axis("off")
        fig.suptitle(title, fontsize=11)
        fig.tight_layout()
        for ext in ("pdf", "png"):
            fig.savefig(out / f"violins{fsuffix}.{ext}", dpi=150)
        plt.close(fig)


def collect(paths, skip_insts=0):
    """(rows, metric definitions) over the run directories under paths."""
    runs = run_dirs(paths)
    if not runs:
        raise SystemExit("no run directories with intervals.csv found")
    rows, defs = [], {}
    for suite, name, d in runs:
        row, mdefs = summarize(suite, name, d, skip_insts)
        if row is None:
            print(f"skip {d}: no stats blocks", file=sys.stderr)
            continue
        rows.append(row)
        for k, m in mdefs.items():
            defs.setdefault(k, {kk: m[kk] for kk in ("key", "group",
                                                      "label", "unit",
                                                      "desc", "level")
                                if kk in m})
    metric_defs = [defs[k] for k in KEYS if k in defs]
    if any("switches" in r for r in rows):
        metric_defs += [{"key": k, "group": "Scheduling", "label": label,
                         "unit": "per M insts",
                         "desc": "context switches in the window"
                         + (f" of kind {kind}" if kind else "")}
                        for k, label, kind in SWITCHES]
        metric_defs += [{"key": k, "group": "Scheduling", "label": label,
                         "unit": unit, "desc": desc}
                        for k, label, unit, desc in SCHED]
    return rows, metric_defs


def topdown_tree(metric_defs):
    """The top-down breakdown (window_view.TOPDOWN_TREE) as page data, when
    the metrics have it."""
    keys = {m["key"] for m in metric_defs}
    return (wv.td_tree() if all(k in keys for k, *_ in wv.td_nodes())
            else None)


def category_defs(rows):
    """CATEGORIES as page definitions; none when no run has slices."""
    if not any("cat" in r for r in rows):
        return []
    return [{"key": k, "label": lab, "desc": desc}
            for k, lab, desc in CATEGORIES]


def write_slices_csv(rows, metric_defs, path):
    """One row per agentic run and slice category."""
    keys = [m["key"] for m in metric_defs]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "name", "category", "time_share",
                    "insts_share"] + keys)
        for r in sorted(rows, key=lambda r: (r["suite"], r["name"])):
            for c, _, _ in CATEGORIES if "cat" in r else ():
                w.writerow([r["suite"], r["name"], c, r["share"][c]["time"],
                            r["share"][c]["insts"]]
                           + [r["cat"][c].get(k) for k in keys])


def write_edges_csv(rows, metric_defs, path):
    """One row per run, edge setting (EDGES) and slice category ("all" for
    the whole window): the share of the instructions kept and every
    metric over the kept blocks."""
    keys = [m["key"] for m in metric_defs]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "name", "edge_blocks", "category", "kept"]
                   + keys)
        for r in sorted(rows, key=lambda r: (r["suite"], r["name"])):
            for k, v in r.get("edge", {}).items():
                w.writerow([r["suite"], r["name"], k, "all", v["kept"]]
                           + [v.get(x) for x in keys])
                for c, cv_ in v.get("cat", {}).items():
                    w.writerow([r["suite"], r["name"], k, c, cv_["kept"]]
                               + [cv_.get(x) for x in keys])


def write_procs_csv(rows, metric_defs, path):
    """One row per agentic run and process (tgid) in its window."""
    keys = [m["key"] for m in metric_defs]
    cols = ["edge", "category", "tgid", "process", "time_share",
            "insts_share", "insts"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "name", "edge_blocks"] + cols[1:] + keys)
        for r in sorted(rows, key=lambda r: (r["suite"], r["name"])):
            for p in r.get("procs", ()):
                w.writerow([r["suite"], r["name"]] + [p[k] for k in cols]
                           + [p.get(k) for k in keys])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", type=Path, nargs="+")
    ap.add_argument("-o", "--out", type=Path,
                    help="output directory (default <first path>/summary)")
    ap.add_argument("--pdf", action="store_true",
                    help="also write violins*.pdf/.png (needs matplotlib)")
    ap.add_argument("--skip-insts", type=float, default=0,
                    help="leave out each window's first N instructions "
                    "(blocks starting there), as extra warm-up; e.g. 100e6")
    args = ap.parse_args()
    out = args.out or args.paths[0] / "summary"
    rows, metric_defs = collect(args.paths, int(args.skip_insts))
    out.mkdir(parents=True, exist_ok=True)
    cols = ["suite", "name", "insts", "blocks"]
    for dfn in metric_defs:
        k = dfn["key"]
        cols += ([k + "_n"] if dfn["group"] == "Scheduling" else [])
        cols += [k, k + "_cv"]
    cols.append("dir")
    with open(out / "sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["suite"], r["name"])))
    write_slices_csv(rows, metric_defs, out / "sweep_slices.csv")
    write_procs_csv(rows, metric_defs, out / "sweep_processes.csv")
    write_edges_csv(rows, metric_defs, out / "sweep_edges.csv")
    for r in rows:      # per-process rows stay out of the page
        r.pop("procs", None)
    # The data sweep_compare.py reads; the pages are comparisons only.
    model = {"version": 3, "name": str(args.paths[0])
             + (f" (first {args.skip_insts / 1e6:g}M instructions of each "
                "window skipped)" if args.skip_insts else ""),
             "metrics": metric_defs, "categories": category_defs(rows),
             "edges": list(EDGES) if any("edge" in r for r in rows) else [],
             "topdown": topdown_tree(metric_defs), "runs": rows}
    (out / "sweep.view.json").write_text(
        json.dumps(model, separators=(",", ":")))
    if args.pdf:
        write_pdfs(rows, metric_defs, out, VIOLINS)
    counts = {s: sum(r["suite"] == s for r in rows) for s in SUITES}
    print(f"{out}/sweep.view.json: {len(rows)} runs "
          f"({counts['spec']} spec, {counts['agentic']} agentic), "
          f"{len(metric_defs)} metrics"
          + (", violins*.pdf/.png" if args.pdf else ""))


if __name__ == "__main__":
    main()
