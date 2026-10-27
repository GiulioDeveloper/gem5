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
# At the end stats.txt is replaced by stats.tsv.zst (analysis_scripts/
# tasktrace/stats_table.py); KEEP_STATS=1 keeps both.
# OUTDIR=<dir> overrides the output directory; PY selects the interpreter
# (Python 3.14+ for the built-in zstd).
set -o pipefail

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

FIFO="$OUTDIR/exec.fifo"
rm -f "$FIFO"
mkfifo "$FIFO"
"$PY" analysis_scripts/tasktrace/pc_trace.py reduce "$FIFO" \
    -o "$OUTDIR/pc_trace.zst" --tasktrace "$OUTDIR/tasktrace.jsonl" \
    --vmlinux "$KERNEL" \
    2> "$OUTDIR/pc_trace.log" &
REDUCER=$!

./build/ARM/gem5.opt --outdir="$OUTDIR" "${G5[@]}" \
    --debug-flags=ExecEnable,ExecUser,ExecKernel,ExecMacro \
    --debug-file=exec.fifo \
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

wait "$REDUCER"
RSTATUS=$?
rm -f "$FIFO"
cat "$OUTDIR/pc_trace.log"

# Replace stats.txt by its values-only table (checked; kept on a mismatch).
# KEEP_STATS=1 keeps stats.txt as well.
if [ -f "$OUTDIR/stats.txt" ]; then
    "$PY" analysis_scripts/tasktrace/stats_table.py "$OUTDIR/stats.txt" \
        ${KEEP_STATS:+--keep}
fi
exit $(( STATUS != 0 ? STATUS : RSTATUS ))
