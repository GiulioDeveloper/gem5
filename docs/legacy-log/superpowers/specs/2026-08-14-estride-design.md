# E-Stride + EVES composition design (EVES Stage 2)

Date: 2026-08-14. Status: draft for review.
Predecessors: `2026-08-02-vp-framework-design.md` (framework contract),
`2026-08-03-vtage-design.md` (history subsystem, verify-site corrective
punish), `2026-08-04-evtage-design.md` (E-VTAGE port, classifier
plumbing, burst guard). This spec adds the second EVES component — the
Enhanced Stride predictor — and the EVES composition that arbitrates
between E-Stride and the already-shipped E-VTAGE.

## 0. Goal and scope

Port CVP-1 EVES's E-Stride predictor (Seznec, "Exploring value
prediction with the EVES predictor", CVP-1 2018, HAL hal-01888864;
local copy `docs/research-papers/eves.pdf`) into the Garfield VP
framework and compose it with our E-VTAGE into the full EVES
predictor, evaluated against the chapter-best `evtage_all` (geomean
1.0238, 190 SPEC26 checkpoints).

Why it should matter: in the CVP framework E-Stride alone contributes
16.1% of EVES's 25.3% — from a <1KB structure — with only 3.4% mean
coverage, concentrated in L2/LLC-miss loads; its complementarity with
E-VTAGE is strong (41 vs 40 traces >10%, only 19 shared) and the
inflight compensation alone is worth ~2%. It is the high-reward,
low-coverage counterpart to E-VTAGE's high-coverage profile.

In scope: a params-free `EStrideTable` core + GTests; a new `EvesVP`
SimObject (`--use-vp eves`); a framework-level in-flight-occurrence
counter subsystem; SafeStride; the arbitration (with its ratified
ablation flag); stats; a `vpstride` microbench; probe-16 → 190
evaluation. Out of scope: any change to E-VTAGE's algorithm or params
(the `EVtageVP` SimObject stays frozen); MRN interactions beyond "must
not break" (the composition chapter closed MRN); FP/vector scope.

## 1. Sources of truth and fidelity doctrine

The authoritative reference is the CVP-1 contest source
(`cvp8KB/mypredictor.{cc,h}` from Seznec.tar.gz,
microarch.org/cvp1; line numbers below cite it as cc:/h:). The paper
is motivation and cross-check only: a 4-agent adversarial
verification (2026-08-14) found the paper's prose wrong or imprecise
in several places, and **the code wins every time**:

- The paper's L2-hit (5/16) and L1-hit (9/64) confidence-increment
  fractions are the author's own arithmetic slip — the two-draw OR
  evaluated as p + p² instead of 2p − p² (the two expressions coincide
  at p = 1/2, and at p = 1 the paper's "1" survives only because
  probability caps at 1 — which is why those two rows check out).
  The code's true values are 7/16 and 15/64 in the two-draw regime.
- The large-stride draw boosts compare the **signed** stride
  (`abs (stride >= 8)` — abs of a boolean, cc:154-155): negative
  strides never get them. Implemented as written.
- The arbitration comment ("when both are high confidence pick the
  VTAGE prediction", cc:142) describes intent, not mechanism — see §5.
- "u reset on misprediction" is conditional (only on conf collapse);
  the SafeStride "16-bit, cap 32767" is a pre-checked plain int that
  can legally reach 32774 and go far below −1024.

Quirks are implemented as written and pinned by tests; deviations from
the source are declared (§12) — nothing is silently "fixed".

## 2. Architecture

One new SimObject, one new params-free core, one new framework
facility:

- **`EStrideTable`** (`src/cpu/o3/vp/estride_table.{hh,cc}`,
  `estride_table.test.cc`): the stride predictor core. Params-free,
  fixed verbatim geometry (ratified fork), injectable RNG
  (`std::function<double()>`, same idiom as `EVtageTables`), zero
  framework dependencies. All CVP table rules from §3 live here —
  **including the SafeStride counter and its tick/credit/penalty
  operations and predict gate** (so §10's SafeStride and gate-order
  GTests target the core directly); `EvesVP` only drives the call
  sites. The arbitration decision (§5) is likewise a pure, GTestable
  helper function over POD inputs, not logic buried in the SimObject.
- **`EvesVP`** (`src/cpu/o3/vp/eves.{hh,cc}`): SimObject
  `--use-vp eves`, inheriting `BaseValuePredictor` directly (Python:
  `EvesVP(BaseValuePredictor)`). It **owns** one `EVtageTables`
  instance (constructed from the same param set E-VTAGE uses — the
  E-VTAGE params are duplicated on the Python class; drift risk
  accepted and documented) plus one `EStrideTable`.
  `trainsAtCommit() = true`, `usesHistory() = true`,
  `usesInflightCounts() = true` (new knob, §4). `EVtageVP` itself is
  not touched.
- **In-flight-occurrence counters** (§4): live in
  `BaseValuePredictor`, maintained only when the attached predictor
  sets `usesInflightCounts()` — the same opt-in pattern as the
  history subsystem.

New params on `EvesVP` beyond the duplicated E-VTAGE set:

- `vtageOverwriteRequiresConfidence` (Bool, default True): the
  ratified arbitration ablation (§5). False = source-verbatim
  overwrite; True = the comment's intended semantics. [Amended
  2026-08-15: the original default was False (source-verbatim); the
  190-checkpoint A/B showed confidence-gating wins by +3.6% (the
  composition report), so True is the shipped default and the
  verbatim mode is the opt-in ablation, exposed as
  `--eves-vtage-overwrite-verbatim`.]

`burstGuardWindow` is inherited from the duplicated set and — unlike
on the frozen `EVtageVP` — is actually usable on `EvesVP`, because
this work finally wires the rename-rate feed (§4). Default stays 0
(chapter-iso); 128 = CVP's own behavior, available as an ablation.

Config layer: `sim_opts.py` gains `eves` in the `--use-vp` choices;
the existing `--evtage-hist-lengths` (and the other evtage knobs it
forwards) apply to the embedded VTAGE side unchanged, plus two new
switches: the arbitration-mode switch (post-amendment:
`--eves-vtage-overwrite-verbatim`, opting back into the source's
overwrite) and the shared `--evtage-burst-guard` (forwards to
`EvesVP.burstGuardWindow`). Evaluation arms run the dense-64 series
`{2,4,6,11,20,36,64}` on the VTAGE side — identical to the
`evtage`/`evtage_all` control arms.

## 3. EStrideTable core — verbatim rules

### 3.1 Geometry and entry (ratified: verbatim 48 entries)

3-way skewed-associative, 16 sets/way interleaved in one flat
48-entry array (way i occupies slots ≡ i mod 3; h:59-62 — the active
K8 block; the disabled K32 block carries identical stride geometry —
and cc:69-87):
LOGSTR=4, NBWAYSTR=3, TAGWIDTHSTR=14, LOGSTRIDE=20. Index and tag are
pure hashes of the folded (PC, µPC) key (`vp_key.hh`) — CVP hashes
`pc + piece`; we hash the folded key, the port's established
equivalent. The source's dead `if (j < 0) j = 0` clamp (cc:77-78,
j ∈ {1,2,3}) is dropped with a comment noting the source contains an
unreachable clamp.

Entry (106 bits accounted): `lastValue` (uint64_t — the last
**committed** value), `stride` (uint64_t at full width; "20 bits" is
storage accounting only — the range check at train is the sole
enforcement), `conf` (5-bit, max 31), `u` (int, invariant 0..3 —
asserted), `tag` (14-bit), `notFirstOcc` (bool). Plus the single
global SafeStride counter (§3.5), also owned by the table. Storage:
48×106 + 16 = 5104 bits ≈ 0.64KB.

Initial state, as in the source (h:125, h:128): everything
zero-initialized, **no valid bit** — a key whose way tag hashes to 0
tag-hits a virgin entry and trains down the hit path (first-occurrence
arm) rather than allocating, exactly as CVP's zeroed static array
behaves; SafeStride starts at 0, so the `>= 0` predict gate passes
from the first cycle. GTest-pinned (§10).

### 3.2 Predict path

Gates, in source order (cc:99-104): tag hit (first-match way 0→2) →
`SafeStride >= 0` → `conf >= 7` (MAXCONFIDSTR/4; ">=", so conf 7..31
predicts). Nothing else gates — not `notFirstOcc`, not the stride
value. On pass:

    predicted = lastValue + (inflight + 1) * (int64_t)stride

with `inflight` supplied by the framework counter (§4), signed 64-bit
arithmetic, cast back to uint64 (cc:114-116).

### 3.3 Commit-time update (train)

Called for every in-scope committed instruction (the framework's
commit-train site), whether or not a prediction was issued. Order
within `EvesVP::trainImpl`: VTAGE train first, then stride train
(CVP's UpdateVtagePred-before-UpdateStridePred, cc:767-772). Way
search re-runs the same pure hashes (CVP saves B[]/TAGSTR[] only to
avoid recompute; values are identical; the entry may have been
reallocated in flight — first tag match wins, aliasing accepted, as
in the source).

On a tag hit (cc:228-306): compute `delta = actual − lastValue`;
range-accept iff delta ∈ [−2^19+1, +2^19] — the source's asymmetric
window, `abs(2*delta − 1) < 2^20` (cc:233-239) — else the candidate
stride is 0. We implement the window as that overflow-free interval
test, not the source's raw expression: `2*delta` is UB-prone at
int64 extremes and the source's unqualified `abs` overload is
harness-header-dependent — the same hazard class the E-VTAGE port
pinned for LOWVAL (evtage_tables.cc's lowVal), and the same
resolution (declared in §12; huge-delta cases GTest-pinned).
`lastValue = actual` unconditionally, **before** any branch (cc:241).
The clamped candidate feeds only the §3.4 draw's stride argument and
the first-occurrence store; the trained-arm match predicate below is
the source's raw arithmetic identity (cc:230-232, 246), not a
comparison against the candidate. Then:

- **First occurrence** (`notFirstOcc == false`): nonzero in-range
  delta → `stride = delta`; zero/out-of-range delta → the demotion
  sentinel `stride = 0xffff, conf = 0, u = 0` (cc:296-302 — this IS
  the paper's "null strides are systematic replacement targets":
  constant-value entries ping-pong between this arm and the mismatch
  arm forever, conf/u pinned at 0, evictable by both victim passes).
  Either way `notFirstOcc = true`.
- **Trained, one-step match** (`lastValue_old + stride == actual`):
  probabilistic `conf++` and `u++`, each gated by an **independent**
  draw of the §3.4 function (cc:249-259); then unconditionally
  `u = 3` if `conf >= 7` (cc:260-261). The `conf < 31` / `u < 3`
  saturation guards sit **outside** the draw function, as in the
  source — a saturated counter consumes zero draws — and §3.4's
  deterministic conjunct short-circuits ahead of all draws (both
  matter for §10's draw-count tests).
- **Trained, one-step mismatch**: `conf > 4 ? conf -= 4 :
  {conf = 0, u = 0}` (conf == 4 resets; u survives the −4 branch);
  `notFirstOcc = false`; stored stride untouched (cc:266-284). This
  is a **table-local** event — it fires regardless of whether a
  pipeline prediction was issued, and is distinct from the SafeStride
  penalty (§3.5).

On a tag miss (cc:307-362): allocation is attempted only when
`!deliveredCorrect` (CVP's `!U->prediction_result` — "already
predicted correctly (by VTAGE): don't waste a stride entry"), and
passes the class/latency draw (§3.4 alloc ladder). Victim search from
a random start way: pass 1 claims `conf == 0`, pass 2 claims
`u == 0`; a claimed entry is installed as `{conf = 1, u = 0, tag,
stride = 0, notFirstOcc = false, lastValue = actual}` (conf = 1
deliberately, to survive pass 1 until the first stride observation —
cc:320). If both passes fail, the last-probed way's u is decremented
with probability 1/2^(2 + 2·(conf > 3) + 2·(conf >= 7)) (cc:352-359;
u stays in 0..3 by construction — pass 2 would have claimed any
u == 0 entry before aging could underflow it; asserted).

### 3.4 Probabilistic draws

Confidence/u increment gate (cc:149-162), evaluated per call with
fresh draws:

- Deterministic conjunct: `!deliveredCorrect || stridePredicted`
  (CVP's `(!U->prediction_result) || (U->predstride)` — a correct
  VTAGE-covered instruction must not warm the stride entry).
- Base Bernoulli p = 2^−E with
  E = NOTLLCMISS + NOTL2MISS + NOTL1MISS + 2·MFASTINST + 2·(≠load),
  mapped from `VpClassifierInfo` exactly as `EVtageTables` maps its
  own exponents (memSrcLevel → notL1Miss/notL2Miss/notLlcMiss;
  fastInst for MFASTINST).
- Draw count: 1; doubled to 2 if `stride >= 8` (signed!); doubled
  again to 4 if `stride >= 64` (signed) — short-circuit OR of
  independent draws, structure preserved so injected-RNG tests can
  count consumed draws.
- Small-stride load throttle (bitwise-& with the above, both sides
  evaluated): pass iff `|stride| > 1` or non-load; stride −1 loads
  pass a further 1/2 coin, +1 loads a 1/4 coin, stride-0 loads never
  pass.

Allocation ladder (cc:166-197): Alu/Store 1/64; SlowAlu (our
IntMult/IntDiv/Float* class, covering CVP's fp and slowAlu — both
1/16) 1/16; Load 1/2^(NOTLLCMISS + NOTL2MISS + NOTL1MISS + MFASTINST)
(LLC-miss 1, LLC-hit 1/2, L2-hit 1/4, L1-hit 1/8, store-forwarded
1/16 — the LLC-hit arm is unreachable under our memSrcLevel mapping,
which has no distinct LLC row, same as the E-VTAGE port); IndirectCall
and Undef never allocate (absent from CVP's
switch — note this differs from E-VTAGE's own "alu-like Undef"
dispatch, which stays as shipped on the VTAGE side).

Draws are probability-equivalent, not bitstream-identical, to CVP's
`random()` masks — the established `EVtageTables` porting rule.

### 3.5 SafeStride

A single **global** plain `int`, exactly as in the source (h:128 —
CVP has one counter, not one per thread), owned by `EStrideTable`
(state, arithmetic, and the predict gate live in the core; `EvesVP`
drives the call sites). Global also sidesteps the verify site's
tid-less interface (`correctiveReset(uint64_t)` carries no ThreadID —
the gap evtage.hh already documents for lastWrongMark). Operations:

- **+1 per in-scope committed instruction**, driven from the
  commit-train site (ratified fork; CVP ticks per eligible
  instruction at its speculative hook — commit excludes wrong-path, a
  declared deviation), pre-checked against the 32767 cap
  (cc:809-810).
- **+4 (+8 for loads)** when `deliveredCorrect && stridePredicted`
  at commit-train (CVP credits at result-reveal; deferring to commit
  is a declared deviation — single-digit cycles of gate lag), with
  the source's pre-check-then-add (can legally overshoot to 32774,
  cc:815-817).
- **−1024** at the verify-wrong site when the token's
  `stridePredicted` bit is set (cc:823-824) — keyed off the flag,
  not off which component supplied the value (source-exact; §5). No
  lower clamp anywhere.
- Gate `SafeStride >= 0` at predict (§3.2).

## 4. In-flight occurrence counters (framework facility)

Ratified fork: an exact per-PC counter table replaces CVP's 256-deep
ring scan (which double-counts past 256 in flight and can match stale
slots — hazards confirmed in the verification pass).

State: `unordered_map<uint64_t, uint32_t>` in `BaseValuePredictor`,
keyed by the folded vpKey (not thread-qualified: two SMT threads at
the same PC would share a counter — the same single-thread declared
generalization as the burst-guard machinery; our runs are
single-threaded), erased on reaching zero; accessor
`inflightCount(key)`. Maintained only when the attached predictor's
`usesInflightCounts()` is true — all hooks below early-return
otherwise, keeping every existing configuration behaviorally inert
(bit-identity gate, §10).

Exactly-once closure — the MRN-proven pattern (resolution bit on the
DynInst, never `isSquashed()`; two squash sites):

- **Increment**: a new `notifyRenamedInst(inst)` on the base class,
  called from `rename.cc` once per renamed instruction, immediately
  **after** the consumption ladder (so a same-cycle, same-PC later
  µop's predict() sees this one — CVP's strictly-before-me scan
  semantics — while the instruction's own predict() does not count
  itself). Base behavior: `renamedCount[tid]++` unconditionally —
  this **supersedes and deletes the unwired `notifyRenamed(tid)`**
  and finally feeds the burst guard — then, if in scope and counting
  is on: `count[key]++` and set a new DynInst flag
  `VpInflightCounted`.
- **Decrement at commit**: in `BaseValuePredictor::train()`,
  **before** the in-scope check (flag ⇒ counted ⇒ always reclaim,
  independent of any future scope dynamics): if the flag is set,
  `count[key]--` and clear it. (EVES trains at commit only, so this
  fires exactly once per committed counted instruction.)
- **Decrement at squash**: a new flag-guarded
  `notifySquashedInFlight(inst)` called from the two proven walk
  sites — `ROB::doSquash()` and `CPU::squashInstIt()` — adjacent to
  (not inside) the existing `vpPredicted && !vpResolved` block, since
  this population is all counted instructions, predicted or not.

Robustness: `panic_if` on decrement-underflow (always on, cheap);
stats identity `inflightIncrements == inflightDecTrain +
inflightDecSquash (± in-flight epsilon at dump; never negative)`;
drift exercised by the squash-storm microbench (§10). One accepted
transient: ROB squash walks are width-bounded per cycle, so a
refetched same-PC instruction can rename and read the counter before
all doomed older instances have been walked — a brief
over-extrapolation window; the closure identity still holds, and the
microbench asserts the final-zero/identity, not point-in-time
exactness. GTest coverage
for the map (increment/decrement/erase-on-zero/key folding) plus a
pipeline-free simulation of interleaved rename/commit/squash
sequences asserting the zero-sum invariant.

Population notes: MRN-claimed loads never call `predict()` but do
train — the rename-site hook is unconditional on the ladder outcome,
so the closure holds in MRN compositions and under `vpBeforeMrn`.
Same-PC instructions share eligibility/scope, so the counted
population is exactly the population that will advance `lastValue`
at commit — the quantity the extrapolation needs.

## 5. Arbitration and token (ratified: verbatim clobber + ablation)

Source mechanism (cc:136-144, 44-57): `getPredStride` runs first;
`getPredVtage` runs second and **assigns `predicted_value` gated only
on {blackout inactive, tag hit, value-pointer materialized} — not on
VTAGE confidence** (confidence only sets the `predvtage` flag). A
high-confidence stride value is silently overwritten by a
low-confidence VTAGE value; the composed prediction is still used
(return `predstride || predvtage`); no state records who supplied the
value; every update rule keys off the two flags.

Port mapping: our E-VTAGE stores a full 64-bit value per entry (the
LDATA hash/pointer indirection was a declared E-VTAGE porting
deviation), so "pointer materialized" has no equivalent — every
tag-hit entry has a retrievable value. **Verbatim mode therefore maps
the overwrite predicate to "VTAGE tag hit && blackout inactive"** —
strictly broader than CVP's population (which excludes
never-materialized entries). The ablation
`vtageOverwriteRequiresConfidence = true` gates the overwrite on the
confident flag — narrower than CVP's in the common case, but **not a
strict subset**: CVP materialization is attempted only at
conf >= MAXCONFID−1, must win a 1/4 draw and find a free value slot,
and is torn down on every mismatch (cc:554, 579, 584-597, 628), so a
confident-but-unmaterialized entry is overwritten by the ablation but
not by CVP. The two modes bracket CVP's population only
approximately; the overwrite stats (§9) plus the probe A/B quantify
the gap, and the §11 verdict is interpreted with that caveat.
Declared deviation.

Arbitration is specified as a **pure helper function** (POD inputs:
the stride lookup, the `EVtageLookup`, blackout state, the ablation
flag → the composed decision + flag bits), so §10 can GTest every
flag combination directly. `EvesVP::predictImpl` outline:

    strideSide = strideTable.lookup(key,     // hit, conf, extrapolated
                     inflightCount(key))     // value -- EvesVP passes
                                             // the framework's count
                                             // in; the core computes
                                             // the value only on a
                                             // gate-passing hit
    stridePredicted = strideSide.predicted   // hit && SafeStride >= 0
                                             // && conf >= 7   (§3.2)
    r = evtage.lookup(pc, upc, hist)         // second, as in source
    blackout = burstGuardWindow > 0
               && (renamedInsts(tid) - lastWrongMark[tid])
                  < burstGuardWindow
    overwrite = r.hit && !blackout
                && (!vtageOverwriteRequiresConfidence || r.confident)
    predvtage = r.confident && !blackout
    // Delivery is expressed ONLY through the engaged optional of
    // VpPredictResult -- there is no separate confident channel.
    // CVP's use-bit is predstride || predvtage; predvtage implies
    // r.hit and hence overwrite in both modes, so the rule is:
    deliver = stridePredicted || predvtage
    result.value = deliver ? (overwrite ? r.value : strideSide.value)
                           : nullopt

(A verbatim-mode tag hit with neither flag set delivers nothing — the
overwrite selects the payload only when something is delivered; this
preserves the flag-keyed quirk of a `stridePredicted` delivery
carrying a low-confidence VTAGE value. Blackout suppresses the whole
VTAGE contribution — value and flag — as in the source, where
`if (LastMispVT >= 128)` at cc:44 wraps both the `predicted_value`
assignment and the `predvtage` computation, cc:44-55. The predecessor
E-VTAGE spec's §6 parenthetical describing CVP as suppressing only
the flag is incorrect on this point — unobservable in Stage 1, where
nothing else could supply a value; an erratum note is added there.
With the default `burstGuardWindow = 0` the blackout is never active,
the chapter-iso configuration.)

Token: the `EVtageTables` token in the low bits (stripped before any
call into `EVtageTables`), plus three high flag bits:
`stridePredicted`, `vtageConfident` (CVP's predvtage), and
`deliveredByVtage` (set when the composed result carried a value and
the overwrite supplied it — stamped at predict time; the verify-wrong
site's firing condition supplies the "was actually consumed"
predicate). The first two are CVP's flags; the third is **gem5-only
routing state** CVP does not have — required because our framework,
unlike CVP, must act at the verify site (§6), and has no other way to
know which table to punish. Declared deviation (it adds information
CVP's update rules never consult; CVP's own rules below still key off
the two CVP flags only). The default-geometry `EVtageTables` token
occupies 37 bits; an `EvesVP`-constructor `fatal_if` requires the
packed-token width computed from the params to stay <= 61 bits so the
three flag bits can never collide with a large-table configuration.

## 6. Verify/train routing

Verify site, delivered-and-WRONG (`correctiveResetImpl(token)`; the
wrong instruction squashes inclusively and never commits):

- SafeStride −1024 iff `stridePredicted` (source-exact — including
  when VTAGE supplied the wrong value; the flag-keyed quirk).
- `lastWrongMark = renamedInsts(tid)` for **all** threads iff
  `vtageConfident` (CVP's `LastMispVT = 0`; feeds blackout + burst
  guard) — `correctiveReset(uint64_t)` carries no ThreadID, so EVES
  adopts EVtageVP's documented all-threads-reset simplification
  verbatim (evtage.hh's lastWrongMark comment; harmless
  single-threaded).
- `EVtageTables::correctivePunish` iff `deliveredByVtage` — the
  established no-livelock exception, now correctly scoped: when the
  stride supplied the value, the VTAGE entry is left alone (its own
  table-local training at the re-executed twin's commit handles it,
  as in CVP), and `correctiveResetImpl` **returns true** in that arm
  (no staleness question was asked — returning false would pollute
  the base's correctiveResetStale stat). When `deliveredByVtage`, it
  returns `correctivePunish`'s own live/stale verdict, as E-VTAGE
  does. **The stride table gets no verify-site punish at all**:
  CVP has no such concept — a transiently-wrong stride prediction
  whose one-step sequence is intact stays confident (faithful), and
  livelock is impossible because SafeStride slams the global gate
  shut after one or two −1024 events.

Verify site, delivered-and-correct: nothing E-Stride-specific (the
+4/+8 credit is deferred to commit-train, §3.5).

Commit-train (`trainImpl`): VTAGE train (existing, token low bits,
classifier unchanged) then stride train (§3.3) then SafeStride tick
and credit (§3.5). `classifier.deliveredCorrect` is CVP's
`prediction_result == 1` at this site (a wrong-delivered instance
never commits; its refetched twin commits unpredicted with
deliveredCorrect false — mapping verified against CVP's
`(prediction_result == 1)`, where "unknown" also counts false).

Inclusive squash, doomed-window handling, history
snapshot/restore: all untouched — EVES inherits E-VTAGE's wiring via
`usesHistory()`/`trainsAtCommit()`.

## 7. Eligibility and scope

Base eligibility rules unchanged. Both scopes are evaluated
(`eves` = loads-only, `eves_all` = all eligible), mirroring the
evtage arms. In loads-only scope the stride table sees loads only
(train() is a scope no-op) and the SafeStride tick population shrinks
accordingly — the misprediction-ratio semantics are preserved within
the scope. CVP's own "predict only loads" experiment (paper §4) cost
1.3–2.7%, so `eves_all` is expected to be the headline arm.

## 8. Files and build

- `src/cpu/o3/vp/estride_table.{hh,cc}` + `estride_table.test.cc`
  (`GTest` in SConscript).
- `src/cpu/o3/vp/eves.{hh,cc}` (`EvesVP`).
- `src/cpu/o3/vp/ValuePredictor.py`: `class EvesVP(BaseValuePredictor)`
  (duplicated E-VTAGE params + `vtageOverwriteRequiresConfidence`);
  SConscript `sim_objects` update.
- `src/cpu/o3/vp/base.{hh,cc}`: `usesInflightCounts()` knob, counter
  map + accessor, `notifyRenamedInst()` (deleting `notifyRenamed()`),
  `notifySquashedInFlight()`, train-site decrement, new stats.
- `src/cpu/o3/dyn_inst.hh`: `VpInflightCounted` flag (+ accessors).
- `src/cpu/o3/rename.cc`: one `notifyRenamedInst` call after the
  consumption ladder (null-guarded).
- `src/cpu/o3/rob.cc`, `src/cpu/o3/cpu.cc`: one flag-guarded
  `notifySquashedInFlight` call each, beside the existing VP squash
  notification.
- `configs/garfield/arm/sim_opts.py`: `eves` choice + the two new
  flags (§2).
- `EVtageVP` (evtage.{hh,cc}) and `EVtageTables` algorithmically
  untouched; **comment-only edits to the frozen files are permitted**
  (comments are not algorithm or params): once `notifyRenamedInst` is
  wired, evtage.cc's fatal_if rationale ("no pipeline stage feeds
  yet") and evtage.hh's "never fed by any pipeline call site" +
  dangling `notifyRenamed()` reference become factually wrong and are
  rewritten to state the real reason the fatal_if survives — E-VTAGE's
  guard stays locked off, EVES's own guard param is the live one. The
  `fatal_if` itself stays.

Implementation phasing (for the plan): the natural seam is (1) the §4
framework counter facility + `notifyRenamedInst` supersession —
independently landable, inert for every existing predictor, with its
own bit-identity gate; then (2) the params-free `EStrideTable` +
GTests; then (3) the `EvesVP` composition, config plumbing,
microbench, and evaluation.

## 9. Statistics (EvesVP + framework)

Stride side: lookups/hits; predictions issued (post-arbitration
stride-supplied vs VTAGE-supplied); `strideOverwrittenByVtage` and
`strideOverwrittenLowConf` (the ratified clobber counters — total
overwrites of a confident stride value, and the subset where VTAGE
was below confidence); safeStrideBlocked (predict-gate rejections
while negative); safeStrideNegEpisodes (>=0 → <0 transitions);
conf-gate fired/suppressed; stride mispredict-decay vs collapse arms;
sentinel demotions; allocations by class arm; victim pass-1/pass-2
claims; aging decrements; inflight histogram-ish scalars (sum +
max observed at predict — enough for the report without a full
histogram). **Per-supplier outcomes** (what §11's supply split
actually needs — the base's predictionsCorrect/Wrong are
supplier-blind): deliveredCorrectByStride / deliveredCorrectByVtage
at commit-train (token flags × `classifier.deliveredCorrect`) and
deliveredWrongByStride / deliveredWrongByVtage at the verify-wrong
site (token flags). Blackout observability (live once
`burstGuardWindow > 0`): blackoutSuppressed (VTAGE contributions
suppressed) and wrongMarkResets — without these the §10 128-ablation
smoke has nothing to assert. Framework: inflightIncrements /
inflightDecTrain / inflightDecSquash (§4 identity). Base-class stats
flow unchanged.

## 10. Testing

- **GTests** (`estride_table.test.cc`, deterministic injected RNG):
  every §3 arm pinned — gate order (SafeStride blocks before conf);
  threshold endpoints (conf 6 vs 7); extrapolation arithmetic incl.
  negative strides and inflight > 0; the asymmetric range window
  (delta = −2^19, −2^19+1, +2^19, +2^19+1, and huge-delta rejection
  near ±2^63 pinning the overflow-free §3.3 semantics); out-of-range
  delta on a **trained** entry (routes down the one-step-mismatch
  arm); virgin-table behavior (zero-init, no valid bit: a tag-0 hash
  hits and trains via the first-occurrence arm, never allocates;
  SafeStride starts at 0 and predicts from cycle one); sentinel
  lifecycle (the 2-cycle constant-value demotion loop); mispredict −4
  vs conf==4 collapse (u untouched vs zeroed); notFirstOcc lifecycle;
  draw-count structure (1/2/4 draws by signed stride regime —
  counting consumed RNG draws; negative-stride exclusion; zero draws
  at counter saturation; the deterministic conjunct short-circuiting
  ahead of all draws); unit-stride load throttles; the deterministic
  `!deliveredCorrect || stridePredicted` conjunct; allocation ladder
  per class; victim pass order, conf=1 install, and aging odds by
  conf band; u 0..3 invariant; SafeStride arithmetic (pre-check
  overshoot to 32774, −1024 stacking below zero, gate at exactly 0
  and −1).
- **Arbitration and routing**: the pure arbitration helper (§5)
  GTest-covered over the full flag/mode cross product — {stride
  hit/miss/confident} × {VTAGE miss/hit-low-conf/hit-confident} ×
  {blackout on/off} × {ablation on/off} — pinning payload selection,
  delivery, and the three token bits (in particular: verbatim-mode
  low-conf clobber of a confident stride; no delivery on a
  flag-less tag hit). Directed stat-asserting smoke checks pin the
  §6 routing: a VTAGE-supplied wrong must show SafeStride penalty +
  a correctivePunish; a stride-supplied wrong must show the penalty
  + **zero** correctivePunish calls + no correctiveResetStale
  pollution.
- **Inflight counter**: map-level GTests + interleaved
  rename/commit/squash zero-sum sequences (§4).
- **Bit-identity gates**: `lvp`, `vtage`, `evtage`, `evtage_all`,
  and one MRN-enabled config (discharging §0's must-not-break)
  before/after every EVES commit. Gate definition: all
  **pre-existing stats value-identical; new counters present and
  zero** (the new base stats register unconditionally, so byte-equal
  stats.txt is not the criterion). The new hooks must be inert for
  `usesInflightCounts() == false` predictors; `renamedCount` going
  live cannot influence any emitted stat or emission decision at
  `burstGuardWindow == 0` (burstGuardSuppresses() is constant-false,
  and E-VTAGE's window is additionally fatal_if-locked to 0).
- **Smoke matrix**: existing microbenches + new `vpstride`
  (gem5-infra): a tight loop of long-latency strided loads whose
  occurrences overlap deeply — asserts inflight-compensated
  predictions fire (stat check) and IPC improves; a hostile variant
  with frequent branch mispredicts storms the squash walks and
  asserts the §4 identity and final-zero counters.
- **Ablation smoke**: `vtageOverwriteRequiresConfidence` both ways;
  `burstGuardWindow` 0 vs 128 boots.

## 11. Evaluation plan

Probe 16 checkpoints: `eves` and `eves_all` vs the existing
`evtage`/`evtage_all` results (dense-64 both sides), plus one
`eves_all` arm with `vtageOverwriteRequiresConfidence` — three new
arms. Promote to 190 unless clearly negative (the probe rule the
chapter has used throughout). Report: EVES vs E-VTAGE with the
committed-instruction coverage counters (commit-site
`committedVpPredicted` needs no change), stride-vs-VTAGE supply
split, the overwrite-quirk A/B verdict, and the ~0.64KB stride
storage note against its speedup contribution.

## 12. Ratified forks and declared deviations (consolidated)

Forks (user-ratified): per-PC inflight counter table (replacing the
ring scan); SafeStride +1 tick at commit-train; verbatim 48-entry
geometry; arbitration = verbatim overwrite default + ablation param +
overwrite stats [amended 2026-08-15, user-ratified: the default is
now the confidence-gated mode — the 190-checkpoint A/B winner by
+3.6% — and the verbatim overwrite is the opt-in ablation].

Declared deviations from the CVP source, each isolated and testable:
(1) inflight = exact counter, not ring scan (removes stale-slot and
wrap hazards; CVP's own number is approximate); (2) SafeStride tick
and +4/+8 credit fire at commit rather than at result-reveal
(wrong-path excluded; few-cycle gate lag); (3) verbatim-overwrite
predicate maps CVP's "pointer materialized" to "any tag hit" because
our E-VTAGE entries store full values (strictly broader; the ablation
flag is narrower but not a strict subset of CVP's population — the
bracket is approximate, §5); (4) the `deliveredByVtage` token bit
exists only to scope the gem5-specific verify-site punish; (5) draws
probability-equivalent rather than bitstream-identical; (6) stride
hashes fold (PC, µPC) via vpKey rather than pc+piece; (7) the
source's dead tag-hash clamp is dropped with a comment; (8) the
stride range window is the overflow-free interval
delta ∈ [−2^19+1, +2^19], not the source's UB-prone
`abs(2*delta − 1)` expression (the lowVal precedent, §3.3); (9) the
default `burstGuardWindow = 0` disables the source's always-on
128-instruction post-misprediction VTAGE blackout (chapter-iso
choice; 128 restores CVP behavior as an ablation). Everything else —
including the abs-of-boolean positive-only stride boosts, the
asymmetric range window, the 0xffff sentinel, the global SafeStride
with its pre-check cap overshoot, and the flag-keyed SafeStride
credit/penalty even when VTAGE supplied the value — is implemented
as written.
