# doc: Scope the EVES correct-residual claim precisely

- **Date:** 2026-08-15 03:03   ·   **Branch:** vp

## Goal
Second review round on the Task 3 (EVES) residual-analysis fix-up
found the round-1 correction itself overclaimed: "structurally
positive whenever the run has any squash pressure ... zero only on a
squash-free run" is falsified by the fix's own `eves_ablation` row
(predictionsSquashed=34, squashedInsts=106 -- not squash-free -- yet
diff=0). No C++/Python code changed; this is a docs-only precision
fix.

## Summary of changes
Replaced the overclaimed "any squash pressure" / "squash-free"
wording, in every place it appeared, with the mechanism-scoped
statement: the `predictionsCorrect == deliveredCorrectByVtage +
deliveredCorrectByStride` residual is positive **exactly when some
verified-correct prediction is squashed or faults before commit**,
and zero when no such victim occurs among however many squashes
happened -- likely, but not guaranteed, at negligible squash
pressure. A run can squash plenty of instructions without ever
killing a *verified-correct* one; `eves_ablation`'s own numbers (more
`predictionsSquashed` than `eves_loads`, yet a smaller/zero gap) are
the direct counterexample to the volume-scaled framing this replaces.
This does not change the underlying mechanism identified in the
previous fix-up (still the verify-site-vs-commit-site population
split for verified-correct-but-never-committed predictions) or any
of the numbers -- only the imprecise summary sentence describing when
the residual is zero vs. nonzero.

Aligned the wording identically across all three docs that stated it:
the original commit note, the implementation plan's identity item 3,
and the prior fix-up's own commit note (which had a softer but still
imprecise "negligible enough" framing).

## Files changed
- `docs/commit-notes/20260815-024230-add-the-eves-value-predictor.md`
  — residual paragraph's summary sentence replaced with the precise,
  victim-scoped wording.
- `docs/superpowers/plans/2026-08-15-estride-eves.md` — Task 3 Step 3
  identity item 3's closing sentence replaced likewise.
- `docs/commit-notes/20260815-025546-correct-eves-residual-analysis-restate-id.md`
  — its own summary/table-commentary sentences aligned to the same
  precise wording.
