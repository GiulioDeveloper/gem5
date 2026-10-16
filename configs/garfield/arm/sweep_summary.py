# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
"""Cross-checkpoint summary of a detailed-window sweep: violins of each
metric over the checkpoints of each suite.

Usage:
    python3 configs/garfield/arm/sweep_summary.py runs/sweep/<ts> [--pdf]
    python3 configs/garfield/arm/sweep_summary.py runs/tasktrace/*o3window*

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
  per-block count.

Writes <out>/sweep.csv (one row per run), sweep.view.json and sweep.html
(violins, SPEC beside agentic, window value or CV). --pdf also writes
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_analysis as ta  # noqa: E402
import window_view as wv  # noqa: E402

TEMPLATE = Path(__file__).with_name("sweep_view.html")
PLACEHOLDER = "__SWEEP_DATA__"

# Metrics shown, in order (keys of window_view.METRICS).
KEYS = ("ipc", "user_share", "fetch_rate",
        "l1i_mpki", "itlb_mpki", "icache_stall",
        "br_mpki", "btb_mispred_pki", "squashed",
        "l1d_mpki", "l2_mpki", "dtlb_mpki", "walks_pki", "l1d_lat",
        "rob_full", "iq_full", "lsq_full")
SWITCHES = (("switches", "Context switches", None),
            ("switch_process", "Process switches", "switch_process"),
            ("switch_thread", "Thread switches", "switch_thread"),
            ("switch_kernel", "Kernel-thread switches", "switch_kernel"))
SUITES = ("spec", "agentic")


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


def summarize(suite, name, d):
    blocks, metrics, _ = wv.block_metrics(d, [])
    if not blocks:
        return None, None
    by = {m["key"]: m for m in metrics}
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
        for e in events:
            if e["event"] != "switch" or not lo <= e["insts"] < hi:
                continue
            b = bisect.bisect_right(starts, e["insts"]) - 1
            per_block["switches"][b] += 1
            per_block[ta.event_kinds(e, tree)[0]][b] += 1
        for k, _, _ in SWITCHES:
            n = sum(per_block[k])
            row[k + "_n"] = n
            row[k] = wv.round4(n / minsts)
            row[k + "_cv"] = r4(cv(per_block[k]))
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


def collect(paths):
    """(rows, metric definitions) over the run directories under paths."""
    runs = run_dirs(paths)
    if not runs:
        raise SystemExit("no run directories with intervals.csv found")
    rows, defs = [], {}
    for suite, name, d in runs:
        row, mdefs = summarize(suite, name, d)
        if row is None:
            print(f"skip {d}: no stats blocks", file=sys.stderr)
            continue
        rows.append(row)
        for k, m in mdefs.items():
            defs.setdefault(k, {kk: m[kk] for kk in ("key", "group",
                                                      "label", "unit",
                                                      "desc")})
    metric_defs = [defs[k] for k in KEYS if k in defs]
    if any("switches" in r for r in rows):
        metric_defs += [{"key": k, "group": "Scheduling", "label": label,
                         "unit": "per M insts",
                         "desc": "context switches in the window"
                         + (f" of kind {kind}" if kind else "")}
                        for k, label, kind in SWITCHES]
    return rows, metric_defs


def write_page(model, out, stem):
    """<out>/<stem>.view.json and <out>/<stem>.html from the template."""
    blob = json.dumps(model, separators=(",", ":"))
    (out / f"{stem}.view.json").write_text(blob)
    page = TEMPLATE.read_text().replace(PLACEHOLDER,
                                        blob.replace("</", "<\\/"))
    page = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">\n' + page + "\n</html>\n")
    (out / f"{stem}.html").write_text(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", type=Path, nargs="+")
    ap.add_argument("-o", "--out", type=Path,
                    help="output directory (default <first path>/summary)")
    ap.add_argument("--pdf", action="store_true",
                    help="also write violins*.pdf/.png (needs matplotlib)")
    args = ap.parse_args()
    out = args.out or args.paths[0] / "summary"
    rows, metric_defs = collect(args.paths)
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
    model = {"version": 1, "name": str(args.paths[0]),
             "metrics": metric_defs, "runs": rows}
    write_page(model, out, "sweep")
    if args.pdf:
        write_pdfs(rows, metric_defs, out, VIOLINS)
    counts = {s: sum(r["suite"] == s for r in rows) for s in SUITES}
    print(f"{out}/sweep.html: {len(rows)} runs "
          f"({counts['spec']} spec, {counts['agentic']} agentic), "
          f"{len(metric_defs)} metrics"
          + (", violins*.pdf/.png" if args.pdf else ""))


if __name__ == "__main__":
    main()
