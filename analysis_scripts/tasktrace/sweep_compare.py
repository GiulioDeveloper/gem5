# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
"""Checkpoint-by-checkpoint comparison of sweeps (the first is the baseline).

Usage:
    python3 analysis_scripts/tasktrace/sweep_compare.py A B [C ...] [-o OUT]
        [--pdf] [--labels TEXT TEXT ...] [--label-a TEXT] [--label-b TEXT]

A, B, ... (two to eight) are sweep directories as
run_scripts/tasktrace/sweep.sh lays them out (or anything sweep_summary.py
accepts). Each sweep's per-run values come from <dir>/summary/
sweep.view.json when it exists, else they are computed as sweep_summary.py
does. Runs are paired by suite and checkpoint name; checkpoints missing
from any sweep are listed and left out. The sweeps should differ only in
the configuration under test: settings that differ in sweep.conf other
than the extra flags are reported, and so are checkpoints whose windows
differ by more than 0.1% in length.

Writes <out>/compare.csv (each metric's value per sweep, and its change
against the first for the others), compare.view.json and compare.html.
The page leads with the aggregate over checkpoints, per suite: every
metric in one table and the top-down breakdown as one stacked bar per
sweep; then, collapsed, one metric (or the breakdown) checkpoint by
checkpoint against the baseline, and the violins of every metric.

Aggregates, also in compare_geomean.csv: for most metrics, the geometric
mean of the first sweep's window values, and for every other sweep the
geometric mean of its per-checkpoint ratio to the first (for IPC, the
speedup). Checkpoints where either value is zero have no ratio and are left
out of that mean (counted); a mean over fewer than half the checkpoints is
left empty. Top-down shares, which add up, are averaged instead: the plain
mean of the first sweep's shares, and for every other sweep the ratio of
its mean to the first's over the checkpoints both have (the page shows the
difference, in percentage points).

When the summaries have slice categories (sweep_summary.py), every view
can be restricted to one category's slices of the agentic runs, the page
shows each category's share of time per sweep, and compare_slices.csv and
compare_geomean_slices.csv hold the per-category values and aggregates (a
category's over the checkpoints where it ran in the baseline). When they
have edge settings (stats blocks dropped at each end of every thread run),
every view and aggregate is also available at each setting, and
compare_geomean_edges.csv holds the aggregates at all of them. --pdf also
writes violins.pdf/.png (the values) and violins_change.pdf/.png (the
ratios). The output directory defaults to <B>/compare-<name of A> for two
sweeps and <A>/compare-multi for more. Labels default to each sweep's extra
flags (`baseline` when it has none).
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_summary as ss  # noqa: E402

TEMPLATE = Path(__file__).with_name("compare_view.html")
PLACEHOLDER = "__COMPARE_DATA__"


def read_conf(d):
    """sweep.conf as {key: value}; empty when there is none."""
    conf = {}
    f = d / "sweep.conf"
    if not f.exists():
        return conf
    for line in f.read_text().splitlines():
        # "SETTLE=1 WARM=..." or "<key> <value>" (e.g. "extra <flags>")
        if "=" in line.split(" ", 1)[0]:
            for part in line.split():
                k, _, v = part.partition("=")
                conf[k] = v
        else:
            k, _, v = line.partition(" ")
            conf[k] = v
    return conf


def load(d):
    """(rows, metric definitions) of one sweep. d is a sweep directory or
    a summary directory written by sweep_summary.py -o (with
    sweep.view.json in it)."""
    view = d / "sweep.view.json"
    if not view.exists():
        view = d / "summary" / "sweep.view.json"
    if view.exists():
        model = json.loads(view.read_text())
        return model["runs"], model["metrics"]
    print(f"{d}: no summary/sweep.view.json, computing it", file=sys.stderr)
    return ss.collect([d])


def change(a, b):
    if a is None or b is None:
        return None, None
    rel = (b - a) / abs(a) if a else None
    return ss.r4(b - a), ss.r4(rel)


MAX_SWEEPS = 8   # categorical colour slots in compare_view.html
CATS = [c for c, _, _ in ss.CATEGORIES]


def geomean(xs, n):
    """Geometric mean of xs, out of n checkpoints; none when fewer than
    half of them have a value (e.g. switch rates, zero in most SPEC
    windows)."""
    if not xs or 2 * len(xs) < n:
        return None
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def geomeans(rows, defs, n, suites=ss.SUITES, get=lambda r: r):
    """Per suite and metric, the aggregate over checkpoints (`agg`):
    "geomean": the geometric mean of the first sweep's window values, and
    for each other sweep the geometric mean of its per-checkpoint ratio to
    the first. Checkpoints where either value is zero or missing have no
    ratio and are left out of that sweep's mean (counted in `excluded`); the
    baseline mean uses the checkpoints with a positive value. A mean over
    fewer than half the checkpoints is left empty.
    "mean" (top-down shares, which add up): the plain mean of the first
    sweep's values, and for each other sweep the ratio of its mean to the
    first's over the checkpoints where both have a value.
    get(row) gives the {metric: values per sweep} to use (a slice
    category's)."""
    out = {}
    for suite in suites:
        rs = [get(r) for r in rows if r["suite"] == suite]
        per = {}
        for m in defs:
            k = m["key"]
            ratios, excluded = [], []
            if "level" in m:
                base = mean([r[k][0] for r in rs if r[k][0] is not None])
                for i in range(1, n):
                    both = [r[k] for r in rs
                            if r[k][0] is not None and r[k][i] is not None]
                    a, b = (mean([v[0] for v in both]),
                            mean([v[i] for v in both]))
                    ratios.append(ss.r4(b / a) if a else None)
                    excluded.append(len(rs) - len(both))
                per[k] = {"agg": "mean", "base": ss.r4(base), "n": len(rs),
                          "ratio": ratios, "excluded": excluded}
                continue
            base = [r[k][0] for r in rs if (r[k][0] or 0) > 0]
            for i in range(1, n):
                xs = [r[k][i] / r[k][0] for r in rs
                      if (r[k][0] or 0) > 0 and (r[k][i] or 0) > 0]
                ratios.append(ss.r4(geomean(xs, len(rs))))
                excluded.append(len(rs) - len(xs))
            per[k] = {"agg": "geomean", "base": ss.r4(geomean(base, len(rs))),
                      "n": len(rs), "ratio": ratios, "excluded": excluded}
        out[suite] = per
    return out


def compare(dirs, labels, out, pdf):
    """Compare two or more sweeps against the first (see the docstring)."""
    confs = [read_conf(d) for d in dirs]
    labels = [lab or c.get("extra") or "baseline"
              for lab, c in zip(labels, confs)]
    notes = []
    for k in ("SETTLE", "WARM", "IVL", "SPEC_DET", "AGENTIC_DET"):
        vals = [c.get(k) for c in confs]
        if len(set(vals)) > 1:
            notes.append(f"{k} differs: " + ", ".join(
                f"{lab} {v}" for lab, v in zip(labels, vals)))

    loaded = [load(d) for d in dirs]
    # Every metric of any sweep, so a metric one configuration lacks (no
    # L1I with a perfect L1I, no L2 with a perfect L2) still has its row,
    # with no value for that sweep. Order: sweep_summary's, so each group
    # stays together.
    # A key sweep_summary no longer knows (an older summary) goes right
    # after the key before it in its own sweep.
    order = list(ss.KEYS) + [k for k, *_ in ss.SWITCHES] \
        + [k for k, *_ in ss.SCHED]
    defs, pos = {}, {}
    for _, ds in loaded:
        prev = -1.0
        for m in ds:
            k = m["key"]
            if k in order:
                prev = order.index(k)
            defs.setdefault(k, m)
            pos.setdefault(k, order.index(k) if k in order else prev + 0.5)
    defs = sorted(defs.values(), key=lambda m: pos[m["key"]])
    keys_kept = [m["key"] for m in defs] + ["kept"]
    by = [{(r["suite"], r["name"]): r for r in rows} for rows, _ in loaded]
    common = set.intersection(*(set(b) for b in by))
    for lab, b in zip(labels, by):
        if set(b) - common:
            notes.append(f"only partly shared, left out ({lab}): "
                         + ", ".join(n for _, n in sorted(set(b) - common)))

    rows = []
    for key in sorted(common):
        rs = [b[key] for b in by]
        row = {"suite": key[0], "name": key[1],
               "insts": [r["insts"] for r in rs]}
        if any(abs(r["insts"] - rs[0]["insts"]) > 1e-3 * rs[0]["insts"]
               for r in rs):
            notes.append(f"{key[1]}: windows of "
                         + ", ".join(str(r["insts"]) for r in rs)
                         + " instructions")
        for m in defs:
            row[m["key"]] = [r.get(m["key"]) for r in rs]
        if all("cat" in r for r in rs):
            row["cat"] = {c: {m["key"]: [r["cat"][c].get(m["key"])
                                         for r in rs] for m in defs}
                          for c in CATS}
            row["share"] = {c: {q: [r["share"][c][q] for r in rs]
                                for q in ("time", "insts")} for c in CATS}
        if all("edge" in r for r in rs):
            row["edge"] = {}
            for k in map(str, ss.EDGES):
                es = [r["edge"][k] for r in rs]
                e = {x: [v.get(x) for v in es] for x in keys_kept}
                if all("cat" in v for v in es):
                    e["cat"] = {c: {x: [v["cat"][c].get(x) for v in es]
                                    for x in keys_kept} for c in CATS}
                row["edge"][k] = e
        rows.append(row)
    if not rows:
        raise SystemExit("no checkpoint is in every sweep")
    sliced = [r for r in rows if "cat" in r]
    if sliced and len(sliced) < sum(r["suite"] == "agentic" for r in rows):
        notes.append("slice categories missing in some agentic runs: "
                     "rerun sweep_summary.py on every sweep")

    out.mkdir(parents=True, exist_ok=True)
    cols = ["suite", "name"]
    for m in defs:
        cols += [f"{m['key']}:{lab}" for lab in labels]
        cols += [f"{m['key']}:{lab}:rel" for lab in labels[1:]]
    with open(out / "compare.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            flat = {"suite": r["suite"], "name": r["name"]}
            for m in defs:
                vals = r[m["key"]]
                for lab, v in zip(labels, vals):
                    flat[f"{m['key']}:{lab}"] = v
                for lab, v in zip(labels[1:], vals[1:]):
                    flat[f"{m['key']}:{lab}:rel"] = change(vals[0], v)[1]
            w.writerow(flat)
    gm = geomeans(rows, defs, len(labels))
    with open(out / "compare_geomean.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "metric", "aggregate", "n", labels[0]]
                   + [f"{lab}:ratio" for lab in labels[1:]]
                   + [f"{lab}:excluded" for lab in labels[1:]])
        for suite in ss.SUITES:
            for m in defs:
                g = gm[suite][m["key"]]
                w.writerow([suite, m["key"], g["agg"], g["n"], g["base"]]
                           + g["ratio"] + g["excluded"])
    gm_cat = category_geomeans(sliced, defs, len(labels), lambda r: r)
    if sliced:
        write_slices(sliced, defs, labels, gm_cat, out)
    # The same at every edge setting (sweep_summary.EDGES).
    gm_edge = {}
    if all("edge" in r for r in rows):
        for k in map(str, ss.EDGES):
            get = lambda r, k=k: r["edge"][k]  # noqa: E731
            gm_edge[k] = {"all": geomeans(rows, defs, len(labels), get=get),
                          "cat": category_geomeans(
                              [r for r in sliced if "cat" in get(r)], defs,
                              len(labels), get)}
        write_edges(gm, gm_cat, gm_edge, defs, labels, out)
    model = {"version": 5,
             "name": " · ".join(str(d) for d in dirs),
             "sweeps": [{"dir": str(d), "label": lab}
                        for d, lab in zip(dirs, labels)],
             "notes": notes, "metrics": defs,
             "categories": ss.category_defs(sliced), "runs": rows,
             "geomean": gm, "geomean_cat": gm_cat,
             "edges": list(ss.EDGES) if gm_edge else [],
             "geomean_edge": gm_edge, "topdown": ss.topdown_tree(defs)}
    write_page(model, out)
    if pdf:
        write_pdfs(rows, defs, labels, out)
    for n in notes:
        print("note:", n, file=sys.stderr)
    counts = {s: sum(r["suite"] == s for r in rows) for s in ss.SUITES}
    print(f"{out}/compare.html: {len(rows)} checkpoints "
          f"({counts['spec']} spec, {counts['agentic']} agentic) in "
          f"{len(dirs)} sweeps against {labels[0]}"
          + (", violins*.pdf/.png" if pdf else ""))


def category_geomeans(rows, defs, n, get):
    """Per slice category, geomeans() of the agentic rows' category values
    (get(row)["cat"]), over the checkpoints where the category ran in the
    baseline (it has an IPC there): an absent category is not a zero."""
    return {c: geomeans([r for r in rows
                         if get(r)["cat"][c]["ipc"][0] is not None],
                        defs, n, ("agentic",),
                        lambda r, c=c: get(r)["cat"][c])["agentic"]
            for c in CATS} if rows else {}


def write_edges(gm, gm_cat, gm_edge, defs, labels, out):
    """compare_geomean_edges.csv: the geometric means at every edge
    setting, 0 (the whole window) included, per suite and per slice
    category."""
    with open(out / "compare_geomean_edges.csv", "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["edge_blocks", "suite", "category", "metric",
                    "aggregate", "n", labels[0]]
                   + [f"{lab}:ratio" for lab in labels[1:]]
                   + [f"{lab}:excluded" for lab in labels[1:]])
        for k, (a, c) in [("0", (gm, gm_cat))] + [
                (k, (v["all"], v["cat"])) for k, v in gm_edge.items()]:
            parts = [(su, "all", a[su]) for su in ss.SUITES]
            parts += [("agentic", cat, c[cat]) for cat in c]
            for su, cat, g in parts:
                for m in defs:
                    x = g[m["key"]]
                    w.writerow([k, su, cat, m["key"], x["agg"], x["n"],
                                x["base"]]
                               + x["ratio"] + x["excluded"])


def write_slices(rows, defs, labels, gm_cat, out):
    """compare_slices.csv (per agentic checkpoint and slice category:
    time and instruction shares and every metric, per sweep) and
    compare_geomean_slices.csv (the aggregates per category)."""
    with open(out / "compare_slices.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "name", "category"]
                   + [f"{q}_share:{lab}" for q in ("time", "insts")
                      for lab in labels]
                   + [f"{m['key']}:{lab}" for m in defs for lab in labels])
        for r in rows:
            for c in CATS:
                w.writerow([r["suite"], r["name"], c]
                           + r["share"][c]["time"] + r["share"][c]["insts"]
                           + [v for m in defs for v in r["cat"][c][m["key"]]])
    with open(out / "compare_geomean_slices.csv", "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "metric", "aggregate", "n", labels[0]]
                   + [f"{lab}:ratio" for lab in labels[1:]]
                   + [f"{lab}:excluded" for lab in labels[1:]])
        for c in CATS:
            for m in defs:
                g = gm_cat[c][m["key"]]
                w.writerow([c, m["key"], g["agg"], g["n"], g["base"]]
                           + g["ratio"] + g["excluded"])


def write_pdfs(rows, defs, labels, out):
    """Grouped violins (suite x sweep) of the values and of the change."""
    # top-down parts below Level 1 are in the CSVs and the page only
    defs = [d for d in defs if d.get("level", 1) == 1]
    import math

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Same categorical order as compare_view.html (light mode).
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
              "#008300", "#6250d6", "#e34948"]
    for fsuffix, title, first in (
            ("", "Window value per checkpoint", 0),
            ("_change", f"Ratio to {labels[0]} (×)", 1)):
        n = len(defs)
        cols = 4
        nrows = math.ceil(n / cols)
        fig, axes = plt.subplots(nrows, cols, figsize=(cols * 4.2,
                                                       nrows * 3.0))
        for ax, dfn in zip(axes.flat, defs):
            k = dfn["key"]
            scale = 1 if first or not dfn["unit"].startswith("%") else 100
            pos, ticks, tlabels = 0, [], []
            for si, suite in enumerate(ss.SUITES):
                for i in range(first, len(labels)):
                    xs = []
                    for r in rows:
                        if r["suite"] != suite:
                            continue
                        a, v = r[k][0], r[k][i]
                        if first:
                            v = v / a if a and v is not None else None
                        if v is not None:
                            xs.append(v * scale)
                    if len(xs) > 1:
                        parts = ax.violinplot([xs], positions=[pos],
                                              showmedians=True, widths=0.8)
                        parts["bodies"][0].set_facecolor(colors[i])
                        parts["bodies"][0].set_alpha(0.35)
                        for c in ("cmedians", "cmins", "cmaxes", "cbars"):
                            parts[c].set_color("#4a535c")
                            parts[c].set_linewidth(0.8)
                    ax.scatter([pos + 0.12 * math.sin(j * 2.399)
                                for j in range(len(xs))], xs, s=5,
                               color=colors[i], zorder=3)
                    ticks.append(pos)
                    tlabels.append(chr(ord("A") + i))
                    pos += 1
                if si == 0:
                    ax.axvline(pos - 0.5, color="#dfe3e7", linewidth=0.8)
            ax.set_xticks(ticks)
            ax.set_xticklabels(tlabels, fontsize=7)
            ax.set_xlabel("SPEC  |  agentic", fontsize=7)
            if first:
                ax.axhline(1, color="#85909a", linewidth=0.6)
            ax.set_title(f"{dfn['label']} ({'×' if first else dfn['unit']})",
                         fontsize=9)
            ax.tick_params(axis="y", labelsize=8)
            ax.grid(axis="y", color="#e9ecef", linewidth=0.6)
            ax.set_axisbelow(True)
        for ax in list(axes.flat)[n:]:
            ax.axis("off")
        key = "   ".join(f"{chr(ord('A') + i)} {lab}"
                         for i, lab in enumerate(labels))
        fig.suptitle(f"{title}: SPEC (left) | agentic (right)\n{key}",
                     fontsize=10)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        for ext in ("pdf", "png"):
            fig.savefig(out / f"violins{fsuffix}.{ext}", dpi=150)
        plt.close(fig)


def write_page(model, out):
    """<out>/compare.view.json and <out>/compare.html from the template."""
    blob = json.dumps(model, separators=(",", ":"))
    (out / "compare.view.json").write_text(blob)
    page = TEMPLATE.read_text().replace(PLACEHOLDER,
                                        blob.replace("</", "<\\/"))
    page = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">\n' + page + "\n</html>\n")
    (out / "compare.html").write_text(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a", type=Path, help="baseline sweep")
    ap.add_argument("b", type=Path, nargs="+",
                    help="sweep(s) compared with it")
    ap.add_argument("-o", "--out", type=Path,
                    help="output directory (default <B>/compare-<A name>, "
                    "or <A>/compare-multi for three or more sweeps)")
    ap.add_argument("--labels", nargs="+",
                    help="names of all sweeps, in order")
    ap.add_argument("--label-a", help="name of A (default: its extra flags)")
    ap.add_argument("--label-b", help="name of B, with two sweeps")
    ap.add_argument("--pdf", action="store_true",
                    help="also write the violins as .pdf/.png "
                    "(needs matplotlib)")
    args = ap.parse_args()
    dirs = [args.a] + args.b
    if len(dirs) > MAX_SWEEPS:
        raise SystemExit(f"at most {MAX_SWEEPS} sweeps")
    labels = args.labels or [None] * len(dirs)
    if len(labels) != len(dirs):
        raise SystemExit("--labels needs one name per sweep")
    labels[0] = args.label_a or labels[0]
    if args.label_b:
        if len(dirs) != 2:
            raise SystemExit("--label-b is for two sweeps; use --labels")
        labels[1] = args.label_b
    out = args.out or (args.b[0] / f"compare-{args.a.resolve().name}"
                       if len(dirs) == 2 else args.a / "compare-multi")
    compare(dirs, labels, out, args.pdf)


if __name__ == "__main__":
    main()
