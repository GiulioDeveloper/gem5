# python: Stop emitting config.json and citations.bib

- **Date:** 2026-07-20 11:40   ·   **Branch:** rbdev

## Goal
Every run wrote three files nobody reads: config.json (a duplicate of
config.ini), citations.bib (~5KB of boilerplate), and the ini itself. Across a
380-job sweep that is pure noise in the output tree.

## Summary of changes
Verified first that config.ini and config.json are genuinely redundant rather
than complementary: both describe 490 objects, neither has an object the other
lacks, and 3405 of 3408 shared parameter values are byte-identical (99.91%).
The only three differences are the spelling `NullOpt` (ini) vs `Null` (json).
JSON nests children where ini uses flat section paths; the content is the same
canonical config. So dropping one loses nothing.

`--json-config` now defaults to empty (disabled) rather than "config.json"; it
still works if passed explicitly. The citations.bib write is removed from
_dump_configs.

## Files changed
- `src/python/m5/main.py` — default --json-config to "" and note in the help text that --dump-config emits the same canonical config as ini.
- `src/python/m5/simulate.py` — drop the gather_citations import and its call in _dump_configs.
