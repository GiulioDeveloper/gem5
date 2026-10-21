---
type: experiment
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - runs/tasktrace/20261013-1735*
tags: [agentic, context-switch, events, o3]
---

# Metrics around scheduling events (cpython, jq, redis)

## Question

With fine stats blocks and the current (L2-TLB) build, how do core metrics
move in the blocks holding a scheduling event, per kind and cause?

## Setup

Three O3 windows, 1 atomic settle instruction, 20M warm-up,
200K-instruction blocks: `714.cpython_r` (200M, `spec-window.sh`),
`jq-2598` and `redis-12272` (400M, `o3-window.sh`). Outputs
`runs/tasktrace/20261013-1735*`. Event block vs the window value, mean over
events, a block counted once per event. Switch causes under the rule of the
time (`same_mm`; redis' `within docker` is 300 and `within opencode` 154
under the current rule, [[context-switch-classification]]).

## Results

| run | window IPC | who ran | switches (process / thread / kernel) |
|---|---|---|---|
| cpython | 2.098 | one slice, `not recorded` | 0 / 0 / 0 |
| jq | 1.420 | `m4` 50%, `bison` 13%, `docker` 11%, `git` 9% | 274 / 129 / 117 |
| redis | 0.778 | `opencode` 70%, `docker` 19%, `git` 6% | 165 / 475 / 137 |

The `run.sh` tree is 12% of jq and 22% of redis.

- **jq, `bison <-> m4` pipe hand-offs** (63): IPC **+20%**, L1I MPKI −65%,
  L2 MPKI −80%: small hot processes, no visible switch cost at 200K.
- **jq, all process switches** (247): IPC −36%, L1I MPKI +522%, iTLB MPKI
  +380%; exits −48% IPC, process forks −54%. Dominated by short-lived
  shells (`bash.fence-real`, `sed`, `mkdir`) running 76–93% in kernel mode.
- **redis, `within opencode`** (156): IPC −44%, L1I MPKI +393%;
  **`within docker`** (290): IPC +13%, L1I MPKI +105%.
- **Recovery is fast:** redis process switches −31% IPC in the event block,
  −7% in the next.
- **cpython control:** no event, yet L1I MPKI steps 0.34 → 0.50 at 64.8M.

## Conclusions

- The cost attributed to a switch depends on who runs around it:
  [[switch-cost-is-around-the-switch]]. Process-switch averages mix cheap
  pipe hand-offs with expensive short-lived processes; use per-cause views.
- Always check a no-event control: [[metric-shift-is-not-event-effect]].

## Open

- Per-cause costs across the whole suite (the sweeps have the traces).
