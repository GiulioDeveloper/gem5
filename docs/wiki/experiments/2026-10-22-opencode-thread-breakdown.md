---
type: experiment
status: current
updated: 2026-10-22
sources:
  - runs/sweep/20261014-110051/agentic/
  - runs/old-tests/analysis/thread_breakdown.py
  - runs/old-tests/analysis/thread_breakdown-20261014-110051.txt
tags: [agentic, opencode, jit, context-switch, harness]
---

# Who runs and who switches: OpenCode's threads vs everything else

## Question

Is OpenCode's JIT runtime (Bun/JavaScriptCore) the main source of the
context switches and the low IPC in the agentic windows?

## Setup

No new simulation. Re-analysed the 27 agentic windows of the
[[2026-10-14-baseline-sweep]] (400M detailed instructions each, 10.67G in
total) from their `tasktrace.jsonl`, counting only the detailed window
(`intervals.csv` range). A slice between two switches belongs to the first
switch's `next`; per-class IPC = instructions / (slice ticks / 333.3).
Script: `runs/old-tests/analysis/thread_breakdown.py <sweep>/agentic`. Thread classes
are OpenCode thread names with trailing digits stripped.

## Results

**Instruction share and IPC, pooled over the 27 windows:**

| group | share of instructions | IPC |
|---|---|---|
| OpenCode, all threads | 42.5% | 0.90 |
| … main JS thread (`opencode`) | 35.2% | 0.89 |
| … `JITWorker` threads (JIT compilation) | 7.2% | 0.97 |
| … `Bun Pool`, helper, HTTP threads | 0.1% | 0.15–0.79 |
| other user processes (tools, git, javac, cc1plus, compile, find, m4, node, …) | 32.1% | 1.17 |
| Docker CLI, dockerd, the replay driver's `python3`, daemons | 25.2% | 0.94 |
| kernel threads and idle | 0.2% | – |

Per window, OpenCode's share ranges from 0% (preact, caddy, lombok,
gson-2134, bat: the window falls inside a tool or build) to 88%, median 56%.
For reference, SPEC IPC is 1.52 (median window).

**Context switches** (18,112 in the windows, 1.68 per M instructions):

| kind | count | share |
|---|---|---|
| between threads of one process other than OpenCode | 8,564 | 47.3% |
| between processes | 4,268 | 23.6% |
| to or from a kernel thread or idle | 2,671 | 14.7% |
| between OpenCode's threads | 2,609 | 14.4% |

- Thread switches within `docker` alone: 7,557; `docker <-> dockerd` 1,266;
  `python3 <-> docker` 732. The replay driver's Docker polling
  ([[replay-polling-in-measurement]]) accounts for well over half of all
  switches in the windows.
- Within OpenCode, 58.7% of switches involve a `JITWorker` (1,531, i.e.
  8.5% of all switches); `Bun Pool` hand-offs are another 35%.

## Conclusions

- **OpenCode is not the main source of switches**: the Docker polling of the
  model-free replay is. The JIT's share of switching is about 8.5%.
- **The direct JIT tax is ~7% of instructions** (compilation threads); the
  rest of OpenCode is its main JS thread, which runs at IPC 0.89, close to
  the Docker CLI (0.94) and below the tools and compilers (1.17). The
  indirect cost of JIT (freshly generated, scattered code) is in the main
  thread's front-end behaviour, not separated here.
- **One vCPU inflates the JIT's switching**: on a multi-core machine the
  `JITWorker` threads would mostly run on other cores, concurrently, rather
  than preempting the main thread.
- Bears on [[agentic-front-end-bound]] and
  [[switch-cost-is-around-the-switch]]; summarised in [[opencode-harness]].

## Open

- Separate the front-end metrics of OpenCode's main thread from the tools'
  per block (blocks dominated by one class), to see the JIT-code effect.
- Compare harnesses on work per agent step, not IPC ([[questions]]).
