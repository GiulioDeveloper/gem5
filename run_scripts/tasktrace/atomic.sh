#!/bin/bash
# Task-tracer dev loop: restore one agentic checkpoint on the ATOMIC core
# only and trace guest task events for a bounded number of instructions.
# usage: [GEM5_OPTS="--debug-flags=..."] run_scripts/tasktrace/atomic.sh [task] [max-insts] [extra virt_run args...]
set -o pipefail

TASK=${1:-gin-2121}
MAX=${2:-20000000}
shift 2 2>/dev/null

AGENTIC=${CKPTS:-/home/snapshots/gem5-ckpts}/rpoint_ckpts/agentic
OUTDIR=runs/tasktrace/$(date +%Y%m%d-%H%M%S)-$TASK-atomic
mkdir -p "$OUTDIR"
echo "Output dir: $OUTDIR"

./build/ARM/gem5.opt --outdir="$OUTDIR" $GEM5_OPTS configs/garfield/arm/virt_run.py \
    --restore-dir "$AGENTIC/checkpoints/agentic-$TASK/cpt.0" \
    --disk-img "$AGENTIC/images/rpoint-ubuntu-24.04-v21.img" \
    --kernel "$AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0" \
    --bootloader "$AGENTIC/bootloader/boot_v2_qemu_virt.arm64" \
    --release kvm-host \
    --progress-interval 10kHz \
    --atomic-only --atomic-max-insts "$MAX" \
    --task-trace \
    "$@" \
    2>&1 | tee "$OUTDIR/run.log"
