---
type: concept
status: draft
updated: 2026-11-13
sources:
  - src/cpu/o3/tdm.cc
  - src/cpu/o3/rename.cc
  - "[[legacy-log/commit-notes/20261013-150754-add-top-down-accounting-from-gem5-pr-2392]]"
  - "[[2026-11-03-top-down-validation]]"
  - "[[2026-11-13-top-down-microbenchmarks]]"
  - https://github.com/gem5/gem5/pull/2392
  - "Yasin, A Top-Down Method for Performance Analysis and Counters Architecture, ISPASS 2014 (read 2026-11-13; not yet in docs/raw/papers)"
tags: [top-down, stats, o3]
---

# Top-down accounting in the O3 core

**What it is:** Yasin's top-down slot breakdown (ISPASS 2014), computed by
the O3 core in `src/cpu/o3/tdm.{hh,cc}` and reported under
`board.processor.start.core.topDown.*`. It started as an import of the
upstream gem5 PR #2392 (open, not merged), branch `topdown-pr2392`, and was
corrected on the merge into `gfdev` (2026-11-03,
[[2026-11-03-top-down-validation]]). The counters do not change timing:
every non-top-down stat is identical to the build without them.

Status: draft. Committed on `gfdev` (2026-11-04) so runs carry the
counters; the results are still under review by the user and may not be
accurate. The counters do not perturb other results
([[2026-11-03-top-down-validation]]).

## Names

One row per node: the paper's name, the gem5 stat (under
`<core>.topDown.`, where `<core>` is `board.processor.start.core` in
full-system runs and `board.processor.cores.core` in SE mode), and the key
the viewers and sweep tables use (`window_view.py`).

| paper | stat | viewer key | in the paper's tree |
|---|---|---|---|
| Retiring | `level1.retiring` | `td_retiring` | yes |
| Bad Speculation | `level1.badSpeculation` | `td_badspec` | yes |
| Branch Mispredicts | `badSpec.branchMispredicts` | `td_bs_branch` | yes |
| Machine Clears | `badSpec.machineClears` | `td_bs_clears` | yes |
| Frontend Bound | `level1.frontendBound` | `td_frontend` | yes |
| Fetch Latency | `frontend.fetchLatency` | `td_fe_latency` | yes |
| Branch Resteers | `frontend.branchResteers` | `td_fe_resteer` | yes, under Fetch Latency; defined differently here |
| Fetch Bandwidth | `frontend.fetchBandwidth` | `td_fe_bandwidth` | yes |
| Backend Bound | `level1.backendBound` | `td_backend` | yes |
| (none) | `backend.serializeBound` | `td_be_serialize` | **no**: from PR #2392 |
| Memory Bound | `backend.memoryBound` | `td_be_memory` | yes, normalised differently |
| Core Bound | `backend.coreBound` | `td_be_core` | yes, normalised differently |
| L1 Bound | `memory.l1Bound` | `td_mem_l1` | yes |
| L2 Bound | `memory.l2Bound` | `td_mem_l2` | yes |
| L3 Bound | (none) | (none) | no L3 in the V2 hierarchy |
| Ext. Memory Bound | `memory.extMemBound` | `td_mem_ext` | yes |
| Stores Bound | `memory.storeBound` | `td_mem_store` | yes, narrower condition |
| MicroSequencer, BASE | (none) | (none) | not implemented |
| MEM Bandwidth, MEM Latency | (none) | (none) | not implemented |

Raw counters behind them (the paper's Table 1 events):

| paper event | counter | where counted |
|---|---|---|
| TotalSlots | `renameWidth` × `topDown.cycles` | `CPU::tick`, idle cycles in `CPU::wakeCPU` |
| SlotsIssued | `rename.renamedInsts` | `Rename::renameInsts` |
| SlotsRetired | `commitStats0.numOps` | commit |
| FetchBubbles | `rename.fetchBubbles` (latency part: `rename.fetchLatencyBubbles`, `rename.resteerBubbles`) | `Rename::countFrontendBubbles`, `Rename::addIdleCycles` |
| RecoveryBubbles | `renameWidth` × `rename.status::Squashing` + `rename.refillBubbles` | rename |
| BrMispredRetired | `iew.branchMispredicts` (execute time, not retired) | `IEW::executeInsts`, `IEW::checkMisprediction` |
| MachineClears | `iew.memOrderViolationEvents` (only) | `IEW::executeInsts` |
| OpsExecuted[= FEW] | `topDown.execStallCycles` | `TopDownStats::countBackend`, called from `InstructionQueue::scheduleReadyInsts` |
| MemStalls.AnyLoad | `topDown.loadStallCycles` | same |
| MemStalls.L1miss / L2miss | `topDown.loadStallL1Miss` / `loadStallL2Miss` | same |
| MemStalls.L3miss | (none) | |
| MemStalls.Stores | `topDown.storeStallCycles` | same |
| MsSlotsRetired, ExtMemOutstanding | (none) | |

## Slots and Level 1

Slots are counted at **rename** (the dispatch point), `renameWidth` (8) per
cycle, over `topDown.cycles`: active cycles plus the cycles the CPU idles
(not WFI/quiesce, [[numcycles-excludes-wfi]]). `subtractIdleCycles=True`
leaves idle cycles out entirely.

| stat (`topDown.level1.`) | slots |
|---|---|
| `retiring` | committed micro-ops (`commitStats0.numOps`) |
| `badSpeculation` | renamed micro-ops never committed + rename's `Squashing` cycles × width + `rename.refillBubbles` (empty or squashed slots in the first `fetchToDecodeDelay + decodeToRenameDelay` = 5 cycles after a squash) |
| `frontendBound` | `rename.fetchBubbles`: slots the back end could take (min of width, free ROB, free IQ) that the front end left empty, outside the refill. None in a cycle where rename stopped on an instruction for a back-end reason: no LQ entry, no SQ entry, no physical register, or a serialize-before (since 2026-11-13) |
| `backendBound` | the rest |

`window_view.py` recomputes every node from these counters (checked
against the formulas block by block) and the viewers stack them
([[viewers]], [[sweeps]]). They stack only the paper's tree: since
2026-11-05 `branchResteers` is a metric of its own, not a part of fetch
latency in the bars.

## Level 2 and 3

| group | stats | how |
|---|---|---|
| `frontend` | `fetchLatency`, `fetchBandwidth`; `branchResteers` ⊂ `fetchLatency` | latency: bubbles in cycles where nothing reached rename. Resteers: those between the end of the refill and the first micro-op after a squash |
| `badSpec` | `branchMispredicts`, `machineClears` | bad speculation split **by event count**: execute-time branch mispredicts vs memory-order violations; squashes from commit (traps, interrupts) have no event and fall in by proportion |
| `backend` | `serializeBound`, `memoryBound`, `coreBound` | serialize: rename's `SerializeStall` cycles × width. The rest split by the share of `execStallCycles` (ROB not empty, ≤ 2 micro-ops issued) that are `loadStallCycles` (none issued, a load outstanding) or `storeStallCycles` (none issued, no load outstanding, SQ full) |
| `memory` | `l1Bound`, `l2Bound`, `extMemBound`, `storeBound` | by the deepest outstanding load's cache-miss depth (`Request::getAccessDepth`). The V2 hierarchy has no L3, so `extMemBound` is DRAM |

Idle cycles: rename charges them as front-end latency if it was running or
idle (in the refill window: bad speculation); the back end charges them to
the state it went idle in (ROB, deepest load, SQ).
On the agentic sweeps idle cycles are 6.6% of cycles in `base` and 0.3% with
a perfect L1I (medians of 27 tasks, `runs/fe-pl1d-pl1i/why_fe.md`), so
they are mostly instruction-miss waits (inferred from the data, not
checked in the code).

## Serialize

`serializeBound` is rename's `SerializeStall`: an instruction flagged
serialize-before waits at rename until the ROB is empty, and nothing
younger is renamed. In this Arm model every `MRS` (system-register read) is
serialize-before; `MSR`, `SVC`/`HVC`/`SMC`, `BRK` and `DSB` are
serialize-after (the next instruction waits); a write to a system register
that is still being produced is made serialize-before
(`rename.tempSerializing`). `ISB` squashes instead (bad speculation).
Agentic code reads `TPIDR_EL0` (thread-local storage) and `CNTVCT_EL0`
(timers) often; a real core likely does not drain for those, so serialize
bound on agentic windows is probably overstated (not checked: which
instructions dominate is open).

### How memory bound is measured, and what it misses (2026-11-09)

The code path: `InstructionQueue` calls `TopDownStats::countIssueCycle`
every cycle (`inst_queue.cc`). Idle cycles replay the state saved at
`noteIdle`. `countBackend` (`tdm.cc`) counts:
- an execution stall when the ROB is not empty and ≤ 2 instructions issued;
- a load stall when 0 issued and `LSQ::deepestOutstandingLoad() ≥ 0`;
- a store stall when 0 issued, no load outstanding and the SQ is full.

The depth is the largest `Request::getAccessDepth()` over every LQ entry
with a request outstanding (in translation, in flight, or a writeback
pending), not just the oldest load. `BaseCache::incMissCount` adds 1 for
each cache that misses (`BaseCache::access`, before the MSHR lookup). So 0
means an L1D hit or a translation in progress, 1 an L1D miss, and ≥ 2 an L2
miss. Level 3 is not measured slot by slot: `memoryBound` is shared out in
proportion to the stall cycles of each depth.

Blind spots, from the code and jq-2598 in the 11-04 base sweep (per 1,000
instructions):
- **Cycles where 1 or 2 instructions issue go to core bound,** even with a
  DRAM miss outstanding. This is the paper's definition (few micro-ops
  executed count as core). jq-2598 has 299 execution-stall cycles per
  1,000 instructions; only 75 are load or store stalls, so 224 go to core
  bound. Under `--perfect-l1d`, core bound falls 63% (agentic mean,
  [[2026-11-06-perfect-l1d]]), so much of it waits on memory. A split by
  outstanding miss would not be a paper category.
- **Secondary L1D misses stay at depth 1.** A load that merges into an
  L1D MSHR is never sent to the L2, so it counts as L2 bound even when the
  fill comes from DRAM. That is unless another load in the LQ has depth 2.
  It happens when the primary miss is an L1D prefetch (`pfLate` 0.94 per
  1,000 instructions), a store's ownership request, or a squashed load. On
  jq-2598, 60% of demand L1D misses are MSHR hits (1.96 of 3.23). The
  skew is from external memory toward L2, but small: L1-miss stall cycles
  are 45.5, of which 38.5 are at depth ≥ 2.
- **The depth rises only when the next cache sees the request.** A
  DRAM-bound load is at depth 1 for its first L1D + crossbar cycles: about
  15 of its ~333.
- **Walks count as L1 bound.** A load waiting for a table walk is
  outstanding at depth 0, even if the walk goes to DRAM; the walker's
  requests are its own. Intel also files DTLB misses under L1 bound.

## Conventions to keep in mind

- **"Issue" means two different things.** This project follows gem5:
  *dispatch* is rename → IQ (`IEW::dispatch`, `dispatchWidth`), *issue*
  is IQ → function units (`InstructionQueue::scheduleReadyInsts`,
  `issueWidth`). The paper uses Intel's terms, where *issue* is allocation
  into the back end and *executed* is leaving the reservation station. So:

  | paper | here |
  |---|---|
  | issue-pipeline slots, `SlotsIssued` | rename/dispatch slots, `rename.renamedInsts` |
  | `OpsExecuted`, "uops executed" | micro-ops issued from the IQ (`total_issued`, passed to `countIssueCycle`) |

  In `tdm.{hh,cc}` and on this page, "issued" (`fewIssuedThreshold`,
  `execStallCycles`, "none issued") is the gem5 sense, the paper's
  "executed".
- **Resteers are front end**: only the 5-cycle refill counts as bad
  speculation. `branchResteers` shows the extra. The 2014 paper already
  has Branch Resteers under Fetch Latency (its Figure 2 and section 3.4),
  and it puts the *whole* fetch from the correct target there, including
  what this code calls the refill (see Known problems).
- **Decode-time redirects** (BTB misses caught at decode,
  `decode.branchMispred`) never reach rename; their cost is front-end
  latency, not bad speculation.
- **The front end delivers at most 6 instructions** (`fetchWidth`,
  `decodeWidth` = 6) into an 8-wide rename, so part of `fetchBandwidth` is
  structural ([[neoverse-v2]]).
- **L1I hit latency shows up as fetch latency.** Fetch waits for each L1I
  response (`fetch.status::icacheWaitResponse` 22-31% of cycles even on
  SPEC with ~0 L1I misses), so on SPEC most of `fetchLatency` is the fetch
  model, not instruction misses ([[2026-11-03-top-down-validation]]).
- Fractions are per window only after summing the raw counters over stats
  blocks; per-block fractions are not averaged
  ([[aggregating-metrics]]). `runs/topdown/td_table.py` does this.

## Known problems

From the 2026-11-13 review of the code against the paper and from
[[2026-11-13-top-down-microbenchmarks]]. Only the register/SQ/LQ leak is
fixed (2026-11-13, uncommitted).

> [!conflict] Level 2 and 3 of the back end are not the paper's formulas
> The paper (Table 2) divides each node by *clocks*: Memory Bound =
> (MemStalls.AnyLoad + MemStalls.Stores) / Clocks, Core Bound =
> ExecutionStalls − Memory Bound, and likewise L1/L2/L3/Ext. Memory + Core
> equals ExecutionStalls, not Backend Bound; the paper says only sibling
> nodes are comparable. `tdm.cc` instead scales the ratio
> (`loadStall + storeStall`) / `execStall` into the back-end slots, which
> PR #2392 introduced. The memory-to-core ratio is the same either way; the
> absolute values are not. The user decided (2026-11-13) to follow the
> paper and not force the sum; not implemented yet.

> [!conflict] Front-end bound in every run before 2026-11-13 is too high
> Until the fix below, rename stalls on physical registers, the SQ or the
> LQ were counted as front-end bandwidth. The "small (≤ 0.001 of slots)"
> in the table below is the effect of the ROB/IQ cap alone and says
> nothing about this. On the kernels the leak was up to 0.27 of slots. On
> the agentic sweeps it is at most 0.076 of slots at the median of
> `20261104-1115-base` (front-end bound 0.416) and at most 0.023 on
> `20261106-2004-pl1d-pl1i` (0.513): one full rename width per stall
> event, an upper bound (`runs/microbench-tma/agentic-bound/`). Existing
> sweeps, viewers and pages carry the old numbers; the exact effect needs
> a rerun. The same slots are missing from back-end bound.

- **Fixed 2026-11-13: register, SQ and LQ stalls leaked into front-end
  bound.** Rename does not stay blocked on them (`Rename::checkStall`
  checks the ROB, the IQ, and LQ and SQ both full). It retries each cycle
  from its skid buffer, and `countFrontendBubbles` charged the slots the
  skid buffer did not cover to `fetchBandwidth` before rename found it
  could not proceed. Now `renameInsts` counts the bubbles after its loop
  and counts none when the loop stopped on an LQ, SQ, register or
  serialize-before condition. Timing is unchanged (same cycles on all 60
  runs). PR #2392 had the same leak for every resource.
- **Restart lag after a rename stall is front-end bound.** When rename
  has drained its skid buffer it idles until decode and fetch restart
  (rename → decode → fetch unblock signals). Those cycles are counted as
  fetch latency: `store-L2` (`fe8`) keeps front-end bound 0.156 with
  rename idle in 12.7% of cycles and fetch never waiting. A real core
  would have micro-ops queued. Not changed; open.
- **Overlapped work turns memory bound into core bound.** A cycle that
  issues 1 or 2 micro-ops with a miss outstanding is a core stall. An L2
  pointer chase with 32 independent adds per iteration reports memory
  0.08, core 0.54, though the chase sets its time. This is the paper's
  definition; memory bound is a lower bound.
- **Execution stalls use "ROB not empty".** Intel's implementation (the
  paper's Table 7) uses "reservation station not empty", which here is the
  IQ. With the ROB test, cycles where the front end starves the core count
  as core stalls.
- **The few-issued threshold is 2,** the paper's value for 4-wide Sandy
  Bridge-like cores, on an 8-wide issue stage.
- **`serializeBound` is not in the paper,** and its cycles also enter
  `execStallCycles`, so they dilute the memory/core ratio as well.
- **Store stalls are narrower than the paper's.** The paper: few micro-ops
  executed and no more stores can be issued (Intel: `RESOURCE_STALLS.SB`).
  Here: none issued, no load outstanding, SQ full.
- **Recovery is wider than the paper's.** The paper's RecoveryBubbles are
  slots where the issue pipeline is blocked recovering (here: rename's
  `Squashing` cycles). The 5-cycle refill is fetch from the correct
  target, which the paper files under Branch Resteers.
- **The bad-speculation split uses the wrong events.**
  `iew.branchMispredicts` counts at execute, wrong-path branches included
  (the paper: retired mispredicts; `commit.branchMispredicts` is not
  retired either). `iew.memOrderViolationEvents` also counts violations
  that cause no squash (`iew.cc`, the "already squashing" branch). Squashes
  from commit (traps, interrupts, squash-after) have no event.
- **Squashed micro-ops met at rename** each add one `refillBubbles` without
  using a slot, so more than `renameWidth` can be counted in a cycle.

## Differences from upstream PR #2392

Bugs fixed on the merge, with what they did on the validation windows:

| upstream | fix | effect |
|---|---|---|
| load stall = no FU busy and *any* load in the LQ, done or not | a load with a translation or memory access outstanding | `memoryBound` roughly halves (llvm 0.133 → 0.062, gin 0.180 → 0.075) |
| `fetchLatency` from the fetch stage's counter, L1 from rename's | both from rename, in slots | `fetchBandwidth` can no longer go negative |
| `badSpec` split counts decode redirects as mispredicts | execute-time mispredicts only | small |
| L3 bins (depth 3) on a hierarchy without an L3 | `l1/l2/extMem` | DRAM was reported as `l3Bound` |
| execution stalls = cycles with 0-2 busy FUs − rename idle cycles | cycles with ROB not empty and ≤ 2 issued | core bound no longer depends on a cross-stage subtraction |
| front-end bubbles counted even when ROB/IQ were full | capped at the free ROB/IQ entries | small (≤ 0.001 of slots) |
| front-end bubbles counted when rename stopped on registers, SQ, LQ or a serialize | none counted in such a cycle (2026-11-13) | up to 0.27 of slots on the kernels; ≤ 0.076 on the agentic base sweep (bound) |
| `subtractIdleCycles` removed cycles but still added idle bubbles | both or neither | |
| `tdaCycles` never counted on active cycles (fixed on the branch) | `topDown.cycles` | |

Also removed: the unused CPU stage counters, the fetch-stage bubble
counters, the duplicate `commit.committedInst` (= `commitStats0.numOps`),
the placeholder stat descriptions. Upstream review issues still open
upstream (idle cycles, overlapping mispredicts, the LSQ `mainReq` assert)
are handled here: idle cycles above; overlapping squashes reset one refill
window instead of adding a fixed penalty each; split loads take the deepest
fragment.
