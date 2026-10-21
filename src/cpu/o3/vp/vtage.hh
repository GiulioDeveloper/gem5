#ifndef __CPU_O3_VP_VTAGE_HH__
#define __CPU_O3_VP_VTAGE_HH__

#include <optional>

#include "base/random.hh"
#include "base/statistics.hh"
#include "base/types.hh"
#include "cpu/o3/vp/base.hh"
#include "cpu/o3/vp/vtage_tables.hh"

namespace gem5
{

struct VtageVPParams;

namespace o3
{

/**
 * Garfield VP: the VTAGE value predictor (Perais & Seznec, HPCA-20
 * 2014) -- indexes values by PC *and* global branch/path history, so
 * values that change in correlation with control flow become
 * predictable instead of merely suppressed (see
 * docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md). A thin
 * SimObject wrapper over the params-free VtageTables
 * (vtage_tables.hh), plus per-component/FPC stats. trainsAtCommit()
 * and usesHistory() are both true -- see base.hh/the design doc's
 * "Verify"/"Train" sections for why VTAGE needs the commit-time
 * trainer and the framework's speculative history subsystem, unlike
 * LastValueVP.
 */
class VtageVP : public BaseValuePredictor
{
  public:
    VtageVP(const VtageVPParams &p);

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
    /** VTAGE's only randomness source: FPC gate draws and allocation-
     *  candidate choice, both consumed through the injected
     *  std::function<double()> below the table takes. Standard gem5
     *  idiom for a params-free predictor core taking an injected RNG
     *  (mirrors src/cpu/pred/tage.hh's `Random::RandomPtr rng =
     *  Random::genRandom();` precedent): one instance per SimObject,
     *  seeded from the global seed, so --rng-seed and any mid-run
     *  reseedAll() cover VTAGE exactly like every other randomized
     *  predictor in the tree. GTests instead inject a deterministic
     *  functor directly into VtageTables, bypassing this member
     *  entirely. */
    Random::RandomPtr rng = Random::genRandom();

    /** Adapts `rng` to VtageTables's std::function<double()> contract
     *  (a draw uniform on [0, 1)). `random<uint32_t>()` draws
     *  uniformly from the full 32-bit range (base/random.hh:
     *  `gen() % numeric_limits<T>::max()`); dividing by 2^32 (not
     *  2^32 - 1, and not the `max()` the draw is itself reduced
     *  modulo) keeps the quotient strictly less than 1.0 -- a
     *  returned exactly-1.0 would silently never fire the rarest FPC
     *  gate (v = 1/32) and could push the allocation-candidate index
     *  `rng() * qualifying.size()` one past the end. ~32 bits of
     *  mantissa precision is ample against the coarsest configured
     *  FPC probability (1/32) or the widest realistic allocation
     *  candidate count (<= numTagged <= 7). */
    std::function<double()> tableRng;

    VtageTables table;

    struct VtageStats : public statistics::Group
    {
        VtageStats(statistics::Group *parent, unsigned numComponents);

        /** Rename-time lookups, by resolved provider (biased rank -
         *  1: index 0 = VT0, 1..6 = VT1..VT6). Includes below-
         *  threshold lookups (no value delivered). */
        statistics::Vector providerLookups;
        /** Commit-time train() calls whose provider verified correct
         *  (CorrectInc or CorrectSat), by provider. */
        statistics::Vector providerCorrect;
        /** Commit-time train() calls whose provider verified wrong
         *  (WrongReset or WrongValOverwrite), by provider. */
        statistics::Vector providerWrong;
        /** Wrong-training allocations into a higher-rank component. */
        statistics::Scalar allocations;
        /** Wrong-training allocation probes that found no u == 0
         *  candidate above the provider (aging fired, no allocation:
         *  the design doc's "allocation-failures (u-aging events)"). */
        statistics::Scalar allocationFailures;
        /** Verify-site corrective resets (trainAtCommit's no-livelock
         *  exception, base.hh's correctiveReset()) whose token still
         *  matched a live provider -- the base class's
         *  correctiveResetStale counts the complementary stale case. */
        statistics::Scalar correctiveResets;
        /** train() calls whose token was stale (reallocated in
         *  flight) or absent (token == 0: MRN-claimed loads, which
         *  bypass predict()), recomputing the provider by longest
         *  match instead of trusting the token. */
        statistics::Scalar tokenStaleRecomputes;
        /** FPC forward transitions (c -> c+1) that fired on a correct
         *  update. */
        statistics::Scalar fpcFired;
        /** FPC forward transitions that were attempted (the counter
         *  was below its saturating max) but did not fire, on a
         *  correct update. VtageTrainOutcome::CorrectSat alone
         *  conflates this with "already saturated, no attempt was
         *  possible" -- distinguished here via
         *  VtageTables::peekProvider()'s pre-train confidence peek
         *  (vtage_tables.hh), a read-only addition to the core kept
         *  separate from train()'s existing, GTest-pinned outcome
         *  semantics. peekProvider falls back to the same
         *  findProvider() recompute train() uses on a stale or absent
         *  token, so the fired/suppressed split is exact. */
        statistics::Scalar fpcSuppressed;
    } vtageStats;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_VTAGE_HH__
