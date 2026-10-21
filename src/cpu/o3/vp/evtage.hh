#ifndef __CPU_O3_VP_EVTAGE_HH__
#define __CPU_O3_VP_EVTAGE_HH__

#include <optional>
#include <unordered_set>

#include "base/random.hh"
#include "base/statistics.hh"
#include "base/types.hh"
#include "cpu/o3/limits.hh"
#include "cpu/o3/vp/base.hh"
#include "cpu/o3/vp/evtage_tables.hh"

namespace gem5
{

struct EVtageVPParams;

namespace o3
{

/**
 * Garfield VP: the E-VTAGE value predictor (Seznec, CVP-1 2018 EVES) --
 * an iso-storage-geometry A/B of plain VTAGE's per-transition FPC
 * update policy against EVES's per-class, per-value, per-serve-level
 * probabilistic policy (design doc
 * docs/legacy-log/superpowers/specs/2026-08-04-evtage-design.md). A thin
 * SimObject wrapper over the params-free
 * EVtageTables (evtage_tables.hh) -- same structural pattern
 * as VtageVP (vtage.hh), plus classifier-context translation and the
 * expanded stat surface the design doc's "Statistics" section calls
 * for (an explicit none/rank-0 provider bucket, allocation-policy
 * bookkeeping, the deferred verify/commit punish split's pending-bit
 * lifecycle, and the burst-guard counter).
 */
class EVtageVP : public BaseValuePredictor
{
  public:
    EVtageVP(const EVtageVPParams &p);

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

  protected:
    VpPredictResult predictImpl(const VpLookupContext &ctx) override;
    void trainImpl(const VpLookupContext &ctx, RegVal actualValue,
                   uint64_t token,
                   const VpClassifierInfo &classifier) override;
    bool correctiveResetImpl(uint64_t token) override;

  private:
    /** Same injected-RNG idiom as VtageVP (vtage.hh's tableRng doc
     *  comment): one Random::RandomPtr per SimObject instance, so
     *  --rng-seed/reseedAll() cover E-VTAGE like every other
     *  randomized predictor. GTests instead inject a deterministic
     *  functor directly into EVtageTables. */
    Random::RandomPtr rng = Random::genRandom();
    std::function<double()> tableRng;

    EVtageTables table;

    /** Shadow tracking for the design doc's "Pending-bit lifecycle"
     *  (S3): correctiveResetImpl() inserts a provider's token here on
     *  a successful (live-token) verify-site punish; trainImpl()
     *  looks the token up (and erases it) to attribute the deferred
     *  remainder as pendingConsumed (a WrongOverwriteOnly outcome) or
     *  pendingDropped (a correct outcome) for the design doc's
     *  Statistics section. Tokens are provider-identity-keyed (way/
     *  index/tag), not instruction-keyed, so this exactly mirrors the
     *  core's own entry-level punishApplied/medConfPending bits --
     *  except across a reallocation of the same provider before its
     *  pending mark is consumed, where a now-unreachable token is
     *  left behind (harmless: it can only ever undercount
     *  pendingConsumed/pendingDropped by that one event, never cause
     *  a spurious attribution to some other provider's token, since
     *  packToken()'s tag field changes on reallocation). */
    std::unordered_set<uint64_t> pendingTokens;

    /** Design doc S6's per-thread LastMispVT mark: the renamedInsts()
     *  snapshot (base.hh) at the last delivered-wrong verify. Burst-
     *  guard emission suppression computes the elapsed window as
     *  renamedInsts(tid) - lastWrongMark[tid]. NOTE: correctiveReset()
     *  (base.hh)'s call sites (lsq_unit.cc/iew.cc) don't carry a
     *  thread ID, so correctiveResetImpl() resets every thread's mark
     *  together rather than only the wronged thread's -- a documented
     *  simplification, harmless while burstGuardWindow defaults to 0
     *  (off) and, on this predictor, stays locked off by the
     *  constructor's fatal_if (see evtage.cc): renamedInsts() is fed
     *  once per renamed instruction (base.hh's notifyRenamedInst()),
     *  but the guard-capable configuration lives in the EVES
     *  composition predictor. Revisit (thread the ID through
     *  correctiveReset()) before relying on burstGuardWindow > 0 in a
     *  multi-hardware-thread config. */
    unsigned lastWrongMark[MaxThreads] = {};

    struct EVtageStats : public statistics::Group
    {
        EVtageStats(statistics::Group *parent, unsigned numComponents);

        /** Rename-time lookups by resolved provider: index 0 = none
         *  (no provider -- design doc "Rank-0 peek/stat contract"),
         *  1 = VT0, 2..(1+numTagged) = VT1..VTnumTagged. Includes
         *  below-threshold lookups (no value delivered) and burst-
         *  guard-suppressed ones (the lookup still ran). */
        statistics::Vector providerLookups;
        /** Commit-time train() calls whose provider verified correct
         *  (CorrectInc or CorrectSat), by provider; index 0 stays
         *  structurally 0 (a "no provider" train never has a correct/
         *  wrong outcome -- see EVtageTrainOutcome::NoProviderTrained). */
        statistics::Vector providerCorrect;
        /** Commit-time train() calls whose provider verified wrong
         *  (WrongPunishSat/WrongPunishReset/WrongOverwriteOnly), by
         *  provider; index 0 stays structurally 0 (see above). */
        statistics::Vector providerWrong;
        /** S1's classifier-driven confidence-increment gate: fired
         *  (CorrectInc) vs attempted-but-suppressed (CorrectSat with
         *  a pre-train counter that was not already saturated) --
         *  repurposes plain VTAGE's fpcFired/fpcSuppressed pair for
         *  E-VTAGE's per-class probability policy (design doc,
         *  "Statistics"). */
        statistics::Scalar confGateFired;
        statistics::Scalar confGateSuppressed;
        /** Verify-site corrective punishes (S2) whose token still
         *  matched a live provider -- the base class's
         *  correctiveResetStale counts the complementary stale case. */
        statistics::Scalar correctiveResets;
        /** train() calls whose token was stale or absent, recomputing
         *  the provider by longest match instead. */
        statistics::Scalar tokenStaleRecomputes;
        /** Rename-time lookups where neither VT0 way tag-matched.
         *  Under this port's longest-match search order (tagged banks
         *  before the base, findProvider()), a base-tag miss is only
         *  externally observable when it coincides with a full no-
         *  provider outcome: a tagged hit preempts the base check
         *  entirely. This counter's value therefore equals
         *  noProviderLookups by construction; kept as its own named
         *  stat for parity with the design doc's Statistics list. */
        statistics::Scalar baseTagMiss;
        /** Rename-time lookups that resolved to "no provider" (S5's
         *  legal rank-0 outcome). */
        statistics::Scalar noProviderLookups;
        /** Commit-time train() calls whose token resolved (directly
         *  or via stale-token recompute) to "no provider". */
        statistics::Scalar noProviderTrains;
        /** S3 allocation-scan candidates visited and not stolen (NA,
         *  summed across every allocation attempt). */
        statistics::Scalar allocScanSteps;
        /** S3 allocation-scan candidates successfully stolen (ALL,
         *  summed; tagged-bank steals plus base-way steals). */
        statistics::Scalar allocSteals;
        /** Subset of allocSteals that landed in a VT0 base way (the
         *  "no provider" arm's dominant 7/8 sub-case; S3). */
        statistics::Scalar allocBaseWay;
        /** Zero-operand-ALU base-way steals seeded to confMax instead
         *  of the usual confMax/2 (S3's special case). */
        statistics::Scalar allocSeedSaturated;
        /** TICK aging passes (S4: every entry's nonzero u decremented,
         *  all components including base ways). */
        statistics::Scalar tickPasses;
        /** Verify-site corrective punishes that set the deferred-
         *  remainder pending bits (S3's "Pending-bit lifecycle") --
         *  equals correctiveResets (every live punish sets them). */
        statistics::Scalar pendingSet;
        /** Deferred commit-train remainders that consumed a pending
         *  mark (a WrongOverwriteOnly outcome on a previously-pending
         *  token). */
        statistics::Scalar pendingConsumed;
        /** Pending marks dropped by an intervening correct outcome on
         *  the same provider before the deferred remainder ran (S3:
         *  "a correct outcome drops them -- matching CVP's one-event
         *  semantics, no memory across events"). */
        statistics::Scalar pendingDropped;
        /** S6 burst-guard: rename-time lookups whose emission was
         *  suppressed (LastMispVT < burstGuardWindow). Zero whenever
         *  burstGuardWindow == 0 (the default). */
        statistics::Scalar burstGuardSuppressed;
    } evtageStats;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_EVTAGE_HH__
