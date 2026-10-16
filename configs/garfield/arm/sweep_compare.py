# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
"""Checkpoint-by-checkpoint comparison of two sweeps (A = baseline, B).

Usage:
    python3 configs/garfield/arm/sweep_compare.py A B [-o OUT] [--pdf]
        [--label-a TEXT] [--label-b TEXT]

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
    """(rows, metric definitions) of one sweep."""
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a", type=Path, help="baseline sweep")
    ap.add_argument("b", type=Path, help="sweep compared with it")
    ap.add_argument("-o", "--out", type=Path,
                    help="output directory (default <B>/compare-<A name>)")
    ap.add_argument("--label-a", help="name of A (default: its extra flags)")
    ap.add_argument("--label-b", help="name of B (default: its extra flags)")
    ap.add_argument("--pdf", action="store_true",
                    help="also write violins_change/_diff.pdf/.png "
                    "(needs matplotlib)")
    args = ap.parse_args()
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
