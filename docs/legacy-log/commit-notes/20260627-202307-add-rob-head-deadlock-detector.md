# cpu-o3,stdlib: Add ROB-head deadlock detector

- **Date:** 2026-06-27 20:23   ·   **Branch:** rbdev

## Goal
Catch the class of bug where an instruction can never issue (e.g. a missing
functional unit for its op class) and the O3 pipeline livelocks silently — turn a
silent hang into a clean, diagnosable exit.

## Summary of changes
Add a per-thread no-forward-progress check to the O3 Commit stage: if the
committed instruction stream (`lastCommitedSeqNum`) does not advance for
`commitStallLimit` cycles and the ROB is non-empty, dump the blocking ROB-head
instruction (identity, status flags, per-stage ticks, heuristic cause hint) and
stop the run via `exitSimLoopNow` instead of hanging. New `BaseO3CPU` param
`commitStallLimit` (Cycles, default 1000000, 0 disables). The empty-ROB
(front-end starvation) case routes to a documented stub for a fast-follow. The
deadlock exit cause is mapped to `ExitEvent.EXIT` so the Simulator returns cleanly.

## Files changed
- `src/cpu/o3/commit.cc` — committed-progress-frozen detection, ROB-head dump, and
  clean exit via `exitSimLoopNow`.
- `src/cpu/o3/commit.hh` — detector state and declarations.
- `src/cpu/o3/BaseO3CPU.py` — new `commitStallLimit` param (Cycles, default
  1000000, 0 disables).
- `src/python/gem5/simulate/exit_event.py` — map the deadlock exit cause to
  `ExitEvent.EXIT`.
