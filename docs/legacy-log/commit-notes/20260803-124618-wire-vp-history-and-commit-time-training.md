# cpu-o3: Wire VP history and commit-time training

- **Date:** 2026-08-03 21:20   ·   **Branch:** vp

## Goal
VTAGE Task 3: the pipeline plumbing for history-indexed, commit-
trained predictors -- speculative history stamp/update/restore, the
commit-time train hook, and the verify-site corrective reset. All of
it dynamically dead until a usesHistory() predictor attaches (next
commit); LVP value-identity and baseline inertness proven.

## Summary of changes
Every DynInst is stamped with the VP history snapshot at
Fetch::buildInst (covering the ifetch-fault noop path -- review
found the unstamped noop would zero the whole history on every FS
page-fault trap); BAC::updatePC advances the per-thread GHR/path for
conditional directions and taken targets. Restores follow the spec's
per-initiator table via a dedicated VP-only commit->fetch carrier
{valid, snapshot, kind} on the wire -- review round: the original
findInst(seq-1) reconstruction silently skipped the inclusive-squash
restore in the dominant case (victim at ROB head) and setting
squashInst leaked into baseline macroop-continuation semantics; the
carrier fixes both, with the victim's own still-ROB-resident snapshot
for inclusive squashes, actual-outcome advance for squash-after, the
decode taken-bit corrected for BTB-missed unconditional branches, and
a 'missed' subname counting the residual null-carrier cases (empty-
ROB TC squashes). Commit::commitHead trains retiring in-scope
instructions when trainsAtCommit(); the two writeback verify sites
skip train() in that mode and fire correctiveReset(token) before the
squash trigger (LVP's proven ordering). Gating bools cached per stage
ctor (one bool test per instruction when off). Stats: historyRestores
by initiator (+missed), correctiveResetStale.

## Files changed
- `src/cpu/o3/fetch.{hh,cc}` — buildInst stamping; the per-initiator
  restore helper consuming the carrier; decode-restore taken-bit fix.
- `src/cpu/o3/bac.{hh,cc}` — notifyControlFlow updates at updatePC;
  cached vpUsesHistory.
- `src/cpu/o3/comm.hh` — VP-only history-restore carrier fields.
- `src/cpu/o3/commit.{hh,cc}` — carrier population per squash kind;
  commitHead train hook; cached bools; valuePred member.
- `src/cpu/o3/iew.cc`, `src/cpu/o3/lsq_unit.cc` — train-site gating +
  verify-site correctiveReset before the squash trigger.
- `src/cpu/o3/vp/base.{hh,cc}` — historyRestores/correctiveResetStale
  stats; correctiveResetImpl wrapper; restore/notify entry points.
- `src/cpu/o3/vp/vp_history.hh` — snapshot-advance helper.
