# Value Prediction Framework + Last-Value Predictor Design

- **Date:** 2026-08-02 · **Branch:** `vp` · **Status:** approved in design
  review (this doc is the written record)
- **Source plan:** `src/cpu/o3/vp/vp_spec.md` (Rahul's rough design plan)
- **Anchor paper:** M. H. Lipasti and J. P. Shen, "Exceeding the Dataflow
  Limit via Value Prediction," MICRO-29, 1996. Successor predictors
  (VTAGE, EVES) are in `src/cpu/o3/vp/papers/` — explicitly out of scope
  here, but the framework API must not preclude them.

## Goal and Context

Value Prediction (VP) is the third stage of Garfield's speculative
data-dependency-breaking sequence (branches → memory renaming → value
prediction). This spec covers the **algorithm-agnostic VP framework**
plus the deliberately simple **Last-Value Predictor (LVP)** whose job is
to prove the framework end-to-end — not to maximize benefit.

Design constraints carried over from the MRN chapter
(`docs/research-log/MRN/`):

- Wrong data-flow predictions are expensive (~60–300 flushed insts per
  wrong, scaling with the service level of the mispredicted load), so
  confidence defaults start conservative.
- Mechanisms must be regime-stable; verify/squash semantics copy MRN's
  proven **inclusive** verify-squash model — the mispredicted
  instruction is squashed and refetched along with everything younger —
  so MRN's measured flush economics carry over directly.
- MRN's chapter is closed: its algorithm code is **not modified**. The
  shared squash plumbing it used is *generalized* — a mechanical enum
  rename plus an IEW helper extraction, no behavior change (see Squash
  Plumbing); everything else is reuse of existing mechanisms as-is.

## Terminology

Two terms are used precisely throughout this spec:

- **Eligible** — passes the hard rules only: single scalar **integer**,
  non-fixed-mapping destination register; not a serializing, barrier,
  non-speculative, atomic, or store-conditional instruction (see
  Eligibility and Knobs).
- **In scope** — eligible AND permitted by the `onlyLoads` knob (in the
  default loads-only mode, only eligible loads are in scope; in
  all-instructions mode, in scope = eligible).

## Directory Layout and Build Glue

All framework code lives in `src/cpu/o3/vp/`:

| File | Role |
|------|------|
| `ValuePredictor.py` | SimObject declarations: `BaseValuePredictor` (abstract) + `LastValueVP` |
| `SConscript` | `SimObject(...)`, `Source(...)`, `GTest(...)`, `DebugFlag('ValuePred')` |
| `base.{hh,cc}` | `BaseValuePredictor` SimObject: unified API, eligibility filter, base stats |
| `vp_key.hh` | Params-free lookup-key helper: folds (PC, micro-PC) into the table key. Lives outside `base.hh` so GTests cover it without the SimObject/params machinery. |
| `last_value.{hh,cc}` | `LastValueVP` SimObject: thin wrapper over the core table |
| `lvp_table.{hh,cc}` | Params-free LVP core table (the VPT) — pure table logic, no SimObject/params dependencies |
| `lvp_table.test.cc` | GTest unit tests for the core table and the key helper |

The O3 CPU (`BaseO3CPU.py`) gains
`valuePred = Param.BaseValuePredictor(NULL, "Value predictor; NULL disables VP")`
— the same NULL-disables-the-feature idiom as the adjacent
`memRenamePredictor` param (`BaseO3CPU.py:213`). NULL keeps VP compiled
in but inert.

**Structure rationale (decided):** prefetcher-style SimObject hierarchy
(cf. `src/mem/cache/prefetch/`) for the pipeline-facing structure, with
each algorithm's table logic in a params-free class exercised by GTests —
the pattern that let MRN catch logic bugs before any simulation ran.
Future predictors (VTAGE, EVES) each add one derived SimObject + one
params-free core + one test file.

## The Unified API

`BaseValuePredictor` exposes four pipeline-facing operations plus one
reserved hook:

- `std::optional<RegVal> predict(const DynInstPtr &inst)` — called at
  **rename** by `rename.cc` for every renamed instruction that MRN did
  not claim; the base class **alone** decides eligibility and scope
  (rename.cc does not replicate the filter). Empty return = no
  prediction, for any of: ineligible, out of scope, table miss, or
  below the confidence threshold. The base class does the stat
  accounting and delegates confident lookups to the derived
  `predictImpl(key)`.
- `void train(const DynInstPtr &inst, RegVal actualValue)` — called at
  **writeback** for every **in-scope** instruction that has not already
  been squashed: loads at LSQ writeback always (including MRN-claimed
  loads and loads whose confidence was below threshold — tables must
  stay warm regardless of predictor engagement); non-loads at IEW
  writeback, which only happens in all-instructions mode. Instructions
  already squashed by the time they reach writeback neither verify nor
  train (wrong-path table pollution). The base class counts the
  eligible population and delegates to `trainImpl(key, actualValue)`.
- `void verifyResult(const DynInstPtr &inst, bool correct, uint64_t
  flushed)` — outcome accounting for a consumed prediction, called
  from the verify sites (which own the value comparison); `flushed` is
  the measured inclusive squash cost when wrong. Level attribution
  runs for loads only.
- `void notifySquashed(const DynInstPtr &inst)` — a predicted instruction
  was squashed (by a branch mispredict, an MRN squash, etc.) before its
  prediction could verify: counted, never trained — matching MRN's
  squashed-before-verify accounting.
- `virtual void notifyPipelineSquash()` — reserved no-op hook for
  restoring speculative predictor state on a squash; LVP ignores it.
  This reduces — but does not eliminate — the API growth VTAGE-class
  predictors will need: they additionally require branch-outcome/path
  history wiring to build the histories they index with, which is an
  anticipated API extension, not a precluded one.

**Lookup key:** the instruction PC with the micro-PC folded in, computed
by the params-free `vp_key.hh` helper (GTest-covered). ARM cracks
macro-ops (e.g. `ldp` → two micro-ops sharing a PC); without the
micro-PC in the key, two different destination values ping-pong a single
VPT entry and confidence never builds.

## Pipeline Integration

- **Rename (consume).** At the existing MRN consume site in
  `rename.cc`, the optimization priority ladder is code order:
  **MRN → VP → normal execute**. If MRN forwarded the load, VP is not
  consulted. Otherwise, if `predict()` returns a value: write it into
  the renamed destination physreg and mark the scoreboard ready (the
  same mechanism MRN's value-forward path uses), stash the predicted
  value on the DynInst, and set its `VpPredicted` flag. Consumers wake
  immediately; the predicted instruction still issues and executes
  normally.
- **Verify — loads.** In `lsq_unit.cc` at load writeback: compare the
  true loaded value against the stashed prediction. Correct → proceed
  normally. Wrong → **inclusive squash**: the load and everything
  younger are squashed and refetched from the load's own PC — MRN's
  actual verify-squash semantics (`includeSquashInst=true`), triggered
  via `IEW::squashDueToValueMispredict` (see Squash Plumbing). Then
  train. No squash livelock: a wrong verify leaves confidence below
  threshold by construction (reset mode; decrement mode clamps to
  threshold − 1; threshold 0 is rejected), and IEW's doomed-window
  guard blocks squash-shadowed instructions from re-training the entry,
  so the corrective train is the last table write before the refetched
  instance re-renames — and it is not re-predicted.
- **Verify — non-loads** (all-instructions mode only). A new, symmetric
  verify site in IEW's writeback path (`IEW::writebackInsts()`): compare
  the FU result against the prediction, with the same inclusive squash
  on mismatch. This is the only genuinely new verify machinery;
  loads-only mode never exercises it, which is why testing is staged
  loads-first.
- **Squash plumbing** (decided in design review). Two mechanical
  generalizations of the shared plumbing, no behavior change:
  1. The squash-attribution enum outgrew its MRN-era name before VP
     arrived (it already carries `Branch`, `MemOrder`, `Other`), so
     `MrnSquashReason` → **`SquashReason`** (`mrn_squash_reason.hh` →
     `squash_reason.hh`), with the names array, the `toCommit`
     time-buffer field, and the ROB accessor renamed to match.
     Enumerators are unchanged (the `Mrn*` members correctly name
     MRN-specific reasons) plus new **`ValuePred`**; the vectored
     kill-attribution stats gain the bucket automatically.
  2. `IEW::squashDueToMemOrder` already serves two masters (real
     memory-order violations and MRN verify squashes), and its body is
     fully generic. Extract that body into a private IEW helper;
     `squashDueToMemOrder` remains a thin wrapper for its existing
     callers (call sites untouched, upstream-recognizable name kept),
     and a new sibling **`IEW::squashDueToValueMispredict(inst, tid)`**
     — writing reason `ValuePred` — serves VP, so VP code (including
     the non-load verify site) never calls a MemOrder-named function.
  No new time-buffer fields are needed. Side benefit: in future MRN+VP
  composition runs, MRN predictions killed by VP squashes are correctly
  attributed instead of lumped into `other`.
- **DynInst additions:** `_vpPredVal` (RegVal) plus `VpPredicted` /
  `VpResolved` instruction flags — mirroring the existing Mrn fields.

## Eligibility and Knobs

Hard eligibility rules (this iteration):

- Single **scalar integer** destination register only (decided in design
  review: integer-only first; FP/vector consume machinery comes later as
  its own extension). Micro-ops are handled individually — each cracked
  micro-op with a single integer dest is eligible on its own.
- Not a serializing/barrier instruction; stores and branches without an
  integer dest are naturally ineligible.

Base-class params (with CLI in `configs/garfield/arm/sim_opts.py`,
`garfield` argument group):

| Param | Default | CLI | Meaning |
|-------|---------|-----|---------|
| `onlyLoads` | `True` | `--vp-all-insts` (clears it) | Scope knob: loads only vs. all eligible instructions (see Terminology) |
| `scalarOnly` | `True` | (param only for now) | Restrict to scalar dests. Redundant while the integer-only hard rule stands (vector dests are already excluded); the knob exists so the API is stable when FP/vector support lands, per the source plan. |

Predictor selection: **`--use-vp <type>`** takes the predictor type name
(decided in design review). Initially the only valid value is `lvp`;
later `vtage`, `eves` attach different derived SimObjects with no new
flags. No `--use-vp` → `valuePred` stays NULL.

## The Last-Value Predictor

VPT entry: `{valid, tag, RegVal lastValue, conf}`. Set-associative, LRU
replacement, full tags (a research simulator should not fold false
aliasing artifacts into results; hardware would truncate).

- `train(key, actual)`: on a hit, `actual == lastValue` → saturating
  `conf++`; mismatch → `conf = 0` (default) or a decrement clamped
  below the threshold, `conf = min(conf − 1, confThreshold − 1)`
  (knob; the clamp keeps the no-livelock invariant true), and
  `lastValue = actual` always. On a miss: allocate (LRU victim),
  `lastValue = actual`, `conf = 0`.
- `predict(key)`: hit ∧ `conf >= confThreshold` → `lastValue`.

`LastValueVP` params (all CLI-exposed):

| Param | Default | CLI |
|-------|---------|-----|
| `entries` | 4096 | `--vp-entries` |
| `assoc` | 4 | `--vp-assoc` |
| `confBits` | 4 | `--vp-conf-bits` |
| `confThreshold` | 15 | `--vp-conf-threshold` |
| `confDecrementOnWrong` | `False` (reset to zero) | `--vp-conf-decrement` |

Default rationale: MRN measured ~60–300 flushed insts per wrong
prediction, so the starting threshold is near-saturated (15 of a 4-bit
counter). Raising the threshold further just means widening `confBits`.
Stage-III/IV run these fixed conservative defaults; threshold/geometry
tuning is a separate later effort (see Out of Scope).

## Statistics

Base class (one stats group per attached predictor, e.g.
`system.cpu.valuePred.*`). Counting sites are pinned to make the
formulas unambiguous:

- **`eligibleLoads` / `eligibleNonLoads`** (two scalars — the
  implemented stat names) increment at the **train site** — i.e., once
  per in-scope, not-already-squashed instruction reaching writeback,
  including MRN-claimed loads. In loads-only mode the non-loads scalar
  is structurally zero (it documents the mode).
- **`predictionsMade`** increments at **rename** (speculative path —
  includes wrong-path predictions later killed by unrelated squashes).
- Outcomes: **`predictionsCorrect`**, **`predictionsWrong`** (verify
  site), **`predictionsSquashed`** (squashed before verify). Accounting
  identity, checked in testing:
  `predictionsMade = correct + wrong + squashed`.
- Flush cost: **`squashedInsts`** — instructions discarded by VP
  verify-squashes (inclusive, so the mispredicted instruction itself
  counts, as in MRN).
- Formula stats: **coverage** = `predictionsCorrect / eligible`
  (the loads-only mode denominator is loads by construction — no
  dilution by never-predicted non-loads); **accuracy** =
  `correct / (correct + wrong)`.
- Service-level attribution for VP-predicted **loads**, reusing the
  `MemSrcLevel` plumbing already on DynInst (stlf/l1d/l2/mem/unknown):
  correct-by-level, wrong-by-level, and wrong-flushed-by-level — the
  stat family the MRN chapter proved out.

Derived LVP stats: table lookups/hits/allocations/evictions, confidence
resets (or decrements), below-threshold suppressions.

## Testing and Deliverable Stages

- **Stage-I + Stage-II land together** (framework + LVP): the framework
  alone cannot run, and LVP is its acceptance test. Gated by
  `lvp_table.test.cc` GTests: predict/train semantics, threshold
  behavior, reset-vs-decrement, eviction, and (PC, micro-PC) key
  folding via the `vp_key.hh` helper.
- **Stage-III — microbenchmarks**, in
  `gem5-infra/workloads/microbenchmarks` following the existing
  `mrncomm`/`mrnrec` structure: (1) loads-only mode: a load-dependent
  serial chain whose loaded values are invariant, so correct VP breaks
  the chain; (2) all-instructions mode: an invariant-value ALU dependency
  chain. Success = high coverage, high accuracy, and speedup over the
  no-VP/no-MRN baseline. Detailed benchmark design happens at this
  stage, not in this spec.
- **Stage-IV — SPEC26 deployment:** the 190-checkpoint sweep against the
  no-VP/no-MRN baseline, using the existing sweep infrastructure
  (first-dump-block ROI, `start.core.ipc` convention). Loads-only and
  all-instructions modes are one flag apart; which to sweep is decided
  at that stage.

MRN+VP composition testing is deferred: the priority ladder is coded
from day one, but all Stage-III/IV runs use MRN off.

## Out of Scope (Deferred, Deliberately)

1. FP and vector destination prediction (`scalarOnly` /
   integer-only rules above).
2. VTAGE and EVES (papers staged in-tree; framework hooks reserved,
   branch-history wiring anticipated as an API extension).
3. MRN+VP composition evaluation.
4. VPT port/bandwidth modeling (predictions are unthrottled at rename,
   as is standard in VP research simulators).
5. Confidence-threshold and table-geometry tuning beyond the
   conservative defaults (Stage-III/IV run the defaults as-is).

## References

1. M. H. Lipasti and J. P. Shen, "Exceeding the Dataflow Limit via
   Value Prediction," MICRO-29, 1996.
2. M. H. Lipasti, C. B. Wilkerson, and J. P. Shen, "Value Locality and
   Load Value Prediction," ASPLOS-VII, 1996.
3. A. Perais and A. Seznec, VTAGE/EVES papers staged in
   `src/cpu/o3/vp/papers/` (exact citations to be verified from the PDFs
   when those predictors are designed).
