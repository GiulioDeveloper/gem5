#!/bin/bash
# sweep.sh with memory-aware launching, so that several sweeps can run side by
# side without the machine running out of memory. Same jobs, outputs, resume
# behaviour and options as sweep.sh; the difference is how runs are started.
#
# Why: a run holds the guest memory its checkpoint has in use, which differs a
# lot between checkpoints (about 3 GB for most agentic tasks, 10.7 GB for
# docusaurus-9897, more than 21 GB for nushell-13831), and reaches most of it
# within a few minutes of the restore. Sweeps launched together walk the checkpoints in the same order, so
# the same heavy task restores several times at once; 12 restores at once
# went past 45 GB in under 30 s and systemd-oomd killed the whole terminal
# (2026-10-19; tracer research log, decision 21).
#
# How: every launch, across all smart sweeps sharing LOCK, takes the lock,
# waits until there is room for the run, starts it, and holds the lock
# STAGGER seconds while the restore ramps up. Room means
#   MemAvailable - headroom of the runs already going >= need + RESERVE_GB
# where a running run's headroom is its expected peak minus its current RSS
# (still to come), and a run's need / expected peak is
#   - the task's peak RSS measured in an earlier run (PEAKS file), +15% and
#     0.5 GB, when there is one;
#   - otherwise a conservative estimate from the checkpoint's compressed
#     memory images (*.pmem): 2 GB + 6 x their size. The gzip ratio varies:
#     docusaurus-9897 and nushell-13831 both have 3.7 GB of images, but
#     hold 10.7 GB and more than 21 GB.
# While a run goes, its gem5 peak RSS (VmHWM) is sampled and written to
# PEAKS (per checkpoint, the maximum over runs), so later launches of the
# same task, in any sweep, use the measured value. Each launch is logged to
# BASE/launch.log.
#
# usage: run_scripts/tasktrace/smart_sweep.sh [BASE]
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
#       RESERVE_GB=8                    memory kept free beyond a run's need
#       STAGGER=60                      seconds the lock is held after a launch
#       LOCK=/tmp/gem5-smart-sweep-$UID.lock   shared by concurrent sweeps
#       STATE=/tmp/gem5-smart-sweep-$UID.d     running runs (gem5 pid, peak)
#       PEAKS=runs/sweep/mem_peaks.tsv  measured peak RSS per checkpoint
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
BASE=${1:-runs/sweep/$(date +%Y%m%d-%H%M%S)}
export PAR=${PAR:-12} SETTLE=${SETTLE:-1} WARM=${WARM:-20000000}
export IVL=${IVL:-200000} SPEC_DET=${SPEC_DET:-200000000}
export AGENTIC_DET=${AGENTIC_DET:-400000000} BASE
export EXTRA=${EXTRA:-}
export RESERVE_GB=${RESERVE_GB:-8} STAGGER=${STAGGER:-60}
export LOCK=${LOCK:-/tmp/gem5-smart-sweep-$UID.lock}
export STATE=${STATE:-/tmp/gem5-smart-sweep-$UID.d}
export PEAKS=${PEAKS:-runs/sweep/mem_peaks.tsv}
mkdir -p "$STATE"
touch "$PEAKS"
PY=${PY:-python3}
export SPEC=${CKPTS:-/home/snapshots/gem5-ckpts}/fs_ckpts/spec26/ckpts
export AGENTIC=${CKPTS:-/home/snapshots/gem5-ckpts}/rpoint_ckpts/agentic/checkpoints
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

# All sizes below are in MB.
# Conservative estimate of a run's peak RSS from checkpoint $1's compressed
# memory images: 2 GB + 6 x their size.
estimate_mb() {
    local bytes
    bytes=$(du -cb "$1"/*.pmem 2>/dev/null | tail -1 | cut -f1)
    echo $((2048 + 6 * ${bytes:-0} / (1 << 20)))
}
# Expected peak of a run of task $1: the measured peak +15% +512 MB, or
# nothing when the task has not been measured yet.
measured_mb() {
    awk -v t="$1" '$1 == t {print int($2 * 1.15) + 512}' "$PEAKS"
}
# Record peak $2 (MB) for task $1, keeping the maximum over runs.
record_peak() {
    (
        flock 8
        awk -v t="$1" -v p="$2" '
            $1 == t { if ($2 > p) p = $2; next } { print }
            END { print t "\t" p }' "$PEAKS" > "$PEAKS.tmp" &&
            mv "$PEAKS.tmp" "$PEAKS"
    ) 8>"$PEAKS.lock"
}
# Memory still to come from the runs already going: the sum over STATE
# entries ("<gem5 pid> <expected peak MB>") of expected peak - current RSS.
headroom_mb() {
    local f pid exp rss sum=0
    for f in "$STATE"/*; do
        [ -f "$f" ] || continue
        read -r pid exp < "$f"
        rss=$(awk '/^VmRSS:/ {print int($2 / 1024)}' /proc/"$pid"/status \
              2>/dev/null) || { rm -f "$f"; continue; }
        [ -n "$rss" ] || { rm -f "$f"; continue; }
        [ "$exp" -gt "$rss" ] && sum=$((sum + exp - rss))
    done
    echo "$sum"
}
# The gem5 process of the run writing to outdir $1 (empty if none yet).
gem5_pid() {
    local p
    for p in $(pgrep -x gem5.opt); do
        tr '\0' ' ' < /proc/"$p"/cmdline 2>/dev/null |
            grep -q -- "--outdir=$1 " && { echo "$p"; return; }
    done
}
export -f estimate_mb measured_mb record_peak headroom_mb gem5_pid

one() {
    local suite=$1 name=$2 out=$BASE/$1/$2 det t0 cpt need src avail head pid
    local waited=0
    [ -e "$out/done" ] && return 0
    rm -rf "$out"   # an unfinished run from an interrupted sweep
    mkdir -p "$out"
    # The checkpoint spec-window.sh / o3-window.sh will restore.
    if [ "$suite" = spec ]; then
        cpt=$(ls -d "$SPEC/$name"/*/cpt.* | head -1)
    else
        cpt=$(ls -d "$AGENTIC/agentic-$name"/cpt.* | head -1)
    fi
    # One launch at a time across all smart sweeps: wait for room, start
    # the run, and keep the lock while its restore ramps up. The need is
    # looked up on every check: another run of the task may have recorded
    # its peak meanwhile.
    exec 9>"$LOCK"
    flock 9
    while need=$(measured_mb "$name")
          src=measured
          [ -n "$need" ] || { need=$(estimate_mb "$cpt"); src=estimated; }
          avail=$(awk '/^MemAvailable:/ {print int($2 / 1024)}' \
                  /proc/meminfo)
          head=$(headroom_mb)
          [ $((avail - head)) -lt $((need + RESERVE_GB * 1024)) ]; do
        sleep 15
        waited=$((waited + 15))
    done
    echo "$(date -Is) start $suite/$name: needs ~$(((need + 512) / 1024)) GB" \
        "($src), $((avail / 1024)) GB available, $(((head + 512) / 1024)) GB" \
        "still to come from running runs, waited ${waited}s" \
        >> "$BASE/launch.log"
    t0=$(date +%s)
    # 9>&- so the run does not inherit (and hold) the lock.
    if [ "$suite" = spec ]; then
        det=$SPEC_DET
        OUTDIR=$out run_scripts/tasktrace/spec-window.sh "$name" \
            "$SETTLE" "$WARM" "$det" "$IVL" o3window $EXTRA \
            > /dev/null 2>&1 9>&- &
    else
        det=$AGENTIC_DET
        OUTDIR=$out run_scripts/tasktrace/o3-window.sh "$name" \
            "$SETTLE" "$WARM" "$det" "$IVL" $EXTRA > /dev/null 2>&1 9>&- &
    fi
    pid=$!
    # Register the run's gem5 with its expected peak, then let it ramp up.
    local g="" state=$STATE/$$-$suite-$name i
    for i in $(seq 1 30); do
        g=$(gem5_pid "$out")
        [ -n "$g" ] && break
        sleep 1
    done
    [ -n "$g" ] && echo "$g $need" > "$state"
    # Sample the run's peak RSS (gem5 VmHWM): every 5 s while holding the
    # lock during the ramp-up, then every 30 s; record it every 5 minutes
    # and at the end.
    local peak=0 hwm last=$SECONDS t_end=$((SECONDS + STAGGER))
    sample() {
        [ -n "$g" ] || return 0
        hwm=$(awk '/^VmHWM:/ {print int($2 / 1024)}' /proc/"$g"/status \
              2>/dev/null)
        [ -n "$hwm" ] && [ "$hwm" -gt "$peak" ] && peak=$hwm
        return 0
    }
    while [ $SECONDS -lt $t_end ]; do
        sample
        sleep 5
    done
    flock -u 9
    exec 9>&-
    while kill -0 "$pid" 2>/dev/null; do
        sample
        if [ $((SECONDS - last)) -ge 300 ] && [ "$peak" -gt 0 ]; then
            record_peak "$name" "$peak"
            last=$SECONDS
        fi
        sleep 30
    done
    wait "$pid"
    rm -f "$state"
    [ "$peak" -gt 0 ] && record_peak "$name" "$peak"
    # Complete when every detailed block was dumped.
    local blocks=0
    [ -f "$out/intervals.csv" ] && blocks=$(($(wc -l < "$out/intervals.csv") - 1))
    if [ "$blocks" -lt $((det / IVL)) ]; then
        echo "$blocks of $((det / IVL)) blocks" > "$out/failed"
        echo "FAILED $suite/$name after $((($(date +%s) - t0) / 60)) min ($blocks blocks)"
        return 1
    fi
    for t in trace_analysis trace_view window_view; do
        python3 analysis_scripts/tasktrace/$t.py "$out" >> "$out/analysis.log" 2>&1 \
            || echo "$t failed" >> "$out/failed"
    done
    touch "$out/done"
    echo "done $suite/$name in $((($(date +%s) - t0) / 60)) min"
}
export -f one

echo "Smart sweep of ${#jobs[@]} checkpoints into $BASE, up to $PAR at a" \
    "time${EXTRA:+, with $EXTRA}; launches gated on memory (lock $LOCK)"
printf '%s\n' "${jobs[@]}" | xargs -P "$PAR" -L 1 bash -c 'one $0 $1' \
    | tee -a "$BASE/progress.log"
echo "finished $(date -Is)" >> "$BASE/sweep.conf"
pdf=$("$PY" -c "import matplotlib" 2>/dev/null && echo --pdf)
"$PY" analysis_scripts/tasktrace/sweep_summary.py "$BASE" $pdf
if [ -n "$BASELINE" ]; then
    "$PY" analysis_scripts/tasktrace/sweep_compare.py "$BASELINE" "$BASE" $pdf
fi
