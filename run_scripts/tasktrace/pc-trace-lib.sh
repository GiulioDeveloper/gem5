# Sourced by the launchers that record a PC trace (pc-trace.sh, and
# o3-window.sh / spec-window.sh with PC_TRACE=1). gem5 writes its Exec trace
# into a named pipe in the output directory, and analysis_scripts/tasktrace/
# pc_trace.py reduces it on the fly to the compact, zstd-compressed PC trace
# (pc_trace.zst), joined with the run's task trace; the full Exec trace is
# never stored. The whole run is traced, settle and warm-up included.
#   pc_trace_start OUTDIR VMLINUX  start the reducer; sets PC_TRACE_G5, the
#                                  gem5 options (before the config script)
#   pc_trace_finish                after gem5 exits: wait for the reducer,
#                                  print its log; returns its status
# PY selects the interpreter (Python 3.14+ for the built-in zstd);
# PC_TRACE_LEVEL the zstd level (default 9; higher is smaller but slower,
# and the reducer must keep up with gem5).

pc_trace_start() {
    PC_TRACE_DIR=$1
    rm -f "$PC_TRACE_DIR/exec.fifo"
    mkfifo "$PC_TRACE_DIR/exec.fifo" || return 1
    "${PY:-python3}" analysis_scripts/tasktrace/pc_trace.py reduce \
        "$PC_TRACE_DIR/exec.fifo" -o "$PC_TRACE_DIR/pc_trace.zst" \
        --tasktrace "$PC_TRACE_DIR/tasktrace.jsonl" --vmlinux "$2" \
        --level "${PC_TRACE_LEVEL:-9}" \
        2> "$PC_TRACE_DIR/pc_trace.log" &
    PC_TRACE_PID=$!
    PC_TRACE_G5=(--debug-flags=ExecEnable,ExecUser,ExecKernel,ExecMacro
                 --debug-file=exec.fifo)
}

pc_trace_finish() {
    local status
    # If gem5 died before opening the pipe, the reducer is still blocked
    # opening it: open and close it once so the reducer sees end of file.
    if kill -0 "$PC_TRACE_PID" 2>/dev/null; then
        timeout 10 sh -c ': > "$0"' "$PC_TRACE_DIR/exec.fifo" 2>/dev/null
    fi
    wait "$PC_TRACE_PID"
    status=$?
    rm -f "$PC_TRACE_DIR/exec.fifo"
    cat "$PC_TRACE_DIR/pc_trace.log"
    return $status
}
