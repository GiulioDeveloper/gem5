# InfiniteBTB: how much do BTB misses cost the agentic workloads?

**Started:** 2026-10-16 · **Branch:** `gfdev`

A record of the unbounded-BTB limit study: why it is built the way it is and
what the runs show. Newest entries last.

Design and code references:
[`docs/garfield/infinite-btb.md`](../../garfield/infinite-btb.md).

---

## Where things are

| path | what |
|---|---|
| `src/cpu/pred/infinite_btb.{hh,cc}`, `BranchPredictor.py` (`InfiniteBTB`) | the BTB |
| `src/arch/generic/mmu.hh` (`currentAsid`), `src/arch/arm/mmu.cc` | ASID query, generic with an Arm override |
| `src/cpu/pred/btb.hh`, `bpred_unit.hh`, `src/cpu/o3/cpu.cc` | thread-context plumbing to the BTB |
| `src/cpu/pred/simple_btb.cc` | `evictions` stat now counted |
| `configs/garfield/arm/{neoverse_v2,sim_opts}.py` | `NeoverseV2_InfiniteBTB`, `--infinite-btb` |
| `run_scripts/btb/infinite-btb-compare.sh` (removed 2026-10-20) | baseline vs. infinite on one O3 window: `o3-window.sh` twice, the second with `--infinite-btb` |
| `runs/btb/20261016-144224-gin-2121/` | first comparison (40M instructions) and a short stats check |

## Goal

The Neoverse V2 config uses the decoupled front-end, where the BTB both
*detects* branches and supplies their targets. A branch the BTB misses goes
unnoticed until predecode. Before looking at oracles, measure the ceiling
gained by removing capacity, conflict and aliasing misses: only compulsory
misses (the first taken occurrence) remain.

## Decision log

### 1. Hash maps instead of a huge set-associative `SimpleBTB`

`AssociativeCache` scans every way and copies the set's pointer vector on
each lookup, and BAC probes the BTB about every 4 bytes of each fetch
target. A 1M-way fully associative configuration would be unusably slow,
and a large 16-way one still has 18-bit tags unless reconfigured. Nested
`unordered_map`s (space → PC → entry) are O(1), never evict and keep full
PCs.

### 2. Address spaces: per-ASID tables plus one kernel table

`tid` in `SimpleBTB`'s key is the SMT slot (always 0 here), not a process,
so today's BTB has no process separation. User code is now keyed by the
ASID the TLB uses, and kernel code (PC bit 63) goes to one shared table.
The kernel test is an OS-layout assumption: Linux on arm64, x86-64 and
RISC-V.

### 3. The ASID comes from a generic MMU hook

The user wanted no ISA-specific code in the BTB.
`BaseISA::getExecutingAsid()` exists but returns `CONTEXTIDR` on Arm, which
is a per-thread PID (and only with `CONFIG_PID_IN_CONTEXTIDR`), not the ASID.
So a new virtual `BaseMMU::currentAsid(tc)` returns `nullopt` by default.
The Arm override runs the TLB's own `CachedState::updateMiscReg` on a
*local* copy, which leaves MMU state and statistics untouched and inherits
the 16-bit ASID fix (`have_large_asid_64`). The O3 CPU hands each thread
context to the BTB through `BPredUnit::setThreadContext`.

### 4. KPTI: ignore ASID bit 0

The guest runs KPTI (task-tracing guide §5.2: EL0 restores land on
`tramp_pg_dir`). Each process uses an ASID pair, so the Garfield core sets
`ignoreAsidLsb = True`. The default is `False` because without KPTI it
would merge two processes. The first runs confirm it: `addressSpaces = 2`
(kernel plus OpenCode) in a short gin window.

### 5. In decoupled mode `btb.misses` is always 0; use `mispredictDueToBTBMiss`

Found while validating. BAC calls `lookup` only after `valid` succeeded, so
in decoupled mode `btb.lookups` equals hits and `btb.misses` is 0, for every
BTB. Missed branches surface at predecode as not-taken placeholders.
`branchPred.mispredictDueToBTBMiss_0` (the placeholder was wrong) and
`branchPred.BTBMispredicted` do count them. So do `bac.noHistByType`'s
always-taken types, which include wrong-path fetches.

An earlier version of this entry claimed that all three `branchPred` stats
were 0 and that every BTB metric was broken. That was wrong: it was
generalized from the first two of the 2,000 blocks of the 2026-10-13 redis
run, which happened to be 0. Summed over the run, redis has 667K
BTB-miss mispredicts, and the 2026-10-14 sweep plots them for every task
(e.g. fmt-3901: 1.12 PKI).

**Consequence:** the sweep's `btb_mispred_pki` and `trace_analysis.py`'s
`btb_mpki` (both from `mispredictDueToBTBMiss`) are correct. Only
`window_view.py`'s "BTB misses" row (`btb_mpki`, from `btb.misses`) reads 0
on decoupled-mode runs. In the `--disable-fdp` sweep it is meaningful
(fmt-3901: 42.4M misses over 400M instructions). Not changed yet; left for
the user to decide.

### 6. Table sizes are live values

The first run showed `addressSpaces = 0` in every block: the spaces were
created during warm-up and the counter was reset. `entries` and
`addressSpaces` are now `statistics::Value`s bound to the table size, which
a stats reset does not touch.

## Validation

### 2026-10-16 — gin-2121, 10M warm-up + 40M measured, baseline vs. infinite

`run_scripts/btb/infinite-btb-compare.sh gin-2121 1000000 10000000 40000000 10000000`

| | Baseline | InfiniteBTB |
|---|---|---|
| IPC (40M) | 1.008 | **1.044 (+3.6%)** |
| `mispredictDueToBTBMiss` | 61.5K (1.54 PKI) | **12.1K (0.30 PKI), −80%** |
| `BTBMispredicted` | 106K | 21.6K |
| Undetected unconditional branches | 171K (4.3 PKI) | **57K (1.4 PKI), −67%** |
| — `CallDirect` / `DirectUncond` / `Return` | 66K / 72K / 19K | 16K / 36K / 3K |
| Undetected `DirectCond` | 3.87M | 3.16M |
| `newEntries` per 10M block | — | 7.8K / 2.0K / 7.9K / 3.9K |
| `noAsidEntries` / `staleEncodings` / `staleTargets` | — | 0 / 0 / 7 |

- Removing BTB capacity, conflict and aliasing misses gives this OpenCode
  window **+3.6% IPC**. That is the ceiling for a larger or better BTB. The
  compulsory part, which an oracle could still remove, is not included.
- Unconditional misses that remain (57K) exceed the compulsory inserts
  (21.5K). `noHistByType` counts every fetched occurrence, wrong path
  included, until the branch first resolves.
- No JIT rewrites were detected in this window. The 7 `staleTargets`
  (same encoding, different direct target) are unexplained and negligible.
- Per-block IPC moves both ways between runs. In full-system mode the two
  runs do not execute identical streams per block, so compare whole
  windows and several tasks.

Short stats check (`infinite-statscheck/`, 2M + 2M): `entries` about 11.5K
after about 4M O3 instructions, `addressSpaces = 2`.

### 2026-10-16 — sanity check: BTB inserts vs. unique taken branches

gin-2121, `--disable-fdp --infinite-btb`, no warm-up, 2M O3 instructions,
with the commit trace and the BTB insert log (scripts kept outside the
repository; output in `runs/btb/20261016-sanity2-gin-2121/`). The
expectation was "inserts = unique taken branches".

- 8,743 unique taken PCs committed; `newEntries` = 12,622.
- 8,739 of the 8,743 were inserted. The other 4 jump to PC+4 (kernel
  Spectre-BHB loop `b`, two user `br`): falling through is correct for
  them, so they never mispredict and never get inserted.
- The 3,883 extra inserts are all wrong-path: 3,645 PCs never committed,
  and 238 committed only as not-taken.
- So `newEntries` = compulsory misses + wrong-path inserts (31% here).
  The design doc's description of the stat was corrected.
- Adding `--debug-flags=BTB` left `newEntries` identical (deterministic).

### 2026-10-16 — second sanity check: axios-5892, 20M instructions, 7 address spaces

Same setup, after a 160M atomic settle, with `--task-trace`
(`runs/btb/20261016-sanity-axios-5892/`). The `Exec`+`BTB` trace is 1.8 GB
compressed.

- 33,954 of 33,970 unique taken PCs were inserted. `newEntries` is 45,585;
  the surplus is again all wrong-path (10,915 never committed, 716
  committed only not-taken).
- `addressSpaces = 7`, matching exactly the 6 user processes the task
  tracer saw running (no exec in the window) plus the kernel. No PC is in
  two spaces, and no entry is in the wrong kernel/user space.
- Of the 16 taken-but-not-inserted PCs, 12 were inspected: 8 are `br`/`b`
  to PC+4, and 4 are conditional branches that never jumped, counted as
  taken because an interrupt followed them (next committed PC = exception
  vector). Both are explained; neither is a BTB fault.
- `CONTEXTIDR` (`ExecAsid`) is 0 throughout: the guest kernel is built
  without `CONFIG_PID_IN_CONTEXTIDR`, which confirms that
  `getExecutingAsid()` would have been useless here.
- The measured IPC of this window is 0.117, versus about 1 for gin. Not
  investigated; likely idle time (WFI) in a docker-heavy stretch.

### 2026-10-16 — whole sweep window: fmt-3901, 400M instructions

`ONLY=fmt-3901 run_scripts/tasktrace/sweep.sh`, with and without
`EXTRA=--infinite-btb`, then `sweep_compare.py`
(`runs/sweep/20261016-155307-fmt-{baseline,infbtb}/`).

- **Baseline re-run is bit-identical** to the 2026-10-14 sweep, apart from
  host-time stats: the BTB plumbing does not perturb the default BTB.
- InfiniteBTB: **IPC +3.0%** (1.049 → 1.080), BTB-miss mispredicts −83.5%
  (1.12 → 0.19 PKI), all branch mispredicts −13.7%, L1I MPKI −33%, iTLB
  MPKI −32%, L2 MPKI −17%.
- Footprint: 20K entries after warm-up, 150K at the end (130K new in the
  window), about 12× the baseline BTB. No stale entries, no ASID-less
  entries, 4–11 address spaces.
- The I-side cache and TLB gains are presumably less wrong-path fetch and
  prefetch past undetected taken branches. Not verified.

**Bug found and fixed: `SimpleBTB` evictions still read 0.**
`AssociativeCache::findVictim` invalidates the victim before returning it,
so the first fix's `victim->isValid()` check was always false. The set is
now inspected before `findVictim`. Verified on a short gin window
(`runs/btb/20261016-evictcheck-gin-2121/`): evictions on about 28% of BTB
updates. The two fmt-3901 runs above predate this fix, so their eviction
stat reads 0. It is a statistic only; timing is unaffected.

### 2026-10-19 — the full sweeps were killed by memory exhaustion

The three full sweeps (`runs/sweep/20261016-172546-{infbtb,inftlb,infbtb-inftlb}`)
stopped at 30/29/30 of 53 runs, killed by systemd-oomd (Fri 21:20, and
twice on 2026-10-19). Cause: the three sweeps restored the same heavy
checkpoints at once (docusaurus-9897 and nushell-13831 need about 10 GB
each). Not a bug in the BTB or TLB, which add about 0.2 GB per run. Fixed
by `run_scripts/tasktrace/smart_sweep.sh`, which gates launches on free
memory; see decision 21 in the tracer log. No finished run was affected;
interrupted runs restart from scratch on resume.

### 2026-10-19 — full sweeps: FDP, no-FDP, infinite BTB, infinite L2 TLB, both

All 53 checkpoints of each configuration (SPEC: 200M instructions,
agentic: 400M, both after 20M of warm-up), compared checkpoint by
checkpoint against the FDP baseline of 2026-10-14 with
`sweep_compare.py` (five sweeps): `runs/sweep/20261019-compare-5way/`
(`compare_multi.html`, `violins_multi*.png`). The three new sweeps ran
with `smart_sweep.sh` after the OOM kills (tracer log, decision 21). All
53/53 completed, with no failures.

Median change against FDP (agentic n=27 / SPEC n=26):

| | no-FDP | inf-BTB | inf-TLB | inf-BTB+TLB |
|---|---|---|---|---|
| **IPC, agentic** | −2.8% | **+3.1%** | **+3.1%** | **+6.4%** |
| IPC, SPEC | −0.2% | +0.1% | +0.0% | +0.1% |
| Fetch rate, agentic | −3.7% | +1.7% | +3.4% | +5.8% |
| BTB-miss mispredicts, agentic | +6.6% | −74.9% | +0.2% | −75.0% |
| All branch mispredicts, agentic | +1.5% | −13.0% | −0.2% | −13.2% |
| L1I MPKI, agentic | +132% | −33.5% | +0.3% | −36.6% |
| iTLB MPKI, agentic | −92.4% | −25.4% | −26.7% | −40.3% |
| Walk requests (`walks_pki`), agentic | −2.9% | −4.7% | −44.0% | −47.7% |
| L2 MPKI, agentic | −22.9% | −16.3% | −1.5% | −17.6% |

- **Agentic workloads gain; SPEC does not.** With both limits every agentic
  task gains (+0.3% to +13.2%; IQR +4.8% to +9.9%), while the SPEC median
  moves by 0.1%. The BTB and TLB gains add up (3.1% + 3.1% ≈ 6.4%), so
  they address independent bottlenecks.
- **The BTB part:** BTB-miss mispredicts −75%, all branch mispredicts
  −13%, and as a side effect L1I −34% and L2 −16%. That fits less fetch
  and prefetch down fall-through paths past undetected taken branches
  (not verified). Largest gains: nushell +5.5%, prometheus +5.1%, jq
  +4.8%; carbon −0.9%.
- **The TLB part:** completed page walks (`requestOrigin_Completed`, not
  `walks_pki`) drop from a median 0.62 to 0.15 per 1K instructions (−76%);
  what remains is first touches. iTLB MPKI also falls 27%, because more FDP
  prefetch translations now hit instead of being dropped. The fetch rate
  rises 3.4%. Largest gains: nushell +7.7%, prometheus +7.6%, redis +6.7%;
  smallest preact +0.3%.
- **Combined, top:** redis +13.2%, rubocop +11.9%, framework +11.6%.
- **SPEC outliers** are the large-code benchmarks: gcc +10.3% with both
  (+5.9% BTB, +3.6% TLB), vpr +4.2%, ns3 +3.6%, llvm +2.4% (BTB).
  **714.cpython_r loses 3.4% with the infinite BTB**; not investigated yet.
- FDP is worth +2.8% on agentic (no-FDP −2.8%). Without it, iTLB MPKI falls
  92% because the dropped prefetch translations disappear (tracer log,
  decision 20).

Memory: nushell-13831's run peaks at 22.2 GB, docusaurus at about 11 GB,
the rest at 2.5–6 GB (`runs/sweep/mem_peaks.tsv`).

### 2026-10-20 — the same sweeps, with the first 100M of each window skipped

The first 20M of the window showed the unbounded structures still filling:
infinite-BTB IPC 4% lower than in the rest of the window, with 1.5× the new
entries, and infinite-TLB completed walks falling from 0.20 to 0.10 per 1000
instructions per 100M quarter. The baseline structures showed no such
effect. To measure with warmer structures without re-simulating, the five
sweeps were re-summarised with the first 100M instructions of each window
skipped: 120M of effective O3 warm-up and 300M measured for agentic (SPEC:
100M of its 200M). The output is in a separate folder,
`runs/sweep/20261020-skip100M/{FDP,no-FDP,inf-BTB,inf-TLB,inf-BTB+TLB}/`
and `compare-5way/`. The originals are unchanged.

Median change against FDP, agentic (full window → skip 100M):

| | no-FDP | inf-BTB | inf-TLB | inf-BTB+TLB |
|---|---|---|---|---|
| IPC | −2.8 → −2.9% | +3.1 → +3.0% | +3.1 → +3.3% | **+6.4 → +7.5%** |
| Fetch rate | −3.7 → −3.8% | +1.7 → +1.9% | +3.4 → +3.5% | +5.8 → +6.4% |
| BTB-miss mispredicts | +6.6 → +6.5% | −74.9 → −76.6% | 0 | −75.0 → −78.0% |
| All branch mispredicts | +1.5 → +1.2% | −13.0 → −13.6% | 0 | −13.2 → −15.5% |
| Completed walks | 0 | 0 → +1% | −79.3 → −81.5% | −78.6 → −80.2% |
| L2 MPKI | −22.9% | −16.3 → −17.4% | −1.5 → −1.0% | −17.6 → −19.2% |

- **The single limits barely move** (BTB +3.0%, TLB +3.3%). Their 20M
  warm-up already gave most of their steady-state benefit.
- **The combination grows: +6.4% → +7.5%** (IQR +4.8% to +9.4%, max
  +15.4%), now more than the sum of the two single limits (6.3%).
- The baseline itself changes little (IPC 0.991 → 0.997, completed walks
  0.63 → 0.59), so 20M of warm-up is enough for the real structures.
- **SPEC:** still about +0.1%. Its skip leaves only the second half of each
  SimPoint region, so its absolute values move (baseline IPC 1.52 → 1.56)
  for reasons of region, not warmth.
- **Conclusion for future sweeps:** a longer O3 warm-up mainly matters when
  both limits are combined. With ~100M more warm-up the combined gain grows
  by about 1 point; the single-limit gains are stable.

## Next

- Investigate 714.cpython_r's −3.4% with the infinite BTB.
- Run more tasks to see how the
  ceiling varies across the workload set.
- Decide on `window_view.py`'s `btb_mpki` row (decision 5).
- Pass-1/pass-2 oracle to remove the compulsory misses.
