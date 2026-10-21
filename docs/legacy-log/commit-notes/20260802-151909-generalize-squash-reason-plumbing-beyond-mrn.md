# cpu-o3: Generalize squash-reason plumbing beyond MRN

- **Date:** 2026-08-02 15:35   ·   **Branch:** vp

## Goal
Prepare the shared squash-attribution plumbing for Value Prediction:
the reason enum had outgrown its MRN-era name (it already carried
Branch/MemOrder/Other), and VP mispredicts need their own inclusive
squash entry point that never calls a MemOrder-named function.

## Summary of changes
Pure mechanical generalization, zero behavior change (verified by a
two-lens review: hunk classification + adversarial behavior
preservation). MrnSquashReason -> SquashReason (header renamed to
squash_reason.hh), names array -> squashReasonNames, IEWStruct wire
field -> squashReason, ROB accessors/member renamed to match. New
ValuePred enumerator (+ "valuePred" stat subname; the reason-indexed
MRN squash stats gain a structurally-zero bucket). IEW's inclusive
squash body extracted into a private squashInclusive helper;
squashDueToMemOrder stays as a thin wrapper for its existing callers,
and the new public squashDueToValueMispredict wraps the same body with
reason ValuePred for the VP verify sites arriving in the integration
task. Both GTest suites pass (14/14, 20/20); full ALL build links.

## Files changed
- `src/cpu/o3/squash_reason.hh` — renamed from mrn_squash_reason.hh;
  SquashReason + ValuePred + squashReasonNames.
- `src/cpu/o3/iew.{hh,cc}` — squashInclusive extraction + the two thin
  wrappers; declarations and comments updated.
- `src/cpu/o3/comm.hh` — IEWStruct::squashReason field rename.
- `src/cpu/o3/commit.cc` — field/accessor renames; initiator comment
  now mentions VP.
- `src/cpu/o3/rob.{hh,cc}` — setSquashReason/getSquashReason/member
  renames.
- `src/cpu/o3/cpu.cc`, `src/cpu/o3/lsq_unit.cc`,
  `src/cpu/o3/mem_rename_predictor.{hh,_sim.cc}` — call-site and
  include renames (mem_rename_predictor_sim.cc: stats subname loop
  now reads squashReasonNames).
