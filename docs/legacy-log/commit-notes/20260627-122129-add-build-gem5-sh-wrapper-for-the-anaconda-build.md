# scons: Add build-gem5.sh wrapper for the Anaconda build env

- **Date:** 2026-06-27 12:21   ·   **Branch:** rbdev

## Goal
Make the Anaconda-based build reproducible on this host and on the cluster by
pinning gem5's toolchain consistently, so a bare `scons` no longer fails on the
Anaconda/system library clash.

## Summary of changes
New wrapper script that pins protoc/protobuf (`PKG_CONFIG_PATH`/`PROTOC`) and
libpython (`LD_LIBRARY_PATH`), exposes overridable `ANACONDA`, `JOBS`, and build
target, and handles the post-`--config=force` two-pass link quirk.

## Files changed
- `build-gem5.sh` — new build wrapper for the Anaconda environment (toolchain
  pinning + two-pass link handling).
