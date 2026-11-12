# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
"""Slide-sized violins of a multi-sweep comparison, one panel per metric.

Usage:
    runs/venv/bin/python analysis_scripts/presentations/slide_violins.py \
        COMPARE_DIR -m ipc [-m td_frontend ...] [--titles T ...] \
        [--sweeps LABEL ...] [--suite agentic] [--size 1664x640] -o OUT.png

COMPARE_DIR is a sweep_compare.py output directory (compare.csv and
compare.view.json). Each panel shows, for every chosen sweep, the per-
checkpoint ratio to the first sweep (the baseline) as a violin with the
points, as sweep_compare.py --pdf draws them, but for one suite, a few
metrics and at a size that reads on a 1920x1080 slide. --sweeps takes the
comparison's labels (default: all but the baseline), in the order drawn.
Colours follow each sweep's position in the comparison, so they match its
compare.html page. --size is the slide box in px; the PNG is rendered at
twice that.
"""

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# The categorical palette of sweep_compare.py and compare_view.html.
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
          "#008300", "#6250d6", "#e34948", "#0e8fa3", "#9c4fb3",
          "#8c6d3f", "#7f9a1f", "#5d6b78", "#c4366f", "#3f5bb5",
          "#d98a5b"]
INK, MUTED, GRID, AXIS = "#16202B", "#4A5568", "#e3e1da", "#b8b6ae"


def ratios(rows, key, base, sweep):
    out = []
    for r in rows:
        a, v = r.get(f"{key}:{base}"), r.get(f"{key}:{sweep}")
        if a and v and float(a):
            out.append(float(v) / float(a))
    return out


def panel(ax, rows, key, base, sweeps, color_of, title, bg, ylabel):
    for pos, s in enumerate(sweeps):
        col = color_of[s]
        xs = ratios(rows, key, base, s)
        if len(xs) > 1:
            parts = ax.violinplot([xs], positions=[pos], showmedians=True,
                                  widths=0.8)
            parts["bodies"][0].set_facecolor(col)
            parts["bodies"][0].set_alpha(0.35)
            for c in ("cmedians", "cmins", "cmaxes", "cbars"):
                parts[c].set_color("#4a535c")
                parts[c].set_linewidth(1.2)
        ax.scatter([pos + 0.12 * math.sin(j * 2.399) for j in range(len(xs))],
                   xs, s=22, color=col, zorder=3)
    ax.axhline(1, color="#85909a", linewidth=1.0)
    ax.set_xticks(range(len(sweeps)))
    ax.set_xticklabels(sweeps, fontsize=15, color=INK)
    ax.set_title(title, fontsize=19, color=INK, loc="left", pad=10)
    if ylabel:
        ax.set_ylabel(f"ratio to {base} (×)", fontsize=15, color=MUTED)
    ax.tick_params(axis="y", labelsize=14, colors=MUTED)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_facecolor(bg)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("compare", type=Path, help="sweep_compare.py output dir")
    ap.add_argument("-m", "--metric", action="append", required=True,
                    help="metric key as in compare.csv (repeat for panels)")
    ap.add_argument("--titles", nargs="+", help="one panel title per metric")
    ap.add_argument("--sweeps", nargs="+", help="sweep labels to draw")
    ap.add_argument("--suite", default="agentic")
    ap.add_argument("--size", default="1664x640",
                    help="slide box WIDTHxHEIGHT in px")
    ap.add_argument("--bg", default="#F6F5F0", help="slide background")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()

    labels = [s["label"] for s in
              json.loads((args.compare / "compare.view.json").read_text())
              ["sweeps"]]
    base = labels[0]
    color_of = {s: COLORS[i % len(COLORS)] for i, s in enumerate(labels)}
    sweeps = args.sweeps or labels[1:]
    unknown = [s for s in sweeps if s not in color_of]
    if unknown:
        raise SystemExit(f"unknown sweeps {unknown}; have {labels}")
    titles = args.titles or args.metric
    if len(titles) != len(args.metric):
        raise SystemExit("--titles needs one title per metric")
    with open(args.compare / "compare.csv") as f:
        rows = [r for r in csv.DictReader(f) if r["suite"] == args.suite]
    if not rows:
        raise SystemExit(f"no {args.suite} rows")

    w, h = (int(v) for v in args.size.split("x"))
    n = len(args.metric)
    fig, axes = plt.subplots(1, n, figsize=(w / 100, h / 100),
                             facecolor=args.bg, squeeze=False)
    for i, (ax, k, t) in enumerate(zip(axes[0], args.metric, titles)):
        panel(ax, rows, k, base, sweeps, color_of, t, args.bg, i == 0)
    fig.tight_layout(w_pad=2.0)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=200, facecolor=args.bg)
    plt.close(fig)
    print(f"{args.out}: {n} panel(s), {len(sweeps)} sweeps, "
          f"{len(rows)} {args.suite} checkpoints")


if __name__ == "__main__":
    main()
