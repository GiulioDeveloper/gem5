/*
 * Copyright (c) 2010, 2016, 2021, 2025 Arm Limited
 * Copyright (c) 2013 Advanced Micro Devices, Inc.
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
 * Copyright (c) 2004-2006 The Regents of The University of Michigan
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

#ifndef __CPU_O3_DYN_INST_HH__
#define __CPU_O3_DYN_INST_HH__

#include <algorithm>
#include <array>
#include <deque>
#include <list>
#include <string>

#include "base/refcnt.hh"
#include "base/trace.hh"
#include "cpu/checker/cpu.hh"
#include "cpu/exec_context.hh"
#include "cpu/exetrace.hh"
#include "cpu/inst_res.hh"
#include "cpu/inst_seq.hh"
#include "cpu/o3/cpu.hh"
#include "cpu/o3/dyn_inst_ptr.hh"
#include "cpu/o3/lsq_unit.hh"
#include "cpu/o3/mem_rename_valuefile.hh"
#include "cpu/o3/vp/vp_history.hh"
#include "cpu/op_class.hh"
#include "cpu/reg_class.hh"
#include "cpu/static_inst.hh"
#include "cpu/translation.hh"
#include "debug/HtmCpu.hh"

namespace gem5
{

class Packet;

namespace o3
{

class DynInst : public ExecContext, public RefCounted
{
  private:
    DynInst(const StaticInstPtr &staticInst, const StaticInstPtr &macroop,
            InstSeqNum seq_num, CPU *cpu);

  public:
    // The list of instructions iterator type.
    typedef typename std::list<DynInstPtr>::iterator ListIt;

    struct Arrays
    {
        size_t numSrcs;
        size_t numDests;

        RegId *flatDestIdx;
        PhysRegIdPtr *destIdx;
        PhysRegIdPtr *prevDestIdx;
        PhysRegIdPtr *srcIdx;
        uint8_t *readySrcIdx;
    };

    static void *operator new(size_t count, Arrays &arrays);
    static void  operator delete(void* ptr);

    /** BaseDynInst constructor given a binary instruction. */
    DynInst(const Arrays &arrays, const StaticInstPtr &staticInst,
            const StaticInstPtr &macroop, InstSeqNum seq_num, CPU *cpu);

    DynInst(const Arrays &arrays, const StaticInstPtr &staticInst,
            const StaticInstPtr &macroop, const PCStateBase &pc,
            const PCStateBase &pred_pc, InstSeqNum seq_num, CPU *cpu);

    /** BaseDynInst constructor given a static inst pointer. */
    DynInst(const Arrays &arrays, const StaticInstPtr &_staticInst,
            const StaticInstPtr &_macroop);

    ~DynInst();

    /** Executes the instruction.*/
    Fault execute();

    /** Initiates the access.  Only valid for memory operations. */
    Fault initiateAcc();

    /** Completes the access.  Only valid for memory operations. */
    Fault completeAcc(PacketPtr pkt);

    /** The sequence number of the instruction. */
    InstSeqNum seqNum = 0;

    /** The StaticInst used by this BaseDynInst. */
    const StaticInstPtr staticInst;

    /** Pointer to the Impl's CPU object. */
    CPU *cpu = nullptr;

    BaseCPU *getCpuPtr() { return cpu; }

    /** Pointer to the thread state. */
    ThreadState *thread = nullptr;

    /** The kind of fault this instruction has generated. */
    Fault fault = NoFault;

    /** InstRecord that tracks this instructions. */
    trace::InstRecord *traceData = nullptr;

  protected:
    enum Status
    {
        IqEntry,                 /// Instruction is in the IQ
        RobEntry,                /// Instruction is in the ROB
        LsqEntry,                /// Instruction is in the LSQ
        Completed,               /// Instruction has completed
        ResultReady,             /// Instruction has its result
        CanIssue,                /// Instruction can issue and execute
        Issued,                  /// Instruction has issued
        Executed,                /// Instruction has executed
        CanCommit,               /// Instruction can commit
        AtCommit,                /// Instruction has reached commit
        Committed,               /// Instruction has committed
        Squashed,                /// Instruction is squashed
        SquashedInIQ,            /// Instruction is squashed in the IQ
        SquashedInLSQ,           /// Instruction is squashed in the LSQ
        SquashedInROB,           /// Instruction is squashed in the ROB
        PinnedRegsRenamed,       /// Pinned registers are renamed
        PinnedRegsWritten,       /// Pinned registers are written back
        PinnedRegsSquashDone,    /// Regs pinning status updated after squash
        RecoverInst,             /// Is a recover instruction
        BlockingInst,            /// Is a blocking instruction
        ThreadsyncWait,          /// Is a thread synchronization instruction
        SerializeBefore,         /// Needs to serialize on
                                 /// instructions ahead of it
        SerializeAfter,          /// Needs to serialize instructions behind it
        SerializeHandled,        /// Serialization has been handled
        NumStatus
    };

    enum Flags
    {
        NotAnInst,
        TranslationStarted,
        TranslationCompleted,
        PossibleLoadViolation,
        HitExternalSnoop,
        EffAddrValid,
        RecordResult,
        Predicate,
        MemAccPredicate,
        PredTaken,
        IsStrictlyOrdered,
        ReqMade,
        MemOpDone,
        HtmFromTransaction,
        NoCapableFU,   /// Processor does not have capability to
                       /// execute the instruction
        IsGhost,       /// Garfield: skip OoO IQ entry, issue
                       /// bandwidth, and execution port
        Mrned,         /// Garfield: load was memory-renamed (MRN)
        MrnResolved,   /// Garfield: the MRN prediction was resolved (correct
                       /// or mispredicted); a squash must not re-account it
        MrnVfEligible, /// Garfield value-file rendezvous: this load passed
                       /// the participation guards at rename (single
                       /// integer destination)
        VpPredicted,   /// Garfield VP: a value prediction was consumed
                       /// into this instruction's renamed destination
        VpResolved,    /// Garfield VP: the prediction was resolved
                       /// (verified or accounted squashed); a squash
                       /// must not re-account it
        VpInflightCounted, /// Garfield VP: counted in the predictor's
                           /// per-PC in-flight occurrence map at
                           /// rename; the exactly-once decrement
                           /// (commit-train or squash walk) clears it
        MaxFlags
    };

  private:
    /* An amalgamation of a lot of boolean values into one */
    std::bitset<MaxFlags> instFlags;

    /** The status of this BaseDynInst.  Several bits can be set. */
    std::bitset<NumStatus> status;

  protected:
    /** The result of the instruction; assumes an instruction can have many
     *  destination registers.
     */
    std::queue<InstResult> instResult;

    /** PC state for this instruction. */
    std::unique_ptr<PCStateBase> pc;

    /** Values to be written to the destination misc. registers. */
    std::vector<RegVal> _destMiscRegVal;

    /** Indexes of the destination misc. registers. They are needed to defer
     * the write accesses to the misc. registers until the commit stage, when
     * the instruction is out of its speculative state.
     */
    std::vector<short> _destMiscRegIdx;

    size_t _numSrcs;
    size_t _numDests;

    // Flattened register index of the destination registers of this
    // instruction.
    RegId *_flatDestIdx;

    // Physical register index of the destination registers of this
    // instruction.
    PhysRegIdPtr *_destIdx;

    // Physical register index of the previous producers of the
    // architected destinations.
    PhysRegIdPtr *_prevDestIdx;

    // Physical register index of the source registers of this instruction.
    PhysRegIdPtr *_srcIdx;

    // Whether or not the source register is ready, one bit per register.
    uint8_t *_readySrcIdx;

  public:
    size_t numSrcs() const { return _numSrcs; }
    size_t numDests() const { return _numDests; }

    // Returns the flattened register index of the idx'th destination
    // register.
    const RegId &
    flattenedDestIdx(int idx) const
    {
        return _flatDestIdx[idx];
    }

    // Flattens a destination architectural register index into a logical
    // index.
    void
    flattenedDestIdx(int idx, const RegId &reg_id)
    {
        _flatDestIdx[idx] = reg_id;
    }

    // Returns the physical register index of the idx'th destination
    // register.
    PhysRegIdPtr
    renamedDestIdx(int idx) const
    {
        return _destIdx[idx];
    }

    // Set the renamed dest register id.
    void
    renamedDestIdx(int idx, PhysRegIdPtr phys_reg_id)
    {
        _destIdx[idx] = phys_reg_id;
    }

    // Returns the physical register index of the previous physical
    // register that remapped to the same logical register index.
    PhysRegIdPtr
    prevDestIdx(int idx) const
    {
        return _prevDestIdx[idx];
    }

    // Set the previous renamed dest register id.
    void
    prevDestIdx(int idx, PhysRegIdPtr phys_reg_id)
    {
        _prevDestIdx[idx] = phys_reg_id;
    }

    // Returns the physical register index of the i'th source register.
    PhysRegIdPtr
    renamedSrcIdx(int idx) const
    {
        return _srcIdx[idx];
    }

    void
    renamedSrcIdx(int idx, PhysRegIdPtr phys_reg_id)
    {
        _srcIdx[idx] = phys_reg_id;
    }

    bool
    readySrcIdx(int idx) const
    {
        uint8_t &byte = _readySrcIdx[idx / 8];
        return bits(byte, idx % 8);
    }

    void
    readySrcIdx(int idx, bool ready)
    {
        uint8_t &byte = _readySrcIdx[idx / 8];
        replaceBits(byte, idx % 8, ready ? 1 : 0);
    }

    /** The thread this instruction is from. */
    ThreadID threadNumber = 0;

    /** Iterator pointing to this BaseDynInst in the list of all insts. */
    ListIt instListIt;

    ////////////////////// Branch Data ///////////////
    /** Predicted PC state after this instruction. */
    std::unique_ptr<PCStateBase> predPC;

    /** The Macroop if one exists */
    const StaticInstPtr macroop;

    /** How many source registers are ready. */
    uint8_t readyRegs = 0;

  public:
    /////////////////////// Load Store Data //////////////////////
    /** The effective virtual address (lds & stores only). */
    Addr effAddr = 0;

    /** The effective physical address. */
    Addr physEffAddr = 0;

    /** The memory request flags (from translation). */
    unsigned memReqFlags = 0;

    /** The size of the request */
    unsigned effSize;

    /** Pointer to the data for the memory access. */
    uint8_t *memData = nullptr;

    /** Load queue index. */
    ssize_t lqIdx = -1;
    typename LSQUnit::LQIterator lqIt;

    /** Store queue index. */
    ssize_t sqIdx = -1;
    typename LSQUnit::SQIterator sqIt;


    /////////////////////// TLB Miss //////////////////////
    /**
     * Saved memory request (needed when the DTB address translation is
     * delayed due to a hw page table walk).
     */
    LSQ::LSQRequest *savedRequest;

    /////////////////////// Checker //////////////////////
    // Need a copy of main request pointer to verify on writes.
    RequestPtr reqToVerify;

  public:
    /** Records changes to result? */
    void recordResult(bool f) { instFlags[RecordResult] = f; }

    /** Is the effective virtual address valid. */
    bool effAddrValid() const { return instFlags[EffAddrValid]; }
    void effAddrValid(bool b) { instFlags[EffAddrValid] = b; }

    /** Whether or not the memory operation is done. */
    bool memOpDone() const { return instFlags[MemOpDone]; }
    void memOpDone(bool f) { instFlags[MemOpDone] = f; }

    bool notAnInst() const { return instFlags[NotAnInst]; }
    void setNotAnInst() { instFlags[NotAnInst] = true; }

    /** Garfield: ghost uop (skips OoO IQ/issue/port accounting). */
    bool
    isGhost() const
    {
        return instFlags[IsGhost];
    }
    void
    setGhost()
    {
        instFlags[IsGhost] = true;
    }

    /** Garfield: load was memory-renamed (MRN). */
    bool
    isMrned() const
    {
        return instFlags[Mrned];
    }
    void
    setMrned()
    {
        instFlags[Mrned] = true;
    }

    /** Garfield: the MRN prediction for this load has been resolved --
     *  it verified correct or it mispredicted. Set on all four resolution
     *  arms in LSQUnit, including the mispredict arms: squashDueToMemOrder
     *  is inclusive, so a mispredicting load squashes itself and would
     *  otherwise be counted both as a mispredict and as a squashed
     *  prediction. */
    bool
    mrnResolved() const
    {
        return instFlags[MrnResolved];
    }
    void
    setMrnResolved()
    {
        instFlags[MrnResolved] = true;
    }

    /** Garfield: MRN-predicted value snapshotted for this load. */
    RegVal
    mrnPredVal() const
    {
        return _mrnPredVal;
    }
    void
    setMrnPredVal(RegVal v)
    {
        _mrnPredVal = v;
    }

    /** Garfield: which MRN forwarding path this load took. NONE = not
     *  forwarded; VALUE = value snapshot (verify vs mrnPredVal);
     *  ALIAS = producer aliasing (verify vs the producer
     *  physreg's value). */
    enum MrnPath
    {
        MrnNone = 0,
        MrnValue,
        MrnAlias
    };

    /** Garfield value-file rendezvous: which consumption or shadow
     *  (non-consuming, confidence-training) mode this instruction took.
     *  NONE = no value-file action; ALIAS/PRODUCER_VALUE/LAST_VALUE are the
     *  three consumed modes (design doc §5); SHADOW_VALUE/SHADOW_PTR are
     *  below-confidence snapshots kept only to train confidence upward
     *  (design doc §5, "Shadow verification"). */
    enum MrnVfMode : uint8_t
    {
        MrnVfNone = 0,
        MrnVfAlias,
        MrnVfProducerValue,
        MrnVfLastValue,
        MrnVfShadowValue,
        MrnVfShadowPtr
    };

    MrnPath
    mrnPath() const
    {
        return _mrnPath;
    }
    void
    setMrnPath(MrnPath p)
    {
        _mrnPath = p;
    }
    bool
    mrnAliased() const
    {
        return _mrnPath == MrnAlias;
    }

    /** Garfield MRN aliasing: the in-flight producer's physreg this load
     * is aliased to. Its value is the prediction verified at writeback. */
    PhysRegIdPtr
    mrnAliasProducer() const
    {
        return _mrnAliasProducer;
    }
    void
    setMrnAliasProducer(PhysRegIdPtr p)
    {
        _mrnAliasProducer = p;
    }

    /** Garfield MRN aliasing: sequence number of the producing store
     * (debug / verify timing). */
    InstSeqNum
    mrnProducerSeq() const
    {
        return _mrnProducerSeq;
    }
    void
    setMrnProducerSeq(InstSeqNum sn)
    {
        _mrnProducerSeq = sn;
    }

    /** Garfield value-file rendezvous: the value-file cell this store
     *  deposited into at its own rename, or this load is bound to by its
     *  PC (invalid, {-1, 0}, when the model made no binding). */
    MrnVfRef
    mrnVfRef() const
    {
        return MrnVfRef{_mrnVfIdx, _mrnVfGen};
    }
    void
    setMrnVfRef(const MrnVfRef &r)
    {
        _mrnVfIdx = r.idx;
        _mrnVfGen = r.gen;
    }

    /** Garfield value-file rendezvous: which mode (MrnVfMode) this
     *  instruction's value-file interaction took. */
    uint8_t
    mrnVfMode() const
    {
        return _mrnVfMode;
    }
    void
    setMrnVfMode(uint8_t m)
    {
        _mrnVfMode = m;
    }

    /** Garfield: which level of the memory system served this load's
     *  data. Stamped MemSrcStlf at store-to-load forwarding (the access
     *  never reaches the caches); otherwise derived at writeback from
     *  the request's cache-miss depth (0 = L1D hit, 1 = L2 hit,
     *  >= 2 = memory). MemSrcUnknown until the load writes back. */
    enum MemSrcLevel : uint8_t
    {
        MemSrcStlf = 0,
        MemSrcL1D,
        MemSrcL2,
        MemSrcMem,
        MemSrcUnknown
    };
    uint8_t
    memSrcLevel() const
    {
        return _memSrcLevel;
    }
    void
    setMemSrcLevel(uint8_t l)
    {
        _memSrcLevel = l;
    }

    /** Garfield value-file rendezvous: this load passed the participation
     *  guards at rename (single integer destination) and is eligible for
     *  value-file lookup and confidence training, independent of whether a
     *  prediction was actually consumed. */
    bool
    mrnVfEligible() const
    {
        return instFlags[MrnVfEligible];
    }
    void
    setMrnVfEligible()
    {
        instFlags[MrnVfEligible] = true;
    }

    /** Garfield value-file rendezvous: the snapshotted value for a
     *  below-confidence shadow prediction (MrnVfShadowValue). Writeback
     *  compares this against the real value purely to train confidence;
     *  a shadow prediction is never consumed, so the comparison never
     *  squashes. Consumed value predictions use the existing
     *  mrnPredVal()/setMrnPredVal() instead. */
    RegVal
    mrnVfShadowVal() const
    {
        return _mrnVfShadowVal;
    }
    void
    setMrnVfShadowVal(RegVal v)
    {
        _mrnVfShadowVal = v;
    }

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

    /** Garfield VP: the {ghr, path} history snapshot stamped at fetch
     *  (docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md, "History
     *  Subsystem"). Only meaningful for history-aware predictors
     *  (BaseValuePredictor::usesHistory()); LVP never reads it. */
    const VpHistSnapshot &
    vpHistSnap() const
    {
        return _vpHistSnap;
    }
    void
    setVpHistSnap(const VpHistSnapshot &snap)
    {
        _vpHistSnap = snap;
    }

    /** Garfield VP: the opaque provider token stamped by predict() on
     *  every lookup (even below-confidence ones), recovered at
     *  train()/verify() to locate the exact provider entry without a
     *  second table search. 0 = no lookup was made (out of scope, or
     *  an MRN-claimed load that bypassed predict()); LVP always
     *  stamps 0. */
    uint64_t
    vpToken() const
    {
        return _vpToken;
    }
    void
    setVpToken(uint64_t token)
    {
        _vpToken = token;
    }

    ////////////////////////////////////////////
    //
    // INSTRUCTION EXECUTION
    //
    ////////////////////////////////////////////

    void
    demapPage(Addr vaddr, uint64_t asn) override
    {
        cpu->demapPage(vaddr, asn);
    }

    Fault initiateMemRead(Addr addr, unsigned size, Request::Flags flags,
            const std::vector<bool> &byte_enable) override;

    Fault initiateMemMgmtCmd(Request::Flags flags) override;

    Fault writeMem(uint8_t *data, unsigned size, Addr addr,
                   Request::Flags flags, uint64_t *res,
                   const std::vector<bool> &byte_enable) override;

    Fault initiateMemAMO(Addr addr, unsigned size, Request::Flags flags,
                         AtomicOpFunctorPtr amo_op) override;

    /** True if the DTB address translation has started. */
    bool translationStarted() const { return instFlags[TranslationStarted]; }
    void translationStarted(bool f) { instFlags[TranslationStarted] = f; }

    /** True if the DTB address translation has completed. */
    bool
    translationCompleted() const
    {
        return instFlags[TranslationCompleted];
    }
    void translationCompleted(bool f) { instFlags[TranslationCompleted] = f; }

    /** True if this address was found to match a previous load and they issued
     * out of order. If that happend, then it's only a problem if an incoming
     * snoop invalidate modifies the line, in which case we need to squash.
     * If nothing modified the line the order doesn't matter.
     */
    bool
    possibleLoadViolation() const
    {
        return instFlags[PossibleLoadViolation];
    }
    void
    possibleLoadViolation(bool f)
    {
        instFlags[PossibleLoadViolation] = f;
    }

    /** True if the address hit a external snoop while sitting in the LSQ.
     * If this is true and a older instruction sees it, this instruction must
     * reexecute
     */
    bool hitExternalSnoop() const { return instFlags[HitExternalSnoop]; }
    void hitExternalSnoop(bool f) { instFlags[HitExternalSnoop] = f; }

    /**
     * Returns true if the DTB address translation is being delayed due to a hw
     * page table walk.
     */
    bool
    isTranslationDelayed() const
    {
        return (translationStarted() && !translationCompleted());
    }

  public:
#ifdef GEM5_DEBUG
    void dumpSNList();
#endif

    /** Renames a destination register to a physical register.  Also records
     *  the previous physical register that the logical register mapped to.
     */
    void
    renameDestReg(int idx, PhysRegIdPtr renamed_dest,
                  PhysRegIdPtr previous_rename)
    {
        renamedDestIdx(idx, renamed_dest);
        prevDestIdx(idx, previous_rename);
        if (renamed_dest->isPinned())
            setPinnedRegsRenamed();
    }

    /** Renames a source logical register to the physical register which
     *  has/will produce that logical register's result.
     *  @todo: add in whether or not the source register is ready.
     */
    void
    renameSrcReg(int idx, PhysRegIdPtr renamed_src)
    {
        renamedSrcIdx(idx, renamed_src);
    }

    /** Dumps out contents of this BaseDynInst. */
    void dump();

    /** Dumps out contents of this BaseDynInst into given string. */
    void dump(std::string &outstring);

    /** Read this CPU's ID. */
    int cpuId() const { return cpu->cpuId(); }

    /** Read this CPU's Socket ID. */
    uint32_t socketId() const { return cpu->socketId(); }

    /** Read this CPU's data requestor ID */
    RequestorID requestorId() const { return cpu->dataRequestorId(); }

    /** Read this context's system-wide ID **/
    ContextID contextId() const { return thread->contextId(); }

    /** Returns the fault type. */
    Fault getFault() const { return fault; }
    /** TODO: This I added for the LSQRequest side to be able to modify the
     * fault. There should be a better mechanism in place. */
    Fault& getFault() { return fault; }

    /** Checks whether or not this instruction has had its branch target
     *  calculated yet.  For now it is not utilized and is hacked to be
     *  always false.
     *  @todo: Actually use this instruction.
     */
    bool doneTargCalc() { return false; }

    /** Set the predicted target of this current instruction. */
    void setPredTarg(const PCStateBase &pred_pc) { set(predPC, pred_pc); }

    const PCStateBase &readPredTarg() { return *predPC; }

    /** Returns whether the instruction was predicted taken or not. */
    bool
    readPredTaken() const
    {
        return instFlags[PredTaken];
    }

    void
    setPredTaken(bool predicted_taken)
    {
        instFlags[PredTaken] = predicted_taken;
    }

    /** Returns whether the instruction mispredicted. */
    bool
    mispredicted() const
    {
        std::unique_ptr<PCStateBase> next_pc(pc->clone());
        staticInst->advancePC(*next_pc);
        return *next_pc != *predPC;
    }

    //
    //  Instruction types.  Forward checks to StaticInst object.
    //
    bool isNop()          const { return staticInst->isNop(); }
    bool isMemRef()       const { return staticInst->isMemRef(); }
    bool isLoad()         const { return staticInst->isLoad(); }
    bool isStore()        const { return staticInst->isStore(); }
    bool isAtomic()       const { return staticInst->isAtomic(); }
    bool isStoreConditional() const
    { return staticInst->isStoreConditional(); }
    bool isInstPrefetch() const { return staticInst->isInstPrefetch(); }
    bool isDataPrefetch() const { return staticInst->isDataPrefetch(); }
    bool isInteger()      const { return staticInst->isInteger(); }
    bool isFloating()     const { return staticInst->isFloating(); }
    bool isVector()       const { return staticInst->isVector(); }
    bool isControl()      const { return staticInst->isControl(); }
    bool isCall()         const { return staticInst->isCall(); }
    bool isReturn()       const { return staticInst->isReturn(); }
    bool isDirectCtrl()   const { return staticInst->isDirectCtrl(); }
    bool isIndirectCtrl() const { return staticInst->isIndirectCtrl(); }
    bool isCondCtrl()     const { return staticInst->isCondCtrl(); }
    bool isUncondCtrl()   const { return staticInst->isUncondCtrl(); }
    bool isSerializing()  const { return staticInst->isSerializing(); }
    bool
    isSerializeBefore() const
    {
        return staticInst->isSerializeBefore() || status[SerializeBefore];
    }
    bool
    isSerializeAfter() const
    {
        return staticInst->isSerializeAfter() || status[SerializeAfter];
    }
    bool isSquashAfter() const { return staticInst->isSquashAfter(); }
    bool isFullMemBarrier()   const { return staticInst->isFullMemBarrier(); }
    bool isReadBarrier() const { return staticInst->isReadBarrier(); }
    bool isWriteBarrier() const { return staticInst->isWriteBarrier(); }
    bool isNonSpeculative() const { return staticInst->isNonSpeculative(); }
    bool isQuiesce() const { return staticInst->isQuiesce(); }
    bool isUnverifiable() const { return staticInst->isUnverifiable(); }
    bool isSyscall() const { return staticInst->isSyscall(); }
    bool isMacroop() const { return staticInst->isMacroop(); }
    bool isMicroop() const { return staticInst->isMicroop(); }
    bool isDelayedCommit() const { return staticInst->isDelayedCommit(); }
    bool isLastMicroop() const { return staticInst->isLastMicroop(); }
    bool isFirstMicroop() const { return staticInst->isFirstMicroop(); }
    // hardware transactional memory
    bool isHtmStart() const { return staticInst->isHtmStart(); }
    bool isHtmStop() const { return staticInst->isHtmStop(); }
    bool isHtmCancel() const { return staticInst->isHtmCancel(); }
    bool isHtmCmd() const { return staticInst->isHtmCmd(); }

    uint64_t
    getHtmTransactionUid() const override
    {
        assert(instFlags[HtmFromTransaction]);
        return htmUid;
    }

    uint64_t
    newHtmTransactionUid() const override
    {
        panic("Not yet implemented\n");
        return 0;
    }

    bool
    inHtmTransactionalState() const override
    {
        return instFlags[HtmFromTransaction];
    }

    uint64_t
    getHtmTransactionalDepth() const override
    {
        if (inHtmTransactionalState())
            return htmDepth;
        else
            return 0;
    }

    void
    setHtmTransactionalState(uint64_t htm_uid, uint64_t htm_depth)
    {
        instFlags.set(HtmFromTransaction);
        htmUid = htm_uid;
        htmDepth = htm_depth;
    }

    void
    clearHtmTransactionalState()
    {
        if (inHtmTransactionalState()) {
            DPRINTF(HtmCpu,
                "clearing instuction's transactional state htmUid=%u\n",
                getHtmTransactionUid());

            instFlags.reset(HtmFromTransaction);
            htmUid = -1;
            htmDepth = 0;
        }
    }

    /** Temporarily sets this instruction as a serialize before instruction. */
    void setSerializeBefore() { status.set(SerializeBefore); }

    /** Clears the serializeBefore part of this instruction. */
    void clearSerializeBefore() { status.reset(SerializeBefore); }

    /** Checks if this serializeBefore is only temporarily set. */
    bool isTempSerializeBefore() { return status[SerializeBefore]; }

    /** Temporarily sets this instruction as a serialize after instruction. */
    void setSerializeAfter() { status.set(SerializeAfter); }

    /** Clears the serializeAfter part of this instruction.*/
    void clearSerializeAfter() { status.reset(SerializeAfter); }

    /** Checks if this serializeAfter is only temporarily set. */
    bool isTempSerializeAfter() { return status[SerializeAfter]; }

    /** Sets the serialization part of this instruction as handled. */
    void setSerializeHandled() { status.set(SerializeHandled); }

    /** Checks if the serialization part of this instruction has been
     *  handled.  This does not apply to the temporary serializing
     *  state; it only applies to this instruction's own permanent
     *  serializing state.
     */
    bool isSerializeHandled() { return status[SerializeHandled]; }

    /** Returns the opclass of this instruction. */
    OpClass opClass() const { return staticInst->opClass(); }

    /** Returns the branch target address. */
    std::unique_ptr<PCStateBase>
    branchTarget() const
    {
        return staticInst->branchTarget(*pc);
    }

    /** Returns the number of source registers. */
    size_t numSrcRegs() const { return numSrcs(); }

    /** Returns the number of destination registers. */
    size_t numDestRegs() const { return numDests(); }

    size_t
    numDestRegs(RegClassType type) const
    {
        return staticInst->numDestRegs(type);
    }

    /** Returns the logical register index of the i'th destination register. */
    const RegId& destRegIdx(int i) const { return staticInst->destRegIdx(i); }

    /** Returns the logical register index of the i'th source register. */
    const RegId& srcRegIdx(int i) const { return staticInst->srcRegIdx(i); }

    /** Return the size of the instResult queue. */
    uint8_t resultSize() { return instResult.size(); }

    /** Pops a result off the instResult queue.
     * If the result stack is empty, return the default value.
     * */
    InstResult
    popResult(InstResult dflt=InstResult())
    {
        if (!instResult.empty()) {
            InstResult t = instResult.front();
            instResult.pop();
            return t;
        }
        return dflt;
    }

    /** Pushes a result onto the instResult queue. */
    /** @{ */
    template<typename T>
    void
    setResult(const RegClass &reg_class, T &&t)
    {
        if (instFlags[RecordResult]) {
            instResult.emplace(reg_class, std::forward<T>(t));
        }
    }
    /** @} */

    /** Records that one of the source registers is ready. */
    void markSrcRegReady();

    /** Marks a specific register as ready. */
    void markSrcRegReady(RegIndex src_idx);

    /** Sets this instruction as completed. */
    void setCompleted() { status.set(Completed); }

    /** Returns whether or not this instruction is completed. */
    bool isCompleted() const { return status[Completed]; }

    /** Marks the result as ready. */
    void setResultReady() { status.set(ResultReady); }

    /** Returns whether or not the result is ready. */
    bool isResultReady() const { return status[ResultReady]; }

    /** Sets this instruction as ready to issue. */
    void setCanIssue() { status.set(CanIssue); }

    /** Returns whether or not this instruction is ready to issue. */
    bool readyToIssue() const { return status[CanIssue]; }

    /** Clears this instruction being able to issue. */
    void clearCanIssue() { status.reset(CanIssue); }

    /** Sets this instruction as issued from the IQ. */
    void setIssued() { status.set(Issued); }

    /** Returns whether or not this instruction has issued. */
    bool isIssued() const { return status[Issued]; }

    /** Clears this instruction as being issued. */
    void clearIssued() { status.reset(Issued); }

    /** Sets this instruction as executed. */
    void setExecuted() { status.set(Executed); }

    /** Returns whether or not this instruction has executed. */
    bool isExecuted() const { return status[Executed]; }

    /** Sets this instruction as ready to commit. */
    void setCanCommit() { status.set(CanCommit); }

    /** Clears this instruction as being ready to commit. */
    void clearCanCommit() { status.reset(CanCommit); }

    /** Returns whether or not this instruction is ready to commit. */
    bool readyToCommit() const { return status[CanCommit]; }

    void setAtCommit() { status.set(AtCommit); }

    bool isAtCommit() { return status[AtCommit]; }

    /** Sets this instruction as committed. */
    void setCommitted() { status.set(Committed); }

    /** Returns whether or not this instruction is committed. */
    bool isCommitted() const { return status[Committed]; }

    /** Sets this instruction as squashed. */
    void setSquashed();

    /** Returns whether or not this instruction is squashed. */
    bool isSquashed() const { return status[Squashed]; }

    //Instruction Queue Entry
    //-----------------------
    /** Sets this instruction as a entry the IQ. */
    void
    setInIQ(IQUnit *_iq)
    {
        assert(!iq);
        status.set(IqEntry);
        iq = _iq;
    }

    /** Clears this instruction as a entry the IQ. */
    void
    clearInIQ()
    {
        assert(iq);
        status.reset(IqEntry);
        iq->remove(this);
        iq = nullptr;
    }

    /** Returns whether or not this instruction has issued. */
    bool isInIQ() const { return status[IqEntry]; }

    /** Sets this instruction as squashed in the IQ. */
    void setSquashedInIQ() { status.set(SquashedInIQ); status.set(Squashed);}

    /** Returns whether or not this instruction is squashed in the IQ. */
    bool isSquashedInIQ() const { return status[SquashedInIQ]; }

    /** Pointer to the IQ storing the instruction */
    IQUnit *iq = nullptr;

    //Load / Store Queue Functions
    //-----------------------
    /** Sets this instruction as a entry the LSQ. */
    void setInLSQ() { status.set(LsqEntry); }

    /** Sets this instruction as a entry the LSQ. */
    void removeInLSQ() { status.reset(LsqEntry); }

    /** Returns whether or not this instruction is in the LSQ. */
    bool isInLSQ() const { return status[LsqEntry]; }

    /** Sets this instruction as squashed in the LSQ. */
    void setSquashedInLSQ() { status.set(SquashedInLSQ); status.set(Squashed);}

    /** Returns whether or not this instruction is squashed in the LSQ. */
    bool isSquashedInLSQ() const { return status[SquashedInLSQ]; }


    //Reorder Buffer Functions
    //-----------------------
    /** Sets this instruction as a entry the ROB. */
    void setInROB() { status.set(RobEntry); }

    /** Sets this instruction as a entry the ROB. */
    void clearInROB() { status.reset(RobEntry); }

    /** Returns whether or not this instruction is in the ROB. */
    bool isInROB() const { return status[RobEntry]; }

    /** Sets this instruction as squashed in the ROB. */
    void setSquashedInROB() { status.set(SquashedInROB); }

    /** Returns whether or not this instruction is squashed in the ROB. */
    bool isSquashedInROB() const { return status[SquashedInROB]; }

    /** Mark this instruction as having attempted to execute
     * but CPU did not have a capable functional unit.
     */
    void setNoCapableFU() { instFlags.set(NoCapableFU); }

    /** Returns whether or not this instruction attempted
     * to execute and found not capable FU.
     */
    bool noCapableFU() const { return instFlags[NoCapableFU]; }

    /** Returns whether pinned registers are renamed */
    bool isPinnedRegsRenamed() const { return status[PinnedRegsRenamed]; }

    /** Sets the destination registers as renamed */
    void
    setPinnedRegsRenamed()
    {
        assert(!status[PinnedRegsSquashDone]);
        assert(!status[PinnedRegsWritten]);
        status.set(PinnedRegsRenamed);
    }

    /** Returns whether destination registers are written */
    bool isPinnedRegsWritten() const { return status[PinnedRegsWritten]; }

    /** Sets destination registers as written */
    void
    setPinnedRegsWritten()
    {
        assert(!status[PinnedRegsSquashDone]);
        assert(status[PinnedRegsRenamed]);
        status.set(PinnedRegsWritten);
    }

    /** Return whether dest registers' pinning status updated after squash */
    bool
    isPinnedRegsSquashDone() const
    {
        return status[PinnedRegsSquashDone];
    }

    /** Sets dest registers' status updated after squash */
    void
    setPinnedRegsSquashDone()
    {
        assert(!status[PinnedRegsSquashDone]);
        status.set(PinnedRegsSquashDone);
    }

    /** Read the PC state of this instruction. */
    const PCStateBase &
    pcState() const override
    {
        return *pc;
    }

    /** Set the PC state of this instruction. */
    void pcState(const PCStateBase &val) override { set(pc, val); }

    bool readPredicate() const override { return instFlags[Predicate]; }

    void
    setPredicate(bool val) override
    {
        instFlags[Predicate] = val;

        if (traceData) {
            traceData->setPredicate(val);
        }
    }

    bool
    readMemAccPredicate() const override
    {
        return instFlags[MemAccPredicate];
    }

    void
    setMemAccPredicate(bool val) override
    {
        instFlags[MemAccPredicate] = val;
    }

    /** Sets the thread id. */
    void setTid(ThreadID tid) { threadNumber = tid; }

    /** Sets the pointer to the thread state. */
    void setThreadState(ThreadState *state) { thread = state; }

    /** Returns the thread context. */
    gem5::ThreadContext *tcBase() const override { return thread->getTC(); }

  public:
    /** Is this instruction's memory access strictly ordered? */
    bool strictlyOrdered() const { return instFlags[IsStrictlyOrdered]; }
    void strictlyOrdered(bool so) { instFlags[IsStrictlyOrdered] = so; }

    /** Has this instruction generated a memory request. */
    bool hasRequest() const { return instFlags[ReqMade]; }
    /** Assert this instruction has generated a memory request. */
    void setRequest() { instFlags[ReqMade] = true; }

    /** Returns iterator to this instruction in the list of all insts. */
    ListIt &getInstListIt() { return instListIt; }

    /** Sets iterator for this instruction in the list of all insts. */
    void setInstListIt(ListIt _instListIt) { instListIt = _instListIt; }

  public:
    /** Returns the number of consecutive store conditional failures. */
    unsigned int
    readStCondFailures() const override
    {
        return thread->storeCondFailures;
    }

    /** Sets the number of consecutive store conditional failures. */
    void
    setStCondFailures(unsigned int sc_failures) override
    {
        thread->storeCondFailures = sc_failures;
    }

  public:
    // monitor/mwait funtions
    void
    armMonitor(Addr address) override
    {
        cpu->armMonitor(threadNumber, address);
    }
    bool
    mwait(PacketPtr pkt) override
    {
        return cpu->mwait(threadNumber, pkt);
    }
    void
    mwaitAtomic(gem5::ThreadContext *tc) override
    {
        return cpu->mwaitAtomic(threadNumber, tc, cpu->mmu);
    }
    AddressMonitor *
    getAddrMonitor() override
    {
        return cpu->getCpuAddrMonitor(threadNumber);
    }

  private:
    // hardware transactional memory
    uint64_t htmUid = -1;
    uint64_t htmDepth = 0;

    /** Garfield: MRN-predicted value snapshotted for this load. */
    RegVal _mrnPredVal = 0;

    /** Garfield: MRN forwarding path taken by this load. */
    MrnPath _mrnPath = MrnNone;

    /** Garfield MRN aliasing: the in-flight producer physreg this load
     * aliases. Also reused (dual-purpose) by the value-file rendezvous
     * model to carry a below-confidence pointer prediction
     * (MrnVfShadowPtr, see _mrnVfMode): in that case _mrnPath is left at
     * MrnNone, so renameDestRegs' destination surgery -- keyed on
     * mrnAliased(), i.e. _mrnPath == MrnAlias -- does not fire and the
     * unconsumed pointer is inert; the LSQ reads it back at writeback
     * purely to train confidence, never to enforce an alias. */
    PhysRegIdPtr _mrnAliasProducer = nullptr;

    /** Garfield MRN aliasing: producing store's sequence number. */
    InstSeqNum _mrnProducerSeq = 0;

    /** Garfield value-file rendezvous: the value-file cell this store
     *  deposited into, or this load is bound to, at rename (-1 = no
     *  binding). See mrnVfRef(). */
    int _mrnVfIdx = -1;
    uint64_t _mrnVfGen = 0;

    /** Garfield value-file rendezvous: which mode (MrnVfMode) this
     *  instruction's value-file interaction took; MrnVfNone if the model
     *  made no binding for it. */
    uint8_t _mrnVfMode = MrnVfNone;

    /** Garfield: memory-system level that served this load (MemSrcLevel).
     *  See memSrcLevel(). */
    uint8_t _memSrcLevel = MemSrcUnknown;

    /** Garfield value-file rendezvous: snapshotted value for a
     *  below-confidence shadow prediction (MrnVfShadowValue). See
     *  mrnVfShadowVal(). */
    RegVal _mrnVfShadowVal = 0;

    /** Garfield VP: value-predicted value consumed at rename. */
    RegVal _vpPredVal = 0;

    /** Garfield VP: fetch-time {ghr, path} history snapshot for
     *  history-aware predictors. See vpHistSnap(). */
    VpHistSnapshot _vpHistSnap;

    /** Garfield VP: opaque provider token stamped by predict(). See
     *  vpToken(). */
    uint64_t _vpToken = 0;

  public:
    // Value -1 indicates that particular phase
    // hasn't happened (yet).
    /** Tick records used for the pipeline activity viewer. */
    Tick fetchTick = -1;      // instruction fetch is completed.
    int32_t decodeTick = -1;  // instruction enters decode phase
    int32_t renameTick = -1;  // instruction enters rename phase
    int32_t renameEndTick = -1; // instruction exits rename phase
    int32_t dispatchTick = -1;
    int32_t issueTick = -1;
    int32_t completeTick = -1;
    int32_t commitTick = -1;
    int32_t storeTick = -1;

    /* Values used by LoadToUse stat */
    Tick firstIssue = -1;
    Tick lastWakeDependents = -1;

    /** Reads a misc. register, including any side-effects the read
     * might have as defined by the architecture.
     */
    RegVal
    readMiscReg(int misc_reg) override
    {
        return cpu->readMiscReg(misc_reg, threadNumber);
    }

    /** Sets a misc. register, including any side-effects the write
     * might have as defined by the architecture.
     */
    void
    setMiscReg(int misc_reg, RegVal val) override
    {
        /** Writes to misc. registers are recorded and deferred until the
         * commit stage, when updateMiscRegs() is called. First, check if
         * the misc reg has been written before and update its value to be
         * committed instead of making a new entry. If not, make a new
         * entry and record the write.
         */
        for (auto &idx: _destMiscRegIdx) {
            if (idx == misc_reg)
                return;
        }

        _destMiscRegIdx.push_back(misc_reg);
        _destMiscRegVal.push_back(val);
    }

    /** Reads a misc. register, including any side-effects the read
     * might have as defined by the architecture.
     */
    RegVal
    readMiscRegOperand(const StaticInst *si, int idx) override
    {
        const RegId& reg = si->srcRegIdx(idx);
        assert(reg.is(MiscRegClass));
        return cpu->readMiscReg(reg.index(), threadNumber);
    }

    /** Sets a misc. register, including any side-effects the write
     * might have as defined by the architecture.
     */
    void
    setMiscRegOperand(const StaticInst *si, int idx, RegVal val) override
    {
        const RegId& reg = si->destRegIdx(idx);
        assert(reg.is(MiscRegClass));
        setMiscReg(reg.index(), val);

        /** If the MiscReg allows non-serializing updates, we
         * can update the value immediately without waiting
         * for commit, but only if the instruction is non
         * speculative
         */
        if (!reg.regClass().isSerializing(reg)) {
            assert(isNonSpeculative());

            bool no_squash_from_TC = thread->noSquashFromTC;
            thread->noSquashFromTC = true;

            /** Update the architectural state with the new value */
            cpu->setMiscReg(reg.index(), val, threadNumber);

            thread->noSquashFromTC = no_squash_from_TC;
        }
    }

    /** Called at the commit stage to update the misc. registers. */
    void
    updateMiscRegs()
    {
        // @todo: Pretty convoluted way to avoid squashing from happening when
        // using the TC during an instruction's execution (specifically for
        // instructions that have side-effects that use the TC).  Fix this.
        // See cpu/o3/dyn_inst_impl.hh.
        bool no_squash_from_TC = thread->noSquashFromTC;
        thread->noSquashFromTC = true;

        for (int i = 0; i < _destMiscRegIdx.size(); i++)
            cpu->setMiscReg(
                _destMiscRegIdx[i], _destMiscRegVal[i], threadNumber);

        thread->noSquashFromTC = no_squash_from_TC;
    }

    void
    forwardOldRegs()
    {

        for (int idx = 0; idx < numDestRegs(); idx++) {
            PhysRegIdPtr prev_phys_reg = prevDestIdx(idx);
            const RegId& original_dest_reg = staticInst->destRegIdx(idx);
            const auto bytes = original_dest_reg.regClass().regBytes();

            // Registers which aren't renamed don't need to be forwarded.
            if (!original_dest_reg.isRenameable())
                continue;

            if (bytes == sizeof(RegVal)) {
                setRegOperand(staticInst.get(), idx,
                        cpu->getReg(prev_phys_reg, threadNumber));
            } else {
                const size_t size = original_dest_reg.regClass().regBytes();
                auto val = std::make_unique<uint8_t[]>(size);
                cpu->getReg(prev_phys_reg, val.get(), threadNumber);
                setRegOperand(staticInst.get(), idx, val.get());
            }
        }
    }
    /** Traps to handle specified fault. */
    void trap(const Fault &fault);

  public:

    // The register accessor methods provide the index of the
    // instruction's operand (e.g., 0 or 1), not the architectural
    // register index, to simplify the implementation of register
    // renaming.  We find the architectural register index by indexing
    // into the instruction's own operand index table.  Note that a
    // raw pointer to the StaticInst is provided instead of a
    // ref-counted StaticInstPtr to redice overhead.  This is fine as
    // long as these methods don't copy the pointer into any long-term
    // storage (which is pretty hard to imagine they would have reason
    // to do).

    RegVal
    getRegOperand(const StaticInst *si, int idx) override
    {
        const PhysRegIdPtr reg = renamedSrcIdx(idx);
        if (reg->is(InvalidRegClass))
            return 0;
        return cpu->getReg(reg, threadNumber);
    }

    void
    getRegOperand(const StaticInst *si, int idx, void *val) override
    {
        const PhysRegIdPtr reg = renamedSrcIdx(idx);
        if (reg->is(InvalidRegClass))
            return;
        cpu->getReg(reg, val, threadNumber);
    }

    void *
    getWritableRegOperand(const StaticInst *si, int idx) override
    {
        return cpu->getWritableReg(renamedDestIdx(idx), threadNumber);
    }

    /** @todo: Make results into arrays so they can handle multiple dest
     *  registers.
     */
    void
    setRegOperand(const StaticInst *si, int idx, RegVal val) override
    {
        const PhysRegIdPtr reg = renamedDestIdx(idx);
        if (reg->is(InvalidRegClass))
            return;
        cpu->setReg(reg, val, threadNumber);
        setResult(reg->regClass(), val);
    }

    void
    setRegOperand(const StaticInst *si, int idx, const void *val) override
    {
        const PhysRegIdPtr reg = renamedDestIdx(idx);
        if (reg->is(InvalidRegClass))
            return;
        cpu->setReg(reg, val, threadNumber);
        setResult(reg->regClass(), val);
    }
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_DYN_INST_HH__
