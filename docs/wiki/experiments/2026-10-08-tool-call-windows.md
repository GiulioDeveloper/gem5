---
type: experiment
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - runs/tasktrace/20261008-125928-gin-2121-o3window-read/
  - runs/tasktrace/20261009-141720-framework-52684-o3window/
tags: [agentic, tool-calls, context-switch, o3]
---

# First O3 windows across tool calls (gin-2121, framework-52684)

## Question

What does the core do around an OpenCode tool call and around context
switches, once the [[task-tracer]] can place them? First looks, one call
per checkpoint.

## Setup

- Builds **before the L2 TLB fix** ([[l2-tlb-disconnected]]): iTLB and walk
  figures are inflated, IPC somewhat too.
- **gin-2121 cpt.0 `read`:** `o3-window.sh gin-2121 2950000000 20000000
  420000000 1000000` (2.95G atomic settle to just before the call, 20M
  warm-up, 420M O3 in 1M blocks). Run
  `runs/tasktrace/20261008-125928-gin-2121-o3window-read`.
- **framework-52684 cpt.0 `bash`** (`ls /testbed && head -20
  /testbed/composer.json`): atomic to ROUND 3 to find the call, then
  `o3-window.sh framework-52684 4330000000 20000000 400000000 250000`,
  rerun 2026-10-09 with the user/kernel split and scheduler cost
  (`runs/tasktrace/20261009-141720-framework-52684-o3window`).
- Block groups aggregated from raw counts ([[aggregating-metrics]]).

## Results

**gin-2121, 420M O3, region IPC 0.768:**

| blocks | n | IPC | L1I MPKI | L2 MPKI | br MPKI | iTLB MPKI |
|---|---|---|---|---|---|---|
| all | 420 | 0.77 | 4.1 | 12.8 | 6.7 | 107 |
| harness before `pending` | 67 | 0.69 | 6.6 | 14.8 | 10.2 | 175 |
| harness `pending` → `running` | 29 | 0.66 | 7.6 | 16.9 | 10.2 | 200 |
| harness `running` → `completed` | 127 | 0.81 | 3.2 | 13.1 | 5.3 | 80 |
| harness after `completed` | 62 | 1.00 | 1.6 | 8.6 | 5.5 | 40 |
| with a process switch | 58 | 0.62 | 5.9 | 17.6 | 7.9 | 149 |
| no switch | 253 | 0.91 | 2.6 | 9.7 | 5.4 | 69 |
| with an exec | 4 | 0.50 | 8.2 | 20.0 | 12.2 | 169 |

**framework-52684, 400M O3 in 250K blocks, region IPC 0.911:**

| blocks | n | IPC | L1I MPKI | L2 MPKI | br MPKI | iTLB MPKI |
|---|---|---|---|---|---|---|
| before the tool, harness only | 571 | 1.10 | 1.8 | 6.8 | 2.5 | 43 |
| tool processes span | 136 | 0.78 | 3.2 | 12.0 | 5.1 | 68 |
| with any tool process | 54 | 0.59 | 5.0 | 14.3 | 8.7 | 102 |
| after the tool, harness only | 487 | 0.90 | 2.6 | 11.1 | 4.4 | 57 |
| with a process switch | 82 | 0.50 | 7.9 | 23.6 | 10.7 | 188 |
| no event | 1355 | 1.01 | 1.8 | 8.0 | 3.2 | 44 |

**User/kernel and scheduler cost (framework-52684):**
- Over 4.74G traced instructions: 85.5% user, 14.5% kernel. Kernel share by
  group: OpenCode 6.5%, replay driver 43%, tool processes 63%, `git` 85%.
- Scheduler path (`__schedule` → `__switch_to`), 676 switches: median 1,815
  instructions, 1,720 cycles (mean 2,945, p90 5,912; IPC 0.61), 0.45% of
  the region's cycles. During the tool's process churn: same instructions
  (median 2,124) but **4,705 cycles**: the same code, cold.
- Blocks with a switch: IPC 0.60 vs 1.00, kernel share 30.5% vs 10.4%, but
  the scheduler path is only 2.1% of their instructions.
- 100K blocks (short framework window): blocks with a process switch IPC
  0.28, L2 MPKI 48.9, against 0.86 and 7.9 without.

## Conclusions

- The run-up to a tool call is the cold part of the harness:
  [[tool-call-runup-is-cold]].
- Switch cost is around the switch, not in the scheduler:
  [[switch-cost-is-around-the-switch]].
- The tool's fork/exec chain (`bash`, `basename`, `bash.fence-real`, `ls`,
  `head`) runs at IPC 0.4–0.7 with L2 MPKI 15–65 per exec block, recovering
  within ~1M instructions; afterwards the harness stays slower than before
  (0.90 vs 1.10) for the remaining ~150M instructions (cache and TLB state
  displaced, or the next phase; not separated).
- Atomic positions moved ~130M instructions on O3 in framework-52684
  ([[window-placement]]).

## Open

- One call per checkpoint, pre-fix TLB: repeat on the current build across
  many calls and tasks ([[questions]]).
- The framework window ends before the call's `completed`; use
  `--tail-insts`.
