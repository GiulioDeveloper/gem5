---
type: entity
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - configs/garfield/arm/fs_run.py
  - /home/snapshots/gem5-ckpts/fs_ckpts/spec26/ckpts/
tags: [spec, workload, checkpoints, reference]
---

# SPEC CPU 2026 (reference suite)

**Role:** the conventional baseline the [[agentic-suite]] is compared
against. Full-system SimPoint checkpoints, restored with `fs_run.py` on the
same Neoverse V2 model ([[neoverse-v2]]) and the same guest kernel binary,
so the [[task-tracer]] works on them unchanged.

**Locally:** 26 benchmarks, **one SimPoint checkpoint each**, in
`/home/snapshots/gem5-ckpts/fs_ckpts/spec26/ckpts/<bench>/<inv>/cpt.*`:
706.stockfish_r, 707.ntest_r, 708.sqlite_r, 709.cactus_r, 710.omnetpp_r,
714.cpython_r, 721.gcc_r, 722.palm_r, 723.llvm_r, 727.cppcheck_r, 729.abc_r,
731.astcenc_r, 734.vpr_r, 735.gem5_r, 736.ocio_r, 737.gmsh_r,
748.flightdm_r, 749.fotonik3d_r, 750.sealcrypto_r, 753.ns3_r, 765.roms_r,
766.femflow_r, 767.nest_r, 772.marian_r, 777.zstd_r, 782.lbm_r.
`spec-window.sh` restores the first `cpt.*` found per benchmark.

> [!conflict] Suite size
> The Garfield reports used 190 SPEC CPU 2026 SimPoint checkpoints (several
> per benchmark and input; "26 benchmarks" in the MRN/LVP reports, "43
> workloads" in the EVES report). Those lived on another host. The agentic
> sweeps use the 26 single checkpoints above, so a Garfield suite-level
> number and an agentic-era SPEC number are not over the same set.

## Behaviour

- The benchmark runs alone, under the console login's launch tree
  (`login > bash > after_boot.sh > <benchmark>`), and is almost never
  switched out (2 switches in 200M O3 instructions of 729.abc_r, none in
  714.cpython_r). With no switch the trace has a single `not recorded`
  slice ([[trace-analysis]]).
- 100% user mode; front-end misses near zero except large-code benchmarks
  (gcc, cpython, gem5, llvm, vpr, ns3), which are the only SPEC runs that
  react to FDP, BTB or TLB changes ([[fdp-value]], [[btb-tlb-limits]]).
- IPC spreads widely across benchmarks (0.47 cactus to 3.17 marian) but is
  stable inside a window (median IPC CV 0.12 against 0.36 for agentic).
- Windows are 200M detailed instructions in the sweeps, so skipping 100M
  halves them ([[warmup-and-skip]]).
- 714.cpython_r shows a phase change (L1I MPKI 0.34 → 0.50 at 64.8M) with no
  scheduling event: the control case of [[metric-shift-is-not-event-effect]].
