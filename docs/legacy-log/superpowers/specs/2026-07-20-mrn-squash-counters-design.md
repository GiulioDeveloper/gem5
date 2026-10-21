# MRN squash-reason counters

Date: 2026-07-20
Status: approved, implementing

## Problem

The MRN (memory-rename predictor) resolution counters do not close. On
`721.gcc_r.2.0` (50M detailed, mode C):

```
predictionsMade   1,620,099  =  forwardsValue 1,553,944 + forwardsAlias 66,155
value path : 1,553,944 = 795,922 correct + 279,810 mispred + 478,212 UNACCOUNTED
alias path :    66,155 =  14,384 correct +  33,673 mispred +  18,098 UNACCOUNTED
```

30.6% of predictions on this checkpoint resolve to nothing. The cause is
that `predictionsMade` / `forwardsValue` / `forwardsAlias` increment at
**rename** (`mem_rename_predictor.hh:211,245,252`), while
`predictionsCorrect` / `mispredicts` and the alias pair only increment
inside `LSQUnit::writeback()`, under `if (!inst->isExecuted())`
(`lsq_unit.cc:1142`). A forwarded load squashed before it completes its
access is counted as made and never resolved.

This silently understates accuracy: computing `correct/made` gives 80.6%
mean across the sweep where `correct/(correct+mispredicts)` gives 91.6%.
It also hides a real cost — those forwards consumed rename bandwidth and
physregs before being discarded.

## Goal

Attribute every unresolved MRN prediction to the reason its load was
squashed, split by forwarding path (mode-B value vs mode-C alias), so that
per-path resolution closes:

```
forwardsValue == predictionsCorrect + mispredicts      + predictionsSquashedValue::total
forwardsAlias == aliasVerifyCorrect + aliasMispredicts + predictionsSquashedAlias::total
```

## Scope decisions

- **Front-end squashes are out of scope.** MRN predicts at rename, so
  decode-resolved mispredicts (`decode.cc:733`), FTQ resteers
  (`fetch.cc:1105`, `:1380`) and BAC history squashes (`bac.cc:815`,
  `:840`) can never discard an MRN-ed load. Only squashes reaching the ROB
  matter.
- **5 reason buckets, not 13.** Traps, interrupts, ReExec replays, HTM
  aborts, ThreadContext writes, drain and serializing instructions all
  collapse into `Other`. These are expected to be near-zero for the FS
  SPEC workloads in question; splitting them further can wait until a
  bucket lights up.
- **Memory-order violations are not subcategorized.** Store->load and
  load->load-via-snoop share one `MemOrder` bucket.

## Design

### Reason enum

New standalone header `src/cpu/o3/mrn_squash_reason.hh`, kept free of
other O3 includes so `rob.hh`, `iew.hh` and `comm.hh` can all include it
without pulling in the predictor:

```cpp
enum class MrnSquashReason { Branch, MemOrder, MrnValue, MrnAlias, Other, Num };
```

### The `mrnResolved` bit

`DynInst` gains an `MrnResolved` flag beside the existing `Mrned`
(`dyn_inst.hh:194`) with accessors beside `isMrned()` (`:403`).

It means "this prediction has been accounted for, by any outcome" — not
merely "verified". It is set at:

- all **four** resolution arms in `lsq_unit.cc`, not two. Both mispredict
  arms (`:1177`, `:1808`) must set it as well as both correct arms
  (`:1190`, `:1818`), because `squashDueToMemOrder` is *inclusive* — a
  mispredicting load squashes itself and would otherwise be counted in
  both `mispredicts` and the squashed vector;
- both squash-accounting sites, immediately before incrementing.

**This bit, not the instruction's squashed status, is what makes the
accounting exactly-once.** An earlier attempt gated on `!isSquashed()`
instead, which fails in both directions: `ROB::squash()` resets `squashIt`
to the tail so overlapping squashes re-walk entries, and a large squash
spans several cycles (`squashWidth`) during which `LSQUnit::squash` marks
the whole load-queue range squashed in one go.

### Reason plumbing

`IEW::squashDueToMemOrder()` is shared by four logically distinct causes
(real MO violation at `iew.cc:1348`, MRN value mispredict at
`lsq_unit.cc:1187`, MRN alias mispredict at `lsq_unit.cc:1815`), and
commit reports all of them identically. Classification therefore cannot be
done at the squash site; the reason must be plumbed from the initiator:

1. `IEW::squashDueToMemOrder(inst, tid)` gains an `MrnSquashReason`
   parameter. Three call sites pass `MemOrder`, `MrnValue`, `MrnAlias`.
2. `IEWStruct` (`comm.hh`) gains `MrnSquashReason mrnSquashReason[MaxThreads]`
   alongside `squashedSeqNum`. `squashDueToBranch` writes `Branch`;
   `squashDueToMemOrder` writes its parameter.
3. `Commit` stashes the reason on the ROB before each `rob->squash()`.
   There are exactly two sites: `commit.cc:525` (inside `squashAll`, used
   by `squashFromTrap` / `squashFromTC` / `squashFromSquashAfter`) writes
   `Other`; `commit.cc:953` (the IEW-driven path) forwards the time-buffer
   value.

### Counting sites

There are **two**, not one. The initial design assumed `ROB::doSquash()`
alone was a sufficient choke point; validation disproved that on both
sides (see "Validation findings" below).

**1. `ROB::doSquash()`, at the `setSquashed()` call (`rob.cc:343`)** —
the main site, guarded by `!isSquashed()`. The guard is required:
`ROB::squash()` resets `squashIt` to the tail, so a squash raised while a
previous one is still draining walks over entries that are already
squashed and would count them again.

**2. `CPU::squashInstIt()` (`cpu.cc:1274`)**, reached from
`CPU::removeInstsNotInROB()` — instructions that were renamed (and
therefore possibly MRN-forwarded) but never reached the ROB. Attributed to
`rob.getMrnSquashReason(tid)`, the reason recorded for the squash
currently in effect.

`Commit::getInsts()` looks like the natural home for this and is **wrong**:
`Commit::commit()` skips `getInsts()` entirely while any thread is
squashing (`commit.cc:998`), which is precisely when these instructions
are dropped. A counting site there never fires for them.

The two sites are disjoint: `removeInstsNotInROB` walks only instructions
past the ROB tail. The `MrnResolved` bit guards the boundary regardless.

Rejected alternatives:

- **`DynInst::setSquashed()`** is called from five sites
  (`rob.cc:343`, `decode.cc:350,397`, `rename.cc:412`,
  `lsq_unit.cc:995,1064`, `cpu.cc:1275`) and is not idempotent-guarded
  (`dyn_inst.cc:323`). The LSQ calls it on load-queue entries the ROB also
  walks, so this double-counts.
- **Iterating the ROB range from Commit** duplicates the walk and fights
  the `squashWidth` rate-limiting.

The ROB reaches the predictor via `cpu->iew.getMemRenamePred()`
(`cpu.hh:440`, `iew.hh:248`).

## Stats

Two `statistics::Vector` of length 5 in `MemRenameStats`, with subnames
`branch`, `memOrder`, `mrnValue`, `mrnAlias`, `other`:

| stat | meaning |
|---|---|
| `predictionsSquashedValue::branch` | mode-B forward killed by a branch mispredict |
| `predictionsSquashedValue::memOrder` | ...by a real memory-order violation |
| `predictionsSquashedValue::mrnValue` | ...by an **older** mode-B mispredict |
| `predictionsSquashedValue::mrnAlias` | ...by an **older** mode-C mispredict |
| `predictionsSquashedValue::other` | ...by trap/interrupt/TC-write/drain/serializing |
| `predictionsSquashedAlias::*` | same five, for mode-C alias forwards |

`statistics::Vector` emits a `::total` line per stat automatically.

Named into the existing `predictions*` resolution family
(`predictionsMade`, `predictionsCorrect`) and deliberately not `squashed*`,
so they do not read as siblings of `squashedInsts`, which counts flush
cost rather than predictions.

## Known limitation

In principle the identities hold only to within the number of MRN loads
still in flight at a stats boundary, bounded by ROB size:
`m5.stats.reset()` at the region start can count a resolution whose
forward was not counted, and `m5.stats.dump()` at the end can count a
forward whose resolution has not happened yet.

In practice the measured residual is exactly 0, because the region ends
via a `schedule_max_insts` exit that drains the pipeline. Treat a
non-zero residual bounded by ROB size as acceptable and anything larger
as a bug.

## Validation findings

The first implementation used a single counting site in `ROB::doSquash()`
with no dedup. Checking the closure identities on `708.sqlite_r.2.2` drove
three iterations:

1. **Over-counting**, residual **-16,340**. A negative residual cannot be
   an in-flight artifact, which can only under-count — so this was proof
   of a real bug rather than a suspicion. Cause: overlapping squashes
   re-walk ROB entries. First fixed with an `!isSquashed()` guard.
2. **Under-counting**, residual **+12,539** (2% of forwards, far above the
   512-entry ROB bound). Hypothesis "these loads commit without resolving"
   was tested with a temporary `committedUnverified` counter and **came
   back exactly 0** — rejecting it and proving the loads were being
   squashed but missed. Cause: instructions renamed but never inserted
   into the ROB. Fixed by counting site 2 in `CPU::squashInstIt`, after an
   initial attempt in `Commit::getInsts()` proved to be dead code during
   squashes.
3. The `!isSquashed()` guard was replaced by the `MrnResolved` bit, which
   is correct in both directions rather than trading one error for the
   other.

Final result on `708.sqlite_r.2.2` (1M warmup / 3M detailed): both
identities close at **exactly +0**, with the squashed totals rising by
precisely the previous residuals (value 87,100 -> 91,103 = +4,003; alias
607 -> 659 = +52).

Every one of these bugs was invisible on the low-squash-rate checkpoints
(`710.omnetpp_r.1.0` and `782.lbm_r.0.2` closed at +0/+0 throughout),
which is why the validation set spans the coverage range rather than
sampling one benchmark.

## Verification

1. Build `build/ARM/gem5.opt`.
2. Re-run `721.gcc_r.2.0` mode C and check both identities close to within
   ROB size.
3. Fan out across several more checkpoints in parallel, spanning high
   coverage (`708.sqlite_r.2.2`), low coverage (`710.omnetpp_r.1.0`) and
   near-zero (`782.lbm_r.0.2`), confirming closure and that `branch`
   dominates.
4. Confirm a baseline (no-MRN) run is unaffected: all new stats zero.
