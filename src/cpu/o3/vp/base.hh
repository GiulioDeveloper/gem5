#ifndef __CPU_O3_VP_BASE_HH__
#define __CPU_O3_VP_BASE_HH__

#include <cstdint>
#include <optional>

#include "base/statistics.hh"
#include "base/types.hh"
#include "cpu/o3/dyn_inst_ptr.hh"
#include "cpu/o3/limits.hh"
#include "cpu/o3/vp/vp_history.hh"
#include "cpu/o3/vp/vp_inflight_map.hh"
#include "cpu/o3/vp/vp_types.hh"
#include "sim/sim_object.hh"

namespace gem5
{

// Forward declaration of the generated params struct. The SimObject
// constructor stays out-of-line (in base.cc) so this header does not
// pull in the generated params/BaseValuePredictor.hh and stays cheap to
// include from pipeline code (rename/iew/lsq).
struct BaseValuePredictorParams;

namespace o3
{

/**
 * Garfield VP: algorithm-agnostic value-predictor base (design doc
 * docs/legacy-log/superpowers/specs/2026-08-02-vp-framework-design.md).
 *
 * The pipeline contract has three operations plus one reserved hook:
 *  - predict() at rename (after renameDestRegs, and only for
 *    instructions MRN did not claim): the base class alone decides
 *    eligibility and scope; a returned value has already been counted
 *    and stamped on the instruction, and the caller forwards it into
 *    the renamed destination (physreg write + scoreboard ready).
 *  - train() at writeback for every in-scope, not-already-squashed
 *    instruction -- whether or not a prediction was made, and including
 *    MRN-claimed loads: the tables stay warm regardless of predictor
 *    engagement.
 *  - verifyResult()/notifySquashed(): outcome accounting from the
 *    verify sites and the squash walks.
 * Derived predictors implement predictImpl()/trainImpl() over the
 * folded (PC, micro-PC) key (vp_key.hh) and keep their table logic in a
 * params-free, unit-tested core class.
 */
class BaseValuePredictor : public SimObject
{
  public:
    BaseValuePredictor(const BaseValuePredictorParams &p);

    /** Rename-time lookup (call only after renameDestRegs). Returns a
     *  value to consume, or nullopt for: ineligible, out of scope,
     *  table miss, or below the confidence threshold. On a hit the
     *  base class counts predictionsMade and stamps
     *  setVpPredicted()/setVpPredVal() on the instruction. */
    std::optional<RegVal> predict(const DynInstPtr &inst);

    /** Writeback-time training with the architected value. Counts the
     *  eligible population (the coverage denominator) and delegates to
     *  trainImpl(). No-op for out-of-scope instructions, so call sites
     *  stay thin. */
    void train(const DynInstPtr &inst, RegVal actualValue);

    /** Verify-site outcome accounting for a consumed prediction.
     *  @param flushed the measured inclusive squash cost when wrong
     *  (0 when correct). Level attribution runs for loads only. */
    void verifyResult(const DynInstPtr &inst, bool correct,
                      uint64_t flushed);

    /** A consumed prediction was discarded before it could verify
     *  (counted, never trained). Called from the ROB/CPU squash walks
     *  under the VpPredicted && !VpResolved exactly-once guard. */
    void notifySquashed(const DynInstPtr &inst);

    /** Reserved hook: predictors carrying speculative state (VTAGE
     *  class) restore it here on any pipeline squash. LVP ignores it. */
    virtual void notifyPipelineSquash() {}

    /** Per-predictor knob: train() is called at commit instead of
     *  writeback (VTAGE-class predictors; see the verify-site
     *  correctiveReset() below, which is only meaningful in this
     *  mode). Default false -- LVP keeps writeback training and its
     *  published behavior is unaffected. */
    virtual bool
    trainsAtCommit() const
    {
        return false;
    }

    /** Per-predictor knob: this predictor folds the fetch-time history
     *  snapshot (VpLookupContext::hist) into its lookup (VTAGE-class).
     *  Default false -- the pipeline only maintains/restores the
     *  history subsystem below when some attached predictor sets
     *  this; LVP configurations are unaffected. */
    virtual bool
    usesHistory() const
    {
        return false;
    }

    /** Verify-site no-livelock exception for trainAtCommit predictors
     *  (docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md,
     *  "Verify"): a
     *  delivered-and-wrong prediction squashes inclusively and never
     *  retires, so a commit-only trainer would never correct its
     *  entry. Resets confidence through the token (tag-checked so a
     *  reallocated entry is not hijacked); no value write, no
     *  allocation. No-op for predictors that keep writeback
     *  training. Returns whether the token still matched a live
     *  provider; a stale token (the entry was reallocated since
     *  predict()/train() stamped it) is counted as
     *  correctiveResetStale here -- the reset itself (on a live
     *  match) is counted by the derived predictor. */
    bool correctiveReset(uint64_t token);

    /** Scope knob: loads only (default) vs all eligible instructions. */
    bool
    onlyLoads() const
    {
        return _onlyLoads;
    }

    /** Eligibility (hard rules) AND scope (onlyLoads). Public so the
     *  IEW non-load site can pre-filter before reading the dest reg. */
    bool inScope(const DynInstPtr &inst) const;

    /**
     * History-subsystem thin wrappers (framework-level, predictor-
     * agnostic; docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md,
     * "History Subsystem"). The pipeline wiring (fetch-side notify,
     * per-inst snapshot stamping, redirect restores) lives in
     * fetch.cc/bac.cc/commit.cc; only predictors with usesHistory()
     * will ever observe non-default history state.
     */

    /** Fetch-side control-flow notification for thread tid: a
     *  conditional branch shifts its predicted direction into ghr;
     *  every taken control transfer shifts target's low bits into
     *  path (masked to historyPathBits wide). */
    void notifyControlFlow(ThreadID tid, bool isCond, bool predTaken,
                           Addr target);

    /** Path-history register width (see _historyPathBits below).
     *  Exposed so Commit can precompute a restore-carrier snapshot via
     *  vp_history.hh's advanceSnapshot() -- a pure function, so it
     *  needs pathBits passed in explicitly -- without mutating any
     *  live history state (design doc, "History Subsystem", the
     *  squash-after restore rule). */
    unsigned
    historyPathBits() const
    {
        return _historyPathBits;
    }

    /** Stamp thread tid's current history state onto inst as its
     *  fetch-time snapshot. */
    void snapshotFor(const DynInstPtr &inst) const;

    /** Restore thread tid's history register to a prior snapshot (any
     *  fetch redirect; restore-site rules live with their pipeline
     *  call sites, not here). */
    void restoreHistory(ThreadID tid, const VpHistSnapshot &snap);

    /** Which pipeline redirect initiated a restoreHistory() call
     *  (design doc, "History Subsystem" restore table); indexes the
     *  historyRestores stat via countHistoryRestore(). Front-end-only
     *  resteers (bacResteer, FTQ pops) discard no DynInsts and never
     *  restore, so they have no bucket here. */
    enum class VpHistInitiator
    {
        Branch,      ///< IEW-resolved branch/indirect mispredict (commit).
        Decode,      ///< Decode-detected direct-branch target correction.
        Inclusive,   ///< Inclusive VP/memory-order squash (commit).
        Trap,        ///< Trap/interrupt/TC/drain squashAll (commit).
        SquashAfter, ///< Commit squash-after (commit).
        /** Commit could not resolve a restore-carrier snapshot for an
         *  Inclusive/Trap/SquashAfter redirect (e.g. the victim
         *  instruction was no longer resolvable in the ROB, or a
         *  trap/TC fired with an already-empty ROB) -- no restore
         *  happened; the live history register was left as-is. */
        Missed,
        Num
    };

    /** Bump the per-initiator historyRestores stat. Call once per
     *  restoreHistory() at each pipeline redirect site (or, for
     *  Missed, once per unresolved carrier -- no restoreHistory()
     *  call accompanies it). */
    void countHistoryRestore(VpHistInitiator initiator);

    /** Per-predictor knob: the framework maintains the per-PC
     *  in-flight occurrence map below for this predictor (EVES-class
     *  extrapolating predictors). Keys are folded vpKey values, not
     *  thread-qualified -- the same single-thread declared
     *  generalization as the burst-guard machinery (design doc,
     *  in-flight counter subsystem). Default false: every hook is
     *  inert and existing predictors are bit-identical. */
    virtual bool
    usesInflightCounts() const
    {
        return false;
    }

    /** Once per renamed instruction, from rename.cc AFTER the
     *  consumption ladder (an instruction never counts itself; a
     *  later same-cycle same-PC micro-op sees this one). Feeds the
     *  burst-guard rename count unconditionally and, for
     *  usesInflightCounts() predictors, the in-flight map (in-scope
     *  instructions only, marked VpInflightCounted). */
    void notifyRenamedInst(const DynInstPtr &inst);

    /** From the two squash walks (ROB::doSquash, CPU::squashInstIt):
     *  reclaim a counted instruction's in-flight count. Flag-guarded
     *  internally -- callers need no eligibility logic; the
     *  VpInflightCounted bit makes it exactly-once across
     *  overlapping walks (the MRN-proven discipline). */
    void notifySquashedInFlight(const DynInstPtr &inst);

    /** Current in-flight occurrence count for a folded key. */
    uint32_t
    inflightCount(uint64_t key) const
    {
        return inflight.count(key);
    }

    /** Renamed-instruction count for thread tid (design doc docs/
     *  superpowers/specs/2026-08-04-evtage-design.md, S6's burst-
     *  misprediction guard): LastMispVT-style predictors need the
     *  full rename rate, not just the eligible/in-scope subset
     *  (counting only eligible instructions would stretch the window
     *  several-fold, per the design doc). Fed once per renamed
     *  instruction, eligible or not, by rename.cc via
     *  notifyRenamedInst(); deliberately not squash-restored (design
     *  doc S6: wrong-path rename increments are kept). Readable by
     *  any predictor that wants a burst-guard-style window; 0 for
     *  every thread unless some attached predictor opts into the
     *  burst guard. */
    unsigned
    renamedInsts(ThreadID tid) const
    {
        return renamedCount[tid];
    }

  protected:
    /** Algorithm-level corrective reset (VTAGE-class only); see
     *  correctiveReset(). Returns whether the token still matched a
     *  live provider. Default true (no-op predictors, and predictors
     *  that never call this because trainsAtCommit() is false, never
     *  report staleness). */
    virtual bool
    correctiveResetImpl(uint64_t)
    {
        return true;
    }

    /** Algorithm lookup over the lookup context. */
    virtual VpPredictResult predictImpl(const VpLookupContext &ctx) = 0;
    /** Algorithm training over the lookup context, the provider token
     *  stamped by the matching predict() (0 if none/stale), and the
     *  classifier context (design doc
     *  docs/legacy-log/superpowers/specs/2026-08-04-evtage-design.md,
     *  "Framework API Changes"). LVP and plain
     *  VTAGE take and ignore the classifier parameter -- same bit-
     *  identity pattern as VpLookupContext::hist. */
    virtual void trainImpl(const VpLookupContext &ctx, RegVal actualValue,
                           uint64_t token,
                           const VpClassifierInfo &classifier) = 0;

    /** Hard eligibility rules: single scalar integer, non-fixed-mapping
     *  destination; not serializing / barrier / non-speculative /
     *  atomic / store-conditional. */
    bool eligible(const DynInstPtr &inst) const;

    const bool _onlyLoads;
    /** Subsumed by the integer-only rule today; retained so the
     *  interface is stable when FP/vector support lands. */
    const bool _scalarOnly;
    /** Path-history register width (ValuePredictor.py's
     *  historyPathBits); passed to VpHistory::takenTarget() by
     *  notifyControlFlow(). Only consumed by history-aware
     *  predictors. */
    const unsigned _historyPathBits;

    /** VTAGE-class predictors' only speculative state: per-thread
     *  branch/path history (vp_history.hh). Idle -- never advanced or
     *  read -- when no attached predictor sets usesHistory(). */
    VpHistory vpHist[MaxThreads];

    /** Backing store for renamedInsts() (S6's burst-guard rename
     *  counter). Zero-initialized; fed once per renamed instruction
     *  by rename.cc via notifyRenamedInst(). */
    unsigned renamedCount[MaxThreads] = {};

    /** Backing store for inflightCount() (design doc, in-flight
     *  counter subsystem). Touched only when some attached predictor
     *  sets usesInflightCounts(). */
    VpInflightMap inflight;

    struct VpStats : public statistics::Group
    {
        explicit VpStats(statistics::Group *parent);

        /** In-scope instructions reaching the train site (the coverage
         *  denominator), split loads / non-loads. Includes MRN-claimed
         *  loads; excludes already-squashed instructions. */
        statistics::Scalar eligibleLoads;
        statistics::Scalar eligibleNonLoads;
        /** Predictions consumed at rename (speculative path). Identity:
         *  made == correct + wrong + squashed (+- in flight at the
         *  dump boundary). */
        statistics::Scalar predictionsMade;
        statistics::Scalar predictionsCorrect;
        statistics::Scalar predictionsWrong;
        /** Consumed predictions discarded before they could verify. */
        statistics::Scalar predictionsSquashed;
        /** Instructions discarded by VP misprediction squashes
         *  (inclusive: the mispredicted instruction itself counts). */
        statistics::Scalar squashedInsts;
        /** History-subsystem restores (usesHistory() predictors only),
         *  by initiator -- see VpHistInitiator. */
        statistics::Vector historyRestores;
        /** correctiveReset() calls (trainAtCommit predictors' verify-
         *  wrong arm) whose token no longer matched a live provider
         *  (the entry was reallocated in flight). */
        statistics::Scalar correctiveResetStale;
        /** In-flight counter closure (usesInflightCounts()
         *  predictors): increments == decTrain + decSquash up to the
         *  live in-flight population at the dump boundary; the
         *  residual can never be negative. */
        statistics::Scalar inflightIncrements;
        statistics::Scalar inflightDecTrain;
        statistics::Scalar inflightDecSquash;
        /** correct / (eligibleLoads + eligibleNonLoads). */
        statistics::Formula coverage;
        /** correct / (correct + wrong). */
        statistics::Formula accuracy;
        /** Memory-system level (stlf/l1d/l2/mem/unknown) that served
         *  each verified predicted load, by outcome; flush cost of
         *  wrong predicted loads by level. */
        statistics::Vector predictedLevelCorrect;
        statistics::Vector predictedLevelWrong;
        statistics::Vector wrongFlushedByLevel;
    } stats;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_BASE_HH__
