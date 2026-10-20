/*
 * LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD
 */

#include "cpu/pred/infinite_btb.hh"

#include "arch/generic/mmu.hh"
#include "base/bitfield.hh"
#include "base/logging.hh"
#include "base/trace.hh"
#include "cpu/thread_context.hh"
#include "debug/BTB.hh"
#include "sim/cur_tick.hh"

namespace gem5::branch_prediction
{

InfiniteBTB::InfiniteBTB(const InfiniteBTBParams &p)
    : BranchTargetBuffer(p),
      ignoreAsidLsb(p.ignoreAsidLsb),
      threadContexts(p.numThreads, nullptr),
      spaceCache(p.numThreads),
      infStats(this)
{
    infStats.entries.functor([this] { return double(numEntries); });
    infStats.addressSpaces.functor(
        [this] { return double(tables.size()); });
}

void
InfiniteBTB::init()
{
    BranchTargetBuffer::init();
    for (ThreadID tid = 0; tid < (ThreadID)numThreads; ++tid) {
        if (!threadContexts[tid]) {
            warn("%s: no thread context for thread %d; user code is "
                 "tagged by VA only (no ASID).", name(), tid);
        }
    }
}

void
InfiniteBTB::setThreadContext(ThreadID tid, ThreadContext *tc)
{
    if (tid >= 0 && (size_t)tid < threadContexts.size()) {
        threadContexts[tid] = tc;
    }
}

void
InfiniteBTB::memInvalidate()
{
    tables.clear();
    numEntries = 0;
}

InfiniteBTB::Space
InfiniteBTB::readUserSpace(ThreadID tid) const
{
    ThreadContext *tc = threadContexts[tid];
    if (!tc) {
        return NoAsidSpace;
    }
    std::optional<uint64_t> asid = tc->getMMUPtr()->currentAsid(tc);
    if (!asid) {
        return NoAsidSpace;
    }
    return ignoreAsidLsb ? (*asid & ~uint64_t(1)) : *asid;
}

InfiniteBTB::Space
InfiniteBTB::spaceOf(ThreadID tid, Addr instPC)
{
    // Kernel/user split by address, not by the committed privilege
    // level, so it does not lag when BAC predicts across a mode switch.
    // Assumes the OS keeps the kernel in the upper half (Linux does).
    if (bits(instPC, 63)) {
        return KernelSpace;
    }
    SpaceCache &cache = spaceCache[tid];
    if (cache.tick != curTick()) {
        cache.tick = curTick();
        cache.space = readUserSpace(tid);
    }
    return cache.space;
}

InfiniteBTB::Entry *
InfiniteBTB::findEntry(ThreadID tid, Addr instPC)
{
    auto table = tables.find(spaceOf(tid, instPC));
    if (table == tables.end()) {
        return nullptr;
    }
    auto entry = table->second.find(instPC);
    return entry == table->second.end() ? nullptr : &entry->second;
}

bool
InfiniteBTB::valid(ThreadID tid, Addr instPC)
{
    return findEntry(tid, instPC) != nullptr;
}

const PCStateBase *
InfiniteBTB::lookup(ThreadID tid, Addr instPC, BranchType type)
{
    stats.lookups[type]++;

    Entry *entry = findEntry(tid, instPC);
    if (entry) {
        return entry->target.get();
    }

    stats.misses[type]++;
    return nullptr;
}

const StaticInstPtr
InfiniteBTB::getInst(ThreadID tid, Addr instPC)
{
    Entry *entry = findEntry(tid, instPC);
    return entry ? entry->inst : nullptr;
}

void
InfiniteBTB::update(ThreadID tid, Addr instPC, const PCStateBase &target,
                    BranchType type, StaticInstPtr inst)
{
    stats.updates[type]++;

    const Space space = spaceOf(tid, instPC);
    auto table = tables.try_emplace(space).first;
    auto [it, inserted] = table->second.try_emplace(instPC);
    Entry &entry = it->second;

    if (inserted) {
        ++numEntries;
        ++infStats.newEntries;
        if (space == KernelSpace) {
            ++infStats.kernelEntries;
        } else {
            ++infStats.userEntries;
            if (space == NoAsidSpace) {
                ++infStats.noAsidEntries;
            }
        }
    } else if (entry.inst && inst &&
               entry.inst->getEMI() != inst->getEMI()) {
        // Different instruction at the same (space, PC): code was
        // rewritten (JIT) or an ASID was reused.
        ++infStats.staleEncodings;
    } else if (inst && inst->isDirectCtrl() &&
               entry.target->instAddr() != target.instAddr()) {
        // A direct branch's target is fixed by its encoding, so a change
        // means the entry was stale.
        ++infStats.staleTargets;
    }

    DPRINTF(BTB, "InfiniteBTB: %s space %#x PC %#x -> %#x\n",
            inserted ? "insert" : "update", space, instPC,
            target.instAddr());

    set(entry.target, target);
    entry.inst = inst;
}

InfiniteBTB::InfiniteBTBStats::InfiniteBTBStats(statistics::Group *parent)
    : statistics::Group(parent),
      ADD_STAT(newEntries, statistics::units::Count::get(),
               "Branches inserted for the first time (compulsory misses)"),
      ADD_STAT(kernelEntries, statistics::units::Count::get(),
               "Entries in the shared kernel space"),
      ADD_STAT(userEntries, statistics::units::Count::get(),
               "Entries in user (per-ASID) spaces"),
      ADD_STAT(noAsidEntries, statistics::units::Count::get(),
               "User entries inserted without an ASID (VA-only tagging)"),
      ADD_STAT(entries, statistics::units::Count::get(),
               "Current number of entries (all address spaces)"),
      ADD_STAT(addressSpaces, statistics::units::Count::get(),
               "Current number of address spaces (ASIDs plus kernel)"),
      ADD_STAT(staleTargets, statistics::units::Count::get(),
               "Updates that changed a direct branch's stored target"),
      ADD_STAT(staleEncodings, statistics::units::Count::get(),
               "Updates where the instruction encoding at the PC changed")
{
}

} // namespace gem5::branch_prediction
