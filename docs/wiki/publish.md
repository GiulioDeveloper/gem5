---
type: meta
status: current
updated: 2026-10-21
---

# Published outputs

Registry of the human-facing outputs built from the wiki (procedure:
[[SCHEMA#Publish (human-facing material)]]). Each output is an HTML artifact
whose source HTML is in `docs/wiki/_publish/<name>.html`. Never edit an
output directly. Change the wiki, then rebuild.

`docs/tools/wiki_lint.py` parses the table below. Keep one row per output,
with the sources as wikilinks separated by commas, and `built` as an ISO
date.

| name | audience | sources | url | built | commit |
|---|---|---|---|---|---|
| tracer-guide | users of the tracer (running, analysing, viewing, sweeping) | [[running-a-traced-window]], [[checkpoints]], [[task-tracer]], [[trace-format]], [[trace-analysis]], [[stats-blocks]], [[viewers]], [[sweeps]], [[run-and-analysis-scripts]], [[window-placement]], [[aggregating-metrics]], [[validation-checks]], [[instruction-counts]], [[context-switch-classification]] | https://claude.ai/artifact/41mPPZTSJuU7EZTC8qssCq | 2026-10-21 | committed together with this row |
| tracer-design | collaborators (why and how it works, validation, findings so far) | [[task-tracer]], [[trace-format]], [[trace-analysis]], [[checkpoints]], [[validation-checks]], [[instruction-counts]], [[context-switch-classification]], [[gem5-tracing-under-kaslr]], [[functional-translation-perturbs]], [[replay-polling-in-measurement]], [[switch-cost-is-around-the-switch]], [[opencode-harness]] | https://claude.ai/artifact/Q3B6N7NjRqWv7ykGraqbgT | 2026-10-21 | committed together with this row |

Both pages are private artifacts: share them from the page's Share menu.
Rebuild by editing `docs/wiki/_publish/<name>.html` from the current source
pages and publishing the same file path, which keeps the URL.
