---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [agentic, replay, measurement]
---

# About a fifth of agentic instructions are the replay driver's polling

**What it is:** the model-free replay driver (`sweagent_driver.py`, which
`OpencodeReplayDriver` subclasses) waits for OpenCode's next model request
in a loop: each time it finds none it runs `docker inspect <orchestrator>`
(`_orchestrator_running()`) and sleeps `_POLL_SECONDS = 0.05`. Each poll
forks the Docker CLI, a Go binary (runtime start, five threads, an API call
to `dockerd`), about **40M instructions** and ~160 switch-ins. It exists
only in the replay (the live run talked to a real model), and in the guest
it shares the single vCPU with OpenCode. In the trace it is the host
`run.sh` launch tree ([[opencode-harness]]).

**Size:** 17–22% of instructions in the traces so far (gin-2121 17%,
framework-52684 21.6%, redis window 22%, jq window 12%); 22–23% of a tool
call's span; 26% of framework-52684's context switches. Because the poll
period is in simulated time, a slower simulated core polls more per unit of
work.

**What to do:** report agentic shares and per-window metrics **with and
without the `run.sh` tree** where it matters ([[aggregating-metrics]]). The
sweep numbers so far include it. It is exactly the short-lived-process
behaviour worth studying, but produced by the benchmark harness, not the
agent. Whether the live capture had the same poller at the same rate is
open ([[questions]]).
