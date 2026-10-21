# mem-cache: Fix FDP infinite loop on last-block fetch targets

- **Date:** 2026-08-04 07:00   ·   **Branch:** vp

## Goal
Fix a base-branch simulator hang: FetchDirectedPrefetcher's
per-fetch-target block walk never terminates when the target ends in
the last cache block of the address space, freezing the whole event
loop inside a single tick (no events fire, simulated time stops).

## Summary of changes
notifyFTQInsert iterated with an address compare
(blk_addr <= end_blk_addr; blk_addr += blkSize); when end_blk_addr is
the final 64-byte block the condition is a tautology (increment wraps
past MaxAddr to 0) and CPU::tick never returns. Reached in practice
under --use-vp evtage --vp-all-insts on 722.palm_r.0.2: an indirect
branch executing with a wrong-but-confident predicted source in the
pre-verify window redirects BAC to a small negative garbage PC, whose
64-byte fetch-target finalization lands in the last block. The
existing wrapped-target guard (fetch consume time) cannot help: the
FDP probe fires at FTQ insert time. Fix: iterate by block count; the
sequence is byte-for-byte identical for every legitimate target,
visits at most the nominal span for the last-block shape, and zero
blocks for wrapped targets. Verified: palm evtage_all now completes
(IPC 2.115, ~5 min; formerly 2x 90-min timeouts + 3 local repros);
value-identity PASS on a completed sweep run (707.ntest_r.0.3
evtage_all re-run under the fixed binary, stats value-identical) --
completed sweep results never executed the changed path (any run that
did hung with no stats), so no re-runs needed. Root-cause forensics
via live-gdb state capture: frozen curTick bit-identical across
independent sessions; the ROB-head load's DRAM respondEvent scheduled
but starved forever.

## Files changed
- `src/mem/cache/prefetch/fdp.cc` — count-bounded block walk in
  notifyFTQInsert with the wrap-tautology rationale in a comment.
