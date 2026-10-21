---
type: method
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
tags: [methodology, warmup]
---

# Warm-up length and skipping the start of a window

**Current practice:** 20M O3 warm-up instructions after the restore is
enough for the **real** structures, but not for unbounded ones (limit
studies). For those, re-summarise with the first 100M of each window
skipped: `sweep_summary.py --skip-insts 100e6 -o <dir>` (no re-simulation;
[[sweeps]]).

Evidence (2026-10-20, [[2026-10-16-btb-tlb-limit-study]]):

- In the first 20M of the window the unbounded structures were still
  filling: infinite-BTB IPC 4% lower than in the rest of the window, with
  1.5× the new entries; infinite-TLB completed walks falling from 0.20 to
  0.10 per 1000 instructions per 100M quarter.
- The baseline barely changed with the skip (IPC 0.991 → 0.997, completed
  walks 0.63 → 0.59).
- Single limits barely moved (BTB +3.1 → +3.0%, TLB +3.1 → +3.3%); the
  combination grew (+6.4 → +7.5%).
- The checkpoints restore with **cold** caches, TLBs and predictors
  (TLBs start empty: a 25M window is dominated by compulsory walks,
  [[infinite-l2-tlb]]).

Caveats:
- SPEC sweep windows are 200M, so a 100M skip halves them and moves their
  absolute values for reasons of region (second half of a SimPoint), not
  warmth.
- Garfield used 10M warm-up + 50M measured on SPEC; numbers from the two
  setups are not directly comparable ([[garfield-lessons]]).
