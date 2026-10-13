#!/bin/bash
# No-perturbation check: the same short O3 window restored twice, without
# and with --task-trace. The hooks only read guest state, so stats.txt must
# be identical apart from host-side fields.
# usage: [PAIR_ON_ARGS="..."] run_scripts/tasktrace/o3-pair.sh [task] [warmup-insts] [detailed-insts]
# PAIR_ON_ARGS= (empty) runs the plain config twice: a determinism check.
set -o pipefail

TASK=${1:-gin-2121}
WARM=${2:-1000000}
DET=${3:-5000000}

AGENTIC=./gem5-ckpts/rpoint_ckpts/agentic
BASE=runs/tasktrace/$(date +%Y%m%d-%H%M%S)-$TASK-o3pair

run() {
    local out=$1; shift
    mkdir -p "$out"
    ./build/ARM/gem5.opt --outdir="$out" configs/garfield/arm/virt_run.py \
        --restore-dir "$AGENTIC/checkpoints/agentic-$TASK/cpt.0" \
        --disk-img "$AGENTIC/images/rpoint-ubuntu-24.04-v21.img" \
        --kernel "$AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0" \
        --bootloader "$AGENTIC/bootloader/boot_v2_qemu_virt.arm64" \
        --release kvm-host \
        --progress-interval 10kHz \
        --settle-insts 0 --warmup-insts "$WARM" --detailed-insts "$DET" \
        "$@" > "$out/run.log" 2>&1
}

run "$BASE/off" &
run "$BASE/on" ${PAIR_ON_ARGS---task-trace} &
wait

strip() { grep -vE '^(hostSeconds|hostTickRate|hostMemory|hostInstRate|hostOpRate)' "$1"; }
if diff <(strip "$BASE/off/stats.txt") <(strip "$BASE/on/stats.txt") > "$BASE/stats.diff"; then
    echo "IDENTICAL stats ($BASE)"
else
    echo "DIFFERENT stats: $(wc -l < "$BASE/stats.diff") diff lines ($BASE/stats.diff)"
fi
grep -h "IPC (measured)" "$BASE"/{off,on}/run.log
wc -l "$BASE/on/tasktrace.jsonl"
