# misc: Add cross-clone commit-notes to git-commit skill

- **Date:** 2026-06-28 06:06   ·   **Branch:** rbdev

## Goal
Enable knowledge sharing between the parallel local clones of this repo (one
Claude Code instance each, merged into a master before pushing). Every commit
should leave behind a short, readable note so that when another clone pulls or
merges it, that clone's Claude understands what changed and why.

## Summary of changes
Introduces the `docs/commit-notes/` convention — one Markdown note per commit,
named `<YYYYMMDD-HHMMSS>-<slug>.md`, committed atomically with the change it
describes (no shared index, so parallel merges never conflict). Teaches the
`git-commit` skill to write such a note from the staged diff and stage it before
committing, so the note always rides in the same commit. This commit is the first
to carry its own note.

## Files changed
- `.claude/skills/git-commit/SKILL.md` — adds a "Write the commit-note" workflow
  step (name recipe + template, fed by `git diff --cached --name-only`) and a
  "Commit-notes (cross-clone sharing)" subsection documenting the convention.
- `docs/commit-notes/README.md` — new convention doc: what these notes are, the
  filename/template rules, and that this README is not itself a note.
