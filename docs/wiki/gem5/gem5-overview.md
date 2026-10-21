---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
tags: [gem5]
---

# gem5 overview

gem5 is a modular, event-driven computer-system architecture simulator. The
C++ core implements the simulated hardware; Python drives configuration and
the simulation loop (the gem5 binary embeds a CPython interpreter).
Understanding the **Python↔C++ boundary** is the key to working in it: see
[[simobject-model]].

This repository is a private research fork. Branches: `gfdev` (agentic
workloads, current), `rbdev` (Garfield, see [[garfield-overview]]), `stable`
(upstream releases; the PR base).

## Pages

- [[building]]: SCons, build configs and variants
- [[testing]]: unit, Python and regression tests
- [[contributing]]: style, pre-commit, commit messages
- [[simobject-model]]: how a component is declared in Python and C++
- [[scons-codegen]]: what the build generates and how sources are registered
- [[python-layers]]: `m5` vs the stdlib, running a simulation, SE vs FS
- [[simulation-core]]: event queue, ports and packets, base infrastructure
- [[isa-dsl]]: the `.isa` instruction-description language
- [[memory-system]]: classic caches vs Ruby

## Source tree

| path | contents |
|---|---|
| `src/` | C++ core, Python wrappers, stdlib |
| `build_opts/` | build configs (KConfig defconfigs) |
| `build_tools/` | code generators |
| `site_scons/` | SCons infrastructure |
| `configs/` | config scripts; `configs/garfield/arm/` holds this fork's Neoverse V2 drivers ([[neoverse-v2]]) |
| `tests/` | regressions; framework in `ext/testlib/` |
| `ext/` | bundled third-party code |
| `util/` | tooling: `m5` guest util, trace decoders, checkpoint upgraders, clang-format/commit hooks |
| `system/` | firmware sources |
| `run_scripts/`, `analysis_scripts/` | this fork's run launchers and host-side analysis ([[run-and-analysis-scripts]]) |
| `runs/` | run outputs and ad-hoc run configs (gitignored) |

`AGENTS.md` is upstream gem5's generic contributor guide (dependency policy,
CI, release process); it has nothing fork-specific.
