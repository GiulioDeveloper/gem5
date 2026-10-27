#!/bin/bash
# Move a trailing guest stall of a traced run into <run>/stall/, so the
# analysis covers only the region where the guest did useful work.
# A run stalls when the guest stops switching tasks: no tracer event after
# its last switch, while the simulation goes on (the agentic checkpoints
# hang this way at their first RNG reseed, docs/wiki/pitfalls/
# guest-trng-hvc-stall.md). The stall starts at the run's last tracer event
# when the run went on for more than STALL_MIN ticks after it; a run that
# did not stall is left alone.
#   intervals.csv, stats.tsv.zst: blocks starting before the stall stay,
#     the rest go to stall/ (the block holding the switch stays, so the
#     stats keep up to one block of stall instructions);
#   pc_trace.zst (if any): cut at the last task marker (the switch into the
#     stalled task); stall/pc_trace.zst gets the header lines and the rest.
# The originals are kept as *.orig until the blocks, stats rows and PC trace
# instructions add up, then deleted; stall/SPLIT.txt records the split.
# Needs the values-only stats table (stats_table.py) and zstd.
# usage (from the repo root): analysis_scripts/tasktrace/split_stall.sh <run>
set -eu   # no pipefail: zstd -dc | head ends with SIGPIPE; the counts below check the split
RUN=${1:?run dir}
STALL_MIN=${STALL_MIN:-100000000000}   # 0.1 s simulated
LEVEL=${LEVEL:-9}

read -r T_EV EVENT <<< "$(tail -n 1 "$RUN/tasktrace.jsonl" | python3 -c '
import json, sys; e = json.loads(sys.stdin.read()); print(e["tick"], e["event"])')"
T_END=$(tail -n 1 "$RUN/intervals.csv" | cut -d, -f3)
if [ $((T_END - T_EV)) -lt "$STALL_MIN" ]; then
    echo "$RUN: no stall (last event at $T_EV, end at $T_END)"
    exit 0
fi
[ "$EVENT" = switch ] || { echo "$RUN: last event is $EVENT, not a switch"; exit 1; }
# The readers prefer stats.txt over the table, so it would hide the split.
[ -f "$RUN/stats.tsv.zst" ] && [ ! -e "$RUN/stats.txt" ] \
    || { echo "$RUN: needs stats.tsv.zst and no stats.txt (stats_table.py converts)"; exit 1; }
[ -e "$RUN/stall" ] && { echo "$RUN: stall/ exists already"; exit 1; }
mkdir "$RUN/stall"

# Blocks: K = number of blocks that start before the stall.
K=$(awk -F, -v t="$T_EV" 'NR > 1 && $2 < t { k++ } END { print k }' \
    "$RUN/intervals.csv")
NB=$(($(wc -l < "$RUN/intervals.csv") - 1))
mv "$RUN/intervals.csv" "$RUN/intervals.csv.orig"
head -n $((K + 1)) "$RUN/intervals.csv.orig" > "$RUN/intervals.csv"
{ head -n 1 "$RUN/intervals.csv.orig"; tail -n +$((K + 2)) "$RUN/intervals.csv.orig"; } \
    > "$RUN/stall/intervals.csv"

# Stats table: 2 header lines, then one row per block (a killed run can
# have one more row than intervals.csv: dumped, not yet logged).
mv "$RUN/stats.tsv.zst" "$RUN/stats.tsv.zst.orig"
zstd -dc "$RUN/stats.tsv.zst.orig" | head -n $((K + 2)) \
    | zstd -q -19 -T0 -o "$RUN/stats.tsv.zst"
zstd -dc "$RUN/stats.tsv.zst.orig" \
    | awk -v k="$K" 'NR <= 2 || NR > k + 2' \
    | zstd -q -19 -T0 -o "$RUN/stall/stats.tsv.zst"
ROWS=$(zstd -dc "$RUN/stats.tsv.zst.orig" | tail -n +3 | wc -l)

# PC trace: byte offset of the last task marker.
HAS_PC=0
if [ -f "$RUN/pc_trace.zst" ]; then
    HAS_PC=1
    mv "$RUN/pc_trace.zst" "$RUN/pc_trace.zst.orig"
    OFF=$(zstd -dc "$RUN/pc_trace.zst.orig" | grep -abP '^#\ttask\t' | tail -n 1 \
        | cut -d: -f1)
    zstd -dc "$RUN/pc_trace.zst.orig" | head -c "$OFF" \
        | zstd -q -"$LEVEL" -T0 -o "$RUN/pc_trace.zst"
    { zstd -dc "$RUN/pc_trace.zst.orig" | head -n 3 | grep '^#'
      zstd -dc "$RUN/pc_trace.zst.orig" | tail -c +$((OFF + 1)); } \
        | zstd -q -"$LEVEL" -T0 -o "$RUN/stall/pc_trace.zst"
fi

# Checks: blocks, rows and instructions add up.
count() { zstd -dc "$1" | grep -vc '^#' || true; }
I_ALL=0 I_MAIN=0 I_STALL=0
if [ "$HAS_PC" = 1 ]; then
    I_ALL=$(count "$RUN/pc_trace.zst.orig")
    I_MAIN=$(count "$RUN/pc_trace.zst")
    I_STALL=$(count "$RUN/stall/pc_trace.zst")
fi
R_STALL=$(zstd -dc "$RUN/stall/stats.tsv.zst" | tail -n +3 | wc -l)
NB_STALL=$(($(wc -l < "$RUN/stall/intervals.csv") - 1))
echo "$RUN: stall at tick $T_EV; blocks $K + $NB_STALL of $NB;" \
    "stats rows $K + $R_STALL of $ROWS; PC trace instructions $I_MAIN + $I_STALL of $I_ALL"
if [ $((K + NB_STALL)) -ne "$NB" ] || [ $((K + R_STALL)) -ne "$ROWS" ] \
    || [ $((I_MAIN + I_STALL)) -ne "$I_ALL" ]; then
    echo "$RUN: MISMATCH, originals kept (*.orig)"
    exit 1
fi
rm -f "$RUN/intervals.csv.orig" "$RUN/stats.tsv.zst.orig" "$RUN/pc_trace.zst.orig"
{
    echo "stall start: tick $T_EV (last tracer event: a switch)"
    echo "blocks: $K before the stall (intervals.csv), $NB_STALL in stall/"
    echo "stats rows: $K / $R_STALL"
    if [ "$HAS_PC" = 1 ]; then
        echo "pc_trace instructions: $I_MAIN before the last task marker, $I_STALL after"
    fi
} > "$RUN/stall/SPLIT.txt"
