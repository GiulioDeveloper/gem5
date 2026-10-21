# MRN Value-File Rendezvous Predictor — Design

**Date:** 2026-07-25 · **Branch:** rbdev · **Status:** approved for planning

A new predictor model for the MRN (memory-rename predictor) producer-aliasing
path, based on Tyson & Austin's memory renaming (MICRO-30, 1997), with the
concrete table structure described by Reinman, Calder, Tullsen, Tyson & Austin,
"Classifying Load and Store Instructions for Memory Renaming," ICS 1999, §2.3
(Store/Load Cache + Value File + Store Cache + confidence).

## 1. Motivation

Measured on 721.gcc_r.2.0 (10M warmup / 50M detailed, alias path only), the
current producer-PC correlator + store-queue instance hunt:

- Correlator accuracy is 58.6% (356,462 correct / 608,142 predictions made):
  the correlator is a last-writer-wins loadPC→storePC table with no
  confidence, no repetition check.
- Only 0.28% of predictions (1,702) become enforced aliases. 60.5% are
  refused by the stale-producer reject (`aliasRequireCurrentProducer`) and
  39.2% find no in-flight store with the predicted PC at all.
- The staleness is structural, not incidental: a store enters the store queue
  at dispatch, `renameToIEWDelay` (2) cycles after its rename, so the
  same-iteration producer store is never visible to
  `findYoungestStoreByPC` at the load's rename. The located store is a prior
  iteration's instance; for a changing recurrence its captured data physreg is
  wrong every iteration.
- A read-only StoreSet-agreement experiment showed the prediction noise is
  filterable (58.6% → 81.7% accuracy under a dependence-set gate while keeping
  96.6% of correct predictions), i.e. a real learning mechanism recovers most
  of the loss. Rather than bolt confidence onto the flawed correlator, this
  design replaces the binding + instance-finding mechanism entirely.

The rendezvous model removes the store-instance hunt: the store *deposits*
its producer information into a named cell at its own rename, and the load
*reads* the cell at its rename. In-order rename guarantees the deposit
precedes the read and belongs to the program-order-youngest earlier instance.

## 2. Design point

- **Dependence distance 1 is the explicit design point.** One rendezvous cell
  per static store; the youngest dynamic instance's deposit wins. Loop-carried
  dependences with distance > 1 are out of scope (the ICS'99 paper §4 states
  the same limitation) and are suppressed by confidence, not predicted.
- The model is the alias path's new binding source. The existing value path
  (`enableValueForwarding`) stays in-tree, independently disable-able, and is
  expected to be OFF in experiments; the model's own value modes cover its
  role and will eventually subsume it (then the old value path and the old
  `fwdCache` correlator get deleted — not in this project).
- Selection: new value `value_file` on the existing `mrnCorrelation` enum
  (`lsq_forward` stays the default; the `store_set` stub stays).

## 3. Structures

All sizes/associativities are SimObject params; defaults in parentheses are
starting points (the ICS'99 paper used 4K direct-mapped SLC/SC and a 1K VF).

**Value File (VF)** (1024 entries, LRU): the rendezvous cells.

```
{ gen, ptrValid, PhysRegIdPtr ptr, InstSeqNum ptrSeq,
  valueValid, RegVal value, lru }
```

**Store/Load Cache (SLC)** (4096 entries, assoc 4, LRU): PC-indexed, one
shared table for store and load PCs.

```
{ tag(PC), vfIdx, gen, conf, lru }        // conf used by load entries only
```

**Store Cache (SC)** (4096 entries, assoc 4, LRU): address-indexed at a
granularity param (8 B lines). Written only by stores; probed only by loads.

```
{ tag(addr), vfIdx, gen, storeSeq, lru }
```

**Confidence:** a saturating counter in the load's SLC entry, reusing the
existing param family (`confBits`, `confThreshold`, `confInc`, `confDec`,
`resetConfOnMispredict`) with the same semantics as the current value path.

### 3.1 The generation counter (`gen`)

`gen` is a **dangling-reference detector, not an iteration counter**. Dynamic
instances of the same static store deposit into the same cell with the same
`gen`; content is overwritten, `gen` is untouched. `gen` increments in exactly
one situation: **LRU reallocation of the VF cell to a different owner**. SLC
and SC entries are references into the VF (`{vfIdx, gen}`); after
reallocation, a stale reference's `gen` mismatches and reads as "no binding"
instead of silently consuming the new owner's channel.

`gen` is orthogonal to `storeSeq` in the SC: `storeSeq` is the dynamic seqNum
of the publishing store, used only to keep SC writes program-ordered under
out-of-order address resolution. `storeSeq` orders content updates to the SC;
`gen` validates references into the VF.

## 4. Dataflow — five events

Nothing happens at decode (deviation from the paper, agreed): the front-end
events run at **rename**, which is in-order — this is what makes the deposit
race-free and the deposited pointer always the correct instance's physreg.

**E1 — Store rename.** Guards as the current alias path (simple store,
integer data register = last source). SLC lookup by store PC; miss →
LRU-allocate a VF cell (`gen++` on the cell), point SLC at `{vfIdx, gen}`.
Deposit into the cell:

- `ptr := current rename-map mapping of the data arch reg` (identical to
  `renamedSrcIdx(n-1)` at the store's own rename — no staleness is possible
  at the deposit site), `ptrSeq := store seqNum`, `ptrValid := 1`.
- **`valueValid := 0`, unless** the data physreg is scoreboard-ready right
  now, in which case rename reads it and deposits `value` too
  (`valueValid := 1`). A leftover value would be the *previous* instance's
  data — wrong for a changing distance-1 recurrence; it must not survive the
  deposit.

Carry `{vfIdx, gen}` on the store's DynInst (for E3).

**E2 — Load rename.** Guards as the current alias path (single integer
destination). SLC lookup by load PC → `{vfIdx, gen, conf}`. If the cell's
`gen` matches and `conf >= confThreshold`, consume per §5. Carry
`{vfIdx, gen}` on the load's DynInst regardless (needed by E4/E5 and
training).

**E3 — Store address resolved** (LSQ execute). Publish
`SC[EA] := {vfIdx, gen, storeSeq}` using the DynInst-carried index — never a
re-lookup of the SLC, so late-resolving instances publish their own binding.
Program-order guard: overwrite only if the occupant's `storeSeq` is
program-order older than the publisher's.

**E4 — Load address resolved** (LSQ execute). Probe `SC[EA]`:

- hit, `{vfIdx, gen}` differs from the load's current SLC binding →
  **rebind** `SLC[loadPC] := {vfIdx, gen}` and **reset conf** (the channel
  changed);
- hit, same binding → nothing (confidence is trained by verification only,
  §5);
- miss → **self-bind**: if the load is not already self-bound, LRU-allocate
  an own VF cell and point `SLC[loadPC]` at it. (Uniform LRU allocation —
  deviation from the paper's PC-indexed fallback slot — so there is a single
  allocation policy.)

**E5 — Load data resolved** (writeback). If self-bound, write the loaded
value into the cell (`valueValid := 1`, `ptrValid := 0`): the next instance
of this load can consume it speculatively — this is last-value prediction of
constant/stable loads falling out of the same structure. If store-bound, the
cell content is owned by the store; the load only trains confidence.

## 5. Consumption, verification, confidence

At E2 with a confident, `gen`-valid binding, in priority order:

1. **`ptrValid` and the producer physreg is NOT scoreboard-ready → alias.**
   Existing enforcement, unchanged: liveness guards in rename
   (`IntRegClass`, `!isFixedMapping`, `refCount > 0`), destination surgery in
   `renameDestRegs` with the producer refcount bump, deferred verification in
   `mrnVerifyAlias` at MAX(load-resolve, producer-resolve). Dependents wake
   when the producer writes back — the alias chains their wakeup to that
   future event, which is the only option while the value does not yet exist.
2. **`ptrValid` and the producer physreg IS ready → value-forward its
   value.** Rename reads the physreg immediately, writes it into the load's
   own renamed destination, marks it ready. Dependents are wake-able at
   dispatch; there is no future event to chain to. Timing is identical to
   aliasing a ready producer; the value form is preferred because it avoids
   extending the producer physreg's lifetime (no refcount surgery) and its
   verification is the plain value compare at load writeback. This matches
   the paper: the spec-move is used only when the producing instruction "has
   not yet completed execution."
3. **`valueValid` only (self-bound last-value cell) → value-forward the
   value.** Same machinery as 2.

Consumption knobs: alias consumption is implied by selecting the model
(`enableProducerAliasing` still gates it); `vfForwardProducerValue` and
`vfForwardLastValue` (both default true) gate modes 2 and 3 so experiments
can isolate each. When the model makes any prediction for a load, the old
value path is skipped for that load (single-writer rule); the recommended
experimental configuration runs the old value path disabled anyway.

**Verification** reuses today's machinery unchanged: value forwards verify by
value compare at load writeback; aliases verify against the producer physreg
(deferred until the producer resolves if needed). A consumed, wrong
prediction squashes from the load (inclusive) and resets `conf`
(per `resetConfOnMispredict`).

**Shadow verification:** below-threshold predictions are not consumed but are
still checked at writeback (no squash) purely to train `conf` upward —
without this, confidence could never rise from zero. Mirrors the existing
`trainOnRenameSnapshot` mechanism. Correct → `conf += confInc` (saturating);
wrong → reset/decrement per the existing params. Consumed predictions train
the same counter through their real verification.

**Squash policy: none of SLC/VF/SC roll back.** They are prediction tables,
like the branch predictor's. A squashed store's dangling `ptr` is absorbed by
the use-time liveness guards, verification, and confidence. DynInst-carried
`{vfIdx, gen}` dies with the instruction. Squashed-before-validation
consumed predictions are counted separately (existing accounting pattern:
made = correct + wrong + squashed, per mode).

## 6. Code organization

- New files `src/cpu/o3/mem_rename_valuefile.{hh,cc}`: a **params-free core
  class** (pattern: `MrnTables`) owning VF/SLC/SC and the confidence logic.
  The core stores `PhysRegIdPtr` opaquely and never dereferences it; all
  liveness checks stay in rename at consumption. Registered in the SConscript;
  unit tests in `mem_rename_valuefile.test.cc` (GTest), covering: deposit
  then consume across instances; deposit invalidating a stale value; rebind
  on SC probe mismatch; self-bind and last-value; gen mismatch after
  reallocation; SC program-order overwrite guard; confidence rise via shadow
  training and reset on rebind/mispredict.
- `MemRenamePredictor` owns the core next to `MrnTables` and exposes the
  event API; rename/LSQ call through it as today. The five events map to:
  E1/E2 in `Rename::renameInsts` (replacing the `tryMemRenameAlias` call when
  `mrnCorrelation == value_file`), E3/E4 in the LSQ execute paths, E5 at load
  writeback.
- Structure names follow the published literature (`valueFile`,
  `storeLoadCache`, `storeCache`), cited to the papers above in the header
  comment. They do not collide with the existing value path's members (which
  live in `MrnTables` and are slated for later deletion).
- Stats: per-mode made/correct/wrong/squashed (alias, producer-value,
  last-value), plus deposits (ptr/value), SC publishes and
  publish-suppressed-by-order, probe hits/misses, rebinds, self-binds,
  gen-mismatch rejects, below-threshold suppressions.

## 7. Non-goals and known limitations

- Dependence distance > 1 (design point, §2).
- SMT partitioning: tables are per-core, PCs cross-thread alias (single-thread
  checkpoints today; same status as the rest of MRN).
- Predictor state is not serialized: cold after checkpoint restore; warmup
  covers it.
- Non-simple memory ops never deposit or consume (store-pair, vector,
  multi-dest loads, non-integer data) — same guards as the current alias
  path.
- Mixed-size / partial-overlap aliasing below SC granularity is left to
  verification.
- Old value path and old correlator are not deleted in this project.

## 8. Test and experiment plan

1. **Unit tests** (§6 list) — build `gem5.opt` + run the test binary.
2. **721.gcc_r.2.0 checkpoint** (10M/50M) first — extensive experience and
   existing baselines: current-alias-path run and pre-MRN baseline
   (IPC 0.578217). Configurations: model with alias only; + producer-value;
   + last-value.
3. **Directed microbenchmarks** from
   `gem5-infra/workloads/microbenchmarks/src`: `mrncomm` (stable-value
   communication — both models should capture it) and `mrnrec` (changing
   distance-1 recurrence — the case the current alias path structurally
   rejects; the new model must capture it).
4. **190-checkpoint sweep** once gcc looks sound.

**Success criteria:**

- Consumed-prediction correctness ≥ 95% on gcc (flush cost demands it).
- Enforced aliases ≫ the current 1,702 on gcc — target order 10⁴–10⁵,
  approaching the ~69K genuine same-set dependence pool the StoreSet
  experiment identified.
- Accounting identity holds exactly per mode
  (made = correct + wrong + squashed).
- `mrnrec` shows correct aliasing of the changing recurrence (near-zero
  mispredicts, nonzero enforced aliases); `mrncomm` regresses nothing.
- IPC ≥ baseline on gcc before entering the sweep.
