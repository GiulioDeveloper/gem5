#include "cpu/o3/vp/eves.hh"

#include <algorithm>
#include <limits>

#include "base/intmath.hh"
#include "base/logging.hh"
#include "cpu/o3/vp/eves_arbiter.hh"
#include "cpu/o3/vp/vp_key.hh"
#include "params/EvesVP.hh"

namespace gem5
{
namespace o3
{

namespace
{

/** VpClassifierInfo::memSrcLevel -> EVtageMemLevel; verbatim copy of
 *  evtage.cc's anonymous-namespace helper of the same name (design doc
 *  docs/legacy-log/superpowers/specs/2026-08-04-evtage-design.md, "Latency-
 *  classifier mapping"). Duplicated rather than shared because
 *  evtage.cc's anonymous namespace is file-local. */
EVtageMemLevel
toMemLevel(uint8_t raw)
{
    switch (raw) {
        case 0:
            return EVtageMemLevel::Stlf;
        case 1:
            return EVtageMemLevel::L1d;
        case 2:
            return EVtageMemLevel::L2;
        default:
            return EVtageMemLevel::Mem;
    }
}

/** VpClassifierInfo -> EVtageClassifier; verbatim copy of evtage.cc's
 *  anonymous-namespace helper of the same name. */
EVtageClassifier
toEVtageClassifier(const VpClassifierInfo &c, RegVal actualValue)
{
    EVtageClassifier ec;
    ec.isLoad = (c.instClass == VpInstClass::Load);
    ec.memLevel = toMemLevel(c.memSrcLevel);
    ec.fastInst = (c.instClass == VpInstClass::Alu);
    ec.slowInst = (c.instClass == VpInstClass::SlowAlu);
    ec.intSrcCount = c.nbOperand;
    ec.isIndirectCall = (c.instClass == VpInstClass::IndirectCall);
    ec.value = actualValue;
    ec.deliveredCorrect = c.deliveredCorrect;
    return ec;
}

/** VpClassifierInfo -> EStrideClassifier: the four CVP latency
 *  predicates via the same memSrcLevel mapping E-VTAGE uses (our
 *  hierarchy has no distinct LLC row, so a load's notLlcMiss and
 *  notL2Miss always agree -- the CVP LLC-hit allocation arm is
 *  unreachable, spec S3.4), the allocation-class ladder, and the two
 *  flag-keyed gates. */
EStrideClassifier
toEStrideClassifier(const VpClassifierInfo &c, bool stride_predicted)
{
    EStrideClassifier sc;
    sc.isLoad = (c.instClass == VpInstClass::Load);
    if (sc.isLoad) {
        const EVtageMemLevel lvl = toMemLevel(c.memSrcLevel);
        sc.notLlcMiss = lvl != EVtageMemLevel::Mem;
        sc.notL2Miss = lvl != EVtageMemLevel::Mem;
        sc.notL1Miss =
            lvl == EVtageMemLevel::L1d || lvl == EVtageMemLevel::Stlf;
        sc.fastInst = lvl == EVtageMemLevel::Stlf;
    } else {
        // Non-loads: all latency terms true. fastInst here is CVP's
        // MFASTINST (latency < 3): every non-load class except the
        // multi-cycle SlowAlu group executes in under 3 cycles, so
        // alu, store, and undef all qualify. (Deliberately NOT
        // EVtageClassifier::fastInst, which means genuine IntAlu --
        // see EStrideClassifier's doc comment in estride_table.hh.)
        sc.notLlcMiss = sc.notL2Miss = sc.notL1Miss = true;
        sc.fastInst = c.instClass != VpInstClass::SlowAlu;
    }
    switch (c.instClass) {
        case VpInstClass::Load:
            sc.allocClass = EStrideAllocClass::Load;
            break;
        case VpInstClass::Alu:
        case VpInstClass::Store:
            sc.allocClass = EStrideAllocClass::AluOrStore;
            break;
        case VpInstClass::SlowAlu:
            sc.allocClass = EStrideAllocClass::FpOrSlowAlu;
            break;
        default: // IndirectCall, Undef: absent from the CVP switch
            sc.allocClass = EStrideAllocClass::Never;
            break;
    }
    sc.deliveredCorrect = c.deliveredCorrect;
    sc.stridePredicted = stride_predicted;
    return sc;
}

} // anonymous namespace

EvesVP::EvesVP(const EvesVPParams &p)
    : BaseValuePredictor(p),
      tableRng([this]() {
          return static_cast<double>(rng->random<uint32_t>()) /
                 (static_cast<double>(std::numeric_limits<uint32_t>::max()) +
                  1.0);
      }),
      overwriteRequiresConfidence(p.vtageOverwriteRequiresConfidence),
      stride(tableRng),
      vtage(EVtageConfig{p.baseEntries, p.taggedEntries, p.numTagged,
                         p.historyLengths, p.baseTagBits, p.confBits,
                         p.confThreshold, p.uBits, p.tickMax,
                         p.burstGuardWindow, p.historyPathBits},
            tableRng),
      evesStats(this)
{
    // The three EVES-only token flag bits (bits 63/62/61) must never
    // collide with EVtageTables's own packed token, which occupies the
    // low bits (evtage_tables.cc's packToken(): rank (4b, biased +1) +
    // way (1b) + index (idx_bits) + tag (20b)). idx_bits is
    // recomputed here from the params rather than read off the table
    // (a private implementation detail) -- ceilLog2 rather than
    // EVtageTables's internal floorLog2 because baseEntries/2 and
    // taggedEntries are validated powers of two by EVtageTables's own
    // ctor, where the two agree; ceilLog2 is the safe choice for this
    // independent sanity recomputation.
    const unsigned idxBits =
        std::max(ceilLog2(p.baseEntries / 2), ceilLog2(p.taggedEntries));
    fatal_if(4 + 1 + idxBits + 20 > 61,
             "EVES token geometry (E-VTAGE rank 4b + way 1b + index %ub "
             "+ tag 20b = %ub) leaves no room below bit 61 for the "
             "three EVES flag bits",
             idxBits, 4 + 1 + idxBits + 20);
}

VpPredictResult
EvesVP::predictImpl(const VpLookupContext &ctx)
{
    const uint64_t key = vpKey(ctx.pc, ctx.upc);
    const unsigned inflight = inflightCount(key);
    const EStrideLookup s = stride.lookup(key, inflight);
    const EVtageLookup r = vtage.lookup(ctx.pc, ctx.upc, ctx.hist);
    const unsigned last_misp = renamedInsts(ctx.tid) - lastWrongMark[ctx.tid];
    const bool blackout = vtage.burstGuardSuppresses(last_misp);

    EvesArbiterIn in;
    in.stridePredicted = s.predicted;
    in.strideValue = s.value;
    in.vtageHit = r.hit;
    in.vtageConfident = r.confident;
    in.vtageValue = r.value;
    in.blackoutActive = blackout;
    in.overwriteRequiresConfidence = overwriteRequiresConfidence;
    const EvesArbiterOut a = evesArbitrate(in);

    if (s.hit) {
        evesStats.strideLookupHits++;
    }
    if (s.predicted) {
        evesStats.stridePredictions++;
        evesStats.strideInflightAtPredict.sample(inflight);
        if (a.deliveredByVtage) {
            evesStats.strideOverwrittenByVtage++;
            if (!r.confident) {
                evesStats.strideOverwrittenLowConf++;
            }
        }
    }
    if (s.blockedBySafeStride) {
        evesStats.safeStrideBlocked++;
    }
    if (blackout && r.hit) {
        evesStats.blackoutSuppressed++;
    }
    if (a.value) {
        if (a.deliveredByVtage) {
            evesStats.suppliedByVtage++;
        } else {
            evesStats.suppliedByStride++;
        }
    }

    uint64_t token = r.token;
    panic_if(token & TokenFlagMask,
             "EVtage token collides with EVES flag bits");
    if (a.stridePredicted) {
        token |= TokenStridePredicted;
    }
    if (a.vtageConfident) {
        token |= TokenVtageConfident;
    }
    if (a.deliveredByVtage) {
        token |= TokenDeliveredByVtage;
    }
    return {a.value, token};
}

void
EvesVP::trainImpl(const VpLookupContext &ctx, RegVal actualValue,
                  uint64_t token, const VpClassifierInfo &classifier)
{
    const uint64_t vtage_token = token & ~TokenFlagMask;
    const bool stride_predicted = token & TokenStridePredicted;

    const EVtageClassifier ec = toEVtageClassifier(classifier, actualValue);
    vtage.train(ctx.pc, ctx.upc, ctx.hist, vtage_token, ec);

    const uint64_t key = vpKey(ctx.pc, ctx.upc);
    const EStrideClassifier sc =
        toEStrideClassifier(classifier, stride_predicted);
    const auto outcomes = stride.train(key, actualValue, sc);
    for (const EStrideTrainOutcome o : outcomes) {
        switch (o) {
            case EStrideTrainOutcome::ConfInc:
                evesStats.strideConfGateFired++;
                break;
            case EStrideTrainOutcome::ConfHeld:
                evesStats.strideConfGateSuppressed++;
                break;
            case EStrideTrainOutcome::UInc:
            case EStrideTrainOutcome::UHeld:
                break;
            case EStrideTrainOutcome::UJamSaturated:
                evesStats.strideUJams++;
                break;
            case EStrideTrainOutcome::MispredictDecay:
                evesStats.strideMispredictDecay++;
                break;
            case EStrideTrainOutcome::MispredictCollapse:
                evesStats.strideMispredictCollapse++;
                break;
            case EStrideTrainOutcome::StrideSet:
                evesStats.strideSet++;
                break;
            case EStrideTrainOutcome::SentinelDemoted:
                evesStats.sentinelDemotions++;
                break;
            case EStrideTrainOutcome::AllocatedConfZeroVictim:
                evesStats.strideAllocPass1++;
                evesStats.strideAllocsByClass[static_cast<unsigned>(
                    sc.allocClass)]++;
                break;
            case EStrideTrainOutcome::AllocatedUZeroVictim:
                evesStats.strideAllocPass2++;
                evesStats.strideAllocsByClass[static_cast<unsigned>(
                    sc.allocClass)]++;
                break;
            case EStrideTrainOutcome::AllocAged:
                evesStats.strideAllocAged++;
                break;
            case EStrideTrainOutcome::AllocAgeHeld:
                break;
            case EStrideTrainOutcome::AllocDrawRefused:
                evesStats.strideAllocDrawRefused++;
                break;
            case EStrideTrainOutcome::AllocSkippedDeliveredCorrect:
                evesStats.strideAllocSkippedCovered++;
                break;
            case EStrideTrainOutcome::SafeStrideCredited:
                evesStats.safeStrideCredits++;
                break;
        }
    }

    if (classifier.deliveredCorrect) {
        if (token & TokenDeliveredByVtage) {
            evesStats.deliveredCorrectByVtage++;
        } else {
            evesStats.deliveredCorrectByStride++;
        }
    }
}

bool
EvesVP::correctiveResetImpl(uint64_t token)
{
    if (token & TokenStridePredicted) {
        if (stride.safeStridePenalty()) {
            evesStats.safeStrideNegEpisodes++;
        }
    }
    if (token & TokenVtageConfident) {
        // No ThreadID reaches this site (the interface gap
        // evtage.hh's lastWrongMark comment documents): reset every
        // thread's mark together, as E-VTAGE does.
        for (ThreadID tid = 0; tid < MaxThreads; tid++) {
            lastWrongMark[tid] = renamedInsts(tid);
        }
        evesStats.wrongMarkResets++;
    }
    if (token & TokenDeliveredByVtage) {
        evesStats.deliveredWrongByVtage++;
        const bool live = vtage.correctivePunish(token & ~TokenFlagMask);
        if (live) {
            evesStats.vtageCorrectivePunishes++;
        }
        return live;
    }
    // Stride supplied the wrong value: SafeStride is the entire
    // corrective mechanism (spec S6) -- the VTAGE entry is left
    // alone, and no staleness question was asked, so report live.
    evesStats.deliveredWrongByStride++;
    return true;
}

EvesVP::EvesStats::EvesStats(statistics::Group *parent)
    : statistics::Group(parent),
      ADD_STAT(suppliedByStride, statistics::units::Count::get(),
               "Composed predictions delivered with the stride "
               "table's value (post-arbitration)"),
      ADD_STAT(suppliedByVtage, statistics::units::Count::get(),
               "Composed predictions delivered with the E-VTAGE "
               "value (post-arbitration)"),
      ADD_STAT(strideLookupHits, statistics::units::Count::get(),
               "Rename-time E-Stride lookups whose key tag-matched"),
      ADD_STAT(stridePredictions, statistics::units::Count::get(),
               "Rename-time E-Stride lookups that passed the predict "
               "gate, before arbitration"),
      ADD_STAT(strideInflightAtPredict, statistics::units::Count::get(),
               "Distribution of the in-flight occurrence count at "
               "each stride-predicting lookup"),
      ADD_STAT(strideOverwrittenByVtage, statistics::units::Count::get(),
               "Stride predictions the composed result overwrote "
               "with the E-VTAGE value (the ratified clobber, design "
               "doc S5)"),
      ADD_STAT(strideOverwrittenLowConf, statistics::units::Count::get(),
               "Subset of strideOverwrittenByVtage where the "
               "overwriting E-VTAGE value was below confidence"),
      ADD_STAT(safeStrideBlocked, statistics::units::Count::get(),
               "Rename-time E-Stride lookups where the predict gate "
               "would have fired but SafeStride was negative"),
      ADD_STAT(safeStrideNegEpisodes, statistics::units::Count::get(),
               "Verify-wrong SafeStride penalty applications that "
               "crossed the predict gate shut this call"),
      ADD_STAT(safeStrideCredits, statistics::units::Count::get(),
               "Commit-train SafeStride +4/+8 credit applications"),
      ADD_STAT(strideConfGateFired, statistics::units::Count::get(),
               "E-Stride one-step-match confidence-increment draws "
               "that fired"),
      ADD_STAT(strideConfGateSuppressed, statistics::units::Count::get(),
               "E-Stride one-step-match confidence-increment draws "
               "attempted but suppressed"),
      ADD_STAT(strideUJams, statistics::units::Count::get(),
               "E-Stride one-step matches whose usefulness-increment "
               "draw jammed u to 3 on crossing ConfThreshold"),
      ADD_STAT(strideMispredictDecay, statistics::units::Count::get(),
               "E-Stride one-step mismatches that decayed confidence "
               "only"),
      ADD_STAT(strideMispredictCollapse, statistics::units::Count::get(),
               "E-Stride one-step mismatches that collapsed "
               "confidence and usefulness to zero"),
      ADD_STAT(strideSet, statistics::units::Count::get(),
               "E-Stride first-occurrence trainings that learned a "
               "nonzero, in-range stride"),
      ADD_STAT(sentinelDemotions, statistics::units::Count::get(),
               "E-Stride first-occurrence trainings demoted to the "
               "0xffff sentinel stride"),
      ADD_STAT(strideAllocPass1, statistics::units::Count::get(),
               "E-Stride allocations that claimed a conf == 0 "
               "victim"),
      ADD_STAT(strideAllocPass2, statistics::units::Count::get(),
               "E-Stride allocations that claimed a u == 0 victim"),
      ADD_STAT(strideAllocAged, statistics::units::Count::get(),
               "E-Stride allocation attempts where both victim "
               "passes failed and the last-probed way's u was aged "
               "down"),
      ADD_STAT(strideAllocDrawRefused, statistics::units::Count::get(),
               "E-Stride allocation attempts refused by the "
               "class/latency draw"),
      ADD_STAT(strideAllocSkippedCovered, statistics::units::Count::get(),
               "E-Stride allocations skipped because the instruction "
               "was already delivered correct by E-VTAGE"),
      ADD_STAT(strideAllocsByClass, statistics::units::Count::get(),
               "E-Stride victim allocations (pass 1 + pass 2), by "
               "the classifying instruction's allocation class"),
      ADD_STAT(deliveredCorrectByStride, statistics::units::Count::get(),
               "Commit-train verifies that verified correct and were "
               "supplied by the stride table"),
      ADD_STAT(deliveredCorrectByVtage, statistics::units::Count::get(),
               "Commit-train verifies that verified correct and were "
               "supplied by E-VTAGE"),
      ADD_STAT(deliveredWrongByStride, statistics::units::Count::get(),
               "Verify-wrong events supplied by the stride table"),
      ADD_STAT(deliveredWrongByVtage, statistics::units::Count::get(),
               "Verify-wrong events supplied by E-VTAGE"),
      ADD_STAT(vtageCorrectivePunishes, statistics::units::Count::get(),
               "Verify-wrong E-VTAGE correctivePunish() calls that "
               "found a still-live provider (subset of "
               "deliveredWrongByVtage)"),
      ADD_STAT(wrongMarkResets, statistics::units::Count::get(),
               "Verify-wrong events that reset every thread's "
               "lastWrongMark"),
      ADD_STAT(blackoutSuppressed, statistics::units::Count::get(),
               "Rename-time lookups where the burst-guard blackout "
               "suppressed an E-VTAGE tag hit's contribution (zero "
               "when burstGuardWindow == 0)")
{
    static const char *alloc_class_names[] = {"aluOrStore", "fpOrSlowAlu",
                                              "load", "never"};
    strideAllocsByClass.init(4).flags(statistics::total);
    for (int i = 0; i < 4; i++) {
        strideAllocsByClass.subname(i, alloc_class_names[i]);
    }
    strideInflightAtPredict.init(8);
}

} // namespace o3
} // namespace gem5
