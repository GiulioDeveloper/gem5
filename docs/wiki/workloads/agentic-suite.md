---
type: entity
status: current
updated: 2026-10-21
sources:
  - "[[raw/external/2026-10-21-agentic-checkpoints-README]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [agentic, workload, checkpoints]
---

# Agentic suite (SWE-bench-Multilingual, OpenCode replays)

**What it is:** 27 tasks (132 checkpoints) of an OpenCode coding agent
(GLM-5.2 via OpenRouter) solving SWE-bench-Multilingual tasks, replayed
**model-free** inside an Ubuntu 24.04 arm64 guest: the recorded model
responses are served from disk, so what runs under gem5 is the agent's
*execution* (the harness, its tool calls, the compilers and test suites it
drives), not inference. Captured with RPoint (QEMU/KVM → gem5) on an AWS
Graviton3 `c7g.metal`, 2026-09-20/21. Nine languages: C, C++, Rust, Go,
Java, PHP, Ruby, JavaScript, TypeScript.

How to restore one: [[checkpoints]]. The processes inside: [[opencode-harness]].

## Shape of the suite

- **Per task, 5 dumps** at random offsets over the agent loop, from
  `RPOINT_REPLAY_ROUND 1` (first tool round) to the harness exit; start-up
  and grading are excluded. Three tasks have 4 (`nushell-13831`,
  `preact-3763`, `immutable-js-2006`: the loop ended first).
- **Agent loops span 7.1 s to 1589.6 s** of guest time, a factor of 224.
- **The replay is unpaced**: model-wait idle is not reproduced, so the
  timelines are agent-loop *compute*, not a deployed agent's duty cycle
  (measured busy fraction of the live runs: median 0.46, range 0.09–0.96).
- **1 vCPU, 16 GiB**, kernel 6.8.12 with KASLR and KPTI, `faketime` pinned
  to 2026-08-19 12:00:00.
- **Locally** (`/home/snapshots/gem5-ckpts/rpoint_ckpts/agentic/`) the
  sweeps use the first checkpoint of each task, `cpt.0` (fastlane-20958 has
  only `cpt.1`).

Task names used everywhere (checkpoint name without `agentic-`): axios-5892,
babel-15649, bat-2835, caddy-4774, carbon-2752, core-11870, docusaurus-9897,
fastlane-20958, fmt-3750, fmt-3901, framework-52684, gin-2121, gson-1093,
gson-2134, immutable-js-2006, jekyll-8167, jq-2598, json-4237, lombok-3479,
micropython-13039, nushell-13831, php-cs-fixer-8064, preact-3763,
prometheus-10720, redis-12272, ripgrep-2209, rubocop-13560.

## How it behaves on the core (summary; details on the linked pages)

| metric (400M-instruction window, median of 27) | agentic | SPEC CPU 2026 |
|---|---|---|
| IPC | 0.99 [0.85–1.14] | 1.52 [1.04–2.07] |
| user-mode share | 81% | 100% |
| L1I / iTLB MPKI | 1.74 / 37 | 0.01 / 0.15 |
| BTB-miss mispredicts PKI | 1.13 | 0.005 |
| context switches per M instructions | 1.6 | 0 |

From [[2026-10-14-baseline-sweep]]. The front end separates the suites
([[agentic-front-end-bound]]). Agentic IPC is tight *across* checkpoints
but unstable *inside* a window ([[agentic-ipc-variability]]).

## Things to know before measuring

- About a fifth of the instructions are the replay driver polling Docker,
  not the agent: [[replay-polling-in-measurement]].
- Memory per run varies 2.5–22 GB (nushell-13831 22.2 GB, docusaurus-9897
  about 11 GB): [[sweep-memory-exhaustion]].
- The checkpoints span IPC 0.35–1.57 (up to 0.86 spread within one task);
  suspiciously uniform IPC across tasks means a broken restore:
  [[restore-silent-failures]].
- Restores are deterministic, but atomic and O3 runs place events at
  different instruction counts: [[window-placement]].
