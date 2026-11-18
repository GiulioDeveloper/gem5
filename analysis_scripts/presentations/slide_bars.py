# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
"""Slide HTML for a horizontal bar chart of aggregate changes vs the baseline
(geomean speedup for IPC, change of arithmetic means for other metrics).

Usage:
    python3 analysis_scripts/presentations/slide_bars.py COMPARE_DIR \
        [-m ipc] [--suite agentic] [--sweeps LABEL ...] \
        [--names NAME ...] [--colors HEX ...] [--max-width 1000]

Reads compare_geomean.csv and compare.view.json from a sweep_compare.py
output directory and prints a <div> of bar rows (name, bar, "+43.2%") in
the Slides artifact subset, to paste into a slide file. Bars are native
slide elements, so they stay editable and sharp. Bar length is
proportional to the change; the largest one gets --max-width px. --names
and --colors give one entry per sweep (defaults: the sweep labels and one
colour); colour alone must not carry meaning, so say what the colours stand
for in the slide's footer.
"""

import argparse
import csv
import json
from pathlib import Path

FONT = "'IBM Plex Sans', Arial, sans-serif"
INK = "#16202b"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("compare", type=Path, help="sweep_compare.py output dir")
    ap.add_argument("-m", "--metric", default="ipc")
    ap.add_argument("--suite", default="agentic")
    ap.add_argument("--sweeps", nargs="+", help="sweep labels, top to bottom")
    ap.add_argument("--names", nargs="+", help="row names, one per sweep")
    ap.add_argument("--colors", nargs="+", help="bar colours, one per sweep")
    ap.add_argument("--max-width", type=int, default=1000)
    ap.add_argument("--font-size", type=int, default=28)
    args = ap.parse_args()

    labels = [s["label"] for s in
              json.loads((args.compare / "compare.view.json").read_text())
              ["sweeps"]]
    with open(args.compare / "compare_geomean.csv") as f:
        row = next((r for r in csv.DictReader(f)
                    if r["suite"] == args.suite and r["metric"] == args.metric),
                   None)
    if row is None:
        raise SystemExit(f"no {args.suite} {args.metric} row")
    sweeps = args.sweeps or labels[1:]
    names = args.names or sweeps
    colors = args.colors or ["#3a6ea5"] * len(sweeps)
    if not len(sweeps) == len(names) == len(colors):
        raise SystemExit("--names and --colors need one entry per sweep")
    change = {}
    for s in sweeps:
        v = row.get(f"{s}:ratio")
        if not v:
            raise SystemExit(f"no ratio for {s!r}; have {labels[1:]}")
        change[s] = float(v) - 1
    top = max(abs(c) for c in change.values()) or 1
    fs = args.font_size
    out = ['<div style="display:flex; flex-direction:column; gap:18px">']
    for s, name, col in zip(sweeps, names, colors):
        c = change[s]
        w = max(4, round(abs(c) / top * args.max_width))
        out.append(
            '  <div style="display:flex; flex-direction:row; gap:24px; '
            'align-items:center">\n'
            f'    <p style="width:420px; font-family:{FONT}; '
            f'font-size:{fs}px; color:{INK}">{name}</p>\n'
            f'    <div style="width:{w}px; height:40px; background:{col}; '
            'border-radius:4px"></div>\n'
            f'    <p style="font-family:{FONT}; font-size:{fs}px; '
            f'font-weight:600; color:{INK}">{c * 100:+.1f}%</p>\n'
            '  </div>')
    out.append("</div>")
    print("\n".join(out))


if __name__ == "__main__":
    main()
