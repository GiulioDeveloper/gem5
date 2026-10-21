---
type: method
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
tags: [methodology, validation, determinism]
---

# Validation checks you can repeat

Run the relevant check after any change to the tracer, the restore path or
a model that should be inert by default.

| check | how | expected | last result |
|---|---|---|---|
| **No perturbation** | `o3-pair.sh` (same short O3 window with and without `--task-trace`; diff `stats.txt` ignoring `host*`) | identical | identical: gin-2121 1M+5M (IPC 0.635), framework-52684 1M+60M, 107 switches (IPC 0.854) |
| **Determinism** | `PAIR_ON_ARGS= o3-pair.sh` (plain config twice), or two atomic runs | identical stats / traces | identical (398 switches in the atomic pair) |
| **Landing** | `landing-all.sh` + `landing_summary.py`: first `switch`'s `prev` and the derived slide against `provenance.json`; if no switch, the landing task must be in the snapshot | same pid, thread name, slide; a rename by an exec before the first switch is legitimate | 22 of 22 labelled checkpoints in one 3M-instruction pass (2026-10-08) |
| **Intervals** | same region with and without `--stats-interval-insts` | same region IPC | same (0.635) |
| **User/kernel split** | `summary.md` of a blocks run | `user_frac_trace` ≈ gem5 `user_frac`; user + kernel = span | mean abs. difference 0.05 (even-spread assumption inside slices) |
| **Counters vs Exec trace** | `--debug-flags=ExecEnable,ExecUser,ExecKernel,ExecMacro` over a short window; classify lines by PC | `insts`, `uinsts`, `sched_insts` deltas match exactly (NOPs excluded) | exact over 14 intervals, 828,936 instructions (2026-10-13) |
| **Default model unchanged** | rerun a baseline sweep window after adding an optional model | bit-identical to the earlier sweep | fmt-3901 with the InfiniteBTB plumbing (2026-10-16) |

Also: the restore itself needs a positive guest signal, not "it didn't
crash" ([[restore-silent-failures]]).

The general pattern (prove an inert-by-default change is bit-identical
before measuring with it) comes from Garfield ([[garfield-lessons]]).
