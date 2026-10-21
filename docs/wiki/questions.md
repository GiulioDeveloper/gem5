---
type: overview
status: current
updated: 2026-10-21
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
- **Where does the rest of the agentic IPC gap come from?** A top-down
  breakdown (the window view shows top-down L1 when the build has it);
  check the back end (L1D miss latency 112 vs 54 cycles, L2 MPKI).
  ([[agentic-front-end-bound]])
- **What realistic structures get close to the ceilings?** Larger or
  ASID-tagged BTBs, a modelled L2 TLB latency, better instruction
  prefetching for JIT and short-lived code.

## Workload and measurement

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

## Tooling

- `window_view.py`'s "BTB misses" row reads `btb.misses`, always 0 in
  decoupled mode: switch it to `mispredictDueToBTBMiss` or drop it?
  ([[btb-miss-stat-zero-decoupled]])
- `trace_analysis.py`'s `blocks.csv` has walk requests only; add completed
  walks. ([[walk-requests-vs-completed]])
- Record command lines of pre-existing processes in the tracer snapshot
  (`mm->arg_start..arg_end`) and the task running at the restore.
  ([[task-tracer#Known limits]])
