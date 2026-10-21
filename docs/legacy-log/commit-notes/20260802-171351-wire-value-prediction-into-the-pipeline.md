# cpu-o3,configs: Wire value prediction into the pipeline

- **Date:** 2026-08-02 17:20   ·   **Branch:** vp

## Goal
Make VP live end-to-end: predict at rename behind the MRN -> VP ->
execute priority ladder, verify at writeback (LSQ for loads, IEW for
non-loads), inclusive squash on wrong, train every in-scope
instruction, squashed-before-verify accounting, and the --use-vp CLI.

## Summary of changes
Rename consumes predictions with MRN's physreg-write + scoreboard-ready
mechanism, guarded !isMrned(). LSQ and IEW verify sites follow MRN's
resolve-before-squash discipline with the squash trigger last; train
runs unconditionally for in-scope instructions (including MRN-claimed
loads). ROB::doSquash and CPU::squashInstIt do exactly-once
notifySquashed via VpResolved. sim_opts gains --use-vp <type> plus the
vp-* knobs, factory, attach, banner.

Review campaign on this task (3 lenses + forensics + fix + re-review)
found and fixed a real in-contract bug: during the 2-cycle window
between a squash signal and victim flag-marking, doomed instructions
verified and trained wrong-path values -- at threshold 0 this closed a
squash/refetch livelock (ROB-head watchdog); at any threshold it
polluted accuracy (all "correct" verifies in the hostile repro were
doomed). Fixes: per-thread pending-squash doomed-window guard in IEW
gating only the VP verify/train sites (MRN accounting untouched; clear
condition documented with its two configuration-level guarantors);
fatal_if(confThreshold == 0); decrement mode now clamps confidence
below threshold on a mismatch, making the documented no-livelock
invariant true by construction (spec amended accordingly).

Validation: full build; 15/15 + 20/20 GTests; 7-run smoke matrix --
baseline inert (no valuePred group), loads-only and all-insts
identities exact, MRN+VP ladder co-existence (MRN claims all loads, VP
still trains), hostile threshold-1 runs complete without deadlock with
bit-exact outputs (vpalu m=3 checksum == closed form
9518916028417131577; branchsort checksum 576402600 == baseline under
440k wrong verifies / 6.1M flushed insts, identity exact to the unit).

## Files changed
- `src/cpu/o3/rename.{hh,cc}` — valuePred member; VP consume site
  behind the priority ladder.
- `src/cpu/o3/iew.{hh,cc}` — valuePred member + accessor; non-load
  verify/train site in writebackInsts; doomed-window mark (set in
  squashInclusive/squashDueToBranch, clear on covering commit ack).
- `src/cpu/o3/lsq_unit.cc` — load verify/train site after the MRN
  verify block.
- `src/cpu/o3/rob.cc`, `src/cpu/o3/cpu.{hh,cc}` — squashed-before-
  verify accounting walks; CPU::getValuePred.
- `src/cpu/o3/vp/base.cc` — squashedInsts description documents the
  verify-time flush attribution convention.
- `src/cpu/o3/vp/lvp_table.{hh,cc}`, `lvp_table.test.cc`,
  `ValuePredictor.py` — threshold-0 fatal; decrement clamp below
  threshold; 15 GTests incl. the clamp pins.
- `configs/garfield/arm/sim_opts.py` — --use-vp TYPE + --vp-* knobs,
  make_vp, apply_core_knobs attach, banner.
- `docs/superpowers/specs/2026-08-02-vp-framework-design.md` — the
  no-livelock paragraph now states the enforced invariant.
