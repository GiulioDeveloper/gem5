#ifndef __CPU_O3_VP_VTAGE_TABLES_HH__
#define __CPU_O3_VP_VTAGE_TABLES_HH__

#include <cstdint>
#include <functional>
#include <vector>

#include "base/types.hh"
#include "cpu/o3/vp/vp_history.hh"

namespace gem5
{
namespace o3
{

/**
 * Plain-value configuration for VtageTables. Mirrors the (future)
 * VTAGE SimObject params but is free of any params/SimObject
 * machinery, so the core logic can be built and unit-tested in
 * isolation (the pattern proven by LvpTable). Defaults are the
 * HPCA'14 evaluated configuration (Perais & Seznec, HPCA-20 2014;
 * docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md,
 * "Configuration").
 */
struct VtageConfig
{
    /** VT0: tagless, PC-indexed base component. */
    unsigned baseEntries = 8192;
    /** Per tagged component (VT1..VTnumTagged); all tagged components
     *  share this size. */
    unsigned taggedEntries = 1024;
    /** Number of tagged components. The biased-rank token field packs
     *  0 = none, 1 = VT0, 2..(1+numTagged) = VT1..VTnumTagged, so
     *  numTagged <= 7 (the constructor rejects anything larger). */
    unsigned numTagged = 6;
    /** Per-component history length L(i), shortest to longest. Size
     *  must equal numTagged. */
    std::vector<unsigned> historyLengths = {2, 4, 8, 16, 32, 64};
    /** Tagged component i's (1-based) tag width is baseTagBits + i. */
    unsigned baseTagBits = 12;
    /** Saturating confidence-counter width, every component. */
    unsigned confBits = 3;
    /** Minimum confidence required to predict. Must be >= 1 (the
     *  constructor rejects 0): otherwise the verify-site corrective
     *  reset (c = 0) would not stop the refetched instance from being
     *  re-predicted, breaking the no-livelock invariant. */
    unsigned confThreshold = 7;
    /** Forward Probabilistic Counters: v[i] is the probability that
     *  the i -> i+1 confidence transition fires on a correct update.
     *  Size must equal the counter's saturating value (2^confBits -
     *  1). Reset to 0 on a wrong update is never probabilistic. */
    std::vector<double> fpcVector = {1,       1. / 16, 1. / 16, 1. / 16,
                                     1. / 16, 1. / 32, 1. / 32};
    /** Path-history register width (VpHistSnapshot::path is 16b). */
    unsigned pathBits = 16;
};

/** What a rename-time lookup saw. */
struct VtageLookup
{
    /** Some component matched. Always true: VT0 is tagless and
     *  always "hits", so every lookup stamps a usable token. */
    bool hit = false;
    /** Provider confidence >= confThreshold: the value below may be
     *  consumed. */
    bool confident = false;
    RegVal value = 0;
    /** Opaque provider token, stamped on every lookup (even below
     *  confidence). Packing is internal to this class; the biased
     *  rank field means this is never 0 for a real lookup. */
    uint64_t token = 0;
};

/** What a train() call did to the provider entry (and, on a wrong
 *  outcome, the allocation probe above it). Feeds the wrapper's
 *  derived stats; a single train() call can return several. */
enum class VtageTrainOutcome
{
    /** Correct; FPC gate fired and the confidence counter advanced. */
    CorrectInc,
    /** Correct; the counter held (already saturated, or the FPC gate
     *  did not fire this attempt). */
    CorrectSat,
    /** Wrong, provider confidence was > 0: unconditional reset to 0. */
    WrongReset,
    /** Wrong, provider confidence was already 0: value overwritten in
     *  place instead of a confidence reset (nothing to reset). */
    WrongValOverwrite,
    /** Wrong training allocated a new entry into a higher-rank
     *  (longer-history) component. */
    Allocated,
    /** Wrong training found no u == 0 candidate above the provider:
     *  no allocation, useful bits aged (reset to 0) instead. */
    AllocFailedAged,
    /** The token was stale (tag mismatch -- entry reallocated in
     *  flight) or absent (token == 0): the provider was recomputed
     *  from (pc, upc, h) instead of trusting the token. */
    StaleTokenRecomputed
};

/**
 * Read-only view of what a lookup()/train() call resolves as its
 * provider, without requiring the caller to understand the token's
 * internal packing (design doc's "opaque 64 bits" -- the framework/
 * base class never decodes a token; only VtageVP, which owns this
 * core, does, via peekProvider() below).
 */
struct VtageProviderPeek
{
    /** Biased rank: 1 = VT0, 2..(1+numTagged) = VT1..VTnumTagged --
     *  the same encoding as the token's rank field (never 0: VT0 is
     *  the ultimate fallback). Wrapper stats index per-component
     *  vectors as rank - 1. */
    unsigned rank = 1;
    /** The resolved provider's confidence counter is already at the
     *  saturating max (2^confBits - 1): no further FPC transition is
     *  possible on a correct update. */
    bool saturated = false;
};

/**
 * The params-free VTAGE core: VT0 (tagless base) plus VT1..VTnumTagged
 * (PC x global-history tagged components), TAGE-style longest-match
 * selection, Forward Probabilistic Counters, and ITTAGE-style
 * allocate-on-mispredict with u-bit aging. Folds are computed
 * on-demand from the {ghr, path} snapshot (no per-component folded
 * history state to checkpoint/restore -- see
 * docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md, "Data
 * Structures"; the fold/index/tag arithmetic mirrors gem5's TAGE,
 * src/cpu/pred/tage_base.{hh,cc}).
 */
class VtageTables
{
  public:
    /** rng: any callable returning a double in [0, 1) -- injected so
     *  GTests can script deterministic FPC / allocation-choice
     *  behavior; production callers pass a functor wrapping a
     *  Random::RandomPtr. */
    VtageTables(const VtageConfig &cfg, std::function<double()> rng);

    /** Rename-time lookup. Never modifies the table. Longest-history
     *  tag hit is the provider; falls back to VT0 (which always
     *  "hits"). Stamps a token on the provider unconditionally,
     *  whether or not it is confident enough to deliver a value. */
    VtageLookup lookup(Addr pc, MicroPC upc, const VpHistSnapshot &h) const;

    /** Commit-time training with the architected value. token == 0
     *  (or a stale/tag-mismatched token) recomputes the provider by
     *  longest-match from (pc, upc, h) instead -- training remains
     *  unconditional. Provider update: correct -> FPC-gated c++,
     *  u = 1; wrong -> val overwrite if c == 0 else c = 0 (always
     *  unconditional), u = 0, then an allocation probe of the
     *  components above the provider. Returns the outcomes that
     *  fired, in the order they happened. */
    std::vector<VtageTrainOutcome> train(Addr pc, MicroPC upc,
                                         const VpHistSnapshot &h,
                                         uint64_t token, RegVal actual);

    /** Verify-site corrective reset (the trainAtCommit no-livelock
     *  exception): c = 0 (and u = 0 for a tagged provider) through
     *  the token, tag-checked so a reallocated entry is not hijacked.
     *  No value write, no allocation. Returns false on a stale or
     *  absent (token == 0) token; the caller counts that. */
    bool correctiveReset(uint64_t token);

    /** Read-only preview of the provider a train(pc, upc, h, token,
     *  ...) call would resolve: the token's own rank if live and
     *  tag-checked, else the same longest-match recompute train()
     *  falls back to for a stale/absent token -- mirrors train()'s
     *  own resolution logic exactly, but performs no mutation. Added
     *  (design doc, "Statistics") so wrapper stats (VTAGE SimObject's
     *  per-component provider/FPC accounting) can classify an
     *  about-to-happen train() outcome without duplicating the
     *  token's internal packing themselves, and without changing
     *  train()'s own GTest-pinned outcome semantics. Call immediately
     *  before the matching train() with identical arguments: no
     *  table mutation happens between the two in the wrapper's
     *  usage, so the peek and the following train() stay
     *  consistent. */
    VtageProviderPeek peekProvider(Addr pc, MicroPC upc,
                                   const VpHistSnapshot &h,
                                   uint64_t token) const;

  private:
    /** VT0 entry: tagless, no allocation, no usefulness bit. */
    struct BaseEntry
    {
        RegVal val = 0;
        unsigned c = 0;
    };

    /** VT1..VTnumTagged entry. `valid` is an implementation-only
     *  bookkeeping bit (not part of the papers' entry layout): it
     *  keeps a never-allocated slot's zero-initialized tag from
     *  spuriously matching a freshly computed zero tag, which would
     *  otherwise make GTest outcomes depend on hash-collision luck.
     *  Real TAGE tables accept that rare collision; this predictor
     *  does not need to, since the bit costs nothing in a functional
     *  model. */
    struct TaggedEntry
    {
        bool valid = false;
        RegVal val = 0;
        unsigned c = 0;
        uint64_t tag = 0;
        bool u = false;
    };

    /** A located provider: bank == 0 means VT0; otherwise bank is the
     *  1-based tagged-component index (VT1 = 1, ..., VTnumTagged =
     *  numTagged) -- the papers' own "rank 1 (shortest) to N
     *  (longest)" numbering, kept distinct from the token's biased
     *  rank field (which is bank + 1 for a tagged provider). */
    struct Provider
    {
        unsigned bank = 0;
        unsigned index = 0;
        uint64_t tag = 0;
    };

    struct UnpackedToken
    {
        unsigned rank = 0;
        unsigned index = 0;
        uint64_t tag = 0;
    };

    /** (((pc XOR (upc << 48)) >> 2) << 2) | (upc & 3) -- vp_key.hh's
     *  fold in place of TAGE's instShiftAmt pre-shift, with the
     *  micro-op residue CONCATENATED into the two low bits the >> 2
     *  vacated: the hashed "pc" every fold/index/tag below is built
     *  from. Deliberately NOT truncated to 32 bits the way gem5's
     *  TAGE truncates its Addr -> unsigned int: the upc lives in
     *  bits [48:63] of the pre-shift value, so truncating would
     *  throw away vp_key.hh's high-bit fold. The low-bit residue is
     *  what actually delivers micro-op separation into the LOW,
     *  masked bits that every index/tag computation keeps: bits
     *  [48:63] never survive the masks below on their own (confirmed
     *  by a 120k-lookup randomized sweep), so micro-ops 0-3 separate
     *  fully and micro-ops >= 4 keep the high-bit fold as their only
     *  distinguisher. Concatenation leaves the PC-delta bits
     *  untouched; XORing the raw upc into them instead recreates a
     *  full-table alias at a power-of-two PC distance -- an XOR at
     *  bit 0 merges (pc, upc = 1) with (pc + 4, upc = 0) for even
     *  pc >> 2, (pc - 4, upc = 0) for odd. */
    uint64_t shiftedPcOf(Addr pc, MicroPC upc) const;

    /** Mirrors gem5 TAGE's FoldedHistory::update() (tage_base.hh),
     *  replayed `origLength` times from a zeroed register: the
     *  fold-on-demand adaptation
     *  docs/legacy-log/superpowers/specs/2026-08-03-vtage-design.md calls for.
     *  Folds ghr[0:origLength) (bit 0 = newest; bits 64..127 read
     *  from ghr1 via histBit(), vp_history.hh) into compLength bits.
     *  Because this replay always starts from an all-zero register
     *  and runs for exactly origLength steps, the bit that "ages
     *  out" of the incremental update (h[origLength]) is always the
     *  zero-filled placeholder for the entire replay, so that XOR
     *  term is elided below (XORing with 0 is a no-op) rather than
     *  transcribed literally from tage_base.hh. */
    uint64_t foldHistory(const VpHistSnapshot &h, unsigned origLength,
                         unsigned compLength) const;

    /** Mirrors gem5 TAGE's F() path-hash (tage_base.cc), adapted to
     *  VTAGE's constant per-tagged-component table size: every
     *  tagged component is `taggedEntries` entries (unlike TAGE's
     *  per-bank logTagTableSizes), so the table-size parameter below
     *  is the fixed logTaggedEntries rather than a per-bank value. */
    uint64_t pathHash(uint64_t path, unsigned size, unsigned bank) const;

    /** Mirrors gem5 TAGE's gindex(): full hash of the shifted pc,
     *  the on-demand folded ghr, and the path hash, for tagged
     *  component `bank` (1-based). */
    unsigned computeIndex(uint64_t shiftedPc, const VpHistSnapshot &h,
                          unsigned bank) const;

    /** Mirrors gem5 TAGE's gtag(): shifted pc XOR'd with two
     *  independent on-demand folds of the same history (widths
     *  tagWidth(bank) and tagWidth(bank) - 1, the second shifted left
     *  1 to decorrelate them), masked to tagWidth(bank) bits. */
    uint64_t computeTag(uint64_t shiftedPc, const VpHistSnapshot &h,
                        unsigned bank) const;

    /** VT0's tagless index: shiftedPc masked to log2(baseEntries)
     *  bits. */
    unsigned computeBaseIndex(uint64_t shiftedPc) const;

    /** Longest-match search over all tagged components, falling back
     *  to VT0. Used by lookup() and by train()'s stale-token
     *  recompute. */
    Provider findProvider(Addr pc, MicroPC upc, const VpHistSnapshot &h) const;

    /** Biased-rank pack: rank 0 = none, 1 = VT0, 2..(1+numTagged) =
     *  VT1..VTnumTagged (bank + 1). index/tag are the provider's own;
     *  tag is unused (0) for a VT0 (rank 1) token. */
    uint64_t packToken(unsigned rank, unsigned index, uint64_t tag) const;
    UnpackedToken unpackToken(uint64_t token) const;

    const unsigned baseEntries;
    const unsigned taggedEntries;
    const unsigned numTagged;
    const std::vector<unsigned> historyLengths;
    const unsigned baseTagBits;
    const unsigned confBits;
    const unsigned confMax;
    const unsigned confThreshold;
    const std::vector<double> fpcVector;
    const unsigned pathBits;

    const unsigned logBaseEntries;
    const unsigned logTaggedEntries;

    /** Reserved token field widths (packing is internal: the token is
     *  just an opaque 64b carrier sized to fit the widest rank/index/
     *  tag any legal configuration can produce). The tag field is a
     *  fixed 20 bits: the widest legal tag is baseTagBits (12) +
     *  numTagged (7) = 19 bits, and the constructor rejects any
     *  configuration whose widest tag exceeds the field. */
    static constexpr unsigned rankFieldBits = 4;
    static constexpr unsigned tagFieldBits = 20;
    const unsigned indexFieldBits;

    std::function<double()> rng;

    /** baseEntries entries. */
    std::vector<BaseEntry> base;
    /** tagged[bank - 1][index], bank 1..numTagged. */
    std::vector<std::vector<TaggedEntry>> tagged;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_VTAGE_TABLES_HH__
