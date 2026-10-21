# doc: Add VTAGE design spec

- **Date:** 2026-08-03 14:30   ·   **Branch:** vp

## Goal
The second predictor on the VP framework: VTAGE (Perais & Seznec,
HPCA-20 2014), targeting the LVP campaign's volume-loser population
with history-correlated prediction and FPC confidence.

## Summary of changes
Design spec with the four ratified forks (VP-private speculative
GHR+path with per-inst snapshots; per-predictor trainAtCommit;
HPCA'14 configuration; plain VTAGE first). The load-bearing outcome
of the three-lens adversarial spec review: commit-only training
composed with our writeback-verify inclusive squash would leave
delivered-wrong predictions permanently untrained (deterministic
same-PC livelock -- the paper validates at commit where the wrong
instruction retires; ours never does). Resolved with a verify-site
corrective reset through a provider token (c=0/u=0 only, tag-checked;
value overwrite + allocation deferred to the refetched instance's
committed train). Also from review: the complete per-initiator
history-restore table (incl. decode squashes and squash-after
advance-past-self), token stamped on every lookup with a biased-rank
encoding, hostile smoke at confThreshold 1 instead of a degenerate
FPC vector, Stage-IV in both scopes, and the coverage-denominator
caveat for trainAtCommit mode.

## Files changed
- `docs/superpowers/specs/2026-08-03-vtage-design.md` — the spec
  (new).
