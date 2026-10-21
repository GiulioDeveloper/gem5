# Commit-notes

This directory holds **per-commit notes** that let parallel clones of this repo
share knowledge. We develop features in several local clones (one Claude Code
instance each) and periodically merge them into a master clone before pushing to
`origin`. Each commit drops a short note here describing what it did, so when
another clone pulls or merges the commit, its Claude can read the note and learn
what changed — without re-reading the diff.

## Convention

- **One file per commit**, written and committed *in the same commit* as the
  change it describes (atomic — a note is never separated from its change).
- **Filename:** `<YYYYMMDD-HHMMSS>-<slug>.md` — a commit-time timestamp (orders the
  notes chronologically) plus a kebab-cased slug of the commit's summary line.
  One file per commit with unique names means parallel clones never conflict on a
  shared index when their histories merge.
- **Template:**

  ```markdown
  # <commit header line>

  - **Date:** <YYYY-MM-DD HH:MM>   ·   **Branch:** <branch the commit was made on>

  ## Goal
  Why this change exists / what it achieves (1-3 sentences).

  ## Summary of changes
  What was done (a short paragraph or a few bullets).

  ## Files changed
  - `path/to/file` — a 1-2 line descriptor of what changed in this file.
  ```

## Producing and reading notes

- **Write side:** the `git-commit` skill (`.claude/skills/git-commit/`) writes a
  note as part of every commit.
- **Read side:** the `git-pull` skill (`.claude/skills/git-pull/`) reads the notes
  that arrived with a pull/merge and briefs you on what the other clones did.

This `README.md` documents the convention; it is **not** itself a commit-note, and
the `git-pull` skill ignores it.
