#ifndef __CPU_O3_VP_EVES_HH__
#define __CPU_O3_VP_EVES_HH__

#include <cstdint>

#include "base/random.hh"
#include "base/statistics.hh"
#include "base/types.hh"
#include "cpu/o3/limits.hh"
#include "cpu/o3/vp/base.hh"
#include "cpu/o3/vp/estride_table.hh"
#include "cpu/o3/vp/evtage_tables.hh"

namespace gem5
{

struct EvesVPParams;

namespace o3
{

/**
 * Garfield VP: EVES, the composed value predictor (Seznec, CVP-1 2018
 * EVES submission) -- E-VTAGE (evtage_tables.hh) and E-Stride
 * (estride_table.hh) arbitrated per the CVP-1 source's write-order
 * mechanism (design doc docs/legacy-log/superpowers/specs/2026-08-14-estride-
 * design.md, "Arbitration and token"): E-Stride predicts first, then
 * an E-VTAGE tag hit outside the post-misprediction blackout
 * overwrites the value even below E-VTAGE confidence -- delivery
 * still requires a component flag. `evesArbitrate()` (eves_arbiter.hh)
 * is the pure helper that implements this cross product; this class
 * owns both component tables, translates the framework's classifier
 * context into each core's own shape, and routes verify/train calls
 * per the spec's S6 routing table.
 */
class EvesVP : public BaseValuePredictor
{
  public:
    EvesVP(const EvesVPParams &p);

    bool
    trainsAtCommit() const override
    {
        return true;
    }

    bool
    usesHistory() const override
    {
        return true;
    }

    bool
    usesInflightCounts() const override
    {
        return true;
    }

  protected:
    VpPredictResult predictImpl(const VpLookupContext &ctx) override;
    void trainImpl(const VpLookupContext &ctx, RegVal actualValue,
                   uint64_t token,
                   const VpClassifierInfo &classifier) override;
    bool correctiveResetImpl(uint64_t token) override;

  private:
    /** Token high-bit flags (design doc S5): stripped (via
     *  TokenFlagMask) before any call into EVtageTables, whose own
     *  packed token occupies the low bits. The ctor's fatal_if
     *  requires the packed-token width to stay <= 61 bits so these
     *  three flag bits can never collide with a large-table
     *  configuration. */
    static constexpr uint64_t TokenStridePredicted = 1ULL << 63;
    static constexpr uint64_t TokenVtageConfident = 1ULL << 62;
    static constexpr uint64_t TokenDeliveredByVtage = 1ULL << 61;
    static constexpr uint64_t TokenFlagMask =
        TokenStridePredicted | TokenVtageConfident | TokenDeliveredByVtage;

    /** Same injected-RNG idiom as EVtageVP/VtageVP (vtage.hh's tableRng
     *  doc comment): one Random::RandomPtr per SimObject instance, so
     *  --rng-seed/reseedAll() cover both component tables like every
     *  other randomized predictor. GTests instead inject a
     *  deterministic functor directly into EStrideTable/EVtageTables. */
    Random::RandomPtr rng = Random::genRandom();
    std::function<double()> tableRng;

    /** The composed predictor's ablation knob (design doc S5): when
     *  false (default, the CVP-1-source-verbatim mode), an E-VTAGE tag
     *  hit outside the blackout overwrites the stride value regardless
     *  of E-VTAGE confidence; when true, the overwrite additionally
     *  requires E-VTAGE confidence. */
    const bool overwriteRequiresConfidence;

    EStrideTable stride;
    EVtageTables vtage;

    /** Design doc S6's per-thread LastMispVT mark, adopted verbatim
     *  from EVtageVP (evtage.hh's lastWrongMark doc comment):
     *  renamedInsts(tid) - lastWrongMark[tid] is the elapsed window the
     *  blackout gate consults. correctiveReset() (base.hh)'s call
     *  sites carry no ThreadID, so correctiveResetImpl() resets every
     *  thread's mark together rather than only the wronged thread's --
     *  harmless for the single-threaded runs this chapter uses. Unlike
     *  EVtageVP, EVES is the guard-capable predictor: burstGuardWindow
     *  is a live, unlocked param here. */
    unsigned lastWrongMark[MaxThreads] = {};

    struct EvesStats : public statistics::Group
    {
        explicit EvesStats(statistics::Group *parent);

        /** Composed predictions delivered with the stride table's
         *  value (post-arbitration; predictImpl's a.value engaged and
         *  !a.deliveredByVtage). */
        statistics::Scalar suppliedByStride;
        /** Composed predictions delivered with the E-VTAGE value
         *  (post-arbitration; predictImpl's a.value engaged and
         *  a.deliveredByVtage). */
        statistics::Scalar suppliedByVtage;
        /** Rename-time E-Stride lookups whose key tag-matched
         *  (EStrideLookup::hit). */
        statistics::Scalar strideLookupHits;
        /** Rename-time E-Stride lookups that passed the predict gate
         *  (EStrideLookup::predicted), before arbitration. */
        statistics::Scalar stridePredictions;
        /** Distribution of the framework's in-flight occurrence count
         *  (inflightCount(key)) at each stride-predicting lookup --
         *  how many not-yet-committed occurrences of the same key the
         *  extrapolation already accounted for. */
        statistics::Histogram strideInflightAtPredict;
        /** Subset of stridePredictions the composed result overwrote
         *  with the E-VTAGE value (the ratified clobber, design doc
         *  S5). */
        statistics::Scalar strideOverwrittenByVtage;
        /** Subset of strideOverwrittenByVtage where the overwriting
         *  E-VTAGE value was below confidence (the verbatim-mode
         *  quirk: a low-confidence VTAGE value silently clobbers a
         *  confident stride value). */
        statistics::Scalar strideOverwrittenLowConf;
        /** Rename-time E-Stride lookups where the predict gate would
         *  have fired but SafeStride was negative
         *  (EStrideLookup::blockedBySafeStride). */
        statistics::Scalar safeStrideBlocked;
        /** Commit-time SafeStride verify-wrong penalty applications
         *  (correctiveResetImpl's TokenStridePredicted arm) that
         *  crossed the predict gate shut this call
         *  (EStrideTable::safeStridePenalty()'s return). */
        statistics::Scalar safeStrideNegEpisodes;
        /** Commit-train SafeStride +4/+8 credit applications
         *  (EStrideTrainOutcome::SafeStrideCredited). */
        statistics::Scalar safeStrideCredits;
        /** E-Stride one-step-match confidence-increment draws that
         *  fired (EStrideTrainOutcome::ConfInc). */
        statistics::Scalar strideConfGateFired;
        /** E-Stride one-step-match confidence-increment draws
         *  attempted but suppressed (EStrideTrainOutcome::ConfHeld). */
        statistics::Scalar strideConfGateSuppressed;
        /** E-Stride one-step matches whose usefulness-increment draw
         *  jammed u to 3 on crossing ConfThreshold
         *  (EStrideTrainOutcome::UJamSaturated). */
        statistics::Scalar strideUJams;
        /** E-Stride one-step mismatches that decayed confidence
         *  (EStrideTrainOutcome::MispredictDecay). */
        statistics::Scalar strideMispredictDecay;
        /** E-Stride one-step mismatches that collapsed confidence and
         *  usefulness to zero (EStrideTrainOutcome::
         *  MispredictCollapse). */
        statistics::Scalar strideMispredictCollapse;
        /** E-Stride first-occurrence trainings that learned a nonzero,
         *  in-range stride (EStrideTrainOutcome::StrideSet). */
        statistics::Scalar strideSet;
        /** E-Stride first-occurrence trainings demoted to the
         *  0xffff sentinel stride (EStrideTrainOutcome::
         *  SentinelDemoted). */
        statistics::Scalar sentinelDemotions;
        /** E-Stride allocations that claimed a conf == 0 victim
         *  (EStrideTrainOutcome::AllocatedConfZeroVictim). */
        statistics::Scalar strideAllocPass1;
        /** E-Stride allocations that claimed a u == 0 victim
         *  (EStrideTrainOutcome::AllocatedUZeroVictim). */
        statistics::Scalar strideAllocPass2;
        /** E-Stride allocation attempts where both victim passes
         *  failed and the last-probed way's u was aged down
         *  (EStrideTrainOutcome::AllocAged). */
        statistics::Scalar strideAllocAged;
        /** E-Stride allocation attempts refused by the class/latency
         *  draw (EStrideTrainOutcome::AllocDrawRefused). */
        statistics::Scalar strideAllocDrawRefused;
        /** E-Stride allocations skipped because the instruction was
         *  already delivered correct by E-VTAGE
         *  (EStrideTrainOutcome::AllocSkippedDeliveredCorrect). */
        statistics::Scalar strideAllocSkippedCovered;
        /** By allocation class: EStrideTrainOutcome::
         *  AllocatedConfZeroVictim/AllocatedUZeroVictim, indexed by
         *  the classifying instruction's EStrideAllocClass. */
        statistics::Vector strideAllocsByClass;
        /** Commit-train verifies that verified correct and were
         *  supplied by the stride table (token & TokenStridePredicted,
         *  !TokenDeliveredByVtage, classifier.deliveredCorrect). */
        statistics::Scalar deliveredCorrectByStride;
        /** Commit-train verifies that verified correct and were
         *  supplied by E-VTAGE (token & TokenDeliveredByVtage,
         *  classifier.deliveredCorrect). */
        statistics::Scalar deliveredCorrectByVtage;
        /** Verify-wrong events supplied by the stride table (token &
         *  TokenStridePredicted, !TokenDeliveredByVtage). */
        statistics::Scalar deliveredWrongByStride;
        /** Verify-wrong events supplied by E-VTAGE (token &
         *  TokenDeliveredByVtage). */
        statistics::Scalar deliveredWrongByVtage;
        /** Verify-wrong events whose EVtageTables::correctivePunish()
         *  call found a still-live provider (subset of
         *  deliveredWrongByVtage; the complement is counted by the
         *  base class's correctiveResetStale). */
        statistics::Scalar vtageCorrectivePunishes;
        /** Verify-wrong events that reset every thread's lastWrongMark
         *  (token & TokenVtageConfident). */
        statistics::Scalar wrongMarkResets;
        /** Rename-time lookups where the burst-guard blackout
         *  suppressed an E-VTAGE tag hit's contribution (blackout &&
         *  r.hit; zero whenever burstGuardWindow == 0). */
        statistics::Scalar blackoutSuppressed;
    } evesStats;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_EVES_HH__
