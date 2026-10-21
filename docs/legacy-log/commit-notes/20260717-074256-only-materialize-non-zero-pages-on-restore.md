# mem: Only materialize non-zero pages on restore

- **Date:** 2026-07-17 07:42   ·   **Branch:** rbdev

## Goal
Make a checkpoint restore's memory footprint proportional to what the guest
actually used, instead of to `mem_size`. Previously a restore's RSS equalled the
full `mem_size` (a 16GiB checkpoint cost ~16.9 GB RSS even though the SPEC guest
never touched more than 2.32 GiB), which capped how many restores fit in RAM and
inflated the memory every cluster job had to request.

## Summary of changes
`PhysicalMemory::unserializeStore()` decompressed the checkpoint straight into
the backing store, writing every byte of the range -- including the vast
all-zero regions -- so every page was faulted in. The backing store is a fresh
mapping that already reads as zero (MAP_ANON|MAP_PRIVATE, or a freshly
ftruncate'd shm), so those writes were pure cost.

Now the data is inflated into a staging buffer and only chunks that actually
carry data are written. All-zero chunks are dropped with MADV_DONTNEED on the
anonymous mapping (restoring zero-fill-on-demand), with unaligned edges zeroed
explicitly; the shared-backstore path still memsets, since MADV_DONTNEED there
would re-read the file rather than guarantee zero.

Verified behaviour-neutral: restoring the same checkpoint with and without this
change produces an identical simulation (IPC 0.784972, 25723680 cycles), while
peak RSS drops 16.86 GB -> 1.23 GB (13.7x) for 710.omnetpp_r, and ~1.05 GB for a
light checkpoint.

## Files changed
- `src/mem/physical.cc` — sparse restore in unserializeStore(): stage each inflated chunk, memcpy only non-zero chunks, MADV_DONTNEED all-zero page ranges (memset unaligned edges / shared backstore); add <algorithm>, <cstring>, <vector> includes.
