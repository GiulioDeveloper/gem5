#ifndef __CPU_O3_VP_EVTAGE_TABLES_HH__
#define __CPU_O3_VP_EVTAGE_TABLES_HH__

#include <cstdint>
#include <functional>
#include <utility>
#include <vector>

#include "base/types.hh"
#include "cpu/o3/vp/vp_history.hh"

namespace gem5
{
namespace o3
{

/**
 * Memory-hierarchy level that served a load, feeding the E/E'/E_u
 * exponent formulas' NOTLLCMISS/NOTL2MISS/NOTL1MISS/FASTINST terms
 * (design doc docs/legacy-log/superpowers/specs/2026-08-04-evtage-design.md,
 * "Latency-classifier mapping"). Meaningless when
 * EVtageClassifier::isLoad is false.
 */
enum class EVtageMemLevel : uint8_t
{
    Stlf, // Store-to-load forward: faster than a genuine L1 hit.
    L1d,
    L2,
    Mem // DRAM / LLC-miss; our 3-level hierarchy has no distinct LLC
        // row, so this is also NOTLLCMISS's false case (design doc:
        // "E skips from L2 to DRAM").
};

/**
 * Per-call classifier inputs to EVtageTables::train(): everything the
 * E/E'/E_u exponent formulas need, precomputed by the caller (Task 2's
 * EVtageVP wrapper) so this core stays params-free and ignorant of
 * OpClass/StaticInst (design doc, "Framework API Changes"). Non-load
 * fastInst/slowInst encode a 3-way split with only two bits:
 *  - fastInst = true: genuine IntAlu -- the ONLY case eligible for
 *    E_u's alu-specific bonus term.
 *  - slowInst = true: multiply/divide/FP ("slow-ALU class"): FASTINST
 *    false, all NOT*MISS terms true.
 *  - both false: store/undef -- "alu-like everywhere [for E/E'] except
 *    S4's alu-specific E_u term, which is alu-only" (design doc, S1's
 *    "Class dispatch"): gets the same FASTINST=true, NOT*MISS=true
 *    treatment as fastInst via the derived fastInstBit() below, but
 *    never the E_u alu bonus (which checks the raw fastInst flag).
 * isIndirectCall (eligible indirect call, e.g. AArch64 BLR) overrides
 * every gate to deterministic true, per S1's class dispatch.
 */
struct EVtageClassifier
{
    bool isLoad = false;
    EVtageMemLevel memLevel = EVtageMemLevel::L1d;
    bool fastInst = false;
    bool slowInst = false;
    /** CVP's NbOperand: count of integer non-flag source registers,
     *  capped as CVP does (design doc, "Operand-count mapping"). */
    unsigned intSrcCount = 0;
    bool isIndirectCall = false;
    /** The actual/committed value: feeds LOWVAL and is the value
     *  written into the provider on a wrong outcome (folds what
     *  VtageTables::train() takes as a separate `actual` parameter
     *  into this single struct). */
    RegVal value = 0;
    /** This instruction's prediction was delivered (consumed at
     *  rename) AND verified correct (design doc, "Framework API
     *  Changes": VpClassifierInfo's deliveredCorrect, carried from
     *  VpPredicted/VpResolved). Gates S4's UPDATEU exploration-credit
     *  draw (fires only when NOT delivered-correct). Not in the task
     *  brief's shape reminder, but required by the spec's E_u
     *  formula -- added per "bind to the spec, these are reminders
     *  not replacements". */
    bool deliveredCorrect = false;
};

/**
 * Params-free configuration for EVtageTables. Mirrors VtageConfig's
 * geometry fields (fpcVector is dropped -- E-VTAGE's classifier-driven
 * confidence gate replaces FPC entirely, design doc S1) and adds the
 * E-VTAGE-only knobs. Defaults mirror VtageConfig's HPCA'14 geometry
 * plus the design doc's "Configuration" table.
 */
struct EVtageConfig
{
    /** VT0: TOTAL entries across its two skewed ways (design doc S5:
     *  "Geometry stays 8192 entries total (2 x 4096-entry ways)").
     *  Must be even; half must be a power of two. */
    unsigned baseEntries = 8192;
    /** Per tagged component (VT1..VTnumTagged); all tagged components
     *  share this size. */
    unsigned taggedEntries = 1024;
    /** Number of tagged components; numTagged <= 7 (biased-rank token
     *  field: 0 = none, 1 = VT0, 2..(1+numTagged) = VT1..VTnumTagged). */
    unsigned numTagged = 6;
    /** Per-component history length L(i), shortest to longest. Size
     *  must equal numTagged. */
    std::vector<unsigned> historyLengths = {2, 4, 8, 16, 32, 64};
    /** VT0's own tag width, and tagged component i's tag width
     *  (baseTagBits + i). Design doc S5: VT0's tag "matches the tagged
     *  components' base width". */
    unsigned baseTagBits = 12;
    /** Saturating confidence-counter width, every component. */
    unsigned confBits = 3;
    /** Minimum confidence required to predict/deliver a value. Must be
     *  >= 1 (no-livelock invariant, inherited from VtageConfig). */
    unsigned confThreshold = 7;
    /** Saturating usefulness-counter width (design doc S4: "u widens
     *  to 2 bits (max 3)"). */
    unsigned uBits = 2;
    /** TICK aging-pass threshold (design doc S4, "TICK += NA - 5*ALL",
     *  K32's MAXTICK). */
    unsigned tickMax = 1024;
    /** Burst-misprediction guard window in renamed instructions (design
     *  doc S6); 0 = off (default; the ratified fork). This core only
     *  exposes the stateless gate predicate (burstGuardSuppresses()) --
     *  the per-thread LastMispVT counter itself is framework/wrapper
     *  state (Task 2), keeping this core free of per-thread mutable
     *  state. */
    unsigned burstGuardWindow = 0;
    /** Path-history register width (VpHistSnapshot::path is 16b). */
    unsigned pathBits = 16;
};

/** What a rename-time lookup saw. */
struct EVtageLookup
{
    /** Some provider (a base way or a tagged bank) tag-matched. Unlike
     *  plain VTAGE's tagless VT0 (always "hits"), E-VTAGE's base is now
     *  tagged: a base-tag miss with no tagged hit is a legal "no
     *  provider" outcome (design doc S5), hit = false. */
    bool hit = false;
    /** Provider confidence >= confThreshold: the value below may be
     *  consumed. Always false when hit is false. */
    bool confident = false;
    RegVal value = 0;
    /** Opaque provider token, stamped on every lookup (even a
     *  no-provider one, and even below confidence). Packing is
     *  internal to this class. */
    uint64_t token = 0;
};

/** Read-only view of what a train() call would resolve as its
 *  provider (mirrors VtageProviderPeek); rank 0 = no provider is a
 *  legal outcome for E-VTAGE (design doc, "Rank-0 peek/stat
 *  contract") -- callers must route it to a dedicated "none" bucket,
 *  never `rank - 1` indexing. */
struct EVtageProviderPeek
{
    /** Biased rank: 0 = no provider, 1 = VT0, 2..(1+numTagged) =
     *  VT1..VTnumTagged. */
    unsigned rank = 0;
    /** The resolved provider's confidence counter is already at the
     *  saturating max (2^confBits - 1). False (meaningless) when
     *  rank == 0. */
    bool saturated = false;
    /** The resolved provider's raw usefulness counter (0 when rank ==
     *  0). Exposed (beyond VtageProviderPeek's shape) so GTests can
     *  directly pin S4's u lifecycle -- u is otherwise unobservable
     *  through the public API. */
    unsigned u = 0;
    /** The resolved provider's raw confidence counter (0 when rank ==
     *  0). Exposed so GTests can pin exact endpoints (e.g. the S2
     *  punish arm's {c = 5, u = 1}) rather than only the saturated
     *  bool. */
    unsigned c = 0;
};

/** What a train() call did; a single call can return several, in the
 *  order they happened (mirrors VtageTrainOutcome). */
enum class EVtageTrainOutcome
{
    /** Correct; the classifier-driven confidence gate fired. */
    CorrectInc,
    /** Correct; the counter held (already saturated, or the gate did
     *  not fire this attempt -- peekProvider()'s pre-train `saturated`
     *  disambiguates, as VtageVP already does for FPC). */
    CorrectSat,
    /** Wrong, no prior verify-site punish mark: full rule applied here
     *  -- provider confidence was saturated (c == confMax): c -= (the
     *  K32 (confMax+1)/4 decrement), u = 1. */
    WrongPunishSat,
    /** Wrong, no prior verify-site punish mark: full rule applied here
     *  -- provider confidence was below saturation: c = 0, u = 0. */
    WrongPunishReset,
    /** Wrong, entry was already punish-marked (verify-site
     *  correctivePunish() already applied the confidence/u rule for
     *  this same delivered misprediction): only the unconditional
     *  value overwrite + allocation probe happen here. */
    WrongOverwriteOnly,
    /** The token resolved to "no provider" (rank 0): no provider
     *  update, straight to the allocation gate. */
    NoProviderTrained,
    /** The token was stale (tag mismatch) or absent (token == 0): the
     *  provider was recomputed from (pc, upc, h) instead. */
    StaleTokenRecomputed,
    /** One allocation-scan candidate was visited and not stolen (NA
     *  bookkeeping). */
    AllocScanStep,
    /** A tagged-bank steal succeeded (ALL bookkeeping). */
    Allocated,
    /** A base-way steal succeeded (ALL bookkeeping; the "no provider"
     *  arm's dominant 7/8 sub-case). */
    AllocatedBaseWay,
    /** The base-way steal above seeded confidence to confMax instead
     *  of the usual confMax/2 (zero-operand-ALU special case, design
     *  doc S3: "exists only in this base-way arm"). Always co-occurs
     *  with AllocatedBaseWay in the same call's outcome vector. */
    AllocSeedSaturated,
    /** This call's allocation attempt drove TICK to tickMax: every
     *  entry's nonzero u (all components, base ways included) was
     *  decremented by 1 and TICK reset to 0. */
    TickPass
};

/**
 * The params-free E-VTAGE core (EVES Stage 1, design doc
 * docs/legacy-log/superpowers/specs/2026-08-04-evtage-design.md): a FORK of
 * VtageTables (not a subclass -- the update policy diverges too far),
 * sharing only the fold/history conventions in vp_history.hh. VT0 is
 * now a tagged, 2-way skewed component (S5); the confidence gate is a
 * per-class probabilistic increment (S1) instead of FPC; mispredicts
 * are punished through a verify/commit split (S2) with 2-bit u and a
 * probabilistic, MedConf-triggered allocation policy (S3/S4).
 */
class EVtageTables
{
  public:
    /** rng: injected so GTests can script deterministic probabilistic
     *  gates; production callers pass a functor wrapping a
     *  Random::RandomPtr (same pattern as VtageTables). */
    EVtageTables(const EVtageConfig &cfg, std::function<double()> rng);

    /** Rename-time lookup. Never modifies the table. Longest-history
     *  tag hit is the provider; falls back to VT0's two skewed ways;
     *  a base-tag miss with no tagged hit is a legal "no provider"
     *  outcome (hit = false). Stamps a token unconditionally. */
    EVtageLookup lookup(Addr pc, MicroPC upc, const VpHistSnapshot &h) const;

    /** Commit-time training. token == 0 (absent) or a stale/mismatched
     *  token recomputes the provider by longest-match from (pc, upc,
     *  h) instead; a token that resolved to "no provider" trains
     *  straight through to the allocation gate with no provider
     *  update. See EVtageTrainOutcome for the full outcome set. */
    std::vector<EVtageTrainOutcome> train(Addr pc, MicroPC upc,
                                          const VpHistSnapshot &h,
                                          uint64_t token,
                                          const EVtageClassifier &classifier);

    /** Verify-site corrective punish (design doc S2's two arms, applied
     *  through the token, tag-checked like any tagged rank -- including
     *  rank-1/VT0 tokens, S5). Sets punishApplied always and
     *  medConfPending when the pre-punish state qualified as MedConf
     *  (S3), for the deferred commit-train remainder to consume. No
     *  value write, no allocation (framework contract). Same signature
     *  as VtageTables::correctiveReset() (design doc, "Framework API
     *  Changes": "same signature, tag-checked") -- MedConf is evaluated
     *  internally from the entry's own state, no classifier needed.
     *  Returns false on a stale or absent token. */
    bool correctivePunish(uint64_t token);

    /** Read-only preview of the provider a train(...) call would
     *  resolve (mirrors VtageTables::peekProvider(), extended with the
     *  rank == 0 "no provider" bucket, design doc "Rank-0 peek/stat
     *  contract"). Call immediately before the matching train() with
     *  identical arguments. */
    EVtageProviderPeek peekProvider(Addr pc, MicroPC upc,
                                    const VpHistSnapshot &h,
                                    uint64_t token) const;

    /** Stateless burst-guard gate predicate (design doc S6): true when
     *  the caller's own per-thread LastMispVT-style counter (owned by
     *  the wrapper/framework, not this params-free core) has not yet
     *  reached the configured window -- prediction *emission* should
     *  be suppressed (the lookup/token/training path is unaffected).
     *  Always false when burstGuardWindow == 0 (off). */
    bool burstGuardSuppresses(unsigned lastMispVT) const;

    /** Test-only accessor: VT0 way `way`'s (0 or 1) {index, tag} hash
     *  for (pc, upc), exposed so GTests can directly confirm the two
     *  skewed ways use distinct hash functions (S5's whole point) --
     *  computeBaseIndex()/computeBaseTag() are otherwise private, and
     *  this declared adaptation has no external CVP source to
     *  cross-check against black-box. Not called
     *  by any production code path. */
    std::pair<unsigned, uint64_t> debugBaseWayHash(Addr pc, MicroPC upc,
                                                   unsigned way) const;

  private:
    /** A base way or tagged-bank entry. E-VTAGE's base is now a full
     *  policy participant (design doc S5): tag, u, and the two
     *  deferred-punish pending bits are shared with tagged entries, so
     *  one struct serves both. `valid` (implementation-only, mirrors
     *  VtageTables::TaggedEntry) guards a never-allocated slot's
     *  zero-initialized tag from spuriously matching a freshly
     *  computed zero tag. */
    struct Entry
    {
        bool valid = false;
        RegVal val = 0;
        unsigned c = 0;
        uint64_t tag = 0;
        unsigned u = 0;
        /** Set only by correctivePunish(); cleared by the next train()
         *  on this entry (design doc S3, "Pending-bit lifecycle"). */
        bool punishApplied = false;
        /** Set alongside punishApplied when the pre-punish state
         *  qualified as MedConf; makes the deferred allocation body
         *  deterministic. */
        bool medConfPending = false;
    };

    /** A located provider. bank == 0 means a VT0 way (see `way`);
     *  bank in [1, numTagged] is a tagged component. found == false
     *  means no provider at all (both VT0 ways tag-missed, no tagged
     *  hit) -- the legal "no provider" lookup outcome. */
    struct Provider
    {
        bool found = false;
        unsigned bank = 0;
        unsigned way = 0;
        unsigned index = 0;
        uint64_t tag = 0;
    };

    /** Internal token rank field: 0 = absent (framework never had a
     *  token -- the literal token == 0 sentinel), 1 = a lookup ran and
     *  found no provider (E-VTAGE's legal rank-0 outcome; still
     *  nonzero as a token so it never collides with "absent"), 2 = VT0
     *  (way disambiguates), 3..(2+numTagged) = tagged banks
     *  1..numTagged. The externally documented "biased rank" (S5;
     *  EVtageProviderPeek::rank) is this field minus 1. */
    struct UnpackedToken
    {
        unsigned rankField = 0;
        unsigned way = 0;
        unsigned index = 0;
        uint64_t tag = 0;
    };

    /** Same fold as VtageTables::shiftedPcOf() (vp_key.hh's fold, upc
     *  residue concatenated into the low 2 bits); duplicated rather
     *  than shared because this file must stay independently
     *  self-contained as a fork (vtage_tables.{hh,cc} stay untouched). */
    uint64_t shiftedPcOf(Addr pc, MicroPC upc) const;

    /** Mirrors VtageTables::foldHistory(): replay FoldedHistory::update
     *  from a zeroed register for exactly `origLength` steps. */
    uint64_t foldHistory(const VpHistSnapshot &h, unsigned origLength,
                         unsigned compLength) const;

    /** Generalization of VtageTables::pathHash() (gem5 TAGE's F()
     *  idiom) parameterized on an explicit register width `regWidth`
     *  instead of a single fixed logTaggedEntries -- needed so the
     *  same rotate/XOR mixing can serve both the tagged components
     *  (regWidth = logTaggedEntries, as in VtageTables) and VT0's two
     *  skewed ways (regWidth = logBaseWayEntries / baseTagBits, S5;
     *  VT0 has no GHR to fold, so `bank` alone must decorrelate the
     *  two ways -- a declared adaptation, the design doc gives no
     *  exact base-skew bit formula, only "two hash functions... mirror
     *  gem5 TAGE's F() idiom with distinct bank constants"). Requires
     *  regWidth > bank (the rotate math's shift-by-(regWidth-bank)).
     */
    uint64_t fBankHash(uint64_t path, unsigned size, unsigned regWidth,
                       unsigned bank) const;

    /** Tagged component `bank`'s (1-based) index -- same recurrence as
     *  VtageTables::computeIndex(). */
    unsigned computeTaggedIndex(uint64_t shiftedPc, const VpHistSnapshot &h,
                                unsigned bank) const;

    /** Tagged component `bank`'s (1-based) tag -- same recurrence as
     *  VtageTables::computeTag(). */
    uint64_t computeTaggedTag(uint64_t shiftedPc, const VpHistSnapshot &h,
                              unsigned bank) const;

    /** VT0 way `way`'s (0 or 1) index: two independent fBankHash()
     *  permutations of shiftedPc (no GHR fold -- S5, "two hash
     *  functions over the µop-distinguished PC"), bank constants
     *  way + 1 (1 or 2). */
    unsigned computeBaseIndex(uint64_t shiftedPc, unsigned way) const;

    /** VT0 way `way`'s 12-bit (baseTagBits-wide) tag: two further,
     *  distinct fBankHash() permutations (bank constants way + 3/way +
     *  5), XORed in the same fold0/fold1<<1 pattern
     *  VtageTables::computeTag() uses for tagged components. */
    uint64_t computeBaseTag(uint64_t shiftedPc, unsigned way) const;

    /** Longest-match search: tagged components longest-to-shortest,
     *  then VT0's two ways (way 0 then way 1). Provider::found is
     *  false only when nothing tag-matches anywhere. */
    Provider findProvider(Addr pc, MicroPC upc, const VpHistSnapshot &h) const;

    /** rank: 0 = no provider, 1 = VT0, 2..(1+numTagged) = tagged.
     *  way/index/tag are the provider's own (way unused for rank !=
     *  1). */
    uint64_t packToken(unsigned rank, unsigned way, unsigned index,
                       uint64_t tag) const;
    UnpackedToken unpackToken(uint64_t token) const;

    /** classifier-driven LOWVAL: 0 = large, 1 = small (fits a signed
     *  16-bit range doubled), 2 = exactly zero (design doc S1,
     *  verbatim K32 macro). */
    static unsigned lowVal(RegVal value);

    /** The FASTINST term used broadly across E/E'/E_u: for a load,
     *  memLevel == Stlf; for a non-load, !slowInst (true for both
     *  genuine alu (fastInst) and the store/undef "alu-like" fallback
     *  -- design doc S1's class-dispatch note). */
    static bool fastInstBit(const EVtageClassifier &c);
    static bool notL1Miss(const EVtageClassifier &c);
    static bool notL2Miss(const EVtageClassifier &c);
    static bool notLlcMiss(const EVtageClassifier &c);

    /** S1's confidence-increment exponent E (verbatim K32 transcription
     *  -- eves-code-brief.md S2). */
    static unsigned confidenceExponent(const EVtageClassifier &c);
    /** S3's allocation-body exponent E' (NOT S1's E: no load-side
     *  doubling, no non-load additive +1 -- verbatim K32
     *  transcription). */
    static unsigned allocationExponent(const EVtageClassifier &c);
    /** S4's usefulness-update exponent E_u (verbatim K32
     *  transcription -- eves-code-brief.md S5). */
    static unsigned uExponent(const EVtageClassifier &c);

    /** Mask-based gate "(random() & ((1<<E)-1)) == 0", reimplemented
     *  against the injected [0,1) rng: always consumes exactly one
     *  draw (matching C's evaluation order -- random() is called
     *  unconditionally as part of the expression, even when the mask
     *  is 0), firing unconditionally when exponent == 0 (mask 0: any
     *  value ANDed with 0 is 0) regardless of what that draw was. */
    bool maskFires(unsigned exponent);

    /** The classifier-driven confidence gate (S1): dispatches
     *  isIndirectCall to deterministic true, else draws maskFires() on
     *  confidenceExponent(), doubled (OR of two independent draws) via
     *  the K32 rule when the provider is rank 1 (VT0, either way) --
     *  matches the raw source's `HitBank <= 1` exactly: CVP's banks 0
     *  and 1 are themselves the two zero-history base ways (see
     *  landProviderExists's doc comment), both of which this core
     *  collapses to providerIsVt0 == true. */
    bool confidenceGateFires(const EVtageClassifier &c, bool providerIsVt0);

    /** S4's UPDATEU probabilistic exploration-credit draw (dispatch:
     *  isIndirectCall deterministic true; else gated on
     *  !classifier.deliveredCorrect, matching C's `&&` short-circuit
     *  -- no draw consumed when deliveredCorrect is true). */
    bool updateUFires(const EVtageClassifier &c);

    /** S3's allocation gate: the outer operand gate (alu/store/undef
     *  only) times the E'-body draw, OR'd with `medConf` -- always
     *  false for a "no provider" train (no entry to be MedConf about).
     *  isIndirectCall is deterministic true overall. The outer gate's
     *  own draw, when it applies, always consumes exactly one rng()
     *  call; the body's E' draw is always attempted (even when
     *  medConf is already true), matching C's `||` left-to-right
     *  evaluation of `draw() || MedConf`. */
    bool shouldAllocate(const EVtageClassifier &c, bool medConf);

    /** S3's landing rule, "provider exists" arm (rank r >= 1): DEP =
     *  providerBankInternal + 1 (+1 w.p. 1/8), in OUR internal bank
     *  units (0 = VT0, 1..numTagged = VT1..VTnumTagged) -- a VT0
     *  provider lands starting at VT1, a VTk provider at VT(k+1),
     *  exactly the design doc's "DEP = r + 1". (CVP's raw source
     *  needs an extra "+1 if HitBank == 0" bump that this core does
     *  NOT replicate: CVP's own bank 0 and bank 1 are the two
     *  zero-history base ways -- see mypredictor.h's `HL[NHIST+1] =
     *  {0, 0, 3, 7, ...}` -- so CVP's bump exists only to align base
     *  way 0 with way 1's already-correct DEP = 2, i.e. CVP's own
     *  first tagged bank; it is not an extra shift into tagged
     *  territory. This core already collapses both base ways to
     *  providerBankInternal == 0 and starts tagged numbering one bank
     *  lower than CVP's raw numbering, so no analogous bump belongs
     *  here -- an earlier, now-corrected version of this code added
     *  one anyway, from a misread of CVP's HitBank numbering, which
     *  silently made VT1 permanently unreachable.) Scans internal tagged
     *  banks starting at DEP for the first u == 0 && (c == confMax/2
     *  || c <= draw7()) candidate, steals it (seed c = confMax/2, no
     *  zero-operand-ALU special case), and updates NA/ALL/outcomes. */
    void landProviderExists(unsigned providerBankInternal, Addr pc,
                            MicroPC upc, const VpHistSnapshot &h,
                            RegVal actual, const EVtageClassifier &classifier,
                            std::vector<EVtageTrainOutcome> &outcomes);

    /** S3's landing rule, "no provider" arm: 7/8 into VT0 (drawn way
     *  first, seed c = confMax/2 except the zero-operand-ALU special
     *  case seeding c = confMax), else 1/8 into the tagged banks,
     *  DEP = 1 (+1 w.p. 1/8, our internal bank units -- VT1 is the
     *  floor, matching CVP's first tagged bank; see
     *  landProviderExists's doc comment); no zero-operand-ALU special
     *  case in this sub-branch. */
    void landNoProvider(Addr pc, MicroPC upc, const VpHistSnapshot &h,
                        RegVal actual, const EVtageClassifier &classifier,
                        std::vector<EVtageTrainOutcome> &outcomes);

    /** A single steal-candidate scan step shared by both landing arms:
     *  u == 0 && (c == confMax/2 || c <= draw7()) -- draw7() (a
     *  "random() & confMax"-style draw) is only consumed when c !=
     *  confMax/2 (short-circuit, matching the C `||`). */
    bool candidateQualifies(const Entry &e);

    /** TICK += NA - 5*ALL (clamped >= 0); at tickMax, decrement every
     *  entry's nonzero u (all components, base ways included) and
     *  reset TICK, pushing TickPass. Called once per allocation
     *  attempt that actually ran a scan (design doc S4; matches the
     *  raw source's placement inside the "gate fired" block only). */
    void tickUpdate(int na, int all,
                   std::vector<EVtageTrainOutcome> &outcomes);

    const unsigned baseEntries;
    const unsigned baseWayEntries;
    const unsigned taggedEntries;
    const unsigned numTagged;
    const std::vector<unsigned> historyLengths;
    const unsigned baseTagBits;
    const unsigned confBits;
    const unsigned confMax;
    const unsigned confThreshold;
    const unsigned uBits;
    const unsigned uMax;
    const unsigned tickMax;
    const unsigned burstGuardWindow;
    const unsigned pathBits;

    const unsigned logBaseWayEntries;
    const unsigned logTaggedEntries;

    /** Reserved token field widths; sized as VtageTables's are, plus
     *  one `way` bit (S5, "1 way bit + 12-bit per-way index + 12-bit
     *  tag fits the existing 64-bit token carrier"). */
    static constexpr unsigned rankFieldBits = 4;
    static constexpr unsigned wayFieldBits = 1;
    static constexpr unsigned tagFieldBits = 20;
    const unsigned indexFieldBits;

    std::function<double()> rng;

    int tick = 0;

    /** base[way][index], way in {0, 1}. */
    std::vector<std::vector<Entry>> base;
    /** tagged[bank - 1][index], bank 1..numTagged. */
    std::vector<std::vector<Entry>> tagged;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_EVTAGE_TABLES_HH__
