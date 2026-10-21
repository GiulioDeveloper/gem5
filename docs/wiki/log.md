---
type: meta
status: current
updated: 2026-10-21
---

# Log

Append-only timeline of the wiki: ingests, experiments, queries, lint
passes, publishes, restructures. Newest last. Format: [[SCHEMA#log.md format]].

## [2026-10-21] restructure | Pass 1: knowledge base scaffold

Decided with the user: the knowledge moves to an LLM-maintained wiki
([[raw/llm-wiki]]). The current project is CPU architecture for agentic
workloads; Garfield is kept as a reference.

- Moved `docs/{research-log,garfield,superpowers,agentic,commit-notes}` to
  `docs/legacy-log/` (frozen, see [[legacy-log/README]]). Updated the path
  references in `src/`, `configs/`, the READMEs and the skills.
- Created `docs/raw/` (immutable sources) and the wiki: [[SCHEMA]],
  [[index]], this log, [[publish]], stubs for [[overview]] and [[questions]].
- Moved the gem5 technical material out of `CLAUDE.md` into `gem5/` pages
  ([[gem5-overview]] and nine others). The Anaconda build section, dropped
  from CLAUDE.md in a5b74be687, was restored from 99aeb0d7f6 into
  [[building]].
- CLAUDE.md is now a short project summary plus how to use the wiki.
- Commit notes are discontinued: commit messages and this log are the
  record. The `git-commit` and `git-pull` skills were updated to match.
- Added `docs/tools/wiki_lint.py`.
- Publish target: HTML artifacts, registered in [[publish]].

## [2026-10-21] ingest | Pass 2: the agentic material

Ingested the agentic legacy notebooks, the tracing guide, the
infinite-BTB/TLB design notes and the configs. Added a raw snapshot of the
checkpoint archive's README
([[raw/external/2026-10-21-agentic-checkpoints-README]]).

- **Workloads:** [[agentic-suite]], [[spec-cpu-2026]], [[opencode-harness]].
- **Hardware:** [[neoverse-v2]] (from the config file, which is
  authoritative), [[decoupled-front-end]], [[btb]], [[tlb-hierarchy]],
  [[infinite-btb-model]], [[infinite-l2-tlb]].
- **Infrastructure** (the tracing guide split up): [[checkpoints]],
  [[task-tracer]], [[trace-format]], [[trace-analysis]], [[stats-blocks]],
  [[viewers]], [[sweeps]], [[run-and-analysis-scripts]],
  [[running-a-traced-window]].
- **Experiments:** [[2026-10-08-tool-call-windows]],
  [[2026-10-14-event-windows]], [[2026-10-14-baseline-sweep]],
  [[2026-10-14-fdp-off-sweep]], [[2026-10-16-btb-tlb-limit-study]].
- **Findings:** [[agentic-front-end-bound]], [[btb-tlb-limits]],
  [[fdp-value]], [[agentic-ipc-variability]],
  [[switch-cost-is-around-the-switch]], [[tool-call-runup-is-cold]] (draft).
- **Methodology:** [[window-placement]], [[warmup-and-skip]],
  [[aggregating-metrics]], [[comparing-configurations]],
  [[validation-checks]], [[instruction-counts]],
  [[context-switch-classification]].
- **Pitfalls:** ten pages, from [[l2-tlb-disconnected]] to
  [[gem5-tracing-under-kaslr]].
- Wrote [[overview]] (the current thesis) and [[questions]].
- Conflicts flagged: the SPEC suite size against Garfield
  ([[spec-cpu-2026]]), and `window_view.py`'s BTB-miss row ([[viewers]]).
  The ROB size is 320, from the config ([[neoverse-v2]]).
- Repointed the code comments and help text (`infinite_btb.hh`,
  `BranchPredictor.py`, `sim_opts.py`, `neoverse_v2.py`, `smart_sweep.sh`)
  and the `run_scripts` and `analysis_scripts` READMEs to wiki pages.
- [[building]]: replaced the restored Anaconda section with a short note
  (the user said it is no longer an issue).

## [2026-10-21] restructure | Findings marked provisional

At the user's request, findings are flagged as volatile working hypotheses
so that agents do not take them as truth. Added the rule
[[SCHEMA#Findings are provisional]], a *Provisional finding* callout on every
`findings/` page, a note on the Findings section of [[index]] and on the
thesis in [[overview]], and a working rule in `CLAUDE.md`.

## [2026-10-21] ingest | Pass 3: Garfield as reference

Ingested the Garfield north-star README, `mrn-ideas.md`, the three MRN and
five VP reports (key ideas, methodology, key results), and the Stage 1/2,
restore, watchdog and FDP-fix commit notes.

- [[garfield-overview]]: the idea, what each stage produced, the code still
  in the tree (all off by default), the Garfield-era methodology.
- Per stage: [[ghost-execution]], [[memory-renaming]], [[value-prediction]].
- [[garfield-lessons]]: what transfers (measuring, trusting the simulator,
  O3 facts, FS restore mechanics).
- New shared pitfalls: [[o3-wrong-path-counting]], [[simulation-hangs]].
  [[checkpoints]] links the restore mechanics.
- Conflicts flagged on [[garfield-overview]]:
  - The reports' ROB sizes (512, 256) are wrong. The config has had 320
    entries since its first commit (360b14ca7f).
  - The README's status ("Next: Stage 1", FFT benchmark set) is stale.
  - `mrn-ideas.md` mixes eras.
  - All Garfield O3 runs predate the L2 TLB fix.
- Lint now warns about backticks inside wikilinks (Obsidian matches the raw
  heading text).

## [2026-10-21] publish | Task tracer guide and design pages

The first outputs registered in [[publish]], both HTML artifacts built from
the wiki:
- `tracer-guide`, for users: setup, commands, flags, window placement,
  analysis outputs, viewers, sweeps, trace format, reading the numbers,
  checks, debugging, limits.
- `tracer-design`, for collaborators: the problem, why gem5's tools do not
  fit, the hooks, reading memory without the MMU, KASLR and offsets,
  instruction counts, validation, what it has shown (marked provisional),
  limits, extending.

The source HTML is in `docs/wiki/_publish/`.
