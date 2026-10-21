---
name: git-pull
description: >-
  Pull or merge changes into this gem5 clone and then brief the user on what
  arrived. Use whenever the user asks to pull, fetch and merge, sync, integrate,
  merge another clone or branch, or "catch me up" / "what changed" here. We run
  several local clones in parallel (one Claude each) and merge them together;
  this skill reads the incoming commit messages and the new docs/wiki/log.md
  entries so you understand what the other clones changed before continuing.
---

# Pulling and merging in this gem5 repository

We develop in several local clones of this repo at once (one Claude Code
instance per clone, each on its own feature) and periodically merge them into a
master clone before pushing to `origin`. What a commit did is recorded in its
**commit message**, and what it changed in our knowledge is recorded in the
wiki's append-only **`docs/wiki/log.md`** (see `docs/wiki/SCHEMA.md`).

This skill does the integration the user asked for, then **reads what just
arrived** and briefs the user, so this clone's Claude learns what the other
clones changed instead of re-reading every incoming diff.

## Workflow

1. **Integrate.** Run the operation the user asked for:
   - plain pull: `git pull`
   - merge another clone/branch: `git merge <ref>`
   Either way git records the pre-integration commit as `ORIG_HEAD`, which we use
   below to find exactly what arrived. (If the user only said "pull", default to
   `git pull`.)
2. **Handle conflicts first.** If the merge/pull reports conflicts, **stop and
   report** the conflicting files (`git status`); do not auto-resolve; hand back
   to the user to resolve (help only if asked). A conflict in
   `docs/wiki/log.md` is two clones appending entries: keep both, in date
   order. A conflict in `docs/wiki/index.md` keeps both sides' lines.
3. **Find what arrived:**

   ```sh
   git log --reverse --format='%h %ad %s%n%b' --date=short ORIG_HEAD..HEAD
   git diff --stat ORIG_HEAD..HEAD
   git diff ORIG_HEAD..HEAD -- docs/wiki/log.md      # new log entries
   ```

   If the range is empty, report "Already up to date." and stop.
4. **Brief the user.** Print a concise catch-up, chronological: for each
   incoming commit its header, a one-line summary of its body, and the
   notable files; then the new `log.md` entries (wiki pages created or
   changed, decisions recorded). Call out anything that touches files this
   clone is also working on, and wiki pages this clone has edited.
5. **Lint the merged wiki:** `python3 docs/tools/wiki_lint.py`. Two clones can
   each add a valid page that together break something (duplicate names,
   index entries lost in a merge). Report the errors; fix only if asked.

## Notes

- `ORIG_HEAD` is set by `git pull`/`git merge`. If you ran several pulls it points
  at the most recent one; to brief over a wider range use an explicit base
  (e.g. `git log --reverse <old-sha>..HEAD`).
- A no-op pull ("Already up to date") leaves `ORIG_HEAD..HEAD` empty, so there
  is nothing to brief, which is correct.
- Commits before 2026-10-21 carry notes in `docs/legacy-log/commit-notes/`;
  read the matching note when briefing over such old commits.
