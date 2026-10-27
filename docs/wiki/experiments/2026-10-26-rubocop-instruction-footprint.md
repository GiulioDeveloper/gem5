---
type: experiment
status: current
updated: 2026-10-27
sources:
  - runs/rubocop-15G/cache8x/footprint/summary.md
  - runs/rubocop-15G/cache8x/footprint/footprint.csv
  - runs/rubocop-15G/cache8x/footprint/instances.csv
  - runs/rubocop-15G/cache8x/footprint/threads.csv
  - runs/rubocop-15G/cache8x/footprint/report.html
  - analysis_scripts/tasktrace/pc_footprint.py
tags: [agentic, rubocop, footprint, icache, branches, pc-trace]
---

# Instruction footprint, LRU hit rates and branches per process (rubocop, 15G)

## Question

How large is each process's code, how would it fit L1I and L2 sizes of
×1/×4/×8, and how many distinct branches does each one have? From the
committed PC stream rather than from the cache model.

## Setup

- The PC trace of the cache8x run of
  [[2026-10-23-rubocop-15g-cache-btb-tlb]] (15.2G instructions, no guest
  stall; one run, as the footprint is a property of the stream).
- `pc_footprint.py runs/rubocop-15G/cache8x` ([[pc-trace#Footprint, hit rates and branches]]):
  14 min, 1.5 GB. All 22,632 switches and 271 execs placed; the
  instruction count matched the switch events at every marker.
- Groups are process names; user addresses are per process instance (tgid
  between execs; threads share it); kernel code is `[kernel]`, also counted
  per process it ran for. LRU = fully associative, instruction lines only,
  no prefetch.

## Results

Whole stream, shared view, LRU misses per 1,000 instructions:

| L1I 64K | 256K | 512K | L2 2M | 8M | 16M |
|---|---|---|---|---|---|
| 3.96 | 1.81 | 1.12 | 0.51 | 0.20 | 0.16 |

For comparison, gem5's L1I MPKI (set associative, with FDP and the tagged
prefetcher; common 12G region) is 1.81 at 64K and 0.86 at 512K.

| process | instances | instructions | distinct insts | code (KiB) | ×64K | ×2M | private MPKI 64K / 512K / 2M / 8M | shared MPKI 64K / 2M | cold MPKI | distinct branches (taken) |
|---|---|---|---|---|---|---|---|---|---|---|
| opencode | 165* | 7,971M | 1.87M | 10,094 | 158 | 4.9 | 2.99 / 1.10 / 0.35 / 0.02 | 3.08 / 0.54 | 0.02 | 336K (217K) |
| [kernel] | — | 2,498M | 161K | 919 | 14 | 0.45 | 4.47 / 0.13 / 0.01 / 0.01 | 7.61 / 0.33 | 0.01 | 32K (23K) |
| bundle | 2 | 1,773M | 418K | 2,238 | 35 | 1.1 | 2.66 / 0.04 / 0.02 / 0.02 | 3.44 / 0.04 | 0.02 | 89K (67K) |
| docker | 55 | 1,238M | 13.1M | 72,346 | 1,130 | 35 | 2.34 / 1.02 / 0.94 / 0.94 | 3.92 / 0.95 | 0.94 | 2.25M (1.66M) |
| gem | 1 | 472M | 198K | 1,056 | 17 | 0.52 | 2.17 / 0.06 / 0.04 / 0.04 | 2.80 / 0.06 | 0.04 | 42K (31K) |
| git | 161 | 388M | 5.8M | 34,330 | 536 | 17 | 1.63 / 1.42 / 1.42 / 1.42 | 3.68 / 1.43 | 1.42 | 1.13M (773K) |
| python3 | 56* | 324M | 88K | 525 | 8 | 0.26 | 1.95 / 0.03 / 0.03 / 0.03 | 2.83 / 0.92 | 0.03 | 20K (10K) |
| ruby | 1 | 276M | 177K | 966 | 15 | 0.47 | 2.55 / 0.07 / 0.06 / 0.06 | 3.12 / 0.08 | 0.06 | 37K (28K) |

\* Mostly fork children that ran a few KiB of the parent's code before
their exec; the main OpenCode process is one instance of 9.5 MB.

One docker instance is ~1.3 MB of code (a Go binary) and one git instance
~200 KB (max 327 KB); their totals are the sum over 55 and 161 short-lived
processes. Kernel code run on behalf of docker and git is ~0.94G
instructions each, as much as their user code.

### Per PID and aggregated by name (second pass, 2026-10-26)

Rerun with three views (`footprint-v1/` holds the first pass; 23 min,
2.7 GB): 541 processes ran user code, 271 of them fork children that ran
~500 instructions of the parent's code before their exec (flagged
`pre_exec_fork`, left out of per-name statistics).

- **Per PID:** the 55 docker processes are near-identical runs: 22.5M
  instructions, 1,316 KiB of code, 2.35 MPKI at 64K and 0.93 at 2M each,
  ~41K branches (30K taken), plus ~17M kernel instructions each. git's 161
  processes vary more: median 2.5M instructions and 195 KiB of code (max
  6.3M, 327 KiB). The two `bundle` processes are the same test run twice
  (888M and 885M instructions, 1,119 KiB each).
- **Aggregated by name** (same-name processes share one address space):
  the code barely shrinks: `overlap` (aggregated / summed footprint) is
  0.978 for docker and 0.986 for git, and their misses beyond 256K stay
  cold (0.91 and 1.40 MPKI). Separate runs share almost no code
  addresses: the binaries and libraries load at randomized addresses
  (ASLR). Overlap below 1 comes from fork children, which share the
  parent's layout (opencode 0.939, python3 0.58). So this view cannot show
  what a physically tagged cache would keep between runs; that needs each
  run's load addresses.

### Per thread (third pass, 2026-10-27)

Rerun with per-thread statistics and the repeat distance per instruction
address (43 min, 7.8 GB): 944 threads committed instructions. Report:
`runs/rubocop-15G/cache8x/footprint/report.html`, published as
https://claude.ai/artifact/WggFB79GWaW6x7nUsun7So. Each thread's stream
includes the kernel code run while it was current. Repeat distance:
distinct instructions or lines since the previous use, median / 90th /
99th percentile.

| thread | instructions | kernel | code (KiB) | ×64K | ×2M | repeat distance, instructions | lines | MPKI 64K / 2M | branches (taken) |
|---|---|---|---|---|---|---|---|---|---|
| opencode main | 6,865M | 2% | 6,985 | 109 | 3.4 | 68 / 1,078 / 116,840 | 7 / 105 / 8,056 | 3.25 / 0.25 | 232K (146K) |
| opencode JITWorker 1263 | 989M | 5% | 2,914 | 46 | 1.4 | 124 / 2,138 / 98,470 | 12 / 194 / 7,233 | 3.65 / 0.08 | 101K (69K) |
| opencode JITWorker 1264 | 279M | 4% | 2,463 | 39 | 1.2 | 126 / 2,616 / 105,793 | 11 / 213 / 7,960 | 4.45 / 0.16 | 84K (57K) |
| bundle 2482 | 968M | 8% | 1,581 | 25 | 0.77 | 497 / 5,426 / 52,655 | 24 / 431 / 4,421 | 4.99 / 0.03 | 60K (44K) |
| gem 2704 | 501M | 6% | 1,471 | 23 | 0.72 | 531 / 4,645 / 43,347 | 24 / 399 / 2,862 | 3.70 / 0.05 | 56K (41K) |
| python3 622 | 363M | 11% | 587 | 9.2 | 0.29 | 733 / 11,525 / 53,183 | 42 / 674 / 3,560 | 3.40 / 0.03 | 21K (12K) |
| docker (typical of 55) | 25–29M | 43–50% | ~1,170 | 18 | 0.57 | ~395 / 3,450 / 39,000 | 21 / 310 / 1,950 | 2.7 / 0.66 | 37.6K (27K) |

- OpenCode's 9.5 MB process splits into a main thread of 7.0 MB and JIT
  workers of 2.5–2.9 MB each, which compile and so touch much code once.
- OpenCode's main thread repeats much sooner than the Ruby or Python
  interpreters (median 68 vs ~500 instructions, 7 vs 24 lines): its
  polling loops. Its 99th percentile is ~2× theirs (117K instructions,
  8K lines = 512 KiB), which is why it needs a large L2.
- The docker client's threads spend half their instructions in the
  kernel; at 2M their misses are cold (0.66 MPKI).

## Conclusions (provisional)

- **OpenCode's code is ~10 MB** (JIT-compiled JavaScript plus the Bun
  runtime), 5× a 2 MB L2, yet its working set is far smaller: alone, LRU
  misses fall from 3.0 MPKI at 64K to 0.35 at 2M and ~0 at 8M. An 8 MB
  L2 would hold it; 2 MB does not.
- **Everything except OpenCode fits in 512K–2M once warm**: the kernel
  (919 KB), Ruby (bundle/gem/ruby, ~1–2 MB each) and Python all fall to
  ≤0.1 MPKI at 512K privately.
- **Short-lived tools are cold, not large**: docker and git misses beyond
  256K are almost all cold (0.94 and 1.42 MPKI), so bigger caches do not
  help them; only keeping their code across invocations would. Caveat:
  without physical addresses every instance counts as new code, while real
  caches (physically tagged L2) can keep a binary's code across
  invocations through the page cache. These cold numbers are an upper
  bound.
- **Interference:** the kernel suffers most from sharing (7.6 vs 4.5 MPKI
  at 64K, 0.33 vs 0.01 at 2M), consistent with
  [[switch-cost-is-around-the-switch]].
- **Distinct branches dwarf the BTB:** OpenCode alone has 217K taken
  branches against a 12K-entry BTB, docker 30K per instance, git ~5K per
  instance.

## Decisions

- 2026-10-26: one run (cache8x), process names as groups, instances per
  tgid between execs, kernel separate; LRU stack distance and footprint
  against capacity; branches by type with taken-ever.
- 2026-10-26: added a per-PID view and a per-name view where same-name
  processes share addresses, on request.
- 2026-10-27: added per-thread statistics, the repeat distance per
  instruction address, and `report.html`, the per-thread page meant for
  every future footprint pass.

## Open

- Code shared across runs of the same binary: needs each process's load
  addresses (the tracer records none), or an alignment heuristic. The
  same-address aggregation shows no sharing because of ASLR.
- Repeat distance in time (instructions executed between repeats), and
  per 4 KiB page for the instruction TLB: not computed.
- Inside OpenCode's main thread, JIT code vs the Bun runtime: needs the
  code's mapping (JIT regions vs the binary).
