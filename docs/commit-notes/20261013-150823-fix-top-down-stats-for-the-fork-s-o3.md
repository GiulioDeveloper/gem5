# cpu-o3: Fix top-down stats for the fork's O3

- **Date:** 2026-10-13 15:08   ·   **Branch:** topdown-pr2392

## Goal
Make the imported top-down accounting (PR #2392) build and produce valid
fractions on this fork's O3 core.

## Summary of changes
- The fork splits the issue queue into units with one FU pool each; the
  top-down counters now sum busy FUs over all pools and treat the FUs as
  drained only when every pool is.
- `tdaCycles`, the denominator of every top-down fraction, is registered
  as a stat and incremented every active cycle (upstream only added idle
  cycles, giving fractions in the hundreds).
- Restores the `instcount` assert the PR commented out.
- Checked on 729.abc_r (1M warmup + 5M detailed): IPC and all
  non-top-down stats identical to gfdev; Level 1 sums to 1.

## Files changed
- `src/cpu/o3/cpu.cc` — registers tdaCycles; increments it in tick()
- `src/cpu/o3/cpu.hh` — tdaCycles declared after quiesceCycles (init order)
- `src/cpu/o3/dyn_inst.cc` — instcount assert restored
- `src/cpu/o3/inst_queue.cc` — busy/drained FU counts across all IQ units' pools
- `src/cpu/o3/rename.cc` — store-stall check across all FU pools
