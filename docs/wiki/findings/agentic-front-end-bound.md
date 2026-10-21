---
type: finding
status: current
updated: 2026-10-21
sources:
  - "[[2026-10-14-baseline-sweep]]"
  - "[[2026-10-14-fdp-off-sweep]]"
  - "[[2026-10-16-btb-tlb-limit-study]]"
tags: [front-end, agentic, btb, icache, itlb]
---

# Agentic windows are front-end bound; SPEC is not

> [!warning] Provisional finding
> Findings are working hypotheses from a few sweeps and windows, and they
> change as new runs arrive. Check the evidence and its caveats before
> relying on this; challenge it when new data disagrees
> ([[SCHEMA#Findings are provisional]]).

**Claim:** on the [[neoverse-v2]] model, the agentic workloads lose
performance in the front end (instruction cache, instruction TLB, BTB
detection) far more than SPEC CPU 2026 does, and front-end improvements
help agentic while leaving SPEC flat. Confidence: high for the miss rates
(53 checkpoints, consistent across configurations); medium for how much of
the IPC gap they explain (no top-down breakdown yet).

## Evidence

| | agentic | SPEC | source |
|---|---|---|---|
| L1I MPKI | 1.74 | 0.01 | [[2026-10-14-baseline-sweep]] |
| iTLB MPKI without FDP (demand) | 2.9 | 0.02 | [[2026-10-14-fdp-off-sweep]] |
| BTB-miss mispredicts PKI | 1.13 | 0.005 | baseline |
| I-cache stall cycles | 22% of cycles | – | baseline |
| FDP worth (IPC) | +2.8% | +0.2% | [[fdp-value]] |
| infinite BTB / L2 TLB / both (IPC) | +3.1 / +3.1 / +6.4–7.5% | +0.1 / 0.0 / +0.1% | [[btb-tlb-limits]] |

- Little overlap between the suites on L1I, iTLB and BTB misses; the SPEC
  runs that come close (gcc, cpython, gem5, llvm, vpr, ns3) are the
  large-code ones, and they are the only SPEC runs that react to FDP, BTB or
  TLB changes.
- Likely causes (interpretation): large, JIT-compiled and frequently
  changing code (Bun/JSC in OpenCode, short-lived Go/shell processes,
  compilers), many address spaces sharing one BTB and TLB, and context
  switches that leave the next task cold ([[switch-cost-is-around-the-switch]]).

## Caveats

- FDP-on iTLB MPKI is inflated by prefetch lookups
  ([[fdp-inflates-itlb-misses]]); compare demand-side metrics.
- About a fifth of the agentic instructions are the replay driver's Docker
  polling, itself a short-lived-process workload
  ([[replay-polling-in-measurement]]); the comparisons include it.
- The back end is not ruled out: agentic L1D miss latency is 112 cycles vs
  54 for SPEC, and L2 MPKI is high. A top-down breakdown is open
  ([[questions]]).
- One 400M window per agentic task (`cpt.0` only).
