# ext: Stop system GoogleTest shadowing the bundled one

- **Date:** 2026-06-28 09:49   ·   **Branch:** rbdev

## Goal
Make gem5's GoogleTest unit tests buildable in this host's Anaconda
environment. They had never built here: the bundled GoogleTest was being
shadowed by an old GoogleTest that Anaconda ships under
`~/anaconda3/include/gtest/`, which lands on the include path via Anaconda's
protobuf/grpc `pkg-config --cflags`. The clash produced redefinition and
missing-macro errors (e.g. `GTEST_FLAG_GET`) in `gtest-all.cc`.

## Summary of changes
Root cause (traced with `g++ -H`): the bundled gtest/gmock include dirs were
passed as **both** `-I` (via CPPPATH) and `-isystem` (in the gtest build flags).
GCC's de-duplication rule then ignores the `-I` and searches the directory only
at its system-include position — behind Anaconda's `-I`, so Anaconda's stale
copy won the `#include "gtest/gtest.h"` lookup. Fix: prepend the bundled
includes to CPPPATH (so their `-I` is first) and drop the now-harmful `-isystem`
duplicates, so the bundled headers are found before any other GoogleTest on the
path. With this, the GTest targets compile and run.

## Files changed
- `ext/googletest/SConscript` — prepend bundled gtest/gmock includes to CPPPATH;
  remove the duplicate `-isystem` entries from the gtest compile flags (`genv`)
  and from `GTEST_CPPFLAGS`, with comments explaining the `-I`/`-isystem` dedup
  pitfall.
