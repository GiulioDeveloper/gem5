# MRN Path Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the MRN value-forwarding and producer-aliasing paths independent — each individually enable/disable-able, with aliasing's trigger no longer borrowed from value-forwarding confidence.

**Architecture:** The two paths already own disjoint data structures (value: storeCache/valueFile/loadCache; aliasing: fwdCache correlator). Only the `rename.cc` trigger and the `mrnMode`/`unified()` config couple them. Replace `mrnMode` with two bool params, split the `rename.cc` triggers (aliasing-first priority), and gate each path's training on its own enable.

**Tech Stack:** gem5 O3 CPU (C++), SimObject params (Python `MemRenamePredictor.py` → generated `params/MemRenamePredictor.hh`), GoogleTest unit tests, SCons.

## Global Constraints

- Build: `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ARM/gem5.opt -j32` (this host; `build-gem5.sh` does not work here).
- Style: C++ 79-col / 4-space / clang-format; Python black line-length 79. Run `python3 util/run-git-clang-format.py` before staging C++.
- Naming: no conversational/session terms in code (enforced by the `precommit-review` skill).
- Commits: use the `git-commit` skill (gem5 tag header, commit-note, **run `precommit-review` first**, no AI-attribution trailer).
- **Default behavior must be byte-identical**: `enableValueForwarding=True, enableProducerAliasing=False` reproduces today's `value_only`.
- Resources for FS runs: `export GEM5_RESOURCE_DIR=/home/rbera/work/tracezoo/gem5/restore_resources`; checkpoints under `/home/rbera/work/tracezoo/gem5/fs_ckpts/<bench>/<inv>/cpt.<id>`.

---

### Task 1: Separate the two paths in the C++ core (atomic)

The param, accessors, ctor, and all call sites must change together — the tree does not compile until they are consistent. This is one commit.

**Files:**
- Modify: `src/cpu/o3/MemRenamePredictor.py` (params)
- Modify: `src/cpu/o3/mem_rename_predictor.hh` (accessors + members)
- Modify: `src/cpu/o3/mem_rename_predictor_sim.cc` (ctor init)
- Modify: `src/cpu/o3/rename.cc` (decoupled triggers)
- Modify: `src/cpu/o3/iew.cc` (`unified()` → `aliasingEnabled()`)
- Modify: `src/cpu/o3/lsq_unit.cc` (gate `commitStore`, `trainForward`)
- Modify: `src/cpu/o3/commit.cc` (gate `commitLoad`)
- Test: `src/cpu/o3/mem_rename_predictor.test.cc` (must still pass; no new unit test — the enable logic lives in the SimObject wrapper, which the plain-int unit test does not link)

**Interfaces:**
- Produces: `MemRenamePredictor::valueForwardingEnabled() const -> bool`, `MemRenamePredictor::aliasingEnabled() const -> bool` (replaces `unified()`).
- Consumes: existing `predict`, `peek`, `commitStore`, `commitLoad`, `trainForward`, `predictProducerPC` (unchanged signatures).

- [ ] **Step 1: Params — replace `mrnMode` with two bools.**

In `src/cpu/o3/MemRenamePredictor.py`, delete the `MrnMode` enum class (lines 6-10) and the `mrnMode` param (lines 82-87). Keep `MrnCorrelation`. Add, where `mrnMode` was:

```python
    enableValueForwarding = Param.Bool(
        True,
        "Forward a snapshotted value into a high-confidence load's renamed "
        "destination (the value path). Independent of producer aliasing.",
    )
    enableProducerAliasing = Param.Bool(
        False,
        "Alias a load's renamed destination to an in-flight producing "
        "store's physreg when the correlator has a binding (the alias "
        "path). Independent of value forwarding; when both are enabled, "
        "aliasing takes priority.",
    )
```

- [ ] **Step 2: Accessors + members in the header.**

In `src/cpu/o3/mem_rename_predictor.hh`, replace the `unified()` accessor (lines 382-387) with:

```cpp
    /** Whether the value-forwarding path is enabled. */
    bool
    valueForwardingEnabled() const
    {
        return _enableValueForwarding;
    }

    /** Whether the producer-aliasing path is enabled. */
    bool
    aliasingEnabled() const
    {
        return _enableProducerAliasing;
    }
```

Replace the member declarations (lines 396-397, the `_unified` block) with:

```cpp
    /** Value-forwarding path enabled. */
    const bool _enableValueForwarding;
    /** Producer-aliasing path enabled. */
    const bool _enableProducerAliasing;
```

- [ ] **Step 3: Constructor init.**

In `src/cpu/o3/mem_rename_predictor_sim.cc`, replace `_unified(p.mrnMode == enums::unified),` (line 18) with:

```cpp
      _enableValueForwarding(p.enableValueForwarding),
      _enableProducerAliasing(p.enableProducerAliasing),
```

Keep member-init order matching the header declaration order (place these where `_unified` was, i.e. after `_predictIntLoadsOnly` / before `_useStoreSet` — mirror the header).

- [ ] **Step 4: Decouple the `rename.cc` triggers (the core change).**

In `src/cpu/o3/rename.cc`, replace the block at lines 749-771:

```cpp
        // Garfield MRN: decide a load's forwarding path *before* renaming its
        // destination, so a producer-register alias can divert the
        // destination map entry. predict() yields both the confidence and the
        // value snapshot used when no in-flight producer is found.
        MrnPrediction mrnPred{false, 0};
        bool mrnAliased = false;
        if (memRenamePred && inst->isLoad() && inst->numDestRegs() > 0) {
            const Addr load_pc = inst->pcState().instAddr();
            mrnPred = memRenamePred->predict(load_pc);
            // Snapshot the value this load's prediction uses REGARDLESS of
            // confidence, so commit can train the counter against what the
            // prediction actually was at rename rather than the value file as
            // of commit (which the producing store may already have
            // refreshed). Captured for every eligible load, not only
            // forwarded ones, so below-threshold loads still train correctly.
            const MrnPrediction snap = memRenamePred->peek(load_pc);
            if (snap.valid) {
                inst->setMrnSnap(snap.value);
            }
            if (mrnPred.valid) {
                mrnAliased = tryMemRenameAlias(inst, inst->threadNumber);
            }
        }
```

with:

```cpp
        // Garfield MRN: decide a load's forwarding path *before* renaming its
        // destination, so a producer alias can divert the destination map
        // entry. The two paths are independent: value forwarding is gated on
        // its own confidence (predict), producer aliasing on its own trigger
        // (a correlator binding, inside tryMemRenameAlias). Aliasing takes
        // priority when both apply.
        MrnPrediction mrnPred{false, 0};
        bool mrnAliased = false;
        if (memRenamePred && inst->isLoad() && inst->numDestRegs() > 0) {
            const Addr load_pc = inst->pcState().instAddr();
            // Value path: confidence + the rename-time training snapshot.
            if (memRenamePred->valueForwardingEnabled()) {
                mrnPred = memRenamePred->predict(load_pc);
                const MrnPrediction snap = memRenamePred->peek(load_pc);
                if (snap.valid) {
                    inst->setMrnSnap(snap.value);
                }
            }
            // Alias path: its own trigger, not the value path's confidence.
            if (memRenamePred->aliasingEnabled()) {
                mrnAliased = tryMemRenameAlias(inst, inst->threadNumber);
            }
        }
```

The value-forward body at line 784 (`if (mrnPred.valid && !mrnAliased)`) is unchanged: `mrnPred.valid` is only ever true when value forwarding is enabled, and `!mrnAliased` gives aliasing priority.

- [ ] **Step 5: Drop the internal enable check in `tryMemRenameAlias`.**

In `src/cpu/o3/rename.cc`, delete the guard at lines 1236-1238:

```cpp
    if (!memRenamePred->unified()) {
        return false;
    }
```

The enable is now the caller's `aliasingEnabled()` guard (Step 4). Leave the rest of `tryMemRenameAlias` unchanged.

- [ ] **Step 6: `iew.cc` producer-writeback verify.**

In `src/cpu/o3/iew.cc` line 1436, change `memRenamePred->unified()` to `memRenamePred->aliasingEnabled()`. Update the trailing comment ("Gated on unified mode so off / value_only are byte-identical.") to "Gated on the aliasing path so it is inactive when aliasing is disabled."

- [ ] **Step 7: Gate value-path training.**

In `src/cpu/o3/lsq_unit.cc`, the `commitStore` call (line 885 guard). Change:

```cpp
        if (mrn && inst->effAddrValid()) {
```
to:
```cpp
        if (mrn && mrn->valueForwardingEnabled() && inst->effAddrValid()) {
```

In `src/cpu/o3/commit.cc`, the `commitLoad` guard (line 1445). Change:

```cpp
    if (memRenamePred && head_inst->isLoad() && head_inst->effAddrValid() &&
        head_inst->memData) {
```
to:
```cpp
    if (memRenamePred && memRenamePred->valueForwardingEnabled() &&
        head_inst->isLoad() && head_inst->effAddrValid() &&
        head_inst->memData) {
```

- [ ] **Step 8: Gate correlator training.**

In `src/cpu/o3/lsq_unit.cc` (the `trainForward` site, lines 1585-1591), change the guard:

```cpp
                if (MemRenamePredictor *mrn = iewStage->getMemRenamePred()) {
                    mrn->trainForward(
```
to:
```cpp
                MemRenamePredictor *mrn = iewStage->getMemRenamePred();
                if (mrn && mrn->aliasingEnabled()) {
                    mrn->trainForward(
```

Update the comment at lines 1585-1586 — replace "Mode-independent: the binding is learned regardless of mrnMode (only its use is gated)." with "The correlator is maintained only when the aliasing path is enabled."

- [ ] **Step 9: Build.**

Run: `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ARM/gem5.opt -j32`
Expected: `scons: done building targets.`, `[ LINK] -> ARM/gem5.opt`, no `error:`.

- [ ] **Step 10: Unit tests still pass.**

Run: `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ARM/cpu/o3/mem_rename_predictor.test.opt -j32 && ./build/ARM/cpu/o3/mem_rename_predictor.test.opt`
Expected: `[ PASSED ] 7 tests.`

- [ ] **Step 11: precommit-review + commit (Task 1).**

Run the `precommit-review` skill on `git diff --cached`; expect clean (no conversational naming — the retired `mrnMode`/`unified`/`value_only` are API identifiers referenced in context). Then commit via the `git-commit` skill. Suggested header: `cpu-o3: Separate MRN value and alias paths` (≤65). Body: the two paths are now independently enabled and independently trained; default (value only) is byte-identical.

---

### Task 2: CLI / config driver

**Files:**
- Modify: `configs/garfield/arm/sim_opts.py` (retire `--mrn-mode`, add two flags, update `make_mrn`)

**Interfaces:**
- Consumes: the Task 1 params `enableValueForwarding`, `enableProducerAliasing`.

- [ ] **Step 1: Replace the `--mrn-mode` argument.**

In `configs/garfield/arm/sim_opts.py`, delete the `--mrn-mode` argument (lines 157-166) and add, in its place:

```python
    garfield.add_argument(
        "--mrn-no-value-forward",
        action="store_true",
        help="Disable the MRN value-forwarding path (on by default). Leaves "
        "the producer-aliasing path unaffected.",
    )
    garfield.add_argument(
        "--mrn-alias",
        action="store_true",
        help="Enable the MRN producer-aliasing path (off by default). "
        "Independent of value forwarding; when both are on, aliasing takes "
        "priority.",
    )
```

- [ ] **Step 2: Update `make_mrn`.**

In `make_mrn` (line 226), remove the `mrnMode=args.mrn_mode.replace("-", "_"),` line and add the two bools:

```python
        enableValueForwarding=not args.mrn_no_value_forward,
        enableProducerAliasing=args.mrn_alias,
```

(Keep `mrnCorrelation=...` and the other args.)

- [ ] **Step 3: black + --help smoke.**

Run: `python3 -m black configs/garfield/arm/sim_opts.py`
Run: `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib ./build/ARM/gem5.opt configs/garfield/arm/se_run.py --help 2>&1 | grep -E 'mrn-alias|mrn-no-value-forward|mrn-mode'`
Expected: the two new flags present, `--mrn-mode` absent.

- [ ] **Step 4: precommit-review + commit (Task 2).**

`precommit-review` (expect clean), then `git-commit`. Suggested header: `configs: Two independent MRN path flags` (≤65).

---

### Task 3: Verification suite (extensive test)

Prove the separation and the no-regression. All FS runs: `export GEM5_RESOURCE_DIR=/home/rbera/work/tracezoo/gem5/restore_resources`, disk `$GEM5_RESOURCE_DIR/spec_shared_root.img`, 2M warmup / 5M detailed for speed (proofs are stat-based, not IPC-based).

**Files:** none modified — this task produces evidence, not code.

- [ ] **Step 1: Default config is byte-identical.**

Run the current build and the pre-refactor build (HEAD before Task 1, `git stash`/worktree not needed — compare against a saved `config.ini` from a prior default run, or regenerate). Concretely, run default MRN on `721.gcc_r.2.0` and confirm the config parameters block for `memRenamePredictor` still carries the same effective knobs and that a no-alias run's MRN stats match a pre-refactor value-only run. Minimal check:

```bash
export GEM5_RESOURCE_DIR=/home/rbera/work/tracezoo/gem5/restore_resources
S=$(mktemp -d)
LD_LIBRARY_PATH=/home/rbera/miniconda3/lib ./build/ARM/gem5.opt --outdir=$S/def \
  configs/garfield/arm/fs_run.py \
  --restore-dir /home/rbera/work/tracezoo/gem5/fs_ckpts/721.gcc_r/2/cpt.721.gcc_r.2.0 \
  --benchmark 721.gcc_r --inv 2 --disk-img $GEM5_RESOURCE_DIR/spec_shared_root.img \
  --warmup-insts 2000000 --detailed-insts 5000000 --use-mrn
grep -E 'forwardsValue|forwardsAlias' $S/def/stats.txt
```
Expected: `forwardsValue > 0`, `forwardsAlias == 0` (default is value-only — aliasing off).

- [ ] **Step 2: Independence proof (the point of the change).**

```bash
LD_LIBRARY_PATH=/home/rbera/miniconda3/lib ./build/ARM/gem5.opt --outdir=$S/alias \
  configs/garfield/arm/fs_run.py \
  --restore-dir /home/rbera/work/tracezoo/gem5/fs_ckpts/721.gcc_r/2/cpt.721.gcc_r.2.0 \
  --benchmark 721.gcc_r --inv 2 --disk-img $GEM5_RESOURCE_DIR/spec_shared_root.img \
  --warmup-insts 2000000 --detailed-insts 5000000 --use-mrn --mrn-alias --mrn-no-value-forward
grep -E 'forwardsValue|forwardsAlias|loadsTrained|bindingsLearned' $S/alias/stats.txt
```
Expected: `forwardsValue == 0` (value path disabled), `forwardsAlias > 0` (aliasing fires on its own trigger). This is impossible on the pre-refactor build and is the direct demonstration of decoupling. Also expect `loadsTrained == 0` (value-path training gated off) and `bindingsLearned > 0` (correlator still trained).

- [ ] **Step 3: `both` reproduces `unified`.**

Build the pre-refactor commit (`e6d0d086c9` era, `--mrn-mode unified`) in a scratch worktree OR compare against the committed `runs/mrn_alias_gate/721.gcc_r.2.0/mrnC_gated` stats. Run the new build with `--mrn-alias` (value + alias, alias-first) at the same 10M/50M and confirm `mispredicts`, `aliasMispredicts`, `forwardsValue`, `forwardsAlias` match the prior `unified` numbers (alias-first is today's order).

- [ ] **Step 4: Extensive multi-lens code review.**

Dispatch review agents (subagent-driven-development's review stage or a review workflow) covering: (a) correctness — does any disabled-path residue still run (e.g. a stat incremented outside its enable)? (b) spec conformance — every §1-§5 item present? (c) the independence property — is there any remaining read of value confidence on the alias trigger, or vice versa? (d) style/naming/precommit-review. Fix confirmed findings; re-run Steps 1-2.

- [ ] **Step 5: Record result.**

Update `docs/garfield/mrn-ideas.md` (1b entry): the paths are now separated (commit refs), independence proven (`forwardsValue==0` with alias-only), aliasing confidence is the next step. Commit via `git-commit`.

## Self-Review

**Spec coverage:** §1 config → Task 1 Steps 1-3; §2 rename triggers → Task 1 Steps 4-5; §3 per-path training gating → Task 1 Steps 7-8; §4 other unified() sites → Task 1 Steps 3, 6; §5 CLI → Task 2; Verification §1-3 → Task 3 Steps 1-3. All covered.

**Placeholder scan:** exact strings and commands throughout; no TBD/TODO.

**Type consistency:** `valueForwardingEnabled()` / `aliasingEnabled()` used identically in Task 1 (accessors, rename.cc, iew.cc, lsq_unit.cc, commit.cc) and consumed by Task 2 params `enableValueForwarding` / `enableProducerAliasing`. `MrnCorrelation` / `mrnCorrelation` retained unchanged.
