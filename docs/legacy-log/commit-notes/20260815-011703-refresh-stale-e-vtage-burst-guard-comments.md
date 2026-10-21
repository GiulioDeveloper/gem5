# cpu-o3: Refresh stale E-VTAGE burst-guard comments

- **Date:** 2026-08-15 01:17   ·   **Branch:** vp

## Goal
Follow-up to the per-PC in-flight occurrence counter commit
(`92a65e8e50`), which wired `notifyRenamedInst()` into `rename.cc` and
deleted the never-called `notifyRenamed(ThreadID)` it superseded.
Design spec `docs/superpowers/specs/2026-08-14-estride-design.md`, S8
calls for `EVtageVP`'s burst-guard comments/rationale to be refreshed
once that rename feed lands, since their stated reasoning ("no
pipeline stage feeds yet", "never fed by any pipeline call site") is
now false and one of them cross-references the deleted method.

## Summary of changes
Comment-only edits (plus the `fatal_if` message string, which was
part of the same falsehood) in `EVtageVP`'s frozen source: no
algorithm, no params, no control flow. The constructor's rationale
comment and the `fatal_if` message in `evtage.cc` now state the real
situation -- `renamedInsts()` is fed once per renamed instruction via
`notifyRenamedInst()`, but `EVtageVP`'s own burst guard stays locked
off pending re-validation of a nonzero window, with the guard-capable
configuration living in the (not-yet-landed) EVES composition
predictor. `evtage.hh`'s `lastWrongMark` doc comment gets the matching
update and drops its reference to the deleted `notifyRenamed()`. The
`fatal_if` itself is unchanged -- it still fails loudly on any nonzero
`burstGuardWindow` for this predictor.

Covering test: rebuilt `gem5.opt` (links cleanly) and reran
`evtage_tables.test.opt` (54/54 pass, including the two burst-guard
tests). No 5-config bit-identity gate rerun: the diff touches only
comments and the text of a `fatal_if` message that is unreachable at
`burstGuardWindow == 0` (the shipped default everywhere), so it cannot
change any emitted stat.

## Files changed
- `src/cpu/o3/vp/evtage.cc` — reworded the constructor's burst-guard
  rationale comment and the `fatal_if` message string.
- `src/cpu/o3/vp/evtage.hh` — reworded `lastWrongMark`'s doc comment
  to match; dropped the dangling `notifyRenamed()` cross-reference.
