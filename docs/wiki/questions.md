---
type: overview
status: current
updated: 2026-10-27
sources:
  - "[[2026-10-16-btb-tlb-limit-study]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [agentic, open-questions]
---

# Open questions

Each entry: the question, where it came from, and the experiment that would
answer it; the current thesis they bear on is in [[overview]]. Move an entry to its experiment page when work starts; strike it
here when answered, with a link.

## Front end and limits

- **What do compulsory BTB misses cost?** Pass-1/pass-2 oracle: dump
  `(space, PC, encoding)` of every branch, preload in a second run.
  ([[infinite-btb-model]], [[btb-tlb-limits]])
- **How much of the infinite-TLB gain goes through FDP?** Sweep
  `--disable-fdp --infinite-tlb` against `--disable-fdp`.
  ([[infinite-l2-tlb]], [[fdp-inflates-itlb-misses]])
- **Why does 714.cpython_r lose 3.4% with the infinite BTB?**
  ([[2026-10-16-btb-tlb-limit-study]])
- **Is carbon-2752's −0.9% with the infinite BTB only a work-mix effect?**
  The clocked replay lays the window out differently after ~180M. A
  PC-matched comparison of the main OpenCode thread would settle it.
  ([[2026-10-16-btb-tlb-limit-study]], [[pc-trace]])
- **Where does the rest of the agentic IPC gap come from?** A top-down
  breakdown (the window view shows top-down L1 when the build has it);
  check the back end (L1D miss latency 112 vs 54 cycles, L2 MPKI).
  ([[agentic-front-end-bound]])
- **What realistic structures get close to the ceilings?** Larger or
  ASID-tagged BTBs, a modelled L2 TLB latency, better instruction
  prefetching for JIT and short-lived code.

## Workload and measurement

- **Investigate the long-run guest hang** ([[guest-trng-hvc-stall]]):
  the TRNG-HVC explanation is a hypothesis from one checkpoint. Confirm it
  (the SMCCC function ID, why the stub loops, other checkpoints and their
  hang times), then fix it: make gem5 answer (or refuse) the SMCCC TRNG
  call at EL2, or change the guest. Also check
  which sweep windows, if any, crossed a reseed deadline (a task trace that
  ends early).
- **PC-trace metrics of the 15G rubocop runs**: footprint and branches done
  ([[2026-10-26-rubocop-instruction-footprint]]); still PC repeat distance; and whether OpenCode's lower MPKI in
  slow configurations is polling ([[2026-10-23-rubocop-15g-cache-btb-tlb]]).
- **Per-phase comparison of configurations** (tool calls, rounds) instead
  of a fixed instruction count, since the work mix shifts
  ([[comparing-configurations]]).

- **How representative is one window per task?** Use the other 4 dumps of
  each task; see how the ceilings vary. ([[agentic-ipc-variability]])
- **Agentic numbers without the replay driver's polling.** Report the sweep
  metrics with the `run.sh` tree excluded; check whether the live capture
  polled at the same rate. ([[replay-polling-in-measurement]])
- **Switch cost per cause, suite-wide**, from the existing sweep traces.
  ([[switch-cost-is-around-the-switch]], [[2026-10-14-event-windows]])
- **Tool-call phases across many calls** on the current build (only one
  call per checkpoint so far, before the L2 TLB fix).
  ([[tool-call-runup-is-cold]])
- **Effect of the single vCPU** on switch counts and costs.
- **How much does the harness itself cost, and does the runtime matter?**
  Compare harnesses (OpenCode on Bun, a Node.js harness, a native Rust
  harness, a Python one) on the same tasks by instructions and cycles per
  agent step, not by IPC; first with `perf` on real Arm hardware, before
  capturing checkpoints. OpenCode's direct JIT share is ~7% of
  instructions and ~8.5% of switches ([[2026-10-22-opencode-thread-breakdown]]).

## Tooling

- `window_view.py`'s "BTB misses" row reads `btb.misses`, always 0 in
  decoupled mode: switch it to `mispredictDueToBTBMiss` or drop it?
  ([[btb-miss-stat-zero-decoupled]])
- `trace_analysis.py`'s `blocks.csv` has walk requests only; add completed
  walks. ([[walk-requests-vs-completed]])
- Record command lines of pre-existing processes in the tracer snapshot
  (`mm->arg_start..arg_end`) and the task running at the restore.
  ([[task-tracer#Known limits]])
