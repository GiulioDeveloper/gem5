# MRN path separation: independent value-forwarding and producer-aliasing

Date: 2026-07-21
Status: approved, ready for implementation planning

## Problem

The MRN predictor has two forwarding mechanisms, but they are not
independent. In `rename.cc`, producer aliasing is only *attempted* when the
value-forwarding path is confident:

```cpp
mrnPred = memRenamePred->predict(load_pc);   // value-forwarding confidence only
if (mrnPred.valid) {                          // <-- coupling
    mrnAliased = tryMemRenameAlias(...);      // aliasing only reached here
}
```

`predict()` is pure value forwarding: a loadCache PC hit plus the
value-forwarding confidence counter. Applying the rule of thumb "would the
alias path work if the value path were disabled?" — no: with value forwarding
off, `predict()` never returns valid, the guard is never true, and aliasing
never runs. The aliasing *mechanism* is already self-contained
(`tryMemRenameAlias` uses the correlator `predictProducerPC` and the rename
map, never the value confidence); only its *trigger* is borrowed.

`mrnMode {value_only, unified}` and `unified()` conflate "is aliasing enabled"
with "keep value forwarding as the fallback", so there is no way to express
"aliasing only, no value path".

Long-term the aliasing path subsumes and replaces the value path (aliasing to
a producer physreg is a superset of forwarding a snapshotted value); value
forwarding was the easy first step. This change is the structural
precondition: make the two paths independent so aliasing can evolve (and
eventually the value path be removed) without entanglement.

## Scope

**This step is structural decoupling + config only.** Producer aliasing keeps
its *current* gating — a correlator binding (`predictProducerPC`) plus the
current-producer check (`aliasRequireCurrentProducer`). It does **not** get a
confidence counter of its own in this step; that is the next step.

## What is already separate (no change)

The two paths own disjoint data structures already:

| path | structures | trained by | read by |
|---|---|---|---|
| value forwarding | storeCache, valueFile, loadCache | `commitStore`, `commitLoad` | `predict`, `peek` |
| producer aliasing | fwdCache (correlator) | `trainForward` (LSQ forward) | `predictProducerPC` |

Only the rename trigger and the config couple them.

## Design

### 1. Config and accessors

Retire the `MrnMode` enum and the `mrnMode` param. Add two independent bools
to `MemRenamePredictor.py`:

```python
enableValueForwarding = Param.Bool(
    True,
    "Forward a snapshotted value into a high-confidence load's renamed "
    "destination (the value path). Independent of producer aliasing.",
)
enableProducerAliasing = Param.Bool(
    False,
    "Alias a load's renamed destination to an in-flight producing store's "
    "physreg when the correlator has a binding (the alias path). Independent "
    "of value forwarding; when both are enabled, aliasing takes priority.",
)
```

Defaults reproduce today's `value_only`. `mrnCorrelation` / `_useStoreSet`
stay — that selects the correlator *source*, which is aliasing-internal.

C++ (`mem_rename_predictor.hh`, `_sim.cc`):
- `_unified` → `_enableProducerAliasing`; add `_enableValueForwarding`.
- `unified()` → `aliasingEnabled()`; add `valueForwardingEnabled()`.
- ctor init: `_enableValueForwarding(p.enableValueForwarding)`,
  `_enableProducerAliasing(p.enableProducerAliasing)`.

### 2. rename.cc control flow

Replace the coupled block (`rename.cc:755-771` and the guard at `:784`) with
two independent triggers, aliasing-first:

```cpp
if (memRenamePred && inst->isLoad() && inst->numDestRegs() > 0) {
    const Addr load_pc = inst->pcState().instAddr();

    // Value path: confidence + training snapshot. Self-contained.
    if (memRenamePred->valueForwardingEnabled()) {
        mrnPred = memRenamePred->predict(load_pc);
        const MrnPrediction snap = memRenamePred->peek(load_pc);
        if (snap.valid) {
            inst->setMrnSnap(snap.value);
        }
    }
    // Alias path: its OWN trigger (a correlator binding), independent of the
    // value path's confidence.
    if (memRenamePred->aliasingEnabled()) {
        mrnAliased = tryMemRenameAlias(inst, inst->threadNumber);
    }
}

renameDestRegs(inst, inst->threadNumber);

// Aliasing-first priority: value forwards only if aliasing did not fire.
if (mrnPred.valid && !mrnAliased) {
    /* forward the value snapshot (unchanged body) */
}
```

`tryMemRenameAlias` drops its internal `unified()` check at `:1236` — the
enable is now the caller's `aliasingEnabled()` guard.

Priority is **aliasing-first, value fallback**: this matches today's order
(the current code tries aliasing first within the value-confident set) and the
long-term direction where aliasing is primary and the value path vestigial.

### 3. Per-path training gating (full independence)

So a disabled path stops maintaining its tables, not just its trigger:

- `commitStore` (value file deposit) — gate on `valueForwardingEnabled()` at
  `lsq_unit.cc:890`.
- `commitLoad` (loadCache bind + value confidence train) — gate on
  `valueForwardingEnabled()` at `commit.cc:1452`.
- `trainForward` (correlator upkeep) — gate on `aliasingEnabled()` at
  `lsq_unit.cc:1588`. Update the comment at `:1586` (which currently says the
  binding is "learned regardless of mrnMode") to reflect that it is now gated
  on aliasing being enabled.

This is what makes each path truly self-contained: disabling one leaves the
other's behavior *and training* completely unchanged.

### 4. Other `unified()` / `mrnMode` sites

- `iew.cc:1436` `memRenamePred->unified()` (producer-writeback alias verify) →
  `aliasingEnabled()`.
- `mem_rename_predictor_sim.cc:18` `_unified(p.mrnMode == enums::unified)` →
  the two new bool inits.

### 5. CLI / callers

`configs/garfield/arm/sim_opts.py`: replace `--mrn-mode {value-only, unified}`
with two flags whose defaults reproduce today's value-only:

- `--mrn-no-value-forward` → `enableValueForwarding=False`
- `--mrn-alias` → `enableProducerAliasing=True`

Update the `MemRenamePredictor(...)` construction in `make_mrn` accordingly
(drop `mrnMode=`, add the two bools). The gitignored `runs/` sweep scripts
that pass `--mrn-mode unified` will need `--mrn-alias` instead; flag this in
the report, do not chase throwaway scripts.

## Verification

1. **Default config is byte-identical.** Regenerate `config.ini` on a
   checkpoint with the default (value-only) flags and diff against the
   pre-refactor build; only `--outdir`-dependent lines may differ. Run the 7
   MRN unit tests.
2. **Independence proof** (the point of the change): a short run with
   `--mrn-alias --mrn-no-value-forward` must show `forwardsValue == 0` and
   `forwardsAlias > 0`. This is impossible on the current build (aliasing
   cannot fire without value confidence) and is the direct demonstration that
   the trigger is decoupled.
3. **`both` is a NEW operating point — it does NOT reproduce `unified`.**
   (Correction, from the implementation review.) Decoupling is exactly what
   changes `both`: the old `unified` attempted aliasing only inside
   `if (predict().valid)`, i.e. only on value-confident loads, whereas
   `--mrn-alias` (value + alias) now attempts aliasing on *every* load with a
   correlator binding, independent of value confidence — a strict superset.
   So `both` is expected to *diverge* from a prior `unified` build; a matching
   A/B is the wrong test. Verify instead that under `--mrn-alias` both paths
   fire (`forwardsValue > 0` and `forwardsAlias > 0`).

**Note on "byte-identical" (verification 1):** the default is byte-identical
in every simulation stat (IPC, cycles, committed insts, all value-path stats)
*except* `bindingsLearned`, which drops to 0 because §3 correctly stops the
value-only path from training the correlator it never reads. The correlator
(fwdCache) is read only under `aliasingEnabled()`, so this has zero timing
effect — it is a dead stat when aliasing is off. Measured on `721.gcc_r.2.0`:
the only diff vs a pre-refactor value-only run is `bindingsLearned`
411,623 → 0.

## Non-goals

- No aliasing confidence counter (next step).
- No change to the aliasing mechanism (rename-map lookup, current-producer
  gate) or to value-forwarding training (rename-snapshot, committed in 1a).
- Commit-message headers referencing old "mode" terms are history, untouched.
