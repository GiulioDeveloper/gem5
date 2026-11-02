#!/bin/bash
# End-of-run stats compression, shared by the launchers. With
# COMPRESS_STATS=1, replaces OUTDIR/stats.txt by its values-only table
# OUTDIR/stats.tsv.zst (analysis_scripts/tasktrace/stats_table.py: every
# value is checked, and stats.txt is kept on a mismatch). KEEP_STATS=1 keeps
# stats.txt as well. PY selects the interpreter (Python 3.14+ for the
# built-in zstd). Does nothing without COMPRESS_STATS=1 or a stats.txt.
# usage: COMPRESS_STATS=1 run_scripts/compress-stats.sh OUTDIR
OUTDIR=${1:?outdir}
[ "${COMPRESS_STATS:-0}" = 1 ] || exit 0
[ -f "$OUTDIR/stats.txt" ] || exit 0
exec "${PY:-python3}" analysis_scripts/tasktrace/stats_table.py \
    "$OUTDIR/stats.txt" ${KEEP_STATS:+--keep}
