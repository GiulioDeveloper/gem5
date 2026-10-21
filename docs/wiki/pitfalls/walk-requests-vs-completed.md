---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/infinite-tlb]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [tlb, page-walk, stats]
---

# `mmu.walker.walks` counts requests, not walks

**The trap:** `walker.walks` (`walks_pki`) counts every request to the
walker, including requests squashed before a walk started (wrong path) and
requests merged into a walk already in flight for the same page. Likewise
an L2 TLB "miss" is counted on every non-functional lookup that misses.
**Completed walks** are `walker.requestOrigin_Completed::{Data,Inst}`,
close to `l2_shared.inserts`.

**Size of the gap:** about 4×. fmt-3901 sweep window: 2.64 requests vs 0.68
completed walks per 1000 instructions (0.58 data, 0.09 instruction). In a
20M check: 55,244 requests, 21,166 squashed before starting, 13,064
completed.

**What it hid:** the infinite L2 TLB cut walk *requests* by 44% but
*completed walks* by 76% ([[btb-tlb-limits]]). Requests also made walks look
like a bigger problem than they are.

**Now:** the window view, sweep summaries and comparisons have
`walks_done_pki` (and data/instruction splits) next to the relabelled
`walks_pki` ("Page-walk requests"). `trace_analysis.py`'s `blocks.csv` still
has only `walks_pki` ([[questions]]).
