# InfiniteBTB: an unbounded, ASID-separated BTB for limit studies

`InfiniteBTB` replaces the core's BTB with one that never evicts, never
aliases and keeps each address space apart. It answers the question *how
much performance do BTB misses cost?* The only misses left are the first
taken occurrence of each branch (compulsory misses). The next step is a
pass-1/pass-2 oracle that also removes those (see [Future work](#future-work)).

Enable it on the Neoverse V2 core with `--infinite-btb` (any Garfield driver
that calls `sim_opts.apply_core_knobs`: `virt_run.py`, `fs_run.py`,
`se_run.py`).

## 1. Why the BTB matters in this core

The Neoverse V2 config runs gem5's **decoupled front-end**
(`decoupledFrontEnd = True`, `requiresBTBHit = True`,
`configs/garfield/arm/neoverse_v2.py`). There the BAC stage
(`src/cpu/o3/bac.cc`) runs ahead of fetch and has no instruction bytes yet.
To find branches it walks addresses in `minInstSize` steps and asks the BTB
whether a branch exists there (`bpu->BTBValid`, `bac.cc:647`). On a hit it
takes the branch's `StaticInst` from the BTB (`BTBGetInst`, `bac.cc:677`)
and makes the prediction. **A branch that misses in the BTB is not detected
at all**: the fetch target runs past it, and the mistake surfaces later at
decode or execute. So the BTB here does two jobs: branch *detection* and
*target* supply. `InfiniteBTB` makes both perfect for every branch that has
already been taken once.

The BTB still holds only branches that were taken at least once: the branch
predictor installs entries only for taken branches (`updateBTB`, called from
`bpred_unit.cc:397` at commit or `:581` at squash). A never-taken
conditional branch stays out of the BTB. BAC then falls through it, which
is the correct prediction, so this costs nothing.

## 2. How it works

### 2.1 Storage (`src/cpu/pred/infinite_btb.hh`)

```
tables : unordered_map<Space, Table>     // one table per address space
Table  : unordered_map<Addr, Entry>      // keyed by the full branch PC
Entry  : { target PCState, StaticInstPtr }
```

- **No capacity, no sets, no replacement, no tag truncation.** Lookup is two
  hash probes, O(1). Compare `SimpleBTB`: a set-associative
  `AssociativeCache` with a linear scan of the ways and tags cut to
  `tagBits` (18 in the Neoverse V2 config), where aliasing gives false hits.
- **One table per address space** (`tables`, `infinite_btb.hh`, `using
  Table`). This matches the "partition by ASID" design: each process gets
  exactly the entries it uses, and kernel code has its own shared table.
  Nested maps also make it cheap to drop one ASID later (ASID-rollover
  hook, future work).
- **`tid` is not part of the key.** Hardware threads that share an address
  space share entries, as in a real shared BTB. (`tid` is the SMT slot,
  always 0 on this single-threaded core, not a process ID.)

### 2.2 Which address space a PC belongs to (`spaceOf`, `infinite_btb.cc:72`)

1. **Kernel code → `KernelSpace`** if bit 63 of the PC is set
   (`infinite_btb.cc:77`). Kernel code is mapped identically in every
   process (global pages), so one shared table avoids repeating its cold
   misses per process.
2. **User code → its ASID**, read through the MMU (`readUserSpace`,
   `infinite_btb.cc:58`), with bit 0 dropped when `ignoreAsidLsb` is set
   (KPTI, §3).
3. **User code without an ASID → `NoAsidSpace`**: plain VA tagging. This
   happens when the CPU model never gave the BTB a thread context, or the
   ISA does not implement `currentAsid()`.

The two reserved values (`KernelSpace = ~0`, `NoAsidSpace = ~1`,
`infinite_btb.hh:57,61`) cannot collide with a real ASID (at most 16 bits).

**Space cache.** BAC probes the BTB about once per 4 bytes of every fetch
target, so `spaceOf` reads the ASID at most **once per tick per thread**
(`SpaceCache`, `infinite_btb.cc:81`). The ASID only changes when a
`TTBR`/`TCR` write commits, so this loses nothing beyond the one-cycle lag
discussed in §3.

### 2.3 Getting the ASID without ISA code in the BTB

The BTB stays ISA-neutral. Two small generic hooks carry the state:

- **`BaseMMU::currentAsid(tc)`** (`src/arch/generic/mmu.hh:140`): "the ASID
  this MMU would use to translate the current context's addresses", or
  `nullopt`. The default returns `nullopt`.
- **Arm override** (`src/arch/arm/mmu.cc:382`): builds a *local*
  `CachedState` and calls its `updateMiscReg`. That is the same code the
  TLB uses: `TTBR0/1_EL1` per `TCR_EL1.A1`, 8 or 16 bits per `TCR_EL1.AS`
  and `haveLargeAsid64`, plus the VHE and AArch32 paths. A local copy is
  used so the MMU's own `s1State` cache is untouched and no MMU statistic
  changes. The EL2/EL3 regimes have no ASID, so it returns `nullopt` there.
  Because it reuses the TLB's computation, the BTB inherits
  `have_large_asid_64 = True` from `virt_run.py` (the 16-bit ASID fix).
- **Thread context plumbing.** The BTB needs a `ThreadContext` per hardware
  thread:
  - `BranchTargetBuffer::setThreadContext` (`src/cpu/pred/btb.hh:73`) is a
    no-op by default;
  - `BPredUnit::setThreadContext` forwards to it (`bpred_unit.hh:138`);
  - the O3 CPU calls it when it creates each thread context
    (`src/cpu/o3/cpu.cc:321`).

  Other CPU models do not call it yet. `InfiniteBTB::init` then warns, and
  user code falls back to `NoAsidSpace`.

`BaseISA::getExecutingAsid()` was **not** used: on Arm it returns
`CONTEXTIDR`. arm64 Linux writes the thread's PID there, and only with
`CONFIG_PID_IN_CONTEXTIDR`; otherwise it is 0. Either way it is not the
ASID the TLB uses. Its only user is the `ExecAsid` trace flag
(`src/cpu/exetrace.cc:71`).

### 2.4 Interface (`infinite_btb.cc`)

| Method | Behaviour |
|---|---|
| `valid` (`:100`) | Entry exists? Used by BAC's branch search. No statistics. |
| `lookup` (`:106`) | Target, or `nullptr`. Counts `lookups` / `misses` per branch type (base-class stats). |
| `getInst` (`:120`) | Stored `StaticInst`, used by BAC to predict a branch it has not fetched yet. |
| `update` (`:127`) | Insert or overwrite target and instruction; counts `updates` and the extra statistics below. |
| `memInvalidate` (`:51`) | Clears everything. gem5 calls it only when switching to a KVM CPU (`atomic_noncaching` mode, `src/python/m5/simulate.py:500`), not on the atomic → O3 switch. |

### 2.5 Statistics (`system.…branchPred.btb.*`)

Base-class: `lookups`, `misses`, `updates`, `mispredict` (per branch type).
`InfiniteBTB` adds:

| Stat | Meaning |
|---|---|
| `newEntries` | Branches inserted for the first time: the compulsory misses, **plus wrong-path inserts**. With `updateBTBAtSquash=True` a branch is inserted when it resolves taken and mispredicted, even if an older mispredict later squashes it. In the 2026-10-16 sanity check (§5) 31% of inserts were wrong-path. |
| `kernelEntries` / `userEntries` | Split of `newEntries` by space. `userEntries` includes `noAsidEntries`. |
| `noAsidEntries` | User entries inserted without an ASID. Should be 0 on the O3 core with Arm; non-zero means VA-only tagging is in use. |
| `entries` | *Current* number of entries over all spaces (a live value, see below). |
| `addressSpaces` | *Current* number of address spaces: ASIDs plus the kernel (a live value). |
| `staleEncodings` | An update found a *different instruction encoding* at the same (space, PC): code was rewritten (JIT), or an ASID was reused. Compared via `StaticInst::getEMI()` (Arm: `machInst`; ISAs without it return 0, so they never count). |
| `staleTargets` | An update changed the stored target of a *direct* branch. A direct target is fixed by the encoding, so this also means a stale entry. |

**Counters vs. live values.** `virt_run.py` resets statistics after warm-up
and at every `--stats-interval-insts` block, but the table survives. The
counters (`newEntries`, `*Entries`, `stale*`) therefore count events in the
block: `newEntries` means *branches first seen in this block*. `entries` and
`addressSpaces` are `statistics::Value`s bound to the table size, so a reset
does not touch them and each dump shows the size at that point.

**Measuring BTB misses in decoupled mode.** BAC calls `lookup` only after
`valid` has found the branch, so in decoupled mode **`btb.lookups` equals
hits and `btb.misses` stays 0**, for `SimpleBTB` too. A branch the BTB
missed never reaches `lookup`. Fetch meets it at predecode with no
prediction history, and BAC creates a not-taken placeholder
(`bac.cc:858`). Three stats do see these misses:

- **`branchPred.mispredictDueToBTBMiss_0`**: mispredictions caused by a
  BTB miss, i.e. the placeholder's "not taken" was wrong. This is the
  cost-relevant metric. It is what `btb_mispred_pki` in the sweep summary
  and `btb_mpki` in `trace_analysis.py` use.
- **`branchPred.BTBMispredicted`**: taken branches that missed the BTB, at
  BTB update time.
- **`bac.noHistByType`**: every *fetched* branch without a prediction, per
  branch type. It is dominated by `DirectCond` (not yet taken, so the
  not-taken placeholder is usually right), and it counts wrong-path and
  repeated fetches. A new branch can be fetched several times before it
  resolves and is inserted, so this can exceed `newEntries`. Its
  unconditional types (always taken) are a fetch-side view of the costly
  misses.

In coupled mode (`--disable-fdp`), `lookup` sees every branch and
`btb.misses` is meaningful.

### 2.6 Configuration

- `src/cpu/pred/BranchPredictor.py:148`: `InfiniteBTB(BranchTargetBuffer)`,
  one parameter `ignoreAsidLsb` (default `False`).
- `configs/garfield/arm/neoverse_v2.py:288`: `NeoverseV2_InfiniteBTB` sets
  `ignoreAsidLsb = True` for the KPTI guest.
- `configs/garfield/arm/sim_opts.py`: `--infinite-btb` swaps
  `cpu.branchPred.btb` in `apply_core_knobs` (`:427`). The machine banner
  shows `BTB=infinite`.

## 3. Assumptions and decisions

| # | Decision / assumption | Why | Consequence / check |
|---|---|---|---|
| 1 | Hash maps, not a huge `SimpleBTB` | `AssociativeCache` scans every way and copies the set's pointer vector on each lookup. 1M fully associative ways would make every BAC probe scan 1M entries. | O(1), truly unbounded. Memory grows with the branch footprint: 150K entries after 400M instructions of fmt-3901, on the order of tens of MB. |
| 2 | Kernel = PC bit 63 set | Decided per address, so no lag when BAC predicts across a syscall or `eret`. Needs no ISA code. | An **OS-layout assumption**: true for Linux on arm64, x86-64 and RISC-V. An OS that puts kernel code in the lower half would mix kernel code into user spaces. |
| 3 | ASID from `BaseMMU::currentAsid`, Arm override reuses `CachedState::updateMiscReg` | Keeps the BTB ISA-neutral and makes it agree with the TLB, including the 16-bit ASID setting. | About 15 lines of Arm code in `src/arch/arm/`. Other ISAs fall back to VA-only until they override it. |
| 4 | `ignoreAsidLsb = True` on the Garfield core | The guest runs KPTI: the restored state at EL0 has `TTBR1_EL1` on `tramp_pg_dir` (task-tracing guide §5.2). arm64 Linux then gives each process an ASID pair, with user = kernel ASID \| 1 (`USER_ASID_FLAG`). User code predicted while the committed state is still EL1 would otherwise read the even half. | Wrong without KPTI: it would merge two processes. That is why the default is `False`. Check: `addressSpaces` should be about one per live process. |
//IMPORTANT:
| 5 | ASID read from the *committed* state, cached per tick | The thread context exposes committed architectural state. BAC runs ahead of commit. | For a few cycles after a context switch (`TTBR` write), BAC may probe with the previous ASID. Real hardware has a similar window. |
| 6 | `tid` not in the key | Address spaces, not SMT slots, decide sharing. | On an SMT core, threads of one process share entries. |
| 7 | No ASID-rollover handling | 16-bit ASIDs (about 32K processes with KPTI pairs) are unlikely to roll over within a simulated window. | After a rollover a reused ASID would see the old process's entries. `staleEncodings` / `staleTargets` would show it. Future: drop user tables on `TLBI VMALLE1`/`ASIDE1`. |
| 8 | No JIT-specific handling | Measure first. | JIT rewrites (Bun/JSC in OpenCode) appear as `staleEncodings`. A stale entry just mispredicts and is corrected, as on real hardware. |
| 9 | Phantom branches are not counted separately | With full PCs and ASIDs, a hit at a non-branch needs rewritten code or ASID reuse, which the stale stats already cover. | If `staleEncodings` is large, add a dedicated counter in fetch. |
| 10 | No BTB latency or bandwidth model | Same as `SimpleBTB`, which has none either. | A *limit* on BTB capacity and aliasing only, not a realistic large-BTB design. |
| 11 | Coupled front-end works too | With `--disable-fdp` the BPU still calls `lookup`/`update`. Only detection-by-BTB is specific to the decoupled mode. | `--infinite-btb --disable-fdp` is valid. |

## 4. Related change: `SimpleBTB` evictions

`SimpleBTB`'s `evictions` statistic was declared (`btb.cc:68`) but never
incremented. `SimpleBTB::update` (`simple_btb.cc:121-137`) now counts an
eviction when the chosen victim held a *different* branch. The check has to
look at the set **before** calling `findVictim()`, because
`AssociativeCache::findVictim` invalidates the victim it returns
(`src/base/cache/associative_cache.hh:249`). The first version tested
`victim->isValid()` afterwards, which is always false, so it always
counted 0. That was noticed on the 400M fmt-3901 window, whose footprint is
far beyond 12K entries. After the fix, a short gin window evicts on about
28% of BTB updates. This makes a large set-associative `SimpleBTB`
checkable: zero evictions means it behaved as infinite.

Observation, not changed: `SimpleBTB::update` always allocates a victim, even
when the branch is already present in another way of the set. A target
update can therefore leave a duplicate entry. Changing it would alter
baseline results, so it is left as is.

## 5. Validation

Compare it like any other configuration change: a sweep with
`EXTRA="--infinite-btb"` and `BASELINE=<baseline sweep>` (`smart_sweep.sh`,
task-tracing guide 8.3), or, for one window, `o3-window.sh` twice with the
same arguments, the second with `--infinite-btb` appended. The first run
below used a dedicated wrapper (`run_scripts/btb/infinite-btb-compare.sh`,
since removed) that did the latter into
`runs/btb/<stamp>-<task>/{baseline,infinite}/`.

**First run (2026-10-16):** gin-2121 (OpenCode on Bun), 1M settle, 10M
O3 warm-up, 40M measured instructions in four 10M blocks
(`runs/btb/20261016-144224-gin-2121/`).

| | Baseline (12K-entry, 6-way, 18-bit tags) | InfiniteBTB |
|---|---|---|
| IPC (whole window) | 1.008 | **1.044 (+3.6%)** |
| `mispredictDueToBTBMiss` (total) | 61.5K (1.54 PKI) | **12.1K (0.30 PKI), −80%** |
| `BTBMispredicted` (total) | 106K | 21.6K |
| Undetected unconditional branches (`noHistByType`, all non-`DirectCond` types) | 171K (4.3 PKI) | **57K (1.4 PKI), −67%** |
| — of which `CallDirect` / `DirectUncond` / `Return` | 66K / 72K / 19K | 16K / 36K / 3K |
| Undetected `DirectCond` | 3.87M | 3.16M |
| `newEntries` (compulsory, per 10M block) | — | 7.8K, 2.0K, 7.9K, 3.9K |
| `noAsidEntries` | — | 0 |
| `staleTargets` / `staleEncodings` (total) | — | 7 / 0 |

Reading:

- The ASID path works: `noAsidEntries = 0`, and kernel and user entries are
  split.
- No JIT rewrites were caught in this window (`staleEncodings = 0`). The 7
  `staleTargets`, a direct target change with the same encoding at the same
  PC, are unexplained but negligible. Use `--debug-flags=BTB` to investigate.
- The remaining unconditional misses (57K) exceed `newEntries` (21.5K):
  repeated fetches of not-yet-inserted branches, as explained in §2.5.
- Per-block IPC differs in both directions between the runs. The two runs
  share instruction counts but not timing, so in full-system mode they do
  not execute identical streams per block (interrupt and scheduling
  timing). Compare whole windows, or several tasks, rather than single
  blocks.

**Sanity check (2026-10-16): inserts vs. the commit trace.** gin-2121,
coupled front-end (`--disable-fdp`), no warm-up (the BTB starts empty when
measurement starts), 2M O3 instructions, with `--debug-flags=Exec…,BTB`. The
run and analysis scripts were kept outside the repository. Taken branches
were taken from the commit trace: unconditional branches always, and
conditional ones when the next committed PC is not PC+4. Results:

| | Count |
|---|---|
| Unique taken branch PCs in the commit trace | 8,743 (902 kernel, 7,841 user) |
| `newEntries` | 12,622 |
| …committed-taken PCs that were inserted | **8,739 of 8,743** |
| …inserted PCs that never committed (wrong path) | 3,645 |
| …inserted PCs that committed only not-taken (taken on a wrong path) | 238 |
| Committed-taken PCs never inserted | 4 |

The 4 never-inserted branches all target PC+4: two kernel `b` in the
Spectre-BHB clearing loop and two user `br`. A BTB miss falls through to
PC+4, which is the correct target, so they never mispredict and are never
inserted. This is correct behaviour. So: every taken branch is learned
exactly once, `addressSpaces = 2`, no stale entries, and the surplus is
fully explained by wrong-path inserts. `btb.misses` (257K over 806K
lookups) is a count of dynamic events, as expected, dominated by
not-yet-taken conditional branches.

**Second sanity check: a larger window with several processes.** axios-5892,
160M atomic instructions to settle, then 20M O3 instructions with the same
setup as the first check, plus `--task-trace`.

| | Count |
|---|---|
| Unique taken branch PCs in the commit trace | 33,970 (8,519 kernel, 25,451 user) |
| `newEntries` | 45,585 (10,906 kernel, 34,679 user) |
| …committed-taken PCs that were inserted | **33,954 of 33,970** |
| …inserted PCs that never committed / committed only not-taken | 10,915 / 716 |
| Entries in the wrong kernel/user space | 0 |
| `addressSpaces` vs. user processes the task tracer saw running | **7 = 6 + kernel** |

- **ASIDs:** six user processes ran in the window (`opencode`, `dockerd`,
  `docker`, `python3`, two `python`), with no exec, and the BTB built
  exactly 6 user spaces plus the kernel. No PC appears in two spaces.
  Without `ignoreAsidLsb`, the KPTI pairs would have given about 13.
  `ExecAsid` prints `CONTEXTIDR`, which is 0 throughout: the guest kernel
  lacks `CONFIG_PID_IN_CONTEXTIDR`. The trace therefore cannot attribute
  instructions to processes, and the tracer's process count is the
  reference.
- **The 16 taken-but-not-inserted branches:** 12 were inspected. 8 are `br`
  or `b` to PC+4, the same harmless case as before. 4 are conditional
  branches that always fell through. The analysis counted them as taken
  because an interrupt arrived right after them, so the next committed
  instruction was the exception vector (`0xfffffbfffddf6400`). That is an
  artifact of the trace heuristic, not a BTB miss.

**Whole sweep window: fmt-3901** (the 2026-10-14 sweep setup: 1-instruction
settle, 20M O3 warm-up, 400M measured instructions in 200K blocks,
decoupled front-end), run with `sweep.sh ONLY=fmt-3901`, with and without
`--infinite-btb`, and compared with `sweep_compare.py`
(`runs/sweep/20261016-155307-fmt-{baseline,infbtb}/`). The re-run baseline
is bit-identical to the 2026-10-14 sweep, apart from host-time stats, so
these changes leave the default BTB's results unchanged.

| Metric | Baseline | InfiniteBTB | Change |
|---|---|---|---|
| IPC | 1.049 | 1.080 | **+3.0%** |
| BTB-miss mispredicts (`btb_mispred_pki`) | 1.122 | 0.186 | **−83.5%** |
| All branch mispredicts (`br_mpki`) | 5.204 | 4.493 | −13.7% |
| L1I MPKI | 2.007 | 1.339 | −33.3% |
| iTLB MPKI | 39.6 | 27.0 | −31.8% |
| L2 MPKI | 6.617 | 5.481 | −17.2% |
| Page walks PKI | 2.638 | 2.411 | −8.6% |
| Fetch rate (insts/cycle) | 1.501 | 1.530 | +1.9% |

- The footprint is large: the `InfiniteBTB` holds 20K entries after
  warm-up and 150K at the end. `newEntries` totals 130K over the window,
  about 12× the 12K-entry baseline BTB.
- `staleTargets = staleEncodings = noAsidEntries = 0` over 400M
  instructions. `addressSpaces` reaches 4–11.
- **The front-end memory side improves too.** L1I and iTLB misses drop by
  a third. A plausible explanation, not verified: an undetected taken
  branch makes fetch, and the FTQ-driven FDP prefetcher, run down the
  fall-through path, touching I-cache lines and pages that are not needed.
  Fewer BTB misses mean less of that pollution.
- The tracer's switch rates differ slightly between the two runs. The
  extra speed changes when interrupts land, so the runs do not execute
  identical instruction streams.

Results and follow-ups are logged in
`docs/research-log/agentic/2026-10-16-infinite-btb.md`.

## Future work

- **Pass-1/pass-2 oracle**: dump `(space, PC, encoding)` of every branch in
  a run, then preload it in a second run so even compulsory misses
  disappear. The set does not depend on timing; let pass 1 run past the
  window and keep this BTB's learning as a fallback.
- **ASID-rollover hook** (decision 7) and **IC IVAU / TLBI-by-VA
  invalidation** if the stale stats call for them.
- **Other CPU models**: call `setThreadContext` from Minor and the simple
  CPUs; implement `currentAsid` for RISC-V (`satp.ASID`) and x86 (PCID).
