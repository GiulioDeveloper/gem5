#ifndef __CPU_O3_VP_ESTRIDE_TABLE_HH__
#define __CPU_O3_VP_ESTRIDE_TABLE_HH__

#include <array>
#include <cstdint>
#include <functional>
#include <vector>

#include "base/types.hh"

namespace gem5
{
namespace o3
{

/**
 * The stride-alloc class an instruction classifies into, feeding
 * EStrideTable::train()'s allocation ladder (design doc
 * docs/legacy-log/superpowers/specs/2026-08-14-estride-design.md, S3.4;
 * Seznec's
 * CVP-1 2018 EVES submission source (cvp8KB/mypredictor.cc), the
 * `allocationDraw` switch at cc:166-197). IndirectCall and Undef fall
 * under `Never` (absent from the source's switch -- unlike E-VTAGE's
 * own "alu-like Undef" dispatch, which stays as shipped on the VTAGE
 * side).
 */
enum class EStrideAllocClass
{
    AluOrStore,
    FpOrSlowAlu,
    Load,
    Never,
};

/**
 * Per-call classifier inputs to EStrideTable::train() and lookup()'s
 * companion draws, precomputed by the caller (the EvesVP wrapper) so
 * this core stays params-free and ignorant of OpClass/StaticInst --
 * the same porting convention EVtageClassifier established
 * (evtage_tables.hh). notLlcMiss/notL2Miss/notL1Miss default true and
 * fastInst defaults false so a plain non-load, non-memory classifier
 * (e.g. an ALU allocation candidate, which never consults the load
 * latency terms) needs no explicit setup.
 */
struct EStrideClassifier
{
    bool isLoad = false;
    /** CVP's NOTLLCMISS/NOTL2MISS/NOTL1MISS latency-band predicates
     *  (Seznec's CVP-1 2018 EVES submission source, mypredictor.cc),
     *  mapped from the load's actual memory-serve level: notL1Miss ~
     *  latency < 12 cycles (proxy for an L1 hit), notL2Miss ~ latency
     *  < 60 (proxy for not missing past the L2), notLlcMiss ~
     *  latency < 150 (proxy for not missing past the LLC/into DRAM).
     *  Meaningless (left at their defaults) when isLoad is false.
     *  Expected monotonic for a real load: notL1Miss implies
     *  notL2Miss implies notLlcMiss (an L1 hit is also not an L2 miss
     *  and not an LLC miss, and so on) -- callers should preserve
     *  this ordering; the core itself does not enforce or rely on
     *  it. */
    bool notLlcMiss = true;
    bool notL2Miss = true;
    bool notL1Miss = true;
    /** CVP's MFASTINST = (actual_latency < 3) (mypredictor.cc:14,
     *  consulted at cc:153 and cc:186) -- a DIFFERENT predicate from
     *  the identically-named EVtageClassifier::fastInst
     *  (evtage_tables.hh), which means "genuine IntAlu" and feeds
     *  E-VTAGE's own FASTINST = (latency == 1). The two classifier
     *  types share a field name but diverge in meaning: a wrapper
     *  must compute this one from E-Stride's own < 3-cycle latency
     *  threshold and must NEVER forward EVtageClassifier::fastInst
     *  through verbatim -- doing so would silently shift every
     *  E-Stride confidence/allocation draw probability, and no test
     *  in either table's GTest suite compares the two classifiers
     *  against each other to catch it. */
    bool fastInst = false;
    EStrideAllocClass allocClass = EStrideAllocClass::AluOrStore;
    /** This instruction's prediction was delivered (consumed at
     *  rename) AND verified correct -- gates the confidence-increment
     *  draw's deterministic conjunct (S3.4) and the allocation gate
     *  (a VTAGE-covered correct commit must not waste a stride
     *  entry). */
    bool deliveredCorrect = false;
    /** The delivered prediction (if any) was supplied by THIS table
     *  (EvesArbiterOut::stridePredicted, carried back through the
     *  wrapper). Together with deliveredCorrect, keys the SafeStride
     *  credit (S3.5) and the confidence-draw conjunct. */
    bool stridePredicted = false;
};

/** What a rename-time lookup saw. */
struct EStrideLookup
{
    /** Some way tag-matched (no valid bit -- a virgin, zero-init
     *  entry whose tag hashes to 0 counts as a hit, design doc
     *  S3.1). */
    bool hit = false;
    /** The predict gate would have fired (conf >= ConfThreshold) but
     *  SafeStride was negative -- a stats refinement distinguishing
     *  "no entry"/"not confident" from "confident but globally
     *  gated", not a behavior change (the composed `predicted` gate
     *  is still conjunctive). */
    bool blockedBySafeStride = false;
    /** hit && SafeStride >= 0 && conf >= ConfThreshold (S3.2). Only
     *  when true is `value` meaningful. */
    bool predicted = false;
    RegVal value = 0;
};

/** Read-only view of a tag-matching entry's state (test/stat support,
 *  mirrors EVtageProviderPeek's purpose): u and stride are otherwise
 *  unobservable through the public API. hit == false leaves every
 *  other field at its default. */
struct EStridePeek
{
    bool hit = false;
    unsigned conf = 0;
    int u = 0;
    bool notFirstOcc = false;
    uint64_t stride = 0;
    /** The entry's last COMMITTED value. */
    uint64_t lastValue = 0;
};

/** What a train() call did; a single call can return several, in the
 *  order they happened (mirrors EVtageTrainOutcome). */
enum class EStrideTrainOutcome
{
    /** One-step match, confidence-increment draw fired. */
    ConfInc,
    /** One-step match, confidence held (draw did not fire, or conf
     *  was already saturated). */
    ConfHeld,
    /** One-step match, usefulness-increment draw fired. */
    UInc,
    /** One-step match, usefulness held. */
    UHeld,
    /** One-step match: conf reached ConfThreshold and u was jammed to
     *  3 as a result (an actual change -- see UHeld/UInc's own
     *  outcome for the increment itself, if any, that crossed the
     *  threshold this call). */
    UJamSaturated,
    /** One-step mismatch, conf was > ConfDecay: conf -= ConfDecay, u
     *  untouched. */
    MispredictDecay,
    /** One-step mismatch, conf was <= ConfDecay: conf = 0, u = 0. */
    MispredictCollapse,
    /** First occurrence, in-range nonzero delta: stride learned. */
    StrideSet,
    /** First occurrence, zero or out-of-range delta: the 0xffff
     *  sentinel stride installed, conf = u = 0 -- a systematic
     *  eviction target for constant-value entries. */
    SentinelDemoted,
    /** Allocation: victim pass 1 claimed a conf == 0 entry. */
    AllocatedConfZeroVictim,
    /** Allocation: victim pass 2 claimed a u == 0 entry. */
    AllocatedUZeroVictim,
    /** Allocation: both passes failed; the last-probed way's u was
     *  aged down by one. */
    AllocAged,
    /** Allocation: both passes failed; the aging draw did not fire. */
    AllocAgeHeld,
    /** Allocation: the class/latency draw did not fire (or the class
     *  never draws -- EStrideAllocClass::Never). */
    AllocDrawRefused,
    /** A tag miss, but the instruction was already delivered correct
     *  (by VTAGE): allocation is skipped entirely, no draw
     *  consumed. */
    AllocSkippedDeliveredCorrect,
    /** SafeStride's +4 (+8 for loads) commit-time credit fired
     *  (deliveredCorrect && stridePredicted, pre-check-then-add). */
    SafeStrideCredited,
};

/**
 * The params-free E-Stride table core (the stride-prediction component
 * of the composed EVES predictor, design doc
 * docs/legacy-log/superpowers/specs/2026-08-14-estride-design.md, S3):
 * a verbatim transcription of Seznec's CVP-1 2018 EVES submission
 * source (cvp8KB/mypredictor.cc)'s
 * stride predictor -- 3-way skewed-associative, 48 entries total,
 * zero-initialized with NO valid bit (a key whose way-0 tag hashes to
 * 0 tag-hits a virgin entry and trains via the first-occurrence arm
 * rather than allocating, exactly as the source's zeroed static array
 * behaves). Owns the single GLOBAL SafeStride counter (S3.5) that
 * gates prediction table-wide. `inflight` (the number of
 * not-yet-committed occurrences of this key already in flight)
 * arrives as a plain argument from the framework's per-PC in-flight
 * occurrence counter, a separate facility this core does not touch.
 */
class EStrideTable
{
  public:
    static constexpr unsigned NumWays = 3; // NBWAYSTR
    static constexpr unsigned LogSets = 4; // LOGSTR
    static constexpr unsigned NumEntries = NumWays * (1u << LogSets);
    static constexpr unsigned TagBits = 14;                   // TAGWIDTHSTR
    static constexpr unsigned ConfBits = 5;                   // WIDTHCONFIDSTR
    static constexpr unsigned ConfMax = (1u << ConfBits) - 1; // 31
    static constexpr unsigned ConfThreshold = ConfMax / 4;    // 7
    static constexpr unsigned ConfDecay = 1u << (ConfBits - 3); // 4
    static constexpr int SafeStrideCap = (1 << 15) - 1;         // 32767
    static constexpr uint64_t StrideSentinel = 0xffff;          // cc:299

    /** rng: injected so GTests can script deterministic probabilistic
     *  gates; production callers pass a functor wrapping a
     *  Random::RandomPtr (same pattern as EVtageTables). */
    explicit EStrideTable(std::function<double()> rng);

    /** Rename-time lookup. Never modifies the table (including
     *  SafeStride). First tag-matching way (0 -> 2) wins; no match ->
     *  all-false. On a hit, `predicted` gates on SafeStride >= 0 &&
     *  conf >= ConfThreshold (S3.2); the extrapolated value adds
     *  (inflight + 1) occurrences' worth of stride to the entry's
     *  last committed value. */
    EStrideLookup lookup(uint64_t key, unsigned inflight) const;

    /** Commit-time training (S3.3). Order: SafeStride tick, then
     *  SafeStride credit, then the tag search and its hit/miss
     *  handling. Returns outcomes in the order they happened. */
    std::vector<EStrideTrainOutcome> train(uint64_t key, RegVal actual,
                                           const EStrideClassifier &c);

    /** SafeStride's -1024 verify-wrong penalty (S3.5), keyed off the
     *  token's stridePredicted flag by the caller -- this method just
     *  applies the arithmetic, no lower clamp. Returns true iff the
     *  counter was >= 0 before the penalty and is < 0 after (crossed
     *  the predict gate shut this call). */
    bool safeStridePenalty();

    /** The single global SafeStride counter's current value. */
    int safeStride() const;

    /** Read-only view of the first tag-matching way's state (test/stat
     *  support, mirrors EVtageProviderPeek's purpose). */
    EStridePeek peek(uint64_t key) const;

    /** Test-only accessor: sets the SafeStride counter directly (name
     *  says what it is for -- pinning boundary conditions like the
     *  32767 pre-check cap without hundreds of train() calls). */
    void setSafeStrideForTest(int v);

    /** Test-only accessors: way `way`'s (0, 1, or 2) flat table index
     *  / tag for `key`, exposed so GTests can precompute set/way
     *  collisions (e.g. a virgin tag-0 entry, or several keys sharing
     *  a way-0 slot) without duplicating the hash. Public and static
     *  so no instance is needed. Not called by any production code
     *  path. */
    static unsigned wayIndex(uint64_t key, unsigned way);
    static uint64_t wayTag(uint64_t key, unsigned way);

  private:
    /** A table entry. Zero-initialized, no valid bit -- see the class
     *  doc comment. `stride` is stored at full uint64_t width; the
     *  source's "20 bits" is storage accounting only (the S3.3 range
     *  check at train time is the sole enforcement). `u`'s invariant
     *  0..3 is asserted, never enforced by the type. */
    struct Entry
    {
        uint64_t lastValue = 0; // Last COMMITTED value.
        uint64_t stride = 0;    // Full width; 20 bits is accounting.
        uint8_t conf = 0;
        int u = 0; // Invariant 0..3, asserted.
        uint16_t tag = 0;
        bool notFirstOcc = false;
    };

    /** First tag-matching way's flat table index, or -1 if none
     *  matches (shared by lookup(), train(), and peek()). */
    int findEntry(uint64_t key) const;

    /** The confidence/usefulness increment gate (S3.4; cc:149-162).
     *  `stride` is the just-computed strideCandidate, signed. */
    bool confIncrementDraw(const EStrideClassifier &c, int64_t stride);

    /** p = 2^-exponent Bernoulli draw against the injected [0, 1) rng;
     *  exponent 0 always passes. */
    bool bernoulli(unsigned exponent);

    /** The allocation-class draw (S3.4 ladder; cc:166-197).
     *  EStrideAllocClass::Never consumes no draw. */
    bool allocationDraw(const EStrideClassifier &c);

    /** Installs a fresh entry at flat index `idx` (way `way`, for
     *  `key`): conf = 1 (deliberately, to survive victim pass 1 until
     *  the first stride observation, cc:320), u = 0, stride = 0,
     *  notFirstOcc = false, lastValue = actual. */
    void installEntry(unsigned idx, uint64_t key, unsigned way,
                      uint64_t actual);

    /** Victim search on a tag miss (cc:312-359): one random starting
     *  way, pass 1 claims the first conf == 0 entry, pass 2 claims the
     *  first u == 0 entry; if both fail, the last-probed way's u is
     *  aged down with probability 1/2^(2 + 2*(conf > ConfMax/8) +
     *  2*(conf >= ConfThreshold)). */
    void allocateVictim(uint64_t key, uint64_t actual,
                        std::vector<EStrideTrainOutcome> &outcomes);

    std::array<Entry, NumEntries> table{};
    int safeStride_ = 0; // Single GLOBAL counter (h:128).
    std::function<double()> rng;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_ESTRIDE_TABLE_HH__
