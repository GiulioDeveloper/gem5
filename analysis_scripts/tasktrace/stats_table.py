"""Store gem5 stats dumps as a values-only table, and read either form.

usage:
  python3 analysis_scripts/tasktrace/stats_table.py <run>/stats.txt \
      [-o <run>/stats.tsv.zst] [--keep] [--level N]

Converts stats.txt (one block per dump) to a TSV with the stat names once,
in a header row, and one row of values per dump; checks that every value
survived; then deletes stats.txt unless --keep. A stat that a dump leaves
out (gem5 omits stats that stayed at zero) is written as 0. Only the value
column is kept: the percentage columns of distributions follow from the
counts.

Readers: dumps(run) yields one {stat: value string} dict per dump from
<run>/stats.txt if it exists, otherwise from <run>/stats.tsv.zst (or .tsv,
.tsv.gz). Absent stats are absent in the text form and "0" in the table;
callers treat both as zero.
"""

import argparse
import gzip
import os
import sys
from pathlib import Path

HEADER = "#stats_table\tv1"
TABLE_NAMES = ("stats.tsv.zst", "stats.tsv.gz", "stats.tsv")


def open_text(path, mode="rt", level=19):
    path = str(path)
    if path.endswith(".gz"):
        return gzip.open(path, mode)
    if path.endswith(".zst"):
        from compression import zstd

        if "w" in mode:
            return zstd.open(path, mode, level=level)
        return zstd.open(path, mode)
    return open(path, mode)


def text_dumps(path):
    """Yield {stat: value} per dump of a gem5 text stats file."""
    cur = None
    with open_text(path) as f:
        for line in f:
            if line.startswith("---------- Begin"):
                cur = {}
            elif line.startswith("---------- End"):
                if cur is not None:
                    yield cur
                cur = None
            elif cur is not None:
                parts = line.split(maxsplit=2)
                if len(parts) >= 2:
                    cur[parts[0]] = parts[1]


def table_dumps(path):
    """Yield {stat: value} per row of a stats table."""
    with open_text(path) as f:
        if f.readline().rstrip("\n") != HEADER:
            raise SystemExit(f"{path}: not a stats table")
        names = f.readline().rstrip("\n").split("\t")
        for line in f:
            yield dict(zip(names, line.rstrip("\n").split("\t")))


def stats_path(run):
    """The stats file of a run directory: text if present, else a table."""
    run = Path(run)
    if (run / "stats.txt").exists():
        return run / "stats.txt"
    for name in TABLE_NAMES:
        if (run / name).exists():
            return run / name
    raise FileNotFoundError(f"no stats.txt or stats table in {run}")


def dumps(run):
    path = stats_path(run)
    if path.name == "stats.txt":
        return text_dumps(path)
    return table_dumps(path)


def convert(src, out, level=19):
    """Write the table; return the number of dumps and of stat names."""
    names, seen = [], set()
    n = 0
    for d in text_dumps(src):  # pass 1: the union of names, in order
        n += 1
        for k in d:
            if k not in seen:
                seen.add(k)
                names.append(k)
    with open_text(out, "wt", level) as w:  # pass 2: one row per dump
        w.write(HEADER + "\n")
        w.write("\t".join(names) + "\n")
        for d in text_dumps(src):
            w.write("\t".join(d.get(k, "0") for k in names) + "\n")
    return n, len(names)


def check(src, out):
    """Every value of the text file is in the table, dump for dump."""
    n = 0
    tab = table_dumps(out)
    for d in text_dumps(src):
        row = next(tab, None)
        if row is None or any(row.get(k) != v for k, v in d.items()):
            return False, n
        n += 1
    return next(tab, None) is None, n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stats", help="a gem5 stats.txt")
    ap.add_argument("-o", "--out",
                    help="output table (default: stats.tsv.zst beside it)")
    ap.add_argument("--keep", action="store_true",
                    help="keep stats.txt after a successful check")
    ap.add_argument("--level", type=int, default=19,
                    help="zstd level (default 19)")
    args = ap.parse_args()
    src = Path(args.stats)
    out = Path(args.out) if args.out else src.with_name("stats.tsv.zst")
    n, k = convert(src, out, args.level)
    ok, checked = check(src, out)
    if not ok:
        print(f"FAIL: {out} differs from {src} at dump {checked}; "
              f"keeping {src}", file=sys.stderr)
        sys.exit(1)
    a, b = os.path.getsize(src), os.path.getsize(out)
    print(f"{n} dumps, {k} stats: {a / 1e6:.1f} MB -> {b / 1e6:.2f} MB "
          f"({a / b:.0f}x); checked", file=sys.stderr)
    if not args.keep:
        src.unlink()


if __name__ == "__main__":
    main()
