#!/usr/bin/env bash
# Build gem5, pinning the toolchain to Anaconda when it is present.
#
# Hosts without Anaconda fall back to a plain scons build with the system
# toolchain (no wrapper needed). Hosts that run with the Anaconda base env active, which collides with the
# system development libraries. This wrapper pins gem5's toolchain to Anaconda
# consistently: the embedded Python, and protobuf (5.29.3) + abseil. See
# CLAUDE.md for the full rationale.
#
# HDF5 is disabled by default in src/base/stats/SConsopts (Anaconda's
# libhdf5_cpp clashes with the system headers gem5 compiles against). Export
# GEM5_ENABLE_HDF5=1 before running this to re-enable it where a consistent
# HDF5 installation exists.
#
# The built binary has an rpath to the Python lib dir (see SConstruct), so it
# runs without LD_LIBRARY_PATH -- important for Slurm batch jobs, which do not
# source ~/.bashrc.
#
# Usage:
#   ./build-gem5.sh [TARGET] [extra scons args...]
#   ANACONDA=/cluster/path/anaconda3 ./build-gem5.sh build/X86/gem5.opt
#   JOBS=32 ./build-gem5.sh build/X86/gem5.opt
#
# Defaults: TARGET=build/X86/gem5.opt, JOBS=$(nproc), ANACONDA from this host.
set -euo pipefail

ANACONDA="${ANACONDA:-/home/rahbera/anaconda3}"
if [ -x "${ANACONDA}/bin/protoc" ]; then
# libpython/libprotobuf/abseil live here. Needed at build time (configure links
# a small test binary, and protoc/headers must come from here). The built
# binary embeds an rpath to this dir, so it is not needed to *run* gem5.
    export LD_LIBRARY_PATH="${ANACONDA}/lib:${LD_LIBRARY_PATH:-}"
    # Resolve protobuf (and other pkg-config deps) from Anaconda so the
    # headers match Anaconda's protoc; this avoids the stale /usr/local
    # protobuf 3.3.0.
    export PKG_CONFIG_PATH="${ANACONDA}/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
    export PROTOC="${ANACONDA}/bin/protoc"
else
    echo ">> No Anaconda at ANACONDA=${ANACONDA}; using the system toolchain."
fi

TARGET="${1:-build/X86/gem5.opt}"
[ $# -gt 0 ] && shift
JOBS="${JOBS:-$(nproc)}"

cd "$(dirname "$0")"

# After a `--config=force` reconfigure, scons can finish a pass having compiled
# everything but without linking the final binary; a second pass performs the
# link. Running twice is a fast no-op once the binary exists.
scons "${TARGET}" -j"${JOBS}" "$@"
if [ ! -x "${TARGET}" ]; then
    echo ">> ${TARGET} not linked yet; running final link pass..."
    scons "${TARGET}" -j"${JOBS}"
fi

echo ">> Built ${TARGET}"
ls -lah "${TARGET}"
