/*
 * Copyright (c) 2025 Technical University of Munich
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

#include "cpu/o3/tdm.hh"

#include "cpu/o3/cpu.hh"
#include "cpu/o3/iew.hh"
#include "cpu/o3/rename.hh"
#include "cpu/o3/rob.hh"

namespace gem5
{

namespace o3
{

namespace
{

const statistics::units::Ratio *ratio() { return statistics::units::Ratio::get(); }

} // anonymous namespace

TopDownStats::TopDownStats(CPU *_cpu, Rename *rename, IEW *_iew,
                           ROB *_rob)
    : statistics::Group(_cpu, "topDown"),
      iew(_iew),
      rob(_rob),
      ADD_STAT(cycles, statistics::units::Cycle::get(),
               "Cycles of the top-down analysis: active and idle, not "
               "quiesced"),
      ADD_STAT(execStallCycles, statistics::units::Cycle::get(),
               "Cycles with micro-ops in the ROB and at most "
               "fewIssuedThreshold (2) issued"),
      ADD_STAT(loadStallCycles, statistics::units::Cycle::get(),
               "Cycles with micro-ops in the ROB, none issued and a load "
               "outstanding"),
      ADD_STAT(loadStallL1Miss, statistics::units::Cycle::get(),
               "loadStallCycles whose deepest outstanding load has missed "
               "the L1D"),
      ADD_STAT(loadStallL2Miss, statistics::units::Cycle::get(),
               "loadStallCycles whose deepest outstanding load has missed "
               "the L2"),
      ADD_STAT(storeStallCycles, statistics::units::Cycle::get(),
               "Cycles with micro-ops in the ROB, none issued, no load "
               "outstanding and the store queue full"),
      level1(this, _cpu, rename),
      frontend(this, rename),
      badSpec(this, _iew),
      backend(this, rename),
      memory(this)
{
}

void
TopDownStats::countBackend(Counter n, int issued, bool rob_empty,
                           int load_depth, bool sq_full)
{
    if (rob_empty || issued > fewIssuedThreshold)
        return;
    execStallCycles += n;
    if (issued > 0)
        return;
    if (load_depth >= 0) {
        loadStallCycles += n;
        if (load_depth >= 1)
            loadStallL1Miss += n;
        if (load_depth >= 2)
            loadStallL2Miss += n;
    } else if (sq_full) {
        storeStallCycles += n;
    }
}

void
TopDownStats::countIssueCycle(int issued)
{
    // Skip the load queue walk on cycles that cannot be a load stall.
    if (rob->isEmpty() || issued > fewIssuedThreshold)
        return;
    LSQ &lsq = iew->ldstQueue;
    countBackend(1, issued, false,
                 issued ? -1 : lsq.deepestOutstandingLoad(), lsq.sqFull());
}

void
TopDownStats::noteIdle()
{
    idleRobEmpty = rob->isEmpty();
    idleLoadDepth = iew->ldstQueue.deepestOutstandingLoad();
    idleSqFull = iew->ldstQueue.sqFull();
}

void
TopDownStats::addIdleCycles(Cycles n)
{
    cycles += n;
    countBackend(n, 0, idleRobEmpty, idleLoadDepth, idleSqFull);
}

TopDownStats::Level1::Level1(TopDownStats *td, CPU *cpu, Rename *rename)
    : statistics::Group(td, "level1"),
      ADD_STAT(slots, statistics::units::Count::get(),
               "Rename slots: renameWidth per top-down cycle"),
      ADD_STAT(frontendBound, ratio(),
               "Share of slots the back end could take but the front end "
               "left empty"),
      ADD_STAT(badSpeculation, ratio(),
               "Share of slots spent on squashed micro-ops, squashing and "
               "the refill after a squash"),
      ADD_STAT(backendBound, ratio(),
               "Share of slots lost to back-end stalls"),
      ADD_STAT(retiring, ratio(),
               "Share of slots of committed micro-ops")
{
    auto &rs = rename->getStats();
    const int width = rename->getWidth();
    slots = width * td->cycles;

    statistics::Temp committed = cpu->commitStats[0]->numOps;
    for (ThreadID tid = 1; tid < cpu->numThreads; ++tid)
        committed = committed + cpu->commitStats[tid]->numOps;

    retiring = committed / slots;
    frontendBound = rs.fetchBubbles / slots;
    badSpeculation = (rs.renamedInsts - committed + rs.refillBubbles +
                      width * rs.status[Rename::Squashing]) / slots;
    backendBound = 1 - (frontendBound + badSpeculation + retiring);
}

TopDownStats::Frontend::Frontend(TopDownStats *td, Rename *rename)
    : statistics::Group(td, "frontend"),
      ADD_STAT(fetchLatency, ratio(),
               "Front-end bound slots of cycles where nothing reached "
               "rename"),
      ADD_STAT(branchResteers, ratio(),
               "Part of fetchLatency: after a squash's refill, before the "
               "first correct-path micro-op reached rename"),
      ADD_STAT(fetchBandwidth, ratio(),
               "Front-end bound slots of cycles where too few micro-ops "
               "reached rename")
{
    auto &rs = rename->getStats();
    auto &slots = td->level1.slots;
    fetchLatency = rs.fetchLatencyBubbles / slots;
    branchResteers = rs.resteerBubbles / slots;
    fetchBandwidth = (rs.fetchBubbles - rs.fetchLatencyBubbles) / slots;
}

TopDownStats::BadSpeculation::BadSpeculation(TopDownStats *td, IEW *iew)
    : statistics::Group(td, "badSpec"),
      ADD_STAT(branchMispredicts, ratio(),
               "Bad speculation split by event count: branch mispredicts "
               "resolved at execute"),
      ADD_STAT(machineClears, ratio(),
               "Bad speculation split by event count: the rest (memory "
               "order violations, and squashes from commit by proportion)")
{
    auto &is = iew->getStats();
    auto &bs = td->level1.badSpeculation;
    branchMispredicts = bs * is.branchMispredicts /
        (is.branchMispredicts + is.memOrderViolationEvents);
    machineClears = bs - branchMispredicts;
}

TopDownStats::Backend::Backend(TopDownStats *td, Rename *rename)
    : statistics::Group(td, "backend"),
      ADD_STAT(serializeBound, ratio(),
               "Slots of cycles rename waited to serialize an instruction"),
      ADD_STAT(memoryBound, ratio(),
               "Rest of back-end bound, by the share of execution stalls "
               "waiting on loads or a full store queue"),
      ADD_STAT(coreBound, ratio(),
               "Rest of back-end bound, the other execution stalls")
{
    auto &rs = rename->getStats();
    auto &l1 = td->level1;
    serializeBound = rename->getWidth() *
        rs.status[Rename::SerializeStall] / l1.slots;
    memoryBound = (l1.backendBound - serializeBound) *
        (td->loadStallCycles + td->storeStallCycles) / td->execStallCycles;
    coreBound = l1.backendBound - serializeBound - memoryBound;
}

TopDownStats::Memory::Memory(TopDownStats *td)
    : statistics::Group(td, "memory"),
      ADD_STAT(l1Bound, ratio(),
               "Memory bound, no outstanding load past the L1D (hits, "
               "translations)"),
      ADD_STAT(l2Bound, ratio(),
               "Memory bound, the deepest outstanding load in the L2"),
      ADD_STAT(extMemBound, ratio(),
               "Memory bound, the deepest outstanding load past the L2 "
               "(DRAM on a hierarchy without an L3)"),
      ADD_STAT(storeBound, ratio(),
               "Memory bound, store queue full")
{
    auto &mem = td->backend.memoryBound;
    statistics::Temp stalls = td->loadStallCycles + td->storeStallCycles;
    l1Bound = mem * (td->loadStallCycles - td->loadStallL1Miss) / stalls;
    l2Bound = mem * (td->loadStallL1Miss - td->loadStallL2Miss) / stalls;
    extMemBound = mem * td->loadStallL2Miss / stalls;
    storeBound = mem * td->storeStallCycles / stalls;
}

} // namespace o3
} // namespace gem5
