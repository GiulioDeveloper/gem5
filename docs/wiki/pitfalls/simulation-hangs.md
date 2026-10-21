---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/commit-notes/20260627-202307-add-rob-head-deadlock-detector]]"
  - "[[legacy-log/commit-notes/20260804-064438-fix-fdp-infinite-loop-on-last-block-fetch-target]]"
  - "[[raw/external/2026-10-21-agentic-checkpoints-README]]"
tags: [o3, hang, livelock, fdp, watchdog]
---

# Silent hangs and livelocks, and the guards against them

**The trap:** a gem5 O3 run can stop making progress without erroring: an
instruction that can never issue, a squash/refetch loop, or an event loop
stuck inside one tick. Without a guard it just runs slowly forever.

## Guards on this fork

- **ROB-head watchdog** (`BaseO3CPU.commitStallLimit`, default 1,000,000
  cycles, 0 disables; `src/cpu/o3/commit.cc`): if committed progress does not
  advance for that long with a non-empty ROB, it dumps the blocking ROB-head
  instruction (identity, status flags, per-stage ticks, a cause hint) and
  exits cleanly (`ExitEvent.EXIT`). Added on Garfield day one for a missing
  functional unit; it later caught the VP doomed-window livelock
  ([[o3-wrong-path-counting]]). The empty-ROB (front-end starvation) case is
  not covered.
- **`--progress-interval 10kHz`** on every restore: a heartbeat with IPC
  and KIPS, so a stalled or crawling run is visible.

## Fixed hang: FDP block walk past MaxAddr (2026-08-04)

`FetchDirectedPrefetcher::notifyFTQInsert` walked a fetch target's cache
blocks with `blk_addr <= end_blk_addr; blk_addr += blkSize`. When the target
ended in the last 64-byte block of the address space, the increment wrapped
to 0, the loop never ended, and `CPU::tick` never returned: simulated time
froze inside one tick. Reached when a confidently wrong value prediction
sent BAC to a garbage negative PC. Fix (`src/mem/cache/prefetch/fdp.cc`):
iterate by block count. Behaviour is identical for every legitimate target.
Diagnosed with live gdb (frozen `curTick` identical across sessions).

## Lesson

When a run hangs, check whether simulated time still advances (progress
line) before suspecting the workload; a frozen tick means an infinite loop
inside an event, a moving tick with no commits means a livelock the
watchdog will report.
