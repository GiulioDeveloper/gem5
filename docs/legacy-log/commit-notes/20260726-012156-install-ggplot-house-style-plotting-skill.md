# misc: Install ggplot-house-style plotting skill

- **Date:** 2026-07-26 01:25   ·   **Branch:** rbdev

## Goal
Make the house-style R plotting skill (canonical source:
github.com/rahulbera/skillhub) invocable from this repo, so future analysis
sessions plot sweep results in the consistent publication style.

## Summary of changes
Synced ggplot-house-style into .claude/skills/ via the skill's own sync.sh.
First use: the per-checkpoint S-curve of the value-file threshold sweep
(analysis artifacts live with the runs, gitignored). The R environment on
this host was provisioned via conda-forge (r-base + ggplot2/hrbrthemes/
dplyr/tidyr/yaml/ragg/scales), verified by the skill's setup script.

## Files changed
- `.claude/skills/ggplot-house-style/**` — skill copy (SKILL.md, conventions, style/contract templates, example scripts, sync.sh).
