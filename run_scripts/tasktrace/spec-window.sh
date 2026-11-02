#!/bin/bash
# Traced restore of a SPEC CPU 2026 FS SimPoint checkpoint through fs_run.py:
# SETTLE atomic instructions, WARMUP + DETAILED on O3 in INTERVAL-instruction
# stats blocks, with the task tracer.
# usage: run_scripts/tasktrace/spec-window.sh BENCH SETTLE WARMUP DETAILED INTERVAL [TAG] [extra fs_run args]
# OUTDIR=<dir> overrides the output directory. COMPRESS_STATS=1 replaces
# stats.txt by stats.tsv.zst at the end (run_scripts/compress-stats.sh).
# PC_TRACE=1 also records the compact, zstd-compressed PC trace
# (pc_trace.zst; pc-trace-lib.sh, PC_TRACE_LEVEL sets the level).
set -o pipefail
. "$(dirname "$0")/pc-trace-lib.sh"
BENCH=$1 SETTLE=$2 WARM=$3 DET=$4 IVL=$5 TAG=${6:-o3window}
shift 6 2>/dev/null || shift $#
SPEC=${CKPTS:-/home/snapshots/gem5-ckpts}/fs_ckpts/spec26
CPT=$(ls -d "$SPEC/ckpts/$BENCH"/*/cpt.* | head -1)
INV=$(basename "$(dirname "$CPT")")
export GEM5_RESOURCE_DIR=$(realpath "$SPEC/restore_resources")
OUTDIR=${OUTDIR:-runs/tasktrace/$(date +%Y%m%d-%H%M%S)-$BENCH-$TAG}
mkdir -p "$OUTDIR"
echo "Output dir: $OUTDIR"
PC_TRACE_G5=()
if [ "${PC_TRACE:-0}" = 1 ]; then
    pc_trace_start "$OUTDIR" "$SPEC/restore_resources/arm64-linux-kernel-6.8.12-1.0.0" || exit 1
fi
./build/ARM/gem5.opt --outdir="$OUTDIR" "--stats-file=stats.txt?desc=False" \
    "${PC_TRACE_G5[@]}" \
    configs/garfield/arm/fs_run.py \
    --restore-dir "$CPT" --benchmark "$BENCH" --inv "$INV" \
    --disk-img "$SPEC/restore_resources/spec_shared_root.img" \
    --settle-insts "$SETTLE" --warmup-insts "$WARM" \
    --detailed-insts "$DET" --stats-interval-insts "$IVL" \
    --task-trace "$@" 2>&1 | tee "$OUTDIR/run.log"
STATUS=$?
if [ "${PC_TRACE:-0}" = 1 ]; then
    pc_trace_finish
    RSTATUS=$?
    [ "$STATUS" = 0 ] && STATUS=$RSTATUS
fi
run_scripts/compress-stats.sh "$OUTDIR"
exit $STATUS
