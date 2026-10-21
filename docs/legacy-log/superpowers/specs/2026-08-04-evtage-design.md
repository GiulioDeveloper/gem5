# E-VTAGE on the Garfield VP Framework: Design (EVES Stage 1)

- **Date:** 2026-08-04 · **Branch:** `vp` · **Status:** forks ratified
  (policy-essence scope; exact CVP-1 rates; burst guard param default
  off); revised after a three-lens adversarial review — every rate
  formula below is a verbatim K32 transcription (checked against the
  submission source, not paraphrased), and the verify/commit split of
  CVP's single commit-site mispredict work is now fully specified;
  staged plan: E-VTAGE first vs plain VTAGE, E-Stride later
- **Normative sources:** the EVES paper (Seznec, CVP-1 2018) and the
  actual CVP-1 submission source
  (`microarch.org/cvp1/code/Seznec.tar.gz`, `mypredictor.{h,cc}`,
  byte-identical across budget tracks) — all rate formulas below are
  transcribed from that code (K32 variant unless noted)
- **Baseline:** the committed VTAGE
  (`docs/superpowers/specs/2026-08-03-vtage-design.md`); everything
  not stated here is inherited unchanged

## Goal and the Hypothesis Under Test

Seznec's own ablation is the sharpest fact in the EVES paper:
replacing the differentiated per-class confidence/allocation
probabilities with flat 1/32 rates drops 32KB EVES from 4.202 to
3.710 IPC — *the policy is the predictor*. Stage 1 therefore tests
the policy at fixed storage: **same table geometry as our committed
VTAGE (8K base + 6×1K tagged, histories per the then-current
default), E-VTAGE's update policy on top.** `e_vtage` vs `vtage` is
an **iso-storage-geometry A/B of the update policy plus the base
organization** — not policy-only: §5's base is tagged and 2-way
skewed, so a base tag miss yields no prediction where plain VTAGE's
tagless VT0 always provided, and 2×4096 skewed aliasing differs from
8192 direct-mapped. The probe report must state this confound
explicitly; if Stage 1 reads out ambiguously, a tagless-base E-VTAGE
ablation knob is the clean pure-policy isolate (follow-up, not built
now). Storage-layout elements of E-VTAGE that exist to fit
championship area budgets — compressed hash-then-pointer values,
banked/interleaved arrays, 47/49-bank counts — are deliberately out
of scope (declared deviation; our comparison is iso-geometry, not
iso-area, and the report must say so).

## Policy Changes vs Plain VTAGE

### 1. Per-Class Probabilistic Confidence Increment (replaces FPC)

Plain VTAGE gates `c++` by the transition-indexed FPC vector. E-VTAGE
gates it by *instruction class, value class, serve level, and
provider*, per the CVP-1 code (`vtageupdateconf`, K32): single-trial
probability `1/2^E` with

```
E = LOWVAL + NOTLLCMISS + 2*FASTINST + NOTL2MISS + NOTL1MISS
    + ((INSTTYPE != load) || NOTL1MISS)
LOWVAL = (|2*value+1| < 2^16) + (value == 0)     // 0 large, 1 small, 2 zero
```

For loads the bracket collapses to `NOTL1MISS`, so the effective load
exponent is `LOWVAL + NOTLLCMISS + NOTL2MISS + 2*NOTL1MISS +
2*FASTINST`; for non-loads the bracket is constant 1 (an additive
+1). K32 doubling rule: when the provider is rank 1 (VT0 — either
way; `HitBank <= 1` in the code), take the OR of two independent
trials. Worked endpoints (loads): correct DRAM-miss large-value →
p = 1 (mask 0, deterministic); 1-cycle small-value L1 hit → 1/128.
Non-loads carry the constant +1; 1-cycle ALU zero-results bottom out
at 1/256.

**Class dispatch (transcribed):** the six classes
alu/fp/slowAlu/undef/load/store draw the probability above;
`uncondIndirectBranchInstClass` returns **deterministic true** — in
this gate and equally in §3's allocation gate and §4's u gate; every
other class returns false (no increment, no allocation — effectively
never predicted). Our mapping: eligible indirect calls
(`isIndirectCtrl() && isCall()` — BLR's link-register destination)
take the always-true arms; direct calls (BL) and conditional branches
take the false arms (as CVP does); eligible instructions fitting none
of load/store/alu/slowAlu/fp map to the undef arms (alu-like
everywhere except §4's alu-specific `E_u` term, which is alu-only).

**Latency-classifier mapping (declared adaptation):** the CVP code
classifies by measured `actual_latency` thresholds (<150/<60/<12/==1
cycles). We map from state we already carry: loads by `MemSrcLevel`
(`mem` → DRAM class; `l2` → L2-class; `l1d` → L1-class; `stlf` →
fast-L1 class ⇒ FASTINST) — our 3-level hierarchy has no distinct
LLC row, so the LLC-hit class is unreachable (E skips from L2 to
DRAM); non-loads by `OpClass` (`IntAlu` → FASTINST; multiply/divide/
FP classes → slow-ALU class: FASTINST false, all NOT*MISS terms
true). Every exponent term is computed in one small classifier helper
so a future latency-measured variant is a drop-in.

**Operand-count mapping (declared adaptation):** CVP's `NbOperand`
counts valid source registers (up to 3). We define it as the count of
**integer non-flag source registers** — naive `numSrcRegs()` on
aarch64 counts condition-code/flag and predication sources, which
would push flag-consuming ALU ops past the ≥2 gate and make
`NbOperand == 0` (immediate-form moves) nearly unreachable. One
quantity, computed in the classifier helper, feeds all three
consumers: §3's outer allocation gate, §4's `E_u` term, and §3's
zero-operand-ALU seed rule.

### 2. Misprediction Rule (replaces unconditional reset)

Both arms verbatim (`UpdateVtagePred` mispredict branch); the arm
test is `c == 7` exactly — saturation, not "high confidence" relative
to the threshold:

```
wrong, c == 7:  c -= 2 (→ 5);  u = 1
wrong, c <  7:  c = 0;         u = 0
```

The `u = 1` on the saturated arm is deliberate (code:
`u = (conf == MAXCONFID)`, evaluated before the decrement): a
just-punished once-hot entry is shielded from allocation steals
(which require `u == 0`) until TICK ages it.

**Value overwrite (declared change vs inherited VTAGE):** on every
wrong commit-train outcome the provider's stored value is overwritten
with the actual value **unconditionally** (CVP: `hashpt = HashData`
is the first line of the mispredict branch, before any confidence
test). Plain VTAGE's inherited overwrite-only-at-`c == 0` rule does
not apply to E-VTAGE. The verify-site punish still writes no value
(framework contract: a bare confidence write is the only table write
that can never create a prediction).

**One punish per misprediction (the verify/commit split):** CVP does
all mispredict work at its single commit-validation site: confidence
punish + value overwrite + MedConf-forced allocation. Our framework
splits it. The **verify-site `correctivePunish`** (through the token,
tag-checked) applies the confidence/u rule above and sets the entry's
pending bits — `punishApplied` always, plus `medConfPending` when the
*pre-punish* state qualified as MedConf (§3). The refetched
instance's **committed train** of a punish-marked entry performs only
the commit-time remainder — the unconditional value overwrite and the
allocation probe (deterministic body if `medConfPending`) — and does
**not** re-apply the confidence rule. Endpoint of a delivered-wrong
lifecycle on a saturated entry: `c = 5, u = 1`, value corrected —
CVP's exact commit endpoint (GTest-pinned). A commit-train wrong on
an entry with no pending mark (an undelivered prediction) applies the
full rule at the train site directly: punish arms, overwrite, MedConf
evaluated from current state, allocation.

**No-livelock bound (stated exactly; parameter-dependent):** at the
default `confThreshold` 7 (and at 6), a punished entry sits at 5 or
0 — below threshold — so a delivered-wrong instruction is never
immediately re-armed; its refetched instance cannot re-predict until
confidence rebuilds. At thresholds ≤ 5, a saturated entry punished
7 → 5 stays deliverable and re-delivers the stale value **at most
once**: the second punish takes the else arm (5 ≠ 7 → c = 0 < 1 ≤
threshold) and disarms it. Bounded double-delivery, not livelock; in
both cases the corrective punish remains the last table write before
the refetched instance re-renames.

### 3. Allocation Policy (probabilistic, MedConf-triggered)

Attempted on a wrong training outcome when no correct prediction was
delivered for this instruction (CVP: `!prediction_result &&
ShouldWeAllocate`; in Stage 1's single-component predictor that is
every wrong commit-train outcome). A rank-0 (no-provider) train
performs no provider update and proceeds straight to this gate. Two
multiplied stages, per `VtageAllocateOrNot` (K32):

- **Outer operand gate — alu/store/undef only** (the code's C
  fallthrough-into-if: if this gate's draw fails, the body never
  runs): `NbOperand >= 2` → 1/16; `NbOperand < 2` → 1/64.
  fp/slowAlu/load skip the gate entirely; indirect calls are
  deterministic true overall (§1 dispatch).
- **Body (verbatim K32):**

```
E' = ((INSTTYPE != load) || NOTL1MISS) * LOWVAL
     + NOTLLCMISS + NOTL2MISS + NOTL1MISS + 2*FASTINST
mask = (2 << E') - 1        // fires when (random() & mask) == 0,
                            // i.e. p = 1/2^(E'+1)
```

**E' is NOT §1's E.** The load/L1 bracket here **multiplies LOWVAL**
(a load that missed L1 loses the value-class term entirely),
`NOTL1MISS` appears once (no load-side doubling), and non-loads carry
no additive +1. Worked endpoints: DRAM-miss load, any value class →
E' = 0 → p = 1/2 (contrast §1's increment p = 1 for the large-value
case); 1-cycle small-value L1-hit load → E' = 6 → p = 1/128.

- **MedConf override (scoped precisely):** MedConf — the
  mispredicting entry had built-up confidence, read from the
  **pre-punish** state: `(c > 3) || (c == 3 && u == 3) ||
  (0 < c < 3)` — makes the **body** deterministic (K32: `|| MedConf`
  replaces the dice). alu/store/undef still pay the outer operand
  gate first, so their MedConf allocation rate is 1/16 or 1/64; only
  fp/slowAlu/load (and indirect calls) get a truly deterministic
  MedConf allocation.

**Landing rule, both arms** (`UpdateVtagePred`; ranks: 0 = none, 1 =
VT0, 2..7 = VT1..VT6; scans use this instruction's per-component
indices):

- **Provider exists (rank r ≥ 1, base or tagged):** `DEP = r + 1`,
  +1 with probability 1/8. (This subsumes CVP's `HitBank == 0 →
  DEP++` way-0 adjustment: either base way is rank 1 → DEP = 2.)
  Scan ranks DEP..7 in order for the first entry with `u == 0 &&
  (c == 3 || c <= (random() & 7))` — "slightly favors the entries
  with real confidence" — and steal it: `{val = actual, c = 3, tag
  written}` (`u` stays 0, the steal precondition; pending bits
  cleared). **No seed-to-7 special case in this arm.**
- **No provider (rank-0 token):** with probability **7/8**, allocate
  into the **base**: draw way `w = random() & 1` and scan the two VT0
  ways in order `(w, 1−w)` with the same steal rule, seeding `c = 3`
  and writing the way's 12-bit tag — **except zero-operand ALU
  (`NbOperand == 0 && alu`), which seeds `c = 7`; this special case
  exists only in this base-way arm.** With probability 1/8, `DEP = 2`
  (+1 with probability 1/8) and scan the tagged ranks as above. The
  base-way arm is the dominant no-hit outcome — it is what populates
  the tagged base from empty.
- **Bookkeeping:** each scanned-but-not-stolen entry increments `NA`;
  a successful steal increments `ALL` (at most one; the scan breaks
  on the first steal). Allocation seeding — either arm — initializes
  both pending bits to 0 on the stolen entry.

**Pending-bit lifecycle (`punishApplied`, `medConfPending` — the
deferral adaptation, declared):** set only by the verify-site
corrective punish (tag-checked; a stale token sets nothing). Cleared
by the **next train on the entry**: a wrong outcome consumes them
(skip the confidence rule per §2; deterministic allocation body if
`medConfPending`); a correct outcome drops them — matching CVP's
one-event semantics, no memory across events. Allocation seeding
clears both bits, so a bit set before an in-flight steal can never
leak to the way's new owner; if the entry was reallocated between
punish and train, the train's tag check fails, the recompute trains a
different entry, and the stale bits are treated as absent (seeding
already cleared them).

### 4. Usefulness and Aging (2-bit u + TICK)

`u` widens to 2 bits (max 3). On misprediction, §2's arms set it:
`u = 1` on the saturated (−2) arm, `u = 0` on the reset arm. On a
correct provider train, the call site verbatim:

```
if (u < 3)
  if (UPDATEU || (c == 7))      // deterministic when saturated
    u++;

UPDATEU = (!delivered_correct)
          && ((random() & ((1 << E_u) - 1)) == 0)
E_u = LOWVAL + 2*NOTL1MISS + (INSTTYPE != load) + FASTINST
      + 2*(INSTTYPE == alu)*(NbOperand < 2)
```

`u` rises **deterministically** whenever confidence is already
saturated — at threshold 7 this is the only u path for
delivered-correct predictions. The probabilistic arm is *exploration
credit*: it fires only when this instruction's prediction was NOT
delivered-and-scored-correct (CVP `!prediction_result`; Stage-1
meaning: the `deliveredCorrect` flag carried to the commit-train
site, §Framework API Changes) — i.e. it rewards a correct entry that
sat below threshold or was suppressed. `E_u` is a third distinct
exponent (neither §1's E nor §3's E'). Global `TICK += NA − 5*ALL`
(clamped ≥ 0) after every allocation attempt; at `TICK >= 1024`,
decrement every entry's nonzero `u` — all components, base ways
included — and reset TICK. This smooth aging pass replaces plain
VTAGE's aging-on-failed-allocation only.

### 5. Tagged, 2-Way Skewed Base Component

VT0 gains partial tags (12 bits, matching the tagged components' base
width) and 2-way skewed associativity (two hash functions over the
µop-distinguished PC; the skewing functions mirror gem5 TAGE's `F()`
idiom with distinct bank constants). Geometry stays 8192 entries
total (2 × 4096-entry ways). Base entries are full policy
participants: `{val, c (3b), tag (12b), u (2b), punishApplied,
medConfPending}` — subject to §3's steal rule (that is how VT0
populates from empty, via the 7/8 base-way landing arm), §4's u
lifecycle, and the TICK pass.

**Token identity:** rank-1 tokens carry `{way, index, tag}` exactly
like tagged-rank tokens, and both the verify-site corrective punish
and the commit train **tag-check rank-1 tokens like any tagged rank**
(stale → counted, no mutation; train falls back to the recompute).
A base way is now reallocatable, so plain VTAGE's index-only base
token is no longer sound. Packing: 1 way bit + 12-bit per-way index +
12-bit tag fits the existing 64-bit token carrier (construction-time
asserts, per the parent spec).

**No provider is now a legal lookup outcome:** a VT0 tag miss with no
tagged hit yields no prediction (plain VTAGE's tagless VT0 always
provided); the token is the biased rank-0/none encoding, and training
with it skips the provider update and goes straight to §3's
allocation gate. The peek/stats contract changes accordingly
(§Framework API Changes, §Statistics). §1's K32 doubling keys on
provider rank 1 — either base way.

### 6. Burst-Misprediction Guard (param, default off)

`LastMispVT`: a per-thread counter incremented once per **renamed
dynamic instruction, eligible or not** — CVP increments it for every
dynamic instruction, outside its eligibility check; counting only
predict-eligible instructions would stretch the window several-fold
and break the `128 = CVP` equivalence. Reset to 0 at verify on any
delivered E-VTAGE wrong. While `LastMispVT < burstGuardWindow`,
prediction **emission** is suppressed — the lookup still runs, the
token is still stamped, provider stats count, and commit training
proceeds unchanged (CVP suppresses only `predvtage`). [Erratum
2026-08-14: that parenthetical is wrong — CVP's `if (LastMispVT >=
128)` at mypredictor.cc:44 wraps the `predicted_value` assignment
too, suppressing the whole VTAGE contribution. Unobservable in
standalone E-VTAGE, where nothing else supplies a value; it matters
in the EVES composition — see
2026-08-14-estride-design.md §5.] Declared
heuristic: the counter is deliberately not squash-restored —
wrong-path rename increments are kept and only shorten the window.
Param `burstGuardWindow` (0 = off, default 0 per the ratified fork;
128 = CVP behavior) — swept in the probe.

## What Does NOT Change

Framework contract (predict at rename, verify at writeback with
inclusive squash, train at commit, doomed-window guard, corrective
punish through the token before the squash trigger), history
subsystem and snapshots, fold arithmetic and the concatenated µop
key, eligibility/scope rules. Counting sites for inherited stats are
unchanged; the new counters and the rank-0 peek change are specified
in §Statistics and §Framework API Changes. `EVtageVP` is a new
SimObject (`--use-vp evtage`) wrapping a params-free `EVtageTables`
core (subclass-or-fork of `VtageTables` — implementer choice,
GTest-covered either way); plain `vtage` remains available unchanged
for the A/B.

## Framework API Changes

- **Classifier plumbing:** `trainImpl` gains a `VpClassifierInfo`
  argument `{instClass, memSrcLevel, nbOperand, deliveredCorrect}`,
  populated from the DynInst in `BaseValuePredictor::train()`: class
  from the StaticInst per §1's dispatch mapping; `memSrcLevel` from
  the existing load-serve-level state; `nbOperand` per §1's operand
  mapping; `deliveredCorrect` = this instance delivered a prediction
  that verified correct (from `VpPredicted`/`VpResolved`). LVP and
  plain VTAGE ignore it — behavior bit-identical (same pattern as the
  history snapshot).
- **Rank-0 peek/stat contract:** `VtageProviderPeek.rank == 0`
  becomes a legal lookup outcome for E-VTAGE ("no provider"); the
  wrapper must not index per-component vectors with `rank − 1` —
  rank 0 routes to a dedicated none bucket (§Statistics). Plain VTAGE
  still never returns rank 0.
- **Rename-count notification:** for §6, the base class gains a
  count-only per-renamed-instruction hook (no-op unless the burst
  guard is enabled) so `LastMispVT` counts every renamed instruction,
  not just eligible ones.
- **Verify-site entry:** `correctivePunish(token)` — the parent's
  corrective reset with §2's two arms plus the pending-bit set; same
  signature, tag-checked (incl. rank-1 tokens, §5).

## Randomness

All probability gates draw from the same seeded RNG stream as the
FPC machinery (deterministic runs); the GTest core takes the
injectable RNG and drives every probabilistic gate deterministically
(mask-based gates test as scripted-draw sequences).

## Configuration

| Param | Default | Provenance |
|---|---|---|
| geometry (base/tagged/histories) | inherited from VtageVP defaults | iso-geometry A/B (declared deviation from EVES storage) |
| `confBits` / threshold | 3 / 7 (saturation; ≥ 1 enforced; single-delivery invariant needs ≥ 6, see §2) | CVP code |
| mispredict punish | `c==7 → {c−=2, u=1}`; else `{c=0, u=0}` | CVP code |
| wrong-train value overwrite | unconditional | CVP code (replaces inherited `c==0`-only rule; declared) |
| `uBits` | 2 | CVP code |
| pending bits | `punishApplied` + `medConfPending` (1b each, per entry) | deferral adaptation (§2/§3) |
| `tickMax` / tick rule | 1024 / `NA − 5·ALL` | CVP code (K32) |
| base assoc / tags | 2-way skewed / 12b | CVP-derived adaptation |
| `burstGuardWindow` | 0 (off; 128 = CVP, counted per renamed instruction) | ratified fork |
| rate formulas | §1 `E`, §3 `E'`, §4 `E_u`; K32 doubling | CVP code, transcribed |
| CLI | `--use-vp evtage` (+ `--evtage-burst-guard`) | — |

## Statistics

Inherited VTAGE counters keep their sites; changes and additions:

- Per-component provider vectors (lookups, correct/wrong-by-provider)
  gain an explicit **none bucket** for rank-0 lookups and no-provider
  trains (no `rank − 1` indexing anywhere).
- The FPC fired/suppressed pair is repurposed as the per-class
  confidence-gate fired/suppressed counters.
- New: `baseTagMiss`, `noProviderLookups`/`noProviderTrains`,
  `allocScanSteps` (NA total), `allocSteals` (ALL total),
  `allocBaseWay`, `allocSeedSaturated` (zero-operand-ALU seed-to-7
  events), `tickPasses`, `pendingSet`/`pendingConsumed`/
  `pendingDropped` (correct-train drops), `burstGuardSuppressed`.

## Testing Gates

1. GTests on the E-VTAGE core: classifier truth tables for **all
   three exponents** (`E`, `E'`, `E_u`) per class/level/value/
   operand-count, incl. the divergence endpoint (DRAM-miss load:
   increment p = 1, allocation p = 1/2); K32 doubling on rank-1
   providers; punish rule both arms **incl. u** (`7 → {5, u=1}`,
   `<7 → {0, u=0}`; trigger is `c == 7` exactly); unconditional
   wrong-train value overwrite; **delivered-wrong lifecycle
   endpoint** (verify punish + deferred train = exactly one
   confidence punish; final `c = 5, u = 1`, value corrected); pending
   round-trip incl. correct-train drop, allocation-clear, and the
   reallocated-between-punish-and-train case (stale token →
   recompute; no spurious deterministic allocation for the new
   owner); landing rule both arms (rank r → DEP = r+1 tagged scan,
   seed `c = 3` only; rank 0 → 7/8 base-way scan in drawn-way-first
   order / 1/8 tagged; seed-to-7 only for zero-operand ALU in the
   base arm; base populate-from-empty); TICK bookkeeping (`NA`/`ALL`,
   the ≥ 1024 pass covering base ways); 2-bit u lifecycle
   (deterministic `c == 7` arm; `UPDATEU` gated on
   not-delivered-correct); skewed-base tag hit/miss, rank-0 token,
   and stale-base-token tag-check at both punish and train.
2. Smoke matrix with `--use-vp evtage`: inertness/ladder runs (at the
   default threshold 7, punished entries — c = 5 or 0 — never
   immediately re-arm) plus the hostile `confThreshold 1` run with
   the corrected expectation: a saturated delivered-wrong entry goes
   7 → 5, stays armed, and re-delivers the stale value **at most
   once** — the second punish takes the reset arm (5 ≠ 7 → 0 < 1) and
   disarms it. Pass criteria: run completes (bounded double-delivery
   episodes, no livelock), `predictionsWrong > 0`, the stat identity,
   and a checksum-vs-baseline match.
3. Probe A/B (16 checkpoints): `evtage` vs `vtage` at identical
   geometry; then 190 both scopes reusing all baselines. The report
   must state the tagged-base confound (§Goal): the delta is policy
   plus base organization, not policy alone.

## Stage 2 Preview (E-Stride — design later, after Stage 1 reads out)

The code brief carries everything needed: the
`LastCommitted + (Inflight+1)×Stride` formula with the 256-slot
ring-window scan, commit-only Val/Stride updates, decrement-by-4
confidence, class-gated increment with the small-stride throttle
(±1 strides pay extra dice), level-gated allocation (DRAM-miss → 1),
the hot-entry-protecting victim aging, and the global `SafeStride`
circuit breaker (+1/instruction, +4/+8 per correct, −1024 per wrong,
gate at ≥ 0). The known hard part for our pipeline is `Inflight` as
genuinely speculative state: increment at rename, decrement at
commit *and in both squash walks* under the framework's exactly-once
discipline. To be specified in its own document.

## Out of Scope

Value compression / shared value tables / banking (area-only;
iso-area claims explicitly disclaimed in any report), E-Stride
(Stage 2), per-class rates for LVP/VTAGE retrofits, EOLE-style
front-end execution, the tagless-base E-VTAGE ablation variant
(noted in §Goal as a follow-up isolate only).
