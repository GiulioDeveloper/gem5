#!/bin/bash
# Detailed-window sweep over every local checkpoint: each SPEC CPU 2026
# SimPoint checkpoint (spec-window.sh) and each agentic task (o3-window.sh)
# gets SETTLE atomic instructions, WARM of warm-up and a detailed O3 window
# in IVL-instruction stats blocks, with the task tracer. Each finished run is
# analysed (trace_analysis, trace_view, window_view) and marked `done`; at
# the end sweep_summary.py writes the cross-checkpoint table and violins.
#
# usage: run_scripts/tasktrace/sweep.sh [BASE]
#   BASE      output root (default runs/sweep/<timestamp>); rerunning with
#             the same BASE resumes: runs marked `done` are skipped, any
#             other run directory is started again from scratch.
#   env PAR=12 SETTLE=1 WARM=20000000 IVL=200000
#       SPEC_DET=200000000 AGENTIC_DET=400000000
#       ONLY="714.cpython_r jq-2598"   limit to these checkpoints
#       PY=python3                      interpreter for the summary (one
#                                       with matplotlib adds the PDFs)
#       EXTRA="--disable-fdp"           extra flags for every run, passed to
#                                       fs_run.py / virt_run.py (recorded
#                                       in sweep.conf; a resume must use
#                                       the same flags)
#       BASELINE=runs/sweep/<ts>        also compare this sweep with
#                                       BASELINE (sweep_compare.py), into
#                                       BASE/compare-<baseline name>
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
BASE=${1:-runs/sweep/$(date +%Y%m%d-%H%M%S)}
export PAR=${PAR:-12} SETTLE=${SETTLE:-1} WARM=${WARM:-20000000}
export IVL=${IVL:-200000} SPEC_DET=${SPEC_DET:-200000000}
export AGENTIC_DET=${AGENTIC_DET:-400000000} BASE
export EXTRA=${EXTRA:-}
PY=${PY:-python3}
SPEC=./gem5-ckpts/fs_ckpts/spec26/ckpts
AGENTIC=./gem5-ckpts/rpoint_ckpts/agentic/checkpoints
mkdir -p "$BASE"
if [ -f "$BASE/sweep.conf" ]; then
    prev=$(sed -n 's/^extra //p' "$BASE/sweep.conf")
    if [ "$prev" != "$EXTRA" ]; then
        echo "$BASE was run with EXTRA=\"$prev\", not \"$EXTRA\"" >&2
        exit 1
    fi
fi

jobs=()
for d in "$SPEC"/*/; do jobs+=("spec $(basename "$d")"); done
for d in "$AGENTIC"/agentic-*/; do
    n=$(basename "$d"); jobs+=("agentic ${n#agentic-}")
done
if [ -n "$ONLY" ]; then
    keep=()
    for j in "${jobs[@]}"; do
        for o in $ONLY; do [ "${j#* }" = "$o" ] && keep+=("$j"); done
    done
    jobs=("${keep[@]}")
fi

cat > "$BASE/sweep.conf" <<EOF
started $(date -Is)
commit $(git rev-parse --short HEAD)$(git diff --quiet HEAD || echo -dirty)
SETTLE=$SETTLE WARM=$WARM IVL=$IVL SPEC_DET=$SPEC_DET AGENTIC_DET=$AGENTIC_DET
extra $EXTRA
runs ${#jobs[@]}
EOF

one() {
    local suite=$1 name=$2 out=$BASE/$1/$2 det t0
    [ -e "$out/done" ] && return 0
    rm -rf "$out"   # an unfinished run from an interrupted sweep
    mkdir -p "$out"
    t0=$(date +%s)
    if [ "$suite" = spec ]; then
        det=$SPEC_DET
        OUTDIR=$out run_scripts/tasktrace/spec-window.sh "$name" \
            "$SETTLE" "$WARM" "$det" "$IVL" o3window $EXTRA > /dev/null 2>&1
    else
        det=$AGENTIC_DET
        OUTDIR=$out run_scripts/tasktrace/o3-window.sh "$name" \
            "$SETTLE" "$WARM" "$det" "$IVL" $EXTRA > /dev/null 2>&1
    fi
    # Complete when every detailed block was dumped.
    local blocks=0
    [ -f "$out/intervals.csv" ] && blocks=$(($(wc -l < "$out/intervals.csv") - 1))
    if [ "$blocks" -lt $((det / IVL)) ]; then
        echo "$blocks of $((det / IVL)) blocks" > "$out/failed"
        echo "FAILED $suite/$name after $((($(date +%s) - t0) / 60)) min ($blocks blocks)"
        return 1
    fi
    for t in trace_analysis trace_view window_view; do
        python3 configs/garfield/arm/$t.py "$out" >> "$out/analysis.log" 2>&1 \
            || echo "$t failed" >> "$out/failed"
    done
    touch "$out/done"
    echo "done $suite/$name in $((($(date +%s) - t0) / 60)) min"
}
export -f one

echo "Sweep of ${#jobs[@]} checkpoints into $BASE, $PAR at a time${EXTRA:+, with $EXTRA}"
printf '%s\n' "${jobs[@]}" | xargs -P "$PAR" -L 1 bash -c 'one $0 $1' \
    | tee -a "$BASE/progress.log"
echo "finished $(date -Is)" >> "$BASE/sweep.conf"
pdf=$("$PY" -c "import matplotlib" 2>/dev/null && echo --pdf)
"$PY" configs/garfield/arm/sweep_summary.py "$BASE" $pdf
if [ -n "$BASELINE" ]; then
    "$PY" configs/garfield/arm/sweep_compare.py "$BASELINE" "$BASE" $pdf
fi
