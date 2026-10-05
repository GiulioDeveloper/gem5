# misc: Apply the style checks to the perf-opt changes

- **Date:** 2026-10-05 13:26   ·   **Branch:** feat/opt

## Goal
Make this branch's own changes pass the two CI style jobs (clang-format-check
and pre-commit), which were failing on PR #1 and causing every test job to
be skipped.

## Summary of changes
- clang-format applied to the lines this branch changed in 21 C++ files.
  Besides whitespace it swapped two includes into alphabetical order
  (arch/arm/pcstate.hh) and added braces around three single-statement if
  bodies (base/refcnt.hh, cpu/pred/simple_btb.cc). Stats stay bit-identical
  on all five perf-opt test checkpoints.
- util/perf-opt: black on the Python tools and tests; clang-format's JSON
  layout for suite.json (content unchanged).
- Trailing whitespace removed from the perf-opt log.
- .pre-commit-config.yaml: exclude docs/perf-opt/patches/. Those are verbatim
  patches; the end-of-file fixer corrupted one whose last hunk ends in a
  blank context line.

## Files changed
- `src/arch/arm/pagetable.hh`, `pcstate.hh`, `tlb.cc` — formatting; include order in pcstate.hh.
- `src/base/pooled_new.hh`, `refcnt.hh`, `cache/associative_cache.hh` — formatting; braces in refcnt.hh.
- `src/cpu/base.hh`, `base.cc` — formatting.
- `src/cpu/o3/bac.cc`, `lsq.hh`, `lsq.cc`, `rename.cc` — formatting.
- `src/cpu/pred/btb.hh`, `btb_entry.hh`, `loop_predictor.hh`, `simple_btb.cc` — formatting; braces in simple_btb.cc.
- `src/mem/cache/tags/base.cc`, `tagged_entry.hh`, `indexing_policies/{base.hh,set_associative.hh,set_associative.cc}` — formatting.
- `util/perf-opt/*.py`, `suite.json` — black and JSON layout.
- `docs/perf-opt/performance-opt-log.md` — trailing whitespace.
- `.pre-commit-config.yaml` — exclude docs/perf-opt/patches/.
