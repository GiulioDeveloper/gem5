# MRN fix ideas

Running list of candidate fixes for the memory-rename predictor, so ideas
don't get lost between sessions. Newest evidence at the bottom of each entry.

Baseline for all numbers: 10M warmup + 50M detailed, Neoverse V2 FS restore.

**CHAPTER CLOSED (2026-07-28).** The MRN configuration is finalized:
`--use-mrn --mrn-alias --mrn-conf-threshold 14`, all gates off (defaults).
Suite geomean 1.0092 over 190 checkpoints. Cost-side criticality
(flush-weighted penalization) is closed with a measured impossibility —
see `docs/research-log/MRN/2026-07-28-cost-side-criticality-closure.md`
and the two prior reports there. The open avenue (benefit-side
schedule-criticality) is a new project, not an MRN tuning item. Do not
reopen the entries below without that research-log context.

**Fleet status (190-checkpoint sweep, current branch = 1a + alias gate):**
geomean speedup **1.0001**, mean coverage 6.22%, verified accuracy 92.0%.
61/190 checkpoints beat 1.0; spread 0.928-1.358. This is up from **0.985**
pre-1a -- 1a took MRN from a 1.5% net TAX to break-even. Results in
`runs/mrn_sweep_1a/` (`summary.csv`, `aggregate.py`). MRN is no longer a
loss, but not yet a win; the bar for any change is "does it move the geomean
above 1.0", and forwarding accurate values only helps when the loads are
latency-critical (see cppcheck: 14% cov, 98% acc, still 0.985).

---

## 1a. Value forwarding trains optimistically (confirmed — IMPLEMENTING)

**Key idea.** `predict()` reads `valueFile[slot]` at **rename**;
`commitLoad()` trains confidence by comparing against `valueFile[slot]` at
**commit** — after the producing store has already deposited its new value.
So training validates a value file updated *since* the prediction was made.
For a changing recurrence the store always refreshes the slot before the load
commits, so training reports "match", confidence saturates, and the forward
(which used the previous iteration's value) is always wrong.

**Measured directly** (shadow probe, 50M, `trainVsSnapshot`): of every
commit-time train that reports a match, the fraction whose actual rename-time
snapshot was WRONG is **43.1% on gcc, 22.8% on sqlite**. The split tracks the
forward-accuracy split (gcc 72%, sqlite 93%). Confidence is trained on a
signal that is ~⅓ noise on gcc.

**Fix.** Train confidence on the value the prediction actually used at rename
(a per-load snapshot), not the commit-time value file. Only train on an
occurrence that had a real prior binding (an actual snapshot); a
just-bound / rebinding occurrence has no prediction to validate.

**Status: IMPLEMENTED AND VALIDATED (uncommitted).** Behind
`trainOnRenameSnapshot` (default True), `--mrn-train-commit-value` restores
the old behaviour. A/B at 10M/50M vs the committed alias-gate build (which
the commit-value control reproduces exactly):

    721.gcc_r.2.0     0.9459 -> 1.0064   (net loss -> net GAIN)
    708.sqlite_r.2.2  0.9385 -> 0.9999   (net loss -> break-even)

Mispredicts fell 95% / 91% (gcc 313,898 -> 15,426), squashed insts 95% / 92%
(gcc 33.8M -> 1.75M), verified accuracy 72->98% / 93->99%. Coverage dropped
modestly (gcc 5.78->4.37%, sqlite 24.1->20.4%) as the changing recurrences
that were mispredicting stopped forwarding -- exactly the intended effect.
**First time in the investigation MRN is not a net loss.** Two unit tests
(`ChangingRecurrence*`) pin the behaviour at the core level. Next: commit,
then re-run the 190-checkpoint sweep, which now has a real chance of a net
win.

## 1b. Independent gates for the two paths

**Structural separation: DONE.** The value and alias paths are now
independently enable/disable-able (`enableValueForwarding` /
`enableProducerAliasing` replacing the `mrnMode` enum + `unified()`), with
each gated on its own trigger in `rename.cc` and its own training gated per
path. Proven: an alias-only run (`--mrn-alias --mrn-no-value-forward`) shows
`forwardsValue == 0`, `forwardsAlias > 0` — impossible before, when aliasing
rode the value path's confidence. Default (value-only) is byte-identical bar
the now-unmaintained `bindingsLearned` (no timing effect). Priority when both
on: aliasing-first. See `docs/superpowers/specs/2026-07-21-mrn-path-separation`.

**The correlator is NOT the problem — the value delivery is.** New stat
(commit `bff5438a28`, `producerPredictCorrect/Wrong/Untrained`, scored at the
LSQ forward against the true producing store) measures the correlator's
loadPC->storePC prediction in isolation: **99.6% accurate on gcc** (357,271 of
358,614 with-binding forwards). Yet aliasing fires on only **1,702** loads — a
**200x gap**. So the storePC predictor is near-perfect; ~99.5% of correctly
predicted producers are lost DOWNSTREAM, in how the value is delivered:
  1. at the load's rename the youngest in-flight store with that PC often is
     not in the SQ yet (same-iteration producer not dispatched);
  2. when it is, the alias reads `renameMap.lookup(store's data arch reg)`,
     which is a stale physreg 99.5% of the time (the liveness bug), so the
     `aliasRequireCurrentProducer` gate correctly rejects it.

This SEPARATES what `aliasVerifyCorrect` had conflated: *which* store produced
the value (correlator: 99.6% right) vs *how* to read that store's value at the
load's rename (~99.5% lost).

**Retract: a per-binding confidence counter is the WRONG next step.** Gating a
99.6%-accurate correlator harder cannot help — the loss is not mis-prediction,
it is value delivery. (Superseded: earlier notes here proposed a confidence
counter; the isolation stat shows the correlator does not need it.)

## 1c. Fix aliasing value delivery (DONE — value-file rendezvous)

**Problem.** A correctly-named producing store's value does not reach the load.
The alias points the load's destination at `renameMap.lookup(data_arch)` — the
CURRENT mapping of the store's data arch reg at the LOAD's rename — rather than
the physreg the producing store instance actually writes. For a changing
recurrence that arch reg is redefined between the store and the load, so the
lookup is stale. Root cause proven structural: a store enters the SQ at
dispatch (`renameToIEWDelay`=2 cycles after its rename), so the
same-iteration producer is NEVER visible to `findYoungestStoreByPC` at the
load's rename — the located store is always a prior iteration's instance.

**Resolution (implemented 2026-07-25, commits `20718d20ff..428f07d488`).**
Replaced find-the-store with a rendezvous, after Tyson & Austin memory
renaming (MICRO-30 1997; tables per Reinman et al., ICS 1999 §2.3): the
store DEPOSITS its data physreg (+ value if ready) into a per-static-store
value-file cell at its own rename (in-order ⇒ always the correct instance);
the load READS the cell at its rename. Address-indexed store cache learns
loadPC→cell bindings at address resolution (program-order write guard);
loads rebind on probe mismatch, self-bind + last-value on miss; generation
tags kill dangling references to reallocated cells; confidence in the
load's SLC entry, shadow-trained below threshold. Select with
`mrnCorrelation=value_file`. Dependence distance 1 is the design point.

**Measured.** `mrnrec` (changing recurrence, the case 1c is about): IPC
0.666 → 1.496 (+125%), one alias per iteration (2.0M), zero mispredicts —
the old alias path managed 1 (one) alias total. `mrncomm`: vf_full matches
the old path (2.488). gcc 721.2.0 (10M/50M): alias-only +0.66% IPC with
44,831 aliases @95.1% (old path: 1,702 @89.5%); full model (+ producer-value
+ last-value modes) +9.35% IPC — decomposes mostly to 3.6M last-value
forwards @95.0%; per-mode made = correct+wrong+squashed identities exact.
Spec: `docs/superpowers/specs/2026-07-25-mrn-valuefile-rendezvous-design.md`.
Next: 190-checkpoint sweep; then fold the legacy value path into the model
and delete it plus the `lsq_forward` correlator.

---

## 1a-followup. Carry a generation counter, not the value (hardware cost)

**Key idea.** The committed 1a fix carries a 64-bit `_mrnSnapValue` on every
predictor-eligible integer load from rename to commit, purely to train
confidence against the rename-time prediction. Real hardware would not move a
64-bit value: give each value-file slot a small generation counter, bumped by
`commitStore` ONLY when the deposited value actually changes; snapshot the
generation (~4 bits) at rename instead of the value; at commit, same
generation => slot unchanged since rename => train on the existing commit-time
read, different => stale => reset. Logically equivalent to the snapshot
comparison (changing recurrence bumps every iteration -> never trains; stable
value never bumps -> trains), but carries ~4 bits instead of 65 and needs no
value in the pipeline.

**Why it does not change results.** Training is commit-time with no timing
effect, so this is pure state accounting -- the gcc 1.0064 / sqlite 0.9999
numbers are identical either way. Also frees a redundancy: forwarded loads
currently store the value twice (`_mrnPredVal` + `_mrnSnapValue`).

**Status:** deferred. Do before writing up the hardware overhead, not urgent
for the sweep. Quote the generation-bit cost, not the 64-bit carry.

## 2. Value-file slots are never invalidated

**Key idea.** `valueAllocate()` has no free list and no back-pointer to the
load cache, and nothing ever sets `ValueSlot::valid = false`. When a slot is
LRU-evicted and reused for a different address, any `LoadEntry` still
pointing at it keeps its saturated confidence and silently starts predicting
an unrelated address's value. With 512 value-file slots against 1024-entry
load and store tables, slot reuse is routine rather than rare.

**Candidate fix.** Add a generation counter to `ValueSlot`, recorded in
`LoadEntry` at bind time and checked in `predict()`; or scan the load cache
on reassignment and clear `le->slot` / `le->conf`.

**Status:** unmeasured. Confirmed as code behaviour by the audit, but its
real frequency is unknown — needs a `valueSlotStolen` counter before it can
be ranked against #1. Sizing argument only so far.

---

## Legacy path deleted (2026-07-26)

The value-snapshot path (MrnTables: store cache / load cache / value file,
commit-time training) and the LSQ-forward correlator (fwdCache,
tryMemRenameAlias, findYoungestStoreByPC, the staleness gate) were **deleted**
after the composition study showed zero net contribution in every corner of
the fallback-reach x threshold space (research log, Key Results 6-7). The
value-file rendezvous model is now the single mechanism; --use-mrn selects
it. Items 1a/1a-followup/1c/2 below and the "Resolved / refuted" entries
about the deleted machinery are HISTORICAL — they describe code that no
longer exists; do not re-litigate or resurrect without the research-log
context.

## Resolved / refuted — don't re-litigate

- **Producer aliasing bet on register liveness, not memory dataflow.** `rename.cc`
  aliased to `renameMap->lookup(store's data arch reg)` rather than the
  physreg the located store captured. Measured 100% correct when the two
  agree (n=155, zero errors) vs 29.9% (gcc) / 0.0% (cpython) when they
  disagree, and disagreement was 96-100% of all attempts. **Fixed** by the
  `aliasRequireCurrentProducer` gate (commit `a6f9565837`); mean speedup
  0.9458 -> 0.9602, alias mispredicts to ~zero.
- **Store/load width mismatch.** Store zero-extends `request->_size`, load
  zero-extends `effSize`, compared with a full 64-bit `==`, so a narrow load
  over a wider store can never train to a match. Real, but **refuted as a
  lead**: 276 of 14,073,122 trains on gcc and 198 of 10,775,144 on sqlite —
  **0.002%**. Not worth fixing. Instrumentation reverted.

## Unexplained observations worth keeping

- **`trainStoreMiss` is 73.8% (gcc) / 55.4% (sqlite).** Three quarters of
  committed loads find no store-cache entry for their address at all, so they
  train nothing and decay nothing. This is the dominant coverage limiter and
  nobody has looked at why — partial-overlap addressing, store-cache
  capacity, and stack traffic are all candidates.
- **`squashedInsts` is an upper bound.** The MRN mispredict path charges the
  entire younger window, double-counting branch-recovery cost. Measured
  ~108 instructions per mispredict on gcc, ~154 on sqlite; the true marginal
  cost is lower. Break-even needs roughly 99% accuracy at that multiplier.
- **Dead knobs:** `isSpGp` (hardcoded `false` at `commit.cc:1454`),
  `trainAtCommit` (declared, never read). `resetConfOnMispredict` governs
  only the commit-time value mismatch, not `MrnTables::mispredict`, which
  zeroes unconditionally — don't sweep it expecting a gentler penalty.
