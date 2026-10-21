---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
  - CONTRIBUTING.md
  - .claude/skills/git-commit/SKILL.md
tags: [gem5, style, git]
---

# Style and commit conventions

The code follows upstream gem5 style, so that changes could go upstream and
the upstream checkers pass.

- **Branches.** Upstream branches off `develop`, not `stable`. In this fork,
  research work happens on `gfdev` (agentic) and `rbdev` (Garfield).
- **pre-commit** mirrors upstream CI: black, isort, clang-format
  (`util/run-git-clang-format.py`), the gem5 style checker
  (`util/git-pre-commit.py`) and the commit-message checker
  (`util/git-commit-msg.py`). Install it with
  `pip install pre-commit && pre-commit install`. It is not installed in
  every clone, so check `.git/hooks`.
- **C++:** lines of at most 79 columns (`.clang-format` `ColumnLimit: 79`,
  comments included), 4-space indent, no trailing whitespace.
  `UpperCamelCase` classes, `lowerCamelCase` methods and members,
  `_leadingUnderscore` for members behind a public accessor, `snake_case`
  locals and parameters.
- **Python:** black with `line-length = 79`, isort, PEP 8 naming. Where a
  file already uses a different convention, follow the file.
- **Commit messages:** a header of the form `tag[,tag]: short description`,
  at most 65 characters, with tags from `MAINTAINERS.yaml` (`cpu:`,
  `arch-arm:`, `configs:`, `mem-cache:`, `misc:`, `tests:`, ...). Body lines
  are at most 72 characters. The `git-commit` skill applies this and runs
  the `precommit-review` naming gate. Commit messages are the per-commit
  record; there are no commit notes (see [[SCHEMA#Commits]]).
- **Naming gate.** Code, comments and parameter help text must not contain
  session jargon (ad-hoc mode letters, private numbered taxonomies). See
  `.claude/skills/precommit-review/SKILL.md`.
