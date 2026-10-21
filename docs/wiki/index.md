---
type: meta
status: current
updated: 2026-10-21
---

# Index

Catalog of every wiki page, by folder, one line each. Read this first when
answering a question. Conventions: [[SCHEMA]]. Timeline: [[log]].
Human-facing outputs: [[publish]].

## Overview

- [[overview]]: current thesis on agentic-workload CPU behaviour, with links to the evidence
- [[questions]]: open questions and candidate experiments

## Workloads

- [[agentic-suite]]: 27 OpenCode replay tasks (132 checkpoints), shape of the suite, headline metrics
- [[spec-cpu-2026]]: the 26 local SPEC SimPoints, how they behave, suite-size conflict with Garfield
- [[opencode-harness]]: processes, containers, threads, tool-call mechanics and costs, rounds

## Hardware

- [[neoverse-v2]]: the O3 core, cache and TLB configuration, `sim_opts` switches
- [[decoupled-front-end]]: BAC/FTQ, BTB-based branch detection, FDP and its iTLB lookups
- [[btb]]: the baseline BTB, gem5 BTB facts, how to measure BTB misses
- [[tlb-hierarchy]]: L1/L2 TLBs, zero-latency L2 hits, walk metrics
- [[infinite-btb-model]]: `InfiniteBTB` design, stats, validation
- [[infinite-l2-tlb]]: the 1M-entry L2 TLB, why stock `ArmTLB`, validation

## Infrastructure

- [[checkpoints]]: where they are, restore flow and arguments, provenance and landing
- [[task-tracer]]: the guest tracer: hooks, memory reads, KASLR, offsets, extending, limits
- [[trace-format]]: `tasktrace.jsonl` fields and events
- [[trace-analysis]]: `trace_analysis.py` outputs, who-ran-when, process labels, tool calls
- [[stats-blocks]]: `--stats-interval-insts`, `intervals.csv`, block size
- [[viewers]]: schedule timeline and window-metrics pages
- [[sweeps]]: `sweep.sh`/`smart_sweep.sh`, summaries, multi-sweep comparisons, known sweeps
- [[run-and-analysis-scripts]]: catalog of the launchers and readers
- [[running-a-traced-window]]: step-by-step commands

## Experiments

- [[2026-10-08-tool-call-windows]]: first O3 windows across a `read` and a `bash` call; user/kernel split; scheduler cost
- [[2026-10-14-event-windows]]: metrics around switches by cause (cpython, jq, redis)
- [[2026-10-14-baseline-sweep]]: SPEC vs agentic over 53 windows (baseline A)
- [[2026-10-14-fdp-off-sweep]]: FDP off, paired per checkpoint
- [[2026-10-16-btb-tlb-limit-study]]: infinite BTB, infinite L2 TLB, both; five-way sweeps; 100M skip

## Findings

*Provisional working hypotheses, expected to change: check the evidence before relying on one ([[SCHEMA#Findings are provisional]]).*

- [[agentic-front-end-bound]]: front-end misses separate agentic from SPEC
- [[btb-tlb-limits]]: ~3% each, ~7% together, agentic only
- [[fdp-value]]: FDP worth ~3% on agentic, ~0 on most SPEC
- [[agentic-ipc-variability]]: tight across tasks, unstable inside a window
- [[switch-cost-is-around-the-switch]]: scheduler is cheap; cold start and kernel work are not
- [[tool-call-runup-is-cold]]: *(draft)* the harness is coldest before a tool call

## Methodology

- [[window-placement]]: atomic first, O3 moves events, settle margins
- [[warmup-and-skip]]: 20M warm-up and the 100M skip for unbounded structures
- [[aggregating-metrics]]: sum counts, harmonic means, CV caveats
- [[comparing-configurations]]: paired per-checkpoint medians, suite-level reading
- [[validation-checks]]: no-perturbation, determinism, landing, intervals, counters
- [[instruction-counts]]: `insts` vs `uinsts` vs stats vs micro-ops
- [[context-switch-classification]]: thread/process/kernel by `tgid`, `via` kernel

## Pitfalls

- [[l2-tlb-disconnected]]: every L1 TLB miss walked before 2026-10-13
- [[functional-translation-perturbs]]: `TranslatingPortProxy` changes TLB state
- [[btb-miss-stat-zero-decoupled]]: `btb.misses` is 0 with the decoupled front end
- [[walk-requests-vs-completed]]: `walker.walks` is ~4× the real walks
- [[fdp-inflates-itlb-misses]]: FDP-on iTLB MPKI is mostly dropped prefetch lookups
- [[replay-polling-in-measurement]]: ~1/5 of agentic instructions are Docker polling
- [[metric-shift-is-not-event-effect]]: phase changes and mixed causes
- [[restore-silent-failures]]: restores that run and give wrong numbers
- [[sweep-memory-exhaustion]]: parallel sweeps and the OOM killer
- [[gem5-tracing-under-kaslr]]: why gem5's own tracing features do not work here
- [[o3-wrong-path-counting]]: verify-site counters and training see doomed instructions
- [[simulation-hangs]]: the ROB-head watchdog, the FDP MaxAddr hang, how to tell a hang from a livelock

## gem5

- [[gem5-overview]]: what gem5 is, this fork's branches, source tree map
- [[building]]: SCons configs and variants, KConfig, `build-gem5.sh` note
- [[testing]]: C++ unit, Python unit and regression tests
- [[contributing]]: C++/Python style, pre-commit, commit-message format, naming gate
- [[simobject-model]]: the Python description, C++ class and SConscript triple
- [[scons-codegen]]: SConscript helpers, generated headers, debug flags
- [[python-layers]]: `m5` vs the stdlib, running a config, SE vs FS
- [[simulation-core]]: event queue, ports and packets, base infrastructure
- [[isa-dsl]]: per-ISA layout, the `.isa` DSL, fork-specific Arm code
- [[memory-system]]: classic caches vs Ruby/SLICC

## Garfield (reference)

- [[garfield-overview]]: the closed lazy-execution project: idea, what happened per stage, code left in the tree, conflicts
- [[ghost-execution]]: Stage 1, ghost accounting and the headroom methodology
- [[memory-renaming]]: Stage 2, MRN up to the value-file rendezvous (1.0092), and why it closed
- [[value-prediction]]: Stage 3, the VP framework, LVP, VTAGE, E-VTAGE (1.0238), EVES
- [[garfield-lessons]]: what transfers: measuring, trusting the simulator, O3 facts, FS restores

## Sources outside the wiki

- [[raw/README|raw/]]: immutable external sources
- [[legacy-log/README|legacy-log/]]: frozen pre-wiki notebooks
