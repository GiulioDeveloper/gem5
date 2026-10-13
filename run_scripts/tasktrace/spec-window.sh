#!/bin/bash
# Traced restore of a SPEC CPU 2026 FS SimPoint checkpoint through fs_run.py:
# SETTLE atomic instructions, WARMUP + DETAILED on O3 in INTERVAL-instruction
# stats blocks, with the task tracer.
# usage: run_scripts/tasktrace/spec-window.sh BENCH SETTLE WARMUP DETAILED INTERVAL [TAG] [extra fs_run args]
set -o pipefail
BENCH=$1 SETTLE=$2 WARM=$3 DET=$4 IVL=$5 TAG=${6:-o3window}
shift 6 2>/dev/null || shift $#
SPEC=./gem5-ckpts/fs_ckpts/spec26
CPT=$(ls -d "$SPEC/ckpts/$BENCH"/*/cpt.* | head -1)
INV=$(basename "$(dirname "$CPT")")
export GEM5_RESOURCE_DIR=$(realpath "$SPEC/restore_resources")
OUTDIR=runs/tasktrace/$(date +%Y%m%d-%H%M%S)-$BENCH-$TAG
mkdir -p "$OUTDIR"
echo "Output dir: $OUTDIR"
./build/ARM/gem5.opt --outdir="$OUTDIR" "--stats-file=stats.txt?desc=False" \
    configs/garfield/arm/fs_run.py \
    --restore-dir "$CPT" --benchmark "$BENCH" --inv "$INV" \
    --disk-img "$SPEC/restore_resources/spec_shared_root.img" \
    --settle-insts "$SETTLE" --warmup-insts "$WARM" \
    --detailed-insts "$DET" --stats-interval-insts "$IVL" \
    --task-trace "$@" 2>&1 | tee "$OUTDIR/run.log"
