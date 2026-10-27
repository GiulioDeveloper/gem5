#!/bin/bash
# Compare long traced runs of the same checkpoint under different
# configurations (one run each, e.g. a limit study).
# 1. Per run, over its whole region: trace_analysis.py and window_view.py
#    (outputs in <run>/analysis/), in parallel.
# 2. A common region: the first N stats blocks of every run, N the smallest
#    block count, laid out as OUT/<label>/agentic/<TASK> (the layout of a
#    sweep), then sweep_summary.py per run and sweep_compare.py of all of
#    them against the first (OUT/compare/).
# 3. process_views.py over the whole regions (OUT/process_views.csv; its
#    IPC summary in OUT/process_views.txt).
# Split a stalled run first (split_stall.sh). Faster configurations get
# further into the guest's work in the same instructions, so the common
# region compares different work; process_views compares like with like
# (docs/wiki/methodology/comparing-configurations.md).
# usage (from the repo root):
#   analysis_scripts/tasktrace/compare_runs.sh OUT RUN [RUN ...]
# The run directory names are the labels; the first run is the baseline.
# TASK names the task in the sweep layout (default: "task"). Logs in OUT/logs/.
set -eu
OUT=${1:?output dir}
shift
[ $# -ge 2 ] || { echo "usage: $0 OUT RUN RUN [RUN ...]"; exit 1; }
RUNS=("$@")
TASK=${TASK:-task}
A=analysis_scripts/tasktrace
for r in "${RUNS[@]}"; do
    [ -f "$r/stats.tsv.zst" ] || { echo "$r: no stats.tsv.zst (stats_table.py converts stats.txt)"; exit 1; }
done
LABELS=()
for r in "${RUNS[@]}"; do LABELS+=("$(basename "$r")"); done
mkdir -p "$OUT/logs"

for i in "${!RUNS[@]}"; do
    r=${RUNS[$i]} n=${LABELS[$i]}
    (
        python3 $A/trace_analysis.py "$r" > "$OUT/logs/trace_analysis-$n.log" 2>&1
        python3 $A/window_view.py "$r" > "$OUT/logs/window_view-$n.log" 2>&1
        echo "$n: per-run analysis done"
    ) &
done
wait

N=$(for r in "${RUNS[@]}"; do echo $(($(wc -l < "$r/intervals.csv") - 1)); done \
    | sort -n | head -n 1)
echo "common region: the first $N blocks"
for i in "${!RUNS[@]}"; do
    r=${RUNS[$i]} d=$OUT/${LABELS[$i]}/agentic/$TASK
    rm -rf "$d"
    mkdir -p "$d"
    head -n $((N + 1)) "$r/intervals.csv" > "$d/intervals.csv"
    zstd -dc "$r/stats.tsv.zst" | head -n $((N + 2)) | zstd -q -3 -T0 -o "$d/stats.tsv.zst"
    ln -s "$(realpath "$r/tasktrace.jsonl")" "$d/tasktrace.jsonl"
    ln -s "$(realpath "$r/config.ini")" "$d/config.ini"
    echo "first $N blocks of $r" > "$d/COMMON.txt"
done
for n in "${LABELS[@]}"; do
    python3 $A/sweep_summary.py "$OUT/$n" > "$OUT/logs/sweep_summary-$n.log" 2>&1 &
done
wait
python3 $A/sweep_compare.py "${LABELS[@]/#/$OUT/}" -o "$OUT/compare" \
    --labels "${LABELS[@]}" > "$OUT/logs/compare.log" 2>&1
echo "compare: $OUT/compare"
python3 $A/process_views.py "${RUNS[@]}" -o "$OUT/process_views.csv" \
    > "$OUT/process_views.txt" 2> "$OUT/logs/process_views.log"
echo "process views: $OUT/process_views.csv, summary in $OUT/process_views.txt"
