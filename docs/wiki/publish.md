---
type: meta
status: current
updated: 2026-11-16
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
| tracer-guide | users of the tracer (running, analysing, viewing, sweeping) | [[running-a-traced-window]], [[checkpoints]], [[task-tracer]], [[trace-format]], [[trace-analysis]], [[stats-blocks]], [[viewers]], [[sweeps]], [[run-and-analysis-scripts]], [[window-placement]], [[aggregating-metrics]], [[validation-checks]], [[instruction-counts]], [[context-switch-classification]], [[run-output-compression]] | https://claude.ai/artifact/41mPPZTSJuU7EZTC8qssCq | 2026-11-12 | 68192bbe68, with the uncommitted 2026-11-09 edits to [[sweeps]] |
| tracer-design | collaborators (why and how it works, validation, findings so far) | [[task-tracer]], [[trace-format]], [[trace-analysis]], [[checkpoints]], [[validation-checks]], [[instruction-counts]], [[context-switch-classification]], [[gem5-tracing-under-kaslr]], [[functional-translation-perturbs]], [[replay-polling-in-measurement]], [[switch-cost-is-around-the-switch]], [[opencode-harness]] | https://claude.ai/artifact/Q3B6N7NjRqWv7ykGraqbgT | 2026-11-02 | committed together with this row |
| long-runs-guide | users running and analysing multi-billion-instruction runs (launch, compaction, stall split, checks, comparisons, per-process views) | [[long-runs]], [[pc-trace]], [[stats-blocks]], [[run-and-analysis-scripts]], [[guest-trng-hvc-stall]], [[comparing-configurations]], [[aggregating-metrics]], [[2026-10-23-rubocop-15g-cache-btb-tlb]], [[run-output-compression]] | https://claude.ai/artifact/Q59pV5tfkzizJsRkw87vGH | 2026-11-12 | 68192bbe68 |
| top-down-guide | anyone reading or changing the top-down numbers (names, exact formulas, reasons, pitfalls, known problems) | [[top-down-accounting]], [[2026-11-03-top-down-validation]], [[2026-11-13-top-down-microbenchmarks]] | https://claude.ai/artifact/9AecQ66jR1esx2Q7bPepoL | 2026-11-13 | the commit after 387f75040f that adds the front-end fix |
| metric-definitions | anyone reading the sweep comparison or window view (what each metric is, which gem5 stats and formula, what it leaves out, pitfalls) | [[metric-definitions]] | https://claude.ai/artifact/M3M8ih92cteVcaXhkhNSYV | 2026-11-16 | 9ff7bdd38c plus the uncommitted cache-hierarchy changes of 2026-11-16 |

Slide decks are not in this table: the user edits them in place, so they
are not rebuilt. They are registered in `presentations/`, one page each:
[[2026-11-10-cache-hierarchy-headroom]].

All pages are private artifacts: share them from the page's Share menu.
Rebuild by editing `docs/wiki/_publish/<name>.html` from the current source
pages and publishing the same file path, which keeps the URL.
`metric-definitions` is the exception: its wiki page and its HTML are both
written by `python3 docs/tools/metric_definitions.py <commit> <date>` from
the content in that script; edit the script, run it, publish the HTML.
