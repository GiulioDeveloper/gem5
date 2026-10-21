# misc: Install research-report skill

- **Date:** 2026-07-26 03:05   ·   **Branch:** rbdev

## Goal
Make the paper-shaped research-log report format (docs/research-log/) a
reusable skill, so future campaigns get recorded with the same structure.

## Summary of changes
Synced the new research-report skill from its canonical home
(github.com/rahulbera/skillhub, commit 6d79761) into .claude/skills/.
The skill encodes: report location and self-contained figs/, the paper
skeleton (Key Idea / Mechanism with Files Touched + Commits Covered /
Evaluation Methodology / Key Results and Next Steps in descending
importance / References), title-cased headers, byline with user + model
names, verified citations, non-clipping figure captions, and the
present-before-commit review loop. Distilled from writing
docs/research-log/MRN/2026-07-26-value-file-rendezvous.md, which ships in
the skill as the exemplar.

## Files changed
- `.claude/skills/research-report/**` — SKILL.md, reference/template.md, examples/mrn-value-file-rendezvous.md, sync.sh.
