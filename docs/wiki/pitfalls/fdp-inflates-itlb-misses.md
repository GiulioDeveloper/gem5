---
type: pitfall
status: current
updated: 2026-10-28
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [tlb, fdp, prefetch, front-end]
---

# With FDP on, iTLB MPKI is mostly prefetch lookups

**The trap:** the FDP prefetcher translates its targets through the L1
iTLB. A prefetch translation that misses is counted as a TLB miss **and
then dropped** (`PrefetchTLBMiss`, no walk, no fill;
`src/arch/arm/mmu.cc:1723`). So iTLB MPKI with FDP is not a demand-miss
rate.

**Size:** median agentic iTLB MPKI 37 with FDP, 2.9 without (−92%); SPEC
0.16 → 0.02. A quarter of agentic L2 misses are FDP prefetch traffic too
([[2026-10-14-fdp-off-sweep]]).

**Decomposition** (rubocop 15G `normal`, 11.3–11.7G instructions, 2,000
blocks): `mmu.itb.misses` 39.1 PKI = `itb.inserts` 5.9 +
`mmu.prefetchFaults` 33.0. Short-lived tools are the worst: bash 71 = 6.5
+ 64, tail 73 = 6.3 + 66, cat 54 = 4.5 + 49, against L1I misses of 3.4–3.9
PKI. `inserts` is not demand-only either: a prefetch lookup that hits the
L2 TLB is copied into the L1 iTLB (`TLB::multiLookup`). Completed
instruction walks are 0.2–0.4 PKI, below the L1I miss rate.

**Use instead:** completed page walks for the demand side
([[walk-requests-vs-completed]]); compare iTLB MPKI only between runs with
the same FDP setting. Even without FDP, agentic iTLB MPKI is about 140×
SPEC's, so the front-end gap is real ([[agentic-front-end-bound]]).

**Knock-on:** structures that make prefetch translations hit (a larger L2
TLB) also help FDP, so part of a TLB gain is a prefetch gain
([[infinite-l2-tlb]]).
