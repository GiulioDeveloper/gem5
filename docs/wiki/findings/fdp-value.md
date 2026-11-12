---
type: finding
status: current
updated: 2026-11-12
sources:
  - "[[2026-10-14-fdp-off-sweep]]"
  - "[[2026-11-12-miss-count-vs-miss-cost]]"
tags: [fdp, front-end, prefetch]
---

# FDP is worth ~3% on agentic and ~nothing on most SPEC

> [!warning] Provisional finding
> Findings are working hypotheses from a few sweeps and windows, and they
> change as new runs arrive. Check the evidence and its caveats before
> relying on this; challenge it when new data disagrees
> ([[SCHEMA#Findings are provisional]]).

**Claim:** the [[decoupled-front-end]] with fetch-directed prefetching
gives the median agentic window +2.8% IPC (FDP off: −2.8% [−4.3, −1.6]) and
SPEC +0.2%. It recovers about half the agentic L1I misses (L1I MPKI 4.03
without, 1.74 with) and cuts I-cache stall cycles by about a third, but
agentic still stalls on the I-cache for 22% of cycles with it.

- Agentic range −2.6% (gson, lombok) to +11.7% (micropython).
- SPEC gains only on large code: cpython +23.6%, gem5 +20.7%, llvm +7.8%.
- Costs: a quarter of agentic L2 misses are FDP prefetch traffic, and its
  translations dominate iTLB miss counts ([[fdp-inflates-itlb-misses]]).
- FDP's coverage of L1I misses is 0.79 on agentic and 0.96 on SPEC;
  accuracy 0.30 vs 0.21 ([[2026-10-14-baseline-sweep]]).

Why so little for so many misses (1B sweeps, [[2026-11-12-miss-count-vs-miss-cost]]):
FDP off adds only about 2 misses per 1,000 instructions, mostly L2 hits
(primary latency 56 cycles, against 112 for the misses FDP leaves). About
78% of the extra fetch-stall cycles overlap with back-end stalls, and
back-end bound falls by about 12 cycle-equivalents per 1,000 instructions
without FDP's L2 traffic. Net: about 13 cycles per extra miss.

Implication (interpretation): FDP depends on BTB detection, so a better BTB
or prefetch translations that hit make FDP more useful; the limit-study
gains are partly FDP gains ([[btb-tlb-limits]]).
