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
# (2026-10-19; docs/wiki/pitfalls/sweep-memory-exhaustion.md).
#
# How: every launch, across all smart sweeps sharing LOCK, takes the lock,
# waits until there is room for the run, starts it, and holds the lock
# STAGGER seconds while the restore ramps up. Room means
#   MemAvailable - headroom of the gem5 runs already going >= need + RESERVE_GB
#   and memory pressure (/proc/pressure/memory, "some" avg10) <= PSI_MAX %
# A running run's headroom is its expected peak minus its current RSS
# (still to come). Every gem5.opt on the host counts, whoever started it
# (another user, a sweep.sh, a hand-run window): its task is read from its
# --restore-dir, and its expected peak is that task's need (below), and at
# least its own VmHWM; a gem5 without --restore-dir counts at its VmHWM.
# A task's need / expected peak is
#   - the task's peak RSS measured in an earlier run (PEAKS file), +15% and
#     0.5 GB, when there is one;
#   - otherwise a conservative estimate from the checkpoint's compressed
#     memory images (*.pmem): 2 GB + 6 x their size. The gzip ratio varies:
#     docusaurus-9897 and nushell-13831 both have 3.7 GB of images, but
#     hold 10.7 GB and more than 21 GB.
# The pressure check is there because a machine already short of memory
# shows it as stall time before MemAvailable looks low; a full swap alone
# (idle pages swapped out long ago) does not stop launches.
#
# Containment: each run goes in its own systemd user scope
# (systemd-run --user --scope) with MemoryMax = need + max(need/4, 2 GB)
# and no swap. A run that grows past it is OOM-killed alone: the kernel
# kills the largest process of the scope (gem5), the launcher finishes
# (OOMPolicy=continue), and the run is marked failed "out of memory". Its
# cap is recorded in PEAKS as a lower bound on its peak, so a resume asks
# for more. Without the scopes, an overrun pushed the whole machine into
# swap and systemd-oomd killed the terminal scope holding every run, the
# shell and Claude (2026-10-19). CAP=0 turns the scopes off.
#
# While a run goes, its gem5 peak RSS (VmHWM) is sampled and written to
# PEAKS every 5 minutes and at the end (per checkpoint, the maximum over
# runs, with the date and the run that set it), so later launches of the
# same task, in any sweep, use the measured value. PEAKS is tracked in git
# (run_scripts/tasktrace/mem_peaks.tsv) so every clone and user gets the
# measurements: commit it after a sweep. It is left out of sweep.conf's
# -dirty check. Each launch is logged to BASE/launch.log.
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
#       COMPRESS_STATS=1                replace each run's stats.txt by
#                                       stats.tsv.zst once it finishes
#                                       (run_scripts/compress-stats.sh;
#                                       the analysis reads either form)
#       PC_TRACE=1                      also record each run's compact
#                                       PC trace, pc_trace.zst
#                                       (pc-trace-lib.sh; the whole run
#                                       is traced, settle and warm-up
#                                       included)
#       RESERVE_GB=8                    memory kept free beyond a run's need
#       PSI_MAX=10                      no launch while memory pressure
#                                       ("some" avg10, %) is above this
#       RAMP_MIN=10                     minutes after which a running gem5
#                                       is taken to be at its peak (VmHWM)
#       CAP=1                           run each run in its own memory-
#                                       capped scope (0: no cap)
#       STAGGER=60                      seconds the lock is held after a launch
#       LOCK=/tmp/gem5-smart-sweep-$UID.lock   shared by concurrent sweeps
#       PEAKS=run_scripts/tasktrace/mem_peaks.tsv
#                                       measured peak RSS per checkpoint
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
BASE=${1:-runs/sweep/$(date +%Y%m%d-%H%M%S)}
export PAR=${PAR:-12} SETTLE=${SETTLE:-1} WARM=${WARM:-20000000}
export IVL=${IVL:-200000} SPEC_DET=${SPEC_DET:-200000000}
export AGENTIC_DET=${AGENTIC_DET:-400000000} BASE
export EXTRA=${EXTRA:-}
export COMPRESS_STATS=${COMPRESS_STATS:-0} PC_TRACE=${PC_TRACE:-0}
export RESERVE_GB=${RESERVE_GB:-8} STAGGER=${STAGGER:-60}
export PSI_MAX=${PSI_MAX:-10} CAP=${CAP:-1} RAMP_MIN=${RAMP_MIN:-10}
export LOCK=${LOCK:-/tmp/gem5-smart-sweep-$UID.lock}
export PEAKS=${PEAKS:-run_scripts/tasktrace/mem_peaks.tsv}
[ -f "$PEAKS" ] || { echo "no peaks file $PEAKS" >&2; exit 1; }
if [ "$CAP" = 1 ] &&
   ! systemd-run --user --scope -q -p MemoryMax=64M true 2>/dev/null; then
    echo "systemd-run --user --scope does not work here (no user manager" \
        "or no memory delegation), so runs cannot be capped; set CAP=0 to" \
        "run them uncapped" >&2
    exit 1
fi
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
commit $(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . \
    ':(exclude)run_scripts/tasktrace/mem_peaks.tsv' || echo -dirty)
SETTLE=$SETTLE WARM=$WARM IVL=$IVL SPEC_DET=$SPEC_DET AGENTIC_DET=$AGENTIC_DET
extra $EXTRA
compress_stats $COMPRESS_STATS
pc_trace $PC_TRACE
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
    awk -F'\t' -v t="$1" '$1 == t {print int($2 * 1.15) + 512}' "$PEAKS"
}
# Record peak $2 (MB) for task $1, set by run $3, keeping the maximum over
# runs. The rows stay sorted by task under the header comment, so the git
# diff of an update shows only the rows that changed.
record_peak() {
    (
        flock 8
        { grep '^#' "$PEAKS"
          awk -F'\t' -v OFS='\t' -v t="$1" -v p="$2" -v r="$3" \
              -v d="$(date +%F)" '
              /^#/ { next }
              $1 == t { if ($2 >= p) kept = 1; else next }
              { print }
              END { if (!kept) print t, p, d, r }' "$PEAKS" | LC_ALL=C sort
        } > "$PEAKS.tmp.$$" && mv "$PEAKS.tmp.$$" "$PEAKS"
    ) 8>"$LOCK.peaks"
}
# Need of a run of the task restored from checkpoint directory $1: the
# measured peak +15% +512 MB, or the image estimate. The task is the
# agentic-<task>/cpt.N or ckpts/<bench>/<inv>/cpt.N name.
need_mb() {
    local d=${1%/} task need
    d=${d%/cpt.*}
    case ${d##*/} in
        agentic-*) task=${d##*/agentic-} ;;
        *) task=${d%/*}; task=${task##*/} ;;
    esac
    need=$(measured_mb "$task")
    echo "${need:-$(estimate_mb "$1")}"
}
# Memory still to come on the host: over every gem5.opt process, whoever
# runs it, expected peak - current RSS. A run takes nearly all its memory
# in the restore and then stays flat, so past RAMP_MIN minutes its expected
# peak is its own VmHWM; before that, it is also at least the need of its
# --restore-dir checkpoint (a gem5 without --restore-dir counts at its
# VmHWM). Swapped-out pages (VmHWM above VmRSS) count as still to come.
headroom_mb() {
    local p rss hwm age cpt exp sum=0
    for p in $(pgrep -x gem5.opt); do
        read -r rss hwm < <(awk '/^VmRSS:/ {r = int($2 / 1024)}
            /^VmHWM:/ {h = int($2 / 1024)} END {print r, h}' \
            /proc/"$p"/status 2>/dev/null)
        age=$(ps -o etimes= -p "$p" 2>/dev/null)
        [ -n "$rss" ] && [ -n "$hwm" ] && [ -n "$age" ] ||
            continue   # exited meanwhile
        cpt=""
        [ "$age" -lt $((RAMP_MIN * 60)) ] &&
            cpt=$(tr '\0' '\n' < /proc/"$p"/cmdline 2>/dev/null | awk '
                f {print; exit}
                $0 == "--restore-dir" {f = 1}
                sub(/^--restore-dir=/, "") {print; exit}')
        exp=$hwm
        if [ -n "$cpt" ]; then
            exp=$(need_mb "$cpt")
            [ "$exp" -lt "$hwm" ] && exp=$hwm
        fi
        [ "$exp" -gt "$rss" ] && sum=$((sum + exp - rss))
    done
    echo "$sum"
}
# Memory pressure, "some" avg10 of /proc/pressure/memory, in whole %.
pressure_pct() {
    awk '/^some/ {sub(/avg10=/, "", $2); print int($2)}' /proc/pressure/memory
}
# The gem5 process of the run writing to outdir $1 (empty if none yet).
gem5_pid() {
    local p
    for p in $(pgrep -x gem5.opt); do
        tr '\0' ' ' < /proc/"$p"/cmdline 2>/dev/null |
            grep -q -- "--outdir=$1 " && { echo "$p"; return; }
    done
}
export -f estimate_mb measured_mb record_peak need_mb headroom_mb \
    pressure_pct gem5_pid

one() {
    local suite=$1 name=$2 out=$BASE/$1/$2 det t0 cpt need src avail head pid
    local psi cap waited=0 run=()
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
          psi=$(pressure_pct)
          [ $((avail - head)) -lt $((need + RESERVE_GB * 1024)) ] ||
          [ "$psi" -gt "$PSI_MAX" ]; do
        sleep 15
        waited=$((waited + 15))
    done
    cap=$((need + (need / 4 > 2048 ? need / 4 : 2048)))
    echo "$(date -Is) start $suite/$name: needs ~$(((need + 512) / 1024)) GB" \
        "($src), $((avail / 1024)) GB available, $(((head + 512) / 1024)) GB" \
        "still to come from running gem5s, pressure ${psi}%," \
        "$([ "$CAP" = 1 ] && echo "cap $(((cap + 512) / 1024)) GB," ||
           echo "no cap,") waited ${waited}s" >> "$BASE/launch.log"
    t0=$(date +%s)
    if [ "$suite" = spec ]; then
        det=$SPEC_DET
        run=(run_scripts/tasktrace/spec-window.sh "$name"
             "$SETTLE" "$WARM" "$det" "$IVL" o3window $EXTRA)
    else
        det=$AGENTIC_DET
        run=(run_scripts/tasktrace/o3-window.sh "$name"
             "$SETTLE" "$WARM" "$det" "$IVL" $EXTRA)
    fi
    # In its own scope, the run is capped at $cap MB with no swap; after
    # the launcher returns, the scope's OOM-kill count goes to
    # $out/oom_kill. 9>&- so the run does not inherit (and hold) the lock.
    if [ "$CAP" = 1 ]; then
        systemd-run --user --scope -q -p MemoryMax="${cap}M" \
            -p MemorySwapMax=0 -p OOMPolicy=continue -- \
            env OUTDIR="$out" bash -c '"${@:2}"; s=$?
                ev=/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)/memory.events
                awk "/^oom_kill / {print \$2}" "$ev" > "$1/oom_kill"
                exit $s' _ "$out" "${run[@]}" > /dev/null 2>&1 9>&- &
    else
        OUTDIR=$out "${run[@]}" > /dev/null 2>&1 9>&- &
    fi
    pid=$!
    # Find the run's gem5, then let it ramp up.
    local g="" i
    for i in $(seq 1 30); do
        g=$(gem5_pid "$out")
        [ -n "$g" ] && break
        sleep 1
    done
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
            record_peak "$name" "$peak" "$out"
            last=$SECONDS
        fi
        sleep 30
    done
    wait "$pid"
    [ "$peak" -gt 0 ] && record_peak "$name" "$peak" "$out"
    # Killed at its cap: the peak is at least the cap, so a resume asks
    # for more.
    if [ "$(cat "$out/oom_kill" 2>/dev/null || echo 0)" -gt 0 ]; then
        record_peak "$name" "$cap" "oom-cap $out"
        echo "out of memory: over its $cap MB cap" > "$out/failed"
        echo "OOM $suite/$name after $((($(date +%s) - t0) / 60)) min" \
            "(cap $(((cap + 512) / 1024)) GB)"
        return 1
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
