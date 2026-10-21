# scons: Disable HDF5 to avoid Anaconda libhdf5_cpp link clash

- **Date:** 2026-06-27 12:20   ·   **Branch:** rbdev

## Goal
Make gem5 link under the Anaconda toolchain. Anaconda puts `~/anaconda3/lib`
on the link line (for the embedded libpython), and its `libhdf5_cpp` shadows the
system HDF5 that `hdf5.cc` was compiled against, causing undefined-symbol link
errors. HDF5 is an optional stats-output format we don't use.

## Summary of changes
Disable HDF5 by default in the stats build options, and gate re-enabling it
behind `GEM5_ENABLE_HDF5=1` for hosts with a consistent HDF5 install.

## Files changed
- `src/base/stats/SConsopts` — default HDF5 off; `GEM5_ENABLE_HDF5=1` restores
  the previous auto-detection behavior.
