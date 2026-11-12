"""Reduce a gem5 Exec trace to a compact PC trace, joined with the task trace.

usage:
  python3 analysis_scripts/tasktrace/pc_trace.py reduce <exec trace> \
      -o <run>/pc_trace.zst [--tasktrace <run>/tasktrace.jsonl] \
      [--vmlinux <guest vmlinux>] [--level N]
  python3 analysis_scripts/tasktrace/pc_trace.py verify <exec trace> \
      <pc trace> [--tasktrace <run>/tasktrace.jsonl]

The exec trace is gem5's --debug-file output (plain, .gz or .zst, a named
pipe, or - for stdin), from the atomic or the O3 core or both. Use
--debug-flags=ExecEnable,ExecUser,ExecKernel,ExecMacro: micro-op lines are
dropped and each architectural instruction is kept once, but ExecFaulting
(part of the Exec compound flag) adds instructions that did not commit.

Output format (text, one line per committed instruction):
  <pc hex> <mnemonic>   the PC is not the previous PC + 4 (a jump target,
                        an exception vector, or the first line after a
                        marker)
  <mnemonic>            the PC is the previous PC + 4
  ...\t<encoding hex>   either form, with the instruction's 32-bit
                        encoding (v2, Exec traces with ExecEncoding): given
                        when it differs from the last encoding seen under
                        the same decode key, or none was; otherwise it is
                        that last encoding
  #...                  header and marker lines; a task marker is
  #\ttask\t<tick>\t<tgid>\t<pid>\t<u|k>\t<process>\t<comm>
                        every instruction after it, up to the next marker,
                        ran as that task (tick: the tracer's switch tick)

Decode key of an instruction's encoding: the PC alone for kernel code (PC
bit 63); for user code, the PC and the tgid of the current marker, except
between the first marker and the second (the instructions before the first
switch, whose owner the reducer learns only at that switch), where the
tgid is taken as -1. A reader rebuilds every encoding from the trace alone
(read_pc_trace(..., encodings=True)). Code written at run time (a JIT, the
kernel patching itself) shows as a new encoding at a PC already seen.

Task markers come from the task trace's switch events. The tracer reports
a switch once per pass through __switch_to, when its first instruction is
next to commit, so the n-th committed instruction at that PC (link address
+ KASLR slide) is the n-th switch: the marker goes right before it. This
join works on every CPU model; ticks cannot be used, because O3's Exec
lines carry the fetch tick. On O3 the event fires when the call into
__switch_to commits, which can precede the fetch of __switch_to's first
instruction (a late fetch of the call target): the "switch ticks before
their Exec tick" count, which does not affect the join.
The first switch's prev owns everything before the first switch.
"""

import argparse
import gzip
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter

# tick: object: [A<asid> ][T<n> : ]0x<pc>[ @sym[+off]][.NN] :
#     [E=<bytes> ]<disassembly>
LINE_RE = re.compile(
    r"^(\d+): [^:]+: (?:A\d+ )?(?:T\d+ : )?0x([0-9a-f]+)"
    r"(?: @\S+)?(\.[ \d]\d)?\s+:\s+(?:E=([0-9a-f]+)\s+)?(\S+)"
)
FORMAT_VERSION = 2
# ExecEncoding prints the ExtMachInst on Arm: the encoding in the low 32
# bits, decoder state above.
ENCODING_MASK = 0xFFFFFFFF
SWITCH_SYMBOL = "__switch_to"
DEFAULT_VMLINUX = os.path.join(
    os.environ.get("CKPTS", "/home/snapshots/gem5-ckpts"),
    "rpoint_ckpts/agentic/kernel/arm64-linux-kernel-6.8.12-1.0.0",
)


def open_text(path, mode="rt", level=9):
    if path == "-":
        return sys.stdin if "r" in mode else sys.stdout
    if path.endswith(".gz"):
        return gzip.open(path, mode)
    if path.endswith(".zst"):
        from compression import zstd

        if "w" in mode:
            return zstd.open(path, mode, level=level)
        return zstd.open(path, mode)
    return open(path, mode)


def exec_insts(path):
    """Yield (tick, pc, mnemonic, encoding or None) once per architectural
    instruction."""
    with open_text(path) as f:
        for line in f:
            m = LINE_RE.match(line)
            if not m or m.group(3):  # not an Exec line, or a micro-op
                continue
            enc = m.group(4)
            if m.group(5).startswith("E="):   # the format drifted
                raise SystemExit(f"cannot parse the encoding: {line!r}")
            yield (int(m.group(1)), int(m.group(2), 16), m.group(5),
                   None if enc is None else int(enc, 16) & ENCODING_MASK)


def decode_key(pc, tgid):
    """The key an encoding is remembered under (see the format above);
    tgid is an int, -1 when unknown or before the first switch."""
    return pc if pc >> 63 else ((tgid + 2) << 64) | pc


def marker_tgid(field):
    return -1 if field == "?" else int(field)


def symbol_address(vmlinux, symbol):
    """Link address of a symbol in the guest kernel, via nm."""
    out = subprocess.run(
        ["nm", vmlinux], capture_output=True, text=True, check=True
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == symbol:
            return int(parts[0], 16)
    raise SystemExit(f"{symbol} not found in {vmlinux}")


def task_fields(task):
    kind = "k" if task.get("kthread") or task.get("pid") == 0 else "u"
    return (
        str(task.get("tgid", "?")),
        str(task.get("pid", "?")),
        kind,
        task.get("process", "?"),
        task.get("comm", "?"),
    )


class TaskFeed:
    """Events of a task trace, read incrementally.

    The trace may still be growing (gem5 writing it while the reducer reads
    the Exec trace from a pipe). The tracer writes and flushes a switch
    when __switch_to's first instruction is next to commit, before gem5
    prints that instruction's Exec line, so the event is in the file by
    the time the reducer reads the line.
    """

    def __init__(self, path):
        self.path = path
        self.f = None  # opened once gem5 has created the file
        self.partial = ""
        self.switches = []
        self.slide = None
        self.first_prev = None

    def read_more(self):
        if not self.f:
            if not self.path or not os.path.exists(self.path):
                return
            self.f = open(self.path)
        while True:
            chunk = self.f.readline()
            if not chunk:
                return
            self.partial += chunk
            if not self.partial.endswith("\n"):
                return  # half-written line: finish it on the next read
            line, self.partial = self.partial, ""
            e = json.loads(line)
            if e["event"] == "start":
                self.slide = e["kaslr_slide"]
            elif e["event"] == "switch":
                if self.first_prev is None and e.get("prev"):
                    self.first_prev = task_fields(e["prev"])
                self.switches.append((e["tick"], task_fields(e["next"])))

    def next_switch(self):
        if not self.switches:
            self.read_more()
        return self.switches.pop(0) if self.switches else None


def reduce_trace(src, out, tasktrace=None, vmlinux=DEFAULT_VMLINUX, level=9):
    feed = TaskFeed(tasktrace)
    link = symbol_address(vmlinux, SWITCH_SYMBOL) if tasktrace else None
    switch_pc = None
    stats = Counter()
    per_task = Counter()
    task = None
    prev_pc = None
    tgid = -1   # decode-key tgid: -1 until the first switch
    last_enc = {}
    with open_text(out, "wt", level) as real:
        real.write(f"#\tpc_trace\tv{FORMAT_VERSION}\n")
        # Until the first switch, its prev (the owner of everything before
        # it) is unknown when streaming: hold those lines in memory.
        w = io.StringIO()
        for tick, pc, mnem, enc in exec_insts(src):
            if link is not None and switch_pc is None:
                feed.read_more()
                if feed.slide is not None:
                    switch_pc = link + feed.slide
                    real.write(f"#\tkaslr_slide\t{feed.slide:#x}\n")
                    real.write(f"#\tswitch_pc\t{switch_pc:#x}\n")
            seq = prev_pc is not None and pc == prev_pc + 4
            if pc == switch_pc:
                sw = feed.next_switch()
                if sw is None:
                    stats["switch PCs without a switch event"] += 1
                else:
                    tick0, task = sw
                    stats["switches"] += 1
                    if tick0 < tick:
                        stats["switch ticks before their Exec tick"] += 1
                    if w is not real:
                        first = feed.first_prev or ("?",) * 4 + ("unknown",)
                        real.write("#\ttask\t0\t%s\n" % "\t".join(first))
                        real.write(w.getvalue())
                        per_task[first] += per_task.pop(None, 0)
                        w = real
                    w.write("#\ttask\t%d\t%s\n" % (tick0, "\t".join(task)))
                    tgid = marker_tgid(task[0])
                    seq = False  # the first line after a marker has its PC
            tail = ""
            if enc is not None:
                key = decode_key(pc, tgid)
                last = last_enc.get(key)
                if last != enc:
                    last_enc[key] = enc
                    tail = f"\t{enc:08x}"
                    stats["encodings written"] += 1
                    if last is not None:
                        stats["encoding changes"] += 1
            if seq:
                w.write(f"{mnem}{tail}\n")
            else:
                w.write(f"{pc:x} {mnem}{tail}\n")
                stats["explicit"] += 1
            prev_pc = pc
            stats["instructions"] += 1
            stats["nops"] += mnem == "nop"
            per_task[task] += 1
        if w is not real:  # no switch in the whole trace
            real.write("#\ttask\t0\t?\t?\t?\t?\tnot recorded\n")
            real.write(w.getvalue())
        feed.read_more()
        stats["switch events after the last instruction"] = len(feed.switches)
    return stats, per_task


def read_pc_trace(path, encodings=False):
    """Yield ("task", fields) and ("inst", pc, mnemonic) from a PC trace;
    with encodings, ("inst", pc, mnemonic, encoding or None).

    fields = (tick, tgid, pid, kind, process, comm).
    """
    pc = None
    markers, tgid = 0, -1
    last_enc = {}
    with open_text(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#"):
                parts = line.split("\t")
                if len(parts) >= 8 and parts[1] == "task":
                    markers += 1
                    if markers >= 2:
                        tgid = marker_tgid(parts[3])
                    yield ("task", tuple(parts[2:8]))
                continue
            line, _, enc = line.partition("\t")
            if " " in line:
                addr, mnem = line.split(" ", 1)
                pc = int(addr, 16)
            else:
                pc += 4
                mnem = line
            if not encodings:
                yield ("inst", pc, mnem)
                continue
            key = decode_key(pc, tgid)
            if enc:
                last_enc[key] = int(enc, 16)
            yield ("inst", pc, mnem, last_enc.get(key))


def verify(src, reduced, tasktrace=None):
    """Check the PC trace expands to the Exec trace's PC sequence."""
    a = exec_insts(src)
    n = encs = 0
    for item in read_pc_trace(reduced, encodings=True):
        if item[0] == "task":
            continue
        try:
            _, pc, mnem, enc = next(a)
        except StopIteration:
            print(f"FAIL: PC trace is longer than the Exec trace ({n})")
            return False
        if (pc, mnem, enc) != item[1:]:
            print(f"FAIL at instruction {n}: Exec {pc:#x} {mnem} {enc}, "
                  f"PC trace {item[1]:#x} {item[2]} {item[3]}")
            return False
        n += 1
        encs += enc is not None
    if next(a, None) is not None:
        print(f"FAIL: Exec trace is longer than the PC trace ({n})")
        return False
    print(f"OK: {n} instructions match PC for PC"
          + (f", with their encodings ({encs})" if encs else ""))
    if tasktrace:
        check_counts(tasktrace, reduced)
    return True


def check_counts(tasktrace, reduced):
    """Compare each complete slice with the tracer's instruction count.

    O3's count leaves out NOPs (the atomic CPU's does not), so slices are
    compared both with and without them.
    """
    sw = [json.loads(line) for line in open(tasktrace)]
    sw = [e for e in sw if e["event"] == "switch"]
    slices, cur, nops = [], 0, 0
    markers = 0
    for item in read_pc_trace(reduced):
        if item[0] == "task":
            if markers >= 2:  # a slice between two switches
                slices.append((cur, nops))
            markers += 1
            cur = nops = 0
        else:
            cur += 1
            nops += item[2] == "nop"
    gaps = [b["insts"] - a["insts"] for a, b in zip(sw, sw[1:])]
    pairs = list(zip(gaps, slices))
    same = sum(g == c for g, (c, _) in pairs)
    same_nonop = sum(g == c - k for g, (c, k) in pairs)
    print(f"slices between switches: {len(pairs)}; equal to the tracer's "
          f"count: {same} with NOPs, {same_nonop} without")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reduce", help="write a PC trace")
    r.add_argument("exec_trace")
    r.add_argument("-o", "--out", required=True,
                   help="output path (.zst, .gz or plain)")
    r.add_argument("--tasktrace", help="tasktrace.jsonl of the same run")
    r.add_argument("--vmlinux", default=DEFAULT_VMLINUX,
                   help="guest kernel with symbols (default: the agentic "
                   "kernel, which the SPEC guests share)")
    r.add_argument("--level", type=int, default=9,
                   help="compression level (default 9)")
    v = sub.add_parser("verify", help="check a PC trace against its source")
    v.add_argument("exec_trace")
    v.add_argument("pc_trace")
    v.add_argument("--tasktrace")
    args = ap.parse_args()

    if args.cmd == "reduce":
        stats, per_task = reduce_trace(args.exec_trace, args.out,
                                       args.tasktrace, args.vmlinux,
                                       args.level)
        n, explicit = stats["instructions"], stats["explicit"]
        print(f"{n} instructions ({stats['nops']} NOPs), {explicit} with an "
              f"explicit PC ({n / max(1, explicit):.1f} per run), "
              f"{stats['switches']} switches", file=sys.stderr)
        if stats["encodings written"]:
            print(f"encodings: {stats['encodings written']} written, "
                  f"{stats['encoding changes']} of them a change at a PC "
                  "already seen", file=sys.stderr)
        for key in ("switch PCs without a switch event",
                    "switch events after the last instruction",
                    "switch ticks before their Exec tick"):
            if stats[key]:
                print(f"WARNING: {stats[key]} {key}", file=sys.stderr)
        for task, count in per_task.most_common(10):
            name = (f"{task[3]}/{task[4]} ({task[0]}/{task[1]})" if task
                    else "before any marker")
            print(f"  {count:12d}  {name}", file=sys.stderr)
    else:
        ok = verify(args.exec_trace, args.pc_trace, args.tasktrace)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
