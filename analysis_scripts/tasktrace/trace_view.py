# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD

"""Interactive schedule view of a --task-trace run (host Python, stdlib).

    python3 analysis_scripts/tasktrace/trace_view.py <outdir> [-o out.html]

Turns <outdir>/tasktrace.jsonl into a compact view model (who ran on the
CPU when, process lifecycle events, OpenCode tool calls) and writes
<outdir>/analysis/schedule.view.json plus a self-contained
<outdir>/analysis/schedule.html built from trace_view.html. The page can
also load any other schedule.view.json. Process labels (kind, where,
launch tree, lineage) and tool calls come from trace_analysis.py, so both
tools agree.
"""

import argparse
import json
from pathlib import Path

import trace_analysis as ta

TEMPLATE = Path(__file__).with_name("trace_view.html")
PLACEHOLDER = "__TRACE_DATA__"


def view_model(outdir):
    events = ta.load_events(outdir / "tasktrace.jsonl")
    tree = ta.Tree(events)
    start = next(e for e in events if e["event"] == "start")
    t0, i0 = start["tick"], start["insts"]
    ms = lambda tick: round((tick - t0) / 1e9, 6)

    procs, proc_index = [], {}

    def proc(task):
        tgid = task["tgid"]
        if tgid not in proc_index:
            path, argv = tree.exec.get(tgid, ("", []))
            proc_index[tgid] = len(procs)
            kind = tree.kind(task)
            user = kind == "user"
            procs.append({"tgid": tgid, "ppid": tree.parent.get(tgid),
                          "names": tree.names.get(tgid, [task["process"]]),
                          "kind": kind,
                          "place": tree.place(tgid) if user else kind,
                          "tree": tree.tree(tgid) if user else kind,
                          "lineage": tree.lineage(tgid) if user else "",
                          "exec": path,
                          "argv": " ".join(argv)[:400], "insts": 0,
                          "switchIns": 0})
        return proc_index[tgid]

    threads, thread_index = [], {}

    def thread(task):
        key = f"{task['comm']} ({task['pid']})"
        if key not in thread_index:
            thread_index[key] = len(threads)
            threads.append(key)
        return thread_index[key]

    # Who ran when: between two switches the CPU belongs to the previous
    # switch's outgoing task.
    # `u` is the user-mode share of each slice (the rest is kernel mode on
    # the task's behalf) and `sc` the scheduler's own instructions at the
    # slice's end (from __schedule() entry to the switch); both are omitted
    # for traces without `uinsts`.
    has_user = "uinsts" in start
    segs = {"s": [], "e": [], "p": [], "th": [], "ts": [], "te": []}
    if has_user:
        segs.update({"u": [], "sc": []})
    cur = (i0, t0, start.get("uinsts"))
    last = None
    for e in events:
        if e["event"] != "switch":
            continue
        if e["prev"]:
            p = proc(e["prev"])
            segs["s"].append(cur[0])
            segs["e"].append(e["insts"])
            segs["p"].append(p)
            segs["th"].append(thread(e["prev"]))
            segs["ts"].append(ms(cur[1]))
            segs["te"].append(ms(e["tick"]))
            procs[p]["insts"] += e["insts"] - cur[0]
            if has_user:
                u = e["uinsts"] - cur[2]
                segs["u"].append(u)
                segs["sc"].append(e.get("sched_insts", 0))
                procs[p]["user"] = procs[p].get("user", 0) + u
        if e["next"]:
            procs[proc(e["next"])]["switchIns"] += 1
        cur = (e["insts"], e["tick"], e.get("uinsts"))
        last = e
    end_i = max(e["insts"] for e in events)
    end_t = max(e["tick"] for e in events)
    # The last task runs to the end of the trace; without any switch the
    # trace never names the task that was running.
    tail = last["next"] if last else ta.NOT_RECORDED
    if tail and end_i > cur[0]:
        p = proc(tail)
        segs["s"].append(cur[0])
        segs["e"].append(end_i)
        segs["p"].append(p)
        segs["th"].append(thread(tail))
        segs["ts"].append(ms(cur[1]))
        segs["te"].append(ms(end_t))
        procs[p]["insts"] += end_i - cur[0]
        if has_user:
            # None when the stats do not cover the end of the trace.
            uend = max(events, key=lambda e: e["insts"]).get("uinsts")
            u = None if uend is None or cur[2] is None else uend - cur[2]
            segs["u"].append(u)
            segs["sc"].append(0)
            procs[p]["user"] = procs[p].get("user", 0) + (u or 0)

    D = {"procs": procs}
    marks = []
    for e in events:
        ev = e["event"]
        if ev == "fork" and e["child"] and e["parent"]:
            kind = ("thread" if e["child"]["tgid"] == e["parent"]["tgid"]
                    else "process")
            marks.append({"k": "fork", "i": e["insts"], "t": ms(e["tick"]),
                          "p": proc(e["parent"]),
                          "text": f"forks {kind} {e['child']['pid']}"})
        elif ev == "exec" and e["task"]:
            marks.append({"k": "exec", "i": e["insts"], "t": ms(e["tick"]),
                          "p": proc(e["task"]),
                          "text": " ".join(e.get("argv", []))[:300]
                          or e["task"]["comm"]})
        elif ev == "exit" and e["task"]:
            marks.append({"k": "exit", "i": e["insts"], "t": ms(e["tick"]),
                          "p": proc(e["task"]),
                          "text": f"{e['task']['comm']} exits ({e['code']})"})
        elif ev == "rename" and e["task"]:
            marks.append({"k": "rename", "i": e["insts"], "t": ms(e["tick"]),
                          "p": proc(e["task"]),
                          "text": f"thread {e['task']['pid']} renamed "
                                  f"{e['task']['comm']}"})

        elif ev == "write" and e["file"] == "cgroup.procs" and e["task"]:
            marks.append({"k": "fence", "i": e["insts"], "t": ms(e["tick"]),
                          "p": proc(e["task"]),
                          "text": f"moves pid {(e['data'] or '').strip()} "
                                  f"into {e.get('path') or 'a cgroup'}"})

    tools = []
    for c in ta.tool_calls(events):
        row = {"tool": c.get("tool", ""),
               "input": c.get("filePath") or c.get("command", "")}
        for st in ("pending", "running", "completed", "error", "logged"):
            if st in c:
                row[st] = {"i": c[st][0], "t": ms(c[st][1])}
        lo = c["running"][0] if "running" in c else None
        end = c.get("completed") or c.get("error")
        hi = end[0] if end else end_i
        row["kind"] = "in-process"
        if lo is not None:
            # A subprocess call: a descendant of the process that recorded
            # it ran while it was running (as in trace_analysis.py).
            writer = c.get("writer")
            spawned = sorted({D["procs"][p]["names"][-1]
                              for s0, e0, p in zip(segs["s"], segs["e"],
                                                   segs["p"])
                              if e0 > lo and s0 < hi and writer is not None
                              and D["procs"][p]["tgid"] != writer
                              and writer in tree.ancestors(
                                  D["procs"][p]["tgid"])})
            if spawned:
                row["kind"] = "subprocess (" + ", ".join(spawned) + ")"
            # The tool's own file I/O: the first read or write of its file
            # while it runs; becomes an `io` mark on the harness lane.
            fp = c.get("filePath")
            for e in events if fp else ():
                if (e["event"] in ("read", "write") and lo <= e["insts"] <= hi
                        and e.get("path", "").endswith(fp)):
                    row["io"] = {"i": e["insts"], "t": ms(e["tick"]),
                                 "k": e["event"]}
                    marks.append({"k": "io", "i": e["insts"],
                                  "t": ms(e["tick"]), "p": proc(e["task"]),
                                  "text": f"{c.get('tool')} {e['event']}s "
                                          f"{e['path']} ({e['count']} B)"})
                    break
        tools.append(row)

    sw_cost = []
    if has_user:
        causes = {}
        for e in events:
            if e["event"] == "switch" and "sched_insts" in e:
                causes.setdefault(ta.switch_cause(e, tree), []).append(e)
        for k, es in sorted(causes.items(), key=lambda kv: -len(kv[1]))[:12]:
            xs = [e["sched_insts"] for e in es]
            sw_cost.append({"cause": k, "n": len(es),
                            "p50": ta.pctl(xs, 0.5), "p90": ta.pctl(xs, 0.9),
                            "ns": round(sum(e["sched_ticks"] for e in es)
                                        / len(es) / 1000, 1)})

    return {
        "version": 3,
        "switchCost": sw_cost,
        "name": outdir.name,
        "kaslrSlide": hex(start.get("kaslr_slide", 0)),
        "i0": i0, "i1": end_i, "t1": ms(end_t),
        "procs": procs, "threads": threads, "segs": segs,
        "marks": marks, "tools": tools,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir", type=Path)
    ap.add_argument("-o", "--output", type=Path,
                    help="HTML output (default: <outdir>/analysis/"
                    "schedule.html)")
    ap.add_argument("--fragment", action="store_true",
                    help="omit the <!doctype html> wrapper (for hosts that "
                    "add their own)")
    args = ap.parse_args()
    model = view_model(args.outdir)
    out_dir = args.outdir / "analysis"
    out_dir.mkdir(exist_ok=True)
    blob = json.dumps(model, separators=(",", ":"))
    (out_dir / "schedule.view.json").write_text(blob)
    page = TEMPLATE.read_text().replace(PLACEHOLDER,
                                        blob.replace("</", "<\\/"))
    if not args.fragment:
        page = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, '
                'initial-scale=1">\n' + page + "\n</html>\n")
    html = args.output or out_dir / "schedule.html"
    html.write_text(page)
    print(f"{html} ({len(page) / 1e6:.1f} MB; {len(model['segs']['s'])} "
          f"segments, {len(model['procs'])} processes, "
          f"{len(model['tools'])} tool calls)")


if __name__ == "__main__":
    main()
