# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD

"""Analyse a --task-trace run of virt_run.py (host Python, stdlib only).

    python3 configs/garfield/arm/trace_analysis.py <outdir> [--window K]

Reads <outdir>/tasktrace.jsonl and, when the run used
--stats-interval-insts, <outdir>/intervals.csv and the per-interval blocks of
<outdir>/stats.txt. Writes <outdir>/analysis/:

  processes.csv  one row per process seen: names, exec path and argv, role,
                 instructions it ran inside the trace (split into user and
                 kernel mode), times switched in
  writes.csv     every recorded write(): the traced process's, and writes
                 to cgroup.procs (a task entering a cgroup) from any process
  reads.csv      every recorded read() of the traced process (no data)
  containers.csv one row per namespace set: its label and member processes
  switches.csv   context switches counted by cause (who switched to whom),
                 with what the scheduler spent on each: instructions and
                 time from __schedule() entry to the switch, and the kernel
                 share of the time slice the switch ended
  tools.csv      one row per OpenCode tool call: name, input, the trace
                 position of each state change, and who ran in between
  blocks.csv     per stats interval: metrics, the dominant process and role,
                 instruction share per role, and the events inside it
  aligned.csv    per event kind, each metric averaged over the intervals at
                 offsets -K..+K from the interval holding the event
  summary.md     the headline numbers

Roles (ROLES, in display order):
  harness        the OpenCode process (all its threads)
  harness-child  anything else OpenCode started, e.g. its snapshot git
  tool           bash.fence-real / rg.fence-real and their descendants:
                 OpenCode's subprocess tools
  framework      other benchmark processes inside the containers (the tool
                 server, the orchestrator's model proxy, faketime)
  replay         user processes on the guest host: the model-free replay
                 driver and what it runs (its `docker inspect` polls,
                 watch_rounds.sh, sleep)
  daemon         system daemons: dockerd, containerd and its shims, runc,
                 systemd services
  kernel         kernel threads (PF_KTHREAD)
  idle           pid 0
  other          anything unclassified
Containers come from the namespace-set pointer (`ns`) the tracer records;
traces from before that field existed fall back to names.
"""

import argparse
import bisect
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HARNESS = "opencode"
TOOL_ROOTS = ("bash.fence-real", "rg.fence-real")
DAEMONS = ("dockerd", "containerd", "runc", "docker-proxy", "systemd",
           "haveged", "agetty", "dbus", "cron", "sshd")
ROLES = ("harness", "harness-child", "tool", "framework", "replay", "daemon",
         "kernel", "idle", "other")

CORE = "board.processor.start.core."
CACHES = "board.cache_hierarchy."
STATS = {
    "cycles": CORE + "numCycles",
    "insts": "simInsts",
    "commit_insts": CORE + "commitStats0.numInsts",
    "user_insts": CORE + "commitStats0.numUserInsts",
    "l1i_miss": CACHES + "l1icaches.overallMisses::total",
    "l1d_miss": CACHES + "l1dcaches.overallMisses::total",
    "l2_miss": CACHES + "l2caches.overallMisses::total",
    "br_miss": CORE + "branchPred.condIncorrect",
    "btb_miss_mispred": CORE + "branchPred.mispredictDueToBTBMiss_0::total",
    "itlb_miss": CORE + "mmu.itb.misses",
    "dtlb_miss": CORE + "mmu.dtb.misses",
    "walks": CORE + "mmu.walker.walks",
}
METRICS = ("ipc", "user_frac", "l1i_mpki", "l1d_mpki", "l2_mpki",
           "br_mpki", "btb_mpki", "itlb_mpki", "dtlb_mpki", "walks_pki")


def load_events(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class Tree:
    """Process names, parentage and container of every task in the trace,
    from the start-up snapshot and every task record."""

    def __init__(self, events):
        self.parent = {}
        self.names = defaultdict(list)
        self.exec = {}
        self.ns, self.cg, self.kthread = {}, {}, {}
        for e in events:
            tasks = list(e.get("tasks") or [])
            tasks += [e[k] for k in ("prev", "next", "task", "parent", "child")
                      if e.get(k)]
            for t in tasks:
                self._note(t)
            if e["event"] == "fork" and e["child"] and e["parent"]:
                c, p = e["child"], e["parent"]
                if c["tgid"] != p["tgid"]:
                    self.parent[c["tgid"]] = p["tgid"]
            if e["event"] == "exec" and e["task"]:
                self.exec[e["task"]["tgid"]] = (
                    e.get("path", ""), e.get("argv", []))
        self.host_ns = self.ns.get(1)
        self.harness_ns = next((self.ns[t] for t, n in self.names.items()
                                if HARNESS in n and t in self.ns), None)

    def _note(self, t):
        tgid = t["tgid"]
        self.parent.setdefault(tgid, t["ppid"])
        if t["process"] not in self.names[tgid]:
            self.names[tgid].append(t["process"])
        # An exiting task has released its namespaces (ns 0): keep the
        # last real value.
        if t.get("ns") and int(t["ns"], 16):
            self.ns[tgid] = t["ns"]
            self.cg[tgid] = t["cg"]
        if "kthread" in t:
            self.kthread[tgid] = self.kthread.get(tgid, False) or t["kthread"]

    def ancestors(self, tgid):
        seen, out = set(), []
        while tgid in self.parent and tgid not in seen and tgid > 1:
            seen.add(tgid)
            tgid = self.parent[tgid]
            out.append(tgid)
        return out

    def is_kernel(self, task):
        tgid = task["tgid"]
        if tgid in self.kthread or "kthread" in task:
            return task.get("kthread") or self.kthread.get(tgid, False)
        # Traces without the flag: kthreadd (pid 2) and its children. A
        # null mm (`kernel_thread`) is not enough: an exiting user process
        # drops its mm before its last context switch.
        return tgid == 2 or self.parent.get(tgid) == 2

    def container(self, tgid):
        """'host', 'opencode-container', 'container-<id>' or 'unknown'.

        A container is a namespace set entered under a containerd-shim.
        Host services that systemd sandboxes into private namespaces
        (systemd-resolved, ...) are still on the host.
        """
        ns = self.ns.get(tgid)
        if ns is None:
            return "unknown"
        if ns == self.host_ns:
            return "host"
        if ns == self.harness_ns:
            return "opencode-container"
        lineage = self.ancestors(tgid)
        if any(n.startswith("containerd-shim")
               for t in lineage for n in self.names.get(t, [])):
            return "container-" + ns[-4:]
        return "host"

    def role(self, task):
        if task is None:
            return "unknown"
        if task["pid"] == 0:
            return "idle"
        if self.is_kernel(task):
            return "kernel"
        tgid = task["tgid"]
        # A process's role follows its latest name: a fork child is named
        # after its parent until it execs.
        process = (self.names.get(tgid) or [task["process"]])[-1]
        if process == HARNESS:
            return "harness"
        lineage = [tgid] + self.ancestors(tgid)
        names = {n for t in lineage for n in self.names.get(t, [])}
        names.add(task["comm"])
        if names & set(TOOL_ROOTS):
            return "tool"
        if any(HARNESS in self.names.get(t, []) for t in lineage[1:]):
            return "harness-child"
        if process.startswith(DAEMONS):
            return "daemon"
        where = self.container(tgid)
        if where == "host":
            return "replay"
        if where != "unknown":
            return "framework"
        # Traces without namespaces: the replay driver's docker CLI calls.
        return "replay" if process == "docker" else "other"


def running_segments(events):
    """([(insts_start, insts_end, task)], [user_insts]) from the switch
    events: the time slices of the CPU, and for each the instructions that
    ran in user mode (None for traces without `uinsts`). The rest of a
    slice is kernel mode on behalf of that task: system calls, interrupts,
    page faults and the scheduler itself. Kernel threads and the idle task
    are all kernel mode."""
    switches = [e for e in events if e["event"] == "switch"]
    segs, user = [], []
    first = next((e for e in events if e["event"] == "start"), events[0])
    start, ustart = first["insts"], first.get("uinsts")

    def add(end, uend, task):
        segs.append((start, end, task))
        user.append(None if uend is None or ustart is None
                    else uend - ustart)

    for e in switches:
        if e["prev"]:
            add(e["insts"], e.get("uinsts"), e["prev"])
        start, ustart = e["insts"], e.get("uinsts")
    if switches and switches[-1]["next"]:
        last = max(events, key=lambda e: e["insts"])
        add(last["insts"], last.get("uinsts"), switches[-1]["next"])
    return segs, user


def user_between(segs, user, lo, hi):
    """User-mode instructions in the instruction range [lo, hi), assuming
    each slice's user instructions are spread evenly over it (exact for
    whole slices; the order inside a slice is not recorded)."""
    total = 0.0
    for (s, e, _), u in zip(segs, user):
        a, b = max(s, lo), min(e, hi)
        if b > a and u is not None and e > s:
            total += u * (b - a) / (e - s)
    return total


def pctl(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


def event_kinds(e, tree=None):
    """The analysis kinds an event counts as."""
    ev = e["event"]
    if ev == "switch":
        p, n = e["prev"] or {}, e["next"] or {}
        if tree and p and n:
            kern = tree.role(p) in ("kernel", "idle") or \
                tree.role(n) in ("kernel", "idle")
        else:
            kern = p.get("kernel_thread") or n.get("kernel_thread")
        if kern:
            return ["switch_kernel"]
        return ["switch_thread" if e["same_mm"] else "switch_process"]
    if ev == "fork":
        c, p = e["child"] or {}, e["parent"] or {}
        return ["fork_thread" if c.get("tgid") == p.get("tgid")
                else "fork_process"]
    if ev in ("exec", "exit", "write", "read", "rename", "tool_start",
              "tool_end", "fence"):
        return [ev]
    return []


def switch_cause(e, tree):
    """Who switched to whom, by role: 'within harness' for a switch between
    threads of one process, else the two roles, e.g. 'harness -> replay'."""
    p, n = e["prev"], e["next"]
    if not p or not n:
        return "unknown"
    a, b = tree.role(p), tree.role(n)
    if e["same_mm"]:
        return f"within {a}"
    return f"{a} -> {b}"


# Where a tool part's JSON object begins: as a row of OpenCode's part table
# ({"type":"tool",...}) or nested in an event row ({"id":"prt_...",...}).
PART_START = re.compile(rb'\{"(?:type":"tool"|id":"prt_)')
PART_FIELDS = {
    "tool": re.compile(rb'"tool":"([^"]+)"'),
    "callID": re.compile(rb'"callID":"([^"]+)"'),
    "status": re.compile(rb'"status":"([a-z]+)"'),
    "filePath": re.compile(rb'"filePath":"([^"]{0,200})"'),
    "command": re.compile(rb'"command":"((?:[^"\\]|\\.){0,200})'),
}
STATUSES = ("pending", "running", "completed", "error")


def json_object(data, i):
    """The bytes of the JSON object starting at data[i], and whether it is
    complete (a WAL page can cut a row short)."""
    depth, in_str, esc = 0, False, False
    for j in range(i, len(data)):
        c = data[j]
        if in_str:
            if esc:
                esc = False
            elif c == 0x5C:      # backslash
                esc = True
            elif c == 0x22:      # quote
                in_str = False
        elif c == 0x22:
            in_str = True
        elif c == 0x7B:          # {
            depth += 1
        elif c == 0x7D:          # }
            depth -= 1
            if depth == 0:
                return data[i:j + 1], True
    return data[i:], False


def tool_part(data, i):
    """Fields of the tool part whose object starts at data[i], or None."""
    raw, complete = json_object(data, i)
    if complete:
        try:
            obj = json.loads(raw)
        except ValueError:
            complete = False
    if complete:
        if obj.get("type") != "tool":
            return None
        state = obj.get("state") or {}
        inp = state.get("input") or {}
        times = state.get("time") or {}
        return {"tool": obj.get("tool", ""), "callID": obj.get("callID", ""),
                "status": state.get("status", ""),
                "filePath": inp.get("filePath", ""),
                "command": inp.get("command", ""),
                "start_ms": times.get("start"), "end_ms": times.get("end")}
    # Truncated: take what the visible part says, without its time.
    if not raw.startswith(b'{"type":"tool"') and b'"type":"tool"' not in raw:
        return None
    f = {}
    for k, r in PART_FIELDS.items():
        m = r.search(raw)
        f[k] = m.group(1).decode("utf-8", "replace") if m else ""
    f["start_ms"] = f["end_ms"] = None
    return f


def tool_calls(events):
    """OpenCode tool calls, from its own writes.

    OpenCode keeps every message part in SQLite and rewrites the part's row
    on each state change (pending -> running -> completed | error); with
    WAL journaling every change is a write() of the page holding the row
    to opencode.db-wal, which the tracer records. A page also carries other
    rows, some stale, so a state counts from its FIRST appearance. The JSON
    event line OpenCode prints for a finished call (its --format json log)
    is recorded as `logged`.
    """
    calls = {}
    for e in events:
        if e["event"] != "write" or not e["data"]:
            continue
        data = e["data"].encode("latin-1")
        for m in PART_START.finditer(data):
            f = tool_part(data, m.start())
            if not f or not f["callID"] or f["status"] not in STATUSES:
                continue
            c = calls.setdefault(f["callID"], {"call": f["callID"]})
            for k in ("tool", "filePath", "command"):
                if f[k] and not c.get(k):
                    c[k] = f[k]
            if f["start_ms"] and f["end_ms"]:
                c.setdefault("start_ms", f["start_ms"])
                c.setdefault("end_ms", f["end_ms"])
            key = "logged" if e["file"].endswith(".log") else f["status"]
            if key not in c:
                c[key] = (e["insts"], e["tick"])
    return sorted(calls.values(),
                  key=lambda c: (c.get("running") or c.get("pending")
                                 or c.get("completed") or (0, 0))[0])


def load_blocks(outdir):
    """Stats blocks joined to intervals.csv, or [] without intervals."""
    ivs = outdir / "intervals.csv"
    if not ivs.exists():
        return []
    with open(ivs) as f:
        intervals = list(csv.DictReader(f))
    dumps, cur = [], None
    with open(outdir / "stats.txt") as f:
        for line in f:
            if line.startswith("---------- Begin"):
                cur = {}
            elif line.startswith("---------- End"):
                dumps.append(cur)
            elif cur is not None:
                parts = line.split()
                if len(parts) >= 2:
                    cur[parts[0]] = parts[1]
    # The run dumps once per interval; gem5's exit dump (e.g. after a tail)
    # follows and has no interval row.
    blocks = []
    for iv, d in zip(intervals, dumps):
        b = {k: int(v) for k, v in iv.items()}
        for name, stat in STATS.items():
            try:
                # gem5 omits a stat from a block when it stayed at zero.
                b[name] = float(d.get(stat, "0"))
            except ValueError:
                b[name] = float("nan")
        n = b["insts"] or 1
        k = n / 1000.0
        b["ipc"] = b["insts"] / b["cycles"] if b["cycles"] else float("nan")
        b["user_frac"] = (b["user_insts"] / b["commit_insts"]
                          if b["commit_insts"] else float("nan"))
        b["l1i_mpki"] = b["l1i_miss"] / k
        b["l1d_mpki"] = b["l1d_miss"] / k
        b["l2_mpki"] = b["l2_miss"] / k
        b["br_mpki"] = b["br_miss"] / k
        b["btb_mpki"] = b["btb_miss_mispred"] / k
        b["itlb_mpki"] = b["itlb_miss"] / k
        b["dtlb_mpki"] = b["dtlb_miss"] / k
        b["walks_pki"] = b["walks"] / k
        blocks.append(b)
    return blocks


def mean(xs):
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


def fmt(x):
    return f"{x:.4g}" if isinstance(x, float) else x


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: fmt(r.get(k, "")) for k in fields})


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--window", type=int, default=3,
                    help="intervals before/after an event in aligned.csv")
    args = ap.parse_args()
    out = args.outdir / "analysis"
    out.mkdir(exist_ok=True)

    events = load_events(args.outdir / "tasktrace.jsonl")
    tree = Tree(events)
    segs, user = running_segments(events)
    has_user = any(u is not None for u in user)
    t0 = events[0]["tick"]
    t1 = max(e["tick"] for e in events)
    i0 = events[0]["insts"]
    i1 = max(e["insts"] for e in events)

    # ---- per process ------------------------------------------------------
    ran, ran_user, switched_in = Counter(), Counter(), Counter()
    task_of = {}
    for (s, e, t), u in zip(segs, user):
        ran[t["tgid"]] += e - s
        ran_user[t["tgid"]] += u or 0
        task_of.setdefault(t["tgid"], t)
    for e in events:
        if e["event"] == "switch" and e["next"]:
            switched_in[e["next"]["tgid"]] += 1
            task_of.setdefault(e["next"]["tgid"], e["next"])
        for key in ("task", "child", "parent"):
            if e.get(key):
                task_of.setdefault(e[key]["tgid"], e[key])
        for t in e.get("tasks") or []:
            if t["pid"] == t["tgid"]:
                task_of.setdefault(t["tgid"], t)
    procs = []
    for tgid, t in task_of.items():
        path, argv = tree.exec.get(tgid, ("", []))
        procs.append({
            "tgid": tgid, "ppid": tree.parent.get(tgid, ""),
            "names": "|".join(tree.names.get(tgid, [])),
            "role": tree.role(t), "container": tree.container(tgid),
            "insts": ran[tgid], "user_insts": ran_user[tgid],
            "kernel_insts": ran[tgid] - ran_user[tgid] if has_user else "",
            "switch_ins": switched_in[tgid],
            "exec_path": path, "argv": " ".join(argv)[:300],
        })
    procs.sort(key=lambda r: (-r["insts"], r["tgid"]))
    write_csv(out / "processes.csv", procs,
              ["tgid", "ppid", "names", "role", "container", "insts",
               "user_insts", "kernel_insts", "switch_ins", "exec_path",
               "argv"])

    role_insts, role_user = Counter(), Counter()
    for (s, e, t), u in zip(segs, user):
        role_insts[tree.role(t)] += e - s
        role_user[tree.role(t)] += u or 0

    # ---- containers -------------------------------------------------------
    members = defaultdict(Counter)
    for tgid in tree.names:
        if tgid in tree.ns:
            members[tree.container(tgid)][tree.names[tgid][-1]] += 1
    containers = [{"container": k, "processes": sum(v.values()),
                   "members": " ".join(f"{n}×{c}" if c > 1 else n
                                       for n, c in v.most_common(12))}
                  for k, v in sorted(members.items())]
    write_csv(out / "containers.csv", containers,
              ["container", "processes", "members"])

    # ---- file I/O ---------------------------------------------------------
    def io_row(e):
        r = {"tick": e["tick"], "insts": e["insts"], "tid": e["task"]["pid"],
             "comm": e["task"]["comm"], "process": e["task"]["process"],
             "file": e["file"], "path": e.get("path", ""),
             "count": e["count"]}
        if e["event"] == "write":
            data = (e["data"] or "").encode("latin-1").decode(
                "utf-8", "replace")
            r["head"] = data[:200].replace("\n", "\\n")
        else:
            r["pos"] = e.get("pos")
        return r
    writes = [io_row(e) for e in events if e["event"] == "write"]
    reads = [io_row(e) for e in events if e["event"] == "read"]
    write_csv(out / "writes.csv", writes,
              ["tick", "insts", "tid", "comm", "process", "file", "path",
               "count", "head"])
    write_csv(out / "reads.csv", reads,
              ["tick", "insts", "tid", "comm", "file", "path", "count",
               "pos"])

    # A write of a pid to a cgroup.procs file moves that task into the
    # cgroup: OpenCode's tools fence does this before each subprocess tool.
    fence_entries = [e for e in events if e["event"] == "write"
                     and e["file"] == "cgroup.procs"]
    for e in fence_entries:
        events.append({"event": "fence", "insts": e["insts"],
                       "tick": e["tick"]})
    # Is the fence effective? Fenced tools must sit in a different cgroup
    # set from the harness.
    harness_cg = {tree.cg[t] for t, n in tree.names.items()
                  if HARNESS in n and t in tree.cg}
    fenced = [t for t, n in tree.names.items()
              if set(n) & set(TOOL_ROOTS) and t in tree.cg]
    fence_note = ("no fenced tool process in this trace" if not fenced else
                  "fence effective: fenced tools are in their own cgroup"
                  if all(tree.cg[t] not in harness_cg for t in fenced) else
                  "fence NOT effective: fenced tools share the harness's "
                  "cgroup (tool/harness split by process name only)")

    # ---- tool calls -------------------------------------------------------
    tools = tool_calls(events)
    for c in tools:
        for st in ("pending", "running", "completed", "error", "logged"):
            if st in c:
                c[st + "_insts"], c[st + "_tick"] = c[st]
        end = c.get("completed") or c.get("error")
        # Observed, not assumed from the tool's name: a call is a
        # subprocess call if a fenced tool process (bash.fence-real,
        # rg.fence-real) ran while it was running.
        c["kind"] = "in-process"
        if "running" in c:
            lo = c["running"][0]
            hi = end[0] if end else i1
            spawned = sorted({t["process"] for s0, e0, t in segs
                              if e0 > lo and s0 < hi
                              and tree.role(t) == "tool"})
            if spawned:
                c["kind"] = "subprocess (" + ", ".join(spawned) + ")"
        if "running" in c and end:
            lo, hi = c["running"][0], end[0]
            c["run_insts"] = hi - lo
            c["run_ms"] = (end[1] - c["running"][1]) / 1e9
            share, threads = Counter(), Counter()
            for s0, e0, t in segs:
                a0, b0 = max(s0, lo), min(e0, hi)
                if b0 > a0:
                    share[tree.role(t)] += b0 - a0
                    threads[f"{t['process']}/{t['comm']}"] += b0 - a0
            tot = sum(share.values()) or 1
            for r in ROLES:
                c["run_share_" + r] = share[r] / tot
            agent = tot - share["replay"]
            c["run_agent_insts"] = agent
            if has_user:
                u = user_between(segs, user, lo, hi)
                c["run_user_insts"] = round(u)
                c["run_kernel_insts"] = round(hi - lo - u)
            c["run_top_threads"] = " ".join(
                f"{k}:{v / tot:.0%}" for k, v in threads.most_common(5))
            # The tool's own file I/O: the first read or write of its file
            # by the harness while it runs.
            if c.get("filePath"):
                for e in events:
                    if (e["event"] in ("read", "write") and lo <= e["insts"]
                            <= hi and e.get("path", "").endswith(
                                c["filePath"])):
                        c["io"] = e["event"]
                        c["io_insts"] = e["insts"]
                        break
        c["input"] = c.get("filePath") or c.get("command", "")
    write_csv(out / "tools.csv", tools,
              ["call", "tool", "kind", "input", "pending_insts",
               "running_insts", "io", "io_insts", "completed_insts",
               "error_insts", "logged_insts", "run_insts", "run_agent_insts",
               "run_ms", "run_user_insts", "run_kernel_insts", "start_ms",
               "end_ms", *("run_share_" + r for r in ROLES),
               "run_top_threads"])
    # Tool-call edges become events too, for blocks.csv and aligned.csv.
    for c in tools:
        for st, kind in (("running", "tool_start"), ("completed", "tool_end"),
                         ("error", "tool_end")):
            if st in c:
                events.append({"event": kind, "insts": c[st][0],
                               "tick": c[st][1]})

    # ---- context switches by cause ----------------------------------------
    # Per cause: how many, what the scheduler spent (instructions and time
    # from __schedule() entry to __switch_to, all kernel mode) and the
    # kernel share of the time slice each switch ended (system call,
    # interrupt and scheduler work on behalf of the task that was running).
    cost = defaultdict(lambda: {"sched": [], "ns": [], "slice": [],
                                "kern": []})
    causes = Counter()
    si = 0
    for e in events:
        if e["event"] != "switch":
            continue
        cause = switch_cause(e, tree)
        causes[cause] += 1
        for key in (cause, "ALL"):
            r = cost[key]
            if "sched_insts" in e:
                r["sched"].append(e["sched_insts"])
                r["ns"].append(e["sched_ticks"] / 1000)
            if e["prev"]:
                s0, e0, _ = segs[si]
                r["slice"].append(e0 - s0)
                if user[si] is not None:
                    r["kern"].append(e0 - s0 - user[si])
        if e["prev"]:
            si += 1
    total_sw = sum(causes.values()) or 1
    switch_rows = []
    for k, v in [("ALL", total_sw)] + causes.most_common():
        r = cost[k]
        switch_rows.append({
            "cause": k, "count": v, "share": v / total_sw,
            "sched_insts_mean": mean(r["sched"]),
            "sched_insts_p50": pctl(r["sched"], 0.5),
            "sched_insts_p90": pctl(r["sched"], 0.9),
            "sched_ns_mean": mean(r["ns"]),
            "slice_insts_mean": mean(r["slice"]),
            "slice_kernel_insts_mean": mean(r["kern"]),
            "slice_kernel_frac": (sum(r["kern"]) / sum(r["slice"])
                                  if r["kern"] and sum(r["slice"])
                                  else float("nan")),
        })
    write_csv(out / "switches.csv", switch_rows,
              ["cause", "count", "share", "sched_insts_mean",
               "sched_insts_p50", "sched_insts_p90", "sched_ns_mean",
               "slice_insts_mean", "slice_kernel_insts_mean",
               "slice_kernel_frac"])

    # ---- event counts -----------------------------------------------------
    kinds = Counter(k for e in events for k in event_kinds(e, tree))
    minsts = (i1 - i0) / 1e6 or float("nan")
    ms = (t1 - t0) / 1e9 or float("nan")

    # ---- per interval -----------------------------------------------------
    blocks = load_blocks(args.outdir)
    starts = [b["insts_start"] for b in blocks]
    for b in blocks:
        share = Counter()
        procs_in = Counter()
        for s, e, t in segs:
            lo, hi = max(s, b["insts_start"]), min(e, b["insts_end"])
            if hi > lo:
                share[tree.role(t)] += hi - lo
                procs_in[t["process"]] += hi - lo
        total = sum(share.values()) or 1
        for r in ROLES:
            b["share_" + r] = share[r] / total
        if has_user:
            b["user_frac_trace"] = (user_between(
                segs, user, b["insts_start"], b["insts_end"]) / (
                    b["insts_end"] - b["insts_start"] or 1))
        b["sched_insts"] = 0
        b["top_process"] = procs_in.most_common(1)[0][0] if procs_in else ""
        b["top_role"] = share.most_common(1)[0][0] if share else ""
        b["events"] = Counter()
    for e in events:
        i = bisect.bisect_right(starts, e["insts"]) - 1
        if 0 <= i < len(blocks) and e["insts"] < blocks[i]["insts_end"]:
            for k in event_kinds(e, tree):
                blocks[i]["events"][k] += 1
            blocks[i]["sched_insts"] += e.get("sched_insts", 0)
    for b in blocks:
        b["sched_pki"] = b["sched_insts"] / ((b["insts_end"]
                                              - b["insts_start"]) / 1000 or 1)
        b["events"] = " ".join(f"{k}={v}"
                               for k, v in sorted(b["events"].items()))
    if blocks:
        write_csv(out / "blocks.csv", blocks,
                  ["block", "tick_start", "insts_start", "insts", *METRICS,
                   "user_frac_trace", "sched_pki", "top_process", "top_role",
                   *("share_" + r for r in ROLES), "events"])

    # ---- event-aligned ----------------------------------------------------
    aligned = []
    K = args.window
    if blocks:
        holder = defaultdict(list)
        for e in events:
            i = bisect.bisect_right(starts, e["insts"]) - 1
            if 0 <= i < len(blocks):
                for k in event_kinds(e, tree):
                    holder[k].append(i)
        base = {m: mean([b[m] for b in blocks]) for m in METRICS}
        aligned.append({"kind": "all-intervals", "offset": "",
                        "n": len(blocks), **base})
        for kind, idxs in sorted(holder.items()):
            for off in range(-K, K + 1):
                rows = [blocks[i + off] for i in idxs
                        if 0 <= i + off < len(blocks)]
                aligned.append({"kind": kind, "offset": off, "n": len(rows),
                                **{m: mean([r[m] for r in rows])
                                   for m in METRICS}})
        write_csv(out / "aligned.csv", aligned,
                  ["kind", "offset", "n", *METRICS])

    # ---- summary ----------------------------------------------------------
    lines = [f"# Task trace summary: {args.outdir.name}", "",
             f"- span: {i1 - i0:,} instructions, {ms:.2f} ms simulated",
             f"- tools fence: {fence_note}; {len(fence_entries)} "
             "cgroup.procs writes", "",
             "| event | count | per M insts | per ms |", "|---|---|---|---|"]
    for k, v in sorted(kinds.items()):
        lines.append(f"| {k} | {v} | {v / minsts:.2f} | {v / ms:.3f} |")
    tot = sum(role_insts.values()) or 1
    agent = tot - role_insts["replay"]
    if has_user:
        tu = sum(role_user.values())
        lines += ["", f"User mode {tu / tot:.1%} of the instructions, kernel "
                  f"mode {1 - tu / tot:.1%} (system calls, interrupts, page "
                  "faults, the scheduler, kernel threads)."]
    lines += ["", "Instruction share by role; *without replay* leaves out the "
              "model-free replay's own processes.", "",
              "| role | share | share without replay | kernel mode |"
              if has_user else "| role | share | share without replay |",
              "|---|---|---|---|" if has_user else "|---|---|---|"]
    for r, v in role_insts.most_common():
        wo = "—" if r == "replay" else f"{v / (agent or 1):.1%}"
        kern = f" {1 - role_user[r] / v:.1%} |" if has_user and v else ""
        lines.append(f"| {r} | {v / tot:.1%} | {wo} |{kern}")
    lines += ["", "Context switches by cause. *sched* is the scheduler's own "
              "path (`__schedule` entry to the switch), kernel mode; "
              "*slice kernel* is the kernel-mode share of the time slice the "
              "switch ended; `sched ns` is simulated time and is meaningful "
              "only on a detailed CPU.", "",
              "| context switch cause | count | share | sched insts p50 | "
              "p90 | sched ns | slice kernel |", "|---|---|---|---|---|---|---|"]
    for r in switch_rows[:13]:
        lines.append(
            f"| {r['cause']} | {r['count']} | {r['share']:.1%} | "
            f"{fmt(r['sched_insts_p50'])} | {fmt(r['sched_insts_p90'])} | "
            f"{fmt(r['sched_ns_mean'])} | "
            f"{fmt(r['slice_kernel_frac'] * 100) if r['slice_kernel_frac'] == r['slice_kernel_frac'] else '—'}"
            "% |")
    if containers:
        lines += ["", "| container | processes | members |", "|---|---|---|"]
        for c in containers:
            lines.append(f"| {c['container']} | {c['processes']} | "
                         f"{c['members'][:90]} |")
    lines += ["", "| process | role | insts | switch-ins | exec |",
              "|---|---|---|---|---|"]
    for p in procs[:15]:
        lines.append(f"| {p['names']} ({p['tgid']}) | {p['role']} | "
                     f"{p['insts']:,} | {p['switch_ins']} | "
                     f"{p['argv'][:60]} |")
    if tools:
        lines += ["", "| tool | kind | input | running→done (insts) | "
                  "of which not replay | file I/O at | harness | replay |",
                  "|---|---|---|---|---|---|---|---|"]
        for c in tools:
            lines.append(
                f"| {c.get('tool', '')} | {c['kind']} | {c['input'][:40]} | "
                f"{c.get('run_insts', '—')} | "
                f"{c.get('run_agent_insts', '—')} "
                f"| {c.get('io', '')} {c.get('io_insts', '')} | "
                + " | ".join(f"{c['run_share_' + r]:.0%}"
                             if 'run_share_' + r in c else "—"
                             for r in ("harness", "replay"))
                + " |")
    if blocks:
        lines += ["", f"{len(blocks)} stats intervals; see blocks.csv and "
                  "aligned.csv."]
        if has_user:
            w = sum(b["insts"] for b in blocks) or 1
            diff = sum(abs(b["user_frac"] - b["user_frac_trace"]) * b["insts"]
                       for b in blocks if b["user_frac"] == b["user_frac"]) / w
            lines.append(f"User-mode share, gem5 stats vs this trace: mean "
                         f"absolute difference {diff:.3f} per interval "
                         "(the trace spreads a slice's user instructions "
                         "evenly over it).")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
