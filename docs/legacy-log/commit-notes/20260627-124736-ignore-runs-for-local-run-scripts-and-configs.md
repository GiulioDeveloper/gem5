# misc: Ignore runs/ for local run scripts and configs

- **Date:** 2026-06-27 12:47   ·   **Branch:** rbdev

## Goal
Keep local run/launch scripts and the configs used for runs out of the tracked
tree, so they can be vetted and run manually without polluting the repo.

## Summary of changes
Gitignore the `runs/` directory and document the convention in `CLAUDE.md`
(`/tmp` is reserved for throwaway build artifacts).

## Files changed
- `.gitignore` — ignore `/runs/`.
- `CLAUDE.md` — document the `runs/` convention.
