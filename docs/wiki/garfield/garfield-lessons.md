---
type: garfield
status: current
updated: 2026-10-21
sources:
  - "[[garfield-overview]]"
  - "[[ghost-execution]]"
  - "[[memory-renaming]]"
  - "[[value-prediction]]"
  - "[[legacy-log/commit-notes/20260717-085026-add-neoverse-v2-fs-checkpoint-restore-script]]"
  - "[[legacy-log/commit-notes/20260717-074256-only-materialize-non-zero-pages-on-restore]]"
  - "[[legacy-log/commit-notes/20260716-180915-implement-feat-dit-msr-mrs-dit]]"
tags: [garfield, lessons, methodology, pitfalls]
---

# What Garfield teaches the current work

The transferable part of [[garfield-overview]], grouped by use. Each item
links to where the agentic work already applies it, or marks it as a
candidate.

## Measuring

- **Single checkpoints mislead; read the suite.** gcc's +9.35% for MRN shrank
  tenfold at 190 checkpoints; a 2M FFT window showed +1.3% that washed out.
  Same in agentic: gin-2121 +3.6% vs median +3.1% for the infinite BTB
  ([[comparing-configurations]]).
- **Per-checkpoint ratios, geomean or median, plus the loser tail.**
  S-curves and the anatomy of the worst checkpoints explained more than the
  mean every time.
- **Probe sets must be balanced** across the suite before promoting to a
  full run (the stockfish-less probe).
- **Coverage is not speedup**, and accuracy alone does not decide winners:
  placement, mispredict volume and schedule criticality do
  ([[value-prediction]]).
- **The benefit may be scheduling, not latency**: MRN's correct forwards were
  97.5% L1-resident ([[memory-renaming]]). Check *which* mechanism a gain
  comes through before explaining it (agentic: BTB gains acting through L1I
  and L2, TLB gains through FDP, [[btb-tlb-limits]]).
- **Exact accounting identities** (e.g. `made = correct + wrong +
  squashed`) catch counter bugs early.
- **Count at the commit site.** Verify-site and speculative-site counters
  include wrong-path work ([[o3-wrong-path-counting]]).
- **Headroom methodology:** gate a limit study on realistic coverage, assume
  predicted = correct, and read the result as a resource-vs-performance
  curve ([[ghost-execution]]). gem5 has no oracles, and two-pass replay
  desyncs once timing changes: relevant to a BTB oracle ([[questions]]).

## Trusting the simulator

- **Prove inert-by-default changes bit-identical** before measuring with
  them; Garfield did it for every feature, the agentic work does it for the
  tracer and the limit models ([[validation-checks]]).
- **Review before running:** five VTAGE defects that would have silently
  corrupted results were caught by review before any checkpoint ran.
- **The ROB-head watchdog** (`commitStallLimit`) turns silent O3 livelocks
  into a diagnosable exit; keep it on ([[simulation-hangs]]).
- **gem5 bugs exist in base code too**: the FDP MaxAddr hang, the never-
  counted `SimpleBTB` evictions, the disconnected L2 TLB in the fork's own
  config ([[simulation-hangs]], [[btb]], [[l2-tlb-disconnected]]).
- **Docs drift from the code**: the Garfield reports state ROB sizes of 512
  and 256 for a config that has always had 320. Read parameters from the
  config, not from reports ([[neoverse-v2]]).

## O3 facts

- Stores enter the SQ `renameToIEWDelay` (2 cycles) after rename.
- A squash takes ~2 cycles to mark its victims; anything that trains or
  counts at verify sees doomed instructions in that window.
- `squashedInsts` overcounts mispredict cost (charges the whole younger
  window).
- Oscillating speculation regimes poison StoreSet training.
- Wrong-prediction cost on this core: ~60–300 flushed instructions per
  wrong, rising with the load's serving level.

## FS restores

- Restore into an **atomic** core primed active (the SPEC checkpoints were
  taken with the atomic switch core active), then switch to O3; both cores
  need `cpu_id=0` (`takeOverFrom` asserts equal cpuIds).
- **Rebind the L1I FDP prefetcher** to the detailed core after the switch,
  or it trains off the atomic core.
- Only the RAM *size* and board/platform must match the checkpoint; CPU,
  caches and DRAM model are free.
- `PhysicalMemory::unserializeStore()` now writes only non-zero chunks: a
  16 GiB restore went from 16.9 GB to 1.2 GB RSS, behaviour-identical.
- KVM-captured guests can use features the simulated CPU lacks: missing
  FEAT_DIT made every SPEC FS+KVM restore storm in the kernel (fixed by
  implementing `MSR/MRS DIT`). The same class of bug produces the "uniform
  IPC" corruption signature ([[restore-silent-failures]]).

See also [[checkpoints]].
