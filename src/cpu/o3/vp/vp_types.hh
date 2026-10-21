#ifndef __CPU_O3_VP_VP_TYPES_HH__
#define __CPU_O3_VP_VP_TYPES_HH__

#include <cstdint>
#include <optional>

#include "base/types.hh"
#include "cpu/o3/vp/vp_history.hh"

namespace gem5
{
namespace o3
{

/**
 * Everything predictImpl()/trainImpl() need to look an entry up: the
 * (PC, micro-PC) pair the framework already folds via vp_key.hh, plus
 * the fetch-time history snapshot
 * (docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md,
 * "Framework API Changes"). LVP ignores hist and
 * folds pc/upc through vpKey() unchanged; VTAGE-class predictors fold
 * pc/upc with hist.{ghr,path} instead.
 */
struct VpLookupContext
{
    Addr pc;
    MicroPC upc;
    VpHistSnapshot hist;
    /** The instruction's thread (design doc docs/legacy-log/superpowers/specs/
     *  2026-08-04-evtage-design.md, S6's per-thread burst-guard
     *  counter). LVP/plain VTAGE ignore it -- same pattern as hist. */
    ThreadID tid = 0;
};

/**
 * predictImpl()'s return: an optional value to consume, plus an opaque
 * provider token. The base class stamps the token on the instruction
 * on every lookup -- even when no value is delivered (a below-
 * confidence hit) -- so trainImpl()/correctiveReset() can recover the
 * exact provider without a second table search. LVP always returns
 * token 0 (it has no provider concept to recover).
 */
struct VpPredictResult
{
    std::optional<RegVal> value;
    uint64_t token = 0;
};

/**
 * Coarse instruction-class dispatch for classifier-driven predictors
 * (E-VTAGE; design doc docs/legacy-log/superpowers/specs/2026-08-04-evtage-
 * design.md, "Class dispatch"), mirroring the shape of CVP-1 EVES's
 * own InstClass enum (Seznec, CVP-1 2018 submission source) at the
 * granularity our port can actually distinguish. Direct calls/
 * conditional branches that happen to be eligible (single scalar int
 * dest -- e.g. AArch64 BL's link-register write) get no distinct
 * arm: the raw CVP source dispatches them to deterministic-false
 * confidence/allocation gates, but EVtageClassifier
 * (evtage_tables.hh) has no field to express "always false" -- only
 * isIndirectCall's "always true" override exists. gem5 defaults
 * flag-less branches to IntAluOp, so an eligible BL classifies as
 * Alu and -- with zero integer sources -- takes the base-way
 * seed-to-7 arm, instantly predicting its constant link value
 * (declared deviation from CVP; symmetric across the A/B, since
 * plain VTAGE predicts these too, isolated to
 * this rare edge case; Undef already gets the "alu-like" probabilistic
 * treatment CVP gives its own undefInstClass).
 */
enum class VpInstClass : uint8_t
{
    Load,
    Store,
    Alu,          ///< OpClass::IntAlu.
    SlowAlu,      ///< IntMult/IntDiv/Float* -- multi-cycle.
    IndirectCall, ///< isIndirectCtrl() && isCall() (e.g. AArch64 BLR).
    Undef         ///< Everything else eligible (the CVP-style fallback).
};

/**
 * Everything a classifier-driven predictor's trainImpl() needs beyond
 * the lookup context (design doc, "Framework API Changes"): built once
 * by the base class at the train() call site from the DynInst and its
 * verify-time outcome. LVP and plain VTAGE take and ignore this
 * parameter -- same bit-identity pattern as VpLookupContext::hist.
 */
struct VpClassifierInfo
{
    VpInstClass instClass = VpInstClass::Undef;
    /** Raw DynInst::MemSrcLevel value (Stlf=0/L1D=1/L2=2/Mem=3/
     *  Unknown=4); meaningless unless instClass == Load. Carried as a
     *  raw uint8_t (rather than DynInst::MemSrcLevel) so this header
     *  stays free of a dyn_inst.hh dependency. */
    uint8_t memSrcLevel = 4;
    /** Count of integer, non-flag (non-CCRegClass/FloatRegClass/
     *  VecRegClass) source registers -- CVP's NbOperand (design doc,
     *  "Operand-count mapping"). */
    unsigned nbOperand = 0;
    /** This instruction delivered a prediction (consumed at rename)
     *  that verified correct at the writeback verify site. */
    bool deliveredCorrect = false;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_VP_TYPES_HH__
