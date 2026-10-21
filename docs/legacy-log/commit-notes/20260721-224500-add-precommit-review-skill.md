# misc: Add precommit-review skill, gate commits on naming

- **Date:** 2026-07-21 22:45   ·   **Branch:** rbdev

## Goal
Stop conversational / session-specific names (arbitrary mode letters, ad-hoc
numbered taxonomies, private jargon) from reaching committed code. Encode the
rule as a skill and make the git-commit flow run it before every commit.

## Summary of changes
New `precommit-review` skill: a lightweight gate over `git diff --cached` with
a mandatory, blocking naming rule ("would a reader who was not in the
conversation understand this term? if not, use a descriptive name"), plus
blocking scaffolding and advisory consistency checks. The git-commit skill now
lists running precommit-review as non-negotiable rule 3 and workflow step 5.

## Files changed
- `.claude/skills/precommit-review/SKILL.md` — new gate skill (naming / scaffolding / consistency).
- `.claude/skills/git-commit/SKILL.md` — require precommit-review before every commit (rule 3, step 5).
