---
type: overview
status: current
updated: 2026-10-21
sources:
  - "[[agentic-front-end-bound]]"
  - "[[btb-tlb-limits]]"
  - "[[fdp-value]]"
  - "[[switch-cost-is-around-the-switch]]"
  - "[[agentic-ipc-variability]]"
tags: [agentic, thesis]
---

# Overview: CPU architecture for agentic workloads

**The question:** how do AI coding agents use a server-class out-of-order
core, and what would make that core run them better? The workloads are
OpenCode agents replayed model-free on SWE-bench-Multilingual tasks
([[agentic-suite]], [[opencode-harness]]); the core is a Neoverse V2 model
with a decoupled front end ([[neoverse-v2]]); SPEC CPU 2026 is the
reference ([[spec-cpu-2026]]).

## Current thesis (2026-10-21)

> [!warning] Provisional
> This thesis is built from provisional findings and will change with new
> runs ([[SCHEMA#Findings are provisional]]).

1. **Agentic execution is front-end bound in a way SPEC is not.** L1I,
   iTLB and BTB misses are two orders of magnitude above SPEC; agentic IPC
   is about two-thirds of SPEC's (0.99 vs 1.52 median). Front-end help (FDP,
   a bigger BTB, a bigger L2 TLB) moves agentic IPC and leaves SPEC flat.
   → [[agentic-front-end-bound]]
2. **The headroom from capacity alone is ~7%.** An unbounded BTB and an
   unbounded L2 TLB each give ~3%; together 6.4–7.5%, and every task gains.
   These ceilings exclude compulsory misses and latency.
   → [[btb-tlb-limits]], [[fdp-value]]
3. **Agentic code is many short, cold phases.** IPC is steady across tasks
   but swings inside a window; low blocks line up with process churn,
   short-lived processes and the run-up to tool calls. The scheduler is
   cheap; the cold start around a switch is not, and it depends on who
   runs. → [[agentic-ipc-variability]], [[switch-cost-is-around-the-switch]],
   [[tool-call-runup-is-cold]]
4. **The measurement includes benchmark harness work.** About a fifth of
   agentic instructions are the replay driver polling Docker; numbers must be
   read with and without it. → [[replay-polling-in-measurement]]

## How we know (and its limits)

- One 400M window per task (`cpt.0`), 20M warm-up, single vCPU; per-checkpoint
  paired comparisons across full sweeps ([[comparing-configurations]],
  [[sweeps]]).
- A non-perturbing guest tracer gives every switch, exec and tool call in
  ticks and instructions ([[task-tracer]]), joined with 200K-instruction
  stats blocks ([[stats-blocks]]).
- Results before 2026-10-13 had the L2 TLB disconnected
  ([[l2-tlb-disconnected]]); the sweeps are after the fix.
- No top-down breakdown yet; the back end (L1D miss latency 112 cycles) is
  not ruled out.

## Where to go next

[[questions]]. Garfield, the earlier project on this fork, is the
reference for O3 pitfalls and methodology ([[garfield-overview]]).
