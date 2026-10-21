#include <gtest/gtest.h>

#include "cpu/o3/vp/vp_inflight_map.hh"

using namespace gem5;
using namespace gem5::o3;

TEST(VpInflightMap, StartsEmptyAndCountsZero)
{
    VpInflightMap m;
    EXPECT_EQ(m.count(0x400123), 0u);
    EXPECT_EQ(m.size(), 0u);
}

TEST(VpInflightMap, IncrementDecrementRoundTrip)
{
    VpInflightMap m;
    m.increment(0x400123);
    m.increment(0x400123);
    m.increment(0x500777);
    EXPECT_EQ(m.count(0x400123), 2u);
    EXPECT_EQ(m.count(0x500777), 1u);
    EXPECT_EQ(m.size(), 2u);
    m.decrement(0x400123);
    EXPECT_EQ(m.count(0x400123), 1u);
    m.decrement(0x400123);
    // Erase-on-zero: the key is gone, not a zero-valued tombstone.
    EXPECT_EQ(m.count(0x400123), 0u);
    EXPECT_EQ(m.size(), 1u);
}

TEST(VpInflightMap, InterleavedRenameCommitSquashZeroSum)
{
    // Design doc
    // docs/legacy-log/superpowers/specs/2026-08-14-estride-design.md,
    // S4's zero-sum sequences: interleave two keys through
    // rename(+)/commit(-)/squash(-) orders, including a same-key
    // burst, and end drained.
    VpInflightMap m;
    const uint64_t a = 0xA, b = 0xB;
    m.increment(a);
    m.increment(a);
    m.increment(b); // rename x3
    m.decrement(a); // commit a#1
    m.increment(a); // rename a#3
    m.decrement(b); // squash b#1
    EXPECT_EQ(m.count(a), 2u);
    EXPECT_EQ(m.count(b), 0u);
    m.decrement(a);
    m.decrement(a); // squash walk
    EXPECT_EQ(m.size(), 0u);
}

// gem5's panic() throws (rather than aborts the process) when linked
// into a GTest binary (base/gtest/logging_mock.cc), so the map's
// panic_if underflow guard shows up here as a C++ exception, not
// process death -- EXPECT_ANY_THROW is the pattern the rest of the
// tree uses for this (e.g. base/stats/info.test.cc,
// vtage_tables.test.cc's ConfThresholdBelowOneIsFatal).
TEST(VpInflightMap, UnderflowPanics)
{
    VpInflightMap m;
    EXPECT_ANY_THROW(m.decrement(0xDEAD));
    m.increment(0xBEEF);
    m.decrement(0xBEEF);
    EXPECT_ANY_THROW(m.decrement(0xBEEF));
}
