# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD

"""Metrics view of a detailed window (host Python, stdlib).

    python3 analysis_scripts/tasktrace/window_view.py <outdir> [-o out.html]
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
build). The top-down shares are recomputed from gem5's counters and
checked against its formulas; the page stacks them per block, Level 1 to
3. --metric adds any other stat: KEY=STAT plots it raw per block,
KEY=STAT/insts per 1000 committed instructions and KEY=STAT/cycles as a
share of the block's cycles. Process labels and event kinds are the ones
of trace_analysis.py.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import stats_table
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
    ("walks_pki", "Memory", "Page-walk requests", "PKI",
     "Requests to the page-table walker per 1000 instructions, including "
     "ones squashed before a walk started and ones merged into a walk "
     "already in flight",
     pki(CORE + "mmu.walker.walks")),
    ("walks_done_pki", "Memory", "Completed page walks", "PKI",
     "Page-table walks that ran to completion per 1000 instructions, data "
     "and instruction side",
     pki(CORE + "mmu.walker.requestOrigin_Completed::Data",
         CORE + "mmu.walker.requestOrigin_Completed::Inst")),
    ("walks_done_d_pki", "Memory", "Completed data walks", "PKI",
     "Completed page-table walks for data accesses per 1000 instructions",
     pki(CORE + "mmu.walker.requestOrigin_Completed::Data")),
    ("walks_done_i_pki", "Memory", "Completed instruction walks", "PKI",
     "Completed page-table walks for instruction fetch per 1000 "
     "instructions",
     pki(CORE + "mmu.walker.requestOrigin_Completed::Inst")),
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

# Top-down accounting (src/cpu/o3/tdm.cc). Every share is recomputed from
# the counters behind gem5's formulas rather than read from the formulas,
# so that it can be summed over blocks, slices and edge settings like any
# other metric; block_metrics checks the result against gem5's formulas
# block by block. Keep topdown() in step with tdm.cc.
TD = CORE + "topDown."
RN = CORE + "rename."
TD_SLOTS = TD + "level1.slots"
TD_STATS = (
    TD_SLOTS, TD + "cycles", CORE + "commitStats0.numOps",
    RN + "renamedInsts", RN + "fetchBubbles", RN + "fetchLatencyBubbles",
    RN + "resteerBubbles", RN + "refillBubbles", RN + "status::Squashing",
    RN + "status::SerializeStall", CORE + "iew.branchMispredicts",
    CORE + "iew.memOrderViolationEvents", TD + "execStallCycles",
    TD + "loadStallCycles", TD + "loadStallL1Miss", TD + "loadStallL2Miss",
    TD + "storeStallCycles")


def topdown(s):
    """Every node of TOPDOWN_TREE as a share of the rename slots, from
    s(stat). A split whose events are all zero puts its parent's share in
    its last part, so every level adds up to 1."""
    slots = s(TD_SLOTS)
    width = slots / s(TD + "cycles")
    ops = s(CORE + "commitStats0.numOps")
    fe = s(RN + "fetchBubbles") / slots
    bs = (s(RN + "renamedInsts") - ops + s(RN + "refillBubbles")
          + width * s(RN + "status::Squashing")) / slots
    ret = ops / slots
    be = 1 - fe - bs - ret
    lat = s(RN + "fetchLatencyBubbles") / slots
    resteer = s(RN + "resteerBubbles") / slots
    br, mo = (s(CORE + "iew.branchMispredicts"),
              s(CORE + "iew.memOrderViolationEvents"))
    branch = bs * br / (br + mo) if br + mo else 0.0
    ser = width * s(RN + "status::SerializeStall") / slots
    load, store = s(TD + "loadStallCycles"), s(TD + "storeStallCycles")
    l1miss, l2miss = s(TD + "loadStallL1Miss"), s(TD + "loadStallL2Miss")
    stalls = load + store
    execs = s(TD + "execStallCycles")
    mem = (be - ser) * stalls / execs if execs else 0.0
    part = (lambda n: mem * n / stalls) if stalls else (lambda n: 0.0)
    return {
        "td_retiring": ret, "td_badspec": bs, "td_frontend": fe,
        "td_backend": be,
        "td_bs_branch": branch, "td_bs_clears": bs - branch,
        "td_fe_latency": lat, "td_fe_bandwidth": fe - lat,
        "td_fe_resteer": resteer,
        "td_be_serialize": ser, "td_be_memory": mem,
        "td_be_core": be - ser - mem,
        "td_mem_l1": part(load - l1miss), "td_mem_l2": part(l1miss - l2miss),
        "td_mem_ext": part(l2miss), "td_mem_store": part(store),
    }


# The breakdown: (key, label, gem5 formula it matches or None, description,
# children). The children of a node add up to it. Level 1 is stacked
# bottom up from Retiring.
TOPDOWN_TREE = [
    ("td_retiring", "Retiring", "level1.retiring",
     "Slots of committed micro-ops", []),
    ("td_badspec", "Bad speculation", "level1.badSpeculation",
     "Slots of squashed micro-ops, of rename's squashing cycles and of the "
     "refill after a squash", [
         ("td_bs_branch", "Branch mispredicts", "badSpec.branchMispredicts",
          "Bad speculation split by event count: branch mispredicts "
          "resolved at execute", []),
         ("td_bs_clears", "Machine clears", "badSpec.machineClears",
          "Bad speculation split by event count: memory-order violations "
          "and squashes from commit", []),
     ]),
    ("td_frontend", "Front-end bound", "level1.frontendBound",
     "Slots the back end could take but the front end left empty", [
         ("td_fe_latency", "Fetch latency", "frontend.fetchLatency",
          "Front-end bound slots of cycles where nothing reached rename",
          []),
         ("td_fe_bandwidth", "Fetch bandwidth", "frontend.fetchBandwidth",
          "Front-end bound slots of cycles where too few micro-ops reached "
          "rename", []),
     ]),
    ("td_backend", "Back-end bound", "level1.backendBound",
     "Slots lost to back-end stalls", [
         ("td_be_serialize", "Serialize", "backend.serializeBound",
          "Slots of cycles rename waited to serialize an instruction", []),
         ("td_be_memory", "Memory bound", "backend.memoryBound",
          "Back-end bound by the share of execution stalls waiting on "
          "loads or a full store queue", [
              ("td_mem_l1", "L1D bound", "memory.l1Bound",
               "No outstanding load past the L1D (hits, translations)", []),
              ("td_mem_l2", "L2 bound", "memory.l2Bound",
               "The deepest outstanding load in the L2", []),
              ("td_mem_ext", "Past L2", "memory.extMemBound",
               "The deepest outstanding load past the L2", []),
              ("td_mem_store", "Store bound", "memory.storeBound",
               "Store queue full", []),
          ]),
         ("td_be_core", "Core bound", "backend.coreBound",
          "The other execution stalls", []),
     ]),
]


def td_nodes(tree=TOPDOWN_TREE, level=1):
    """(key, label, formula, description, level) of every node, depth
    first."""
    for key, label, formula, desc, kids in tree:
        yield key, label, formula, desc, level
        yield from td_nodes(kids, level + 1)


def td_tree(tree=TOPDOWN_TREE):
    """The breakdown as page data: [{key, children}]."""
    return [{"key": k, "children": td_tree(kids)}
            for k, _, _, _, kids in tree]


# Top-down shares outside the breakdown, as (key, label, formula,
# description, level, the node they are part of): tdm.cc reports them, but
# they are not nodes of Yasin's tree, so no page stacks them.
TD_EXTRA = [
    ("td_fe_resteer", "Branch resteers", "frontend.branchResteers",
     "Part of fetch latency: after a squash's refill, before the first "
     "correct-path micro-op reached rename (not a node of the 2014 paper)",
     3, "td_fe_latency"),
]


def td_all():
    """(key, label, formula, description, level) of every top-down metric:
    the breakdown's nodes depth first, each TD_EXTRA entry after the node
    it is part of."""
    for node in td_nodes():
        yield node
        yield from (x[:5] for x in TD_EXTRA if x[5] == node[0])


def td_keys():
    return [n[0] for n in td_all()]


TD_LEVEL = {k: lvl for k, _, _, _, lvl in td_all()}
METRICS += [
    (key, "Top-down", label, "% slots",
     desc + (f" (Level {lvl})" if lvl > 1 else ""),
     ((TD_SLOTS,), lambda s, b, k=key: topdown(s)[k]))
    for key, label, _, desc, lvl in td_all()]
TD_GEM5 = {key: TD + f for key, _, f, _, _ in td_all() if f}


def read_dumps(run, wanted):
    """Per stats dump, {stat: float} restricted to `wanted`. Reads
    stats.txt or its values-only table (stats_table)."""
    dumps = []
    for d in stats_table.dumps(run):
        cur = {}
        for name, value in d.items():
            if name in wanted:
                try:
                    cur[name] = float(value)
                except ValueError:
                    pass
        dumps.append(cur)
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


def block_metrics(outdir, extra, skip_insts=0):
    """Per-block and whole-window metrics of a detailed window. With
    skip_insts, the blocks that start in the window's first skip_insts
    instructions are left out of everything, the window values included,
    as if they had been part of the warm-up."""
    with open(outdir / "intervals.csv") as f:
        intervals = [{k: int(v) for k, v in r.items()}
                     for r in csv.DictReader(f)]
    metrics = METRICS + [custom_metric(m) for m in extra]
    wanted = {x for m in metrics for x in m[5][0]}
    wanted |= {CORE + "numCycles", CORE + "commitStats0.numInsts"}
    wanted |= set(TD_STATS) | set(TD_GEM5.values())
    dumps = read_dumps(outdir, wanted)
    # One dump per interval; gem5's exit dump has no interval row.
    blocks = []
    for iv, d in zip(intervals, dumps):
        b = {"s": iv["insts_start"], "e": iv["insts_end"],
             "t0": iv["tick_start"],
             "insts": iv["insts_end"] - iv["insts_start"],
             "ticks": iv["tick_end"] - iv["tick_start"],
             "cycles": d.get(CORE + "numCycles", 0), "stats": d}
        if b["insts"] > 0 and b["cycles"] > 0:
            blocks.append(b)
    if skip_insts and blocks:
        first = blocks[0]["s"]
        blocks = [b for b in blocks if b["s"] >= first + skip_insts]
    seen = set().union(*(b["stats"] for b in blocks)) if blocks else set()
    # Stats that are already per-block averages or ratios cannot be summed
    # over blocks; their window value is the cycle-weighted mean.
    averaged = {CORE + "lsq0.lqAvgOccupancy", CORE + "lsq0.sqAvgOccupancy"}
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
        # Top-down nodes stay when zero: the breakdown needs all of them.
        if key != "ipc" and key not in TD_LEVEL and not any(vals):
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
        if key in TD_LEVEL:
            out[-1]["level"] = TD_LEVEL[key]
    if TD_SLOTS in seen:
        check_topdown(outdir, blocks)
    return blocks, out, dropped


def check_topdown(outdir, blocks, tol=1e-4):
    """Warn when the recomputed top-down shares differ from gem5's own
    formulas in some block: topdown() has drifted from tdm.cc."""
    worst = {}
    for b in blocks:
        d = b["stats"]
        if not d.get(TD_SLOTS):
            continue
        try:
            ours = topdown(lambda n: d.get(n, 0.0))
        except ZeroDivisionError:
            continue
        for key, stat in TD_GEM5.items():
            # gem5 prints nan for a split with no events, and leaves out
            # a zero
            g = d.get(stat, 0.0)
            if g == g and abs(ours[key] - g) > worst.get(key, tol):
                worst[key] = abs(ours[key] - g)
    if worst:
        print(f"warning: {outdir}: top-down shares differ from gem5's "
              "formulas (topdown() out of step with tdm.cc?): "
              + ", ".join(f"{k} by {v:.2g}" for k, v in worst.items()),
              file=sys.stderr)


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
            # A kernel run ending in another process is also a process
            # switch: one mark per kind, the process switch first so that
            # it is the one hovering finds.
            for k in sorted(kinds, key=lambda k: k != "switch_process"):
                t = text
                if k == "switch_process" and e.get("via"):
                    v = e["via"]
                    t = (f"{v['comm']} ({v['pid']}) → {n['comm']} "
                         f"({n['pid']}) via {p['comm']} ({p['pid']})")
                marks.append({"k": k, "i": e["insts"], "text": t,
                              "cause": ta.switch_cause(e, tree, k)})
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
        "topdown": td_tree() if any("level" in m for m in metrics)
        else None,
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
