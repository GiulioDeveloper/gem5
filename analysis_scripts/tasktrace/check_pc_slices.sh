#!/bin/bash
# Check that a PC trace and its task trace agree: the instructions between
# consecutive task markers of pc_trace.zst, against the tracer's global
# instruction count between the same switch events. On O3 the tracer's count
# leaves NOPs out, on the atomic core it includes them; both are compared.
# Prints the counts of equal and different slices (and up to 10 of the
# different ones); exits 1 if any differs. Fast: one awk pass over the
# trace (about 10 minutes per 15G instructions).
# usage (from the repo root): analysis_scripts/tasktrace/check_pc_slices.sh <run>
set -euo pipefail
RUN=${1:?run dir}
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
zstd -dc "$RUN/pc_trace.zst" | LC_ALL=C awk -F'\t' '
    /^#\ttask\t/ { if (m++) print tick, n, nop; tick = $3; n = 0; nop = 0; next }
    /^#/ { next }
    { n++; if ($0 ~ /(^| )nop$/) nop++ }' > "$TMP"
python3 - "$RUN/tasktrace.jsonl" "$TMP" <<'PY'
import json
import sys

ev = [json.loads(line) for line in open(sys.argv[1])]
sw = [(e["tick"], e["insts"]) for e in ev if e["event"] == "switch"]
nxt = {sw[k][0]: sw[k + 1][1] - sw[k][1] for k in range(len(sw) - 1)}
eq_nonop = eq_all = other = 0
bad = []
for line in open(sys.argv[2]):
    t, n, nop = map(int, line.split())
    if t not in nxt:
        continue                     # the tick-0 slice, before the first switch
    want = nxt[t]
    if n - nop == want:
        eq_nonop += 1
    elif n == want:
        eq_all += 1
    else:
        other += 1
        if len(bad) < 10:
            bad.append((t, n, nop, want))
print(f"{sys.argv[1].rsplit('/', 1)[0]}: slices equal without NOPs {eq_nonop}, "
      f"equal with NOPs {eq_all}, different {other}")
for b in bad:
    print("  tick %d: %d instructions (%d NOPs), tracer %d" % b)
sys.exit(1 if other else 0)
PY
