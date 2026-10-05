#!/usr/bin/env python3
"""Bit-identity gate for gem5 stats.txt files (perf-opt campaign).

A line counts unless it is blank, a comment, a '----' separator, or starts
with 'host' or 'simFreq' (host-dependent). Every counted baseline line must
reappear verbatim in the candidate; stats that exist only in the candidate
must be zero. Stat names in an exclusion file are skipped: they are the ones
that differ between two identical baseline runs.

Trial layout: <runs>/<trial>/<checkpoint-id>/stats.txt

  stats_gate.py gate <baseline-trial-dir> <candidate-trial-dir> [--exclude F]
  stats_gate.py nondet <run-a-dir> <run-b-dir>
"""
import argparse
import sys
from pathlib import Path

IGNORED_PREFIXES = ("#", "----", "host", "simFreq")


def load(path):
    """Map stat name -> full stripped line for every counted line."""
    stats = {}
    for line in Path(path).read_text().splitlines():
        s = line.strip()
        if not s or s.startswith(IGNORED_PREFIXES):
            continue
        stats[s.split()[0]] = s
    return stats


def _nonzero(line):
    toks = line.split()
    val = toks[1] if len(toks) > 1 else "?"
    try:
        return float(val) != 0.0
    except ValueError:
        return val not in ("nan", "inf")


def diff(base, cand, exclude=frozenset()):
    """Human-readable differences between two loaded stats; [] = identical."""
    bad = []
    for name, line in base.items():
        if name in exclude:
            continue
        if name not in cand:
            bad.append(f"MISSING {name}")
        elif cand[name] != line:
            bad.append(f"DIFFERS {name}: base[{line}] cand[{cand[name]}]")
    for name, line in cand.items():
        if name in base or name in exclude:
            continue
        if _nonzero(line):
            bad.append(f"NEW NONZERO {line}")
    return bad


def differing_names(a, b):
    """Names whose lines differ (or exist on one side only) between runs."""
    return {n for n in set(a) | set(b) if a.get(n) != b.get(n)}


def load_exclusions(path):
    """First token of each non-blank, non-comment line; no file = none."""
    if path is None or not Path(path).exists():
        return frozenset()
    names = set()
    for line in Path(path).read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            names.add(s.split()[0])
    return frozenset(names)


def trial_checkpoints(trial_dir):
    """Sorted checkpoint ids that have a stats.txt in a trial dir."""
    return sorted(p.parent.name for p in Path(trial_dir).glob("*/stats.txt"))


def gate(base_dir, cand_dir, exclude):
    """Print a per-checkpoint verdict; return True iff all identical."""
    ok = True
    base_ids = set(trial_checkpoints(base_dir))
    cand_ids = set(trial_checkpoints(cand_dir))
    if not base_ids:
        # A mistyped or empty baseline must not read as "all identical".
        print(f"NO BASELINE STATS in {base_dir}")
        return False
    for cid in sorted(base_ids | cand_ids):
        if cid not in cand_ids:
            print(f"{cid}: NO STATS in candidate")
            ok = False
            continue
        if cid not in base_ids:
            print(f"{cid}: NO STATS in baseline")
            ok = False
            continue
        bad = diff(
            load(Path(base_dir) / cid / "stats.txt"),
            load(Path(cand_dir) / cid / "stats.txt"),
            exclude,
        )
        if bad:
            ok = False
            print(f"{cid}: {len(bad)} difference(s)")
            for b in bad[:10]:
                print(f"    {b}")
        else:
            print(f"{cid}: IDENTICAL")
    return ok


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("base")
    g.add_argument("cand")
    g.add_argument("--exclude", default=None)
    n = sub.add_parser("nondet")
    n.add_argument("a")
    n.add_argument("b")
    args = ap.parse_args()

    if args.cmd == "gate":
        sys.exit(
            0
            if gate(args.base, args.cand, load_exclusions(args.exclude))
            else 1
        )

    union = set()
    for cid in trial_checkpoints(args.a):
        names = differing_names(
            load(Path(args.a) / cid / "stats.txt"),
            load(Path(args.b) / cid / "stats.txt"),
        )
        print(f"{cid}: {len(names)} differing stat(s)")
        for name in sorted(names):
            print(f"    {name}")
        union |= names
    print(f"union: {len(union)}")
    for name in sorted(union):
        print(name)


if __name__ == "__main__":
    main()
