#ifndef __CPU_O3_VP_VP_INFLIGHT_MAP_HH__
#define __CPU_O3_VP_VP_INFLIGHT_MAP_HH__

#include <cstdint>
#include <unordered_map>

#include "base/logging.hh"

namespace gem5
{
namespace o3
{

/**
 * Exact per-key in-flight occurrence counts for value predictors that
 * extrapolate over speculative same-PC occurrences (design doc
 * docs/legacy-log/superpowers/specs/2026-08-14-estride-design.md, the
 * in-flight counter subsystem): an exact replacement for CVP-1 EVES's 256-deep
 * ring scan, which double-counts past 256 in flight and can match
 * stale slots. Keys are folded vpKey values (vp_key.hh). Erases on
 * zero so size() tracks only keys with live occurrences. Panics on
 * decrement-underflow: the pipeline hook sites guarantee one
 * decrement per increment (the VpInflightCounted DynInst flag), so
 * underflow is always a closure bug, never legal state.
 */
class VpInflightMap
{
  public:
    void
    increment(uint64_t key)
    {
        counts[key]++;
    }

    void
    decrement(uint64_t key)
    {
        auto it = counts.find(key);
        panic_if(it == counts.end() || it->second == 0,
                 "VP in-flight counter underflow for key %#x", key);
        if (--it->second == 0) {
            counts.erase(it);
        }
    }

    uint32_t
    count(uint64_t key) const
    {
        auto it = counts.find(key);
        return it == counts.end() ? 0 : it->second;
    }

    size_t
    size() const
    {
        return counts.size();
    }

  private:
    std::unordered_map<uint64_t, uint32_t> counts;
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_VP_VP_INFLIGHT_MAP_HH__
