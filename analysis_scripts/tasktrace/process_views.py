#!/usr/bin/env python3
"""Per-process metrics of agentic runs: the agent harness against the tools
it calls, against the replay driver, with the slices around context
switches trimmed or not.

A run's detailed region (the stats blocks of <run>/analysis/blocks.csv,
written by trace_analysis.py) is cut at every switch event of
tasktrace.jsonl into scheduling slices; a slice belongs to the switch's
`next` task. A process's stretch is a maximal run of consecutive slices of
that process. Four views of each process:
  all     every slice whole. IPC = instructions / cycles of the slice
          (ticks over the core clock period from config.ini), user/kernel
          split from the tracer's user-instruction count (both exact);
          misses from the stats blocks, shared out by the slice's
          instruction overlap with each block.
  skip1   only the blocks wholly inside a stretch, minus the block holding
          the switch in and the block holding the switch out;
  skip3, skip6
          minus 3 or 6 blocks at each end (the switch-in block and the 2 or
          5 after it, the switch-out block and the 2 or 5 before it).
          These views are the kept blocks' stats.
A group row sums its processes' kept blocks, so it trims at switches
between its own processes too; the task row sums every process.

Groups (by launch tree, trace_analysis.Tree):
  harness  OpenCode (every task whose latest name is "opencode": a fork
           child keeps its parent's name until it execs) and the processes
           it starts itself outside tool calls (its git snapshots);
  tools    processes under bash.fence-real or rg.fence-real, the wrappers
           of OpenCode's bash and search tools;
  driver   the replay driver (the run.sh tree) and the Docker daemons;
  other    every other user process;
  kernel   kernel threads, idle included.
Processes below --min-share of the instructions in every run are summed per
group into "(smaller processes)", view "all" only.

Run trace_analysis.py on every run first. Only slices between two switch
events count, so a trailing guest stall (no switch) is left out by itself.

usage: process_views.py RUN [RUN ...] -o OUT.csv [--labels A,B,...]
The first run is the baseline of the summary printed on stdout; OUT.csv
has a row per run, group or process, and view, with absolute values.
"""

import argparse
import bisect
import csv
import sys
from collections import defaultdict
from pathlib import Path

import trace_analysis as ta

MISS = ("l1i", "l1d", "l2", "br", "btb", "itlb", "dtlb")
VIEWS = {"all": None, "skip1": 1, "skip3": 3, "skip6": 6}
FENCED = {"bash.fence-real", "rg.fence-real"}
DAEMONS = {"dockerd", "containerd", "containerd-shim",
           "containerd-shim-runc-v2"}
GROUPS = {"task": "Whole task", "harness": "Harness: OpenCode and its own git",
          "tools": "Tools, all", "driver": "Replay driver and Docker",
          "other": "Other user processes", "kernel": "Kernel threads and idle"}
SMALL = "(smaller processes)"


def entity(task, tree, oc):
    """(group, process) of a task."""
    if tree.kind(task) != "user":
        return "kernel", "kernel threads"
    tgid, proc = task["tgid"], task["process"]
    if tgid in oc:
        return "harness", "opencode"
    anc = tree.ancestors(tgid)
    names = {n for t in [tgid] + anc for n in tree.names.get(t, [])}
    if any(a in oc for a in anc):
        if names & FENCED:
            return "tools", proc
        return "harness", "opencode " + proc     # its git snapshots
    if "run.sh" in names or proc in DAEMONS:
        return "driver", proc
    return "other", proc


def label(key):
    """Display name of a group or group/process key."""
    if "/" not in key:
        return GROUPS[key]
    g, p = key.split("/", 1)
    if g == "harness":
        return {"opencode": "OpenCode", "opencode git": "OpenCode's git snapshots",
                "opencode opencode": "OpenCode forks before exec"}.get(
                    p, "OpenCode child: " + p.replace("opencode ", ""))
    if g == "tools" and p == "opencode":
        return "tool forks before exec"
    return p


def clock_period(run):
    """Ticks per core cycle: the board clock domain of config.ini."""
    section = None
    for line in open(run / "config.ini"):
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[board.clk_domain]" and line.startswith("clock="):
            return float(line.split("=")[1].split()[0])
    sys.exit(f"{run}: no board.clk_domain clock in config.ini")


def load_blocks(run):
    b = {"s": [], "n": [], "cyc": [], "user": [], **{m: [] for m in MISS}}
    with open(run / "analysis/blocks.csv") as f:
        for r in csv.DictReader(f):
            n = float(r["insts"])
            b["s"].append(int(r["insts_start"]))
            b["n"].append(n)
            b["cyc"].append(n / float(r["ipc"]))
            b["user"].append(float(r["user_frac"]) * n)
            for m in MISS:
                b[m].append(float(r[m + "_mpki"]) * n / 1000)
    return b


def new_acc():
    return {"insts": 0.0, "user": 0.0, "cyc": 0.0, "blocks": 0,
            "stretches": 0, **dict.fromkeys(MISS, 0.0)}


def analyse(run):
    """{key: {view: accumulator}} for the groups, "task" and every
    group/process, and the region's (instructions, cycles)."""
    B = load_blocks(run)
    if not B["s"]:
        sys.exit(f"{run}: analysis/blocks.csv is empty")
    nb = len(B["s"])
    lo, hi = B["s"][0], B["s"][-1] + int(B["n"][-1])
    period = clock_period(run)
    events = ta.load_events(run / "tasktrace.jsonl")
    tree = ta.Tree(events)
    oc = {t for t, ns in tree.names.items() if ns[-1] == "opencode"}
    sw = [e for e in events if e["event"] == "switch"]
    slices = []
    for a, b in zip(sw, sw[1:]):
        if a["insts"] < lo or b["insts"] > hi or b["insts"] <= a["insts"]:
            continue
        g, p = entity(a["next"], tree, oc)
        slices.append((a["insts"], b["insts"], b["uinsts"] - a["uinsts"],
                       (b["tick"] - a["tick"]) / period, g, p))

    acc = defaultdict(lambda: {v: new_acc() for v in VIEWS})
    # View "all", per slice; misses shared out by instruction overlap.
    for s, e, u, cyc, g, p in slices:
        i0 = bisect.bisect_right(B["s"], s) - 1
        for key in (g, "task", f"{g}/{p}"):
            a = acc[key]["all"]
            a["insts"] += e - s
            a["user"] += u
            a["cyc"] += cyc
            i = i0
            while i < nb and B["s"][i] < e:
                bs, bn = B["s"][i], B["n"][i]
                ov = min(e, bs + bn) - max(s, bs)
                if ov > 0:
                    for m in MISS:
                        a[m] += B[m][i] * ov / bn
                i += 1
    # Trimmed views, per process stretch; a group's are the sum of its
    # processes' kept blocks.
    stretches = []
    for s, e, u, cyc, g, p in slices:
        if stretches and stretches[-1][2:] == [g, p] and stretches[-1][1] == s:
            stretches[-1][1] = e
        else:
            stretches.append([s, e, g, p])
    for s, e, g, p in stretches:
        accs = [acc[f"{g}/{p}"], acc[g], acc["task"]]
        for a in accs:
            a["all"]["stretches"] += 1
        first = bisect.bisect_right(B["s"], s) - 1
        last = bisect.bisect_right(B["s"], e - 1) - 1
        for view, k in VIEWS.items():
            if k is None:
                continue
            kept = [i for i in range(first + k, last - k + 1)
                    if B["s"][i] >= s and B["s"][i] + B["n"][i] <= e]
            for x in accs:
                a = x[view]
                for i in kept:
                    a["insts"] += B["n"][i]
                    a["user"] += B["user"][i]
                    a["cyc"] += B["cyc"][i]
                    a["blocks"] += 1
                    for m in MISS:
                        a[m] += B[m][i]
                a["stretches"] += bool(kept)
    total = (sum(x[1] - x[0] for x in slices), sum(x[3] for x in slices))
    return acc, total


def metrics(a, total, whole):
    """total: the region's (instructions, cycles); whole: the entity's
    view-"all" accumulator (coverage and time share)."""
    n = a["insts"]
    if n <= 0:
        return None
    r = {"time": whole["cyc"] / total[1], "share": n / total[0],
         "coverage": n / whole["insts"] if whole["insts"] else None,
         "user": a["user"] / n, "ipc": n / a["cyc"] if a["cyc"] else None}
    r.update({m + "_mpki": 1000 * a[m] / n for m in MISS})
    r.update({"blocks": a["blocks"], "stretches": a["stretches"]})
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--labels", help="comma-separated run labels "
                    "(default: the run directory names)")
    ap.add_argument("--min-share", type=float, default=0.0005,
                    help="processes below this instruction share in every "
                    "run are summed per group (default 0.0005)")
    args = ap.parse_args()
    labels = (args.labels.split(",") if args.labels
              else [r.name for r in args.runs])
    if len(labels) != len(args.runs):
        sys.exit("--labels: one label per run")

    res = {}
    for lab, run in zip(labels, args.runs):
        res[lab] = analyse(run)
        print(f"{lab}: done", file=sys.stderr)
    keep = {k for acc, total in res.values() for k, v in acc.items()
            if "/" in k and v["all"]["insts"] / total[0] >= args.min_share}
    keep.discard("kernel/kernel threads")          # the same as its group
    rows = {}
    for lab, (acc, total) in res.items():
        d = rows[lab] = {}
        small = defaultdict(new_acc)
        for key, views in acc.items():
            if "/" not in key or key in keep:
                d[key] = {v: metrics(a, total, views["all"])
                          for v, a in views.items()}
            elif key != "kernel/kernel threads":
                s = small[key.split("/")[0] + "/" + SMALL]
                for f, x in views["all"].items():
                    s[f] += x
        for key, a in small.items():
            d[key] = {"all": metrics(a, total, a)}

    base = rows[labels[0]]
    gorder = list(GROUPS)

    def order(k):
        sh = ((base.get(k) or {}).get("all") or {}).get("share", 0)
        return (gorder.index(k.split("/")[0]), "/" in k, k.endswith(SMALL), -sh)
    keys = sorted({k for d in rows.values() for k in d}, key=order)

    cols = ["run", "group", "level", "entity", "view", "time", "share",
            "coverage", "user", "ipc", *(m + "_mpki" for m in MISS),
            "blocks", "stretches"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for lab in labels:
            for k in keys:
                for v in VIEWS:
                    r = (rows[lab].get(k) or {}).get(v)
                    if not r:
                        continue
                    w.writerow({
                        "run": lab, "group": k.split("/")[0],
                        "level": "process" if "/" in k else "group",
                        "entity": label(k) if not k.endswith(SMALL) else SMALL,
                        "view": v,
                        **{c: (f"{x:.5g}" if isinstance(x, float) else x)
                           for c, x in r.items()},
                        "blocks": r["blocks"] if v != "all" else ""})

    # Summary: group IPC per run and view, change against the first run.
    print(f"IPC by group and view; time share in the first run; "
          f"change against {labels[0]}")
    print("%-34s %6s %6s" % ("group", "time", "view")
          + "".join("%18s" % lab[:17] for lab in labels))
    for k in (k for k in keys if "/" not in k):
        for v in VIEWS:
            ipcs = [((rows[lab].get(k) or {}).get(v) or {}).get("ipc")
                    for lab in labels]
            t = (base.get(k) or {}).get("all") or {}
            line = ("%-34s %5.1f%% %6s" % (label(k)[:34], 100 * t.get("time", 0), v)
                    if v == "all" else "%-34s %6s %6s" % ("", "", v))
            for i, x in enumerate(ipcs):
                if x is None:
                    line += "%18s" % "-"
                elif i == 0 or not ipcs[0]:
                    line += "%18.3f" % x
                else:
                    line += "%11.3f %+5.1f%%" % (x, 100 * (x / ipcs[0] - 1))
            print(line)
    print(f"rows: {args.out}")


if __name__ == "__main__":
    main()
