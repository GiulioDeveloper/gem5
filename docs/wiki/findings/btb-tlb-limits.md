---
type: finding
status: current
updated: 2026-10-25
sources:
  - "[[2026-10-16-btb-tlb-limit-study]]"
  - "[[2026-10-23-rubocop-15g-cache-btb-tlb]]"
tags: [btb, tlb, limit-study, front-end]
---

# Removing BTB and L2-TLB capacity limits gains ~3% each, ~7% together, on agentic only

> [!warning] Provisional finding
> Findings are working hypotheses from a few sweeps and windows, and they
> change as new runs arrive. Check the evidence and its caveats before
> relying on this; challenge it when new data disagrees
> ([[SCHEMA#Findings are provisional]]).

**Claim:** with an unbounded, ASID-separated BTB the median agentic window
gains +3.1% IPC; with an effectively perfect L2 TLB +3.1%; with both
+6.4% (+7.5% with 100M more warm-up, then more than the sum). Every agentic
task gains with both (+0.3% to +13.2%). SPEC's median moves by 0.1%.

| agentic median | inf-BTB | inf-TLB | both | both, skip 100M |
|---|---|---|---|---|
| IPC | +3.1% | +3.1% | +6.4% | +7.5% |
| BTB-miss mispredicts | −75% | 0 | −75% | −78% |
| completed page walks | 0 | −79% | −79% | −80% |
| L1I MPKI | −34% | 0 | −37% | |
| L2 MPKI | −16% | −2% | −18% | −19% |

## Reading

- The two bottlenecks look **independent**: the gains add up, and grow
  together with warm-up.
- These are **ceilings for capacity, conflict and aliasing**; compulsory
  misses remain, and neither model has latency. A pass-1/pass-2 oracle
  would give the compulsory part ([[questions]]).
- **Side effects carry part of the gain:** the infinite BTB cuts L1I and L2
  misses (fewer wrong fall-through fetches and prefetches); the infinite
  L2 TLB lets more FDP prefetch translations hit (iTLB MPKI −27%).
- SPEC exceptions are large-code programs (gcc +10.3% with both);
  714.cpython_r *loses* 3.4% with the infinite BTB (unexplained).
- Top agentic gainers with both: redis +13.2%, rubocop +11.9%, framework
  +11.6%.

- **Long run, one task** ([[2026-10-23-rubocop-15g-cache-btb-tlb]], 12–15G
  instructions of rubocop): both together gain +2–11% per process (+7%
  for OpenCode, +9.8% over the whole common region). ×8 L1/L2 caches gain
  more (+12–25% per process), and the two add up. Whole-window comparisons
  there are confounded by a shift in work mix.

Models: [[infinite-btb-model]], [[infinite-l2-tlb]]. Context:
[[agentic-front-end-bound]].
