/*
 * Copyright (c) 2022-2023 The University of Edinburgh
 * All rights reserved
 *
 * The license below extends only to copyright in the software and shall
 * not be construed as granting a license to any other intellectual
 * property including but not limited to intellectual property relating
 * to a hardware implementation of the functionality of the software
 * licensed hereunder.  You may use the software subject to the license
 * terms below provided that you ensure that this notice is replicated
 * unmodified and in its entirety in all distributions of the software,
 * modified or unmodified, in source code or in binary form.
 *
 * Copyright (c) 2004-2005 The Regents of The University of Michigan
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include "cpu/pred/simple_btb.hh"

#include <algorithm>

#include "base/intmath.hh"
#include "base/trace.hh"
#include "debug/BTB.hh"

namespace gem5::branch_prediction
{

SimpleBTB::SimpleBTB(const SimpleBTBParams &p)
    : BranchTargetBuffer(p),
      btb("simpleBTB", p.numEntries, p.associativity, p.btbReplPolicy,
          p.btbIndexingPolicy, BTBEntry(genTagExtractor(p.btbIndexingPolicy))),
      setAssocIndexing(
          dynamic_cast<const BTBSetAssociative *>(p.btbIndexingPolicy))
{
    DPRINTF(BTB, "BTB: Creating BTB object.\n");

    if (setAssocIndexing &&
        setAssocIndexing->getTagMask() < (uint64_t(1) << 47)) {
        mirrorAssoc = setAssocIndexing->getAssoc();
        tagMirror.assign(p.numEntries, 0);
    }

    if (!isPowerOf2(p.numEntries / p.associativity)) {
        fatal("BTB sets is not a power of 2!");
    }
}

void
SimpleBTB::memInvalidate()
{
    btb.clear();
    std::fill(tagMirror.begin(), tagMirror.end(), 0);
}

BTBEntry *
SimpleBTB::probe(Addr instPC, ThreadID tid) const
{
    if (!setAssocIndexing) {
        return btb.findEntry({instPC, tid});
    }

    if (!tagMirror.empty()) {
        // A slot equals the wanted key exactly when its entry is valid and
        // holds this tag and thread, i.e. when matchTag() would be true.
        const uint32_t set = setAssocIndexing->setIndex({instPC, tid});
        const uint64_t want =
            mirrorKey(setAssocIndexing->extractTag(instPC), tid);
        const uint64_t *slot = &tagMirror[set * mirrorAssoc];
        for (unsigned way = 0; way < mirrorAssoc; ++way) {
            if (slot[way] == want) {
                return static_cast<BTBEntry *>(
                    setAssocIndexing->getEntry(set, way));
            }
        }
        return nullptr;
    }

    const Addr tag = setAssocIndexing->extractTag(instPC);
    for (auto *candidate : setAssocIndexing->possibleEntries({instPC, tid})) {
        auto *entry = static_cast<BTBEntry *>(candidate);
        if (entry->matchTag(tag, tid)) {
            return entry;
        }
    }
    return nullptr;
}

BTBEntry *
SimpleBTB::findEntry(Addr instPC, ThreadID tid)
{
    return probe(instPC, tid);
}

bool
SimpleBTB::valid(ThreadID tid, Addr instPC)
{
    return probe(instPC, tid) != nullptr;
}

// @todo Create some sort of return struct that has both whether or not the
// address is valid, and also the address.  For now will just use addr = 0 to
// represent invalid entry.
const PCStateBase *
SimpleBTB::lookup(ThreadID tid, Addr instPC, BranchType type)
{
    stats.lookups[type]++;

    BTBEntry *entry = btb.accessEntry({instPC, tid});

    if (entry) {
        return entry->target.get();
    }

    stats.misses[type]++;
    return nullptr;
}

bool
SimpleBTB::findFirstBranch(ThreadID tid, Addr start, Addr width, Addr step,
                           Addr &addr, StaticInstPtr &inst)
{
    // Same addresses and result as the base class's valid()/getInst()
    // loop, with one probe per address and no virtual call per step.
    for (addr = start;; addr += step) {
        if (BTBEntry *entry = probe(addr, tid)) {
            inst = entry->inst;
            return true;
        }
        if (addr - start >= width) {
            return false;
        }
    }
}

const StaticInstPtr
SimpleBTB::getInst(ThreadID tid, Addr instPC)
{
    BTBEntry *entry = probe(instPC, tid);

    if (entry) {
        return entry->inst;
    }

    return nullptr;
}

void
SimpleBTB::update(ThreadID tid, Addr instPC,
                  const PCStateBase &target,
                  BranchType type, StaticInstPtr inst)
{
    stats.updates[type]++;

    BTBEntry *victim = btb.findVictim({instPC, tid});

    btb.insertEntry({instPC, tid}, victim);
    victim->update(target, inst);

    if (!tagMirror.empty()) {
        const auto key = victim->getTag();
        tagMirror[victim->getSet() * mirrorAssoc + victim->getWay()] =
            mirrorKey(key.address, key.tid);
    }
}


} // namespace gem5::branch_prediction
