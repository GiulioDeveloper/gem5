#!/bin/bash
# Landing check over every local agentic checkpoint (the first cpt.N of each
# task): restore on the atomic core with the tracer for a few million
# instructions, then compare the first switch's outgoing task and the derived
# KASLR slide with the checkpoint's recorded landing label.
# usage: run_scripts/tasktrace/landing-all.sh [insts] [parallel]
#        BASE=<existing dir> SUMMARY_ONLY=1 run_scripts/tasktrace/landing-all.sh
#        re-summarizes a finished run; TASKS="gin-2121 ..." limits the tasks.
INSTS=${1:-3000000}
PAR=${2:-6}
AGENTIC=${CKPTS:-/home/snapshots/gem5-ckpts}/rpoint_ckpts/agentic
BASE=${BASE:-runs/tasktrace/$(date +%Y%m%d-%H%M%S)-landing-all}
mkdir -p "$BASE"

one() {
    local task=$1 out=$BASE/${1#agentic-}
    local cpt
    cpt=$(ls -d "$AGENTIC/checkpoints/$task"/cpt.* | head -1)
    [ -e "$out/tasktrace.jsonl" ] && return
    mkdir -p "$out"
    ./build/ARM/gem5.opt --outdir="$out" configs/garfield/arm/virt_run.py \
        --restore-dir "$cpt" \
        --disk-img "$AGENTIC/images/rpoint-ubuntu-24.04-v21.img" \
        --kernel "$AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0" \
        --bootloader "$AGENTIC/bootloader/boot_v2_qemu_virt.arm64" \
        --release kvm-host --atomic-only --atomic-max-insts "$INSTS" \
        --task-trace > "$out/run.log" 2>&1
}
export -f one
export BASE AGENTIC INSTS
[ -n "$SUMMARY_ONLY" ] ||
    { [ -n "$TASKS" ] && printf "agentic-%s\n" $TASKS || ls "$AGENTIC/checkpoints"; } |
    xargs -P "$PAR" -I{} bash -c 'one {}'

python3 analysis_scripts/tasktrace/landing_summary.py "$BASE" "$AGENTIC/checkpoints"
