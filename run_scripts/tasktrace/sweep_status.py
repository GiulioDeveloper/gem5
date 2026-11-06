#!/usr/bin/env python3
"""Progress and state of smart sweeps (run_scripts/tasktrace/smart_sweep.sh).

Reads only what a sweep already writes (sweep.conf, launch.log, each run's
run.log, done / failed / oom_kill) and /proc, so it can run at any time,
from any shell, without disturbing the sweep.

Run states:
  queued     no run directory yet
  gate       directory made, waiting for the memory gate (no gem5 yet)
  running    gem5 alive; progress = committed / (warm-up + detailed)
  analysing  gem5 exited, per-run analyses still running
  done       finished and analysed
  failed     out of memory, too few blocks, or an analysis failed
  stale      started, not finished, and its sweep is no longer running

usage:
  sweep_status.py runs/sweep/20261104-1115-*      # one line per sweep
  sweep_status.py -r runs/sweep/20261104-1115-*   # plus running runs
  sweep_status.py -a runs/sweep/20261104-1115-base  # every run
  sweep_status.py -w 60 ...                       # refresh every 60 s
  sweep_status.py --pending-runs 162 ...          # count runs of sweeps
                                                  # not started yet in the ETA
With no sweep given, shows the newest stamp under runs/sweep/.
"""

import argparse
import glob
import os
import pwd
import re
import shutil
import sys
import time
from datetime import datetime

PROGRESS = re.compile(r"total committed (\d+), \+(\d+) since last, "
                      r"IPC ([\d.]+), host ([\d.]+) KIPS")
START = re.compile(r"^(\S+) start (\w+)/(\S+): needs ~(\d+) GB.*?"
                   r"(?:cap (\d+) GB|no cap)")
RATE_LINES = 30   # progress lines (100M ticks each) used for speed and ETA

TTY = sys.stdout.isatty()


def color(s, code):
    return f"\033[{code}m{s}\033[0m" if TTY else s


STATE_COLOR = {"running": "32", "analysing": "36", "done": "2",
               "failed": "31", "stale": "33", "gate": "35", "queued": "2"}


def fmt_dur(sec):
    if sec is None:
        return "-"
    sec = int(sec)
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        return f"{sec // 3600}h{sec % 3600 // 60:02d}"
    return f"{sec // 86400}d{sec % 86400 // 3600:02d}h"


def gem5_procs():
    """outdir -> (pid, rss MB, cpu ticks) for every gem5 of this user;
    plus a count of everyone's gem5s per user."""
    mine, users = {}, {}
    uid = os.getuid()
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            with open(f"/proc/{p}/comm") as f:
                if f.read().strip() != "gem5.opt":
                    continue
            st = os.stat(f"/proc/{p}")
            with open(f"/proc/{p}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
            with open(f"/proc/{p}/stat") as f:
                fields = f.read().rsplit(")", 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])   # utime + stime
            rss = 0
            with open(f"/proc/{p}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss = int(line.split()[1]) // 1024
        except OSError:
            continue
        users[st.st_uid] = users.get(st.st_uid, 0) + 1
        if st.st_uid != uid:
            continue
        for a in args:
            if a.startswith(b"--outdir="):
                out = os.path.normpath(a[9:].decode())
                mine[out] = (int(p), rss, ticks)
    return mine, users


def live_sweeps():
    """Sweep directories with a smart_sweep.sh still running."""
    live = set()
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        for i, a in enumerate(args):
            if a.endswith(b"smart_sweep.sh") and i + 1 < len(args):
                live.add(os.path.normpath(os.path.abspath(args[i + 1].decode())))
    return live


def read_conf(base):
    conf = {}
    try:
        with open(os.path.join(base, "sweep.conf")) as f:
            for line in f:
                for kv in line.split():
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        conf[k] = v
                k, _, v = line.strip().partition(" ")
                conf.setdefault(k, v)
    except OSError:
        pass
    return conf


def read_starts(base):
    starts = {}
    try:
        with open(os.path.join(base, "launch.log")) as f:
            for line in f:
                m = START.match(line)
                if m:
                    t = datetime.fromisoformat(m.group(1)).timestamp()
                    starts[(m.group(2), m.group(3))] = {
                        "t": t, "need": int(m.group(4)),
                        "cap": int(m.group(5)) if m.group(5) else None}
    except OSError:
        pass
    return starts


def tail_progress(path, n=RATE_LINES):
    """The last n progress lines of a run.log, read from its end."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 64 * 1024))
            text = f.read().decode(errors="replace")
    except OSError:
        return []
    return [(int(m.group(1)), int(m.group(2)), float(m.group(3)),
             float(m.group(4)))
            for m in PROGRESS.finditer(text)][-n:]


def run_info(base, suite, name, target, procs, starts, alive_sweep, now):
    out = os.path.normpath(os.path.join(base, suite, name))
    r = {"suite": suite, "name": name, "out": out, "frac": 0.0,
         "ipc": None, "kips": None, "eta": None, "rss": None, "cpu": None,
         "start": starts.get((suite, name)), "note": ""}
    if r["start"]:
        r["elapsed"] = now - r["start"]["t"]
    else:
        r["elapsed"] = None
    if os.path.exists(os.path.join(out, "done")):
        r["state"], r["frac"] = "done", 1.0
        failed = os.path.join(out, "failed")
        if os.path.exists(failed):   # done, but an analysis failed
            r["note"] = open(failed).read().strip().replace("\n", "; ")
        return r
    if os.path.exists(os.path.join(out, "failed")):
        r["state"] = "failed"
        r["note"] = open(os.path.join(out, "failed")).read().strip() \
            .replace("\n", "; ")
        return r
    prog = tail_progress(os.path.join(out, "run.log"))
    if prog:
        committed = prog[-1][0]
        r["frac"] = min(committed / target, 1.0) if target else 0.0
        r["ipc"] = sum(p[2] for p in prog[-5:]) / len(prog[-5:])
        # Instruction-weighted host speed over the last RATE_LINES lines.
        insts = sum(p[1] for p in prog)
        secs = sum(p[1] / (p[3] * 1000) for p in prog if p[3] > 0)
        if secs > 0:
            r["kips"] = insts / secs / 1000
            r["eta"] = max(target - committed, 0) / (r["kips"] * 1000)
    if out in procs:
        r["state"] = "running"
        r["rss"] = procs[out][1]
        r["cpu"] = procs[out][3] if len(procs[out]) > 3 else None
    elif not os.path.isdir(out):
        r["state"] = "queued"
    elif not alive_sweep:
        r["state"] = "stale"
    elif not os.path.exists(os.path.join(out, "run.log")):
        r["state"] = "gate"
    elif r["frac"] >= 1.0 or os.path.exists(os.path.join(out, "analysis.log")):
        r["state"] = "analysing"
    else:
        # Between the gem5 exit and the launcher's bookkeeping, or a gem5
        # that died; the sweep will mark it failed shortly if so.
        r["state"] = "analysing" if r["frac"] > 0.99 else "gate"
    return r


def sweep_info(base, procs, live, now):
    conf = read_conf(base)
    starts = read_starts(base)
    warm = int(conf.get("WARM", 0))
    det = {"agentic": int(conf.get("AGENTIC_DET", 0)),
           "spec": int(conf.get("SPEC_DET", 0))}
    nruns = int(conf.get("runs", 0) or 0)
    alive = os.path.normpath(os.path.abspath(base)) in live
    runs = []
    seen = set()
    for suite in ("agentic", "spec"):
        for d in sorted(glob.glob(os.path.join(base, suite, "*"))):
            if os.path.isdir(d):
                name = os.path.basename(d)
                seen.add((suite, name))
                runs.append(run_info(base, suite, name, warm + det[suite],
                                     procs, starts, alive, now))
    queued = max(nruns - len(runs), 0)
    states = {}
    for r in runs:
        states[r["state"]] = states.get(r["state"], 0) + 1
    if queued:
        states["queued"] = states.get("queued", 0) + queued
    finished = "finished" in conf
    t0 = None
    if "started" in conf:
        try:
            t0 = datetime.fromisoformat(conf["started"]).timestamp()
        except ValueError:
            pass
    # Remaining work in run-equivalents and the current throughput.
    rate = sum(r["kips"] * 1000 for r in runs
               if r["state"] == "running" and r["kips"])
    target = warm + det["agentic"]
    remaining = sum((1 - r["frac"]) * target for r in runs
                    if r["state"] in ("running", "gate", "stale")) \
        + queued * target
    return {"base": base, "name": os.path.basename(os.path.normpath(base)),
            "bytes": dir_bytes(base),
            "extra": conf.get("extra", ""), "commit": conf.get("commit", "?"),
            "runs": runs, "nruns": nruns or len(runs), "states": states,
            "alive": alive, "finished": finished, "t0": t0, "rate": rate,
            "remaining": remaining, "target": target}


def dir_bytes(path):
    """Disk space of a directory tree (allocated blocks, like du)."""
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_blocks * 512
            except OSError:
                pass
    return total


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") \
                else f"{n:.1f} {unit}"
        n /= 1024


def cpu_ticks():
    """Host (busy, total) jiffies from /proc/stat."""
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + v[4]   # idle + iowait
    return sum(v[:8]) - idle, sum(v[:8])


class Sampler:
    """CPU use needs two readings: keep the previous one between renders
    (watch mode), or take two a second apart (one-shot)."""

    def __init__(self):
        self.prev = None

    def sample(self):
        procs, users = gem5_procs()
        now = (time.time(), cpu_ticks(),
               {o: p[2] for o, p in procs.items()})
        if self.prev is None:
            self.prev = now
            time.sleep(1)
            procs, users = gem5_procs()
            now = (time.time(), cpu_ticks(),
                   {o: p[2] for o, p in procs.items()})
        (t0, (b0, a0), p0), (t1, (b1, a1), _) = self.prev, now
        host = 100 * (b1 - b0) / (a1 - a0) if a1 > a0 else 0.0
        hz = os.sysconf("SC_CLK_TCK")
        for o, p in procs.items():
            cpu = (100 * (p[2] - p0[o]) / hz / (t1 - t0)
                   if o in p0 and t1 > t0 else None)
            procs[o] = p + (cpu,)
        self.prev = now
        return procs, users, host


def host_block(users, cpu_pct, sweeps):
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            mem[k] = int(v.split()[0]) / 1024 / 1024   # GB
    psi = "?"
    try:
        with open("/proc/pressure/memory") as f:
            psi = f.readline().split()[1].split("=")[1]
    except OSError:
        pass
    who = []
    for uid, n in sorted(users.items()):
        try:
            u = pwd.getpwuid(uid).pw_name
        except KeyError:
            u = str(uid)
        who.append(f"{u} {n}")
    used = mem["MemTotal"] - mem["MemAvailable"]
    swap = mem["SwapTotal"] - mem["SwapFree"]
    path = sweeps[0]["base"] if sweeps else "."
    du = shutil.disk_usage(path)
    mount = path
    while not os.path.ismount(mount):
        mount = os.path.dirname(os.path.abspath(mount))
    set_bytes = sum(s["bytes"] for s in sweeps)
    return [
        f"cpu   {bar(cpu_pct / 100)} {cpu_pct:>4.0f}%  "
        f"{os.cpu_count()} threads, load {os.getloadavg()[0]:.1f}; "
        f"gem5: {', '.join(who) or 'none'}",
        f"mem   {bar(used / mem['MemTotal'])} "
        f"{100 * used / mem['MemTotal']:>4.0f}%  {used:.1f} of "
        f"{mem['MemTotal']:.0f} GB used, {mem['MemAvailable']:.1f} available; "
        f"swap {swap:.1f} of {mem['SwapTotal']:.1f} GB; pressure {psi}%",
        f"disk  {bar(du.used / du.total)} {100 * du.used / du.total:>4.0f}%  "
        f"{mount}: {fmt_bytes(du.used)} of {fmt_bytes(du.total)} used, "
        f"{fmt_bytes(du.free)} free; these sweeps {fmt_bytes(set_bytes)}",
    ]


def bar(frac, width=20):
    n = int(round(frac * width))
    return "█" * n + "·" * (width - n)


def render(args, sampler):
    procs, users, cpu_pct = sampler.sample()
    now = time.time()
    live = live_sweeps()
    sweeps = [sweep_info(b, procs, live, now) for b in args.sweeps]
    lines = [f"{datetime.now():%Y-%m-%d %H:%M:%S}"] \
        + host_block(users, cpu_pct, sweeps) + [""]
    order = ["done", "failed", "analysing", "running", "gate", "queued",
             "stale"]
    w = max(len(s["name"]) for s in sweeps)
    fw = max([len("extra flags")] + [len(s["extra"] or "-") for s in sweeps])
    lines.append(f"{'sweep':<{w}}  {'extra flags':<{fw}}  {'runs':>4}  "
                 f"{'progress':<20}  {'%':>4}  "
                 + "  ".join(f"{k:>5}" for k in order[:6])
                 + f"  {'disk':>8}  status")
    tot_rem = tot_rate = 0
    tot = {k: 0 for k in order}
    tot_frac = tot_n = 0
    for s in sweeps:
        n = s["nruns"]
        frac = (sum(r["frac"] for r in s["runs"])) / n if n else 0
        tot_frac += frac * n
        tot_n += n
        tot_rem += s["remaining"]
        tot_rate += s["rate"]
        for k, v in s["states"].items():
            tot[k] += v
        if s["finished"]:
            status = color("finished", "2")
        elif s["alive"]:
            status = color("running", "32")
        else:
            status = color("NOT RUNNING", "31")
        if s["states"].get("stale"):
            status += color(f" ({s['states']['stale']} stale)", "33")
        cells = []
        for k in order[:6]:
            v = s["states"].get(k, 0)
            c = f"{v:>5}" if v else f"{'.':>5}"
            cells.append(color(c, STATE_COLOR[k]) if v and k in
                         ("failed", "running") else c)
        lines.append(f"{s['name']:<{w}}  {s['extra'] or '-':<{fw}}  {n:>4}  "
                     f"{bar(frac)}  {frac * 100:>3.0f}%  "
                     + "  ".join(cells)
                     + f"  {fmt_bytes(s['bytes']):>8}  {status}")
    # Totals and a rough ETA: remaining instructions over the current
    # aggregate speed, plus runs of sweeps that have not started yet.
    pend = args.pending_runs * (sweeps[0]["target"] if sweeps else 0)
    if len(sweeps) > 1 or pend:
        n = tot_n + args.pending_runs
        frac = tot_frac / n if n else 0
        lines.append(f"{'all':<{w}}  {'':<{fw}}  {n:>4}  "
                     f"{bar(frac)}  {frac * 100:>3.0f}%  "
                     + "  ".join(f"{tot[k] or '.':>5}" for k in order[:6])
                     + f"  {fmt_bytes(sum(s['bytes'] for s in sweeps)):>8}"
                     + (f"  incl. {args.pending_runs} not started"
                        if args.pending_runs else ""))
    eta = (tot_rem + pend) / tot_rate if tot_rate else None
    running = tot["running"]
    lines.append("")
    lines.append(f"{running} running at {tot_rate / 1e6:.2f} MIPS in all; "
                 f"rough time left {fmt_dur(eta)} at the current "
                 "concurrency")
    for s in sweeps:
        if not s["alive"] and not s["finished"]:
            lines.append(color(f"! {s['name']}: no smart_sweep.sh running "
                               "and sweep.conf has no 'finished' line", "31"))
        for r in s["runs"]:
            if r["state"] == "failed" or (r["state"] == "done" and r["note"]):
                lines.append(color(f"! {s['name']} {r['name']}: "
                                   f"{r['note']}", "31"))
    # Per-run detail.
    detail = []
    for s in sweeps:
        for r in s["runs"]:
            if args.all or (args.running and r["state"] in
                            ("running", "gate", "analysing", "stale")):
                detail.append((s, r))
    if detail:
        lines.append("")
        lines.append(f"{'sweep':<{w}}  {'task':<22} {'state':<9} "
                     f"{'progress':<20} {'%':>4}  {'IPC':>5} {'KIPS':>5} {'CPU':>4} "
                     f"{'RSS/cap GB':>10} {'elapsed':>7} {'left':>6}")
        for s, r in detail:
            cap = r["start"]["cap"] if r["start"] else None
            mem = (f"{r['rss'] / 1024:.1f}/{cap}" if r["rss"] is not None
                   else "-") if cap or r["rss"] is not None else "-"
            st = color(f"{r['state']:<9}", STATE_COLOR[r["state"]])
            lines.append(
                f"{s['name']:<{w}}  {r['name']:<22} {st} "
                f"{bar(r['frac'])} {r['frac'] * 100:>3.0f}%  "
                f"{'-' if r['ipc'] is None else format(r['ipc'], '.2f'):>5} "
                f"{'-' if r['kips'] is None else format(r['kips'], '.0f'):>5} "
                f"{'-' if r['cpu'] is None else format(r['cpu'], '.0f') + '%':>4} "
                f"{mem:>10} {fmt_dur(r['elapsed']):>7} "
                f"{fmt_dur(r['eta']) if r['state'] == 'running' else '':>6}"
                + (f"  {r['note']}" if r["note"] else ""))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog=__doc__.split("usage:")[1].split("With no")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sweeps", nargs="*", help="sweep directories")
    ap.add_argument("-r", "--running", action="store_true",
                    help="list running, gated and analysing runs")
    ap.add_argument("-a", "--all", action="store_true", help="list every run")
    ap.add_argument("-w", "--watch", type=float, metavar="SEC",
                    help="refresh every SEC seconds (Ctrl-C to stop)")
    ap.add_argument("--pending-runs", type=int, default=0, metavar="N",
                    help="runs of sweeps not started yet, counted in the "
                         "total and the time left")
    args = ap.parse_args()
    if not args.sweeps:
        dirs = sorted(d for d in glob.glob("runs/sweep/*")
                      if os.path.isfile(os.path.join(d, "sweep.conf")))
        if not dirs:
            sys.exit("no sweeps under runs/sweep/")
        stamp = re.match(r"\d{8}-\d{4,6}", os.path.basename(dirs[-1]))
        args.sweeps = [d for d in dirs if stamp and
                       os.path.basename(d).startswith(stamp.group(0))] \
            or dirs[-1:]
    args.sweeps = [d for d in args.sweeps
                   if os.path.isfile(os.path.join(d, "sweep.conf"))]
    if not args.sweeps:
        sys.exit("no sweep directories (with a sweep.conf) given")
    if not args.watch:
        print(render(args, Sampler()))
        return
    sampler = Sampler()
    try:
        while True:
            text = render(args, sampler)
            sys.stdout.write("\033[H\033[2J" + text + "\n")
            sys.stdout.flush()
            time.sleep(args.watch)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
