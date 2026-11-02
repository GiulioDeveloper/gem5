#!/bin/bash
# Traced restore of one agentic checkpoint that keeps a compact PC
# trace instead of gem5's full Exec trace: gem5 writes the Exec trace into a
# named pipe, and analysis_scripts/tasktrace/pc_trace.py reduces it on the
# fly, joining each instruction with its task from tasktrace.jsonl.
# usage: run_scripts/tasktrace/pc-trace.sh TASK MAX_INSTS [virt_run args...]
# Atomic core by default (MAX_INSTS instructions). O3="SETTLE WARMUP
# DETAILED" runs a detailed window instead (MAX_INSTS is then ignored); the
# whole run is traced, settle and warm-up included.
# GEM5_OPTS: gem5 options, placed before the config script (default
# "--stats-file=stats.txt?desc=False", which drops stat descriptions).
# At the end stats.txt is replaced by stats.tsv.zst (run_scripts/
# compress-stats.sh; on by default here, COMPRESS_STATS=0 keeps only the
# text); KEEP_STATS=1 keeps both.
# OUTDIR=<dir> overrides the output directory; PY selects the interpreter
# (Python 3.14+ for the built-in zstd); PC_TRACE_LEVEL the trace's zstd
# level (pc-trace-lib.sh). o3-window.sh / spec-window.sh with PC_TRACE=1
# record the same trace on a window in stats blocks.
set -o pipefail
. "$(dirname "$0")/pc-trace-lib.sh"

TASK=${1:?task}
MAX=${2:?max instructions}
shift 2

AGENTIC=${CKPTS:-/home/snapshots/gem5-ckpts}/rpoint_ckpts/agentic
OUTDIR=${OUTDIR:-runs/tasktrace/$(date +%Y%m%d-%H%M%S)-$TASK-pctrace}
PY=${PY:-python3}
read -r -a G5 <<< "${GEM5_OPTS-"--stats-file=stats.txt?desc=False"}"
KERNEL=$AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0
if [ -n "$O3" ]; then
    read -r SETTLE WARM DET <<< "$O3"
    MODE=(--settle-insts "$SETTLE" --warmup-insts "$WARM"
          --detailed-insts "$DET")
else
    MODE=(--atomic-only --atomic-max-insts "$MAX")
fi
mkdir -p "$OUTDIR"
echo "Output dir: $OUTDIR"

pc_trace_start "$OUTDIR" "$KERNEL" || exit 1

./build/ARM/gem5.opt --outdir="$OUTDIR" "${G5[@]}" "${PC_TRACE_G5[@]}" \
    configs/garfield/arm/virt_run.py \
    --restore-dir "$AGENTIC/checkpoints/agentic-$TASK/cpt.0" \
    --disk-img "$AGENTIC/images/rpoint-ubuntu-24.04-v21.img" \
    --kernel "$KERNEL" \
    --bootloader "$AGENTIC/bootloader/boot_v2_qemu_virt.arm64" \
    --release kvm-host \
    --progress-interval 10kHz \
    "${MODE[@]}" \
    --task-trace \
    "$@" \
    2>&1 | tee "$OUTDIR/run.log"
STATUS=$?

pc_trace_finish
RSTATUS=$?

COMPRESS_STATS=${COMPRESS_STATS:-1} PY=$PY \
    run_scripts/compress-stats.sh "$OUTDIR"
exit $(( STATUS != 0 ? STATUS : RSTATUS ))
