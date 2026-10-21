# cpu-o3: Clarify E-Stride classifier and test comments

- **Date:** 2026-08-15 15:20   ·   **Branch:** vp

## Goal
Discharge the final whole-branch review's comment findings: two
note-to-self comments transcribed from planning material, and a
classifier comment that justified the non-load MFASTINST mapping by
appeal to the E-VTAGE flag the sibling header explicitly warns
diverges in meaning.

## Summary of changes
Comment-only. eves.cc's non-load fastInst comment now derives the
mapping in MFASTINST's own terms (every non-load class except the
multi-cycle SlowAlu group executes in under 3 cycles) and points at
EStrideClassifier's divergence warning. estride_table.test.cc's two
stream-of-consciousness comments are restated as facts (the Never
allocation class refuses deterministically with zero RNG draws; the
first miss consumes the exponent-0 allocation draw plus the way draw).

## Files changed
- `src/cpu/o3/vp/eves.cc` — non-load MFASTINST comment reworded.
- `src/cpu/o3/vp/estride_table.test.cc` — two comment restatements.
