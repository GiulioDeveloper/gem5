# CLAUDE.md

Guidance for Claude Code in this repository.

## The project

This is a private research fork of **gem5**, the event-driven architecture
simulator. The current effort, on branch `gfdev`, is **CPU architecture for
agentic workloads**: how AI coding agents use a server-class out-of-order
core, and what would make that core run them better. The agents are OpenCode
replays of SWE-bench-Multilingual tasks, restored from full-system Arm
checkpoints. The core is a Neoverse V2 model with a decoupled front end, and
SPEC CPU 2026 serves as the reference suite. Work so far:
- a guest task and tool-call tracer;
- sweeps of SPEC vs agentic windows;
- limit studies such as an infinite BTB and an infinite L2 TLB.

**Garfield** (branch `rbdev`) is the earlier project on this fork. It asked
whether accurately predicted instructions could be executed lazily on a
cheap in-order backend, and worked through branches, memory renaming and
value prediction. It is closed. Keep it as a reference for simulator
pitfalls, methodology and reusable infrastructure (the Neoverse V2 configs
in `configs/garfield/arm/` come from it), not as current work.

## The knowledge base: `docs/` (an Obsidian vault)

Knowledge lives in an LLM-maintained wiki, not in this file.

- **`docs/wiki/`** belongs to you: you write and maintain it.
  - Start at `docs/wiki/index.md` (the catalog), then read the pages you
    need.
  - `docs/wiki/SCHEMA.md` is the contract: page types, frontmatter,
    `[[wikilinks]]`, and the ingest, query, lint and publish workflows.
    Follow it.
  - The gem5 technical material is under `docs/wiki/gem5/`: building,
    testing, style and commit conventions, SimObjects, code generation,
    ISAs, the memory system.
- **`docs/raw/`** holds immutable external sources. Read them, never edit
  them.
- **`docs/legacy-log/`** holds the frozen pre-wiki notebooks. Never edit
  them. They are history, not truth: they may be stale or contradict each
  other.
- `docs/tools/wiki_lint.py` checks the wiki's structure. Run it after
  editing the wiki and fix the errors it reports.

Working rules:
- **Keep the wiki current as you work.**
  - A change to code, infrastructure or results that the wiki describes
    updates the affected pages and `index.md`, and appends a `log.md`
    entry, in the same piece of work.
  - A new study gets an experiment page under `docs/wiki/experiments/`;
    no separate notebooks.
  - Answers worth keeping become pages.
- **Findings are provisional.** `docs/wiki/findings/` and the thesis in
  `overview.md` are working hypotheses from a few runs. Do not present them
  as facts. Check the evidence behind them, and update or weaken them when
  new data disagrees.
- **Don't take the docs as hard truth.** Details may be missing or wrong.
  When something looks odd, check the code or the runs. Flag the conflict
  on the page (`> [!conflict]`) and tell the user.
- **Published outputs.** Human-facing outputs are HTML artifacts built from
  wiki pages and registered in `docs/wiki/publish.md`. When an output's
  source pages change, ask the user whether to rebuild it.
- **Commits.** Use the `git-commit` skill: gem5 tag format and the
  pre-commit naming review. The commit message is the per-commit record.
- **Runs.** Put run and launch scripts, and configs made for a run, in
  `runs/` (gitignored), so they can be vetted and run by hand. Run outputs
  go there too. Use `/tmp` only for throwaway build artifacts.

## Quick reference

```sh
scons build/ARM/gem5.opt -j$(nproc)          # the build used for this work (see docs/wiki/gem5/building.md)
run_scripts/tasktrace/o3-window.sh ...       # traced detailed window; see run_scripts/README.md
python3 docs/tools/wiki_lint.py              # wiki health check
```

Checkpoints live outside the repo, in `/home/snapshots/gem5-ckpts`
(override with `CKPTS`).
