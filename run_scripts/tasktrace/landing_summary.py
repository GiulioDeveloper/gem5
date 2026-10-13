"""Compare each traced restore's first switch with its landing label.

usage: python3 run_scripts/tasktrace/landing_summary.py <landing-run dir> <checkpoints>
"""

import json
import sys
from pathlib import Path

base, cpts = Path(sys.argv[1]), Path(sys.argv[2])
ok = bad = 0
for d in sorted(p for p in base.iterdir() if p.is_dir()):
    cpt = sorted((cpts / f"agentic-{d.name}").glob("cpt.*"))[0]
    land = json.loads((cpt / "provenance.json").read_text()).get("landing") or {}
    tr = d / "tasktrace.jsonl"
    if not tr.exists():
        print(f"{d.name:24} NO TRACE (see run.log)")
        bad += 1
        continue
    ev = [json.loads(line) for line in open(tr)]
    slide = ev[0]["kaslr_slide"]
    first = next((e for e in ev if e["event"] == "switch" and e["prev"]), None)
    prev = first and first["prev"]
    desc = prev and (prev["pid"], prev["comm"], prev["process"])
    if not land.get("pid"):
        print(f"{d.name:24} ({cpt.name}) no label; slide {slide:#x}; "
              f"first switch away from {desc}")
        continue
    # The landing task may be renamed before its first switch by an exec that
    # was in flight at the dump; the trace records that exec.
    renamed = bool(prev) and any(
        e["event"] == "exec" and e["task"]["pid"] == prev["pid"]
        and e["insts"] <= first["insts"] for e in ev)
    match = bool(prev) and int(land["kaslr_slide"], 16) == slide \
        and prev["pid"] == land["pid"] \
        and (prev["comm"] == land["comm"] or renamed)
    note = (" (renamed by an in-flight exec)"
            if match and prev["comm"] != land["comm"] else "")
    if not prev:
        # No switch yet: fall back to the start-up process snapshot, which
        # must hold the landing task under its recorded name.
        snap = next((e for e in ev if e["event"] == "snapshot"), None)
        hit = snap and any(t["pid"] == land["pid"] and t["comm"] == land["comm"]
                           for t in snap["tasks"])
        match = bool(hit) and int(land["kaslr_slide"], 16) == slide
        note = " (no switch yet; found in the snapshot)" if match else ""
    ok += match
    bad += not match
    print(f"{d.name:24} ({cpt.name}) {'OK      ' if match else 'MISMATCH'} "
          f"label=({land['pid']},{land['comm']},{land.get('process')}) "
          f"trace={desc}{note}")
print(f"{ok} match, {bad} mismatch/failed")
