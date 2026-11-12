---
type: concept
status: draft
updated: 2026-11-09
sources:
  - src/cpu/o3/tdm.cc
  - src/cpu/o3/rename.cc
  - "[[legacy-log/commit-notes/20261013-150754-add-top-down-accounting-from-gem5-pr-2392]]"
  - "[[2026-11-03-top-down-validation]]"
  - https://github.com/gem5/gem5/pull/2392
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

## Slots and Level 1

Slots are counted at **rename** (the dispatch point), `renameWidth` (8) per
cycle, over `topDown.cycles`: active cycles plus the cycles the CPU idles
(not WFI/quiesce, [[numcycles-excludes-wfi]]). `subtractIdleCycles=True`
leaves idle cycles out entirely.

| stat (`topDown.level1.`) | slots |
|---|---|
| `retiring` | committed micro-ops (`commitStats0.numOps`) |
| `badSpeculation` | renamed micro-ops never committed + rename's `Squashing` cycles × width + `rename.refillBubbles` (empty or squashed slots in the first `fetchToDecodeDelay + decodeToRenameDelay` = 5 cycles after a squash) |
| `frontendBound` | `rename.fetchBubbles`: slots the back end could take (min of width, free ROB, free IQ) that the front end left empty, outside the refill |
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

- **Resteers are front end**, as in Intel's later TMA versions: only the
  5-cycle refill counts as bad speculation. `branchResteers` shows the
  extra.
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
| `subtractIdleCycles` removed cycles but still added idle bubbles | both or neither | |
| `tdaCycles` never counted on active cycles (fixed on the branch) | `topDown.cycles` | |

Also removed: the unused CPU stage counters, the fetch-stage bubble
counters, the duplicate `commit.committedInst` (= `commitStats0.numOps`),
the placeholder stat descriptions. Upstream review issues still open
upstream (idle cycles, overlapping mispredicts, the LSQ `mainReq` assert)
are handled here: idle cycles above; overlapping squashes reset one refill
window instead of adding a fixed penalty each; split loads take the deepest
fragment.
