#!/bin/bash
# Detailed O3 window around a chosen point of an agentic checkpoint, with
# the task tracer and per-interval stats: fast-forward SETTLE instructions on
# the atomic core, warm up, then simulate DETAILED instructions on O3 in
# INTERVAL-instruction stats blocks.
# usage: run_scripts/tasktrace/o3-window.sh TASK SETTLE WARMUP DETAILED INTERVAL [extra virt_run args]
# OUTDIR=<dir> overrides the output directory.
set -o pipefail
TASK=$1 SETTLE=$2 WARM=$3 DET=$4 IVL=$5
shift 5
AGENTIC=./gem5-ckpts/rpoint_ckpts/agentic
CPT=$(ls -d "$AGENTIC/checkpoints/agentic-$TASK"/cpt.* | head -1)
OUTDIR=${OUTDIR:-runs/tasktrace/$(date +%Y%m%d-%H%M%S)-$TASK-o3window}
mkdir -p "$OUTDIR"
echo "Output dir: $OUTDIR"
./build/ARM/gem5.opt --outdir="$OUTDIR" "--stats-file=stats.txt?desc=False" \
    configs/garfield/arm/virt_run.py \
    --restore-dir "$CPT" \
    --disk-img "$AGENTIC/images/rpoint-ubuntu-24.04-v21.img" \
    --kernel "$AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0" \
    --bootloader "$AGENTIC/bootloader/boot_v2_qemu_virt.arm64" \
    --release kvm-host --progress-interval 10kHz \
    --settle-insts "$SETTLE" --warmup-insts "$WARM" \
    --detailed-insts "$DET" --stats-interval-insts "$IVL" \
    --task-trace "$@" 2>&1 | tee "$OUTDIR/run.log"
