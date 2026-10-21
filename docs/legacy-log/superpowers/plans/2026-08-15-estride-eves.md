# E-Stride + EVES Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port CVP-1 EVES's Enhanced Stride predictor into the Garfield
VP framework and compose it with the shipped E-VTAGE into the full EVES
predictor (`--use-vp eves`), evaluated against `evtage_all` (1.0238).

**Architecture:** Three landable stages. (1) A framework-level exact
per-PC in-flight occurrence counter in `BaseValuePredictor` (opt-in,
inert for every existing predictor). (2) A params-free `EStrideTable`
core carrying every CVP stride rule verbatim, plus a pure arbitration
helper — both fully GTest-pinned. (3) An `EvesVP` SimObject that owns
one `EVtageTables` and one `EStrideTable` and routes predict/train/
verify per the spec's flag-keyed rules.

**Tech Stack:** gem5 SCons build (bare `scons`, see Global Constraints),
GoogleTest for cores, the repo's `se_run.py` smoke harness, aarch64
microbenchmarks in the sibling `gem5-infra` repo.

**Spec:** `docs/superpowers/specs/2026-08-14-estride-design.md`
(committed 11b3cb543f). The spec is the contract; where this plan and
the spec disagree, STOP and escalate. The CVP-source reconciliation
lives in the spec §1/§12; cc:/h: cites refer to the CVP-1 contest
source (`cvp8KB/mypredictor.{cc,h}`, microarch.org/cvp1 Seznec.tar.gz).

## Global Constraints

- Build on this host with the Anaconda-clash workaround: bare scons,
  `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ALL/gem5.opt -j$(nproc)`
  (NOT `./build-gem5.sh` — it fails on this machine). GTest binaries:
  `scons build/ALL/cpu/o3/vp/<name>.test.opt` then run the binary.
- C++: 79-col lines, 4-space indent, `UpperCamelCase` classes,
  `lowerCamelCase` methods/members, `snake_case` locals/params.
  Python: black, line-length 79.
- Naming gate (precommit-review, blocking): no conversational or
  session-specific names in code/comments/param help/stat descriptions.
  CVP terms (SafeStride, NotFirstOcc) and descriptive names only.
  Cite the CVP source or the spec — never `.superpowers/` paths.
- Every commit: gem5 tag header <= 65 chars via the `git-commit` skill
  (which runs `precommit-review` and writes the `docs/commit-notes/`
  note in the same commit). NO AI attribution trailers of any kind.
- `EVtageVP` (evtage.{hh,cc}) and `EVtageTables` stay algorithmically
  untouched; comment-only edits permitted (spec §8).
- Bit-identity gate (spec §10) after Tasks 1 and 3: all pre-existing
  stats value-identical on the gate matrix; new counters present and
  zero. Task 1 Step 1 captures the baseline BEFORE any code change.
- RNG: production draws through an injected `std::function<double()>`
  wrapping `Random::genRandom()` (the `EVtageVP` idiom); GTests inject
  scripted functors. Draws are probability-equivalent to CVP, with the
  draw-count discipline the spec §3.3-§3.4 pins.

## File Structure

```
src/cpu/o3/vp/
  vp_inflight_map.hh          NEW  header-only counter map (Task 1)
  vp_inflight_map.test.cc     NEW  GTests for the map (Task 1)
  base.hh / base.cc           MOD  counter facility + notifyRenamedInst
  estride_table.hh / .cc      NEW  params-free E-Stride core (Task 2)
  eves_arbiter.hh             NEW  pure arbitration helper (Task 2)
  estride_table.test.cc       NEW  GTests: stride core + arbiter
  eves.hh / eves.cc           NEW  EvesVP SimObject (Task 3)
  ValuePredictor.py           MOD  class EvesVP (Task 3)
  SConscript                  MOD  sources, sim_objects, GTests
  evtage.hh / evtage.cc       MOD  comment-only staleness fixes (Task 3)
src/cpu/o3/dyn_inst.hh        MOD  VpInflightCounted flag (Task 1)
src/cpu/o3/rename.cc          MOD  notifyRenamedInst call (Task 1)
src/cpu/o3/rob.cc             MOD  squash-walk decrement (Task 1)
src/cpu/o3/cpu.cc             MOD  squash-walk decrement (Task 1)
configs/garfield/arm/sim_opts.py MOD eves choice + flag (Task 3)
docs/superpowers/specs/2026-08-14-estride-design.md MOD amendment (T3)
../gem5-infra/workloads/microbenchmarks/src/{vpstride,vpstorm}.c NEW (T4)
```

---

### Task 1: Framework in-flight occurrence counters

**Files:**
- Create: `src/cpu/o3/vp/vp_inflight_map.hh`
- Create: `src/cpu/o3/vp/vp_inflight_map.test.cc`
- Modify: `src/cpu/o3/vp/base.hh` (facility + delete `notifyRenamed`),
  `src/cpu/o3/vp/base.cc`, `src/cpu/o3/dyn_inst.hh` (flag ~line 204,
  accessors ~line 635), `src/cpu/o3/rename.cc` (~line 954),
  `src/cpu/o3/rob.cc` (~line 390), `src/cpu/o3/cpu.cc` (~line 1315),
  `src/cpu/o3/vp/SConscript`
- Test: `vp_inflight_map.test.cc` + the bit-identity gate

**Interfaces:**
- Consumes: `vpKey(Addr, MicroPC)` (`vp_key.hh`), `DynInstPtr`,
  existing `renamedCount[MaxThreads]` in base.hh.
- Produces (Task 3 relies on these exact names):
  `virtual bool usesInflightCounts() const` (default false);
  `void notifyRenamedInst(const DynInstPtr &inst)`;
  `void notifySquashedInFlight(const DynInstPtr &inst)`;
  `uint32_t inflightCount(uint64_t key) const`;
  DynInst `vpInflightCounted()/setVpInflightCounted()/
  clearVpInflightCounted()`. `notifyRenamed(ThreadID)` is DELETED
  (zero callers today; `renamedInsts(tid)` accessor stays).

- [ ] **Step 1: Capture the bit-identity baseline at current HEAD
  (BEFORE any edit).** Verify `git status` clean at 11b3cb543f. Build,
  then run the gate matrix and stash the stats:

```bash
cd /home/rbera/work/garfield/gem5
LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ALL/gem5.opt -j$(nproc)
mkdir -p runs/eves_identity
cat > runs/eves_identity/run_gate.sh <<'SH'
#!/bin/bash
# Bit-identity gate matrix (spec S10): lvp, vtage, evtage, evtage_all,
# and one MRN config. $1 = output subdir (baseline / after_task1 / ...).
set -euo pipefail
cd "$(dirname "$0")/../.."
GEM5=./build/ALL/gem5.opt
BIN=/home/rbera/work/garfield/gem5-infra/workloads/microbenchmarks/bin
export LD_LIBRARY_PATH=/home/rbera/miniconda3/lib
OUT="runs/eves_identity/$1"
run() { local n="$1"; shift; mkdir -p "$OUT/$n";
  "$GEM5" --outdir="$OUT/$n" configs/garfield/arm/se_run.py \
      --max-insts 5000000 "$@" > "$OUT/$n/run.log" 2>&1; }
run lvp        --binary "$BIN/vpchase" --args "50000" --use-vp lvp
run vtage      --binary "$BIN/vpchase" --args "50000" --use-vp vtage
run evtage     --binary "$BIN/vpchase" --args "50000" --use-vp evtage
run evtage_all --binary "$BIN/vpalu" --args "20000 1" \
               --use-vp evtage --vp-all-insts
run mrn_vp     --binary "$BIN/vpchase" --args "50000" \
               --use-mrn --mrn-conf-threshold 14 --use-vp lvp
echo "gate runs done -> $OUT"
SH
chmod +x runs/eves_identity/run_gate.sh
bash runs/eves_identity/run_gate.sh baseline
```

Write the comparator:

```bash
cat > runs/eves_identity/compare.py <<'PY'
#!/usr/bin/env python3
"""Compare two stats.txt: every old line must reappear verbatim; lines
only in the new file must carry value 0 (new counters). Host-dependent
lines are ignored."""
import sys


def load(path):
    keep = {}
    for line in open(path):
        s = line.strip()
        if (not s or s.startswith("#") or s.startswith("----")
                or s.startswith("host") or s.startswith("simFreq")):
            continue
        keep[s.split()[0]] = s
    return keep


old, new = load(sys.argv[1]), load(sys.argv[2])
bad = []
for k, line in old.items():
    if k not in new:
        bad.append(f"MISSING in new: {k}")
    elif new[k] != line:
        bad.append(f"DIFFERS: old[{line}] new[{new[k]}]")
for k, line in new.items():
    if k not in old:
        toks = line.split()
        val = toks[1] if len(toks) > 1 else "?"
        try:
            nonzero = float(val) != 0.0
        except ValueError:
            nonzero = val not in ("nan", "inf")
        if nonzero:
            bad.append(f"NEW NONZERO: {line}")
print("\n".join(bad) if bad else "IDENTICAL (modulo new zero stats)")
sys.exit(1 if bad else 0)
PY
```

- [ ] **Step 2: Write the failing GTest for the map.** Create
`src/cpu/o3/vp/vp_inflight_map.test.cc`:

```cpp
#include <gtest/gtest.h>

#include "cpu/o3/vp/vp_inflight_map.hh"

using namespace gem5;
using namespace gem5::o3;

TEST(VpInflightMap, StartsEmptyAndCountsZero)
{
    VpInflightMap m;
    EXPECT_EQ(m.count(0x400123), 0u);
    EXPECT_EQ(m.size(), 0u);
}

TEST(VpInflightMap, IncrementDecrementRoundTrip)
{
    VpInflightMap m;
    m.increment(0x400123);
    m.increment(0x400123);
    m.increment(0x500777);
    EXPECT_EQ(m.count(0x400123), 2u);
    EXPECT_EQ(m.count(0x500777), 1u);
    EXPECT_EQ(m.size(), 2u);
    m.decrement(0x400123);
    EXPECT_EQ(m.count(0x400123), 1u);
    m.decrement(0x400123);
    // Erase-on-zero: the key is gone, not a zero-valued tombstone.
    EXPECT_EQ(m.count(0x400123), 0u);
    EXPECT_EQ(m.size(), 1u);
}

TEST(VpInflightMap, InterleavedRenameCommitSquashZeroSum)
{
    // Spec S4's zero-sum sequences: interleave two keys through
    // rename(+)/commit(-)/squash(-) orders, including a same-key
    // burst, and end drained.
    VpInflightMap m;
    const uint64_t a = 0xA, b = 0xB;
    m.increment(a); m.increment(a); m.increment(b);   // rename x3
    m.decrement(a);                                   // commit a#1
    m.increment(a);                                   // rename a#3
    m.decrement(b);                                   // squash b#1
    EXPECT_EQ(m.count(a), 2u);
    EXPECT_EQ(m.count(b), 0u);
    m.decrement(a); m.decrement(a);                   // squash walk
    EXPECT_EQ(m.size(), 0u);
}

TEST(VpInflightMapDeathTest, UnderflowPanics)
{
    VpInflightMap m;
    EXPECT_DEATH(m.decrement(0xDEAD), "underflow");
    m.increment(0xBEEF);
    m.decrement(0xBEEF);
    EXPECT_DEATH(m.decrement(0xBEEF), "underflow");
}
```

- [ ] **Step 3: Register the GTest and run it to verify it fails.**
Add to `src/cpu/o3/vp/SConscript` after the existing GTest lines:

```python
    GTest('vp_inflight_map.test', 'vp_inflight_map.test.cc')
```

Run:
`LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ALL/cpu/o3/vp/vp_inflight_map.test.opt`
Expected: FAIL to compile ("vp_inflight_map.hh: No such file").

- [ ] **Step 4: Implement the map.** Create
`src/cpu/o3/vp/vp_inflight_map.hh`:

```cpp
#ifndef __CPU_O3_VP_VP_INFLIGHT_MAP_HH__
#define __CPU_O3_VP_VP_INFLIGHT_MAP_HH__

#include <cstdint>
#include <unordered_map>

#include "base/logging.hh"

namespace gem5
{
namespace o3
{

/**
 * Exact per-key in-flight occurrence counts for value predictors that
 * extrapolate over speculative same-PC occurrences (design doc
 * docs/superpowers/specs/2026-08-14-estride-design.md, the in-flight
 * counter subsystem): an exact replacement for CVP-1 EVES's 256-deep
 * ring scan, which double-counts past 256 in flight and can match
 * stale slots. Keys are folded vpKey values (vp_key.hh). Erases on
 * zero so size() tracks only keys with live occurrences. Panics on
 * decrement-underflow: the pipeline hook sites guarantee one
 * decrement per increment (the VpInflightCounted DynInst flag), so
 * underflow is always a closure bug, never legal state.
 */
class VpInflightMap
{
  public:
    void
    increment(uint64_t key)
    {
        counts[key]++;
    }

    void
    decrement(uint64_t key)
    {
        auto it = counts.find(key);
        panic_if(it == counts.end() || it->second == 0,
                 "VP in-flight counter underflow for key %#x", key);
        if (--it->second == 0) {
            counts.erase(it);
        }
    }

    uint32_t
    count(uint64_t key) const
    {
        auto it = counts.find(key);
        return it == counts.end() ? 0 : it->second;
    }

    size_t
    size() const
    {
        return counts.size();
    }

  private:
    std::unordered_map<uint64_t, uint32_t> counts;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_VP_INFLIGHT_MAP_HH__
```

- [ ] **Step 5: Run the GTest to verify it passes.**
`./build/ALL/cpu/o3/vp/vp_inflight_map.test.opt` — expected: 4/4 PASS.

- [ ] **Step 6: Add the DynInst flag + accessors.** In
`src/cpu/o3/dyn_inst.hh`, append to the Flags enum after `VpResolved`
(before `MaxFlags`):

```cpp
        VpInflightCounted, /// Garfield VP: counted in the predictor's
                           /// per-PC in-flight occurrence map at
                           /// rename; the exactly-once decrement
                           /// (commit-train or squash walk) clears it
```

Next to the `vpResolved()` accessors (~line 635), add:

```cpp
    bool
    vpInflightCounted() const
    {
        return instFlags[VpInflightCounted];
    }

    void
    setVpInflightCounted()
    {
        instFlags[VpInflightCounted] = true;
    }

    void
    clearVpInflightCounted()
    {
        instFlags[VpInflightCounted] = false;
    }
```

- [ ] **Step 7: Base-class facility.** In `src/cpu/o3/vp/base.hh`:
add `#include "cpu/o3/vp/vp_inflight_map.hh"`; DELETE the whole
`notifyRenamed(ThreadID)` method (its doc comment moves, updated, onto
`notifyRenamedInst`; `renamedInsts()`'s comment now says "fed once per
renamed instruction by rename.cc via notifyRenamedInst()"). Add to the
public section:

```cpp
    /** Per-predictor knob: the framework maintains the per-PC
     *  in-flight occurrence map below for this predictor (EVES-class
     *  extrapolating predictors). Keys are folded vpKey values, not
     *  thread-qualified — the same single-thread declared
     *  generalization as the burst-guard machinery (design doc,
     *  in-flight counter subsystem). Default false: every hook is
     *  inert and existing predictors are bit-identical. */
    virtual bool
    usesInflightCounts() const
    {
        return false;
    }

    /** Once per renamed instruction, from rename.cc AFTER the
     *  consumption ladder (an instruction never counts itself; a
     *  later same-cycle same-PC micro-op sees this one). Feeds the
     *  burst-guard rename count unconditionally and, for
     *  usesInflightCounts() predictors, the in-flight map (in-scope
     *  instructions only, marked VpInflightCounted). */
    void notifyRenamedInst(const DynInstPtr &inst);

    /** From the two squash walks (ROB::doSquash, CPU::squashInstIt):
     *  reclaim a counted instruction's in-flight count. Flag-guarded
     *  internally — callers need no eligibility logic; the
     *  VpInflightCounted bit makes it exactly-once across
     *  overlapping walks (the MRN-proven discipline). */
    void notifySquashedInFlight(const DynInstPtr &inst);

    /** Current in-flight occurrence count for a folded key. */
    uint32_t
    inflightCount(uint64_t key) const
    {
        return inflight.count(key);
    }
```

to the protected section, next to `renamedCount`:

```cpp
    /** Backing store for inflightCount() (design doc, in-flight
     *  counter subsystem). Touched only when some attached predictor
     *  sets usesInflightCounts(). */
    VpInflightMap inflight;
```

and to `VpStats`:

```cpp
        /** In-flight counter closure (usesInflightCounts()
         *  predictors): increments == decTrain + decSquash up to the
         *  live in-flight population at the dump boundary; the
         *  residual can never be negative. */
        statistics::Scalar inflightIncrements;
        statistics::Scalar inflightDecTrain;
        statistics::Scalar inflightDecSquash;
```

- [ ] **Step 8: base.cc implementations.** Add `#include
"cpu/o3/vp/vp_key.hh"` and:

```cpp
void
BaseValuePredictor::notifyRenamedInst(const DynInstPtr &inst)
{
    renamedCount[inst->threadNumber]++;
    if (!usesInflightCounts() || !inScope(inst)) {
        return;
    }
    inflight.increment(
        vpKey(inst->pcState().instAddr(), inst->pcState().microPC()));
    inst->setVpInflightCounted();
    stats.inflightIncrements++;
}

void
BaseValuePredictor::notifySquashedInFlight(const DynInstPtr &inst)
{
    if (!inst->vpInflightCounted()) {
        return;
    }
    inflight.decrement(
        vpKey(inst->pcState().instAddr(), inst->pcState().microPC()));
    inst->clearVpInflightCounted();
    stats.inflightDecSquash++;
}
```

At the TOP of `train()` — BEFORE the `inScope` early-return (spec §4:
flag implies counted implies always reclaim):

```cpp
    if (inst->vpInflightCounted()) {
        inflight.decrement(vpKey(inst->pcState().instAddr(),
                                 inst->pcState().microPC()));
        inst->clearVpInflightCounted();
        stats.inflightDecTrain++;
    }
```

Register the three stats in the `VpStats` ctor (after
`correctiveResetStale`):

```cpp
      ADD_STAT(inflightIncrements, statistics::units::Count::get(),
               "In-flight occurrence map increments at rename "
               "(usesInflightCounts() predictors only)"),
      ADD_STAT(inflightDecTrain, statistics::units::Count::get(),
               "In-flight occurrence map decrements at the train site"),
      ADD_STAT(inflightDecSquash, statistics::units::Count::get(),
               "In-flight occurrence map decrements from the squash "
               "walks"),
```

- [ ] **Step 9: Pipeline wiring.** `src/cpu/o3/rename.cc` — after the
consumption ladder's final block (`if (!vpBeforeMrn && valuePred &&
!inst->isMrned()) { consume_value_pred(); }`, ~line 953) and before
the `storesInProgress` bookkeeping:

```cpp
        // Garfield VP: per-renamed-instruction notification -- feeds
        // the burst-guard rename count and, for in-flight-counting
        // predictors, the per-PC occurrence map. Placed after the
        // consumption ladder so an instruction never counts itself
        // and a later same-cycle same-PC micro-op sees this one.
        if (valuePred) {
            valuePred->notifyRenamedInst(inst);
        }
```

`src/cpu/o3/rob.cc` — immediately after the existing
`vpPredicted() && !vpResolved()` block (~line 389):

```cpp
        // Garfield VP: reclaim this instruction's in-flight
        // occurrence count (predicted or not; flag-guarded inside).
        if (BaseValuePredictor *vp = cpu->getValuePred()) {
            vp->notifySquashedInFlight(squashing);
        }
```

`src/cpu/o3/cpu.cc` — immediately after the matching block in
`squashInstIt` (~line 1314), same code with `inst` and
`getValuePred()`.

- [ ] **Step 10: Build everything, rerun GTests.**
`LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ALL/gem5.opt build/ALL/cpu/o3/vp/vp_inflight_map.test.opt -j$(nproc)`
Expected: clean build; existing VP GTests
(`lvp_table.test.opt`, `vtage_tables.test.opt`,
`evtage_tables.test.opt`) still pass — run all four binaries.

- [ ] **Step 11: Bit-identity gate.**
`bash runs/eves_identity/run_gate.sh after_task1`, then for each of
the five configs:
`python3 runs/eves_identity/compare.py runs/eves_identity/baseline/<cfg>/stats.txt runs/eves_identity/after_task1/<cfg>/stats.txt`
Expected: `IDENTICAL (modulo new zero stats)` — the only new lines are
the three inflight counters at 0. Any DIFFERS/MISSING is a stop-fix.

- [ ] **Step 12: Commit** via the `git-commit` skill (runs
precommit-review + commit-note). Header:
`cpu-o3: Add VP per-PC in-flight occurrence counters`

---

### Task 2: EStrideTable core + arbitration helper + GTests

**Files:**
- Create: `src/cpu/o3/vp/estride_table.hh`,
  `src/cpu/o3/vp/estride_table.cc`, `src/cpu/o3/vp/eves_arbiter.hh`,
  `src/cpu/o3/vp/estride_table.test.cc`
- Modify: `src/cpu/o3/vp/SConscript`

**Interfaces:**
- Consumes: nothing from Task 1 (pure core; `inflight` arrives as a
  plain unsigned argument).
- Produces (Task 3 relies on these exact names):
  `EStrideTable(std::function<double()> rng)`;
  `EStrideLookup lookup(uint64_t key, unsigned inflight) const`
  with fields `{bool hit; bool blockedBySafeStride; bool predicted;
  RegVal value;}`;
  `std::vector<EStrideTrainOutcome> train(uint64_t key, RegVal actual,
  const EStrideClassifier &c)`;
  `bool safeStridePenalty()` (returns "crossed >= 0 to < 0");
  `int safeStride() const`; `EStridePeek peek(uint64_t key) const`;
  `EStrideClassifier {bool isLoad; bool notLlcMiss; bool notL2Miss;
  bool notL1Miss; bool fastInst; EStrideAllocClass allocClass;
  bool deliveredCorrect; bool stridePredicted;}`;
  `enum class EStrideAllocClass {AluOrStore, FpOrSlowAlu, Load,
  Never}`;
  `EvesArbiterOut evesArbitrate(const EvesArbiterIn &in)` in
  `eves_arbiter.hh` with
  `EvesArbiterIn {bool stridePredicted; RegVal strideValue;
  bool vtageHit; bool vtageConfident; RegVal vtageValue;
  bool blackoutActive; bool overwriteRequiresConfidence;}` and
  `EvesArbiterOut {std::optional<RegVal> value; bool stridePredicted;
  bool vtageConfident; bool deliveredByVtage;}`.

**Verbatim algorithm reference (transcribe EXACTLY; spec §3 governs):**

Geometry constants (spec §3.1; h:59-62):

```cpp
    static constexpr unsigned NumWays = 3;              // NBWAYSTR
    static constexpr unsigned LogSets = 4;              // LOGSTR
    static constexpr unsigned NumEntries = NumWays * (1u << LogSets);
    static constexpr unsigned TagBits = 14;             // TAGWIDTHSTR
    static constexpr unsigned ConfBits = 5;             // WIDTHCONFIDSTR
    static constexpr unsigned ConfMax = (1u << ConfBits) - 1;   // 31
    static constexpr unsigned ConfThreshold = ConfMax / 4;      // 7
    static constexpr unsigned ConfDecay = 1u << (ConfBits - 3); // 4
    static constexpr int SafeStrideCap = (1 << 15) - 1;         // 32767
    static constexpr uint64_t StrideSentinel = 0xffff;          // cc:299
```

Entry + state (zero-initialized, NO valid bit — a key hashing to tag 0
hits a virgin entry and trains via the first-occurrence arm, spec
§3.1):

```cpp
    struct Entry
    {
        uint64_t lastValue = 0; // last COMMITTED value
        uint64_t stride = 0;    // full width; 20 bits is accounting
        uint8_t conf = 0;
        int u = 0;              // invariant 0..3, asserted
        uint16_t tag = 0;
        bool notFirstOcc = false;
    };
    std::array<Entry, NumEntries> table{};
    int safeStride_ = 0;        // single GLOBAL counter (h:128)
    std::function<double()> rng;
```

Way hashes (verbatim cc:69-87 with the folded key in place of
pc+piece; the source's unreachable `j < 0` clamp is dropped — j =
NumWays − way is always in {1,2,3}):

```cpp
unsigned
EStrideTable::wayIndex(uint64_t key, unsigned way)
{
    return ((key ^ (key >> (2 * LogSets - way)) ^
             (key >> (LogSets - way)) ^ (key >> (3 * LogSets - way))) *
                NumWays +
            way) %
           NumEntries;
}

uint64_t
EStrideTable::wayTag(uint64_t key, unsigned way)
{
    const unsigned j = NumWays - way;
    return ((key >> (LogSets - j)) ^ (key >> (2 * LogSets - j)) ^
            (key >> (3 * LogSets - j)) ^ (key >> (4 * LogSets - j))) &
           ((1u << TagBits) - 1);
}
```

`lookup(key, inflight)` (gates in source order, cc:99-118): first
tag-matching way 0→2 (`findEntry(key)` helper returning the index or
−1, shared with train). No hit → all-false. On a hit:
`predicted = safeStride_ >= 0 && e.conf >= ConfThreshold`; when
predicted,

```cpp
    out.value = static_cast<uint64_t>(
        static_cast<int64_t>(e.lastValue) +
        (static_cast<int64_t>(inflight) + 1) *
            static_cast<int64_t>(e.stride));
```

`blockedBySafeStride = safeStride_ < 0 && e.conf >= ConfThreshold`
(the would-have-predicted rejection — a stat refinement, not a
behavior change; spec §3.2 gates are conjunctive).

`train(key, actual, c)` — order matters, transcribe exactly:

1. SafeStride tick (pre-checked cap, cc:809-810):
   `if (safeStride_ < SafeStrideCap) safeStride_++;`
2. SafeStride credit (flag-keyed, pre-check-then-add — CAN overshoot
   to 32774, cc:815-817):
   `if (c.deliveredCorrect && c.stridePredicted && safeStride_ <
   SafeStrideCap) { safeStride_ += 4 * (1 + (c.isLoad ? 1 : 0));
   outcomes SafeStrideCredited; }`
3. `findEntry(key)`. On a HIT: read `lastValueOld = e.lastValue`;
   `oneStep = (uint64_t)((int64_t)lastValueOld + (int64_t)e.stride)`;
   `delta = (int64_t)actual - (int64_t)lastValueOld`; range window
   OVERFLOW-FREE (spec deviation 8):
   `inRange = delta >= -(int64_t{1} << 19) + 1 && delta <= (int64_t{1}
   << 19)`; `strideCandidate = inRange ? (uint64_t)delta : 0;` then
   `e.lastValue = actual;` UNCONDITIONALLY before any branch (cc:241).
   - `e.notFirstOcc` TRUE and `oneStep == actual` (raw arithmetic
     identity, cc:230-246 — never compared against strideCandidate):
     saturation guards OUTSIDE the draws (zero draws at saturation):
     `if (e.conf < ConfMax) { conf++ iff confIncrementDraw(c,
     (int64_t)strideCandidate) -> ConfInc else ConfHeld; }`
     `if (e.u < 3) { u++ iff an INDEPENDENT confIncrementDraw(...) ->
     UInc else UHeld; }`
     `if (e.conf >= ConfThreshold && e.u != 3) { e.u = 3;
     UJamSaturated; } else if (e.conf >= ConfThreshold) e.u = 3;`
     (write unconditional as in cc:260-261; the outcome only on an
     actual change).
   - `e.notFirstOcc` TRUE and mismatch (cc:263-284):
     `if (e.conf > ConfDecay) { e.conf -= ConfDecay;
     MispredictDecay; } else { e.conf = 0; e.u = 0;
     MispredictCollapse; }` then `e.notFirstOcc = false;`
     (conf == 4 COLLAPSES — the boundary GTest pins it). Stride
     untouched.
   - `e.notFirstOcc` FALSE (first occurrence, cc:286-305):
     `if (strideCandidate != 0) { e.stride = strideCandidate;
     StrideSet; } else { e.stride = StrideSentinel; e.conf = 0;
     e.u = 0; SentinelDemoted; }` then `e.notFirstOcc = true;`
4. On a MISS: `if (c.deliveredCorrect) { AllocSkippedDeliveredCorrect;
   } else if (!allocationDraw(c)) { AllocDrawRefused; } else
   allocateVictim(key, actual, outcomes);`

`confIncrementDraw(c, stride)` (cc:149-162; spec §3.4):

```cpp
bool
EStrideTable::confIncrementDraw(const EStrideClassifier &c,
                                int64_t stride)
{
    // Deterministic conjunct short-circuits ahead of every draw: a
    // correct prediction covered by VTAGE alone (delivered-correct
    // without the stride flag) must not warm the stride entry.
    if (c.deliveredCorrect && !c.stridePredicted) {
        return false;
    }
    const unsigned exponent = c.notLlcMiss + c.notL2Miss +
                              c.notL1Miss + 2 * c.fastInst +
                              2 * !c.isLoad;
    // 1 draw; doubled at stride >= 8 and again at stride >= 64 --
    // SIGNED comparisons (the source's abs-of-a-boolean quirk,
    // cc:154-155): negative strides never get the extra draws.
    unsigned draws = 1;
    if (stride >= 8) {
        draws *= 2;
    }
    if (stride >= 64) {
        draws *= 2;
    }
    bool passed = false;
    for (unsigned i = 0; i < draws && !passed; i++) {
        passed = bernoulli(exponent);
    }
    // Small-stride load throttle (cc:156-159): stride-0 loads never
    // pass; -1 draws an extra 1/2 coin, +1 an extra 1/4 coin. The
    // coin is drawn only when its stride case applies (clean draw
    // discipline; probability-equivalent to the source's
    // both-sides-evaluated bitwise &).
    bool filter = std::llabs(stride) > 1 || !c.isLoad;
    if (!filter && stride == -1) {
        filter = bernoulli(1);
    }
    if (!filter && stride == 1) {
        filter = bernoulli(2);
    }
    return passed && filter;
}

bool
EStrideTable::bernoulli(unsigned exponent)
{
    // p = 2^-exponent; exponent 0 always passes (rng() in [0, 1)).
    return rng() < std::ldexp(1.0, -static_cast<int>(exponent));
}
```

`allocationDraw(c)` (cc:166-197): AluOrStore → `bernoulli(6)` (1/64);
FpOrSlowAlu → `bernoulli(4)` (1/16); Load → `bernoulli(c.notLlcMiss +
c.notL2Miss + c.notL1Miss + c.fastInst)`; Never → `false` (no draw
consumed).

`allocateVictim(key, actual, outcomes)` (cc:312-359): starting way
`unsigned way = static_cast<unsigned>(rng() * NumWays);` (one draw).
Pass 1 over 3 ways from `way`: claim the first with `conf == 0`;
pass 2: claim the first with `u == 0`. Install on claim (way w):
`{conf = 1 /* survive pass 1 until the first stride observation,
cc:320 */, u = 0, tag = wayTag(key, w), stride = 0, notFirstOcc =
false, lastValue = actual}` → outcome `AllocatedConfZeroVictim` /
`AllocatedUZeroVictim`. Both passes fail → age the LAST-probed way's
entry: `gem5_assert(e.u > 0)` (pass 2 would have claimed u == 0), then
`u--` with probability `bernoulli(2 + 2 * (e.conf > ConfMax / 8) +
2 * (e.conf >= ConfThreshold))` → `AllocAged` else `AllocAgeHeld`.

`safeStridePenalty()` (cc:823-824, no lower clamp):

```cpp
bool
EStrideTable::safeStridePenalty()
{
    const bool was_non_negative = safeStride_ >= 0;
    safeStride_ -= 1024;
    return was_non_negative && safeStride_ < 0;
}
```

`peek(key)` (test/stat support, mirrors EVtageProviderPeek's purpose):
returns `{bool hit; unsigned conf; int u; bool notFirstOcc; uint64_t
stride; uint64_t lastValue;}` for the first tag-matching way.

Outcome enum (exact spelling):

```cpp
enum class EStrideTrainOutcome
{
    ConfInc,
    ConfHeld,
    UInc,
    UHeld,
    UJamSaturated,
    MispredictDecay,
    MispredictCollapse,
    StrideSet,
    SentinelDemoted,
    AllocatedConfZeroVictim,
    AllocatedUZeroVictim,
    AllocAged,
    AllocAgeHeld,
    AllocDrawRefused,
    AllocSkippedDeliveredCorrect,
    SafeStrideCredited,
};
```

`eves_arbiter.hh` (header-only, pure — spec §5's exact rule):

```cpp
#ifndef __CPU_O3_VP_EVES_ARBITER_HH__
#define __CPU_O3_VP_EVES_ARBITER_HH__

#include <optional>

#include "base/types.hh"

namespace gem5
{
namespace o3
{

/**
 * EVES component arbitration (design doc docs/superpowers/specs/
 * 2026-08-14-estride-design.md, "Arbitration and token"): pure
 * function over POD inputs so every flag/mode combination is directly
 * GTest-able. Reproduces the CVP-1 source's write-order mechanism
 * (getPredStride first, getPredVtage second overwriting the value,
 * cc:136-144): with overwriteRequiresConfidence false (the verbatim
 * default), a VTAGE tag hit outside the blackout overwrites the
 * stride value even below VTAGE confidence — delivery still requires
 * a component flag (stride or VTAGE confident), matching the source's
 * predstride || predvtage use-bit.
 */
struct EvesArbiterIn
{
    bool stridePredicted = false;
    RegVal strideValue = 0;
    bool vtageHit = false;
    bool vtageConfident = false; // implies vtageHit
    RegVal vtageValue = 0;
    bool blackoutActive = false;
    bool overwriteRequiresConfidence = false;
};

struct EvesArbiterOut
{
    std::optional<RegVal> value; // engaged iff delivering
    bool stridePredicted = false;   // CVP predstride (token bit)
    bool vtageConfident = false;    // CVP predvtage (token bit)
    bool deliveredByVtage = false;  // gem5-only routing (token bit)
};

inline EvesArbiterOut
evesArbitrate(const EvesArbiterIn &in)
{
    EvesArbiterOut out;
    // The blackout suppresses the WHOLE VTAGE contribution -- value
    // and flag -- as in the source's LastMispVT >= 128 wrapper
    // (cc:44-55).
    const bool vtage_contributes = in.vtageHit && !in.blackoutActive;
    const bool overwrite =
        vtage_contributes &&
        (!in.overwriteRequiresConfidence || in.vtageConfident);
    out.stridePredicted = in.stridePredicted;
    out.vtageConfident = in.vtageConfident && !in.blackoutActive;
    if (out.stridePredicted || out.vtageConfident) {
        out.value = overwrite ? in.vtageValue : in.strideValue;
        out.deliveredByVtage = overwrite;
    }
    return out;
}

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_EVES_ARBITER_HH__
```

- [ ] **Step 1: Write the failing GTests.** Create
`src/cpu/o3/vp/estride_table.test.cc`. Test scaffolding: a scripted
RNG that returns queued doubles and counts consumption —

```cpp
#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <deque>
#include <vector>

#include "cpu/o3/vp/estride_table.hh"
#include "cpu/o3/vp/eves_arbiter.hh"

using namespace gem5;
using namespace gem5::o3;

namespace
{

/** Scripted RNG: pops queued values; counts every draw. 0.0 always
 *  passes any bernoulli; 0.999... fails any exponent >= 1 (an
 *  exponent-0 draw passes regardless -- p = 1). */
struct ScriptedRng
{
    std::deque<double> values;
    unsigned draws = 0;

    double
    operator()()
    {
        draws++;
        if (values.empty()) {
            return 0.0;
        }
        double v = values.front();
        values.pop_front();
        return v;
    }
};

/** A classifier for an LLC-missing load (every latency term false):
 *  exponent 0 -- confidence and allocation draws pass at p = 1. */
EStrideClassifier
llcMissLoad()
{
    EStrideClassifier c;
    c.isLoad = true;
    c.notLlcMiss = false;
    c.notL2Miss = false;
    c.notL1Miss = false;
    c.fastInst = false;
    c.allocClass = EStrideAllocClass::Load;
    return c;
}

/** Drive key from freshly-allocated to a confident strided entry:
 *  miss-allocate at v0, then occurrences v0+s, v0+2s, ... until
 *  peek(key).conf >= EStrideTable::ConfThreshold. */
void
warmToConfident(EStrideTable &t, uint64_t key, uint64_t v0, int64_t s)
{
    const EStrideClassifier c = llcMissLoad();
    uint64_t v = v0;
    t.train(key, v, c); // allocate
    v += s;
    t.train(key, v, c); // first occurrence: stride set
    while (t.peek(key).conf < EStrideTable::ConfThreshold) {
        v += s;
        t.train(key, v, c);
    }
}

} // anonymous namespace
```

Then the tests, each pinning a spec §3/§5 arm (write ALL of these):

```cpp
TEST(EStrideTable, VirginTableTagZeroHitsAndTrainsWithoutAllocating)
{
    // Spec S3.1: zero-init, no valid bit. Find a key whose way-0 tag
    // is 0; its first train() must go down the HIT path (first-
    // occurrence arm on the virgin entry), never the allocation path.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0;
    while (EStrideTable::wayTag(key, 0) != 0) {
        key += 64;
    }
    auto out = t.train(key, 700, llcMissLoad());
    ASSERT_EQ(out.size(), 1u);
    // delta = 700 - 0 in range and nonzero -> StrideSet, not any
    // Allocated* outcome.
    EXPECT_EQ(out[0], EStrideTrainOutcome::StrideSet);
    EXPECT_EQ(t.peek(key).stride, 700u);
}

TEST(EStrideTable, SafeStrideStartsAtZeroAndGatePassesFromCycleOne)
{
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    EXPECT_EQ(t.safeStride(), 0);
    uint64_t key = 0x1000;
    warmToConfident(t, key, 100, 8);
    EXPECT_TRUE(t.lookup(key, 0).predicted);
}

TEST(EStrideTable, PredictionExtrapolatesByInflightPlusOne)
{
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0x2000;
    warmToConfident(t, key, 1000, 24);
    const uint64_t last = t.peek(key).lastValue;
    EXPECT_EQ(t.lookup(key, 0).value, last + 24);
    EXPECT_EQ(t.lookup(key, 3).value, last + 4 * 24);
}

TEST(EStrideTable, NegativeStrideExtrapolatesSigned)
{
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0x3000;
    warmToConfident(t, key, 100000, -16);
    const uint64_t last = t.peek(key).lastValue;
    EXPECT_EQ(t.lookup(key, 2).value, last - 3 * 16);
}

TEST(EStrideTable, ConfSixDoesNotPredictConfSevenDoes)
{
    // Threshold endpoint (spec S3.2: conf >= 7 of 31).
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0x4000;
    const EStrideClassifier c = llcMissLoad();
    uint64_t v = 500;
    t.train(key, v, c);
    v += 8;
    t.train(key, v, c);
    while (t.peek(key).conf < EStrideTable::ConfThreshold - 1) {
        v += 8;
        t.train(key, v, c);
    }
    EXPECT_EQ(t.peek(key).conf, EStrideTable::ConfThreshold - 1);
    EXPECT_FALSE(t.lookup(key, 0).predicted);
    v += 8;
    t.train(key, v, c);
    EXPECT_EQ(t.peek(key).conf, EStrideTable::ConfThreshold);
    EXPECT_TRUE(t.lookup(key, 0).predicted);
}

TEST(EStrideTable, SafeStrideBlocksBeforeConfidence)
{
    // Gate order (spec S3.2): a saturating-confidence entry is
    // blocked while SafeStride < 0, and blockedBySafeStride reports
    // exactly the would-have-predicted case.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0x5000;
    warmToConfident(t, key, 100, 8);
    EXPECT_TRUE(t.safeStridePenalty()); // 0 -> -1024, crossed
    EXPECT_EQ(t.safeStride(), -1024);
    const EStrideLookup l = t.lookup(key, 0);
    EXPECT_TRUE(l.hit);
    EXPECT_FALSE(l.predicted);
    EXPECT_TRUE(l.blockedBySafeStride);
}

TEST(EStrideTable, SafeStrideTickCreditPenaltyArithmetic)
{
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0x6000;
    // Tick: +1 per train call.
    t.train(key, 1, llcMissLoad());
    EXPECT_EQ(t.safeStride(), 1);
    // Credit: deliveredCorrect && stridePredicted, load -> +8 on top
    // of the tick.
    EStrideClassifier c = llcMissLoad();
    c.deliveredCorrect = true;
    c.stridePredicted = true;
    auto out = t.train(key, 9, c);
    EXPECT_NE(std::find(out.begin(), out.end(),
                        EStrideTrainOutcome::SafeStrideCredited),
              out.end());
    EXPECT_EQ(t.safeStride(), 1 + 1 + 8);
    // Non-load credit is +4.
    // Penalty: -1024, no lower clamp; stacking goes far below zero.
    EXPECT_TRUE(t.safeStridePenalty());
    EXPECT_FALSE(t.safeStridePenalty()); // already negative: no cross
    EXPECT_EQ(t.safeStride(), 10 - 2048);
}

TEST(EStrideTable, SafeStrideCapIsPreCheckedAndCanOvershoot)
{
    // Spec S3.5: the 32767 cap is a PRE-check -- from 32766 a load
    // credit legally lands the counter at 32774; further ticks and
    // credits are then refused.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    t.setSafeStrideForTest(32765);
    uint64_t key = 0x7000;
    EStrideClassifier c = llcMissLoad();
    c.deliveredCorrect = true;
    c.stridePredicted = true;
    t.train(key, 1, c); // tick 32765->32766 (< cap), credit +8
    EXPECT_EQ(t.safeStride(), 32774);
    t.train(key, 2, c); // tick refused, credit refused (>= cap)
    EXPECT_EQ(t.safeStride(), 32774);
}

TEST(EStrideTable, MispredictDecaysByFourAndConfFourCollapses)
{
    // Spec S3.3: conf > 4 -> conf -= 4 with u untouched; conf == 4
    // -> {0, 0}. Drive an entry to conf 8 / u 3, break the sequence.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0x8000;
    const EStrideClassifier c = llcMissLoad();
    warmToConfident(t, key, 100, 8); // conf >= 7 -> u jammed to 3
    while (t.peek(key).conf != 8) {
        uint64_t v = t.peek(key).lastValue;
        t.train(key, v + 8, c);
        ASSERT_LE(t.peek(key).conf, 8u);
    }
    auto out = t.train(key, t.peek(key).lastValue + 999, c);
    EXPECT_NE(std::find(out.begin(), out.end(),
                        EStrideTrainOutcome::MispredictDecay),
              out.end());
    EXPECT_EQ(t.peek(key).conf, 4u);
    EXPECT_EQ(t.peek(key).u, 3);            // u survives the decay
    EXPECT_FALSE(t.peek(key).notFirstOcc);  // stride learning restarts
    // Re-establish the (same) stride, then break again at conf 4+...
    t.train(key, t.peek(key).lastValue + 8, c); // first-occ: StrideSet
    auto out2 = t.train(key, t.peek(key).lastValue + 999, c);
    // conf was 4 (== ConfDecay): the collapse arm fires.
    EXPECT_NE(std::find(out2.begin(), out2.end(),
                        EStrideTrainOutcome::MispredictCollapse),
              out2.end());
    EXPECT_EQ(t.peek(key).conf, 0u);
    EXPECT_EQ(t.peek(key).u, 0);
}

TEST(EStrideTable, ConstantValueSentinelDemotionLoop)
{
    // Spec S3.3: the 2-cycle sentinel loop for constant values --
    // conf and u pinned at 0, stride = 0xffff, notFirstOcc
    // oscillates; the entry stays a victim candidate forever.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0x9000;
    const EStrideClassifier c = llcMissLoad();
    t.train(key, 42, c); // allocate (conf = 1)
    for (int i = 0; i < 6; i++) {
        auto out = t.train(key, 42, c);
        const auto &want =
            (i % 2 == 0) ? EStrideTrainOutcome::SentinelDemoted
                         : EStrideTrainOutcome::MispredictCollapse;
        EXPECT_NE(std::find(out.begin(), out.end(), want), out.end())
            << "iteration " << i;
    }
    EXPECT_EQ(t.peek(key).conf, 0u);
    EXPECT_EQ(t.peek(key).u, 0);
    EXPECT_EQ(t.peek(key).stride, EStrideTable::StrideSentinel);
}

TEST(EStrideTable, RangeWindowAsymmetricEndpoints)
{
    // Spec S3.3 / deviation 8: delta in [-2^19 + 1, +2^19]. +2^19 is
    // accepted as a stride; -2^19 is rejected (sentinel path).
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    const EStrideClassifier c = llcMissLoad();
    const int64_t kPos = int64_t{1} << 19;

    uint64_t key = 0xA000;
    t.train(key, 1000, c);
    auto out = t.train(key, 1000 + kPos, c);
    EXPECT_NE(std::find(out.begin(), out.end(),
                        EStrideTrainOutcome::StrideSet),
              out.end());
    EXPECT_EQ(t.peek(key).stride, static_cast<uint64_t>(kPos));

    uint64_t key2 = 0xB000;
    t.train(key2, 10000000, c);
    auto out2 = t.train(key2, 10000000 - kPos, c);
    EXPECT_NE(std::find(out2.begin(), out2.end(),
                        EStrideTrainOutcome::SentinelDemoted),
              out2.end());
}

TEST(EStrideTable, RangeWindowHugeDeltaRejectedOverflowFree)
{
    // Spec S3.3: near-2^63 deltas must reject cleanly (the source's
    // raw abs(2*delta - 1) is UB here; our interval test is not).
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    const EStrideClassifier c = llcMissLoad();
    uint64_t key = 0xC000;
    t.train(key, 0, c);
    auto out = t.train(key, 0x8000000000000000ull, c);
    EXPECT_NE(std::find(out.begin(), out.end(),
                        EStrideTrainOutcome::SentinelDemoted),
              out.end());
}

TEST(EStrideTable, OutOfRangeDeltaOnTrainedEntryTakesMismatchArm)
{
    // Spec S10: a trained entry hit with an out-of-range delta routes
    // down the one-step-mismatch arm (raw identity check), never the
    // sentinel arm.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0xD000;
    warmToConfident(t, key, 100, 8);
    const unsigned conf_before = t.peek(key).conf;
    auto out =
        t.train(key, t.peek(key).lastValue + (uint64_t{1} << 40),
                llcMissLoad());
    EXPECT_NE(std::find(out.begin(), out.end(),
                        EStrideTrainOutcome::MispredictDecay),
              out.end());
    EXPECT_EQ(t.peek(key).conf, conf_before - 4);
}

TEST(EStrideTable, DrawCountsByStrideRegimeAndSignedExclusion)
{
    // Spec S3.4: 1/2/4 draws by SIGNED stride regime; zero draws at
    // saturation; the deterministic conjunct consumes no draws.
    // Exponent > 0 so a draw is actually consumed: use an L1-hit load
    // (notLlc/notL2/notL1 true, fastInst false -> E = 3).
    EStrideClassifier c;
    c.isLoad = true;
    c.allocClass = EStrideAllocClass::Load;
    // (notLlcMiss/notL2Miss/notL1Miss default true, fastInst false)

    auto drawsForStride = [&](int64_t stride_val, uint64_t key) {
        ScriptedRng rng;
        EStrideTable t([&rng] { return rng(); });
        const EStrideClassifier alloc = llcMissLoad();
        t.train(key, 1 << 20, alloc);              // no draw (miss+p=1
                                                   // alloc: 1 draw at
                                                   // exponent 0 + 1
                                                   // way draw)
        t.train(key, (1 << 20) + stride_val, alloc); // StrideSet
        const unsigned before = rng.draws;
        // All queued fails: every conf draw AND u draw consumed.
        rng.values.assign(20, 0.999999);
        t.train(key, (1 << 20) + 2 * stride_val, c); // one-step match
        return rng.draws - before;
    };
    // conf: k draws (all fail) + u: k draws (all fail); no filter
    // coin (|stride| > 1).
    EXPECT_EQ(drawsForStride(4, 0xE000), 2u * 1u);
    EXPECT_EQ(drawsForStride(8, 0xE100), 2u * 2u);
    EXPECT_EQ(drawsForStride(64, 0xE200), 2u * 4u);
    EXPECT_EQ(drawsForStride(-64, 0xE300), 2u * 1u); // negative: k=1
}

TEST(EStrideTable, SaturatedCountersConsumeZeroDraws)
{
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0xE400;
    const EStrideClassifier c = llcMissLoad();
    warmToConfident(t, key, 0, 8);
    while (t.peek(key).conf < EStrideTable::ConfMax) {
        t.train(key, t.peek(key).lastValue + 8, c);
    }
    const unsigned before = rng.draws;
    t.train(key, t.peek(key).lastValue + 8, c);
    // conf saturated (31) and u jammed (3): zero increment draws.
    EXPECT_EQ(rng.draws, before);
}

TEST(EStrideTable, DeliveredCorrectWithoutStrideFlagBlocksWarming)
{
    // The deterministic conjunct (spec S3.4): VTAGE-covered correct
    // commits never warm the stride entry -- and consume no draws.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0xE500;
    EStrideClassifier c = llcMissLoad();
    t.train(key, 0, c);
    t.train(key, 8, c);
    const unsigned conf_before = t.peek(key).conf;
    const unsigned before = rng.draws;
    c.deliveredCorrect = true; // stridePredicted stays false
    t.train(key, 16, c);
    EXPECT_EQ(t.peek(key).conf, conf_before);
    EXPECT_EQ(rng.draws, before);
}

TEST(EStrideTable, UnitStrideLoadThrottles)
{
    // stride +1 loads: conf draw passes, then a 1/4 coin decides; the
    // coin is one extra draw. stride 0 never passes (covered by the
    // sentinel tests -- a zero stride never trains the match arm).
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    uint64_t key = 0xE600;
    const EStrideClassifier c = llcMissLoad(); // exponent 0: p = 1
    t.train(key, 100, c);
    t.train(key, 101, c); // stride +1 set
    // conf draw auto-passes (E=0 -> one consumed draw at p=1); coin
    // 0.999 fails -> ConfHeld. Same for u. 4 draws total.
    rng.values.assign({0.0, 0.999, 0.0, 0.999});
    const unsigned before = rng.draws;
    auto out = t.train(key, 102, c);
    EXPECT_EQ(rng.draws - before, 4u);
    EXPECT_NE(std::find(out.begin(), out.end(),
                        EStrideTrainOutcome::ConfHeld),
              out.end());
    // Coin passes (< 0.25): conf increments. NOTE the entry was
    // installed at conf = 1 (the allocation seed), so the increment
    // lands it at 2.
    rng.values.assign({0.0, 0.2, 0.0, 0.999});
    t.train(key, 103, c);
    EXPECT_EQ(t.peek(key).conf, 2u);
}

TEST(EStrideTable, AllocationLadderPerClass)
{
    // AluOrStore 1/64, FpOrSlowAlu 1/16, Load by latency, Never no
    // draw at all. Verify via draw consumption + pass/fail edges.
    auto tryAlloc = [](EStrideAllocClass klass, bool is_load,
                       double first_draw, unsigned key) {
        ScriptedRng rng;
        EStrideTable t([&rng] { return rng(); });
        EStrideClassifier c;
        c.isLoad = is_load;
        c.allocClass = klass;
        // Load latency terms: L1-hit load (E' = 3) when is_load.
        rng.values.assign({first_draw, 0.0}); // alloc draw, way draw
        const unsigned before = rng.draws;
        auto out = t.train(key, 777, c);
        return std::make_pair(out, rng.draws - before);
    };
    // AluOrStore: p = 1/64. 0.9 fails; 0.01 passes.
    {
        auto [out, draws] =
            tryAlloc(EStrideAllocClass::AluOrStore, false, 0.9, 0xF000);
        EXPECT_EQ(out[0], EStrideTrainOutcome::AllocDrawRefused);
        EXPECT_EQ(draws, 1u);
    }
    {
        auto [out, draws] = tryAlloc(EStrideAllocClass::AluOrStore,
                                     false, 1.0 / 128, 0xF100);
        EXPECT_EQ(out[0], EStrideTrainOutcome::AllocatedConfZeroVictim);
        EXPECT_EQ(draws, 2u); // alloc draw + way draw
    }
    // Never: zero draws, no outcome... actually AllocDrawRefused is
    // pushed (the draw "fails" deterministically without consuming
    // rng) -- assert exactly that:
    {
        auto [out, draws] =
            tryAlloc(EStrideAllocClass::Never, false, 0.9, 0xF200);
        EXPECT_EQ(out[0], EStrideTrainOutcome::AllocDrawRefused);
        EXPECT_EQ(draws, 0u);
    }
}

TEST(EStrideTable, AllocSkippedWhenDeliveredCorrect)
{
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    EStrideClassifier c = llcMissLoad();
    c.deliveredCorrect = true;
    auto out = t.train(0xF300, 5, c);
    // Only the skip outcome (plus no SafeStride credit: the stride
    // flag is false).
    ASSERT_EQ(out.size(), 1u);
    EXPECT_EQ(out[0],
              EStrideTrainOutcome::AllocSkippedDeliveredCorrect);
}

TEST(EStrideTable, VictimPassOrderAndInstallState)
{
    // Fill all three ways of one set-group with confident entries,
    // then allocate a fourth key mapping there: pass 1 finds no
    // conf == 0, pass 2 finds no u == 0 (jammed to 3), so aging fires
    // on the last-probed way. Then drain one entry's u to 0 via
    // repeated aging and watch pass 2 claim it.
    // (Keys colliding in ways are found by scanning: for the test,
    // brute-force four keys whose wayIndex sets overlap on all three
    // ways -- see the helper below.)
    // Helper: find keys k1..k3 that fully occupy the ways key0 maps
    // to. With 16 sets/way this is a short scan.
    ScriptedRng rng;
    EStrideTable t([&rng] { return rng(); });
    const uint64_t key0 = 0x10000;
    unsigned idx[3] = {EStrideTable::wayIndex(key0, 0),
                       EStrideTable::wayIndex(key0, 1),
                       EStrideTable::wayIndex(key0, 2)};
    // Occupy each way with a confident entry through key0 itself is
    // impossible (one key, one entry), so use keys that alias:
    // The scripted RNG's empty-queue 0.0 makes every allocation start
    // at way 0 and claim the occupant key's OWN way-0 slot, so search
    // on wayIndex(k, 0) specifically.
    std::vector<uint64_t> occupants;
    for (uint64_t k = 0x20000; occupants.size() < 3; k += 8) {
        if (EStrideTable::wayIndex(k, 0) == idx[occupants.size()] &&
            std::find(occupants.begin(), occupants.end(), k) ==
                occupants.end()) {
            occupants.push_back(k);
        }
    }
    for (uint64_t k : occupants) {
        warmToConfident(t, k, 100, 8); // conf >= 7, u = 3
    }
    // Precondition: key0 itself must MISS all three ways (no
    // accidental tag alias with an occupant's installed tag).
    ASSERT_FALSE(t.peek(key0).hit);
    // Aging draw: entry conf >= 7 -> exponent 2+2+2 = 6 (p = 1/64).
    // Script: alloc draw passes (exponent 0 for LLC-miss load), way
    // draw 0.0 -> start way 0, aging draw passes.
    rng.values.assign({0.0, 0.0, 0.0});
    auto out = t.train(key0, 999, llcMissLoad());
    EXPECT_NE(std::find(out.begin(), out.end(),
                        EStrideTrainOutcome::AllocAged),
              out.end());
}

TEST(EStrideArbiter, FlagModeCrossProduct)
{
    // Spec S5/S10: pin payload selection, delivery, and the three
    // token bits over the full cross product.
    auto arb = [](bool sp, bool vh, bool vc, bool blackout,
                  bool require_conf) {
        EvesArbiterIn in;
        in.stridePredicted = sp;
        in.strideValue = 111;
        in.vtageHit = vh;
        in.vtageConfident = vc;
        in.vtageValue = 222;
        in.blackoutActive = blackout;
        in.overwriteRequiresConfidence = require_conf;
        return evesArbitrate(in);
    };
    // Verbatim mode: low-conf VTAGE hit CLOBBERS a confident stride.
    {
        auto o = arb(true, true, false, false, false);
        ASSERT_TRUE(o.value.has_value());
        EXPECT_EQ(*o.value, 222u);
        EXPECT_TRUE(o.stridePredicted);
        EXPECT_FALSE(o.vtageConfident);
        EXPECT_TRUE(o.deliveredByVtage);
    }
    // Ablation mode: the same case delivers the STRIDE value.
    {
        auto o = arb(true, true, false, false, true);
        ASSERT_TRUE(o.value.has_value());
        EXPECT_EQ(*o.value, 111u);
        EXPECT_FALSE(o.deliveredByVtage);
    }
    // Flag-less tag hit delivers NOTHING in either mode.
    {
        auto o = arb(false, true, false, false, false);
        EXPECT_FALSE(o.value.has_value());
        EXPECT_FALSE(o.deliveredByVtage);
    }
    // Both confident: VTAGE wins (either mode).
    {
        auto o = arb(true, true, true, false, false);
        EXPECT_EQ(*o.value, 222u);
        EXPECT_TRUE(o.deliveredByVtage);
        EXPECT_TRUE(o.stridePredicted);
        EXPECT_TRUE(o.vtageConfident);
    }
    // Blackout suppresses value AND flag: stride survives untouched.
    {
        auto o = arb(true, true, true, true, false);
        EXPECT_EQ(*o.value, 111u);
        EXPECT_FALSE(o.vtageConfident);
        EXPECT_FALSE(o.deliveredByVtage);
    }
    // VTAGE-only confident delivery.
    {
        auto o = arb(false, true, true, false, false);
        EXPECT_EQ(*o.value, 222u);
        EXPECT_TRUE(o.deliveredByVtage);
    }
    // Nothing anywhere.
    {
        auto o = arb(false, false, false, false, false);
        EXPECT_FALSE(o.value.has_value());
    }
}
```

Also add a u-invariant death/assert test if `gem5_assert` fires in
`.opt` test builds (it does — GTest binaries build with TRACING_ON):
constructing the aging state with u == 0 through the public API is
impossible (that is the invariant); document with a comment instead of
a test.

- [ ] **Step 2: Register and run to verify failure.** SConscript:

```python
    Source('estride_table.cc')
    GTest('estride_table.test', 'estride_table.test.cc',
          'estride_table.cc')
```

Build the test target — expected: compile FAIL (missing headers).

- [ ] **Step 3: Implement `estride_table.hh`, `estride_table.cc`,
`eves_arbiter.hh`** exactly per the "Verbatim algorithm reference"
block above. The header carries the class doc comment citing the CVP-1
source (Seznec, CVP-1 2018, cvp8KB/mypredictor.cc) and the spec path,
declares everything from the Interfaces block, plus the test-support
members: `static unsigned wayIndex(uint64_t, unsigned)`,
`static uint64_t wayTag(uint64_t, unsigned)` (public and static so
tests can precompute collisions), `void setSafeStrideForTest(int v)`
(sets `safeStride_`; name says what it is for), and `EStridePeek
peek(uint64_t) const`. `train()` returns outcomes in event order.

- [ ] **Step 4: Run the GTests until all pass.**
`LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ALL/cpu/o3/vp/estride_table.test.opt`
then run the binary. Expected: every test above PASSES. Iterate on
transcription bugs here — this suite IS the fidelity net.

- [ ] **Step 5: Full build + existing tests still green.**
`scons build/ALL/gem5.opt` (with the LD_LIBRARY_PATH prefix) and rerun
the other three VP GTest binaries.

- [ ] **Step 6: Commit** via `git-commit`. Header:
`cpu-o3: Add the E-Stride table core and EVES arbiter`

---

### Task 3: EvesVP SimObject, config plumbing, smokes

**Files:**
- Create: `src/cpu/o3/vp/eves.hh`, `src/cpu/o3/vp/eves.cc`
- Modify: `src/cpu/o3/vp/ValuePredictor.py`,
  `src/cpu/o3/vp/SConscript`, `configs/garfield/arm/sim_opts.py`,
  `src/cpu/o3/vp/evtage.hh` + `evtage.cc` (COMMENT-ONLY),
  `docs/superpowers/specs/2026-08-14-estride-design.md` (amendment)
- Test: boots + directed-routing smokes + bit-identity re-gate

**Interfaces:**
- Consumes: Task 1's `usesInflightCounts()/inflightCount()/
  notifyRenamedInst` (wired already); Task 2's `EStrideTable`,
  `evesArbitrate`; `EVtageTables` (ctor `(const EVtageConfig &,
  std::function<double()>)`, `lookup(pc, upc, hist)`,
  `train(pc, upc, hist, token, EVtageClassifier)`,
  `correctivePunish(token)`, `burstGuardSuppresses(lastMispVT)`);
  `vpKey(pc, upc)`.
- Produces: SimObject `EvesVP` (`--use-vp eves`).

Key implementation facts:

- Token flag bits (spec §5): bits 63/62/61 =
  `TokenStridePredicted` / `TokenVtageConfident` /
  `TokenDeliveredByVtage`; `TokenFlagMask` is their OR. Strip with
  `token & ~TokenFlagMask` before ANY `EVtageTables` call. The
  EVtageTables token layout is rank(4b, biased +1) + way(1b) +
  index(max(log2(baseEntries/2), log2(taggedEntries)) bits) +
  tag(20b) — evtage_tables.cc packToken; ctor `fatal_if` when
  `4 + 1 + idx_bits + 20 > 61` with idx_bits recomputed from the
  params (`ceilLog2` from `base/intmath.hh`), so the three flag bits
  can never collide.
- `EvesVP` overrides: `trainsAtCommit() = true`,
  `usesHistory() = true`, `usesInflightCounts() = true`.
- Classifier translation: copy `toMemLevel()` / `toEVtageClassifier()`
  from evtage.cc's anonymous namespace verbatim (file-local there; a
  comment cites evtage.cc as the original). Add the stride-side
  translation:

```cpp
/** VpClassifierInfo -> EStrideClassifier: the four CVP latency
 *  predicates via the same memSrcLevel mapping E-VTAGE uses (our
 *  hierarchy has no distinct LLC row, so a load's notLlcMiss and
 *  notL2Miss always agree -- the CVP LLC-hit allocation arm is
 *  unreachable, spec S3.4), the allocation-class ladder, and the two
 *  flag-keyed gates. */
EStrideClassifier
toEStrideClassifier(const VpClassifierInfo &c, bool stride_predicted)
{
    EStrideClassifier sc;
    sc.isLoad = (c.instClass == VpInstClass::Load);
    if (sc.isLoad) {
        const EVtageMemLevel lvl = toMemLevel(c.memSrcLevel);
        sc.notLlcMiss = lvl != EVtageMemLevel::Mem;
        sc.notL2Miss = lvl != EVtageMemLevel::Mem;
        sc.notL1Miss =
            lvl == EVtageMemLevel::L1d || lvl == EVtageMemLevel::Stlf;
        sc.fastInst = lvl == EVtageMemLevel::Stlf;
    } else {
        // Non-loads: all latency terms true; MFASTINST mirrors
        // E-VTAGE's fastInstBit (!slowInst covers alu, store, undef).
        sc.notLlcMiss = sc.notL2Miss = sc.notL1Miss = true;
        sc.fastInst = c.instClass != VpInstClass::SlowAlu;
    }
    switch (c.instClass) {
        case VpInstClass::Load:
            sc.allocClass = EStrideAllocClass::Load;
            break;
        case VpInstClass::Alu:
        case VpInstClass::Store:
            sc.allocClass = EStrideAllocClass::AluOrStore;
            break;
        case VpInstClass::SlowAlu:
            sc.allocClass = EStrideAllocClass::FpOrSlowAlu;
            break;
        default: // IndirectCall, Undef: absent from the CVP switch
            sc.allocClass = EStrideAllocClass::Never;
            break;
    }
    sc.deliveredCorrect = c.deliveredCorrect;
    sc.stridePredicted = stride_predicted;
    return sc;
}
```

- `predictImpl` (order: stride first, VTAGE second, as in the source):

```cpp
VpPredictResult
EvesVP::predictImpl(const VpLookupContext &ctx)
{
    const uint64_t key = vpKey(ctx.pc, ctx.upc);
    const unsigned inflight = inflightCount(key);
    const EStrideLookup s = stride.lookup(key, inflight);
    const EVtageLookup r = vtage.lookup(ctx.pc, ctx.upc, ctx.hist);
    const unsigned last_misp =
        renamedInsts(ctx.tid) - lastWrongMark[ctx.tid];
    const bool blackout = vtage.burstGuardSuppresses(last_misp);

    EvesArbiterIn in;
    in.stridePredicted = s.predicted;
    in.strideValue = s.value;
    in.vtageHit = r.hit;
    in.vtageConfident = r.confident;
    in.vtageValue = r.value;
    in.blackoutActive = blackout;
    in.overwriteRequiresConfidence = overwriteRequiresConfidence;
    const EvesArbiterOut a = evesArbitrate(in);

    if (s.hit) {
        evesStats.strideLookupHits++;
    }
    if (s.predicted) {
        evesStats.stridePredictions++;
        evesStats.strideInflightAtPredict.sample(inflight);
        if (a.deliveredByVtage) {
            evesStats.strideOverwrittenByVtage++;
            if (!r.confident) {
                evesStats.strideOverwrittenLowConf++;
            }
        }
    }
    if (s.blockedBySafeStride) {
        evesStats.safeStrideBlocked++;
    }
    if (blackout && r.hit) {
        evesStats.blackoutSuppressed++;
    }
    if (a.value) {
        if (a.deliveredByVtage) {
            evesStats.suppliedByVtage++;
        } else {
            evesStats.suppliedByStride++;
        }
    }

    uint64_t token = r.token;
    panic_if(token & TokenFlagMask,
             "EVtage token collides with EVES flag bits");
    if (a.stridePredicted) {
        token |= TokenStridePredicted;
    }
    if (a.vtageConfident) {
        token |= TokenVtageConfident;
    }
    if (a.deliveredByVtage) {
        token |= TokenDeliveredByVtage;
    }
    return {a.value, token};
}
```

- `trainImpl` (VTAGE before stride, cc:767-772):

```cpp
void
EvesVP::trainImpl(const VpLookupContext &ctx, RegVal actualValue,
                  uint64_t token, const VpClassifierInfo &classifier)
{
    const uint64_t vtage_token = token & ~TokenFlagMask;
    const bool stride_predicted = token & TokenStridePredicted;

    const EVtageClassifier ec =
        toEVtageClassifier(classifier, actualValue);
    vtage.train(ctx.pc, ctx.upc, ctx.hist, vtage_token, ec);

    const uint64_t key = vpKey(ctx.pc, ctx.upc);
    const EStrideClassifier sc =
        toEStrideClassifier(classifier, stride_predicted);
    const auto outcomes = stride.train(key, actualValue, sc);
    for (const EStrideTrainOutcome o : outcomes) {
        switch (o) {
          case EStrideTrainOutcome::ConfInc:
            evesStats.strideConfGateFired++;
            break;
          case EStrideTrainOutcome::ConfHeld:
            evesStats.strideConfGateSuppressed++;
            break;
          case EStrideTrainOutcome::UInc:
          case EStrideTrainOutcome::UHeld:
            break;
          case EStrideTrainOutcome::UJamSaturated:
            evesStats.strideUJams++;
            break;
          case EStrideTrainOutcome::MispredictDecay:
            evesStats.strideMispredictDecay++;
            break;
          case EStrideTrainOutcome::MispredictCollapse:
            evesStats.strideMispredictCollapse++;
            break;
          case EStrideTrainOutcome::StrideSet:
            evesStats.strideSet++;
            break;
          case EStrideTrainOutcome::SentinelDemoted:
            evesStats.sentinelDemotions++;
            break;
          case EStrideTrainOutcome::AllocatedConfZeroVictim:
            evesStats.strideAllocPass1++;
            evesStats.strideAllocsByClass[
                static_cast<unsigned>(sc.allocClass)]++;
            break;
          case EStrideTrainOutcome::AllocatedUZeroVictim:
            evesStats.strideAllocPass2++;
            evesStats.strideAllocsByClass[
                static_cast<unsigned>(sc.allocClass)]++;
            break;
          case EStrideTrainOutcome::AllocAged:
            evesStats.strideAllocAged++;
            break;
          case EStrideTrainOutcome::AllocAgeHeld:
            break;
          case EStrideTrainOutcome::AllocDrawRefused:
            evesStats.strideAllocDrawRefused++;
            break;
          case EStrideTrainOutcome::AllocSkippedDeliveredCorrect:
            evesStats.strideAllocSkippedCovered++;
            break;
          case EStrideTrainOutcome::SafeStrideCredited:
            evesStats.safeStrideCredits++;
            break;
        }
    }

    if (classifier.deliveredCorrect) {
        if (token & TokenDeliveredByVtage) {
            evesStats.deliveredCorrectByVtage++;
        } else {
            evesStats.deliveredCorrectByStride++;
        }
    }
}
```

- `correctiveResetImpl` (spec §6 routing, exact return semantics):

```cpp
bool
EvesVP::correctiveResetImpl(uint64_t token)
{
    if (token & TokenStridePredicted) {
        if (stride.safeStridePenalty()) {
            evesStats.safeStrideNegEpisodes++;
        }
    }
    if (token & TokenVtageConfident) {
        // No ThreadID reaches this site (the interface gap
        // evtage.hh's lastWrongMark comment documents): reset every
        // thread's mark together, as E-VTAGE does.
        for (ThreadID tid = 0; tid < MaxThreads; tid++) {
            lastWrongMark[tid] = renamedInsts(tid);
        }
        evesStats.wrongMarkResets++;
    }
    if (token & TokenDeliveredByVtage) {
        evesStats.deliveredWrongByVtage++;
        const bool live =
            vtage.correctivePunish(token & ~TokenFlagMask);
        if (live) {
            evesStats.vtageCorrectivePunishes++;
        }
        return live;
    }
    // Stride supplied the wrong value: SafeStride is the entire
    // corrective mechanism (spec S6) -- the VTAGE entry is left
    // alone, and no staleness question was asked, so report live.
    evesStats.deliveredWrongByStride++;
    return true;
}
```

- Ctor: mirror `EVtageVP`'s (rng functor, `EVtageConfig` from the
  duplicated params, `EStrideTable` with the same `tableRng`), plus
  the token-width `fatal_if` above. No burst-guard `fatal_if` — the
  feed is wired (Task 1); `lastWrongMark[MaxThreads] = {}` as in
  evtage.hh with the same doc comment adapted.
- `EvesStats` group (all `statistics::Scalar` unless noted):
  `suppliedByStride, suppliedByVtage, strideLookupHits,
  stridePredictions, strideOverwrittenByVtage,
  strideOverwrittenLowConf, safeStrideBlocked, safeStrideNegEpisodes,
  safeStrideCredits, strideConfGateFired, strideConfGateSuppressed,
  strideUJams, strideMispredictDecay, strideMispredictCollapse,
  strideSet, sentinelDemotions, strideAllocPass1, strideAllocPass2,
  strideAllocAged, strideAllocDrawRefused, strideAllocSkippedCovered,
  deliveredCorrectByStride, deliveredCorrectByVtage,
  deliveredWrongByStride, deliveredWrongByVtage,
  vtageCorrectivePunishes, wrongMarkResets, blackoutSuppressed`;
  `strideAllocsByClass` = `statistics::Vector` init(4) with subnames
  `aluOrStore, fpOrSlowAlu, load, never`;
  `strideInflightAtPredict` = `statistics::Histogram` init(8).
  Every description states the event and site (follow evtage.cc's
  ADD_STAT style).

- `ValuePredictor.py`: `class EvesVP(BaseValuePredictor)` duplicating
  ALL ten EVtageVP params verbatim (same names, defaults, help — a
  leading class comment notes the deliberate duplication and the
  drift risk, per the spec §2), plus:

```python
    vtageOverwriteRequiresConfidence = Param.Bool(
        False,
        "EVES arbitration: require the embedded E-VTAGE side to be "
        "high-confidence before its value overwrites the stride "
        "prediction. False (default) reproduces the CVP-1 source "
        "verbatim: a VTAGE tag hit outside the post-misprediction "
        "blackout overwrites even below confidence.",
    )
```

- SConscript: add `'EvesVP'` to sim_objects, `Source('eves.cc')`.
- `sim_opts.py`: `choices=["lvp", "vtage", "evtage", "eves"]`; help
  gains "; eves = full EVES (E-VTAGE + E-Stride)". New flag:

```python
    garfield.add_argument(
        "--eves-vtage-overwrite-requires-confidence",
        action="store_true",
        help="EVES arbitration ablation: require E-VTAGE confidence "
        "before its value overwrites a stride prediction (default "
        "off = CVP-1 source-verbatim overwrite).",
    )
```

  and in the `vp()` factory, BEFORE the lvp fallback:

```python
    if args.use_vp == "eves":
        kwargs = {}
        if args.evtage_hist_lengths is not None:
            kwargs["historyLengths"] = args.evtage_hist_lengths
            kwargs["numTagged"] = len(args.evtage_hist_lengths)
        return EvesVP(
            onlyLoads=not args.vp_all_insts,
            burstGuardWindow=args.evtage_burst_guard,
            confThreshold=args.evtage_conf_threshold,
            vtageOverwriteRequiresConfidence=(
                args.eves_vtage_overwrite_requires_confidence
            ),
            **kwargs,
        )
```

  (`--evtage-hist-lengths`, `--evtage-conf-threshold`, and
  `--evtage-burst-guard` are shared with the evtage arm — update
  their help strings to say "E-VTAGE / EVES". The spec §2 named a
  separate `--eves-burst-guard`; sharing the existing flag is
  simpler and identical in effect — amend the spec sentence in this
  task's commit.)
- Comment-only frozen-file updates: evtage.cc:75-83's fatal_if
  comment now reads that the rename feed EXISTS (notifyRenamedInst)
  but E-VTAGE's guard stays locked off pending re-validation — EVES
  is the guard-capable predictor; evtage.hh:94-98 drops the dangling
  `notifyRenamed()` reference. The `fatal_if` itself STAYS.
- Spec amendment (same commit): §2's config-layer sentence — replace
  "`--eves-burst-guard <N>` (forwards to `EvesVP.burstGuardWindow`)"
  with "the shared `--evtage-burst-guard` (forwards to
  `EvesVP.burstGuardWindow`)".

- [ ] **Step 1: Write eves.hh/eves.cc per the blocks above; wire
Python/SConscript/sim_opts.** Build: full `gem5.opt` compiles, Python
imports (`./build/ALL/gem5.opt --help` runs).

- [ ] **Step 2: Boot smokes.** Using the Task 1 harness pattern
(vpchase = pointer-chase constants; expect VTAGE-side coverage,
near-zero stride):

```bash
GEM5=./build/ALL/gem5.opt
BIN=/home/rbera/work/garfield/gem5-infra/workloads/microbenchmarks/bin
export LD_LIBRARY_PATH=/home/rbera/miniconda3/lib
for cfg in \
  "eves_loads:--use-vp eves" \
  "eves_all:--use-vp eves --vp-all-insts" \
  "eves_ablation:--use-vp eves --vp-all-insts --eves-vtage-overwrite-requires-confidence" \
  "eves_guard128:--use-vp eves --evtage-burst-guard 128"; do
  name="${cfg%%:*}"; flags="${cfg#*:}"
  mkdir -p runs/eves_smoke/$name
  $GEM5 --outdir=runs/eves_smoke/$name configs/garfield/arm/se_run.py \
    --binary $BIN/vpchase --args 50000 --max-insts 5000000 $flags \
    > runs/eves_smoke/$name/run.log 2>&1
  echo "$name rc=$?"
done
```

Expected: rc=0 all four; in stats: predictionsMade > 0,
`inflightIncrements == inflightDecTrain + inflightDecSquash` (drained
SE exit), predictionsCorrect/Wrong sane, and for eves_guard128 a
nonzero blackoutSuppressed only if wrongs occurred.

- [ ] **Step 3: Directed routing smokes (spec §10).** Run the hostile
matrix entries (m_evtage_hostile pattern — address-varying loads that
mispredict) under `--use-vp eves` and `--use-vp eves --vp-all-insts`,
plus vpalu (strided non-load values). Assert with grep/python over
stats.txt:
1. `deliveredWrongByVtage == vtageCorrectivePunishes +
   correctiveResetStale` (every VTAGE-delivered wrong asks exactly one
   punish; stride-delivered wrongs ask none).
2. `predictionsWrong == deliveredWrongByVtage +
   deliveredWrongByStride`.
3. `predictionsCorrect == deliveredCorrectByVtage +
   deliveredCorrectByStride + (verified-correct predictions squashed
   or faulted before commit)`. predictionsCorrect counts at the
   verify site; deliveredCorrect* counts at commit-train, which only
   runs for instructions that actually commit. A prediction that
   verifies correct and is then squashed by an OLDER redirect
   (branch/VP/memory-order) or whose instruction faults at commit
   never reaches commit-train, so it lands in neither
   deliveredCorrectByVtage nor deliveredCorrectByStride — this term
   does not drain away at exit (the instructions it counts never
   commit, by definition). It is positive exactly when some
   verified-correct prediction is squashed or faults before commit;
   zero when no such victim occurs — likely, but not guaranteed, at
   negligible squash pressure (a run can squash plenty of
   instructions without ever killing a verified-correct prediction).
4. Inflight closure: `inflightIncrements == inflightDecTrain +
   inflightDecSquash`.

- [ ] **Step 4: Bit-identity re-gate.**
`bash runs/eves_identity/run_gate.sh after_task3` + compare.py against
`baseline` for all five configs. Expected: IDENTICAL modulo new zero
stats.

- [ ] **Step 5: GTests all green** (4 binaries), `pre-commit` clean.

- [ ] **Step 6: Commit** via `git-commit`. Header:
`cpu-o3,configs: Add the EVES value predictor (E-VTAGE + E-Stride)`

---

### Task 4: vpstride + vpstorm microbenches, closure demonstration

**Files (in `/home/rbera/work/garfield/gem5-infra`, separate repo):**
- Create: `workloads/microbenchmarks/src/vpstride.c`,
  `workloads/microbenchmarks/src/vpstorm.c`
- Modify: `workloads/microbenchmarks/Makefile` (same pattern as
  existing benches; aarch64 cross-gcc from conda)

**Interfaces:** none consumed by later tasks; Task 5 uses the built
binaries for nothing (SPEC checkpoints only) — these benches prove the
mechanism.

- [ ] **Step 1: Write vpstride.** Deep in-flight, strided values,
LLC-missing loads (follow the existing benches' `bench.h` ROI
conventions — read `src/vpchase.c` first and mirror its structure,
argument handling, and checksum-print epilogue):

```c
/* vpstride: one load PC whose values stride uniformly while its
 * addresses miss the cache -- the E-Stride target pattern. Values
 * arr[i] = i * 7 stride by 7 per iteration; the footprint (arg1
 * elements, default 8M = 64MB) defeats the LLC so many iterations of
 * the SAME load PC overlap in flight: correctness of the predicted
 * value REQUIRES inflight compensation. arg2 = iterations. */
#include "bench.h"

int
main(int argc, char **argv)
{
    long n = argc > 1 ? atol(argv[1]) : (8L << 20);
    long iters = argc > 2 ? atol(argv[2]) : 400000;
    long *arr = xmalloc_pages(n * sizeof(long));
    for (long i = 0; i < n; i++)
        arr[i] = i * 7;
    long sum = 0;
    roi_begin();
    for (long r = 0, i = 0; r < iters; r++) {
        sum += arr[i];          /* the strided-value load */
        i += 1021;              /* prime step: cache-hostile walk    */
        if (i >= n) i -= n;     /* wrap without a divide             */
    }
    roi_end();
    print_checksum(sum);
    return 0;
}
```

NOTE for the implementer: the value stride per ROI iteration is
`1021 * 7` except at wraps — E-Stride tracks whatever constant delta
dominates; verify with stats, and if wraps pollute training, size
iters below n. Adapt `xmalloc_pages`/`roi_*`/`print_checksum` to the
ACTUAL helpers in `bench.h` (read it first; do not invent names).

- [ ] **Step 2: Write vpstorm** — vpstride's loop body plus a
data-dependent unpredictable branch (LCG low bit) toggling a counter,
forcing branch-mispredict squash storms across the in-flight window:

```c
    unsigned lcg = 12345;
    roi_begin();
    for (long r = 0, i = 0; r < iters; r++) {
        sum += arr[i];
        lcg = lcg * 1103515245u + 12345u;
        if (lcg & 0x100)        /* unpredictable */
            sum ^= r;
        i += 1021;
        if (i >= n) i -= n;
    }
    roi_end();
```

- [ ] **Step 3: Build both** (`make` in microbenchmarks/, conda
cross-gcc per the Makefile), commit in gem5-infra with that repo's
conventions (plain git commit message; it has no gem5 hook).

- [ ] **Step 4: Demonstration runs (gem5 repo, runs/eves_smoke/).**
  1. `vpstride --use-vp eves`: expect stridePredictions >> 0,
     strideInflightAtPredict histogram mass at > 0 buckets,
     deliveredCorrectByStride >> deliveredWrongByStride, and IPC
     visibly above a no-VP baseline run of the same binary (two runs,
     compare sim_insts/sim_ticks). Also run `--use-vp evtage` for
     contrast: near-zero coverage on the strided-value load is the
     expected complementarity headline at microbench scale.
  2. `vpstorm --use-vp eves`: expect nonzero inflightDecSquash and the
     closure identity `inflightIncrements == inflightDecTrain +
     inflightDecSquash` EXACT at exit; no panic (the underflow
     panic_if is the real assertion here).
  3. Record the numbers in the ledger (they seed the report's
     mechanism section).

- [ ] **Step 5: Commit** the gem5-infra changes (that repo), and any
gem5-side smoke-script tweaks stay in runs/ (gitignored, no commit).

---

### Task 5: Evaluation — probe 16 → 190 (campaign lead runs this)

**Files:** sweep driver extensions under
`/home/rbera/work/garfield/runs/vp_lvp_sweep/` (outside the repo;
resumable setsid pattern from the prior campaigns).

- [ ] **Step 1:** Add arms `eves` (`--use-vp eves
--evtage-hist-lengths 2,4,6,11,20,36,64`), `eves_all` (+
`--vp-all-insts`), `eves_all_confgate` (+
`--eves-vtage-overwrite-requires-confidence`) to the driver config
table (dense-64 series both sides, matching the evtage arms).
- [ ] **Step 2:** Probe on the 16 vp_evtage_probe checkpoints; compare
against the stored evtage/evtage_all results. Gate: promote to 190
unless clearly negative (the chapter's standing probe rule).
- [ ] **Step 3:** 190-checkpoint sweep, Monitor armed, auto-retry
driver; aggregate with the existing analysis scripts (speedups +
committed-coverage via `commit.committedVpPredicted`; per-supplier
split from the new stats).
- [ ] **Step 4:** Research-log report via the `research-report` skill
(EVES vs E-VTAGE; the overwrite-quirk A/B verdict; ~0.64KB storage
note; complementarity per spec §11).

---

## Execution notes

- Tasks 1→2→3 are strictly ordered; Task 4 needs Task 3's binary;
  Task 5 needs Task 4 only for confidence, not artifacts.
- Subagent implementers MUST read the spec
  (`docs/superpowers/specs/2026-08-14-estride-design.md`) before their
  task; this plan repeats the load-bearing rules but the spec governs.
- Any transcription doubt against the CVP source: STOP and check
  `cvp8KB/mypredictor.cc` (scratchpad copy; line cites throughout) —
  never guess.
- After each task's commit, the lead re-runs the task's gates
  independently before dispatching the next task (rigorous vetting is
  part of the campaign contract).
