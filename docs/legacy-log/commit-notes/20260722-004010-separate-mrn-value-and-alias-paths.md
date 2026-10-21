# cpu-o3,configs: Separate MRN value and alias paths

- **Date:** 2026-07-22 00:55   ·   **Branch:** rbdev

## Goal
Make the MRN value-forwarding and producer-aliasing paths independent, each
individually enable/disable-able, with aliasing's trigger no longer borrowed
from the value path's confidence. Structural precondition for giving aliasing
its own confidence counter later.

## Summary of changes
The two paths already owned disjoint data structures; only the rename trigger
and the mrnMode/unified() config coupled them. Two bool params
(enableValueForwarding / enableProducerAliasing) replace the mrnMode enum;
accessors become valueForwardingEnabled() / aliasingEnabled(). rename.cc gates
each path on its own trigger -- value on predict() confidence, aliasing on its
own correlator-binding trigger -- with aliasing-first priority when both
apply. Per-path training is gated too (commitStore/commitLoad value,
trainForward alias), so a disabled path stops maintaining its tables. CLI:
--mrn-mode replaced by --mrn-no-value-forward / --mrn-alias; the banner names
the active paths.

Verified: default (value-only) is byte-identical to the pre-refactor value_only
run in every simulation stat except bindingsLearned (411,623 -> 0; the
correlator is no longer trained when aliasing is off, and it is never read
then, so no timing effect). Independence proven: --mrn-alias
--mrn-no-value-forward gives forwardsValue==0, forwardsAlias>0 -- impossible
before. The 7 MRN unit tests pass. Note: --mrn-alias (both paths) is a NEW
operating point, NOT the old unified (it aliases every binding-hit load, a
superset of unified's value-confident-only loads).

## Files changed
- `src/cpu/o3/MemRenamePredictor.py` — two bool params replace mrnMode/MrnMode; help/comments.
- `src/cpu/o3/SConscript` — drop the removed MrnMode enum from codegen.
- `src/cpu/o3/mem_rename_predictor.hh` — valueForwardingEnabled()/aliasingEnabled() accessors and members; comment fixes.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — init the two bools from params.
- `src/cpu/o3/rename.cc` — decoupled per-path triggers; drop the internal unified() check.
- `src/cpu/o3/rename.hh` — rewrite the stale tryMemRenameAlias doc-comment.
- `src/cpu/o3/iew.cc` — producer-writeback verify gated on aliasingEnabled().
- `src/cpu/o3/lsq_unit.cc` — gate commitStore (value) and trainForward (alias).
- `src/cpu/o3/commit.cc` — gate commitLoad (value) on valueForwardingEnabled().
- `configs/garfield/arm/sim_opts.py` — --mrn-no-value-forward / --mrn-alias flags; make_mrn; path-naming banner.
- `docs/superpowers/specs/2026-07-21-mrn-path-separation-design.md` — spec; verification #3 corrected.
- `docs/garfield/mrn-ideas.md` — 1b structural separation done; confidence counter deferred.
- `.claude/skills/precommit-review/SKILL.md` — catch parenthesized mode-letter naming.
