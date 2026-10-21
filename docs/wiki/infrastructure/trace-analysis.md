---
type: howto
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - analysis_scripts/tasktrace/trace_analysis.py
tags: [analysis, tracer, tool-calls]
---

# Trace analysis: `trace_analysis.py`

```sh
python3 analysis_scripts/tasktrace/trace_analysis.py <run> [--window K]
```

Host Python, stdlib only. Reads `tasktrace.jsonl` ([[trace-format]]) and,
when present, `intervals.csv` + `stats.txt` ([[stats-blocks]]); writes
`<run>/analysis/` and prints `summary.md`. It is also the library the
viewers and sweep tools import (`load_events`, `load_blocks`, `Tree`, ...).

## Outputs

| file | contents |
|---|---|
| `summary.md` | event rates per M instructions and per simulated ms; instruction shares by place, launch tree and process; top processes with lineage; tool calls; fence verdict; the user-fraction cross-check |
| `processes.csv` | per process: names over its life (`python3\|docker` = fork then exec), kind, place, launch tree, lineage, exec path and argv, user and kernel instructions, switch-ins |
| `containers.csv` | one row per place and its member processes |
| `switches.csv` | switches by cause, with scheduler cost (p50/p90/mean instructions, ns) and the kernel share of the slice each switch ended |
| `writes.csv`, `reads.csv` | recorded writes (traced process + `cgroup.procs`) and reads |
| `tools.csv` | one row per OpenCode tool call (below) |
| `blocks.csv` | per stats block: IPC, user fraction (gem5 and trace), scheduler PKI, L1I/L1D/L2 MPKI, branch and BTB mispredicts PKI, TLB misses and walk requests PKI, dominant process and tree, shares, events |
| `aligned.csv` | per event kind, each metric averaged over blocks at offsets −K..+K from the event's block, beside the all-blocks mean |

## Who ran when

Between two `switch` events the CPU belongs to the first switch's `next`.
Work in interrupt or kernel context counts to the current task (system
calls, faults, interrupts and the scheduler run under its pid); only kernel
threads have pids of their own. The slice before the first switch belongs
to that switch's `prev`; the last slice runs to the end of the last stats
block; a trace with no switch has one `not recorded` slice. Each slice is
split into user and kernel instructions by its `uinsts` difference; a range
that cuts a slice assumes an even spread.

## Process labels

Labels are facts the trace supports, never guesses at purpose (an earlier
role scheme, "any host user process is the replay driver", mislabelled
`snapd`, `run.sh` and the SPEC benchmarks, and was removed):

| label | what |
|---|---|
| kind | `user`, `kernel` (`PF_KTHREAD`), `idle` (pid 0) |
| name | latest name; a fork child keeps its parent's name until it execs |
| place | `host`, or `container <top> (<tgid>)`: a namespace set entered under a `containerd-shim`, named after its first process. systemd-sandboxed host services count as host. A process with no recorded `ns` takes its parent's |
| launch tree | `<name> (<tgid>)` of the topmost ancestor below systemd, or the container's top process |
| lineage | names from the tree root down, e.g. `run.sh > sudo > make > sh > uv > python3 > docker` |

What each label looks like in practice: [[opencode-harness]].

## Tool calls (`tools.csv`)

Parsed from OpenCode's WAL page writes ([[opencode-harness#Tool calls]]).
Rows are brace-balanced JSON objects; a row cut at the page end is read
with field regexes; a page also carries stale neighbouring rows, so a state
counts from its first appearance.

| column | meaning |
|---|---|
| `tool`, `input` | tool name; file path or command |
| `kind` | `in-process`, or `subprocess (<names>)` when a descendant of the recording process ran during the call (observed) |
| `io`, `io_insts` | the call's own first read/write of its file |
| `pending_insts` … `logged_insts` | instruction count at the first write showing each state |
| `run_insts`, `run_ms` | running → completed |
| `start_ms`, `end_ms` | the call's own guest-clock times (faketime) |
| `run_share_{caller,descendants,kernel,idle,other}` | who ran during the span |
| `run_top_processes`, `run_top_threads` | top five |

**Two views of a tool call.** *Framework view*: what the model asked for,
start to end (`tools.csv`); in-process tools are harness work. *CPU view*:
every change of execution context, whoever causes it (`switches.csv`). Use
the first to say what the agent was doing and the second as the unit of
disruption. Switch classification: [[context-switch-classification]].

Aggregating the per-block numbers: [[aggregating-metrics]].
