# VTAGE on the Garfield VP Framework: Design

- **Date:** 2026-08-03 · **Branch:** `vp` · **Status:** design forks
  ratified in review; spec revised after a three-lens adversarial
  review (the train-site/verify-site reconciliation in §Train is the
  load-bearing outcome of that review)
- **Normative paper digests:** `.superpowers/sdd/vtage-paper-brief.md`
  (Perais & Seznec, RR-8155 2012 + HPCA-20 2014) and
  `.superpowers/sdd/eves-paper-brief.md` (Seznec, CVP-1 2018)
- **Framework spec:** `docs/superpowers/specs/2026-08-02-vp-framework-design.md`
  — everything not stated here (eligibility, consume, verify, squash,
  doomed-window guard, base stats) is inherited unchanged

## Goal and Context

The LVP campaign (research log `docs/research-log/VP/`) showed that
loads-only last-value prediction matches MRN's finalized gain (geomean
1.0093/190) and that losers — in both scopes — are separated from
winners only by mispredict *volume*: values that repeat long enough to
reach confidence, then change. VTAGE [HPCA'14] targets exactly that
population: it indexes values by PC *and* global branch/path history,
so values that change in correlation with control flow become
predictable instead of merely suppressed, and its FPC confidence holds
accuracy above 99.7% by construction.

VTAGE's decisive property: **no speculative predictor state beyond one
small history register pair.** Indices depend only on PC and branch
history — never on previous values — so back-to-back same-PC instances
predict trivially (the tight-loop case that kills stride/FCM), tables
are written only from committed-path events, and squash recovery
reduces to restoring two registers.

## Fork Decisions (Ratified 2026-08-02)

1. **History source: VP-private speculative GHR + path register**,
   maintained by fetch-side notifications, snapshotted onto every
   DynInst, restored on every fetch redirect (full rules below).
2. **Train site: per-predictor `trainAtCommit` knob**, with one
   verify-site exception that carries the no-livelock invariant
   (§Train — this is the review's critical finding). LVP keeps
   writeback training; published Stage-IV numbers stay reproducible.
3. **Configuration: HPCA'14 baseline** (table below; deviations and
   project choices footnoted there).
4. **Scope: plain VTAGE first.** EVES per-class rates later; E-Stride,
   HAL alternate-component substitution, selective reissue out of
   scope.

**Declared placement deviation from HPCA'14:** the paper predicts at
Fetch (value needed before Dispatch) and validates at commit; we
predict at rename (framework-inherited) using the *fetch-time* history
snapshot — equivalent index inputs — and validate at writeback with
the framework's inclusive squash, strictly earlier than the paper's
commit-time squash, so the squash-recovery FPC vector remains the
conservative choice.

## Data Structures

- **Base component VT0** — tagless, PC-indexed, 8192 entries. Entry
  `{val (64b), c (3b)}`.
- **Tagged components VT1..VT6** — 1024 entries each. Entry
  `{val (64b), c (3b), tag (12+rank b, rank 1..6), u (1b)}`. History
  lengths **L = {2, 4, 8, 16, 32, 64}**.
- **Confidence** `c`: prediction requires `c >= confThreshold`
  (default 7 = saturation, per the paper); `c++` on correct
  (FPC-gated); `c = 0` on wrong — unconditional, never probabilistic.
- **Usefulness** `u`: 1 bit, `u = correct` on provider update (VTAGE's
  simplification; not ITTAGE's `correct && alt != pred`).
- **History state (the only speculative state):** per-thread
  `{ghr (64b), path (16b)}` in the framework's history subsystem.
  Max history length 64 ⇒ per-component folded registers are
  unnecessary: **fold on demand from the snapshot** — exact and
  stateless (equivalent to TAGE incremental folding for histories
  ≤ the snapshot width). Fold/index/tag arithmetic mirrors gem5's
  TAGE (`FoldedHistory`, `gindex`/`gtag`, the `F()` path hash).
- **Per-instruction state (framework-level):** the existing
  `VpPredicted`/`VpResolved`/`_vpPredVal`; new: a history snapshot
  `{ghr, path}` stamped at fetch, and an opaque 64-bit **provider
  token** stamped by the base class on *every* predict() lookup —
  including below-confidence lookups where no value is returned.
  Token encoding is implementation-internal within the opaque 64 bits;
  the rank field is biased so the all-zero word is never a legal token
  (0 = none, 1 = VT0, 2..7 = VT1..VT6), and construction-time asserts
  check the configured geometry fits the packing (an implementation
  safeguard beyond the papers, which carry the fetch-time provider
  identity implicitly).

## Algorithms

### Predict (rename, via the framework's predict())

1. Build per-component indices/tags by folding the µop-distinguished
   PC — `(((pc XOR (upc << 48)) >> 2) << 2) | (upc & 3)` — with
   `snapshot.ghr[0:L(i)]` and `snapshot.path` (TAGE-style folds,
   computed on demand). The µop residue is **concatenated** into the
   two low bits the `>> 2` vacated, leaving the PC-delta bits
   untouched: the high-bit fold alone never reaches VTAGE's ≤18-bit
   hashed tags/indices, so without the low-bit residue cracked
   micro-ops would collide in every component, and any XOR of the raw
   upc into the PC-delta bits instead recreates that full-table alias
   at a power-of-two PC distance (an XOR of upc = 1 at bit k of the
   shifted PC merges (pc, µop 1) with (pc ± 2^(k+2), µop 0) in every
   component's index and tag). (LVP's `vpKey` is unaffected: its
   full-width tags see the high bits.)
2. Longest-history tag hit = provider; no tagged hit → VT0.
3. Stamp the provider token on the instruction **unconditionally**;
   deliver the value only if provider `c >= confThreshold`. All
   predict-path instructions therefore train their predict-time
   provider (paper-faithful), whether or not a value was delivered.

### Verify (writeback — the no-livelock exception)

A delivered-and-wrong prediction squashes inclusively at writeback and
**never retires**, so a commit-only trainer would never correct its
entry — the refetched instance would re-predict the same wrong value
forever. Therefore, in `trainAtCommit` mode the verify-wrong path
still performs an immediate **corrective reset through the token**:
`c = 0`, `u = 0`, tag-checked so a reallocated entry is not hijacked.
Nothing else happens at the verify site: no value overwrite, no
allocation (a delivered-wrong instruction can itself be wrong-path
under an in-flight older mispredict, and a bare confidence reset is
the only table write that can never create a prediction). This is the
same train-before-squash ordering LVP proved; the corrective reset is
the last table write before the refetched instance re-renames, and at
`c = 0 < confThreshold (>= 1)` it is not re-predicted.

**Declared deviation:** relative to the paper's commit-time
validation, the value-overwrite and the mispredict-driven allocation
are deferred by one dynamic instance — the refetched instance's
committed train (below) observes the stale value at `c == 0`,
overwrites it in place, and performs the allocation probe with
committed-path state.

### Train (commit, provider-only)

Hooked at the head-instruction retirement point; squashed instructions
never reach it, so wrong-path never trains and no doomed-window gating
is needed at this site.

1. Locate the provider from the instruction's token (tag-checked). A
   stale token (entry reallocated in flight) or a token-less
   instruction (only MRN-claimed loads, which bypass predict())
   falls back to a train-time longest-match recompute from the
   instruction's snapshot — training remains unconditional (recompute
   events are counted; a declared deviation from training the
   predict-time provider).
2. Provider update: correct → `c++` with FPC probability, `u = 1`;
   wrong → if `c == 0` overwrite `val` with the actual value,
   else `c = 0`; `u = 0`.
3. Allocation on a wrong training outcome: probe components with
   rank > provider at their indices; allocate into a randomly chosen
   one with `u == 0` (`{val = actual, c = 0, u = 0}`, write tag); if
   none qualifies, reset `u = 0` on all of them (aging), no
   allocation.

### FPC (Forward Probabilistic Counters)

Each forward transition `i → i+1` fires with probability `v[i]`;
default (squash-recovery vector) **`v = {1, 1/16, 1/16, 1/16, 1/16,
1/32, 1/32}`**. The reset to 0 is never probabilistic. Randomness via
gem5's `Random::genRandom()` (deterministic under the global seed);
the params-free core takes an injectable RNG handle so GTests drive
transitions deterministically. The vector is a param — the EVES
follow-up replaces it per instruction class.

### History Subsystem (framework-level, predictor-agnostic)

- **Update choke point:** the per-instruction fetch path where the
  predicted direction and the DynInst coexist (`BAC::updatePC` in this
  tree — it covers both the decoupled-FDP and coupled front-end modes
  and BTB-miss surprise branches). Conditional branches shift their
  predicted direction into `ghr`; every taken control transfer shifts
  low target-PC bits into `path`. Every fetched instruction is stamped
  with the pre-update `{ghr, path}`.
- **Restore — general rule: every fetch redirect restores `{ghr,
  path}` to the history state at the refetch point.** Per initiator:
  - IEW-resolved conditional mispredict at branch B: restore
    `B.snapshot`, then advance by B's *resolved* outcome — direction
    into `ghr`, target bits into `path` if taken.
  - Indirect/target-only mispredict: `ghr` per the direction rule
    (unchanged if the direction was right), `path` advanced with the
    corrected target.
  - Decode-detected branch corrections (`squashFromDecode`): same
    rule with the decode-resolved outcome.
  - Inclusive VP/memory-order squash at instruction I (I refetches):
    restore `I.snapshot` exactly.
  - Commit trap/interrupt (`squashAll`): restore the squash-point
    instruction's snapshot exactly.
  - Commit squash-after (ISB/eret-class — the instruction COMMITS,
    younger squash): restore the committed instruction's snapshot
    advanced past its own contribution.
  - FTQ/BAC resteers that discard no DynInsts need no restore.
- LVP ignores all of it: predictors declare `usesHistory()`; the
  subsystem is active only when the attached predictor uses it, so
  LVP configurations remain behaviorally identical: pre-existing stat
  values and simTicks are unchanged (the two framework counters —
  `historyRestores`, `correctiveResetStale` — appear as new
  zero-valued lines in stats.txt).

## Framework API Changes

- `predictImpl`/`trainImpl` take a `VpLookupContext {Addr pc; MicroPC
  upc; VpHistSnapshot hist}`, with `VpHistSnapshot = {uint64_t ghr;
  uint16_t path}` (`vp_types.hh` / `vp_history.hh`). **predictImpl
  returns a result
  struct `{std::optional<RegVal> value; uint64_t token;}`** — the base
  class stamps the token on every lookup (see Predict step 3) and
  passes it back in at train/verify. LVP ignores context history and
  returns token 0; its behavior is bit-identical.
- `BaseValuePredictor` gains `virtual bool trainsAtCommit() const`
  and `virtual bool usesHistory() const` (both default false; VTAGE
  overrides both), plus the verify-site corrective-reset entry
  (`correctiveReset(token)`) used only in `trainAtCommit` mode.
- Commit-stage hook at head-instruction retirement (after the
  fault/interrupt outs, before the committed rename-map update): for
  in-scope retiring instructions, read the dest physreg (still live —
  it becomes the committed mapping and is freed only when a younger
  same-arch-reg writer commits) and call `train()`. The LSQ/IEW
  writeback train calls are skipped when `trainsAtCommit()`.
- Verify (and the wrong-prediction squash) stays at writeback,
  unchanged, plus the corrective reset above.

## Configuration (All Params)

| Param | Default | Provenance |
|---|---|---|
| `baseEntries` | 8192 | HPCA'14 |
| `taggedEntries` (per component) | 1024 | HPCA'14 |
| `numTagged` | 6 | HPCA'14 |
| `historyLengths` | 2, 4, 8, 16, 32, 64 | HPCA'14 |
| `tagBits` | 12 + rank | HPCA'14 |
| `confBits` | 3 | HPCA'14 |
| `confThreshold` | 7 (saturation; >= 1 enforced) | HPCA'14 |
| `fpcVector` | 1, 1/16, 1/16, 1/16, 1/16, 1/32, 1/32 | HPCA'14 (squash variant) |
| `pathBits` | 16 | project choice (HPCA'14 gives no width; ghr width 64 derived from max history) |
| CLI | `--use-vp vtage` + `--vtage-*` overrides | — |

## Files (Planned)

`src/cpu/o3/vp/vtage_tables.{hh,cc}` (params-free core: banks, folds,
selection, FPC with injected RNG, allocation, corrective reset) +
`vtage_tables.test.cc`; `src/cpu/o3/vp/vtage.{hh,cc}` (SimObject
wrapper + per-component stats); `ValuePredictor.py` + `SConscript`
additions; framework edits in `base.{hh,cc}` (context, result struct,
knobs, history subsystem), `fetch.cc`/`bac.cc` (notifications +
stamping + restores), `commit.cc` (train hook), `lsq_unit.cc`/`iew.cc`
(corrective reset + train-site gating), `dyn_inst.hh` (snapshot +
token), `sim_opts.py` (CLI).

## Statistics

Base-class surface unchanged in shape. **Denominator caveat
(declared):** in `trainAtCommit` mode the eligible counters — the
coverage denominator — count *retiring* instructions, whereas LVP's
count at writeback includes instructions squashed after writeback;
VTAGE-vs-LVP coverage comparisons carry this systematic difference
(stat descriptions will state the counting site; the Stage-IV report
must repeat the caveat). Two counters live on the BASE class (every
predictor reports them; zero-valued for LVP): `historyRestores`, a
vector by initiating redirect plus a `missed` bucket, and
`correctiveResetStale`. VTAGE adds: per-component provider counts and
correct/wrong-by-provider (7-way vectors), allocations,
allocation-failures (u-aging events), corrective resets, token-stale
recomputes, FPC increments fired/suppressed.

## Testing Gates

1. GTests on `vtage_tables`: fold determinism (same snapshot → same
   indices), longest-match selection, threshold gating, FPC statistics
   under an injected deterministic RNG, provider update rules
   (val-overwrite only at `c == 0`), allocation/aging, corrective
   reset via token incl. the stale-tag skip and the VT0/index-0 token
   case, µPC separation.
2. Smoke matrix with `--use-vp vtage`: baseline inertness, the MRN+VP
   ladder co-existence run (run 4 of the LVP plan's Step-7 smoke
   matrix), and a hostile wrong-path run at **`confThreshold 1`**
   (arms after one correct with `v[0] = 1`; reset to 0 < 1 keeps the
   no-livelock invariant) with the explicit pass criterion
   `predictionsWrong > 0` plus the stat identity and a
   checksum-vs-baseline match.
3. Stage-III: `vpchase`/`vpalu` (the base component should reproduce
   LVP's ~6x), plus a new `vphist` microbenchmark: a single-PC integer
   load whose value is fully determined by a branch-direction pattern
   — unpredictable to LVP, fully predictable to VTAGE. Constraints
   from review: the branch must survive compilation (aarch64
   if-conversion turns this exact shape into csel — force a real
   branch and verify by disassembly), and the pattern's windows must
   be phase-unique within the shortest useful history length.
4. Stage-IV: 190-checkpoint sweep in **both scopes** (`vtage`
   loads-only and `vtage_all`), reusing the existing `base` runs;
   headline comparison vs `lvp`/`lvp_all`. Note the paper's
   accuracy/coverage expectations correspond to all-instructions
   scope.

## Out of Scope

E-VTAGE per-class FPC rates (follow-up knob); E-Stride; HAL
alternate-component substitution; selective reissue; FP/vector
destinations (framework rule unchanged).
