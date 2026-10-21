#ifndef __CPU_O3_MEM_RENAME_VALUEFILE_HH__
#define __CPU_O3_MEM_RENAME_VALUEFILE_HH__

#include <cstdint>
#include <vector>

#include "base/types.hh"
#include "cpu/inst_seq.hh"
#include "cpu/reg_class.hh"

namespace gem5
{
namespace o3
{

/**
 * Core tables for the value-file rendezvous memory-renaming model (Garfield
 * MRN).
 *
 * Based on Tyson & Austin's memory renaming (MICRO-30, 1997), with the
 * concrete table structure -- Store/Load Cache + Value File + Store Cache,
 * plus a saturating confidence counter -- from Reinman, Calder, Tullsen,
 * Tyson & Austin, "Classifying Load and Store Instructions for Memory
 * Renaming," ICS 1999, §2.3.
 *
 * A store deposits its producer information (data physreg, and the value
 * when already scoreboard-ready) into a named cell -- the value file (VF) --
 * at its own rename. A load looks the cell up by PC at its own rename. Since
 * rename is in-order, the deposit always precedes the read and belongs to
 * the program-order-youngest earlier static instance: this removes the
 * store-instance hunt the older correlator-based path needs.
 *
 * `MrnValueFileTables` is a params-free core class (in the style of
 * mem_rename_predictor.hh): it is built purely from `MrnVfConfig` so it can
 * be constructed and unit-tested without the SimObject/params machinery.
 * `PhysRegIdPtr` is stored and returned opaquely -- this class never
 * dereferences it; all liveness checks belong to the caller (rename).
 *
 *  - Value file (`valueFile`): the rendezvous cells, LRU across the whole
 *    table (not set-associative -- there is no address/PC to index it by).
 *  - Store/Load cache (`storeLoadCache`): PC-indexed, set-associative with
 *    modulo indexing and LRU within a set, shared by store and load PCs.
 *    Each entry points at a value-file cell by `{index, generation}` and
 *    (for load entries) carries the confidence counter.
 *  - Store cache (`storeCache`): address-indexed (at a configurable
 *    granularity) the same way, written only by stores and probed only by
 *    loads at address resolution.
 *
 * See docs/legacy-log/superpowers/specs/
 * 2026-07-25-mrn-valuefile-rendezvous-design.md
 * §3-§5 for the full structure and dataflow rationale.
 */

/**
 * Plain-int configuration for MrnValueFileTables. Mirrors the eventual
 * SimObject params but is free of any params/SimObject machinery, so the
 * core logic can be built and unit-tested in isolation.
 */
struct MrnVfConfig
{
    unsigned vfEntries = 1024;
    unsigned slcEntries = 4096;
    unsigned slcAssoc = 4;
    unsigned scEntries = 4096;
    unsigned scAssoc = 4;
    unsigned scGranularityBytes = 8; // power of two
    unsigned confBits = 4;
    unsigned confThreshold = 8;
    unsigned confInc = 1;
    unsigned confDec = 1;
    bool resetConfOnMispredict = true;
    /** Address-instability hysteresis for last-value consumption: a
     *  wrong forward whose address also changed earns a strike; at two
     *  strikes last-value consumption is disabled for that PC (sticky --
     *  no oscillation) until this many consecutive same-line executes
     *  are observed (shadow training continues throughout). 0 disables
     *  the gate entirely. */
    unsigned lvStabilityTarget = 0;
    /** Flush-weighted ledger: replace the gate's count-based earning
     *  test (>= 256 corrects per wrong) with a cost-benefit ledger --
     *  a binding is spared from disabling while
     *  lvCorrects * lvBenefitPerCorrect >= accumulated flush cost of
     *  its address-changed wrongs. Cheap (L1D-verified) wrongs drain
     *  the ledger slower than expensive (L2/memory-verified) ones. */
    bool lvFlushLedger = false;
    /** Benefit credited per correct verify, in flushed-instruction
     *  equivalents (the ledger's one free parameter, swept). */
    double lvBenefitPerCorrect = 1.0;
};

/** Reference to a value-file cell: index + the generation observed when the
 *  reference was created. A reference is dead once the cell's generation
 *  moves on (the cell was reallocated to another owner). */
struct MrnVfRef
{
    int idx = -1;
    uint64_t gen = 0;
    bool
    valid() const
    {
        return idx >= 0;
    }
    bool
    operator==(const MrnVfRef &o) const
    {
        return idx == o.idx && gen == o.gen;
    }
};

/** What a load sees in its bound cell at rename. */
struct MrnVfCellRead
{
    bool bound = false;     // SLC hit and the cell generation still matches
    bool confident = false; // conf >= confThreshold
    bool ptrValid = false;  // cell holds a producer physreg pointer
    PhysRegIdPtr ptr = nullptr;
    InstSeqNum ptrSeq = 0;
    bool valueValid = false; // cell holds a value
    RegVal value = 0;
    /** Last-value consumption suppressed by strike probation (shadow
     *  training still runs; alias/producer-value unaffected). */
    bool lvProbation = false;
    MrnVfRef ref; // valid iff bound
};

/** Outcome of the load-side store-cache probe at address resolution. */
struct MrnVfProbeResult
{
    enum Outcome
    {
        SameBinding,
        Rebound,
        SelfBound,
        AlreadySelfBound
    };
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

    /** Whether this self-bound cell's load resolved to a different line
     *  this instance than the previous one (address instability;
     *  gen-checked). Feeds the strike test in trainVerify. */
    bool cellAddrChanged(const MrnVfRef &ref) const;

    /** Confidence training at writeback (consumed or shadow). Trains only
     *  when the load's SLC entry is still bound to usedRef -- a rebind
     *  between rename and writeback discards the outcome. For a wrong
     *  consumed forward, flushed is the squash cost measured at the
     *  verify (clamped internally); it feeds the flush-weighted ledger
     *  and is otherwise ignored. */
    void trainVerify(Addr loadPC, const MrnVfRef &usedRef, bool correct,
                     bool addrChanged = false, uint64_t flushed = 0);

    /** Whether the most recent trainVerify disabled the binding. */
    bool
    lastStrikeDisabled() const
    {
        return lastDisable;
    }

    /** Whether the most recent trainVerify held a would-be-disabling
     *  strike because the binding passed the earning/ledger test. */
    bool
    lastStrikeSpared() const
    {
        return lastSpare;
    }

  private:
    struct VfCell
    {
        /** Address-stability tracking: the line this cell's load resolved
         *  to last instance, and whether the current instance's line
         *  differs from it. Read at the verify site (cellAddrChanged) as
         *  the strike test's address-instability input, and compared at
         *  address resolution for the hysteresis re-enable streak. */
        Addr lastLine = 0;
        bool lineKnown = false;
        bool addrChanged = false;
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
        /** Address-instability strikes (wrong forward + changed line). */
        uint8_t strikes = 0;
        /** Correct verifies since the last strike decay (slow decay). */
        uint8_t strikeDecayCtr = 0;
        /** Lifetime last-value verify outcomes for the earning test:
         *  a binding is only disabled if it earns fewer than
         *  lvEarningRatio corrects per wrong (saturating). */
        uint32_t lvCorrects = 0;
        uint16_t lvWrongs = 0;
        /** Accumulated (clamped, saturating) flush cost of this
         *  binding's address-changed wrongs -- the debit side of the
         *  flush-weighted ledger. */
        uint32_t lvFlushCost = 0;
        /** Consecutive same-line executes observed while disabled;
         *  reaching the stability target re-enables last-value use. */
        uint8_t stableStreak = 0;
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

    /** Find the store/load-cache entry for pc, or nullptr on a miss. */
    SlcEntry *slcFind(Addr pc);
    /** Allocate (LRU-evict within the set) a store/load-cache entry. */
    SlcEntry *slcAllocate(Addr pc);
    /** Find the store-cache entry for lineAddr, or nullptr on a miss. */
    ScEntry *scFind(Addr lineAddr);
    /** Allocate (LRU-evict within the set) a store-cache entry. */
    ScEntry *scAllocate(Addr lineAddr);
    /** Allocate a value-file cell: global min-lru victim across the whole
     *  table (the VF is not set-associative). Bumps the victim's gen and
     *  clears its content. Returns the victim's index. */
    int vfAllocate();
    /** Store-cache line address for an effective address. */
    Addr
    scLine(Addr ea) const
    {
        return ea >> scGranularityLog2;
    }
    /** Saturating maximum confidence value for confBits. */
    unsigned
    confMax() const
    {
        const unsigned capped = confBits > 31 ? 31 : confBits;
        return (1u << capped) - 1;
    }

    const unsigned slcSets, slcAssoc, scSets, scAssoc;
    const unsigned scGranularityLog2;
    const unsigned confBits, confThreshold, confInc, confDec;
    const bool resetConfOnMispredict;
    std::vector<VfCell> valueFile;
    std::vector<SlcEntry> storeLoadCache;
    std::vector<ScEntry> storeCache;
    /** Monotonic counter used as the LRU timestamp for all structures. */
    uint64_t lruTick = 0;
    const unsigned lvStabilityTarget;
    const bool lvFlushLedger;
    const double lvBenefitPerCorrect;
    /** Whether the most recent trainVerify disabled a binding. */
    bool lastDisable = false;
    /** Whether the most recent trainVerify spared a binding via the
     *  earning/ledger test. */
    bool lastSpare = false;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_MEM_RENAME_VALUEFILE_HH__
