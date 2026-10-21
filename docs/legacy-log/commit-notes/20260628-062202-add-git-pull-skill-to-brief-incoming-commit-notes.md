# misc: Add git-pull skill to brief incoming commit-notes

- **Date:** 2026-06-28 06:22   ·   **Branch:** rbdev

## Goal
Complete the cross-clone knowledge-sharing loop. The `git-commit` skill writes a
note per commit; this is the read side — when a clone pulls or merges another
clone's work, its Claude should automatically learn what changed instead of
re-reading every incoming diff.

## Summary of changes
Add a new project-scoped `git-pull` skill. It runs the pull/merge the user asked
for, stops and reports on conflicts, then finds the notes that arrived via
`git diff --diff-filter=A ORIG_HEAD..HEAD -- docs/commit-notes/` (ignoring the
README), reads them, and prints a concise per-commit catch-up briefing. Its
description triggers on pull/fetch/merge/sync/"catch me up" phrasing.

## Files changed
- `.claude/skills/git-pull/SKILL.md` — new read-side skill: integrate, handle
  conflicts, find incoming notes from `ORIG_HEAD..HEAD`, read, and brief the user.
