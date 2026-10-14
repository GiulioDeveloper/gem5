# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD

"""Metrics view of a detailed window (host Python, stdlib).

    python3 configs/garfield/arm/window_view.py <outdir> [-o out.html]
        [--metric KEY=STAT[/insts|/cycles]] ...

Reads the stats blocks of a run made with --stats-interval-insts
(<outdir>/stats.txt and intervals.csv) and, when the run used --task-trace,
its tasktrace.jsonl. Writes <outdir>/analysis/window.view.json and a
self-contained <outdir>/analysis/window.html built from window_view.html:
one bar chart per metric, with a bar per stats block on the committed
instruction axis, and the guest schedule (who ran, context switches,
process events, tool calls) drawn on the same axis. Who ran is coloured by
process name, launch tree or place, the labels of trace_analysis.py. The
page also averages each metric over the blocks around every event of a
chosen kind, to show how the core behaves before and after a scheduling
point. A metric is dropped when it is zero in every block.

Metrics come from METRICS below; a metric is also dropped when none of
its stats appears in the run (e.g. the top-down ones outside the top-down
build). --metric adds any other stat: KEY=STAT plots it raw per block,
KEY=STAT/insts per 1000 committed instructions and KEY=STAT/cycles as a
share of the block's cycles. Process labels and event kinds are the ones
of trace_analysis.py.
"""

import argparse
import csv
import json
from pathlib import Path

import trace_analysis as ta
import trace_view

TEMPLATE = Path(__file__).with_name("window_view.html")
PLACEHOLDER = "__WINDOW_DATA__"

CORE = ta.CORE
L1I = ta.CACHES + "l1icaches."
L1D = ta.CACHES + "l1dcaches."
L2 = ta.CACHES + "l2caches."


def pki(*stats):
    return (stats, lambda s, b: sum(s(x) for x in stats) * 1000 / b["insts"])


def per_cycle(*stats):
    """A share of the block's cycles: 'stalls per cycle' for event counts
    that rename and dispatch bump once per stalled cycle."""
    return (stats, lambda s, b: sum(s(x) for x in stats) / b["cycles"])


def per_commit(stat):
    total = CORE + "commitStats0.numInsts"
    return ((stat,), lambda s, b: s(stat) / (s(total) or b["insts"]))


def miss_latency(cache):
    """Average demand miss latency in core cycles."""
    lat, miss = cache + "overallMissLatency::total", \
        cache + "overallMisses::total"
    return ((lat, miss),
            lambda s, b: (s(lat) / s(miss) * b["cycles"] / b["ticks"]
                          if s(miss) else float("nan")))


# (key, group, label, unit, description, (stats, formula)). The formula
# gets s(stat) -> the stat's value in the block (0 when gem5 left it out)
# and the block's insts, cycles and ticks.
METRICS = [
    ("ipc", "Throughput", "IPC", "insts/cycle",
     "Committed instructions per cycle",
     ((CORE + "numCycles",), lambda s, b: b["insts"] / b["cycles"])),
    ("user_share", "Throughput", "User-mode share", "% insts",
     "Committed instructions that ran in user mode",
     per_commit(CORE + "commitStats0.numUserInsts")),
    ("fetch_rate", "Throughput", "Fetch rate", "insts/cycle",
     "Instructions fetched per cycle, wrong path included",
     per_cycle(CORE + "fetchStats0.numInsts")),
    ("issue_rate", "Throughput", "Issue rate", "insts/cycle",
     "Instructions issued per cycle, wrong path included",
     per_cycle(CORE + "instsIssued")),

    ("l1i_mpki", "Front end", "L1I misses", "PKI",
     "L1 instruction cache misses per 1000 instructions",
     pki(L1I + "overallMisses::total")),
    ("itlb_mpki", "Front end", "iTLB misses", "PKI",
     "L1 instruction TLB misses per 1000 instructions",
     pki(CORE + "mmu.itb.misses")),
    ("btb_mpki", "Front end", "BTB misses", "PKI",
     "BTB lookups that missed, per 1000 instructions",
     pki(CORE + "branchPred.btb.misses::total")),
    ("icache_stall", "Front end", "I-cache stall cycles", "% cycles",
     "Cycles fetch waited on the instruction cache",
     per_cycle(CORE + "fetchStats0.icacheStallCycles")),
    ("ftq_full", "Front end", "FTQ full", "% cycles",
     "Cycles the branch predictor stalled on a full fetch target queue",
     per_cycle(CORE + "bac.status::FTQFull")),
    ("decode_blocked", "Front end", "Decode blocked", "% cycles",
     "Cycles decode was blocked by rename",
     per_cycle(CORE + "decode.status::Blocked")),

    ("br_mpki", "Bad speculation", "Conditional mispredicts", "PKI",
     "Conditional branches predicted wrong, per 1000 instructions",
     pki(CORE + "branchPred.condIncorrect")),
    ("mispred_pki", "Bad speculation", "All mispredicts", "PKI",
     "Committed branches mispredicted (direction or target), per 1000 "
     "instructions",
     pki(CORE + "branchPred.mispredicted_0::total")),
    ("btb_mispred_pki", "Bad speculation", "BTB-miss mispredicts", "PKI",
     "Mispredicts caused by a BTB miss, per 1000 instructions",
     pki(CORE + "branchPred.mispredictDueToBTBMiss_0::total")),
    ("squashed", "Bad speculation", "Squashed per committed", "ratio",
     "Instructions squashed in the ROB per committed instruction",
     per_commit(CORE + "commit.commitSquashedInsts")),
    ("fetch_squash", "Bad speculation", "Fetch squashing", "% cycles",
     "Cycles fetch spent squashing",
     per_cycle(CORE + "fetch.status::squashing")),
    ("memorder_pki", "Bad speculation", "Memory-order violations", "PKI",
     "Loads replayed after a memory-order violation, per 1000 "
     "instructions",
     pki(CORE + "iew.memOrderViolationEvents")),

    ("l1d_mpki", "Memory", "L1D misses", "PKI",
     "L1 data cache misses per 1000 instructions",
     pki(L1D + "overallMisses::total")),
    ("l2_mpki", "Memory", "L2 misses", "PKI",
     "L2 misses (demand, prefetch and page walks) per 1000 instructions",
     pki(L2 + "overallMisses::total")),
    ("dtlb_mpki", "Memory", "dTLB misses", "PKI",
     "L1 data TLB misses per 1000 instructions",
     pki(CORE + "mmu.dtb.misses")),
    ("walks_pki", "Memory", "Page walks", "PKI",
     "Page-table walks per 1000 instructions",
     pki(CORE + "mmu.walker.walks")),
    ("l1d_lat", "Memory", "L1D miss latency", "cycles",
     "Average L1D miss latency", miss_latency(L1D)),
    ("l1i_lat", "Memory", "L1I miss latency", "cycles",
     "Average L1I miss latency", miss_latency(L1I)),

    ("rename_blocked", "Back end", "Rename blocked", "% cycles",
     "Cycles rename was blocked by a full back end",
     per_cycle(CORE + "rename.status::Blocked")),
    ("rob_full", "Back end", "ROB full", "% cycles",
     "Rename stalls on a full ROB, per cycle",
     per_cycle(CORE + "rename.ROBFullEvents")),
    ("iq_full", "Back end", "IQ full", "% cycles",
     "Dispatch stalls on a full issue queue, per cycle",
     per_cycle(CORE + "iew.iqFullEvents")),
    ("lsq_full", "Back end", "LSQ full", "% cycles",
     "Dispatch stalls on a full load/store queue, per cycle",
     per_cycle(CORE + "iew.lsqFullEvents")),
    ("regs_full", "Back end", "Registers full", "% cycles",
     "Rename stalls on no free physical registers, per cycle",
     per_cycle(CORE + "rename.fullRegistersEvents")),
    ("lq_occ", "Back end", "LQ occupancy", "entries",
     "Average load queue occupancy",
     ((CORE + "lsq0.lqAvgOccupancy",),
      lambda s, b: s(CORE + "lsq0.lqAvgOccupancy"))),
    ("sq_occ", "Back end", "SQ occupancy", "entries",
     "Average store queue occupancy",
     ((CORE + "lsq0.sqAvgOccupancy",),
      lambda s, b: s(CORE + "lsq0.sqAvgOccupancy"))),

    ("ghost_share", "Garfield", "Ghost-executed share", "% insts",
     "Committed instructions that skipped the issue queue (ghost "
     "execution)",
     per_commit(CORE + "ghost.ghostInsts")),
    ("mrn_share", "Garfield", "Memory-renamed share", "% insts",
     "Committed loads served by the memory-rename predictor (MRN), per "
     "committed instruction",
     per_commit(CORE + "commit.committedMrned")),
    ("vp_share", "Garfield", "Value-predicted share", "% insts",
     "Committed instructions with a value prediction",
     per_commit(CORE + "commit.committedVpPredicted")),
]

# Top-down Level 1 (gem5 PR #2392, branch topdown-pr2392): found by suffix,
# since the stat group differs between versions of the PR.
TOPDOWN = [
    ("td_frontend", "frontendBound", "Front-end bound"),
    ("td_badspec", "badSpeculation", "Bad speculation"),
    ("td_backend", "backendBound", "Back-end bound"),
    ("td_retiring", "retiring", "Retiring"),
]


def read_dumps(path, wanted, suffixes):
    """Per stats dump, {stat: float} restricted to `wanted` and to stats
    ending in one of `suffixes`."""
    dumps, cur = [], None
    with open(path) as f:
        for line in f:
            if line.startswith("---------- Begin"):
                cur = {}
            elif line.startswith("---------- End"):
                dumps.append(cur)
                cur = None
            elif cur is not None:
                parts = line.split(maxsplit=2)
                if len(parts) < 2:
                    continue
                name = parts[0]
                if name in wanted or name.endswith(suffixes):
                    try:
                        cur[name] = float(parts[1])
                    except ValueError:
                        pass
    return dumps


def custom_metric(spec):
    key, _, stat = spec.partition("=")
    stat, _, den = stat.partition("/")
    if not key or not stat or den not in ("", "insts", "cycles"):
        raise SystemExit(f"--metric {spec!r}: expected KEY=STAT"
                         "[/insts|/cycles]")
    if den == "insts":
        return (key, "Custom", key, "PKI", stat, pki(stat))
    if den == "cycles":
        return (key, "Custom", key, "% cycles", stat, per_cycle(stat))
    return (key, "Custom", key, "", stat,
            ((stat,), lambda s, b: s(stat)))


def round4(x):
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return float(f"{x:.4g}")


def block_metrics(outdir, extra):
    with open(outdir / "intervals.csv") as f:
        intervals = [{k: int(v) for k, v in r.items()}
                     for r in csv.DictReader(f)]
    metrics = METRICS + [custom_metric(m) for m in extra]
    wanted = {x for m in metrics for x in m[5][0]}
    wanted |= {CORE + "numCycles", CORE + "commitStats0.numInsts"}
    suffixes = tuple("." + t[1] for t in TOPDOWN)
    dumps = read_dumps(outdir / "stats.txt", wanted, suffixes)
    # One dump per interval; gem5's exit dump has no interval row.
    blocks = []
    for iv, d in zip(intervals, dumps):
        b = {"s": iv["insts_start"], "e": iv["insts_end"],
             "insts": iv["insts_end"] - iv["insts_start"],
             "ticks": iv["tick_end"] - iv["tick_start"],
             "cycles": d.get(CORE + "numCycles", 0), "stats": d}
        if b["insts"] > 0 and b["cycles"] > 0:
            blocks.append(b)
    seen = set().union(*(b["stats"] for b in blocks)) if blocks else set()
    for key, stat, label in TOPDOWN:
        full = sorted(n for n in seen if n.endswith("." + stat))
        if full:
            metrics.append((key, "Top-down", label, "% slots",
                            f"Top-down Level 1: {full[0]}",
                            ((full[0],),
                             lambda s, b, n=full[0]: s(n))))
    # Stats that are already per-block averages or ratios cannot be summed
    # over blocks; their window value is the cycle-weighted mean.
    averaged = {CORE + "lsq0.lqAvgOccupancy", CORE + "lsq0.sqAvgOccupancy"}
    averaged |= {m[5][0][0] for m in metrics if m[1] == "Top-down"}
    total = {"insts": sum(b["insts"] for b in blocks),
             "cycles": sum(b["cycles"] for b in blocks),
             "ticks": sum(b["ticks"] for b in blocks)}
    summed = {}
    for b in blocks:
        for n, v in b["stats"].items():
            summed[n] = summed.get(n, 0.0) + v
    out, dropped = [], []
    for key, group, label, unit, desc, (stats, formula) in metrics:
        # gem5 leaves a stat out of a dump while it is zero, so a missing
        # stat reads as 0. A metric none of whose stats ever appears is not
        # in this build; one that is zero throughout (a disabled feature)
        # is dropped too.
        if key != "ipc" and not any(x in seen for x in stats):
            continue
        vals = []
        for b in blocks:
            def s(n, d=b["stats"]):
                return d.get(n, 0.0)
            try:
                vals.append(round4(formula(s, b)))
            except ZeroDivisionError:
                vals.append(None)
        if key != "ipc" and not any(vals):
            dropped.append(key)
            continue
        if any(x in averaged for x in stats):
            pairs = [(v, b["cycles"]) for v, b in zip(vals, blocks)
                     if v is not None]
            whole = (sum(v * c for v, c in pairs) / sum(c for _, c in pairs)
                     if pairs else float("nan"))
        else:
            try:
                whole = formula(lambda n: summed.get(n, 0.0), total)
            except ZeroDivisionError:
                whole = float("nan")
        out.append({"key": key, "group": group, "label": label,
                    "unit": unit, "desc": desc, "whole": round4(whole),
                    "v": vals})
    return blocks, out, dropped


def schedule(outdir, lo, hi):
    """The guest schedule inside [lo, hi): CPU slices, events and tool
    calls, from trace_view's model so both pages agree."""
    trace = outdir / "tasktrace.jsonl"
    if not trace.exists():
        return None
    model = trace_view.view_model(outdir)
    events = ta.load_events(trace)
    tree = ta.Tree(events)
    S = model["segs"]
    keep = [i for i in range(len(S["s"])) if S["e"][i] > lo and S["s"][i] < hi]
    segs = {k: [S[k][i] for i in keep] for k in ("s", "e", "p", "u")
            if k in S}
    # The task running at the trace's last event keeps the CPU to the end
    # of the window (a quiet SPEC run has no events after its last switch);
    # its user share is assumed to stay the same.
    if segs["e"] and segs["e"][-1] == model["i1"] and model["i1"] < hi:
        n = segs["e"][-1] - segs["s"][-1]
        if "u" in segs and n > 0 and segs["u"][-1] is not None:
            segs["u"][-1] = round(segs["u"][-1] * (hi - segs["s"][-1]) / n)
        segs["e"][-1] = hi
    used = sorted(set(segs["p"]))
    marks = []
    for e in events:
        if not lo <= e["insts"] < hi or e["event"] in ("start", "snapshot"):
            continue
        kinds = ta.event_kinds(e, tree)
        ev = e["event"]
        if ev == "switch":
            p, n = e["prev"], e["next"]
            text = (f"{p['comm']} ({p['pid']}) → {n['comm']} ({n['pid']})"
                    if p and n else "switch")
            marks.append({"k": kinds[0], "i": e["insts"], "text": text,
                          "cause": ta.switch_cause(e, tree)})
        elif ev in ("fork", "exec", "exit"):
            t = e.get("task") or e.get("child") or {}
            if ev == "exec":
                text = " ".join(e.get("argv", []))[:200] or t.get("comm", "")
            elif ev == "fork":
                text = (f"{e['parent']['comm']} ({e['parent']['pid']}) "
                        f"forks {e['child']['pid']}"
                        if e["parent"] and e["child"] else "fork")
            else:
                text = f"{t.get('comm', '?')} ({t.get('pid')}) exits " \
                       f"({e.get('code')})"
            marks.append({"k": kinds[0], "i": e["insts"], "text": text})
    for c in model["tools"]:
        for st in ("pending", "running", "completed", "error"):
            if st in c and lo <= c[st]["i"] < hi:
                marks.append({"k": "tool_" + st, "i": c[st]["i"],
                              "text": f"{c['tool']} {st}: {c['input']}"[:200]})
    marks.sort(key=lambda m: m["i"])
    procs = [{"idx": i, "name": model["procs"][i]["names"][-1],
              **{k: model["procs"][i][k] for k in ("tgid", "kind", "place",
                                                   "tree", "lineage")}}
             for i in used]
    remap = {p["idx"]: j for j, p in enumerate(procs)}
    segs["p"] = [remap[p] for p in segs["p"]]
    for p in procs:
        del p["idx"]
    tools = [c for c in model["tools"]
             if any(st in c and c[st]["i"] < hi for st in ("running",
                                                         "pending"))
             and (c.get("completed") or c.get("error") or {"i": hi})["i"]
             > lo]
    return {"procs": procs, "segs": segs, "marks": marks, "tools": tools}


def view_model(outdir, extra):
    blocks, metrics, dropped = block_metrics(outdir, extra)
    if not blocks:
        raise SystemExit(f"{outdir}: no stats blocks (run without "
                         "--stats-interval-insts?)")
    lo, hi = blocks[0]["s"], blocks[-1]["e"]
    sched = schedule(outdir, lo, hi)
    return {
        "version": 2,
        "name": outdir.name,
        "i0": lo, "i1": hi,
        "blocks": {"s": [b["s"] for b in blocks],
                   "e": [b["e"] for b in blocks],
                   "cyc": [int(b["cycles"]) for b in blocks]},
        "metrics": metrics,
        "zeroMetrics": dropped,
        "sched": sched,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir", type=Path)
    ap.add_argument("-o", "--output", type=Path,
                    help="HTML output (default: <outdir>/analysis/"
                    "window.html)")
    ap.add_argument("--metric", action="append", default=[],
                    metavar="KEY=STAT[/insts|/cycles]",
                    help="add a metric from any stat in stats.txt "
                    "(repeatable)")
    ap.add_argument("--fragment", action="store_true",
                    help="omit the <!doctype html> wrapper (for hosts that "
                    "add their own)")
    args = ap.parse_args()
    model = view_model(args.outdir, args.metric)
    out_dir = args.outdir / "analysis"
    out_dir.mkdir(exist_ok=True)
    blob = json.dumps(model, separators=(",", ":"))
    (out_dir / "window.view.json").write_text(blob)
    page = TEMPLATE.read_text().replace(PLACEHOLDER,
                                        blob.replace("</", "<\\/"))
    if not args.fragment:
        page = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, '
                'initial-scale=1">\n' + page + "\n</html>\n")
    html = args.output or out_dir / "window.html"
    html.write_text(page)
    n = len(model["blocks"]["s"])
    sched = model["sched"]
    print(f"{html} ({len(page) / 1e6:.1f} MB; {n} blocks, "
          f"{len(model['metrics'])} metrics"
          + (f", {len(sched['segs']['s'])} CPU slices, "
             f"{len(sched['marks'])} events" if sched else
             ", no task trace") + ")")


if __name__ == "__main__":
    main()
