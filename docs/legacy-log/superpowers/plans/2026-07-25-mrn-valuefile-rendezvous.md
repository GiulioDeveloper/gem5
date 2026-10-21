# MRN Value-File Rendezvous Predictor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the value-file rendezvous predictor from
`docs/superpowers/specs/2026-07-25-mrn-valuefile-rendezvous-design.md`: a
Tyson–Austin-style Store/Load-Cache + Value-File + Store-Cache model that
replaces the alias path's correlator + store-queue instance hunt.

**Architecture:** A params-free core class (`MrnValueFileTables`) mirrors the
existing `MrnTables` two-layer pattern; the `MemRenamePredictor` SimObject
wraps it with params/stats; rename hooks deposit (E1) and consume (E2); the
LSQ hooks publish (E3), probe/rebind (E4), and last-value + confidence
training (E5). Enforcement (destination aliasing, value forwarding,
verification, squash) reuses the existing MRN machinery unchanged.

**Tech Stack:** gem5 O3 CPU (C++17), SCons, GoogleTest, gem5 stdlib configs.

## Global Constraints

- **Build command on this host (minitron):**
  `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ARM/gem5.opt -j32`
  from `/home/rbera/work/garfield/gem5`. Do NOT use `./build-gem5.sh` (fails
  on this host). A GTest binary builds as
  `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ARM/cpu/o3/mem_rename_valuefile.test.opt -j32`.
- **Naming:** No conversational or session-specific names in code, comments,
  stat descriptions, or param help (no letter/number mode labels, no plan
  jargon). Structure names `valueFile`, `storeLoadCache`, `storeCache` are
  published terms — cite "Tyson & Austin, MICRO-30 1997; Reinman et al.,
  ICS 1999 §2.3" in the new header's file comment.
- **Commits:** gem5 tag header (`cpu-o3: ...`), first line ≤ 65 chars total,
  imperative, no trailing period. Body wrapped at 72. **No AI attribution
  of any kind** (no Co-Authored-By, no Generated-with, no session links).
  Every commit must include a commit-note file
  `docs/commit-notes/$(date +%Y%m%d-%H%M%S)-<kebab-slug-of-summary>.md`
  staged in the SAME commit, following the template in
  `docs/commit-notes/` (Goal / Summary of changes / Files changed sections;
  see any recent note there as example). Do not pass `--no-verify`.
- **C++ style:** 79-col lines, 4-space indent, `lowerCamelCase`
  methods/members, `snake_case` locals. Match surrounding code.
- **Do not modify** `configs/garfield/arm/virt_run.py` (developed elsewhere),
  anything under `runs/` (gitignored run scripts belong to the controller),
  or the existing `MrnTables` value-path/correlator logic beyond the exact
  integration points named below.
- The five dataflow events are named E1–E5 in this plan **only for
  cross-referencing between tasks**; these labels must NOT appear in code or
  comments — write what the hook does ("store deposit at rename", "publish at
  store address resolution", ...).

---

### Task 1: Core `MrnValueFileTables` class + unit tests

**Files:**
- Create: `src/cpu/o3/mem_rename_valuefile.hh`
- Create: `src/cpu/o3/mem_rename_valuefile.cc`
- Create: `src/cpu/o3/mem_rename_valuefile.test.cc`
- Modify: `src/cpu/o3/SConscript` (Source + GTest lines; anchors below)

**Interfaces:**
- Consumes: `base/types.hh` (`Addr`, `RegVal`), `cpu/inst_seq.hh`
  (`InstSeqNum`), `cpu/reg_class.hh` (`PhysRegIdPtr` — stored opaquely, never
  dereferenced in this class).
- Produces (used verbatim by Tasks 2–4):

```cpp
namespace gem5 { namespace o3 {

struct MrnVfConfig
{
    unsigned vfEntries = 1024;
    unsigned slcEntries = 4096;
    unsigned slcAssoc = 4;
    unsigned scEntries = 4096;
    unsigned scAssoc = 4;
    unsigned scGranularityBytes = 8;   // power of two
    unsigned confBits = 4;
    unsigned confThreshold = 8;
    unsigned confInc = 1;
    unsigned confDec = 1;
    bool resetConfOnMispredict = true;
};

/** Reference to a value-file cell: index + the generation observed when the
 *  reference was created. A reference is dead once the cell's generation
 *  moves on (the cell was reallocated to another owner). */
struct MrnVfRef
{
    int idx = -1;
    uint64_t gen = 0;
    bool valid() const { return idx >= 0; }
    bool operator==(const MrnVfRef &o) const
    { return idx == o.idx && gen == o.gen; }
};

/** What a load sees in its bound cell at rename. */
struct MrnVfCellRead
{
    bool bound = false;       // SLC hit and the cell generation still matches
    bool confident = false;   // conf >= confThreshold
    bool ptrValid = false;    // cell holds a producer physreg pointer
    PhysRegIdPtr ptr = nullptr;
    InstSeqNum ptrSeq = 0;
    bool valueValid = false;  // cell holds a value
    RegVal value = 0;
    MrnVfRef ref;             // valid iff bound
};

/** Outcome of the load-side store-cache probe at address resolution. */
struct MrnVfProbeResult
{
    enum Outcome { SameBinding, Rebound, SelfBound, AlreadySelfBound };
    Outcome outcome = SameBinding;
    /** The probe hit a store-cache entry whose cell generation had moved on
     *  (channel died by reallocation); treated as a miss. */
    bool scHitDeadChannel = false;
};

class MrnValueFileTables
{
  public:
    explicit MrnValueFileTables(const MrnVfConfig &cfg);

    /** Store deposit at rename: find-or-allocate the store PC's cell and
     *  deposit the data physreg (+ the value, when readyValue != nullptr;
     *  a null readyValue MUST clear any stale value in the cell). */
    MrnVfRef storeRename(Addr storePC, PhysRegIdPtr dataReg, InstSeqNum sn,
                         const RegVal *readyValue);

    /** Load lookup at rename. */
    MrnVfCellRead loadRename(Addr loadPC);

    /** Store publish at address resolution. Returns false when suppressed:
     *  stale ref (cell reallocated since rename) or a program-order-younger
     *  occupant already holds the address. */
    bool storeAddrResolved(const MrnVfRef &ref, Addr ea, InstSeqNum sn);

    /** Load probe at address resolution: rebind / self-bind per spec. */
    MrnVfProbeResult loadAddrResolved(Addr loadPC, Addr ea);

    /** Load value at writeback: updates the cell only when the load is
     *  self-bound (last-value); returns whether it wrote. */
    bool loadDataResolved(Addr loadPC, RegVal value);

    /** Confidence training at writeback (consumed or shadow). Trains only
     *  when the load's SLC entry is still bound to usedRef — a rebind
     *  between rename and writeback discards the outcome. */
    void trainVerify(Addr loadPC, const MrnVfRef &usedRef, bool correct);

  private:
    struct VfCell
    {
        uint64_t gen = 0;
        bool ptrValid = false;
        PhysRegIdPtr ptr = nullptr;
        InstSeqNum ptrSeq = 0;
        bool valueValid = false;
        RegVal value = 0;
        uint64_t lru = 0;
    };
    struct SlcEntry
    {
        Addr tag = 0;
        int vfIdx = -1;
        uint64_t gen = 0;
        unsigned conf = 0;
        bool selfBound = false;
        bool valid = false;
        uint64_t lru = 0;
    };
    struct ScEntry
    {
        Addr tag = 0;
        int vfIdx = -1;
        uint64_t gen = 0;
        InstSeqNum storeSeq = 0;
        bool valid = false;
        uint64_t lru = 0;
    };

    SlcEntry *slcFind(Addr pc);
    SlcEntry *slcAllocate(Addr pc);
    ScEntry *scFind(Addr lineAddr);
    ScEntry *scAllocate(Addr lineAddr);
    int vfAllocate();          // global-LRU victim; bumps gen; clears content
    Addr scLine(Addr ea) const { return ea >> scGranularityLog2; }
    unsigned confMax() const { return (1u << confBits) - 1; }

    const unsigned slcSets, slcAssoc, scSets, scAssoc;
    const unsigned scGranularityLog2;
    const unsigned confBits, confThreshold, confInc, confDec;
    const bool resetConfOnMispredict;
    std::vector<VfCell> valueFile;
    std::vector<SlcEntry> storeLoadCache;
    std::vector<ScEntry> storeCache;
    uint64_t lruTick = 0;
};

}} // namespace gem5::o3
```

Follow the `MrnTables` implementation style exactly (`mem_rename_predictor.hh:39-190`,
`mem_rename_predictor.cc`): sets = entries/assoc, modulo set indexing,
LRU-within-set via the shared monotonic `lruTick`, find returns nullptr on
miss. `vfAllocate` scans all cells for global min-`lru`, increments the
victim's `gen`, resets `ptrValid/valueValid`, returns the index.

Method semantics (implement exactly; each maps to a spec §4/§5 rule):

- `storeRename`: `slcFind(storePC)`; miss → `slcAllocate` + `vfAllocate`,
  point entry `{vfIdx, gen}`. Hit but `valueFile[vfIdx].gen != entry->gen`
  (cell stolen) → `vfAllocate` a fresh cell and repoint. Then deposit:
  `ptr = dataReg; ptrSeq = sn; ptrValid = true;` and
  `valueValid = (readyValue != nullptr)`, `value = *readyValue` when set.
  Bump cell + entry lru. Return `{vfIdx, gen}`.
- `loadRename`: `slcFind(loadPC)`; miss → `{bound=false}`. Hit with gen
  mismatch → `{bound=false}` (leave the entry; the address-resolution probe
  repairs it). Hit + gen match → fill all fields,
  `confident = entry->conf >= confThreshold`, `ref = {vfIdx, gen}`.
- `storeAddrResolved`: `ref` invalid or `valueFile[ref.idx].gen != ref.gen`
  → return false. `scFind(scLine(ea))`: hit with `storeSeq > sn` (occupant
  program-order younger) → return false. Hit else → overwrite
  `{vfIdx, gen, storeSeq=sn}`. Miss → `scAllocate` and fill. Return true.
- `loadAddrResolved`: `scFind(scLine(ea))`. Hit → if
  `valueFile[e->vfIdx].gen != e->gen`, set `scHitDeadChannel = true` and
  fall through to the miss path. Live hit → compare `{e->vfIdx, e->gen}`
  with the load's SLC binding: equal → `SameBinding`; else (or no SLC
  entry) → bind `slcFind/slcAllocate(loadPC)` to it, `conf = 0`,
  `selfBound = false`, → `Rebound`. Miss path → if the load's SLC entry
  exists, is `selfBound`, and its cell gen still matches →
  `AlreadySelfBound`; else `vfAllocate` an own cell, bind, `conf = 0`,
  `selfBound = true`, → `SelfBound`.
- `loadDataResolved`: SLC entry exists, `selfBound`, gen matches → write
  `value`, `valueValid = true`, `ptrValid = false`, return true; else false.
- `trainVerify`: SLC entry exists and `{vfIdx, gen} == usedRef` → correct:
  `conf = min(conf + confInc, confMax())`; wrong: `conf = 0` when
  `resetConfOnMispredict`, else `conf = (conf > confDec) ? conf - confDec : 0`.

- [ ] **Step 1: Write the failing unit tests**

`src/cpu/o3/mem_rename_valuefile.test.cc`, mirroring the style of
`src/cpu/o3/mem_rename_predictor.test.cc` (plain `TEST` macros, no fixture,
anonymous-namespace helpers). Fake physregs via
`reinterpret_cast<PhysRegIdPtr>(uintptr_t)` — the core never dereferences.

```cpp
#include <gtest/gtest.h>

#include "cpu/o3/mem_rename_valuefile.hh"

using namespace gem5;
using namespace gem5::o3;

namespace
{

MrnVfConfig
testConfig()
{
    MrnVfConfig c;
    c.vfEntries = 4;
    c.slcEntries = 8;
    c.slcAssoc = 2;
    c.scEntries = 8;
    c.scAssoc = 2;
    c.scGranularityBytes = 8;
    c.confBits = 2;
    c.confThreshold = 2;
    c.confInc = 1;
    c.confDec = 1;
    c.resetConfOnMispredict = true;
    return c;
}

PhysRegIdPtr
fakeReg(uintptr_t n)
{
    return reinterpret_cast<PhysRegIdPtr>(n);
}

// Establish a confident store->load binding: deposit, publish, probe
// (rebind), then train to threshold.
MrnVfRef
bindAndTrain(MrnValueFileTables &t, Addr store_pc, Addr load_pc, Addr ea,
             PhysRegIdPtr reg, InstSeqNum sn)
{
    MrnVfRef ref = t.storeRename(store_pc, reg, sn, nullptr);
    EXPECT_TRUE(t.storeAddrResolved(ref, ea, sn));
    auto probe = t.loadAddrResolved(load_pc, ea);
    EXPECT_EQ(probe.outcome, MrnVfProbeResult::Rebound);
    for (int i = 0; i < 2; i++)
        t.trainVerify(load_pc, ref, true);
    return ref;
}

} // namespace

TEST(MrnValueFileTables, ColdLoadRenameUnbound)
{
    MrnValueFileTables t(testConfig());
    auto r = t.loadRename(0x400);
    EXPECT_FALSE(r.bound);
    EXPECT_FALSE(r.ref.valid());
}

TEST(MrnValueFileTables, DepositBindTrainConsume)
{
    MrnValueFileTables t(testConfig());
    MrnVfRef ref = bindAndTrain(t, 0x100, 0x200, 0x1000, fakeReg(7), 10);
    auto r = t.loadRename(0x200);
    EXPECT_TRUE(r.bound);
    EXPECT_TRUE(r.confident);
    EXPECT_TRUE(r.ptrValid);
    EXPECT_EQ(r.ptr, fakeReg(7));
    EXPECT_EQ(r.ptrSeq, 10u);
    EXPECT_TRUE(r.ref == ref);
}

TEST(MrnValueFileTables, DepositClearsStaleValue)
{
    MrnValueFileTables t(testConfig());
    RegVal v1 = 42;
    t.storeRename(0x100, fakeReg(7), 10, &v1);       // value deposited
    t.storeRename(0x100, fakeReg(8), 20, nullptr);   // next instance: no
    // Bind a load so we can observe the cell.
    MrnVfRef ref{0, 0};
    ref = t.storeRename(0x100, fakeReg(9), 30, nullptr);
    ASSERT_TRUE(t.storeAddrResolved(ref, 0x1000, 30));
    t.loadAddrResolved(0x200, 0x1000);
    for (int i = 0; i < 2; i++)
        t.trainVerify(0x200, ref, true);
    auto r = t.loadRename(0x200);
    ASSERT_TRUE(r.bound);
    EXPECT_TRUE(r.ptrValid);
    EXPECT_FALSE(r.valueValid);   // stale value must not survive deposits
}

TEST(MrnValueFileTables, RebindResetsConfidence)
{
    MrnValueFileTables t(testConfig());
    bindAndTrain(t, 0x100, 0x200, 0x1000, fakeReg(7), 10);
    ASSERT_TRUE(t.loadRename(0x200).confident);
    // A different store PC (its own cell) publishes the same address,
    // program-order younger.
    MrnVfRef refB = t.storeRename(0x300, fakeReg(9), 50, nullptr);
    ASSERT_TRUE(t.storeAddrResolved(refB, 0x1000, 50));
    auto probe = t.loadAddrResolved(0x200, 0x1000);
    EXPECT_EQ(probe.outcome, MrnVfProbeResult::Rebound);
    auto r = t.loadRename(0x200);
    EXPECT_TRUE(r.bound);
    EXPECT_FALSE(r.confident);           // rebind reset confidence
    EXPECT_EQ(r.ptr, fakeReg(9));        // now the new channel
}

TEST(MrnValueFileTables, SelfBindLastValue)
{
    MrnValueFileTables t(testConfig());
    auto probe = t.loadAddrResolved(0x200, 0x2000);   // nothing published
    EXPECT_EQ(probe.outcome, MrnVfProbeResult::SelfBound);
    EXPECT_TRUE(t.loadDataResolved(0x200, 77));
    auto r0 = t.loadRename(0x200);
    ASSERT_TRUE(r0.bound);
    for (int i = 0; i < 2; i++)
        t.trainVerify(0x200, r0.ref, true);
    auto r = t.loadRename(0x200);
    ASSERT_TRUE(r.bound);
    EXPECT_TRUE(r.confident);
    EXPECT_TRUE(r.valueValid);
    EXPECT_EQ(r.value, 77u);
    EXPECT_FALSE(r.ptrValid);
    EXPECT_EQ(t.loadAddrResolved(0x200, 0x2000).outcome,
              MrnVfProbeResult::AlreadySelfBound);
}

TEST(MrnValueFileTables, GenMismatchAfterReallocation)
{
    MrnValueFileTables t(testConfig());   // vfEntries = 4
    bindAndTrain(t, 0x100, 0x200, 0x1000, fakeReg(7), 10);
    // Exhaust the value file: four more stores steal all four cells.
    for (int i = 0; i < 4; i++)
        t.storeRename(0x300 + 8 * i, fakeReg(20 + i), 100 + i, nullptr);
    auto r = t.loadRename(0x200);
    EXPECT_FALSE(r.bound);   // the load's cell was reallocated: dead channel
}

TEST(MrnValueFileTables, ScProgramOrderGuard)
{
    MrnValueFileTables t(testConfig());
    MrnVfRef refA = t.storeRename(0x100, fakeReg(7), 10, nullptr);
    ASSERT_TRUE(t.storeAddrResolved(refA, 0x1000, 10));
    MrnVfRef refB = t.storeRename(0x300, fakeReg(9), 5, nullptr);
    // B is program-order OLDER (sn 5 < 10) but resolves later: suppressed.
    EXPECT_FALSE(t.storeAddrResolved(refB, 0x1000, 5));
    t.loadAddrResolved(0x200, 0x1000);
    auto r0 = t.loadRename(0x200);
    ASSERT_TRUE(r0.bound);
    EXPECT_EQ(r0.ptr, fakeReg(7));   // still A's channel
}

TEST(MrnValueFileTables, StaleRefPublishSuppressed)
{
    MrnValueFileTables t(testConfig());
    MrnVfRef ref = t.storeRename(0x100, fakeReg(7), 10, nullptr);
    for (int i = 0; i < 4; i++)   // steal every cell
        t.storeRename(0x300 + 8 * i, fakeReg(20 + i), 100 + i, nullptr);
    EXPECT_FALSE(t.storeAddrResolved(ref, 0x1000, 10));
}

TEST(MrnValueFileTables, WrongTrainResetsAndStaleTrainIgnored)
{
    MrnValueFileTables t(testConfig());
    MrnVfRef ref = bindAndTrain(t, 0x100, 0x200, 0x1000, fakeReg(7), 10);
    ASSERT_TRUE(t.loadRename(0x200).confident);
    t.trainVerify(0x200, ref, false);
    EXPECT_FALSE(t.loadRename(0x200).confident);
    // Training against a reference the load is no longer bound to is a
    // no-op: rebind to another channel first.
    MrnVfRef refB = t.storeRename(0x300, fakeReg(9), 50, nullptr);
    ASSERT_TRUE(t.storeAddrResolved(refB, 0x1000, 50));
    t.loadAddrResolved(0x200, 0x1000);
    t.trainVerify(0x200, ref, true);   // stale usedRef
    EXPECT_FALSE(t.loadRename(0x200).confident);
}

TEST(MrnValueFileTables, SameBindingProbeKeepsConfidence)
{
    MrnValueFileTables t(testConfig());
    MrnVfRef ref = bindAndTrain(t, 0x100, 0x200, 0x1000, fakeReg(7), 10);
    // Re-publish (next instance) and re-probe: same channel, conf kept.
    ASSERT_TRUE(t.storeAddrResolved(ref, 0x1000, 60));
    EXPECT_EQ(t.loadAddrResolved(0x200, 0x1000).outcome,
              MrnVfProbeResult::SameBinding);
    EXPECT_TRUE(t.loadRename(0x200).confident);
}
```

- [ ] **Step 2: Register in SConscript and verify the tests fail to build**

In `src/cpu/o3/SConscript`: after `Source('mem_rename_predictor_sim.cc')`
(~line 71) add `Source('mem_rename_valuefile.cc')`; after the
`GTest('mem_rename_predictor.test', ...)` entry (~lines 82-83) add:

```python
GTest('mem_rename_valuefile.test', 'mem_rename_valuefile.test.cc',
      'mem_rename_valuefile.cc')
```

Run: `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ARM/cpu/o3/mem_rename_valuefile.test.opt -j32`
Expected: FAIL (header does not exist yet).

- [ ] **Step 3: Implement `mem_rename_valuefile.hh`/`.cc`**

Header exactly as in **Interfaces** above, with the file comment citing the
papers. Implementation per **Method semantics**. If the GTest link fails on
`PhysRegId`/`RegClass` symbols, append the missing `.cc` (e.g.
`'../reg_class.cc'`) to the GTest source list rather than weakening the
header.

- [ ] **Step 4: Build and run the tests**

Run: `LD_LIBRARY_PATH=/home/rbera/miniconda3/lib scons build/ARM/cpu/o3/mem_rename_valuefile.test.opt -j32 && ./build/ARM/cpu/o3/mem_rename_valuefile.test.opt`
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

Header: `cpu-o3: Add value-file rendezvous predictor core tables`
(+ commit-note file per Global Constraints).

---

### Task 2: Params, stats, wrapper methods, CLI plumbing

**Files:**
- Modify: `src/cpu/o3/MemRenamePredictor.py` (enum + params)
- Modify: `src/cpu/o3/mem_rename_predictor.hh` (include, member, wrappers, stats)
- Modify: `src/cpu/o3/mem_rename_predictor_sim.cc` (ctor + ADD_STATs)
- Modify: `configs/garfield/arm/sim_opts.py` (CLI flags + make_mrn)

**Interfaces:**
- Consumes: Task 1's `MrnValueFileTables`, `MrnVfConfig`, `MrnVfRef`,
  `MrnVfCellRead`, `MrnVfProbeResult`.
- Produces (used by Tasks 3–4): on `MemRenamePredictor` —

```cpp
bool valueFileEnabled() const { return _useValueFile; }
bool vfForwardProducerValue() const { return _vfForwardProducerValue; }
bool vfForwardLastValue() const { return _vfForwardLastValue; }

/** Per-mode index for the vfPredict* stat vectors. */
enum VfMode { VfModeAlias = 0, VfModeProducerValue, VfModeLastValue,
              VfModeCount };

MrnVfRef vfStoreRename(Addr pc, PhysRegIdPtr reg, InstSeqNum sn,
                       const RegVal *rv);      // counts deposits
MrnVfCellRead vfLoadRename(Addr pc);           // counts below-conf suppress
void vfStoreAddrResolved(const MrnVfRef &ref, Addr ea, InstSeqNum sn);
void vfLoadAddrResolved(Addr pc, Addr ea);     // counts probe outcomes
void vfLoadDataResolved(Addr pc, RegVal v);
void vfTrainVerify(Addr pc, const MrnVfRef &ref, bool correct);
void vfNotePredictMade(int mode);              // vfPredictMade[mode]++
void vfNotePredictOutcome(int mode, bool correct);
void vfNotePredictSquashed(int mode);
void vfNoteShadow(bool correct);               // shadow compare outcome
void vfNoteShadowSkipped();                    // producer unavailable
```

- [ ] **Step 1: Python enum + params**

`MemRenamePredictor.py`: `vals = ["lsq_forward", "store_set", "value_file"]`
(update the comment: value_file = the rendezvous model, deposits at rename,
learned by address at execution). Add params (defaults; help text must be
descriptive, no plan jargon):

```python
vfEntries = Param.Unsigned(1024, "Value-file rendezvous cells")
slcEntries = Param.Unsigned(4096, "Store/load cache entries (PC-indexed)")
slcAssoc = Param.Unsigned(4, "Store/load cache associativity")
scEntries = Param.Unsigned(4096, "Store cache entries (address-indexed)")
scAssoc = Param.Unsigned(4, "Store cache associativity")
scGranularityBytes = Param.Unsigned(8, "Store cache line granularity")
vfForwardProducerValue = Param.Bool(
    True, "Forward the producer physreg's value when it is already "
    "ready at the load's rename (value_file correlation only)")
vfForwardLastValue = Param.Bool(
    True, "Forward the last value from a self-bound cell "
    "(value_file correlation only)")
```

- [ ] **Step 2: Wrapper + stats**

`mem_rename_predictor.hh`: include `cpu/o3/mem_rename_valuefile.hh`; members
`MrnValueFileTables vfTables;`, `const bool _useValueFile;`,
`const bool _vfForwardProducerValue; const bool _vfForwardLastValue;`.
Wrapper methods inline per **Interfaces** (each bumps its stat then
delegates — follow the existing wrapper style at
`mem_rename_predictor.hh:203-243`). Stats in `MemRenameStats`:

- `statistics::Vector vfPredictMade, vfPredictCorrect, vfPredictWrong,
  vfPredictSquashed;` — `.init(VfModeCount)`, subnames
  `{"alias", "producerValue", "lastValue"}`, `flags(statistics::total)`.
- Scalars: `vfDepositsPtr, vfDepositsWithValue, vfScPublishes,
  vfScPublishSuppressed, vfScProbeHits, vfScProbeMisses,
  vfScProbeDeadChannel, vfRebinds, vfSelfBinds, vfBelowConfSuppressed,
  vfShadowCorrect, vfShadowWrong, vfShadowSkipped`.

`mem_rename_predictor_sim.cc`: construct
`vfTables(MrnVfConfig{p.vfEntries, p.slcEntries, p.slcAssoc, p.scEntries,
p.scAssoc, p.scGranularityBytes, p.confBits, p.confThreshold, p.confInc,
p.confDec, p.resetConfOnMispredict})`,
`_useValueFile(p.mrnCorrelation == enums::value_file)`, the two bools; add
every ADD_STAT with descriptive help (pattern: existing producerPredict*
registrations in the same file). Note `MrnVfConfig` is brace-initialized
positionally — the field order in Task 1's struct must be kept.

- [ ] **Step 3: CLI plumbing**

`sim_opts.py`: `--mrn-correlation` choices += `"value-file"` (the existing
`.replace("-", "_")` in `make_mrn` maps it to `value_file`); add
`--mrn-vf-no-producer-value` and `--mrn-vf-no-last-value` (store_true) and
pass `vfForwardProducerValue=not args.mrn_vf_no_producer_value`,
`vfForwardLastValue=not args.mrn_vf_no_last_value` in `make_mrn`
(sim_opts.py:225-240). Update `_mrn_banner()` to include the correlation and
the two knobs.

- [ ] **Step 4: Build gem5.opt + rerun both test binaries**

Run the Global-Constraints build; then run
`./build/ARM/cpu/o3/mem_rename_valuefile.test.opt` and
`./build/ARM/cpu/o3/mem_rename_predictor.test.opt`.
Expected: clean build, all tests PASS.

- [ ] **Step 5: Commit**

Header: `cpu-o3,configs: Wire value-file predictor params and stats`

---

### Task 3: DynInst carry fields + rename deposit/consume

**Files:**
- Modify: `src/cpu/o3/dyn_inst.hh` (flags, fields, accessors)
- Modify: `src/cpu/o3/rename.cc` (the MRN block in `renameInsts`, ~755-823)
- Modify: `src/cpu/o3/rename.hh` only if a helper declaration is added

**Interfaces:**
- Consumes: Task 2's wrapper methods and `VfMode` enum;
  `scoreboard->getReg(PhysRegIdPtr)` (rename has the pointer;
  usage examples rename.cc:789, 1213); `cpu->getReg(PhysRegIdPtr, ThreadID)`.
- Produces (used by Task 4): DynInst API —

```cpp
// New flags in the Flags enum (after MrnProducerResolved):
MrnVfEligible,   // load passed the participation guards at rename
// New MrnVfMode field values (uint8_t _mrnVfMode):
enum MrnVfMode : uint8_t { MrnVfNone = 0, MrnVfAlias, MrnVfProducerValue,
                           MrnVfLastValue, MrnVfShadowValue,
                           MrnVfShadowPtr };
// Accessors (conventions per existing _mrnXxx fields at dyn_inst.hh:1217+):
MrnVfRef mrnVfRef() const;                    // {_mrnVfIdx, _mrnVfGen}
void setMrnVfRef(const MrnVfRef &r);
uint8_t mrnVfMode() const; void setMrnVfMode(uint8_t m);
bool mrnVfEligible() const; void setMrnVfEligible();
RegVal mrnVfShadowVal() const; void setMrnVfShadowVal(RegVal v);
```

Fields: `int _mrnVfIdx = -1; uint64_t _mrnVfGen = 0;
uint8_t _mrnVfMode = MrnVfNone; RegVal _mrnVfShadowVal = 0;` placed after
`_mrnPredStorePC` (~dyn_inst.hh:1234). `mem_rename_valuefile.hh` must be
includable from dyn_inst.hh (it only needs base types — verify no cycle; if
one appears, define `MrnVfRef` in `mem_rename_valuefile.hh` and
forward-include only that header, which dyn_inst.hh may include directly).

Shadow-pointer predictions (below confidence, producer not ready) store the
pointer in the existing `_mrnAliasProducer` field with `_mrnPath` left at
`MrnNone` — `renameDestRegs`' surgery is keyed on `mrnAliased()`
(rename.cc:1363), so an un-consumed pointer is inert there; Task 4 reads it
back at writeback. Document this in the field comment.

- [ ] **Step 1: DynInst edits** (as specified above; follow naming/accessor
  conventions verbatim from the fact block at dyn_inst.hh:488-534).

- [ ] **Step 2: rename.cc — deposit and consume**

In `renameInsts`, extend the existing MRN block (rename.cc:755-771). When
`memRenamePred && memRenamePred->valueFileEnabled()`:

**Store deposit** (new; before `renameDestRegs`, sources already renamed at
rename.cc:747): guards `inst->isStore() && !inst->isAtomic() &&
inst->numSrcRegs() > 0`, data register = last source, flattened
(`inst->srcRegIdx(n-1).flatten(*isa)`, pattern rename.cc:1272) must be
`IntRegClass`. Then:

```cpp
PhysRegIdPtr data_reg = inst->renamedSrcIdx(n - 1);
RegVal ready_val = 0;
const RegVal *rv = nullptr;
if (scoreboard->getReg(data_reg)) {
    ready_val = cpu->getReg(data_reg, inst->threadNumber);
    rv = &ready_val;
}
inst->setMrnVfRef(memRenamePred->vfStoreRename(
    inst->pcState().instAddr(), data_reg, inst->seqNum, rv));
```

**Load lookup + decision** (replaces the `tryMemRenameAlias` call and the
old value-path `predict()` for value_file mode — old paths run only when
`!valueFileEnabled()`; for an eligible load where the model has NO binding,
fall through to the old value path only if `valueForwardingEnabled()`):
guards `inst->isLoad() && inst->numDestRegs() == 1` and flattened dest is
`IntRegClass` → `setMrnVfEligible()`. Then:

```cpp
MrnVfCellRead cr = memRenamePred->vfLoadRename(load_pc);
bool vf_alias = false;          // consume as alias (before renameDestRegs)
bool vf_value_pending = false;  // consume as value (after renameDestRegs)
RegVal vf_value = 0;
uint8_t vf_value_mode = DynInst::MrnVfNone;
if (cr.bound) {
    inst->setMrnVfRef(cr.ref);
    const bool ptr_usable = cr.ptrValid && cr.ptr &&
        cr.ptr->is(IntRegClass) && !cr.ptr->isFixedMapping() &&
        cr.ptr->getRefCount() > 0;
    if (cr.confident) {
        if (ptr_usable && !scoreboard->getReg(cr.ptr) &&
            memRenamePred->aliasingEnabled()) {
            inst->setMrnAliasProducer(cr.ptr);
            inst->setMrnProducerSeq(cr.ptrSeq);
            inst->setMrnPath(DynInst::MrnAlias);
            inst->setMrnVfMode(DynInst::MrnVfAlias);
            memRenamePred->vfNotePredictMade(
                MemRenamePredictor::VfModeAlias);
            vf_alias = true;
        } else if (ptr_usable && scoreboard->getReg(cr.ptr) &&
                   memRenamePred->vfForwardProducerValue()) {
            vf_value = cpu->getReg(cr.ptr, inst->threadNumber);
            vf_value_pending = true;
            vf_value_mode = DynInst::MrnVfProducerValue;
        } else if (!cr.ptrValid && cr.valueValid &&
                   memRenamePred->vfForwardLastValue()) {
            vf_value = cr.value;
            vf_value_pending = true;
            vf_value_mode = DynInst::MrnVfLastValue;
        }
    } else {
        // Below threshold: snapshot what would have been predicted so
        // writeback can train confidence without consuming.
        if (cr.ptrValid && cr.ptr && scoreboard->getReg(cr.ptr)) {
            inst->setMrnVfShadowVal(
                cpu->getReg(cr.ptr, inst->threadNumber));
            inst->setMrnVfMode(DynInst::MrnVfShadowValue);
        } else if (cr.ptrValid && cr.ptr) {
            inst->setMrnAliasProducer(cr.ptr);   // pointer only; not aliased
            inst->setMrnVfMode(DynInst::MrnVfShadowPtr);
        } else if (cr.valueValid) {
            inst->setMrnVfShadowVal(cr.value);
            inst->setMrnVfMode(DynInst::MrnVfShadowValue);
        }
        memRenamePred->vfNoteBelowConf();  // wrapper name: see Task 2 stats
    }
}
```

After `renameDestRegs(...)` (rename.cc:773), where the old value path
forwards (pattern rename.cc:784-800), add the value_file consumption:

```cpp
if (vf_value_pending) {
    PhysRegIdPtr dest = inst->renamedDestIdx(0);
    if (dest->is(IntRegClass) && !dest->isFixedMapping()) {
        cpu->setReg(dest, vf_value, inst->threadNumber);
        scoreboard->setReg(dest);
        inst->setMrned();
        inst->setMrnPath(DynInst::MrnValue);
        inst->setMrnPredVal(vf_value);
        inst->setMrnVfMode(vf_value_mode);
        memRenamePred->noteForwarded();
        memRenamePred->noteForwardValue();
        memRenamePred->vfNotePredictMade(
            vf_value_mode == DynInst::MrnVfProducerValue
                ? MemRenamePredictor::VfModeProducerValue
                : MemRenamePredictor::VfModeLastValue);
    }
}
```

The aliased case (`vf_alias`) needs no post-`renameDestRegs` action: the
existing `mrnAliased()`-keyed surgery and `noteForwarded/noteForwardAlias`
block (rename.cc:816-823) fire as they do today.

- [ ] **Step 3: Build** (Global Constraints command). Expected: clean; both
  unit-test binaries still pass. `--mrn-correlation value-file` not yet
  exercised end-to-end (LSQ hooks land in Task 4) — a smoke run now would
  show deposits but no rebinds; do not run experiments in this task.

- [ ] **Step 4: Commit**

Header: `cpu-o3: Deposit and consume value-file bindings at rename`

---

### Task 4: LSQ publish/probe/last-value, verify training, squash accounting

**Files:**
- Modify: `src/cpu/o3/lsq_unit.cc` (executeStore, executeLoad, writeback,
  mrnVerifyAlias)
- Modify: `src/cpu/o3/rob.cc` (~355-372) and `src/cpu/o3/cpu.cc`
  (~1282-1298) squash blocks

**Interfaces:**
- Consumes: Task 2 wrapper methods; Task 3 DynInst API; existing anchors:
  `iewStage->getMemRenamePred()` (usage lsq_unit.cc:1155),
  `iewStage->isRegReady(...)` (lsq_unit.cc:1873),
  writeback block lsq_unit.cc:1142-1213, `mrnVerifyAlias`
  lsq_unit.cc:1822-1866, `checkViolations` call at lsq_unit.cc:737,
  `effAddrValid()` / `physEffAddr` (set in lsq.cc:820-825 / :871).

- [ ] **Step 1: Store publish (executeStore)**

Immediately before the `checkViolations(loadIt, store_inst)` call
(lsq_unit.cc:737), when the store fault is `NoFault`:

```cpp
if (MemRenamePredictor *mrn = iewStage->getMemRenamePred()) {
    if (mrn->valueFileEnabled() && store_inst->mrnVfRef().valid() &&
        store_inst->effAddrValid()) {
        mrn->vfStoreAddrResolved(store_inst->mrnVfRef(),
                                 store_inst->physEffAddr,
                                 store_inst->seqNum);
    }
}
```

- [ ] **Step 2: Load probe (executeLoad)**

After `inst->initiateAcc()` returns (lsq_unit.cc:623) and the fault is
`NoFault`, where `inst->effAddrValid()` holds (the existing check is at
lsq_unit.cc:667 — place the hook in that vicinity so blocked/deferred loads
that never resolved an address are excluded):

```cpp
if (MemRenamePredictor *mrn = iewStage->getMemRenamePred()) {
    if (mrn->valueFileEnabled() && inst->mrnVfEligible() &&
        inst->effAddrValid()) {
        mrn->vfLoadAddrResolved(inst->pcState().instAddr(),
                                inst->physEffAddr);
    }
}
```

A cache-blocked load that re-executes probes twice; the probe is idempotent
(`SameBinding`/`AlreadySelfBound` the second time) — acceptable, note in a
comment.

- [ ] **Step 3: Writeback — last-value, shadow training, consumed training**

In `LSQUnit::writeback` inside the `!inst->isExecuted()` block (which runs
once), after the producer-prediction resolution block (lsq_unit.cc:1153-1159)
and before the `isMrned()` verify block (lsq_unit.cc:1173):

```cpp
if (MemRenamePredictor *mrn = iewStage->getMemRenamePred();
    mrn && mrn->valueFileEnabled() && inst->isLoad() &&
    inst->mrnVfEligible() && inst->numDestRegs() > 0) {
    const Addr load_pc = inst->pcState().instAddr();
    const RegVal actual =
        cpu->getReg(inst->renamedDestIdx(0), inst->threadNumber);
    mrn->vfLoadDataResolved(load_pc, actual);   // self-bound last-value
    switch (inst->mrnVfMode()) {
      case DynInst::MrnVfShadowValue: {
        const bool ok = actual == inst->mrnVfShadowVal();
        mrn->vfNoteShadow(ok);
        mrn->vfTrainVerify(load_pc, inst->mrnVfRef(), ok);
        break;
      }
      case DynInst::MrnVfShadowPtr: {
        PhysRegIdPtr p = inst->mrnAliasProducer();
        if (p && iewStage->isRegReady(p)) {
            const bool ok =
                actual == cpu->getReg(p, inst->threadNumber);
            mrn->vfNoteShadow(ok);
            mrn->vfTrainVerify(load_pc, inst->mrnVfRef(), ok);
        } else {
            mrn->vfNoteShadowSkipped();
        }
        break;
      }
      default: break;   // consumed modes train via their verify paths
    }
}
```

(For an aliased load, `renamedDestIdx(0)` is the private execution register
holding the true loaded value after `completeAcc` — see the rename.cc
comment at :1355-1362 — so `actual` is correct for every mode.)

**Consumed value modes** (`MrnVfProducerValue`/`MrnVfLastValue`): in the
existing value-verify branch (lsq_unit.cc:1176-1211), next to the existing
`mrn->mispredict(...)` call (:1193) and its success counterpart, add — keyed
on `inst->mrnVfMode()`:

```cpp
// mismatch path:
mrn->vfNotePredictOutcome(vf_mode_index, false);
mrn->vfTrainVerify(load_pc, inst->mrnVfRef(), false);
// match path:
mrn->vfNotePredictOutcome(vf_mode_index, true);
mrn->vfTrainVerify(load_pc, inst->mrnVfRef(), true);
```

where `vf_mode_index` maps `MrnVfProducerValue → VfModeProducerValue`,
`MrnVfLastValue → VfModeLastValue`. Do NOT call the old-path
`mrn->mispredict()/commit-side` confidence for value_file loads' cells —
the old calls act on the old tables and are harmless, leave them as-is.

**Consumed alias mode** (`MrnVfAlias`): in `mrnVerifyAlias`
(lsq_unit.cc:1822-1866), in the mismatch branch (:1837-1853) and match
branch (:1854-1865), when `load->mrnVfMode() == DynInst::MrnVfAlias`:

```cpp
mrn->vfNotePredictOutcome(MemRenamePredictor::VfModeAlias, correct);
mrn->vfTrainVerify(load->pcState().instAddr(), load->mrnVfRef(), correct);
```

- [ ] **Step 4: Squash accounting**

The existing squash blocks already fire for consumed value_file predictions
(they set `Mrned`/`MrnAlias` exactly like the old paths and are counted by
`noteSquashedPrediction` keyed on `isMrned() && !mrnResolved()` —
rob.cc:356-361, cpu.cc:1283-1290). Add the per-mode value_file counter in
BOTH blocks, inside the same `if`, right after `noteSquashedPrediction`:

```cpp
if (inst->mrnVfMode() == DynInst::MrnVfAlias ||
    inst->mrnVfMode() == DynInst::MrnVfProducerValue ||
    inst->mrnVfMode() == DynInst::MrnVfLastValue) {
    mrn->vfNotePredictSquashed(/* map mode as in Step 3 */);
}
```

(`rob.cc` uses `squashing`, `cpu.cc` uses `inst` as the DynInst name.)
This preserves the identity vfPredictMade[m] = Correct[m] + Wrong[m] +
Squashed[m] because consumed predictions resolve exactly once through
verify-or-squash under the existing `MrnResolved` discipline.

- [ ] **Step 5: Build + unit tests + single-config smoke**

Build per Global Constraints; run both test binaries. Then smoke ONE tiny SE
run to prove the pipeline is wired (hello world is enough — no experiment):

```sh
LD_LIBRARY_PATH=/home/rbera/miniconda3/lib ./build/ARM/gem5.opt \
  --outdir=/tmp/vf_smoke configs/garfield/arm/se_run.py \
  --use-mrn --mrn-alias --mrn-no-value-forward \
  --mrn-correlation value-file --max-insts 2000000
grep -E 'vfDeposits|vfScPublishes|vfRebinds|vfPredictMade' /tmp/vf_smoke/stats.txt
```

Expected: nonzero `vfDepositsPtr` and `vfScPublishes`; `vfPredictMade` may
be small/zero on hello — the check is that stats exist and the sim exits 0.

- [ ] **Step 6: Commit**

Header: `cpu-o3: Wire value-file publish, probe and training in LSQ`

---

### Task 5: Experiments (controller-executed; scripts in `runs/`, gitignored)

**Not a subagent implementation task.** The controller builds the
microbenchmarks, runs the experiment matrix, and analyzes. Recorded here so
the plan is complete.

1. **Microbenchmarks:** cross-compile with the conda-forge toolchain
   (`CROSS=aarch64-conda-linux-gnu-` after
   `conda install --override-channels -c conda-forge gcc_linux-aarch64
   binutils_linux-aarch64`), `make -C
   gem5-infra/workloads/microbenchmarks` (env `GEM5_ROOT=<gem5 checkout>`);
   if libm5 fights the conda toolchain, build marker-free
   (`M5_DEFINE= LIBM5=`) — whole-run stats are acceptable (kernels are 20M
   iterations; init is negligible).
2. **Microbenchmark matrix** (`se_run.py --binary .../bin/<b> --args
   "2000000"`, `--use-mrn --mrn-alias --mrn-no-value-forward` plus):
   - baseline (no `--use-mrn`)
   - old alias path (`--mrn-correlation lsq-forward`)
   - value_file alias-only (`--mrn-correlation value-file
     --mrn-vf-no-producer-value --mrn-vf-no-last-value`)
   - value_file full (`--mrn-correlation value-file`)
   on both `mrnrec` (must newly capture the changing recurrence:
   `vfPredictMade[alias]` large, correctness ≥ 95%, IPC > baseline) and
   `mrncomm` (must not regress).
3. **gcc checkpoint** (`runs/` script cloned from
   `runs/mrn_correlator_gcc/run.sh`, 10M/50M, same checkpoint): the same
   four configurations; compare against the recorded old-alias run
   (`forwardsAlias` 1,702, accuracy 58.6%) and baseline IPC 0.578217.
   Verify the accounting identity per mode and the spec §8 success
   criteria before reporting.

---

## Self-Review Notes

- Spec coverage: §3 structures → Task 1; §4 E1/E2 → Task 3, E3/E4/E5 →
  Task 4; §5 consumption/verify/confidence → Tasks 3–4; §6 organization →
  Tasks 1–2; §8 experiments → Task 5. Gen semantics (§3.1) tested by
  `GenMismatchAfterReallocation`/`StaleRefPublishSuppressed`; program-order
  guard by `ScProgramOrderGuard`; deposit-clears-value by
  `DepositClearsStaleValue`; rebind/conf by `RebindResetsConfidence` +
  `WrongTrainResetsAndStaleTrainIgnored`.
- Type consistency: `MrnVfRef/MrnVfCellRead/MrnVfProbeResult` defined once
  (Task 1), consumed by name in Tasks 2–4; `VfMode` enum (Task 2) used in
  Tasks 3–4; DynInst accessors (Task 3) used in Task 4.
- Deliberate deviation noted inline: uniform LRU self-bind allocation
  (spec §4 E4 states it too).
