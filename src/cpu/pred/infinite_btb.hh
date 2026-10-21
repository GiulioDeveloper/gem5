/*
 * LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
 */

/**
 * @file
 * An unbounded BTB for limit studies: it never evicts, keeps full-width
 * tags and separates address spaces by ASID, so the only misses left are
 * the first taken occurrence of each branch. See
 * docs/wiki/hardware/infinite-btb-model.md.
 */

#ifndef __CPU_PRED_INFINITE_BTB_HH__
#define __CPU_PRED_INFINITE_BTB_HH__

#include <cstdint>
#include <memory>
#include <unordered_map>
#include <vector>

#include "base/statistics.hh"
#include "base/types.hh"
#include "cpu/pred/btb.hh"
#include "params/InfiniteBTB.hh"

namespace gem5
{

class ThreadContext;

namespace branch_prediction
{

class InfiniteBTB : public BranchTargetBuffer
{
  public:
    InfiniteBTB(const InfiniteBTBParams &params);

    void init() override;
    void memInvalidate() override;
    void setThreadContext(ThreadID tid, ThreadContext *tc) override;

    bool valid(ThreadID tid, Addr instPC) override;
    const PCStateBase *lookup(ThreadID tid, Addr instPC,
                              BranchType type = BranchType::NoBranch) override;
    const StaticInstPtr getInst(ThreadID tid, Addr instPC) override;
    void update(ThreadID tid, Addr instPC, const PCStateBase &target_pc,
                BranchType type = BranchType::NoBranch,
                StaticInstPtr inst = nullptr) override;

  private:
    /** Address-space identifier of an entry: an ASID (at most 16 bits on
     *  Arm) or one of the two reserved values below. */
    using Space = uint64_t;

    /** Kernel code (PC bit 63 set), shared by every address space. */
    static constexpr Space KernelSpace = ~Space(0);

    /** User code when no ASID is available (no thread context, or an ISA
     *  without currentAsid()): plain VA tagging. */
    static constexpr Space NoAsidSpace = ~Space(1);

    struct Entry
    {
        std::unique_ptr<PCStateBase> target;
        StaticInstPtr inst;
    };

    /** One table per address space, keyed by the full branch PC. */
    using Table = std::unordered_map<Addr, Entry>;

    /** The address space a branch at instPC belongs to. */
    Space spaceOf(ThreadID tid, Addr instPC);

    /** The current user address space of tid, read via the MMU. */
    Space readUserSpace(ThreadID tid) const;

    Entry *findEntry(ThreadID tid, Addr instPC);

    std::unordered_map<Space, Table> tables;

    /** Entries over all tables. */
    uint64_t numEntries = 0;

    /** Drop ASID bit 0 (KPTI: the user/kernel halves of one ASID pair). */
    const bool ignoreAsidLsb;

    std::vector<ThreadContext *> threadContexts;

    /** Per-thread user space, recomputed at most once per tick: BAC probes
     *  the BTB many times per cycle and the ASID only changes at commit. */
    struct SpaceCache
    {
        Tick tick = MaxTick;
        Space space = NoAsidSpace;
    };
    std::vector<SpaceCache> spaceCache;

    struct InfiniteBTBStats : public statistics::Group
    {
        InfiniteBTBStats(statistics::Group *parent);

        statistics::Scalar newEntries;
        statistics::Scalar kernelEntries;
        statistics::Scalar userEntries;
        statistics::Scalar noAsidEntries;
        /** Current table sizes: not reset with the other stats. */
        statistics::Value entries;
        statistics::Value addressSpaces;
        statistics::Scalar staleTargets;
        statistics::Scalar staleEncodings;
    } infStats;
};

} // namespace branch_prediction
} // namespace gem5

#endif // __CPU_PRED_INFINITE_BTB_HH__
