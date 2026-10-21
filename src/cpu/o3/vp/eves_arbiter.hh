#ifndef __CPU_O3_VP_EVES_ARBITER_HH__
#define __CPU_O3_VP_EVES_ARBITER_HH__

#include <optional>

#include "base/types.hh"

namespace gem5
{
namespace o3
{

/**
 * EVES component arbitration (design doc docs/legacy-log/superpowers/specs/
 * 2026-08-14-estride-design.md, "Arbitration and token"): pure
 * function over POD inputs so every flag/mode combination is directly
 * GTest-able. Reproduces the CVP-1 source's write-order mechanism
 * (getPredStride first, getPredVtage second overwriting the value,
 * cc:136-144): with overwriteRequiresConfidence false (the
 * source-verbatim mode, opt-in since the 190-checkpoint A/B showed
 * confidence-gating wins by +3.6% -- the composition report,
 * docs/legacy-log/research-log/VP/2026-08-15-eves-estride-composition.md), a
 * VTAGE tag hit outside the blackout overwrites the stride value
 * even below VTAGE confidence -- delivery still requires a component
 * flag (stride or VTAGE confident), matching the source's
 * predstride || predvtage use-bit.
 */
struct EvesArbiterIn
{
    bool stridePredicted = false;
    RegVal strideValue = 0;
    bool vtageHit = false;
    bool vtageConfident = false; // implies vtageHit
    RegVal vtageValue = 0;
    bool blackoutActive = false;
    bool overwriteRequiresConfidence = true;
};

struct EvesArbiterOut
{
    std::optional<RegVal> value;   // engaged iff delivering
    bool stridePredicted = false;  // CVP predstride (token bit)
    bool vtageConfident = false;   // CVP predvtage (token bit)
    bool deliveredByVtage = false; // gem5-only routing (token bit)
};

inline EvesArbiterOut
evesArbitrate(const EvesArbiterIn &in)
{
    EvesArbiterOut out;
    // The blackout suppresses the WHOLE VTAGE contribution -- value
    // and flag -- as in the source's LastMispVT >= 128 wrapper
    // (cc:44-55).
    const bool vtage_contributes = in.vtageHit && !in.blackoutActive;
    const bool overwrite =
        vtage_contributes &&
        (!in.overwriteRequiresConfidence || in.vtageConfident);
    out.stridePredicted = in.stridePredicted;
    out.vtageConfident = in.vtageConfident && !in.blackoutActive;
    if (out.stridePredicted || out.vtageConfident) {
        out.value = overwrite ? in.vtageValue : in.strideValue;
        out.deliveredByVtage = overwrite;
    }
    return out;
}

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_EVES_ARBITER_HH__
