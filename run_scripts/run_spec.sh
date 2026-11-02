#!/bin/bash
# Restore a SPEC FS checkpoint on the detailed O3 core.
# usage: runs/run_spec.sh <benchmark> <inv> <simpoint> [warmup] [detailed]
# COMPRESS_STATS=1 replaces stats.txt by stats.tsv.zst at the end
# (run_scripts/compress-stats.sh).
set -o pipefail
B=${1:-777.zstd_r}; INV=${2:-0}; SP=${3:-1}
WARM=${4:-10000000}; DET=${5:-50000000}
R=${CKPTS:-/home/snapshots/gem5-ckpts}/fs_ckpts/spec26
export GEM5_RESOURCE_DIR=$R/restore_resources
OUTDIR=runs/$(date +%Y%m%d-%H%M%S)-spec-$B-$INV-$SP
mkdir -p "$OUTDIR"; echo "Output dir: $OUTDIR"
./build/ARM/gem5.opt --outdir=$OUTDIR configs/garfield/arm/fs_run.py \
    --restore-dir $R/ckpts/$B/$INV/cpt.$B.$INV.$SP \
    --benchmark $B --inv $INV \
    --disk-img $R/restore_resources/spec_shared_root.img \
    --progress-interval 10kHz \
    --warmup-insts $WARM --detailed-insts $DET 2>&1 | tee "$OUTDIR/run.log"
STATUS=$?
run_scripts/compress-stats.sh "$OUTDIR"
exit $STATUS
