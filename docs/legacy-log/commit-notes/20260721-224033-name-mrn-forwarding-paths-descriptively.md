# cpu-o3: Name MRN forwarding paths descriptively

- **Date:** 2026-07-21 22:40   ·   **Branch:** rbdev

## Goal
The MRN code carried conversational labels ("mode B", "mode C", "C.1",
"Stage 1/2") that were shorthand from design discussions and carry no
microarchitectural meaning to a reader who was not in those conversations.
Replace them with terms that describe what the mechanism does.

## Summary of changes
Comment / doc-string / param-help edits only across src/cpu/o3 and
configs/garfield -- no behaviour change, build and the 7 MRN unit tests
unaffected. Mapping:

- "mode B" -> value forwarding / the value path / the value snapshot
- "mode C" -> producer aliasing / the alias path (recurring code-comment
  labels shortened to "aliasing" to stay within the 79-col limit)
- "C.1" / "C.1 lsq_forward" -> the LSQ-forward correlator
- "Garfield Stage 2" -> Garfield MRN
- "Garfield Stage 1" (ghost work) -> ghost execution / the initial policy

The mrnMode enum values `value_only` / `unified` are left unchanged -- they
are shipped API spellings; their explanatory comments were reworded to drop
the mode letters.

## Files changed
- `src/cpu/o3/mem_rename_predictor.hh` — core doc-comments: value forwarding / producer aliasing / LSQ-forward correlator, stat descriptions.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — squashed-forward stat descriptions.
- `src/cpu/o3/MemRenamePredictor.py` — param help text and enum-explanation comments.
- `src/cpu/o3/rename.cc`, `rename.hh` — value-forwarding vs producer-aliasing rename comments.
- `src/cpu/o3/lsq_unit.cc`, `lsq_unit.hh`, `lsq.hh` — alias-verify / correlator comments.
- `src/cpu/o3/dyn_inst.hh` — MRN field comments (snapshot, alias producer, stale-diagnostic).
- `src/cpu/o3/commit.cc`, `iew.cc`, `iew.hh` — aliasing rename/writeback comments.
- `src/cpu/o3/mrn_squash_reason.hh` — squash-reason enum comments.
- `src/cpu/o3/ghost_policy.hh` — ghost-policy stage wording.
- `configs/garfield/arm/sim_opts.py` — `--mrn-*` help text.
