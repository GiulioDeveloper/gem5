# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
"""Checkpoint-by-checkpoint comparison of sweeps (the first is the baseline).

Usage:
    python3 analysis_scripts/tasktrace/sweep_compare.py A B [-o OUT] [--pdf]
        [--label-a TEXT] [--label-b TEXT]
    python3 analysis_scripts/tasktrace/sweep_compare.py A B C [D ...] [-o OUT]
        [--pdf] [--labels TEXT TEXT TEXT ...]

A and B are sweep directories as run_scripts/tasktrace/sweep.sh lays them
out (or anything sweep_summary.py accepts). Each side's per-run values come
from <dir>/summary/sweep.view.json when it exists, else they are computed
as sweep_summary.py does. Runs are paired by suite and checkpoint name;
checkpoints in only one sweep are listed and left out.

For every metric of every pair it writes the window values of A and B, the
difference B - A and the relative change B / A - 1 (none when A is zero).
The sweeps should differ only in the configuration under test: settings
that differ in sweep.conf other than the extra flags are reported, and so
are pairs whose windows differ by more than 0.1% in length.

Writes <out>/compare.csv (one row per pair), compare.view.json and
compare.html (violins of the change over the checkpoints of each suite,
or of either sweep's values). --pdf also writes violins_change.pdf/.png
and violins_diff.pdf/.png. The output directory defaults to
<B>/compare-<name of A>. Labels default to each sweep's extra flags
(`baseline` when it has none).

With three or more sweeps (at most 8), checkpoints present in every sweep
are compared against the first. It writes <out>/compare_multi.csv (each
metric's value per sweep, and its change against the first for the
others), compare_multi.view.json and compare_multi.html: one panel per
metric with a violin per suite and sweep, of the values, the change B / A
- 1 or the difference B - A. --pdf also writes violins_multi.pdf/.png (the
values) and violins_multi_change.pdf/.png. The output directory defaults
to <A>/compare-multi.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_summary as ss  # noqa: E402


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


MAX_SWEEPS = 8   # categorical colour slots in sweep_view.html


def compare_multi(dirs, labels, out, pdf):
    """Compare three or more sweeps against the first (see the docstring)."""
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
    keys = set.intersection(*({m["key"] for m in defs}
                              for _, defs in loaded))
    defs = [m for m in loaded[0][1] if m["key"] in keys]
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
        rows.append(row)
    if not rows:
        raise SystemExit("no checkpoint is in every sweep")

    out.mkdir(parents=True, exist_ok=True)
    cols = ["suite", "name"]
    for m in defs:
        cols += [f"{m['key']}:{lab}" for lab in labels]
        cols += [f"{m['key']}:{lab}:rel" for lab in labels[1:]]
    with open(out / "compare_multi.csv", "w", newline="") as f:
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
    model = {"version": 2, "multi": True,
             "name": " · ".join(str(d) for d in dirs),
             "sweeps": [{"dir": str(d), "label": lab}
                        for d, lab in zip(dirs, labels)],
             "notes": notes, "metrics": defs, "runs": rows}
    ss.write_page(model, out, "compare_multi")
    if pdf:
        write_multi_pdfs(rows, defs, labels, out)
    for n in notes:
        print("note:", n, file=sys.stderr)
    counts = {s: sum(r["suite"] == s for r in rows) for s in ss.SUITES}
    print(f"{out}/compare_multi.html: {len(rows)} checkpoints "
          f"({counts['spec']} spec, {counts['agentic']} agentic) in "
          f"{len(dirs)} sweeps against {labels[0]}"
          + (", violins_multi*.pdf/.png" if pdf else ""))


def write_multi_pdfs(rows, defs, labels, out):
    """Grouped violins (suite x sweep) of the values and of the change."""
    import math

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Same categorical order as sweep_view.html (light mode).
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
              "#008300", "#6250d6", "#e34948"]
    for fsuffix, title, first in (
            ("", "Window value per checkpoint", 0),
            ("_change", f"Relative change against {labels[0]} (%)", 1)):
        n = len(defs)
        cols = 4
        nrows = math.ceil(n / cols)
        fig, axes = plt.subplots(nrows, cols, figsize=(cols * 4.2,
                                                       nrows * 3.0))
        for ax, dfn in zip(axes.flat, defs):
            k = dfn["key"]
            scale = 100 if first or dfn["unit"].startswith("%") else 1
            pos, ticks, tlabels = 0, [], []
            for si, suite in enumerate(ss.SUITES):
                for i in range(first, len(labels)):
                    xs = []
                    for r in rows:
                        if r["suite"] != suite:
                            continue
                        a, v = r[k][0], r[k][i]
                        if first:
                            v = change(a, v)[1]
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
                ax.axhline(0, color="#85909a", linewidth=0.6)
            ax.set_title(f"{dfn['label']} ({'%' if first else dfn['unit']})",
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
            fig.savefig(out / f"violins_multi{fsuffix}.{ext}", dpi=150)
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a", type=Path, help="baseline sweep")
    ap.add_argument("b", type=Path, nargs="+",
                    help="sweep(s) compared with it")
    ap.add_argument("-o", "--out", type=Path,
                    help="output directory (default <B>/compare-<A name>, "
                    "or <A>/compare-multi for three or more sweeps)")
    ap.add_argument("--label-a", help="name of A (default: its extra flags)")
    ap.add_argument("--label-b", help="name of B (default: its extra flags)")
    ap.add_argument("--labels", nargs="+",
                    help="names of all sweeps, in order (three or more)")
    ap.add_argument("--pdf", action="store_true",
                    help="also write the violins as .pdf/.png "
                    "(needs matplotlib)")
    args = ap.parse_args()
    if len(args.b) > 1:
        dirs = [args.a] + args.b
        if len(dirs) > MAX_SWEEPS:
            raise SystemExit(f"at most {MAX_SWEEPS} sweeps")
        labels = args.labels or [None] * len(dirs)
        if len(labels) != len(dirs):
            raise SystemExit("--labels needs one name per sweep")
        compare_multi(dirs, labels, args.out or args.a / "compare-multi",
                      args.pdf)
        return
    args.b = args.b[0]
    out = args.out or args.b / f"compare-{args.a.resolve().name}"

    confs = [read_conf(args.a), read_conf(args.b)]
    labels = [args.label_a, args.label_b]
    for i, c in enumerate(confs):
        labels[i] = labels[i] or c.get("extra") or "baseline"
    notes = []
    for k in ("SETTLE", "WARM", "IVL", "SPEC_DET", "AGENTIC_DET"):
        va, vb = confs[0].get(k), confs[1].get(k)
        if va != vb:
            notes.append(f"{k} differs: A {va}, B {vb}")

    (rows_a, defs_a), (rows_b, defs_b) = load(args.a), load(args.b)
    keys_b = {m["key"] for m in defs_b}
    defs = [m for m in defs_a if m["key"] in keys_b]
    by_a = {(r["suite"], r["name"]): r for r in rows_a}
    by_b = {(r["suite"], r["name"]): r for r in rows_b}
    only_a = sorted(set(by_a) - set(by_b))
    only_b = sorted(set(by_b) - set(by_a))
    for side, missing in (("A", only_a), ("B", only_b)):
        if missing:
            notes.append(f"only in {side}: "
                         + ", ".join(n for _, n in missing))

    rows = []
    for key in sorted(set(by_a) & set(by_b)):
        ra, rb = by_a[key], by_b[key]
        row = {"suite": key[0], "name": key[1], "insts_a": ra["insts"],
               "insts_b": rb["insts"]}
        # Blocks end on the first instruction past the count, so the same
        # window can differ by a few instructions.
        if abs(ra["insts"] - rb["insts"]) > 1e-3 * ra["insts"]:
            notes.append(f"{key[1]}: window of {ra['insts']} instructions "
                         f"in A, {rb['insts']} in B")
        for m in defs:
            k = m["key"]
            a, b = ra.get(k), rb.get(k)
            row[k + "_a"], row[k + "_b"] = a, b
            row[k + "_diff"], row[k + "_rel"] = change(a, b)
        rows.append(row)
    if not rows:
        raise SystemExit("no checkpoint is in both sweeps")

    out.mkdir(parents=True, exist_ok=True)
    cols = ["suite", "name", "insts_a", "insts_b"]
    for m in defs:
        cols += [m["key"] + s for s in ("_a", "_b", "_diff", "_rel")]
    with open(out / "compare.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    model = {"version": 1, "compare": True,
             "name": f"A {args.a} · B {args.b}",
             "a": {"dir": str(args.a), "label": labels[0]},
             "b": {"dir": str(args.b), "label": labels[1]},
             "notes": notes, "metrics": defs, "runs": rows}
    ss.write_page(model, out, "compare")
    if args.pdf:
        pct = lambda d: d["unit"].startswith("%")  # noqa: E731
        ss.write_pdfs(rows, defs, out, (
            ("_rel", "_change",
             f"Relative change, {labels[1]} against {labels[0]} (%)",
             lambda d: "% change", lambda d: 100),
            ("_diff", "_diff",
             f"Difference, {labels[1]} minus {labels[0]}",
             lambda d: "pp" if pct(d) else d["unit"],
             lambda d: 100 if pct(d) else 1),
        ))
    for n in notes:
        print("note:", n, file=sys.stderr)
    counts = {s: sum(r["suite"] == s for r in rows) for s in ss.SUITES}
    print(f"{out}/compare.html: {len(rows)} pairs "
          f"({counts['spec']} spec, {counts['agentic']} agentic), "
          f"{labels[1]} against {labels[0]}"
          + (", violins_*.pdf/.png" if args.pdf else ""))


if __name__ == "__main__":
    main()
