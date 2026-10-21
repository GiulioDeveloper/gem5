# misc: Add Claude Code setup to enable AI-driven development

- **Date:** 2026-06-27 12:27   ·   **Branch:** rbdev

## Goal
Give AI-driven development consistent project context and commit conventions so
work in this fork follows gem5's norms.

## Summary of changes
Add `CLAUDE.md` (build/test commands, the host Anaconda build environment, the
dual Python/C++ SimObject model, the m5 vs gem5 Python layers, and the ISA/memory
subsystems) plus a project-scoped `git-commit` skill that writes gem5 tag-format
messages with no AI co-authorship trailers.

## Files changed
- `CLAUDE.md` — project guide: build/test commands, host build env, and an
  architecture overview.
- `.claude/skills/git-commit/SKILL.md` — git-commit skill enforcing gem5's
  tag-based header and forbidding AI attribution trailers.
