---
type: finding
status: draft
updated: 2026-10-21
sources:
  - "[[2026-10-08-tool-call-windows]]"
tags: [tool-calls, opencode, cold-code, jit]
---

# The harness is coldest in the run-up to a tool call

> [!warning] Provisional finding
> Findings are working hypotheses from a few sweeps and windows, and they
> change as new runs arrive. Check the evidence and its caveats before
> relying on this; challenge it when new data disagrees
> ([[SCHEMA#Findings are provisional]]).

**Claim (draft, one call):** while OpenCode handles a model response and
prepares a tool call (before `pending` and from `pending` to `running`),
it runs at IPC 0.66–0.69 with twice the L1I and branch MPKI and 2–5× the
iTLB misses of its steady part; after the call completes the same process
runs at IPC 1.00 (gin-2121, before the L2 TLB fix).

- Consistent with code new to the run: first use of a tool path and JIT
  compilation (`JITWorker` threads took 21% of the first `read`'s span on
  atomic).
- A tool call is expensive in instructions: a 45-line `read` took 171–179M
  instructions running → completed, most of it OpenCode serialising and
  persisting state and the JS runtime, plus ~22% replay polling
  ([[opencode-harness]], [[replay-polling-in-measurement]]).
- For `bash`, the fork/exec chain of the tool processes is short (~70M of
  1.02G instructions) but slow (IPC 0.4–0.7 per exec block), and the harness
  is slower afterwards ([[2026-10-08-tool-call-windows]]).

Needs: the same analysis over many tool calls, on the current build
([[questions]]).
