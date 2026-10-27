---
type: experiment
status: current
updated: 2026-10-27
sources:
  - runs/rubocop-15G/launch.sh
  - runs/rubocop-15G/split_stall.sh
  - runs/rubocop-15G/analyse.sh
  - runs/rubocop-15G/common/compare/compare_multi.csv
  - runs/rubocop-15G/checks/per-process.txt
  - runs/rubocop-15G/checks/process-views.csv
  - runs/rubocop-15G/checks/switch-exclusion.txt
  - runs/rubocop-15G/checks/harness-vs-tools.txt
tags: [agentic, rubocop, caches, btb, tlb, pc-trace, long-run]
---

# rubocop over 15G detailed instructions: caches ×1/×4/×8, with and without infinite BTB + L2 TLB

## Question

How does one agentic task behave over a long detailed run (15G
instructions instead of a 400M window), and how much do larger caches and
the BTB/TLB ceilings ([[btb-tlb-limits]]) gain? The runs also record a
[[pc-trace]] of every committed instruction, for footprint and repeat
distance metrics later.

## Setup

- Checkpoint rubocop-13560 cpt.0 (GLM-5.2 agent), [[neoverse-v2]] O3 core.
  Launcher `runs/rubocop-15G/launch.sh` (commit 07fb4950bb + uncommitted
  `--cache-scale`): `pc-trace.sh` with `O3="1 20000000 15000000000"`
  (settle 1, 20M warm-up, 15G detailed), `--stats-interval-insts 200000`.
  Started 2026-10-23 17:37, six runs in parallel.
- Six configurations: {baseline, `--infinite-btb --infinite-tlb`} ×
  `--cache-scale` {1, 4, 8}. The scale multiplies the L1I, L1D and L2 sizes
  (more sets; same associativity and latencies): ×8 is 512 KiB L1s and a
  16 MiB L2.
- **Four runs hit a guest stall at simulated tick ≈ 4.6228e12**
  ([[guest-trng-hvc-stall]]; the cause is a hypothesis still to
  investigate): the guest spins in the EL2 hyp stub until the
  run ends. The two ×8 runs reached 15G before it; `normal` and
  `infbtbtlb` were stopped by hand (SIGTERM, 2026-10-25) after 42 h.
  `split_stall.sh` (now `analysis_scripts/tasktrace/split_stall.sh`) moved everything after the stall into `<run>/stall/`
  (PC trace from the switch into the kworker; stats blocks from the first
  block that starts after it); blocks, rows and instructions add up exactly.

| run | pre-stall detailed blocks (200K) | stall blocks | wall time to the end |
|---|---|---|---|
| normal | 60,136 (12.03G) | 7,202 | stopped at 42 h |
| infbtbtlb | 66,032 | 6,607 | stopped at 42 h |
| cache4x | 70,222 | 4,778 | 40.2 h |
| infbtbtlb-cache4x | 73,515 | 1,485 | 33.1 h |
| cache8x | 75,000 (no stall) | — | 30.4 h |
| infbtbtlb-cache8x | 75,000 (no stall) | — | 30.5 h |

- Cost: 124–176K instructions/s before the stall, ~22K/s in it; gem5 RSS
  grew from ~3 GB to ~8.6 GB per run (the guest touching more memory),
  ~51 GB for six. Output per run after the split: PC trace 0.37–0.54 GB,
  stats table 0.23–0.27 GB (20–22 GB of text each), ~0.9 GB in total.
- Analysis (`runs/rubocop-15G/analyse.sh`; the general version is
  `analysis_scripts/tasktrace/compare_runs.sh`, [[long-runs]]): `trace_analysis.py` and
  `window_view.py` per run over its pre-stall region (`<run>/analysis/`);
  a **common region**, the first 60,136 blocks (12.03G instructions) of
  every run, in `common/<config>/` with `sweep_summary.py` per config and
  `sweep_compare.py` of all six against `normal`
  (`common/compare/compare_multi.csv`); per-process aggregates over blocks
  that are ≥95% one process (`checks/per-process.txt`).
- PC-join check on cache8x: all 22,631 complete slices between task
  markers equal the tracer's instruction count without NOPs
  (`checks/cache8x-slices.txt`). On the four split runs (2026-10-27,
  `check_pc_slices.sh`, pre-stall part): every slice equal too, 20,213
  (normal), 20,962 (infbtbtlb), 22,003 (cache4x), 22,552 (inf+4x), none
  different (`checks/<run>-slices.txt`).

## Results

### Same instructions, different work

Over the common 12.03G instructions the configurations do not do the
same guest work: a faster core gets further into the agent's session in
the same instruction count, while the wall-clock-driven parts (Docker
polling, OpenCode waiting) shrink. Instruction share by process in the
common region:

| process | normal | infbtbtlb | cache4x | cache8x | inf+4x | inf+8x |
|---|---|---|---|---|---|---|
| opencode | 71.1% | 67.1% | 65.5% | 60.8% | 64.0% | 60.5% |
| docker | 14.4% | 13.9% | 12.6% | 12.0% | 12.3% | 11.4% |
| bundle (rubocop's Ruby test run) | 3.1% | 7.9% | 9.7% | 15.7% | 12.6% | 15.8% |
| simulated seconds | 4.41 | 4.01 | 3.81 | 3.47 | 3.61 | 3.34 |

Agent rounds reached by the end of each run (`board.terminal`): 14
(normal), 15, 16, 17 (cache8x), 16, 17. So whole-region metrics mix the
uarch effect with a shift in work mix: in the common region the cache runs
show branch MPKI +24–26%, squashed instructions +19–22% and dTLB MPKI +13%,
which come from the mix, not from the caches.

### Whole common region (`compare_multi.csv`)

| metric | normal | infbtbtlb | cache4x | cache8x | inf+4x | inf+8x |
|---|---|---|---|---|---|---|
| IPC | 0.921 | 1.011 (+9.8%) | 1.063 (+15.4%) | 1.172 (+27.3%) | 1.139 (+23.7%) | 1.222 (+32.7%) |
| L1I MPKI | 1.81 | 1.12 | 1.17 | 0.86 | 0.63 | 0.47 |
| L1D MPKI | 16.3 | 15.7 | 12.0 | 9.4 | 11.4 | 9.1 |
| L2 MPKI | 10.9 | 8.6 | 6.9 | 4.5 | 5.3 | 3.7 |
| iTLB MPKI | 32.3 | 15.6 | 31.5 | 29.6 | 14.3 | 13.7 |
| BTB-miss mispredicts PKI | 1.23 | 0.15 | 1.34 | 1.36 | 0.15 | 0.15 |
| completed walks PKI | 1.09 | 0.09 | 1.32 | 1.26 | 0.09 | 0.09 |
| context switches per M instructions | 1.68 | 1.57 | 1.62 | 1.51 | 1.50 | 1.49 |

(IPC is the window value, total instructions over total cycles. The mean
of the per-block IPCs is higher, 1.147 for normal, because equal-instruction
blocks over-weight the fast ones: [[aggregating-metrics]].)

### Per process (blocks ≥95% one process, whole pre-stall region)

IPC change against `normal`:

| process (normal IPC) | infbtbtlb | cache4x | cache8x | inf+4x | inf+8x |
|---|---|---|---|---|---|
| opencode (0.950) | +7.3% | +11.4% | +20.5% | +18.4% | +26.4% |
| bundle (1.261) | +5.3% | +18.0% | +25.1% | +20.8% | +29.3% |
| docker (0.952) | +3.0% | +8.2% | +13.3% | +9.5% | +15.3% |
| git (0.986) | +1.9% | +7.7% | +12.4% | +9.7% | +14.6% |
| python3 (1.311) | +10.9% | +11.3% | +13.9% | +18.6% | +19.6% |

- **Caches:** within every process, ×4 and ×8 cut L1I, L1D and L2 misses
  steadily (bundle L2 MPKI 4.3 → 1.8 → 0.8; opencode 11.6 → 7.8 → 5.3)
  and raise IPC by 8–18% (×4) and 12–25% (×8).
- **Infinite BTB + L2 TLB** removes almost all BTB-miss mispredicts and
  completed walks in every process, and adds on top of the larger caches
  (opencode +20.5% → +26.4% at ×8).
- **OpenCode's own branch MPKI rises with cache size** (4.0 → 5.9 → 6.2),
  and its dTLB MPKI and walks too, unlike every other process. Likely the
  same mix effect inside OpenCode: in slower configurations it spends more
  instructions in highly predictable wait/poll loops (the PC trace opens on
  a `b; subs; b.ne` spin in a Bun pool thread), which dilute its
  per-instruction miss rates. Not checked yet.

### Harness against tools, around context switches (`process_views.py`)

Per slice between two switches (2026-10-27; [[long-runs#Process views]]),
pre-stall region of each run. Harness = OpenCode and its own git
snapshots; tools = processes under the fence wrappers; the replay driver
and Docker are separate. In `normal` the harness has 73.9% of the time,
the driver 20.7%, the tools 2.8%. Group IPC, and its change against
`normal` in the same view:

| group | view | normal | infbtbtlb | cache4x | cache8x | inf+4x | inf+8x |
|---|---|---|---|---|---|---|---|
| whole task | all | 0.909 | +9.8% | +16.7% | +27.2% | +22.2% | +32.5% |
| | skip3 | 1.010 | +6.5% | +14.1% | +23.0% | +19.0% | +27.4% |
| harness | all | 0.923 | +7.9% | +12.1% | +21.4% | +19.1% | +27.3% |
| | skip3 | 0.995 | +5.4% | +10.8% | +18.7% | +16.2% | +23.3% |
| tools | all | 1.147 | +10.7% | +25.1% | +34.3% | +29.2% | +38.4% |
| | skip3 | 1.250 | +7.0% | +19.4% | +26.2% | +22.2% | +29.8% |
| driver + Docker | all | 0.891 | +7.3% | +12.3% | +19.5% | +16.9% | +23.5% |
| | skip3 | 1.012 | +3.2% | +7.7% | +12.0% | +9.0% | +13.9% |

- **Tools run faster than the harness**: 1.24× its IPC in `normal`,
  1.35–1.39× with larger caches; they also gain more from every
  configuration.
- **Much of each gain sits next to the switches**: dropping 3 blocks at
  each end of every process run lowers the gains (the infinite BTB + TLB
  from +9.8% to +6.5% over the whole task), and the driver's most. The
  trimmed IPC of `normal` is 11% higher than the whole-slice one.
- `skip6` keeps few blocks of the short processes (tools, other), so it is
  noisier there. Kernel threads have almost no runs longer than 3 blocks.

Upper bound of the switch cost over the whole region
(`runs/rubocop-15G/switch_exclusion.py`): removing every 200K block that
holds a switch raises `normal`'s IPC by 9.7% (11.6% of the blocks), and
that block with its neighbours by 13.7% (21.9% of the blocks); on
infbtbtlb-cache8x by 4.2% and 6.6%. The gain is all in the front end
(L1I, iTLB, BTB and branch MPKI fall; L1D does not move). With the switch
blocks removed the configuration gains shrink (cache8x +27.0% → +21.1%),
so part of each gain is faster recovery after a switch.

Built for a dashboard: `runs/rubocop-15G/entity_views.py` and
`dash_rows.py` (the experiment versions of `process_views.py`) fed
<https://claude.ai/artifact/7gqgixiSYp2CpJj48Nbz8D> (private; source in
`runs/rubocop-15G/dashboard/`). Its whole-slice IPCs use 333.33 ticks per
cycle instead of config.ini's 333, so they are 0.1% lower than
`process_views.py`'s.

## Conclusions

- Provisional, one task: on rubocop the infinite BTB + L2 TLB gain is
  +2–11% per process (+7% for OpenCode), in line with the 400M-window
  sweeps ([[btb-tlb-limits]]: rubocop +11.9% with both). Larger caches
  give more: ×8 caches gain more than the BTB/TLB ceilings, and the two
  add up.
- **Comparisons across configurations over a fixed instruction count are
  confounded by the work mix** in agentic runs: the guest does
  timing-dependent work. Compare per process (or per phase), not over the
  whole window. This matters for the existing sweep comparisons too
  ([[comparing-configurations]]).
- Long runs of these checkpoints can stop doing useful work a few
  simulated seconds after the restore. The RNG-reseed explanation
  ([[guest-trng-hvc-stall]]) is not confirmed and needs a separate
  investigation; the results here use only the region before the hang.

## Decisions

- 2026-10-23: 200K stats blocks, PC trace on, all six in parallel; cache
  scaling keeps latencies (an upper bound on the capacity gain).
- 2026-10-25: stopped `normal` and `infbtbtlb` inside the stall; kept the
  stall parts in `<run>/stall/` for the stall investigation.
- 2026-10-27: the reusable scripts moved to `analysis_scripts/tasktrace/`
  (`split_stall.sh`, `check_pc_slices.sh`, `compare_runs.sh`,
  `process_views.py`); the experiment's own copies stay in
  `runs/rubocop-15G/`.
- 2026-10-25: common region = the shortest pre-stall region (normal's
  60,136 blocks); per-process aggregates as the main comparison because of
  the work-mix shift.

## Open

- PC-trace metrics: instruction footprint per process, unique branches,
  PC repeat distance (definitions to settle: time vs stack distance; PC,
  line or page granularity).
- Check the OpenCode polling explanation with the PC trace (share of
  instructions in the spin loops per configuration).
- Compare per agent phase (tool calls, rounds) instead of per instruction.
