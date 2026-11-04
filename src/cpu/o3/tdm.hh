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

/**
 * @file
 * Top-down accounting for the O3 CPU, after Yasin, "A Top-Down method for
 * performance analysis and counters architecture" (ISPASS 2014). Adapted
 * from gem5 PR #2392 (Osman Yasar, David Schall).
 *
 * Slots are counted at rename, the dispatch point: renameWidth per cycle.
 * Level 1 splits them into
 *  - retiring: slots of committed micro-ops;
 *  - bad speculation: slots of renamed micro-ops that were squashed, slots
 *    of rename's squashing cycles, and slots left empty during the refill
 *    after a squash (the fetch-to-rename depth);
 *  - front-end bound: slots the back end could take but the front end
 *    left empty, outside the refill;
 *  - back-end bound: the rest.
 * Front-end resteers after the refill (the extra latency of fetching the
 * correct path) are front-end latency, as in Intel's later TMA versions,
 * and reported as branchResteers.
 */

#ifndef __CPU_O3_TDM_HH__
#define __CPU_O3_TDM_HH__

#include "base/statistics.hh"
#include "base/types.hh"

namespace gem5
{

namespace o3
{

class CPU;
class IEW;
class Rename;
class ROB;

struct TopDownStats : public statistics::Group
{
    TopDownStats(CPU *cpu, Rename *rename, IEW *iew, ROB *rob);

    /** A cycle that issues at most this many micro-ops, with work in the
     * ROB, is an execution stall. */
    static constexpr int fewIssuedThreshold = 2;

    /** Classify one cycle of the back end by the micro-ops it issued. */
    void countIssueCycle(int issued);

    /** Remember the back end's state as the CPU goes idle... */
    void noteIdle();
    /** ...and charge the idle cycles to it when the CPU wakes. */
    void addIdleCycles(Cycles cycles);

    IEW *iew;
    ROB *rob;

    /** State the back end idled in. */
    bool idleRobEmpty = true;
    int idleLoadDepth = -1;
    bool idleSqFull = false;

    void countBackend(Counter cycles, int issued, bool rob_empty,
                      int load_depth, bool sq_full);

    /** Cycles of the analysis (active and idle, not quiesced). */
    statistics::Scalar cycles;
    /** Execution stalls: work in the ROB, few micro-ops issued. */
    statistics::Scalar execStallCycles;
    /** Execution stalls with nothing issued and a load outstanding... */
    statistics::Scalar loadStallCycles;
    /** ...whose deepest load has missed the L1D... */
    statistics::Scalar loadStallL1Miss;
    /** ...and the L2. */
    statistics::Scalar loadStallL2Miss;
    /** Execution stalls with nothing issued, no load outstanding and the
     * store queue full. */
    statistics::Scalar storeStallCycles;

    struct Level1 : public statistics::Group
    {
        Level1(TopDownStats *td, CPU *cpu, Rename *rename);
        statistics::Formula slots;
        statistics::Formula frontendBound;
        statistics::Formula badSpeculation;
        statistics::Formula backendBound;
        statistics::Formula retiring;
    } level1;

    struct Frontend : public statistics::Group
    {
        Frontend(TopDownStats *td, Rename *rename);
        statistics::Formula fetchLatency;
        statistics::Formula branchResteers;
        statistics::Formula fetchBandwidth;
    } frontend;

    struct BadSpeculation : public statistics::Group
    {
        BadSpeculation(TopDownStats *td, IEW *iew);
        statistics::Formula branchMispredicts;
        statistics::Formula machineClears;
    } badSpec;

    struct Backend : public statistics::Group
    {
        Backend(TopDownStats *td, Rename *rename);
        statistics::Formula serializeBound;
        statistics::Formula memoryBound;
        statistics::Formula coreBound;
    } backend;

    struct Memory : public statistics::Group
    {
        Memory(TopDownStats *td);
        statistics::Formula l1Bound;
        statistics::Formula l2Bound;
        statistics::Formula extMemBound;
        statistics::Formula storeBound;
    } memory;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_TDM_HH__
