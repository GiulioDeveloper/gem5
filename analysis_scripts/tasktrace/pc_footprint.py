"""Instruction footprint, LRU hit rates and branches per process and per
thread, from a run's PC trace (pc_trace.py) and task trace.

usage:
  python3 analysis_scripts/tasktrace/pc_footprint.py <run> [-o OUT]
      [--vmlinux VMLINUX] [--limit N]

A process instance ("PID") is a tgid between execs (threads share it): an
exec event, placed at its exact instruction by the global instruction
count without NOPs, which the PC trace reproduces, starts a new instance
with the new name. Kernel code (PC bit 63) is its own group, `[kernel]`,
with global addresses, and is also counted per process it ran for ("on
behalf of": the task current at the time, kernel threads included).

Three views of user code:
- per PID: every instance on its own (instances.csv);
- per name, each process separate: a name's processes are summed, but an
  address in two of them counts twice (two address spaces);
- per name, aggregated: all processes of a name share one address space,
  so code at the same address in two git runs counts once and can hit in
  the cache. This matches code shared through the page cache only where
  binaries and libraries load at the same addresses in every run (no
  ASLR); `overlap` reports how much the union shrinks.

Per group, view and instance:
- distinct instructions, 64-byte lines and 4 KiB pages, and the line
  footprint as a multiple of each cache size;
- LRU stack distance of every line access (a fetch moving to another
  line): the share of accesses that hit in a fully associative LRU
  instruction-only cache of each size, and the misses per 1,000
  instructions. "private": the group's code alone in the cache;
  "shared": the whole interleaved stream, as the core sees it, with each
  access charged to its group;
- distinct branch instructions by type, and how many were ever taken
  (the next instruction is not at PC + 4; a transfer into the kernel's
  exception vectors is an exception, not a taken branch).

Per thread (a pid within a process instance, or a kernel thread): its
whole stream, user code and the kernel code run while it was current, on
its own: distinct instructions and lines (user and kernel), LRU stack
distance per line as above (private: the thread alone; shared: the
interleaved stream), the repeat distance per instruction address (the
number of distinct instructions since the same PC last committed), and
distinct branches by type.

Writes OUT (default <run>/footprint/): groups.tsv, hist.tsv (stack
distance histograms, log2 buckets), instances.tsv from the C++ pass
(pc_footprint.cc, built on first use), threads.tsv and thread_hist.tsv,
then footprint.csv (per name, both views), instances.csv (per PID),
threads.csv (per thread), summary.md and report.html
(pc_footprint_report.py).
"""

import argparse
import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pc_footprint_report  # noqa: E402
from pc_trace import DEFAULT_VMLINUX  # noqa: E402

SRC = Path(__file__).with_name("pc_footprint.cc")
LINE = 64
# (label, bytes): L1I and L2 of the Neoverse V2 config at x1, x4, x8.
CACHES = (("L1I 64K", 64 << 10), ("L1I 256K", 256 << 10),
          ("L1I 512K", 512 << 10), ("L2 2M", 2 << 20), ("L2 8M", 8 << 20),
          ("L2 16M", 16 << 20))
BRANCHES = ("cond", "direct", "call", "indirect_call", "indirect_jump",
            "return", "exception_return")


def build():
    """The pass's binary, rebuilt when the source changes."""
    digest = hashlib.sha1(SRC.read_bytes()).hexdigest()[:12]
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    exe = cache / "gem5-analysis" / f"pc_footprint-{digest}"
    if not exe.exists():
        exe.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["g++", "-O2", "-std=c++17", "-o", str(exe),
                        str(SRC)], check=True)
    return exe


def vector_tables(vmlinux):
    """Link addresses of the kernel's EL1 vector tables."""
    out = subprocess.run(["nm", vmlinux], capture_output=True, text=True,
                         check=True).stdout
    found = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] in ("vectors",
                                            "__bp_harden_el1_vectors"):
            found[parts[2]] = parts[0]
    return found.get("vectors", "0"), found.get("__bp_harden_el1_vectors",
                                                found.get("vectors", "0"))


def side_files(run, out):
    """Switch instruction counts in order, and exec events."""
    switches, execs = [], []
    with open(run / "tasktrace.jsonl") as f:
        for line in f:
            e = json.loads(line)
            if e["event"] == "switch":
                switches.append(e["insts"])
            elif e["event"] == "exec":
                execs.append((e["insts"], e["task"]["tgid"],
                              e["task"]["process"]))
    execs.sort()
    sw, ex = out / "switches.txt", out / "execs.txt"
    sw.write_text("".join(f"{n}\n" for n in switches))
    ex.write_text("".join(f"{n} {t} {p}\n" for n, t, p in execs))
    return sw, ex


def run_pass(run, out, vmlinux, limit):
    exe = build()
    sw, ex = side_files(run, out)
    v0, v1 = vector_tables(vmlinux)
    caps = [str(size // LINE) for _, size in CACHES]
    src = f"zstd -dc {run / 'pc_trace.zst'}"
    if limit:   # zstd ends with SIGPIPE (141) when head stops reading
        src = f"{{ {src} || [ $? -eq 141 ]; }} | head -n {int(limit)}"
    cmd = (f"{src} | {exe} {sw} {ex} {out} {v0} {v1} " + " ".join(caps))
    subprocess.run(["bash", "-o", "pipefail", "-c", cmd], check=True)


def rows_of(path):
    with open(path) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def key_of(label):
    return label.replace(" ", "_")


def rates(n, prefix=""):
    """Footprint multiples, MPKI and branch totals of one stats row (numbers
    keyed by column name) in one view (prefix "" or "m_")."""
    caps = [size // LINE for _, size in CACHES]
    insts, acc = n[prefix + "insts"], n[prefix + "line_accesses"]
    lines = n[prefix + "uniq_lines"]
    r = {"uniq_insts": int(n[prefix + "uniq_insts"]),
         "uniq_lines": int(lines),
         "uniq_pages": int(n[prefix + "uniq_pages"]),
         "code_kib": lines * LINE / 1024,
         "cold_mpki": n[prefix + "priv_cold"] / insts * 1000 if insts else None}
    for (label, size), c in zip(CACHES, caps):
        k = key_of(label)
        r[f"x_{k}"] = lines * LINE / size
        for view in ("priv", "shared"):
            hits = n[f"{prefix}{view}_hits_{c}"]
            r[f"{view}_mpki_{k}"] = ((acc - hits) / insts * 1000
                                     if insts else None)
    r["branches"] = int(sum(n[f"{prefix}br_{b}"] for b in BRANCHES))
    r["branches_taken"] = int(sum(n[f"{prefix}br_{b}_taken"]
                                  for b in BRANCHES))
    for b in BRANCHES:
        r[f"br_{b}"] = int(n[f"{prefix}br_{b}"])
        r[f"br_{b}_taken"] = int(n[f"{prefix}br_{b}_taken"])
    return r


def numbers(row, skip):
    return {k: float(v) for k, v in row.items() if k not in skip}


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def fmt(x, digits=2):
    return "" if x is None else f"{x:.{digits}f}"


def mpki_table(lines, rows, view, title):
    lines.append(title)
    lines.append("")
    lines.append("| process | " + " | ".join(l for l, _ in CACHES)
                 + " | of which cold |")
    lines.append("|---|" + "---|" * (len(CACHES) + 1))
    for name, r in rows:
        lines.append(f"| {name} | " + " | ".join(
            fmt(r[f"{view}_mpki_{key_of(l)}"]) for l, _ in CACHES)
            + f" | {fmt(r['cold_mpki'])} |")
    lines.append("")


def branch_table(lines, rows, title):
    lines.append(title)
    lines.append("")
    lines.append("| process | all | taken | " + " | ".join(BRANCHES) + " |")
    lines.append("|---|---|---|" + "---|" * len(BRANCHES))
    for name, r in rows:
        lines.append(f"| {name} | {r['branches']:,} | "
                     f"{r['branches_taken']:,} | " + " | ".join(
                         f"{r[f'br_{b}']:,} ({r[f'br_{b}_taken']:,})"
                         for b in BRANCHES) + " |")
    lines.append("")


def thread_hists(out):
    """{thread: {view: [(bucket, accesses), ...]}} from thread_hist.tsv;
    bucket b holds distances d with d + 1 in [2^(b-1), 2^b)."""
    hists = {}
    for r in rows_of(out / "thread_hist.tsv"):
        hists.setdefault(int(r["thread"]), {}).setdefault(r["view"], []).append(
            (int(r["bucket"]), int(r["accesses"])))
    for views in hists.values():
        for h in views.values():
            h.sort()
    return hists


def quantile(hist, total, p):
    """The p-quantile of the repeat distance d (log-interpolated inside its
    bucket), or None when it falls among the first accesses (cold)."""
    need, cum = p * total, 0
    for b, n in hist:
        if cum + n >= need:
            lo = 1 << (b - 1)
            return lo * 2 ** ((need - cum) / n) - 1
        cum += n
    return None


def summarize_threads(out):
    """threads.csv: one row per thread that committed instructions."""
    hists = thread_hists(out)
    caps = [size // LINE for _, size in CACHES]
    rows = []
    for t in rows_of(out / "threads.tsv"):
        n = numbers(t, ("thread", "group", "comm"))
        insts, acc = n["insts"], n["line_accesses"]
        if not insts:
            continue
        tid = int(t["thread"])
        lines = n["u_uniq_lines"] + n["k_uniq_lines"]
        r = {"thread": tid, "tgid": int(n["tgid"]), "pid": int(n["pid"]),
             "instance": int(n["instance"]), "process": t["group"],
             "comm": t["comm"], "kthread": int(n["kthread"]),
             "insts": int(insts), "k_insts": int(n["k_insts"]),
             "uniq_insts": int(n["u_uniq_insts"] + n["k_uniq_insts"]),
             "u_uniq_insts": int(n["u_uniq_insts"]),
             "k_uniq_insts": int(n["k_uniq_insts"]),
             "uniq_lines": int(lines),
             "code_kib": lines * LINE / 1024,
             "u_code_kib": n["u_uniq_lines"] * LINE / 1024,
             "k_code_kib": n["k_uniq_lines"] * LINE / 1024,
             "line_accesses": int(acc),
             "line_cold_pct": n["priv_cold"] / acc * 100 if acc else None,
             "pc_cold_pct": n["pc_cold"] / insts * 100}
        for (label, size), c in zip(CACHES, caps):
            k = key_of(label)
            r[f"x_{k}"] = lines * LINE / size
            r[f"priv_hit_pct_{k}"] = (n[f"priv_hits_{c}"] / acc * 100
                                      if acc else None)
            for view in ("priv", "shared"):
                r[f"{view}_mpki_{k}"] = ((acc - n[f"{view}_hits_{c}"])
                                         / insts * 1000)
        h = hists.get(tid, {})
        for view, total in (("pc", insts), ("line", acc)):
            for p in (50, 90, 99):
                r[f"{view}_p{p}"] = quantile(h.get(view, []), total, p / 100)
        r["branches"] = int(sum(n[f"br_{b}"] for b in BRANCHES))
        r["branches_taken"] = int(sum(n[f"br_{b}_taken"] for b in BRANCHES))
        r["k_branches"] = int(sum(n[f"k_br_{b}"] for b in BRANCHES))
        for b in BRANCHES:
            r[f"br_{b}"] = int(n[f"br_{b}"])
            r[f"br_{b}_taken"] = int(n[f"br_{b}_taken"])
        rows.append(r)
    rows.sort(key=lambda r: -r["insts"])
    write_csv(out / "threads.csv", rows)
    return rows


def thread_label(r):
    if r["kthread"]:
        return f"{r['comm']} (kernel, {r['pid']})"
    if r["comm"] == r["process"]:
        return f"{r['process']} ({r['pid']})"
    return f"{r['process']} {r['comm']} ({r['pid']})"


def thread_section(lines, threads):
    def dist(x):
        return "cold" if x is None else f"{x:,.0f}"
    lines.append("## 4. By thread")
    lines.append("")
    lines.append(f"{len(threads)} threads committed instructions. Each "
                 "thread's whole stream (user and kernel code) on its own; "
                 "the 30 with the most instructions, all in `threads.csv` "
                 "and `report.html`. Repeat distance: distinct instructions "
                 "(per PC) or distinct 64-byte lines since the previous use, "
                 "50th / 90th / 99th percentile.")
    lines.append("")
    lines.append("| thread | instructions | kernel | code (KiB) | ×64K | ×2M "
                 "| repeat distance, instructions | lines | MPKI 64K | 2M "
                 "| branches (taken) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in threads[:30]:
        lines.append(
            f"| {thread_label(r)} | {r['insts'] / 1e6:,.1f}M "
            f"| {r['k_insts'] / r['insts'] * 100:.0f}% "
            f"| {r['code_kib']:,.0f} | {r['x_L1I_64K']:.1f} "
            f"| {r['x_L2_2M']:.2f} "
            f"| {' / '.join(dist(r[f'pc_p{p}']) for p in (50, 90, 99))} "
            f"| {' / '.join(dist(r[f'line_p{p}']) for p in (50, 90, 99))} "
            f"| {fmt(r['priv_mpki_L1I_64K'])} | {fmt(r['priv_mpki_L2_2M'])} "
            f"| {r['branches']:,} ({r['branches_taken']:,}) |")
    lines.append("")


def summarize(out):
    groups = rows_of(out / "groups.tsv")
    caps = [size // LINE for _, size in CACHES]

    # ---- per name, both views ------------------------------------------
    table = []
    for g in groups:
        n = numbers(g, ("group", "kernel"))
        if not n["insts"] and not n["k_insts"]:
            continue
        r = {"group": g["group"], "kernel": g["kernel"],
             "processes": int(n["instances"]), "insts": int(n["insts"])}
        r.update({k: v for k, v in rates(n).items()})
        r.update({"m_" + k: v for k, v in rates(n, "m_").items()})
        r["overlap"] = (n["m_uniq_lines"] / n["uniq_lines"]
                        if n["uniq_lines"] else None)
        for (label, _), c in zip(CACHES, caps):
            kh = n[f"k_shared_hits_{c}"]
            r[f"k_shared_mpki_{key_of(label)}"] = (
                (n["k_accesses"] - kh) / n["k_insts"] * 1000
                if n["k_insts"] else None)
        r["k_insts"] = int(n["k_insts"])
        r["k_uniq_insts"] = int(n["k_uniq_insts"])
        r["k_uniq_lines"] = int(n["k_uniq_lines"])
        table.append(r)
    table.sort(key=lambda r: -(r["insts"] or r["k_insts"]))
    write_csv(out / "footprint.csv", table)

    # ---- per PID -----------------------------------------------------------
    pids = []
    for i in rows_of(out / "instances.tsv"):
        n = numbers(i, ("instance", "tgid", "generation", "group"))
        if not n["insts"]:
            continue
        r = {"instance": int(i["instance"]), "pid": int(i["tgid"]),
             "exec": int(i["generation"]), "process": i["group"],
             "insts": int(n["insts"]), "k_insts": int(n["k_insts"])}
        r.update(rates(n))
        pids.append(r)
    # A fork child that runs a little of its parent's code and then execs
    # (the same PID has a later exec) is not a run of the parent's program.
    last_exec = {}
    for r in pids:
        last_exec[r["pid"]] = max(last_exec.get(r["pid"], 0), r["exec"])
    for r in pids:
        r["pre_exec_fork"] = int(r["exec"] < last_exec[r["pid"]])
    pids.sort(key=lambda r: -r["insts"])
    write_csv(out / "instances.csv", pids)
    per_name = {}
    for r in pids:
        if not r["pre_exec_fork"]:
            per_name.setdefault(r["process"], []).append(r)

    total_insts = sum(r["insts"] for r in table)
    lines = [f"# Instruction footprint: {out.parent.name}", ""]
    lines.append(f"{total_insts:,} instructions. Whole-stream LRU misses per "
                 "1,000 instructions (shared cache, instruction lines only, "
                 "fully associative, no prefetch):")
    lines.append("")
    lines.append("| view | " + " | ".join(l for l, _ in CACHES) + " |")
    lines.append("|---|" + "---|" * len(CACHES))
    for prefix, label in (("", "each process separate"),
                          ("m_", "same-name processes share code")):
        vals = []
        acc = sum(float(g[prefix + "line_accesses"]) for g in groups)
        for c in caps:
            hits = sum(float(g[f"{prefix}shared_hits_{c}"]) for g in groups)
            vals.append(f"{(acc - hits) / total_insts * 1000:.2f}")
        lines.append(f"| {label} | " + " | ".join(vals) + " |")
    lines.append("")

    top = [r for r in table if r["insts"] >= total_insts * 0.002]
    rows = [(r["group"], r) for r in top]
    mrows = [(r["group"], {k[2:]: v for k, v in r.items()
                           if k.startswith("m_")}) for r in top]

    lines.append("## 1. By name, each process separate")
    lines.append("")
    lines.append("Every process is its own address space; a name's row sums "
                 "its processes. Groups with ≥0.2% of the instructions.")
    lines.append("")
    lines.append("| process | processes | instructions | distinct insts | "
                 "code (KiB) | ×64K | ×512K | ×2M | ×16M | code per "
                 "process, median / max (KiB) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in top:
        inst = [p["code_kib"] for p in per_name.get(r["group"], [])]
        med = (f"{statistics.median(inst):,.0f} / {max(inst):,.0f}"
               if inst else "")
        lines.append(
            f"| {r['group']} | {len(inst)} | {r['insts'] / 1e6:,.1f}M "
            f"| {r['uniq_insts']:,} | {r['code_kib']:,.0f} "
            f"| {r['x_L1I_64K']:.1f} | {r['x_L1I_512K']:.2f} "
            f"| {r['x_L2_2M']:.2f} | {r['x_L2_16M']:.3f} | {med} |")
    lines.append("")
    mpki_table(lines, rows, "priv", "### Misses per 1,000 instructions, "
               "private (the process name's code alone)")
    mpki_table(lines, rows, "shared", "### Misses per 1,000 instructions, "
               "shared (the interleaved stream)")
    branch_table(lines, rows, "### Distinct branches (taken at least once)")

    lines.append("## 2. By name, aggregated: same-name processes share code")
    lines.append("")
    lines.append("All processes of a name share one address space: code at "
                 "the same address in two runs counts once and stays in the "
                 "cache between runs. `overlap` = aggregated code / code "
                 "summed over the processes: near 1 means the runs share "
                 "little at the same addresses (different code, or ASLR).")
    lines.append("")
    lines.append("| process | processes | distinct insts | code (KiB) | "
                 "overlap | ×64K | ×512K | ×2M | ×16M |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for (name, m), r in zip(mrows, top):
        lines.append(
            f"| {name} | {len(per_name.get(name, []))} "
            f"| {m['uniq_insts']:,} | {m['code_kib']:,.0f} "
            f"| {fmt(r['overlap'], 3)} | {m['x_L1I_64K']:.1f} "
            f"| {m['x_L1I_512K']:.2f} | {m['x_L2_2M']:.2f} "
            f"| {m['x_L2_16M']:.3f} |")
    lines.append("")
    mpki_table(lines, mrows, "priv", "### Misses per 1,000 instructions, "
               "private, aggregated")
    mpki_table(lines, mrows, "shared", "### Misses per 1,000 instructions, "
               "shared, aggregated")
    branch_table(lines, mrows, "### Distinct branches, aggregated")

    lines.append("## 3. By PID")
    lines.append("")
    forks = sum(r["pre_exec_fork"] for r in pids)
    lines.append(f"{len(pids)} processes ran user code (a PID is listed once "
                 f"per exec), {forks} of them fork children that ran a little "
                 "of their parent's code before their exec (left out of the "
                 "per-name statistics). The 30 with the most instructions; "
                 "all in `instances.csv`. MPKI: the process's code alone.")
    lines.append("")
    lines.append("| PID | exec | process | instructions | distinct insts | "
                 "code (KiB) | MPKI 64K | 512K | 2M | cold | branches "
                 "(taken) | kernel instructions |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in pids[:30]:
        lines.append(
            f"| {r['pid']} | {r['exec']} | {r['process']} "
            f"| {r['insts'] / 1e6:,.1f}M | {r['uniq_insts']:,} "
            f"| {r['code_kib']:,.0f} | {fmt(r['priv_mpki_L1I_64K'])} "
            f"| {fmt(r['priv_mpki_L1I_512K'])} | {fmt(r['priv_mpki_L2_2M'])} "
            f"| {fmt(r['cold_mpki'])} | {r['branches']:,} "
            f"({r['branches_taken']:,}) | {r['k_insts'] / 1e6:,.1f}M |")
    lines.append("")
    lines.append("Per name, over its processes (median / max):")
    lines.append("")
    lines.append("| process | processes | instructions | code (KiB) | "
                 "MPKI 64K | MPKI 512K | branches |")
    lines.append("|---|---|---|---|---|---|---|")

    def mm(xs, f):
        xs = [x for x in xs if x is not None]
        return (f"{f(statistics.median(xs))} / {f(max(xs))}" if xs else "")
    for name, ps in sorted(per_name.items(),
                           key=lambda kv: -sum(p["insts"] for p in kv[1])):
        if len(ps) < 2:
            continue
        lines.append(
            f"| {name} | {len(ps)} "
            f"| {mm([p['insts'] / 1e6 for p in ps], lambda x: f'{x:,.1f}M')} "
            f"| {mm([p['code_kib'] for p in ps], lambda x: f'{x:,.0f}')} "
            f"| {mm([p['priv_mpki_L1I_64K'] for p in ps], fmt)} "
            f"| {mm([p['priv_mpki_L1I_512K'] for p in ps], fmt)} "
            f"| {mm([p['branches'] for p in ps], lambda x: f'{x:,.0f}')} |")
    lines.append("")

    kt = sorted((r for r in table if r["k_insts"]),
                key=lambda r: -r["k_insts"])[:15]
    lines.append("## Kernel code on behalf of each process")
    lines.append("")
    lines.append("| process | kernel instructions | distinct kernel insts "
                 "| kernel lines (KiB) | shared MPKI L1I 64K | L2 2M |")
    lines.append("|---|---|---|---|---|---|")
    for r in kt:
        lines.append(f"| {r['group']} | {r['k_insts'] / 1e6:,.1f}M "
                     f"| {r['k_uniq_insts']:,} "
                     f"| {r['k_uniq_lines'] * LINE / 1024:,.0f} "
                     f"| {fmt(r['k_shared_mpki_L1I_64K'])} "
                     f"| {fmt(r['k_shared_mpki_L2_2M'])} |")
    threads = summarize_threads(out)
    thread_section(lines, threads)
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"{out / 'summary.md'}, {out / 'footprint.csv'}, "
          f"{out / 'instances.csv'}, {out / 'threads.csv'}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--vmlinux", default=DEFAULT_VMLINUX)
    ap.add_argument("--limit", type=float,
                    help="read only the first N lines of the PC trace")
    ap.add_argument("--summary-only", action="store_true",
                    help="reformat an existing OUT without rerunning")
    args = ap.parse_args()
    out = args.out or args.run / "footprint"
    out.mkdir(parents=True, exist_ok=True)
    if not args.summary_only:
        run_pass(args.run, out, args.vmlinux, args.limit)
    summarize(out)
    pc_footprint_report.write_report(out)


if __name__ == "__main__":
    main()
