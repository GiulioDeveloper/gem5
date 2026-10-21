---
type: entity
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - "[[legacy-log/agentic/task-tracing-guide]]"
tags: [agentic, opencode, processes, tool-calls]
---

# Inside an agentic guest: OpenCode and the processes around it

**What runs:** OpenCode (on Bun/JavaScriptCore) inside a container, driven
by a model-free replay driver on the host. Each model response triggers
tool calls; some run inside OpenCode, some fork processes. Everything
shares one vCPU. This page is what the [[task-tracer]] observed; purposes
("tool server", "replay driver") are the benchmark's descriptions, not
facts the trace can show ([[trace-analysis#Process labels]]).

## Processes

| place | launch tree | what is there |
|---|---|---|
| container `python (1003)` | `python (1003)` | `python` (the tool server) → `faketime` → `opencode`, and every process OpenCode starts (`git`, `bash.fence-real`, `rg.fence-real` and their children) |
| container `python (1077)` | `python (1077)` | a second container's `python` (the orchestrator's model proxy) |
| host | `run.sh (519)` | `run.sh > watch_rounds.sh > sleep` and `run.sh > sudo > make > sh > uv > python3 > docker`: the replay driver and its Docker polling |
| host | one per service | `dockerd`, `containerd`, `containerd-shim`, `systemd-*`, `snapd`, ... |

(pids from gin-2121 / framework-52684; they differ per task.)

OpenCode's own threads: the main JS thread, `JITWorker`s, `Bun Pool N` (file
I/O thread pool), `HTTP`. Most context switches in the agentic traces are
**between OpenCode's threads** or **between the Docker CLI's threads**;
fenced tools contribute few ([[context-switch-classification]]).

## Tool calls

- **State machine in SQLite.** OpenCode keeps its session in SQLite with
  WAL (`opencode.db-wal`). Each state change of a tool part (`pending` →
  `running` → `completed` | `error`) is one `write()` of the 4 KiB page
  holding that JSON row, which the tracer records, so every transition has
  an exact instruction count. A finished call is also printed as a
  `tool_use` line to `agentic-benchmark-opencode.log`.
- **In-process tools:** `read`, `edit`, `write`, `todowrite`, `grep`,
  `glob` run inside `opencode`; their file I/O goes through `Bun Pool N`.
- **Subprocess tools:** `bash` runs as `bash.fence-real`; ripgrep as
  `rg.fence-real`, often a direct child of `opencode` (its search tools spawn
  it). So "kind" is observed per call, not inferred from the tool name.
- **The tools fence is inactive.** `fence-exec.sh` would move tools into a
  separate cgroup only when `/benchmark-fence/tools` is mounted; in the
  replay guests it is not (no `cgroup.procs` writes; `rg.fence-real` shares
  OpenCode's cgroup set).

## What a tool call costs (from single windows)

- A `read` of one 45-line file: 171M instructions running → completed
  (atomic, gin-2121), of which OpenCode 75%, `docker inspect` 22%. The span
  includes OpenCode serialising and persisting the part (three WAL page
  writes per state change) and JIT compilation (`JITWorker` 21%).
- A `bash` call (`ls /testbed && head -20 composer.json`): 1.02G
  instructions running → completed in framework-52684; the tool processes
  themselves span only ~70M of it (1.2%).
- Details and the microarchitectural picture: [[2026-10-08-tool-call-windows]],
  [[tool-call-runup-is-cold]].

## Rounds

The restore starts inside `RPOINT_REPLAY_ROUND 1` (start-up); the guest
prints `RPOINT_REPLAY_ROUND N` on `board.terminal`, and each later round
holds one model response and its tool calls. Rounds are billions of
instructions apart (framework-52684: ROUND 2 at ~3.56G, ROUND 3 at ~6.4G).
See [[window-placement]].
