# scons: Embed Python lib dir as rpath in gem5 binaries

- **Date:** 2026-06-27 12:21   ·   **Branch:** rbdev

## Goal
Let the embedded libpython (and, under a conda prefix, the co-located
libprotobuf/abseil) resolve at run time without `LD_LIBRARY_PATH`. This is needed
for Slurm batch jobs, which do not source `~/.bashrc`.

## Summary of changes
`config_embedded_python()` now adds a `-Wl,-rpath` entry for each `-L` directory
reported by `python-config`. The rpath is computed at build time, so it is correct
wherever gem5 is rebuilt.

## Files changed
- `SConstruct` — `config_embedded_python()` emits an rpath entry per
  `python-config` `-L` directory.
