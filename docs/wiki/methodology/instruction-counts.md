---
type: method
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [methodology, counters]
---

# Instruction counts: which one is which

| count | source | basis |
|---|---|---|
| `insts` (trace, `intervals.csv`) | `BaseCPU::totalNumSimulatedInsts()`, sum over all CPUs since the restore | O3 excludes NOPs and instruction prefetches (as gem5's `totalInsts()` always has); **atomic counts NOPs**. Never reset by `m5.stats.reset()`; continues across core switches |
| `uinsts` (trace) | `BaseCPU::userInsts()`, a fork counter incremented in the simple, O3 (`CPU::instDone`), Minor and KVM CPUs | same basis as `insts`; never reset. `insts − uinsts` = kernel-mode (EL1) instructions |
| `commitStats0.numInsts`, `numUserInsts` (stats) | per-block stats | **include** NOPs, so do not mix them with `insts`; use `numUserInsts / numInsts` for a ratio |
| progress line "total committed" | `totalOps()` | micro-ops: about 12% above `insts` |

- NOPs were about 2% of instructions in one checked window, so the global
  count changes basis slightly at the atomic → O3 switch.
- The first `uinsts` version counted next to `numUserInsts` and gave
  negative kernel work (−1 to −3%) for pure user slices; the O3 increment
  moved to `CPU::instDone`. After the fix, a long `rg` slice's kernel share
  matched gem5's stats (54.1% vs 54.2%).
- Ticks are 1 ps; at 3 GHz a cycle is 333.3 ticks. On the atomic core
  every instruction is one cycle, so simulated time there is not
  comparable with real time; instruction counts are the meaningful unit.
- O3's Exec trace prints the **fetch** tick, the tracer the **commit** tick
  (10–150 ns apart).
