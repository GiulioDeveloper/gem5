# doc: Correct EVES residual analysis; restate identity

- **Date:** 2026-08-15 02:55   ·   **Branch:** vp

## Goal
Fix a wrong root-cause attribution in the Task 3 (EVES) commit note
and implementation plan, found in review: the `predictionsCorrect ==
deliveredCorrectByVtage + deliveredCorrectByStride` residual was
attributed to the same `m5_reset_stats()`-at-ROI_BEGIN mechanism as
the inflight-closure residual, but the sign is wrong -- a stats reset
zeroes the EARLIER-site counter and produces a NEGATIVE residual
(exactly what the inflight identity shows, -7/-7/-10), while the
`predictionsCorrect` residual is POSITIVE (+9/+24/+34 on the hostile
runs, and nonzero even on some boot smokes). No C++/Python code
changed; this is a docs-only correction.

## Summary of changes
Identified the true mechanism: `predictionsCorrect` counts at the
verify site; `deliveredCorrectByVtage`/`deliveredCorrectByStride`
count at commit-train, which only runs for instructions that actually
commit. A prediction that verifies correct and is then squashed by an
OLDER redirect (branch/VP/memory-order mispredict) or whose
instruction faults at commit never reaches commit-train, so it is
counted in `predictionsCorrect` but attributed to neither
`deliveredCorrectBy*` bucket -- a term that does not drain at exit
(those instructions never commit, by definition). It is positive
exactly when some verified-correct prediction is squashed or faults
before commit; zero when no such victim occurs -- likely, but not
guaranteed, at negligible squash pressure (a run can squash plenty of
instructions without ever killing a verified-correct prediction).
This exonerates the S6 verify/train routing: mis-routing would move
counts between the two `deliveredCorrectBy*` buckets (preserving the
sum), not shrink it; only never-trained instructions can shrink it.

Extracted `predictionsCorrect`/`deliveredCorrectByVtage`/
`deliveredCorrectByStride`/`predictionsWrong`/`predictionsSquashed`/
`squashedInsts` from the four EXISTING `runs/eves_smoke/*/stats.txt`
boot-smoke files (no re-runs) to substantiate the "boot smokes are
exact" claim, which turned out to be true only for the inflight
identity, not this one:

| run | predictionsCorrect | deliveredCorrectByVtage+ByStride | diff | predictionsWrong | predictionsSquashed | squashedInsts |
|---|---|---|---|---|---|---|
| eves_loads | 49860 | 49857 | 3 | 2 | 16 | 106 |
| eves_all | 52585 | 52118 | 467 | 109 | 1961 | 7140 |
| eves_ablation | 98947 | 98947 | 0 | 2 | 34 | 106 |
| eves_guard128 | 49860 | 49857 | 3 | 2 | 16 | 106 |

Raw squash volume does not, by itself, predict the gap:
eves_ablation's predictionsSquashed=34/squashedInsts=106 is no
smaller than eves_loads's 16/106, yet eves_ablation's diff is 0
against eves_loads's 3 -- consistent with the precise mechanism (a
victim-specific event, not a volume-scaled one): the residual is
positive exactly when some verified-correct prediction is squashed or
faults before commit, zero when no such victim occurs among however
many squashes happened, likely but not guaranteed at negligible
squash pressure. The inflight-closure identity remains
exact (0 diff) on all four boot smokes -- that mechanism (and its
negative sign) is unchanged from the original commit note; only the
`predictionsCorrect` paragraph was wrong.

Corrected `docs/commit-notes/20260815-024230-add-the-eves-value-
predictor.md`'s residual paragraphs to state both mechanisms
separately with their correct signs and the boot-smoke evidence
above. Corrected `docs/superpowers/plans/2026-08-15-estride-eves.md`
Task 3 Step 3 identity item 3 to include the missing
"squashed-or-faulted-before-commit" term and deleted the now-wrong
"allow the in-flight epsilon: recheck equality only at exit
(drained)" caveat (that caveat implied the residual would drain to
zero at exit, which it structurally cannot for a squashed-before-
commit population).

## Files changed
- `docs/commit-notes/20260815-024230-add-the-eves-value-predictor.md`
  — residual root-cause paragraphs corrected (two mechanisms, correct
  signs, boot-smoke numbers added).
- `docs/superpowers/plans/2026-08-15-estride-eves.md` — Task 3 Step 3
  identity item 3 restated with the missing term; wrong epsilon
  caveat deleted.
