# VP Framework + Last-Value Predictor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the algorithm-agnostic Value Prediction framework in
`src/cpu/o3/vp/` plus the Last-Value Predictor that proves it end-to-end,
per `docs/superpowers/specs/2026-08-02-vp-framework-design.md`.

**Architecture:** Prefetcher-style SimObject hierarchy (`BaseValuePredictor`
abstract + `LastValueVP`) whose table logic lives in a params-free,
GTest-covered core (`LvpTable` + `vpKey`). Pipeline contract: predict at
rename behind the MRN → VP → execute priority ladder (value written into the
renamed dest physreg + scoreboard-ready, MRN's proven mechanism); train at
writeback for every in-scope instruction; wrong predictions trigger MRN's
inclusive verify-squash through a generalized `SquashReason` enum and a new
`IEW::squashDueToValueMispredict` sibling entry.

**Tech Stack:** gem5 SCons build, SimObject/pybind params codegen, GoogleTest
unit tests, existing Garfield run configs (`configs/garfield/arm/`).

## Global Constraints

- Branch `vp`; merge to `rbdev` only when the chapter is done.
- **Implementer subagents do NOT commit.** The controller commits after each
  task's review passes, via the repo `git-commit` skill: gem5 tag header
  ≤65 chars, body ≤72 cols, commit-note file under `docs/commit-notes/` in
  the same commit, `precommit-review` gate first, **never** any AI
  attribution trailer.
- C++: 79-col lines, 4-space indent, `UpperCamelCase` classes,
  `lowerCamelCase` methods/members, `snake_case` locals; function name on
  its own line in definitions. Python: black, 79 cols.
- **MRN algorithm code is untouched** except the exact Task 2 scope (the
  mechanical `SquashReason` rename + IEW body extraction). No naming from
  the design conversation may ship (precommit naming gate).
- Build host: run `scons` **from the repo root**
  (`/home/rbera/work/garfield/gem5`), never through a pipe that masks the
  exit code. Capture `rc=$?` explicitly. If configure/link fails on
  libpython, prefix `LD_LIBRARY_PATH=$HOME/miniconda3/lib`. Verify new code
  actually landed in the binary with
  `strings -a build/ALL/gem5.opt | grep -c <newSymbolOrStatName>`.
- Full build: `scons build/ALL/gem5.opt -j$(nproc)`. Unit test:
  `scons build/ALL/cpu/o3/vp/lvp_table.test.opt -j$(nproc)` then run the
  binary. Never run scons while simulation sweeps are running; check
  gem5 processes with `pgrep -cx gem5.opt` (never `pgrep -f`).
- Stats conventions for evaluation: FIRST stats-dump block only (ROI);
  IPC is the line ending `start.core.ipc` (the switch core is nan).
- New debug flag is `ValuePred`; DPRINTF only through it.
- The spec (`docs/superpowers/specs/2026-08-02-vp-framework-design.md`) is
  normative for behavior; this plan is normative for code shape. Exact
  line numbers below were verified 2026-08-02 and may drift a few lines —
  anchor on the quoted code, not the number.

## File Structure

New (all under `src/cpu/o3/vp/` unless noted):

| File | Responsibility |
|------|----------------|
| `vp_key.hh` | Params-free (PC, micro-PC) → key folding, GTest-covered |
| `lvp_table.{hh,cc}` | Params-free LVP core table (VPT): lookup/train, LRU, confidence |
| `lvp_table.test.cc` | GTests for `LvpTable` + `vpKey` |
| `base.{hh,cc}` | `BaseValuePredictor` SimObject: API, eligibility/scope, base stats |
| `last_value.{hh,cc}` | `LastValueVP` SimObject wrapping `LvpTable` + derived stats |
| `ValuePredictor.py` | SimObject declarations (abstract base + LVP) |
| `SConscript` | Registration: SimObject/Source/GTest/DebugFlag |

Modified: `src/cpu/o3/{BaseO3CPU.py, SConscript(no), dyn_inst.hh, rename.hh,
rename.cc, iew.hh, iew.cc, lsq_unit.cc, comm.hh, commit.cc, rob.hh, rob.cc,
cpu.hh, cpu.cc, mem_rename_predictor.hh, mem_rename_predictor_sim.cc}`,
`mrn_squash_reason.hh` → `squash_reason.hh` (git mv + rewrite),
`configs/garfield/arm/sim_opts.py`.
(gem5's `src/SConscript` auto-discovers per-directory SConscript files — no
parent SConscript edit is needed for the new `vp/` directory.)

Microbenchmarks (separate repo `/home/rbera/work/garfield/gem5-infra`):
`workloads/microbenchmarks/src/vpchase/`, `src/vpalu/` following the
existing `mrnrec` layout.

---

### Task 1: Params-Free LVP Core (`vp_key.hh`, `LvpTable`, GTests)

**Files:**
- Create: `src/cpu/o3/vp/vp_key.hh`
- Create: `src/cpu/o3/vp/lvp_table.hh`
- Create: `src/cpu/o3/vp/lvp_table.cc`
- Create: `src/cpu/o3/vp/lvp_table.test.cc`
- Create: `src/cpu/o3/vp/SConscript`
- Also staged into this task's commit by the controller: the pre-existing
  untracked `src/cpu/o3/vp/vp_spec.md` and `src/cpu/o3/vp/papers/*.pdf`
  (chapter kickoff material; user-approved).

**Interfaces:**
- Consumes: nothing (params-free; only `base/types.hh`).
- Produces: `Addr gem5::o3::vpKey(Addr pc, MicroPC upc)`;
  `struct LvpConfig {unsigned entries=4096, assoc=4, confBits=4,
  confThreshold=15; bool confDecrementOnWrong=false;}`;
  `struct LvpLookup {bool hit, confident; RegVal value;}`;
  `enum class LvpTrainOutcome {Allocated, Match, MismatchReset,
  MismatchDecrement}`;
  `class LvpTable { explicit LvpTable(const LvpConfig&);
  LvpLookup lookup(Addr key) const;
  LvpTrainOutcome train(Addr key, RegVal actual); }`.

- [ ] **Step 1: Write `vp_key.hh`** (complete file):

```cpp
#ifndef __CPU_O3_VP_VP_KEY_HH__
#define __CPU_O3_VP_VP_KEY_HH__

#include "base/types.hh"

namespace gem5
{
namespace o3
{

/**
 * Fold an instruction's (PC, micro-PC) into the value-prediction lookup
 * key. Cracked macro-ops (e.g. an AArch64 ldp splitting into two
 * micro-ops) share a PC; without the micro-PC in the key their distinct
 * destination values would ping-pong one table entry and confidence
 * could never build. The micro-PC lands in the upper bits, away from
 * the set-index bits, so the micro-ops of one PC land in the same set
 * with distinct tags.
 */
static inline Addr
vpKey(Addr pc, MicroPC upc)
{
    return pc ^ (static_cast<Addr>(upc) << 48);
}

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_VP_KEY_HH__
```

- [ ] **Step 2: Write the failing tests** — `lvp_table.test.cc` (complete
  file; mirrors the plain-`TEST` idiom of `mem_rename_valuefile.test.cc`):

```cpp
#include <gtest/gtest.h>

#include "cpu/o3/vp/lvp_table.hh"
#include "cpu/o3/vp/vp_key.hh"

using namespace gem5;
using namespace gem5::o3;

namespace
{

// Small geometry: 4 sets x 2 ways, 2-bit confidence, threshold 2.
LvpConfig
testConfig()
{
    LvpConfig c;
    c.entries = 8;
    c.assoc = 2;
    c.confBits = 2;
    c.confThreshold = 2;
    c.confDecrementOnWrong = false;
    return c;
}

// Train the same (key, value) pair n times.
void
trainN(LvpTable &t, Addr key, RegVal val, int n)
{
    for (int i = 0; i < n; i++) {
        t.train(key, val);
    }
}

} // namespace

TEST(LvpTable, ColdLookupMisses)
{
    LvpTable t(testConfig());
    auto r = t.lookup(0x400);
    EXPECT_FALSE(r.hit);
    EXPECT_FALSE(r.confident);
}

TEST(LvpTable, FirstTrainAllocatesUnconfident)
{
    LvpTable t(testConfig());
    EXPECT_EQ(t.train(0x400, 42), LvpTrainOutcome::Allocated);
    auto r = t.lookup(0x400);
    EXPECT_TRUE(r.hit);
    EXPECT_FALSE(r.confident); // conf starts at 0, threshold is 2
    EXPECT_EQ(r.value, 42u);
}

TEST(LvpTable, ConfidenceBuildsToThreshold)
{
    LvpTable t(testConfig());
    t.train(0x400, 42);                      // alloc, conf = 0
    EXPECT_EQ(t.train(0x400, 42), LvpTrainOutcome::Match); // conf = 1
    EXPECT_FALSE(t.lookup(0x400).confident);
    EXPECT_EQ(t.train(0x400, 42), LvpTrainOutcome::Match); // conf = 2
    auto r = t.lookup(0x400);
    EXPECT_TRUE(r.confident); // conf == threshold predicts
    EXPECT_EQ(r.value, 42u);
}

TEST(LvpTable, MismatchResetsConfidenceAndUpdatesValue)
{
    LvpTable t(testConfig());
    trainN(t, 0x400, 42, 4); // confident (saturated at 3)
    ASSERT_TRUE(t.lookup(0x400).confident);
    EXPECT_EQ(t.train(0x400, 99), LvpTrainOutcome::MismatchReset);
    auto r = t.lookup(0x400);
    EXPECT_TRUE(r.hit);
    EXPECT_FALSE(r.confident); // reset to zero
    EXPECT_EQ(r.value, 99u);   // last value always updated
}

TEST(LvpTable, MismatchDecrementMode)
{
    LvpConfig c = testConfig();
    c.confDecrementOnWrong = true;
    LvpTable t(c);
    trainN(t, 0x400, 42, 4); // conf saturated at 3
    EXPECT_EQ(t.train(0x400, 99), LvpTrainOutcome::MismatchDecrement);
    // conf = 2 == threshold: still confident, value updated.
    auto r = t.lookup(0x400);
    EXPECT_TRUE(r.confident);
    EXPECT_EQ(r.value, 99u);
    EXPECT_EQ(t.train(0x400, 42), LvpTrainOutcome::MismatchDecrement);
    EXPECT_FALSE(t.lookup(0x400).confident); // conf = 1 < threshold
}

TEST(LvpTable, ConfidenceSaturatesAtCounterMax)
{
    LvpTable t(testConfig());
    trainN(t, 0x400, 42, 100); // way past 2-bit max (3)
    ASSERT_TRUE(t.lookup(0x400).confident);
    // One wrong resets from saturation; two rights get back to threshold.
    t.train(0x400, 7);
    EXPECT_FALSE(t.lookup(0x400).confident);
    trainN(t, 0x400, 7, 2);
    EXPECT_TRUE(t.lookup(0x400).confident);
}

TEST(LvpTable, LruEvictionWithinSet)
{
    LvpTable t(testConfig()); // 4 sets x 2 ways; index = (key >> 2) & 3
    // Three keys in set 0: 0x000, 0x010, 0x020 (bits [3:2] == 0).
    t.train(0x000, 1); // way A (LRU after the next train)
    t.train(0x010, 2); // way B
    t.train(0x020, 3); // evicts 0x000 (LRU)
    EXPECT_FALSE(t.lookup(0x000).hit);
    EXPECT_TRUE(t.lookup(0x010).hit);
    EXPECT_TRUE(t.lookup(0x020).hit);
    // Training 0x010 refreshes it; the next alloc evicts 0x020.
    t.train(0x010, 2);
    t.train(0x030, 4);
    EXPECT_TRUE(t.lookup(0x010).hit);
    EXPECT_FALSE(t.lookup(0x020).hit);
}

TEST(LvpTable, LookupDoesNotTouchLru)
{
    LvpTable t(testConfig());
    t.train(0x000, 1);
    t.train(0x010, 2);
    // Lookups on 0x000 must not refresh it: it is still the LRU victim.
    (void)t.lookup(0x000);
    (void)t.lookup(0x000);
    t.train(0x020, 3);
    EXPECT_FALSE(t.lookup(0x000).hit);
    EXPECT_TRUE(t.lookup(0x010).hit);
}

TEST(LvpTable, WrongThenRetrainRecovers)
{
    LvpTable t(testConfig());
    trainN(t, 0x400, 42, 3);
    t.train(0x400, 99); // reset
    trainN(t, 0x400, 99, 2);
    auto r = t.lookup(0x400);
    EXPECT_TRUE(r.confident);
    EXPECT_EQ(r.value, 99u);
}

TEST(VpKey, MicroPcDistinguishesCrackedMicroOps)
{
    const Addr pc = 0x400890;
    EXPECT_NE(vpKey(pc, 0), vpKey(pc, 1));
    // Same set (low bits untouched), distinct tags.
    LvpTable t(testConfig());
    t.train(vpKey(pc, 0), 111);
    t.train(vpKey(pc, 1), 222);
    EXPECT_EQ(t.lookup(vpKey(pc, 0)).value, 111u);
    EXPECT_EQ(t.lookup(vpKey(pc, 1)).value, 222u);
}

TEST(VpKey, PlainPcIsIdentity)
{
    EXPECT_EQ(vpKey(0x400890, 0), 0x400890u);
}
```

- [ ] **Step 3: Write `lvp_table.hh`** (complete file):

```cpp
#ifndef __CPU_O3_VP_LVP_TABLE_HH__
#define __CPU_O3_VP_LVP_TABLE_HH__

#include <cstdint>
#include <vector>

#include "base/types.hh"

namespace gem5
{
namespace o3
{

/**
 * Plain-int configuration for LvpTable. Mirrors the LastValueVP SimObject
 * params but is free of any params/SimObject machinery, so the core logic
 * can be built and unit-tested in isolation (the pattern proven by
 * MrnValueFileTables).
 */
struct LvpConfig
{
    unsigned entries = 4096;
    unsigned assoc = 4;
    /** Saturating confidence counter width. */
    unsigned confBits = 4;
    /** Minimum confidence required to predict. */
    unsigned confThreshold = 15;
    /** Decrement (rather than reset to zero) confidence on a value
     *  mismatch. */
    bool confDecrementOnWrong = false;
};

/** What a rename-time lookup saw. */
struct LvpLookup
{
    bool hit = false;
    /** conf >= confThreshold: the value below may be consumed. */
    bool confident = false;
    RegVal value = 0;
};

/** What a train() call did (feeds the wrapper's derived stats). */
enum class LvpTrainOutcome
{
    Allocated,
    Match,
    MismatchReset,
    MismatchDecrement
};

/**
 * The last-value prediction table (VPT): set-associative, LRU, full tags
 * (a research simulator should not fold false aliasing artifacts into
 * results). Entry: {valid, tag, lastValue, conf}.
 */
class LvpTable
{
  public:
    explicit LvpTable(const LvpConfig &cfg);

    /** Rename-time lookup. Never modifies the table -- recency is
     *  tracked at train, which runs for every in-scope instruction. */
    LvpLookup lookup(Addr key) const;

    /** Writeback-time training with the architected value: match
     *  increments confidence (saturating); mismatch resets (default) or
     *  decrements it, and always updates the stored value; a miss
     *  allocates over the LRU way with confidence zero. */
    LvpTrainOutcome train(Addr key, RegVal actual);

  private:
    struct Entry
    {
        bool valid = false;
        Addr tag = 0;
        RegVal lastValue = 0;
        unsigned conf = 0;
        uint64_t lastUse = 0;
    };

    unsigned setIndex(Addr key) const;

    const unsigned sets;
    const unsigned assoc;
    const unsigned confMax;
    const unsigned confThreshold;
    const bool confDecrementOnWrong;

    /** Monotonic use counter backing LRU (no wall-clock dependence). */
    uint64_t useCounter = 0;

    /** sets x assoc entries, row-major by set. */
    std::vector<Entry> table;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_LVP_TABLE_HH__
```

- [ ] **Step 4: Write `lvp_table.cc`** (complete file):

```cpp
#include "cpu/o3/vp/lvp_table.hh"

#include "base/intmath.hh"
#include "base/logging.hh"

namespace gem5
{
namespace o3
{

LvpTable::LvpTable(const LvpConfig &cfg)
    : sets(cfg.assoc ? cfg.entries / cfg.assoc : 0),
      assoc(cfg.assoc),
      confMax((1u << cfg.confBits) - 1),
      confThreshold(cfg.confThreshold),
      confDecrementOnWrong(cfg.confDecrementOnWrong),
      table(sets * cfg.assoc)
{
    fatal_if(cfg.assoc == 0 || cfg.entries % cfg.assoc != 0,
             "LVP entries (%u) must be a nonzero multiple of assoc (%u)",
             cfg.entries, cfg.assoc);
    fatal_if(!isPowerOf2(sets), "LVP set count (%u) must be a power of two",
             sets);
    fatal_if(confThreshold > confMax,
             "LVP confThreshold (%u) exceeds the %u-bit counter max (%u)",
             confThreshold, cfg.confBits, confMax);
}

unsigned
LvpTable::setIndex(Addr key) const
{
    // Low two bits of an AArch64 PC are zero; the micro-PC is folded into
    // the high bits (vp_key.hh), so bits [2..] index well.
    return (key >> 2) & (sets - 1);
}

LvpLookup
LvpTable::lookup(Addr key) const
{
    const Entry *set = &table[setIndex(key) * assoc];
    for (unsigned w = 0; w < assoc; w++) {
        if (set[w].valid && set[w].tag == key) {
            LvpLookup r;
            r.hit = true;
            r.confident = set[w].conf >= confThreshold;
            r.value = set[w].lastValue;
            return r;
        }
    }
    return {};
}

LvpTrainOutcome
LvpTable::train(Addr key, RegVal actual)
{
    Entry *set = &table[setIndex(key) * assoc];
    Entry *hit = nullptr;
    for (unsigned w = 0; w < assoc; w++) {
        if (set[w].valid && set[w].tag == key) {
            hit = &set[w];
            break;
        }
    }

    if (!hit) {
        Entry *victim = &set[0];
        for (unsigned w = 1; w < assoc && victim->valid; w++) {
            if (!set[w].valid || set[w].lastUse < victim->lastUse) {
                victim = &set[w];
            }
        }
        victim->valid = true;
        victim->tag = key;
        victim->lastValue = actual;
        victim->conf = 0;
        victim->lastUse = ++useCounter;
        return LvpTrainOutcome::Allocated;
    }

    hit->lastUse = ++useCounter;
    if (actual == hit->lastValue) {
        if (hit->conf < confMax) {
            hit->conf++;
        }
        return LvpTrainOutcome::Match;
    }

    hit->lastValue = actual;
    if (confDecrementOnWrong) {
        if (hit->conf > 0) {
            hit->conf--;
        }
        return LvpTrainOutcome::MismatchDecrement;
    }
    hit->conf = 0;
    return LvpTrainOutcome::MismatchReset;
}

} // namespace o3
} // namespace gem5
```

- [ ] **Step 5: Write `src/cpu/o3/vp/SConscript`** (complete file; the
  SimObject/DebugFlag lines arrive in Task 3 — keep this task buildable):

```python
Import('*')

if env['CONF']['BUILD_ISA']:
    Source('lvp_table.cc')

    GTest('lvp_table.test', 'lvp_table.test.cc', 'lvp_table.cc')
```

(If the GTest link fails on logging symbols from `fatal_if`, add the same
transitive deps the MRN GTest uses: `'../../../base/debug.cc'` — check the
`mem_rename_valuefile.test` line in `src/cpu/o3/SConscript:81-83` for the
relative-path idiom; note paths are relative to `src/cpu/o3/vp/` here, one
directory deeper.)

- [ ] **Step 6: Build and run the unit tests**

Run (repo root):
`scons build/ALL/cpu/o3/vp/lvp_table.test.opt -j$(nproc); echo rc=$?`
Expected: `rc=0`.
Run: `./build/ALL/cpu/o3/vp/lvp_table.test.opt`
Expected: all 11 tests PASS (`LvpTable.*` ×9, `VpKey.*` ×2).

- [ ] **Step 7: Hand back for review + controller commit**
  Suggested header: `cpu-o3: Add params-free LVP core table for VP`

---

### Task 2: SquashReason Generalization + IEW Inclusive-Squash Extraction

**Files:**
- Rename: `src/cpu/o3/mrn_squash_reason.hh` → `src/cpu/o3/squash_reason.hh`
  (`git mv`, then rewrite content)
- Modify: `src/cpu/o3/iew.hh` (~lines 264-278), `src/cpu/o3/iew.cc`
  (~477-528, 1351, 495/524), `src/cpu/o3/comm.hh` (~105-109),
  `src/cpu/o3/commit.cc` (~527, 959), `src/cpu/o3/rob.hh` (~210-226, 352),
  `src/cpu/o3/rob.cc` (~113, 343-377), `src/cpu/o3/cpu.cc` (~1291),
  `src/cpu/o3/mem_rename_predictor.hh` (include + ~100),
  `src/cpu/o3/mem_rename_predictor_sim.cc` (~134-141),
  `src/cpu/o3/lsq_unit.cc` (MRN squash call sites ~1301, ~1929)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `enum class SquashReason {Branch, MemOrder, MrnValue, MrnAlias,
  ValuePred, Other, Num}` + `squashReasonNames[]` in
  `cpu/o3/squash_reason.hh`; renamed wire field
  `IEWStruct::squashReason[MaxThreads]`; renamed ROB accessors
  `setSquashReason(tid, r)` / `getSquashReason(tid)`; **public**
  `void IEW::squashDueToValueMispredict(const DynInstPtr &inst, ThreadID
  tid)`; private `void IEW::squashInclusive(const DynInstPtr &inst,
  ThreadID tid, SquashReason reason)`.

This is a **pure mechanical generalization — zero behavior change** (the
only observable difference: the reason-indexed MRN squash stats gain a
structurally-zero `valuePred` bucket).

- [ ] **Step 1: `git mv src/cpu/o3/mrn_squash_reason.hh
  src/cpu/o3/squash_reason.hh`** and rewrite its live content (keep the
  existing license header verbatim):

```cpp
#ifndef __CPU_O3_SQUASH_REASON_HH__
#define __CPU_O3_SQUASH_REASON_HH__

namespace gem5
{
namespace o3
{

/**
 * Garfield: why a pipeline squash was raised / why an in-flight
 * speculative-dataflow prediction (MRN, VP) was discarded.
 *
 * A prediction consumed at rename resolves exactly once: it verifies
 * correct, verifies wrong (mispredict), or is squashed before it can
 * verify at all. This enum categorizes that third outcome; it is plumbed
 * from the squash initiator (IEW) through IEWStruct to Commit to the ROB,
 * because the cause cannot be recovered at the squash site --
 * IEW::squashInclusive is shared by real memory-order violations, both
 * MRN mispredict paths, and VP mispredicts.
 *
 * Deliberately coarse. Traps, interrupts, ReExec replays, HTM aborts,
 * ThreadContext writes, drain and squash-after all collapse into Other;
 * they are expected to be near-zero for compute-bound regions. Front-end
 * squashes (decode, FTQ, BAC) cannot appear here at all -- they discard
 * instructions upstream of rename, which have no prediction yet.
 */
enum class SquashReason
{
    /** Branch mispredict (IEW::squashDueToBranch). */
    Branch,
    /** A real memory-order violation: store->load, or load->load by snoop. */
    MemOrder,
    /** An OLDER value-forwarding MRN mispredict squashed this load. */
    MrnValue,
    /** An OLDER producer-aliasing MRN mispredict squashed this load. */
    MrnAlias,
    /** An OLDER wrong value prediction (VP) squashed this instruction. */
    ValuePred,
    /** Trap, interrupt, ReExec, HTM abort, TC write, drain, squash-after. */
    Other,
    Num
};

/** Stat subnames, indexed by SquashReason. */
constexpr const char *squashReasonNames[] = {
    "branch", "memOrder", "mrnValue", "mrnAlias", "valuePred", "other"};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_SQUASH_REASON_HH__
```

- [ ] **Step 2: Mechanical rename across `src/cpu/o3/`.** Apply exactly:
  - `#include "cpu/o3/mrn_squash_reason.hh"` →
    `#include "cpu/o3/squash_reason.hh"` (sites: `mem_rename_predictor.hh`,
    plus wherever else grep finds it — `comm.hh`, `iew.hh`, `rob.hh`).
  - Type `MrnSquashReason` → `SquashReason` (all uses).
  - Array `mrnSquashReasonNames` → `squashReasonNames`
    (`mem_rename_predictor_sim.cc` stats-init loop).
  - Wire field `IEWStruct::mrnSquashReason` → `squashReason` (`comm.hh:109`
    decl + writers `iew.cc:495`, `iew.cc:524` + reader `commit.cc:959`).
    Update the field's comment to say the initiator may be a memory-order
    violation, an MRN mispredict, or a VP mispredict.
  - ROB: `setMrnSquashReason` → `setSquashReason`, `getMrnSquashReason` →
    `getSquashReason`, member `mrnSquashReason[MaxThreads]` →
    `squashReason[MaxThreads]` (`rob.hh:210-226,352`; `rob.cc:113,361`;
    callers `commit.cc:527,959`, `cpu.cc:1291`).
  - Verify with: `grep -rn 'MrnSquashReason\|mrnSquashReason' src/` →
    expected **zero** hits.

- [ ] **Step 3: Extract the IEW inclusive-squash body + add the VP sibling.**
  In `iew.hh`, replace the `squashDueToMemOrder` declaration block
  (~iew.hh:264-272) with:

```cpp
    /** Squashes from an instruction inclusive: the instruction itself
     *  and everything younger refetch (commit redirects to the
     *  instruction's own PC). Public so the LSQ can trigger MRN
     *  misprediction recovery via its iewStage pointer. @param reason
     *  why the squash was raised -- shared by real memory-order
     *  violations and both MRN mispredict paths, and only the caller
     *  knows which. Carried to the ROB for the squash accounting. */
    void squashDueToMemOrder(const DynInstPtr &inst, ThreadID tid,
                             SquashReason reason);

    /** Garfield VP: inclusive squash for a wrong value prediction. The
     *  predicted instruction refetches and -- with its confidence
     *  dropped by training before the refetch re-renames -- is not
     *  re-predicted, so no squash livelock is possible. */
    void squashDueToValueMispredict(const DynInstPtr &inst, ThreadID tid);
```

  and in the private section (next to `squashDueToBranch`, ~iew.hh:278):

```cpp
    /** Shared body of the inclusive squashes: squash from inst
     *  (inclusive) with the given reason on the IEW->commit wire. */
    void squashInclusive(const DynInstPtr &inst, ThreadID tid,
                         SquashReason reason);
```

  In `iew.cc`, replace the whole `IEW::squashDueToMemOrder` definition
  (~iew.cc:502-528) with (the body is the old one verbatim, DPRINTF text
  generalized):

```cpp
void
IEW::squashInclusive(const DynInstPtr &inst, ThreadID tid,
                     SquashReason reason)
{
    DPRINTF(IEW, "[tid:%i] Squashing from PC %s [sn:%llu] inclusive.\n",
            tid, inst->pcState(), inst->seqNum);
    // Need to include inst->seqNum in the following comparison to cover the
    // corner case when a branch misprediction and a memory violation for the
    // same instruction (e.g. load PC) are detected in the same cycle.  In this
    // case the memory violator should take precedence over the branch
    // misprediction because it requires the violator itself to be included in
    // the squash.
    if (!toCommit->squash[tid] ||
            inst->seqNum <= toCommit->squashedSeqNum[tid]) {
        toCommit->squash[tid] = true;

        toCommit->squashedSeqNum[tid] = inst->seqNum;
        set(toCommit->pc[tid], inst->pcState());
        toCommit->mispredictInst[tid] = NULL;

        // Must include the squashing instruction in the squash.
        toCommit->includeSquashInst[tid] = true;
        toCommit->squashReason[tid] = reason;

        wroteToTimeBuffer = true;
    }
}

void
IEW::squashDueToMemOrder(const DynInstPtr &inst, ThreadID tid,
                         SquashReason reason)
{
    squashInclusive(inst, tid, reason);
}

void
IEW::squashDueToValueMispredict(const DynInstPtr &inst, ThreadID tid)
{
    squashInclusive(inst, tid, SquashReason::ValuePred);
}
```

- [ ] **Step 4: Full build + zero-diff verification**

Run (repo root): `scons build/ALL/gem5.opt -j$(nproc); echo rc=$?`
Expected: `rc=0`.
Run: `grep -rn 'MrnSquashReason\|mrnSquashReason' src/ | wc -l`
Expected: `0`.
Run a 30-second MRN smoke (any quick SE workload, e.g.
`./build/ALL/gem5.opt configs/garfield/arm/se_run.py --use-mrn --mrn-alias
--mrn-conf-threshold 14 <bench args from runs/ precedent>`); confirm the
`predictionsSquashed*::valuePred` bucket exists and is 0, and the run
completes. (Reviewer note: the run itself may be deferred to Task 4's
smoke if SE arguments need discovery; the build + grep gates are the hard
requirement here.)

- [ ] **Step 5: Hand back for review + controller commit**
  Suggested header: `cpu-o3: Generalize squash-reason plumbing beyond MRN`

---

### Task 3: SimObject Layer (`BaseValuePredictor`, `LastValueVP`, params, DynInst state)

**Files:**
- Create: `src/cpu/o3/vp/ValuePredictor.py`
- Create: `src/cpu/o3/vp/base.hh`, `src/cpu/o3/vp/base.cc`
- Create: `src/cpu/o3/vp/last_value.hh`, `src/cpu/o3/vp/last_value.cc`
- Modify: `src/cpu/o3/vp/SConscript` (add SimObject/Sources/DebugFlag)
- Modify: `src/cpu/o3/BaseO3CPU.py` (insert after `memRenamePredictor`,
  ~line 215)
- Modify: `src/cpu/o3/dyn_inst.hh` (flags enum ~line 198; accessors after
  the `mrnVfShadowVal` block ~line 599; private field near `_mrnPredVal`
  ~line 1231)

**Interfaces:**
- Consumes: Task 1 (`LvpTable`, `LvpConfig`, `LvpLookup`,
  `LvpTrainOutcome`, `vpKey`).
- Produces: `class BaseValuePredictor : public SimObject` with
  `std::optional<RegVal> predict(const DynInstPtr&)`,
  `void train(const DynInstPtr&, RegVal)`,
  `void verifyResult(const DynInstPtr&, bool correct, uint64_t flushed)`,
  `void notifySquashed(const DynInstPtr&)`,
  `virtual void notifyPipelineSquash() {}`,
  `bool onlyLoads() const`, `bool inScope(const DynInstPtr&) const`;
  protected pure virtuals `predictImpl(Addr)` / `trainImpl(Addr, RegVal)`;
  DynInst: flags `VpPredicted`, `VpResolved` + accessors
  `vpPredicted()/setVpPredicted()`, `vpResolved()/setVpResolved()`,
  `vpPredVal()/setVpPredVal(RegVal)`; O3 param `valuePred`
  (`params.valuePred`, NULL default).

**Contract notes (from the spec, binding):**
- `predict()`/`train()` may only be called **after `renameDestRegs`** (they
  read `renamedDestIdx(0)`); the base class alone decides eligibility.
- Eligible = single scalar integer dest
  (`renamedDestIdx(0)->is(IntRegClass)`, not fixed-mapping, exactly one
  dest), not serializing/barrier/non-speculative/atomic/store-conditional.
- In scope = eligible ∧ (`!onlyLoads` ∨ `isLoad()`).
- Stats counting sites: `eligibleLoads/eligibleNonLoads` at `train()`;
  `predictionsMade` at `predict()`; identity
  `made = correct + wrong + squashed` (± in-flight at dump).

- [ ] **Step 1: DynInst state.** In `dyn_inst.hh` flags enum, after
  `MrnVfEligible` (before `MaxFlags`):

```cpp
        VpPredicted,   /// Garfield VP: a value prediction was consumed
                       /// into this instruction's renamed destination
        VpResolved,    /// Garfield VP: the prediction was resolved
                       /// (verified or accounted squashed); a squash
                       /// must not re-account it
```

  After the `mrnVfShadowVal` accessor block (~line 599):

```cpp
    /** Garfield VP: a value prediction was forwarded into this
     *  instruction's renamed destination at rename. */
    bool
    vpPredicted() const
    {
        return instFlags[VpPredicted];
    }
    void
    setVpPredicted()
    {
        instFlags[VpPredicted] = true;
    }

    /** Garfield VP: the prediction resolved -- verified correct,
     *  verified wrong, or accounted squashed-before-verify. Set on all
     *  resolution arms (the verify squash is inclusive, so a
     *  mispredicting instruction would otherwise be double-counted as
     *  a squashed prediction). */
    bool
    vpResolved() const
    {
        return instFlags[VpResolved];
    }
    void
    setVpResolved()
    {
        instFlags[VpResolved] = true;
    }

    /** Garfield VP: the predicted value consumed at rename. */
    RegVal
    vpPredVal() const
    {
        return _vpPredVal;
    }
    void
    setVpPredVal(RegVal v)
    {
        _vpPredVal = v;
    }
```

  Private field, next to `_mrnPredVal` (~line 1231):

```cpp
    /** Garfield VP: value-predicted value consumed at rename. */
    RegVal _vpPredVal = 0;
```

- [ ] **Step 2: `ValuePredictor.py`** (complete file):

```python
from m5.params import *
from m5.SimObject import SimObject


class BaseValuePredictor(SimObject):
    type = "BaseValuePredictor"
    abstract = True
    cxx_class = "gem5::o3::BaseValuePredictor"
    cxx_header = "cpu/o3/vp/base.hh"

    onlyLoads = Param.Bool(
        True,
        "Predict loads only; when false, every eligible (single scalar "
        "integer destination) instruction is in scope.",
    )
    scalarOnly = Param.Bool(
        True,
        "Restrict prediction to scalar destinations. Currently subsumed "
        "by the integer-only eligibility rule; the knob exists so the "
        "interface is stable when FP/vector support lands.",
    )


class LastValueVP(BaseValuePredictor):
    type = "LastValueVP"
    cxx_class = "gem5::o3::LastValueVP"
    cxx_header = "cpu/o3/vp/last_value.hh"

    entries = Param.Unsigned(4096, "Value prediction table entries")
    assoc = Param.Unsigned(4, "Value prediction table associativity")
    confBits = Param.Unsigned(4, "Confidence counter width in bits")
    confThreshold = Param.Unsigned(
        15, "Minimum confidence required to predict"
    )
    confDecrementOnWrong = Param.Bool(
        False,
        "Decrement (rather than reset to zero) confidence on a value "
        "mismatch",
    )
```

- [ ] **Step 3: `base.hh`** (complete file):

```cpp
#ifndef __CPU_O3_VP_BASE_HH__
#define __CPU_O3_VP_BASE_HH__

#include <cstdint>
#include <optional>

#include "base/statistics.hh"
#include "base/types.hh"
#include "cpu/o3/dyn_inst_ptr.hh"
#include "sim/sim_object.hh"

namespace gem5
{

// Forward declaration of the generated params struct. The SimObject
// constructor stays out-of-line (in base.cc) so this header does not
// pull in the generated params/BaseValuePredictor.hh and stays cheap to
// include from pipeline code (rename/iew/lsq).
struct BaseValuePredictorParams;

namespace o3
{

/**
 * Garfield VP: algorithm-agnostic value-predictor base (design doc
 * docs/superpowers/specs/2026-08-02-vp-framework-design.md).
 *
 * The pipeline contract has three operations plus one reserved hook:
 *  - predict() at rename (after renameDestRegs, and only for
 *    instructions MRN did not claim): the base class alone decides
 *    eligibility and scope; a returned value has already been counted
 *    and stamped on the instruction, and the caller forwards it into
 *    the renamed destination (physreg write + scoreboard ready).
 *  - train() at writeback for every in-scope, not-already-squashed
 *    instruction -- whether or not a prediction was made, and including
 *    MRN-claimed loads: the tables stay warm regardless of predictor
 *    engagement.
 *  - verifyResult()/notifySquashed(): outcome accounting from the
 *    verify sites and the squash walks.
 * Derived predictors implement predictImpl()/trainImpl() over the
 * folded (PC, micro-PC) key (vp_key.hh) and keep their table logic in a
 * params-free, unit-tested core class.
 */
class BaseValuePredictor : public SimObject
{
  public:
    BaseValuePredictor(const BaseValuePredictorParams &p);

    /** Rename-time lookup (call only after renameDestRegs). Returns a
     *  value to consume, or nullopt for: ineligible, out of scope,
     *  table miss, or below the confidence threshold. On a hit the
     *  base class counts predictionsMade and stamps
     *  setVpPredicted()/setVpPredVal() on the instruction. */
    std::optional<RegVal> predict(const DynInstPtr &inst);

    /** Writeback-time training with the architected value. Counts the
     *  eligible population (the coverage denominator) and delegates to
     *  trainImpl(). No-op for out-of-scope instructions, so call sites
     *  stay thin. */
    void train(const DynInstPtr &inst, RegVal actualValue);

    /** Verify-site outcome accounting for a consumed prediction.
     *  @param flushed the measured inclusive squash cost when wrong
     *  (0 when correct). Level attribution runs for loads only. */
    void verifyResult(const DynInstPtr &inst, bool correct,
                      uint64_t flushed);

    /** A consumed prediction was discarded before it could verify
     *  (counted, never trained). Called from the ROB/CPU squash walks
     *  under the VpPredicted && !VpResolved exactly-once guard. */
    void notifySquashed(const DynInstPtr &inst);

    /** Reserved hook: predictors carrying speculative state (VTAGE
     *  class) restore it here on any pipeline squash. LVP ignores it. */
    virtual void notifyPipelineSquash() {}

    /** Scope knob: loads only (default) vs all eligible instructions. */
    bool
    onlyLoads() const
    {
        return _onlyLoads;
    }

    /** Eligibility (hard rules) AND scope (onlyLoads). Public so the
     *  IEW non-load site can pre-filter before reading the dest reg. */
    bool inScope(const DynInstPtr &inst) const;

  protected:
    /** Algorithm lookup over the folded key. */
    virtual std::optional<RegVal> predictImpl(Addr key) = 0;
    /** Algorithm training over the folded key. */
    virtual void trainImpl(Addr key, RegVal actualValue) = 0;

    /** Hard eligibility rules: single scalar integer, non-fixed-mapping
     *  destination; not serializing / barrier / non-speculative /
     *  atomic / store-conditional. */
    bool eligible(const DynInstPtr &inst) const;

    const bool _onlyLoads;
    /** Subsumed by the integer-only rule today; retained so the
     *  interface is stable when FP/vector support lands. */
    const bool _scalarOnly;

    struct VpStats : public statistics::Group
    {
        explicit VpStats(statistics::Group *parent);

        /** In-scope instructions reaching the train site (the coverage
         *  denominator), split loads / non-loads. Includes MRN-claimed
         *  loads; excludes already-squashed instructions. */
        statistics::Scalar eligibleLoads;
        statistics::Scalar eligibleNonLoads;
        /** Predictions consumed at rename (speculative path). Identity:
         *  made == correct + wrong + squashed (+- in flight at the
         *  dump boundary). */
        statistics::Scalar predictionsMade;
        statistics::Scalar predictionsCorrect;
        statistics::Scalar predictionsWrong;
        /** Consumed predictions discarded before they could verify. */
        statistics::Scalar predictionsSquashed;
        /** Instructions discarded by VP misprediction squashes
         *  (inclusive: the mispredicted instruction itself counts). */
        statistics::Scalar squashedInsts;
        /** correct / (eligibleLoads + eligibleNonLoads). */
        statistics::Formula coverage;
        /** correct / (correct + wrong). */
        statistics::Formula accuracy;
        /** Memory-system level (stlf/l1d/l2/mem/unknown) that served
         *  each verified predicted load, by outcome; flush cost of
         *  wrong predicted loads by level. */
        statistics::Vector predictedLevelCorrect;
        statistics::Vector predictedLevelWrong;
        statistics::Vector wrongFlushedByLevel;
    } stats;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_BASE_HH__
```

- [ ] **Step 4: `base.cc`** (complete file):

```cpp
#include "cpu/o3/vp/base.hh"

#include "cpu/o3/dyn_inst.hh"
#include "cpu/o3/vp/vp_key.hh"
#include "params/BaseValuePredictor.hh"

namespace gem5
{
namespace o3
{

BaseValuePredictor::BaseValuePredictor(const BaseValuePredictorParams &p)
    : SimObject(p),
      _onlyLoads(p.onlyLoads),
      _scalarOnly(p.scalarOnly),
      stats(this)
{}

bool
BaseValuePredictor::eligible(const DynInstPtr &inst) const
{
    if (inst->numDestRegs() != 1) {
        return false;
    }
    if (inst->isSerializing() || inst->isSerializeBefore() ||
        inst->isSerializeAfter() || inst->isNonSpeculative() ||
        inst->isMemBarrier() || inst->isWriteBarrier() ||
        inst->isAtomic() || inst->isStoreConditional()) {
        return false;
    }
    PhysRegIdPtr dest = inst->renamedDestIdx(0);
    if (!dest || !dest->is(IntRegClass) || dest->isFixedMapping()) {
        return false;
    }
    return true;
}

bool
BaseValuePredictor::inScope(const DynInstPtr &inst) const
{
    if (_onlyLoads && !inst->isLoad()) {
        return false;
    }
    return eligible(inst);
}

std::optional<RegVal>
BaseValuePredictor::predict(const DynInstPtr &inst)
{
    if (!inScope(inst)) {
        return std::nullopt;
    }
    const Addr key = vpKey(inst->pcState().instAddr(),
                           inst->pcState().microPC());
    std::optional<RegVal> v = predictImpl(key);
    if (v) {
        stats.predictionsMade++;
        inst->setVpPredicted();
        inst->setVpPredVal(*v);
    }
    return v;
}

void
BaseValuePredictor::train(const DynInstPtr &inst, RegVal actualValue)
{
    if (!inScope(inst)) {
        return;
    }
    if (inst->isLoad()) {
        stats.eligibleLoads++;
    } else {
        stats.eligibleNonLoads++;
    }
    trainImpl(vpKey(inst->pcState().instAddr(), inst->pcState().microPC()),
              actualValue);
}

void
BaseValuePredictor::verifyResult(const DynInstPtr &inst, bool correct,
                                 uint64_t flushed)
{
    const unsigned lvl =
        inst->memSrcLevel() > 4 ? 4 : inst->memSrcLevel();
    if (correct) {
        stats.predictionsCorrect++;
        if (inst->isLoad()) {
            stats.predictedLevelCorrect[lvl]++;
        }
    } else {
        stats.predictionsWrong++;
        stats.squashedInsts += flushed;
        if (inst->isLoad()) {
            stats.predictedLevelWrong[lvl]++;
            stats.wrongFlushedByLevel[lvl] += flushed;
        }
    }
}

void
BaseValuePredictor::notifySquashed(const DynInstPtr &)
{
    // The instruction handle is part of the API for derived predictors
    // (and future per-reason buckets); the base count needs only the
    // event. Unnamed to satisfy -Werror=unused-parameter.
    stats.predictionsSquashed++;
}

BaseValuePredictor::VpStats::VpStats(statistics::Group *parent)
    : statistics::Group(parent),
      ADD_STAT(eligibleLoads, statistics::units::Count::get(),
               "In-scope loads reaching the train site (includes "
               "MRN-claimed loads; excludes already-squashed ones)"),
      ADD_STAT(eligibleNonLoads, statistics::units::Count::get(),
               "In-scope non-loads reaching the train site (structurally "
               "zero in loads-only mode)"),
      ADD_STAT(predictionsMade, statistics::units::Count::get(),
               "Value predictions consumed into a renamed dest at rename"),
      ADD_STAT(predictionsCorrect, statistics::units::Count::get(),
               "Consumed predictions that verified correct at writeback"),
      ADD_STAT(predictionsWrong, statistics::units::Count::get(),
               "Consumed predictions that verified wrong and forced an "
               "inclusive squash"),
      ADD_STAT(predictionsSquashed, statistics::units::Count::get(),
               "Consumed predictions discarded before they could verify"),
      ADD_STAT(squashedInsts, statistics::units::Count::get(),
               "Instructions discarded by VP misprediction squashes "
               "(inclusive of the mispredicted instruction)"),
      ADD_STAT(coverage, statistics::units::Ratio::get(),
               "Verified-correct predictions over the in-scope "
               "population at the train site"),
      ADD_STAT(accuracy, statistics::units::Ratio::get(),
               "Verified-correct predictions over verified predictions"),
      ADD_STAT(predictedLevelCorrect, statistics::units::Count::get(),
               "Memory-system level that served each correct predicted "
               "load (stlf = store-to-load forward; l2/mem from the "
               "request's own miss depth)"),
      ADD_STAT(predictedLevelWrong, statistics::units::Count::get(),
               "Memory-system level that served each wrong predicted "
               "load (same attribution as predictedLevelCorrect)"),
      ADD_STAT(wrongFlushedByLevel, statistics::units::Count::get(),
               "Instructions flushed by wrong predicted loads, "
               "accumulated by serving level (divide by "
               "predictedLevelWrong for avg flush per wrong)")
{
    static const char *level_names[] = {"stlf", "l1d", "l2", "mem",
                                        "unknown"};
    predictedLevelCorrect.init(5).flags(statistics::total);
    predictedLevelWrong.init(5).flags(statistics::total);
    wrongFlushedByLevel.init(5).flags(statistics::total);
    for (int i = 0; i < 5; i++) {
        predictedLevelCorrect.subname(i, level_names[i]);
        predictedLevelWrong.subname(i, level_names[i]);
        wrongFlushedByLevel.subname(i, level_names[i]);
    }

    coverage.flags(statistics::total);
    coverage = predictionsCorrect / (eligibleLoads + eligibleNonLoads);
    accuracy.flags(statistics::total);
    accuracy = predictionsCorrect /
               (predictionsCorrect + predictionsWrong);
}

} // namespace o3
} // namespace gem5
```

- [ ] **Step 5: `last_value.hh`** (complete file):

```cpp
#ifndef __CPU_O3_VP_LAST_VALUE_HH__
#define __CPU_O3_VP_LAST_VALUE_HH__

#include <optional>

#include "base/statistics.hh"
#include "base/types.hh"
#include "cpu/o3/vp/base.hh"
#include "cpu/o3/vp/lvp_table.hh"

namespace gem5
{

struct LastValueVPParams;

namespace o3
{

/**
 * Garfield VP: the Last-Value Predictor (Lipasti & Shen, MICRO-29 1996)
 * -- deliberately minimal, existing to prove the VP framework
 * end-to-end. A thin SimObject wrapper over the params-free LvpTable
 * (lvp_table.hh), plus table-level stats.
 */
class LastValueVP : public BaseValuePredictor
{
  public:
    LastValueVP(const LastValueVPParams &p);

  protected:
    std::optional<RegVal> predictImpl(Addr key) override;
    void trainImpl(Addr key, RegVal actualValue) override;

  private:
    LvpTable table;

    struct LvpStats : public statistics::Group
    {
        explicit LvpStats(statistics::Group *parent);
        statistics::Scalar lookups;
        statistics::Scalar hits;
        /** Hits below the confidence threshold (no prediction). */
        statistics::Scalar belowThreshold;
        statistics::Scalar allocs;
        statistics::Scalar confResets;
        statistics::Scalar confDecrements;
    } lvpStats;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_LAST_VALUE_HH__
```

- [ ] **Step 6: `last_value.cc`** (complete file):

```cpp
#include "cpu/o3/vp/last_value.hh"

#include "params/LastValueVP.hh"

namespace gem5
{
namespace o3
{

LastValueVP::LastValueVP(const LastValueVPParams &p)
    : BaseValuePredictor(p),
      table(LvpConfig{p.entries, p.assoc, p.confBits, p.confThreshold,
                      p.confDecrementOnWrong}),
      lvpStats(this)
{}

std::optional<RegVal>
LastValueVP::predictImpl(Addr key)
{
    lvpStats.lookups++;
    LvpLookup r = table.lookup(key);
    if (!r.hit) {
        return std::nullopt;
    }
    lvpStats.hits++;
    if (!r.confident) {
        lvpStats.belowThreshold++;
        return std::nullopt;
    }
    return r.value;
}

void
LastValueVP::trainImpl(Addr key, RegVal actualValue)
{
    switch (table.train(key, actualValue)) {
      case LvpTrainOutcome::Allocated:
        lvpStats.allocs++;
        break;
      case LvpTrainOutcome::MismatchReset:
        lvpStats.confResets++;
        break;
      case LvpTrainOutcome::MismatchDecrement:
        lvpStats.confDecrements++;
        break;
      case LvpTrainOutcome::Match:
        break;
    }
}

LastValueVP::LvpStats::LvpStats(statistics::Group *parent)
    : statistics::Group(parent),
      ADD_STAT(lookups, statistics::units::Count::get(),
               "VPT lookups from in-scope predict() calls"),
      ADD_STAT(hits, statistics::units::Count::get(), "VPT tag hits"),
      ADD_STAT(belowThreshold, statistics::units::Count::get(),
               "VPT hits below the confidence threshold (no prediction)"),
      ADD_STAT(allocs, statistics::units::Count::get(),
               "VPT allocations (train misses)"),
      ADD_STAT(confResets, statistics::units::Count::get(),
               "Confidence resets on a value mismatch"),
      ADD_STAT(confDecrements, statistics::units::Count::get(),
               "Confidence decrements on a value mismatch (decrement "
               "mode)")
{}

} // namespace o3
} // namespace gem5
```

- [ ] **Step 7: Registration.** Replace `src/cpu/o3/vp/SConscript` with:

```python
Import('*')

if env['CONF']['BUILD_ISA']:
    SimObject('ValuePredictor.py',
        sim_objects=['BaseValuePredictor', 'LastValueVP'])

    Source('base.cc')
    Source('last_value.cc')
    Source('lvp_table.cc')

    GTest('lvp_table.test', 'lvp_table.test.cc', 'lvp_table.cc')

    DebugFlag('ValuePred')
```

  In `src/cpu/o3/BaseO3CPU.py`, insert directly after the
  `memRenamePredictor` param (after its closing `)`, ~line 215):

```python
    valuePred = Param.BaseValuePredictor(
        NULL, "Value predictor; NULL disables VP"
    )
```

- [ ] **Step 8: Build + inertness check**

Run: `scons build/ALL/gem5.opt -j$(nproc); echo rc=$?` → `rc=0`.
Run: `./build/ALL/cpu/o3/vp/lvp_table.test.opt` → all PASS (rebuild it
first if scons did not).
Run: `strings -a build/ALL/gem5.opt | grep -c 'LastValueVP'` → ≥ 1.
Python sanity:
`./build/ALL/gem5.opt --version` runs; and a trivial import check —
`echo "from m5.objects import LastValueVP, BaseValuePredictor; print('ok')" > /tmp/claude-1000/-home-rbera-work-garfield-gem5/d8c06440-e8c6-4f06-9473-ab1842b0ee8e/scratchpad/vp_import.py && ./build/ALL/gem5.opt /tmp/claude-1000/-home-rbera-work-garfield-gem5/d8c06440-e8c6-4f06-9473-ab1842b0ee8e/scratchpad/vp_import.py` → prints `ok`.
No pipeline stage consumes `params.valuePred` yet — gem5 behavior is
byte-identical (param defaults NULL).

- [ ] **Step 9: Hand back for review + controller commit**
  Suggested header: `cpu-o3: Add value-predictor SimObject framework + LVP`

---

### Task 4: Pipeline Integration + CLI (predict, verify, squash, train, knobs)

**Files:**
- Modify: `src/cpu/o3/rename.hh` (fwd decl ~66; member ~361),
  `src/cpu/o3/rename.cc` (includes ~42-54; ctor ~86; consume site — insert
  after the `vf_value_pending` block closing ~line 915, before the
  `storesInProgress` accounting)
- Modify: `src/cpu/o3/iew.hh` (fwd decl ~68; accessor ~252; member ~377),
  `src/cpu/o3/iew.cc` (includes; ctor ~81; `writebackInsts` ~1419)
- Modify: `src/cpu/o3/lsq_unit.cc` (includes; verify/train site after the
  MRN `isMrned` block closing ~line 1319, inside the `fault == NoFault`
  region)
- Modify: `src/cpu/o3/rob.cc` (include; `doSquash` attribution after the
  MRN block ~line 377)
- Modify: `src/cpu/o3/cpu.hh` (accessor next to `getMemRenamePred`
  ~line 430), `src/cpu/o3/cpu.cc` (include; `squashInstIt` after the MRN
  block ~line 1313)
- Modify: `configs/garfield/arm/sim_opts.py` (import ~48; args after
  `--mrn-*` block ~186; `make_vp` + `apply_core_knobs` ~208-232; banner
  ~235-263)

**Interfaces:**
- Consumes: Task 2 (`squashDueToValueMispredict`), Task 3 (the full
  `BaseValuePredictor` API, DynInst Vp state, `params.valuePred`).
- Produces: `IEW::getValuePred()` (the LSQ's access path);
  `CPU::getValuePred()` (the ROB's access path); CLI `--use-vp lvp`,
  `--vp-all-insts`, `--vp-entries`, `--vp-assoc`, `--vp-conf-bits`,
  `--vp-conf-threshold`, `--vp-conf-decrement`.

- [ ] **Step 1: Pointer plumbing.**
  `rename.hh`: add `class BaseValuePredictor;` next to the
  `class MemRenamePredictor;` fwd decl (~line 66, inside `namespace o3`);
  add member next to `memRenamePred` (~line 361):

```cpp
    /** Garfield VP: value predictor (null = VP disabled). */
    BaseValuePredictor *valuePred = nullptr;
```

  `rename.cc`: add `#include <optional>` (with the std includes),
  `#include "cpu/o3/vp/base.hh"` and `#include "debug/ValuePred.hh"`
  (alphabetical among the existing includes, ~42-54); ctor init after
  `memRenamePred(params.memRenamePredictor),` (~line 86):

```cpp
      valuePred(params.valuePred),
```

  `iew.hh`: fwd decl `class BaseValuePredictor;` next to
  `class MemRenamePredictor;` (~line 68); accessor next to
  `getMemRenamePred()` (~line 252):

```cpp
    /** Garfield VP: the value predictor (null = VP disabled). The LSQ
     *  reaches it through its iewStage back-pointer. */
    BaseValuePredictor *
    getValuePred() const
    {
        return valuePred;
    }
```

  member next to `memRenamePred` (~line 377):

```cpp
    /** Garfield VP: value predictor (null = VP disabled). */
    BaseValuePredictor *valuePred = nullptr;
```

  `iew.cc`: includes `#include "cpu/o3/vp/base.hh"`,
  `#include "debug/ValuePred.hh"`; ctor init after
  `memRenamePred(params.memRenamePredictor),` (~line 81):
  `valuePred(params.valuePred),`.

  `cpu.hh`: next to `getMemRenamePred()` (~line 430):

```cpp
    /** Garfield VP: the value predictor, or NULL when VP is disabled.
     *  It lives in IEW; this exposes it to the ROB, which does the
     *  squashed-prediction accounting. */
    BaseValuePredictor *
    getValuePred() const
    {
        return iew.getValuePred();
    }
```

  (`cpu.hh` sees `o3::BaseValuePredictor` via a fwd decl next to the
  existing `class MemRenamePredictor;` fwd decl in that header — add it
  where iew.hh's types are forward-declared; the call compiles because
  iew.hh is included by cpu.hh already. If cpu.hh has no MRN fwd decl of
  its own, none is needed for VP either.)

- [ ] **Step 2: Rename consume site.** In `rename.cc`, directly after the
  `vf_value_pending` consume block closes (~line 915) and before the
  `if (inst->isAtomic() || inst->isStore())` bookkeeping:

```cpp
        // Garfield VP: value-predict behind the MRN -> VP -> execute
        // priority ladder -- only instructions MRN left unclaimed are
        // consulted. predict() does all eligibility/scope filtering and,
        // on a hit, stamps the prediction on the instruction; consuming
        // it is the same physreg-write + scoreboard-ready mechanism as
        // MRN's value forward. The instruction still executes normally
        // and verifies at writeback (LSQ for loads, IEW for non-loads).
        if (valuePred && !inst->isMrned()) {
            if (std::optional<RegVal> pv = valuePred->predict(inst)) {
                PhysRegIdPtr dest = inst->renamedDestIdx(0);
                cpu->setReg(dest, *pv, inst->threadNumber);
                scoreboard->setReg(dest);
                DPRINTF(ValuePred,
                        "[tid:%i] [sn:%llu] VP forward PC %s value=%#x "
                        "to renamed dest\n",
                        inst->threadNumber, inst->seqNum, inst->pcState(),
                        *pv);
            }
        }
```

  (No fixed-mapping/int guard here: `inScope` already enforced both on the
  renamed dest — that is the predict() contract.)

- [ ] **Step 3: LSQ load verify + train.** In `lsq_unit.cc`, add includes
  `#include "cpu/o3/vp/base.hh"` and `#include "debug/ValuePred.hh"`.
  Directly after the MRN `if (inst->isMrned() && ...)` verify block closes
  (~line 1319), still inside the `fault == NoFault` / `!isExecuted` region:

```cpp
            // Garfield VP: verify a value-predicted load, then train the
            // predictor on every in-scope load -- predicted or not, and
            // including MRN-claimed loads (the table stays warm
            // regardless of who consumed the load). inScope() guards the
            // integer-dest read below. The squash trigger goes last,
            // after all accounting, matching the MRN site above.
            if (BaseValuePredictor *vp = iewStage->getValuePred();
                vp && inst->isLoad() && vp->inScope(inst)) {
                const RegVal actual = cpu->getReg(
                    inst->renamedDestIdx(0), inst->threadNumber);
                bool vp_wrong = false;
                if (inst->vpPredicted() && !inst->vpResolved()) {
                    inst->setVpResolved();
                    if (actual != inst->vpPredVal()) {
                        vp_wrong = true;
                        // Flush cost: the load and every younger
                        // in-flight inst (inclusive squash).
                        InstSeqNum flushed =
                            cpu->getCurrentInstSeq() - inst->seqNum;
                        vp->verifyResult(inst, false, flushed);
                        DPRINTF(ValuePred,
                                "[tid:%i] [sn:%llu] VP mispredict PC %s "
                                "pred=%#x real=%#x -- squashing %llu "
                                "insts\n",
                                inst->threadNumber, inst->seqNum,
                                inst->pcState(), inst->vpPredVal(),
                                actual, flushed);
                    } else {
                        vp->verifyResult(inst, true, 0);
                    }
                }
                vp->train(inst, actual);
                if (vp_wrong) {
                    iewStage->squashDueToValueMispredict(
                        inst, inst->threadNumber);
                }
            }
```

- [ ] **Step 4: IEW non-load verify + train.** In `IEW::writebackInsts()`
  (~iew.cc:1419), at the top of the
  `!isSquashed() && isExecuted() && NoFault` block, before
  `int dependents = instQueue.wakeDependents(inst);`:

```cpp
            // Garfield VP (all-instructions scope): verify a
            // value-predicted non-load against its FU result, then
            // train on every in-scope non-load. Loads verify and train
            // at LSQ writeback instead. The onlyLoads() short-circuit
            // keeps the default loads-only mode zero-cost here;
            // inScope() guards the integer-dest read.
            if (valuePred && !valuePred->onlyLoads() && !inst->isLoad() &&
                valuePred->inScope(inst)) {
                const RegVal actual =
                    cpu->getReg(inst->renamedDestIdx(0), tid);
                bool vp_wrong = false;
                if (inst->vpPredicted() && !inst->vpResolved()) {
                    inst->setVpResolved();
                    if (actual != inst->vpPredVal()) {
                        vp_wrong = true;
                        InstSeqNum flushed =
                            cpu->getCurrentInstSeq() - inst->seqNum;
                        valuePred->verifyResult(inst, false, flushed);
                        DPRINTF(ValuePred,
                                "[tid:%i] [sn:%llu] VP mispredict PC %s "
                                "pred=%#x real=%#x -- squashing %llu "
                                "insts\n",
                                tid, inst->seqNum, inst->pcState(),
                                inst->vpPredVal(), actual, flushed);
                    } else {
                        valuePred->verifyResult(inst, true, 0);
                    }
                }
                valuePred->train(inst, actual);
                if (vp_wrong) {
                    squashDueToValueMispredict(inst, tid);
                }
            }
```

- [ ] **Step 5: Squashed-before-verify accounting (both walks).**
  `rob.cc` — add `#include "cpu/o3/vp/base.hh"`; in `doSquash`, directly
  after the MRN attribution block (after its closing brace, ~line 377):

```cpp
        // Garfield VP: a value-predicted instruction discarded before
        // it could verify. Same exactly-once discipline as MRN above:
        // the VpResolved bit, not isSquashed(), makes this count once
        // across overlapping squash walks.
        if (squashing->vpPredicted() && !squashing->vpResolved()) {
            squashing->setVpResolved();
            if (BaseValuePredictor *vp = cpu->getValuePred()) {
                vp->notifySquashed(squashing);
            }
        }
```

  `cpu.cc` — add `#include "cpu/o3/vp/base.hh"`; in `squashInstIt`,
  directly after the MRN block (after its closing brace, ~line 1313,
  before `(*instIt)->setSquashed();`):

```cpp
        // Garfield VP: same coverage as the MRN block above -- a
        // value-predicted instruction dropped without ever reaching the
        // ROB walk.
        if (inst->vpPredicted() && !inst->vpResolved()) {
            inst->setVpResolved();
            if (BaseValuePredictor *vp = getValuePred()) {
                vp->notifySquashed(inst);
            }
        }
```

- [ ] **Step 6: CLI.** In `configs/garfield/arm/sim_opts.py`:
  - Import (~line 48): `from m5.objects import LastValueVP,
    MemRenamePredictor` (extend the existing import line).
  - After the last `--mrn-*` argument (~line 186), still in the `garfield`
    group:

```python
    garfield.add_argument(
        "--use-vp",
        type=str,
        choices=["lvp"],
        default=None,
        metavar="TYPE",
        help="Garfield: attach a value predictor of the given type "
        "(lvp = last-value predictor). Absent = VP disabled (NULL).",
    )
    garfield.add_argument(
        "--vp-all-insts",
        action="store_true",
        help="VP scope: predict all eligible instructions, not only "
        "loads.",
    )
    garfield.add_argument(
        "--vp-entries",
        type=int,
        default=4096,
        help="VP table entries.",
    )
    garfield.add_argument(
        "--vp-assoc",
        type=int,
        default=4,
        help="VP table associativity.",
    )
    garfield.add_argument(
        "--vp-conf-bits",
        type=int,
        default=4,
        help="VP confidence-counter width in bits.",
    )
    garfield.add_argument(
        "--vp-conf-threshold",
        type=int,
        default=15,
        help="VP minimum confidence required to predict.",
    )
    garfield.add_argument(
        "--vp-conf-decrement",
        action="store_true",
        help="Decrement (rather than reset) VP confidence on a value "
        "mismatch.",
    )
```

  - Factory after `make_mrn` (~line 221):

```python
def make_vp(args):
    """The value predictor selected by --use-vp, or None."""
    if args.use_vp is None:
        return None
    assert args.use_vp == "lvp"
    return LastValueVP(
        onlyLoads=not args.vp_all_insts,
        entries=args.vp_entries,
        assoc=args.vp_assoc,
        confBits=args.vp_conf_bits,
        confThreshold=args.vp_conf_threshold,
        confDecrementOnWrong=args.vp_conf_decrement,
    )
```

  - In `apply_core_knobs` (~line 232), after the MRN attach:

```python
    vp = make_vp(args)
    if vp is not None:
        cpu.valuePred = vp
```

  - Banner helper after `_mrn_banner` (~line 249) and a `vp` line in
    `describe()` next to the `mrn` line:

```python
def _vp_banner(args):
    """VP banner fragment naming the predictor and scope."""
    if not args.use_vp:
        return "off"
    scope = "all-insts" if args.vp_all_insts else "loads-only"
    return f"{args.use_vp} ({scope}) confThreshold={args.vp_conf_threshold}"
```

- [ ] **Step 7: Build, unit tests, smoke matrix**

Run: `scons build/ALL/gem5.opt -j$(nproc); echo rc=$?` → `rc=0`.
Run: `./build/ALL/cpu/o3/vp/lvp_table.test.opt` → PASS.
Run: `strings -a build/ALL/gem5.opt | grep -c 'valuePred'` → ≥ 1.
Smoke matrix on one existing SE microbenchmark binary (e.g.
`/home/rbera/work/garfield/gem5-infra/workloads/microbenchmarks/bin/stream`
— check `se_run.py --help` / the runs/ directory for the exact invocation
precedent; write throwaway scripts under `runs/vp_smoke/`):
1. **Baseline inertness:** run WITHOUT `--use-vp`; stats must contain no
   `valuePred` group and complete normally.
2. **VP attached:** run with `--use-vp lvp`; expect the
   `system.cpu.valuePred.*` (path per config naming) group present;
   `eligibleLoads > 0`; `lookups > 0`; identity check
   `predictionsMade == predictionsCorrect + predictionsWrong +
   predictionsSquashed` within a few units (in-flight at dump).
3. **All-insts scope:** add `--vp-all-insts`; expect `eligibleNonLoads > 0`
   and the run to complete.
4. **MRN + VP ladder co-existence (build sanity only):** run with both
   `--use-mrn --mrn-alias --mrn-conf-threshold 14` and `--use-vp lvp`;
   must complete without assertion (full composition evaluation is out of
   scope; the ladder guard `!inst->isMrned()` is what is being smoked).

- [ ] **Step 8: Hand back for review + controller commit**
  Suggested header: `cpu-o3,configs: Wire value prediction into the pipeline`

---

### Task 5: Stage-III Microbenchmarks (gem5-infra repo)

**Files (repo `/home/rbera/work/garfield/gem5-infra`):**
- Create: `workloads/microbenchmarks/src/vpchase/vpchase.c` (+ whatever
  per-bench build file the existing `mrnrec`/`mrncomm` layout uses — copy
  that structure exactly; inspect `src/mrnrec/` first)
- Create: `workloads/microbenchmarks/src/vpalu/vpalu.c` (same layout)
- Output binaries land in `workloads/microbenchmarks/bin/` via the
  existing Makefile flow (aarch64 cross-gcc from conda-forge is already
  installed on this host).

**Interfaces:**
- Consumes: the Task 4 gem5 binary + CLI.
- Produces: `bin/vpchase`, `bin/vpalu` static AArch64 SE binaries.

**Benchmark design (from the spec):**
- `vpchase` — loads-only mode target: a serial load chain whose loaded
  values are invariant. A self-loop pointer cell (`cell == &cell`) chased
  through an opaque register breaks all compiler folding; without VP each
  iteration serializes on L1D latency, with VP the chain pipelines.
- `vpalu` — all-instructions mode target: a serial integer-multiply chain
  whose operand (`mul == 1`, passed via argv so the compiler cannot fold)
  keeps every ALU PC's result invariant across iterations.

- [ ] **Step 1: `vpchase.c`** (complete file):

```c
/* vpchase: Garfield VP microbenchmark (loads-only scope).
 *
 * A pointer self-loop: cell holds its own address, and the loop chases
 * it. Every iteration's load has a serial address dependence on the
 * previous load, but the loaded VALUE is invariant -- the ideal
 * last-value prediction target. Without VP the loop serializes on L1D
 * hit latency; with VP the predicted value breaks the chain and the
 * loads pipeline.
 *
 * The empty asm makes p opaque each iteration so the compiler can
 * neither hoist the load nor collapse the loop.
 */
#include <stdio.h>
#include <stdlib.h>

int
main(int argc, char **argv)
{
    long iters = argc > 1 ? atol(argv[1]) : 20000000L;
    void *cell;
    void *p;

    cell = (void *)&cell; /* *(&cell) == &cell: a one-node cycle */
    p = (void *)&cell;

    for (long i = 0; i < iters; i++) {
        p = *(void **)p;
        __asm__ volatile("" : "+r"(p));
    }

    printf("vpchase done: %ld iters, p=%p\n", iters, p);
    return 0;
}
```

- [ ] **Step 2: `vpalu.c`** (complete file):

```c
/* vpalu: Garfield VP microbenchmark (all-instructions scope).
 *
 * A serial integer-multiply chain: x = x * m eight times per
 * iteration, with m == 1 read from argv so the compiler cannot fold
 * the chain and every multiply PC produces the same value in every
 * iteration -- the ideal last-value target for non-load VP. Without VP
 * the chain serializes on multiply latency; with --vp-all-insts the
 * predicted results break it.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int
main(int argc, char **argv)
{
    long iters = argc > 1 ? atol(argv[1]) : 10000000L;
    uint64_t m = argc > 2 ? strtoull(argv[2], 0, 10) : 1;
    uint64_t x = 12345;

    for (long i = 0; i < iters; i++) {
        x = x * m;
        x = x * m;
        x = x * m;
        x = x * m;
        x = x * m;
        x = x * m;
        x = x * m;
        x = x * m;
        __asm__ volatile("" : "+r"(x));
    }

    printf("vpalu done: %ld iters, x=%llu\n", iters,
           (unsigned long long)x);
    return 0;
}
```

- [ ] **Step 3: Build both** following the existing microbenchmark
  Makefile flow (inspect `workloads/microbenchmarks/Makefile` + one
  existing `src/<bench>/` first; match it exactly — compiler flags should
  include `-O1 -static` unless the repo Makefile dictates otherwise; -O1
  keeps the loop bodies intact alongside the asm barriers).
  Verify: `file bin/vpchase` → `aarch64 ... statically linked`, and
  disassemble the loop (`aarch64-*-objdump -d bin/vpchase | grep -A6
  '<main>:'` region) to confirm one load per iteration survives in
  vpchase and eight multiplies in vpalu.

- [ ] **Step 4: Stage-III evaluation runs** (scripts under
  `runs/vp_stage3/` in the gem5 repo, gitignored):
  - `vpchase`: baseline (no VP) vs `--use-vp lvp`.
  - `vpalu`: baseline vs `--use-vp lvp --vp-all-insts`.
  - Success criteria (spec): high coverage (`coverage` stat), high
    accuracy (`accuracy` ≈ 1.0), and clear IPC speedup over baseline on
    the same binary. Also verify: `predictionsWrong` ≈ 0 on these
    invariant-value kernels; the made = correct + wrong + squashed
    identity; and in vpchase's VP run, `predictedLevelCorrect::l1d`
    dominating (self-loop cell stays L1-resident).
  - Record a small results table (bench × config → IPC, coverage,
    accuracy, speedup) in the task report for the eventual research log.

- [ ] **Step 5: Hand back for review + commits** (gem5-infra repo commit
  for the benchmarks — follow that repo's existing log style; runs/
  scripts stay untracked).

---

### Task 6: Stage-IV SPEC26 Deployment (190-Checkpoint Sweep)

**Files:** run scripts + analysis under `runs/vp_lvp_sweep/` (gitignored);
no tree changes expected.

**Interfaces:**
- Consumes: Task 4 binary + CLI; the existing checkpoint-restore sweep
  infrastructure (copy the driver pattern from `runs/mrn_lvgate_sweep/` —
  resumable driver, 20-way parallelism, retry round for resources-API
  startup races, persistent Monitor waiter with driver-death coverage).

- [ ] **Step 1: Baseline reference.** Locate existing no-MRN/no-VP
  baseline stats for the 190 checkpoints under `runs/` (the MRN campaign
  kept baseline refs). If absent or stale vs the current binary, run the
  190-checkpoint baseline first — the spec's comparison base is
  no-VP/no-MRN on the same binary.
- [ ] **Step 2: VP sweep.** 190 checkpoints × `--use-vp lvp` (loads-only
  default). ROI = first stats-dump block; IPC = line ending
  `start.core.ipc`.
- [ ] **Step 3: Analysis.** Per-checkpoint speedup vs baseline: geomean,
  spread, winners/losers table, coverage/accuracy distributions,
  flush-cost by level (`wrongFlushedByLevel`). Deliverable: summary.csv +
  a written summary in the task report. (Whether to also sweep
  `--vp-all-insts` is decided from the loads-only result + Stage-III
  vpalu evidence — flag it in the report rather than auto-running.)
- [ ] **Step 4: Hand back — results feed the research-log report (written
  with the research-report skill, user sign-off gate; NOT part of this
  plan's tasks).**

---

## Verification Summary (whole-branch, before merge consideration)

1. All GTests pass; full `build/ALL/gem5.opt` builds clean.
2. `grep -rn 'MrnSquashReason\|mrnSquashReason' src/` → 0.
3. Baseline (no `--use-vp`) runs are statistically identical to
   pre-branch behavior (VP paths all behind null checks).
4. Stats identities on every VP run: `predictionsMade == correct + wrong +
   squashed` (± in-flight); `sum(wrongFlushedByLevel) == squashedInsts`.
5. Final whole-branch review (most capable model) over
   `merge-base(rbdev, vp)..HEAD` before any merge to `rbdev`.
```
