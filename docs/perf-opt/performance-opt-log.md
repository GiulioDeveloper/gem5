# gem5 simulation-speed optimization log

This log records every optimization trial of the perf-opt campaign, whether it was
accepted or rejected. Negative results are kept as carefully as positive ones: they
tell the next person what not to try again. The design is in
`docs/superpowers/specs/2026-09-26-perf-opt-design.md`.

## Preamble

### Starting point
- **Branch:** `feat/opt`, cut from `rbdev` at `8d0dafc8154f039cffa0924fc0e25a9fdabb39ba`
  ("arm: restore QEMU-virt checkpoints with 16-bit ASIDs").
- **Simulator code:** every trial builds the same simulator sources. Only build flags,
  libraries and link steps change, so any stats difference is a real defect of the lever.

### Host and toolchain
- **Host:** AMD Ryzen AI MAX+ 395 (Zen 5, 16 cores / 32 threads, up to 5.19 GHz,
  2×32 MB L3), 60 GiB RAM, Ubuntu 24.04, kernel 7.0.0. Clocks and SMT are left at their
  defaults; the machine is otherwise lightly loaded.
- **Compiler:** g++-12 12.4.0 (`CC=gcc-12 CXX=g++-12`). The same major version is used
  on the kratos2 cluster, so results and recipes carry over.
- **Python and SCons:** system Python 3.12 (`python3-dev`) and SCons 4.5.2, with conda
  kept off PATH. Every binary links the system `libstdc++` and `libpython3.12`.
- **Build configuration:** every build dir is configured from `build_opts/ARM` and has
  the same auto-detected features: Ruby with CHI, SystemC, x86 KVM, capstone. No
  protobuf, no HDF5, no PNG.
- **Harness:** `util/perf-opt/`. `build.sh` builds a configuration and records the exact
  command; `run_suite.sh` runs one trial; `stats_gate.py` checks bit-identity;
  `kips_table.py` prints each trial's table and verdict.

### Test suite
- **Test checkpoints:** five SPEC CPU 2026 SimPoint checkpoints, drawn with
  `random.Random(20260926).sample(rows, 5)` from the 190 rows of
  `gem5-infra/ckpt-tools/simpoint/manifests/checkpoints.json`:
  `708.sqlite_r.0.3`, `706.stockfish_r.2.4`, `706.stockfish_r.1.1`, `753.ns3_r.2.0`,
  `723.llvm_r.1.0`. The draw happens to include two stockfish checkpoints.
- **PGO training checkpoints:** drawn next from the remaining 185 by the same
  generator, and never used for evaluation: `748.flightdm_r.2.2`, `721.gcc_r.2.0`,
  `767.nest_r.1.0`.
- **Selection record:** `util/perf-opt/suite.json`.

### Run protocol
- **Command:** each checkpoint runs `configs/garfield/arm/fs_run.py` with 10M warmup
  and 30M detailed instructions (`--warmup-insts 10000000 --detailed-insts 30000000`,
  `--mem-size 16GiB`) on the Neoverse V2 O3 model with default knobs.
- **Pinning:** the five runs go concurrently, each pinned with `taskset` to its own
  physical core (logical CPUs 1–5; their SMT siblings 17–21 stay idle). Builds never
  overlap runs.
- **KIPS:** the region's `hostInstRate` from `stats.txt`, divided by 1000.
  `fs_run.py` dumps only the region stats.

### Gate
- **Identity:** a trial's `stats.txt` must match the baseline on every checkpoint.
  - Lines starting with `host` or `simFreq`, blank lines and separators are ignored.
  - Every other baseline line must appear verbatim.
  - New stats must be zero.
  - Stats that differ between two identical baseline runs are listed in
    `docs/perf-opt/nondeterministic-stats.txt` and excluded by name.
- **Verdict:** a lever is **accepted** if and only if stats are identical on all five
  checkpoints **and** at least three of the five are faster than the last accepted
  configuration. The ladder is cumulative.
- **Noise:** the noise figure is the run-to-run KIPS spread of the two baseline runs.
  Gains inside it are marked "within noise" but still count.
  - **Caveat (added 2026-09-27):** that figure understates the real noise. The same
    Trial 4 bfd binary, run twice, differed by 0.95%, 1.55%, 4.06%, 2.55% and 1.71% on
    the five checkpoints (see Trial 4). Changes below ~4% are therefore not reliably
    distinguishable from noise in this protocol. The "within noise" column still uses
    the baseline figure, as the plan specified.
- **Identity reference:** `baseline-a` for Trial 1. From Trial 2 on it is `trial1-fast`,
  following the user's ruling on Trial 1 (below).

## Baseline

- **Build:** `build/ARM/gem5.opt`, built in 595 s. The binary is 1126 MB, of which
  45.2 MB is `.text`. No tcmalloc.

  ```
  CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='' LINKFLAGS_EXTRA='' scons build/ARM/gem5.opt -j32 --ignore-style --without-tcmalloc
  ```

- **Two identical runs** (`baseline-a` 22:39, `baseline-b` 22:43, 2026-09-26) were
  **bit-identical on every stat of all five checkpoints**. No stat is nondeterministic
  in these windows, so `nondeterministic-stats.txt` excludes nothing.
- **Noise figure:** the run-to-run KIPS spread is **0.36–1.57%**. Neither run waited
  for a quiet machine (that guard was added in Trial 4): `baseline-a` started at a
  1-minute load average of 2.74 and `baseline-b` at 1.92. The 5- and 15-minute averages
  were higher still (12.95/16.63 and 7.74/13.78), so the load was falling at both starts.
- **Fixed cost per run:** wall time per run minus the region's `hostSeconds` is 50–105 s.
  That covers startup, resource lookup, restore and the 10M warmup. The detailed region
  is 55–108 s.

| Checkpoint | IPC | KIPS run a | KIPS run b | Baseline KIPS (mean) | Spread |
|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 2.282 | 522.9 | 521.0 | 521.9 | 0.36% |
| 706.stockfish_r.2.4 | 2.515 | 544.1 | 546.1 | 545.1 | 0.36% |
| 708.sqlite_r.0.3 | 1.808 | 379.7 | 374.4 | 377.1 | 1.41% |
| 723.llvm_r.1.0 | 1.101 | 282.7 | 278.5 | 280.6 | 1.50% |
| 753.ns3_r.2.0 | 1.259 | 308.8 | 304.0 | 306.4 | 1.57% |

## Trials

### Trial 1 — `.fast` build variant

**Summary:** building `gem5.fast` instead of `gem5.opt` speeds up every test checkpoint
by 6.4–8.6%. Every stat is identical except one assert-inflated counter (explained
below). **Accepted.**

**Key idea:** `.opt` is `-O3 -g` with `TRACING_ON=1` and asserts enabled. `.fast` is `-O3`
with `NDEBUG` and `TRACING_ON=0`. That removes every `assert`/`gem5_assert`, the per-event
`debug::Event` check, the `DPRINTF` flag tests and the NDEBUG-only O3 instruction-count
bookkeeping from the hot paths (`src/SConscript:680-682`).

**Files and flags targeted:** build variant only; no source change. Objects are `.fo`, so
the `.opt` build in the same dir is untouched.

```
CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='' LINKFLAGS_EXTRA='' scons build/ARM/gem5.fast -j32 --ignore-style --without-tcmalloc
```

Built in 319 s. The binary is 94 MB (1126 MB for `.opt`, which carries debug info), with
42.4 MB of `.text` against 45.2 MB.

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 521.9 | 560.0 | +7.30% | faster | +7.30% | 0.36% | NO |
| 706.stockfish_r.2.4 | 545.1 | 592.1 | +8.61% | faster | +8.61% | 0.36% | NO |
| 708.sqlite_r.0.3 | 377.1 | 401.5 | +6.48% | faster | +6.48% | 1.41% | NO |
| 723.llvm_r.1.0 | 280.6 | 298.6 | +6.41% | faster | +6.41% | 1.50% | NO |
| 753.ns3_r.2.0 | 306.4 | 328.2 | +7.12% | faster | +7.12% | 1.57% | NO |

**Stats difference:** exactly one stat differs on every checkpoint,
`board.processor.start.core.executeStats0.numMiscRegReads`. `.fast` counts 8 fewer reads
on the two stockfish checkpoints and 16 fewer on the other three, out of 23–34 million.
All other stats are identical, including cycles, instructions, IPC and every predictor,
cache and pipeline counter.
- **Root cause:** `src/arch/arm/interrupts.hh:217`, `assert(checkInterrupts())` in
  `Interrupts::getInterrupt()`.
  - `checkInterrupts()` reads `HCR_EL2`, then calls `takeInt64()`
    (`src/arch/arm/interrupts.cc:117-119`), which reads `CPSR`, `SCR_EL3` and `HCR_EL2`.
  - All four reads go through `o3::CPU::readMiscReg`, which increments the stat
    (`src/cpu/o3/cpu.cc:953`). Its other helpers use the uncounted `NoEffect` path.
  - So each evaluation of the assert adds 4 to the counter in `.opt` and nothing in
    `.fast`. The observed differences, 8 and 16, are exact multiples of 4 and scale with
    the number of interrupts taken in the region.
- **Why it doesn't matter:** the reads have no architectural side effect, so the
  simulation is unchanged. `.opt`'s count is inflated by debug-only code.

**Verdict: accepted, by user ruling.** Grounds: faster on 5/5 (+6.41% to +8.61%), and the
only stats difference is the assert-inflated counter above.
- **Gate rebase (ruling 2026-09-26):** from Trial 2 on, the identity reference is the
  `trial1-fast` run, not `baseline-a`. Every later lever is therefore checked for strict
  bit-identity with no exclusions.
- **Debugging:** keep `gem5.opt`, because `--debug-flags` and asserts exist only there.

### Trial 2 — tcmalloc

**Summary:** linking gperftools' `tcmalloc_minimal` in place of glibc malloc speeds up
every test checkpoint by 21.2–23.0% on top of `.fast`, with stats bit-identical.
**Accepted.**

**Key idea:** gem5 allocates and frees objects at a very high rate on its hot paths. That
includes a heap-allocated `DynInst` per fetched instruction, `Request`/`Packet` pairs
per memory access, prefetcher candidates, per-lookup candidate vectors in the
set-associative tags, and branch-predictor history records. tcmalloc's per-thread free
lists serve these small allocations far more cheaply than glibc's malloc. gem5's
SConstruct already supports it: it links `tcmalloc_minimal` when the library is present
and adds `-fno-builtin-malloc/calloc/realloc/free` (`SConstruct:710`, `854-863`). No
build before this campaign had it: this box lacked `libgoogle-perftools-dev`, and the
kratos2 compute image lacks it too.

**Files and flags targeted:** `apt install libgoogle-perftools-dev` (2.15), and a new
build dir `ARM_tcm` without `--without-tcmalloc`. No source change. `ldd` confirms
`libtcmalloc_minimal.so.4`.

```
CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='' LINKFLAGS_EXTRA='' scons build/ARM_tcm/gem5.fast -j32 --ignore-style
```

Built in 407 s.

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 560.0 | 688.9 | +23.01% | faster | +31.99% | 0.36% | yes |
| 706.stockfish_r.2.4 | 592.1 | 719.3 | +21.48% | faster | +31.95% | 0.36% | yes |
| 708.sqlite_r.0.3 | 401.5 | 492.6 | +22.70% | faster | +30.65% | 1.41% | yes |
| 723.llvm_r.1.0 | 298.6 | 362.0 | +21.24% | faster | +29.02% | 1.50% | yes |
| 753.ns3_r.2.0 | 328.2 | 402.8 | +22.74% | faster | +31.47% | 1.57% | yes |

**Verdict: accepted.** Stats are bit-identical to `trial1-fast` on 5/5, and all five are
faster, by +21.24% to +23.01%. Cumulatively the build is +29.0% to +32.0% over the
`.opt` baseline.
- **Why so large:** gem5's own "12%" claim for tcmalloc is exceeded here.
- **For the kratos2 port:** compute nodes have no tcmalloc, so the port must ship
  `libtcmalloc_minimal.so.4` next to the binary (with an rpath) or link it statically.

### Trial 3 — optimized `ext/` libraries

**Summary:** the bundled `ext/` libraries were compiled with no `-O` flag, i.e. -O0.
Building them at `-O3` gains 3.3–3.4% on the two memory-heavy checkpoints and is neutral
to slightly negative on the compute-bound ones. Stats are bit-identical.
**Accepted, narrowly.**

**Key idea:** gem5's SConstruct runs the `ext/` SConscripts on the base environment
before the per-variant `-O3` is added (`SConstruct:1003-1011` vs `src/SConscript:689-698`).
So every `ext/` library is compiled at -O0 in every variant, `.fast` included.
`ext/drampower` is on the simulation path: every DRAM command is logged to DRAMPower,
and `calcWindowEnergy` runs at each refresh (`src/mem/dram_interface.cc:1219, 1777,
1827`). `CCFLAGS_EXTRA` is appended before the `ext/` loop (`SConstruct:998-999`), so
`CCFLAGS_EXTRA=-O3` optimizes `ext/`. `src/` is unaffected because its own `-O3` comes
later.

**Files and flags targeted:** `CCFLAGS_EXTRA=-O3`, new build dir `ARM_ext`. No source
change. `compile_commands.json` confirms that all 13 `ext/drampower` sources now get `-O3`.

```
CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='-O3' LINKFLAGS_EXTRA='' scons build/ARM_ext/gem5.fast -j32 --ignore-style
```

Built in 412 s, with 42247820 bytes of `.text`.

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 688.9 | 676.4 | -1.82% | slower | +29.59% | 0.36% | yes |
| 706.stockfish_r.2.4 | 719.3 | 712.8 | -0.91% | slower | +30.75% | 0.36% | yes |
| 708.sqlite_r.0.3 | 492.6 | 496.1 | +0.71% | faster (within noise) | +31.58% | 1.41% | yes |
| 723.llvm_r.1.0 | 362.0 | 374.2 | +3.38% | faster | +33.38% | 1.50% | yes |
| 753.ns3_r.2.0 | 402.8 | 416.3 | +3.34% | faster | +35.86% | 1.57% | yes |

**Verdict: accepted.** Stats are bit-identical on 5/5, and 3/5 are faster than Trial 2, so
the rule is met. But it is narrow:
- the gain is clear only on `723.llvm_r` (+3.38%) and `753.ns3_r` (+3.34%), the two
  lowest-IPC, most memory-active checkpoints, where DRAMPower sees the most commands;
- `708.sqlite_r`'s +0.71% is inside its noise;
- both stockfish checkpoints, compute-bound at IPC 2.3–2.5, got slower by 0.91% and
  1.82%.

The stockfish drop is larger than its baseline noise. It is more likely a code-layout
side effect than a real cost, since only `ext/` code changed. Expect this lever to help
DRAM-heavy workloads (like the agentic ones) and to be neutral elsewhere.

**Correction (2026-09-27, from the profile, see "Profile of the accepted build"):** the
DRAMPower explanation above is wrong.
- **Evidence:** profiling the Trial 2 binary (`ext/` still at -O0) over
  `723.llvm_r`'s measured region puts all DRAMPower code at **0.14%** of samples.
  Optimizing it cannot yield +3.4%.
- **So:** Trial 3's gains on llvm and ns3 are most likely code-layout or measurement
  noise, and the stockfish losses the same. The lever is harmless and stays in the
  recipe, but it gives no real speedup.
- **Protocol lesson:** the two-run noise figure underestimates layout noise. The same
  Trial 2 binary measured 362.0 KIPS on llvm with five concurrent runs and 381.5 KIPS
  running alone.

### Trial 4 — link-time optimization (LTO), with a linker comparison

**Summary:** building with GCC LTO shrinks `.text` from 42.2 MB to 29.8 MB. It speeds up
all five checkpoints by 1.3–6.3% (quiet-start rerun, bfd), with stats bit-identical.
The linker (bfd, gold, mold) matters about as much as run-to-run noise.
**Accepted, with bfd.**

**Key idea:** gem5 is hundreds of separately compiled files with hot calls across
them (O3 pipeline stages, caches, TLBs, branch predictor, the event queue). LTO lets
GCC inline and optimize across those file boundaries and drop unused code.
- It is opt-in via `--with-lto` (`SConstruct:125-126, 693-708`), which sets
  `-flto=<jobs>` for the compile and the link. It has been off by default since v21
  (`RELEASE-NOTES.md:1605`).
- `ext/` libraries do not get the LTO flags.

**Files and flags targeted:** `--with-lto --linker={bfd,gold,mold}` on top of the Trial 3
configuration, in a new build dir `ARM_lto`. `apt install mold` (2.30) was needed. The
first build compiles everything; the gold and mold builds only relink. Objects carry
`.gnu.lto_*` sections (1346 in `cpu/o3/cpu.fo`), confirming LTO. No source change.

```
CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='-O3' LINKFLAGS_EXTRA='' scons build/ARM_lto/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
```

| Linker | Build time | Binary | `.text` |
|---|---|---|---|
| bfd | 325 s (full compile + LTO link) | 68.0 MB | 29.85 MB |
| gold | 93 s (relink only) | 68.2 MB | 29.85 MB |
| mold | 83 s (relink only) | 87.9 MB | 32.21 MB |

The first pass ran the three linkers back to back. gold and mold started with a 1-minute
load average of 3.7, which the plan requires to be re-run: the load average lags, so it
still read high right after the previous trial. `run_suite.sh` now waits for it to fall
below 1.0 before starting (up to 5 min), and records the wait. All three linkers were
re-run under that guard. Both passes are shown.

**bfd, quiet-start rerun (`trial4-lto-bfd-r2`), the configuration that was adopted:**

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 676.4 | 710.4 | +5.03% | faster | +36.11% | 0.36% | yes |
| 706.stockfish_r.2.4 | 712.8 | 757.5 | +6.27% | faster | +38.95% | 0.36% | yes |
| 708.sqlite_r.0.3 | 496.1 | 523.5 | +5.51% | faster | +38.83% | 1.41% | yes |
| 723.llvm_r.1.0 | 374.2 | 380.0 | +1.53% | faster | +35.42% | 1.50% | yes |
| 753.ns3_r.2.0 | 416.3 | 421.8 | +1.32% | faster (within noise) | +37.66% | 1.57% | yes |

**gold, quiet-start rerun:**

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 676.4 | 708.5 | +4.75% | faster | +35.75% | 0.36% | yes |
| 706.stockfish_r.2.4 | 712.8 | 738.1 | +3.56% | faster | +35.40% | 0.36% | yes |
| 708.sqlite_r.0.3 | 496.1 | 516.0 | +4.00% | faster | +36.84% | 1.41% | yes |
| 723.llvm_r.1.0 | 374.2 | 377.1 | +0.76% | faster (within noise) | +34.39% | 1.50% | yes |
| 753.ns3_r.2.0 | 416.3 | 425.8 | +2.29% | faster | +38.98% | 1.57% | yes |

**mold, quiet-start rerun:**

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 676.4 | 707.2 | +4.56% | faster | +35.51% | 0.36% | yes |
| 706.stockfish_r.2.4 | 712.8 | 735.5 | +3.19% | faster | +34.93% | 0.36% | yes |
| 708.sqlite_r.0.3 | 496.1 | 501.2 | +1.02% | faster (within noise) | +32.91% | 1.41% | yes |
| 723.llvm_r.1.0 | 374.2 | 374.4 | +0.04% | faster (within noise) | +33.43% | 1.50% | yes |
| 753.ns3_r.2.0 | 416.3 | 425.6 | +2.24% | faster | +38.91% | 1.57% | yes |

First pass, not quiet at start (for the record): bfd faster on 3/5 (mean +2.11%);
gold on 3/5 (mean +1.58%, started at load 3.74); mold on 5/5 (mean +2.52%, started at
load 3.77). Stats were bit-identical in all six runs.

| Linker | Mean change, first pass | Mean change, quiet rerun | Average |
|---|---|---|---|
| bfd | +2.11% | +3.93% | +3.02% |
| gold | +1.58% | +3.07% | +2.33% |
| mold | +2.52% | +2.21% | +2.37% |

**Verdict: accepted, with the bfd linker.** Stats are bit-identical on 5/5 for every
linker, and the quiet-start rerun is faster on 5/5 for every linker.
- **Why bfd:** it has the best quiet-start result (mean +3.93%) and the best two-pass
  average, and it is the system default, which is also simplest for the kratos2 port.
- **The linker gap is small:** about 1%, the same size as run-to-run noise. This agrees
  with gem5's own linker benchmark, which found that linkers don't matter for runtime.
- **mold is worth it for development builds:** it relinks in 83 s. It gives `.text`
  2.4 MB larger than bfd/gold.
- **Cumulative:** +35% to +39% over the `.opt` baseline.
- **Same-binary noise:** the two bfd runs (first pass and quiet rerun) used the same
  binary, yet differed by 0.95% (stockfish.1.1), 1.55% (stockfish.2.4), 4.06% (sqlite),
  2.55% (llvm) and 1.71% (ns3). The first pass started at load 1.34, so part of this is
  load, but it bounds how much any single trial below ~4% can be trusted.
- **Local binaries:** the adopted binary is `build/ARM_lto/gem5.fast.bfd`.
  `build/ARM_lto/gem5.fast` is whichever linker ran last, which is mold.

### Trial 5a — `-march=x86-64-v2`

**Summary:** targeting x86-64-v2 (SSE4.2, POPCNT, SSSE3) on top of Trial 4 has no
measurable effect on speed. Against the adopted bfd run, 4 of 5 checkpoints are slower
(−0.2% to −3.4%); against the first run of the same bfd binary, 3 of 5 are faster. Every
change is inside the same-binary spread. Stats are bit-identical. **Not adopted.**

**Key idea:** x86-64-v2 is the newest ISA level every kratos2 node class is certain to
support. It lets GCC use `popcnt` and SSE4.x instead of the generic x86-64 baseline:
bit-count builtins become single instructions, and some loops and string/memory idioms
get better code. Since v2 has no FMA, host floating-point results cannot change.

**Files and flags targeted:** `CCFLAGS_EXTRA="-O3 -march=x86-64-v2"` and
`LINKFLAGS_EXTRA="-march=x86-64-v2"` (the link flag is needed because LTO does code
generation at link time). New build dir `ARM_v2`. No source change.
- **Flag check:** the binary has 161 `popcnt` and 1723 SSE4.x instructions; the Trial 4
  binary has none.
- **Build:** 316 s, `.text` 29.79 MB.

```
CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='-O3 -march=x86-64-v2' LINKFLAGS_EXTRA='-march=x86-64-v2' scons build/ARM_v2/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
```

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 710.4 | 708.9 | -0.21% | slower (within noise) | +35.83% | 0.36% | yes |
| 706.stockfish_r.2.4 | 757.5 | 740.1 | -2.29% | slower | +35.77% | 0.36% | yes |
| 708.sqlite_r.0.3 | 523.5 | 506.0 | -3.35% | slower | +34.18% | 1.41% | yes |
| 723.llvm_r.1.0 | 380.0 | 374.3 | -1.48% | slower (within noise) | +33.42% | 1.50% | yes |
| 753.ns3_r.2.0 | 421.8 | 427.2 | +1.28% | faster (within noise) | +39.42% | 1.57% | yes |

**Verdict: not adopted; no measurable effect.** Stats are bit-identical on 5/5, but only
1/5 is faster than the reference (`753.ns3_r` +1.28%, within noise), so the rule is not
met.
- **The verdict depends on the reference run.** Against the first-pass run of the same
  bfd binary (`trial4-lto-bfd`), v2 is faster on 3/5 and would pass:

  | Checkpoint | v2 vs first bfd run | v2 vs bfd rerun (reference) |
  |---|---|---|
  | 706.stockfish_r.1.1 | −1.16% | −0.21% |
  | 706.stockfish_r.2.4 | −0.77% | −2.29% |
  | 708.sqlite_r.0.3 | +0.66% | −3.35% |
  | 723.llvm_r.1.0 | +1.07% | −1.48% |
  | 753.ns3_r.2.0 | +3.03% | +1.28% |

  Every change is inside the 0.95–4.06% spread between the two runs of that one
  binary, so neither a gain nor a loss is demonstrated.
- **Why no effect is plausible:** gem5's time goes to pointer chasing, branchy control
  flow and heap allocation, not to the bit-counting or vector idioms v2 speeds up. v2
  mostly perturbs code layout.
- **Not adopted** because it has no demonstrated benefit and is one more build knob.
- **Next:** Trial 5b tries x86-64-v3 from the same base (Trial 4), not on top of v2.

### Trial 5b — `-march=x86-64-v3 -ffp-contract=off`

**Summary:** targeting x86-64-v3 (AVX, AVX2, BMI1/2, FMA, LZCNT/TZCNT, MOVBE), with
floating-point contraction disabled, **changes simulation results**. About 2000 stats
differ on every checkpoint, including simulated time and cache hit/miss counts. A rerun
of the same binary reproduces its results exactly, so the change is deterministic. It is
not measurably faster either. **Rejected** because results change.

**Key idea:** v3 adds 256-bit vectors and BMI2 bit manipulation. `-ffp-contract=off` was
added so that GCC could not fuse multiply-adds, since FMA changes host floating-point
rounding. The goal was faster simulation with identical results.

**Deployability check:** one tiny `srun --immediate` probe per kratos2 node class:
- **kratos0–9:** kratos9, Xeon Gold 5118 (Skylake-SP): AVX2, AVX-512.
- **kratos11–19:** kratos12 and kratos17, Xeon Gold 6226R (Cascade Lake): AVX2, AVX-512.
- **safari-nexus1:** AMD EPYC 9554 (Zen 4): AVX2, AVX-512. (Later excluded from all
  runs by the user.)
- **kratos10:** the single 256-CPU node was busy and is not verified.

So v3 would have been deployable on every verified class.

**Files and flags targeted:** `CCFLAGS_EXTRA="-O3 -march=x86-64-v3 -ffp-contract=off"` and
the same `-march`/`-ffp-contract` in `LINKFLAGS_EXTRA` (LTO), on top of Trial 4 (not on
top of 5a). New build dir `ARM_v3`. No source change.
- **Flag check:** 38,434 `ymm` and 9,514 BMI2 instructions, against zero in Trial 4.
  Only 3 FMA instructions remain; they come from explicit `fma()` calls, which are
  exactly rounded either way.
- **Build:** 317 s, `.text` 30.58 MB.

```
CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='-O3 -march=x86-64-v3 -ffp-contract=off' LINKFLAGS_EXTRA='-march=x86-64-v3 -ffp-contract=off' scons build/ARM_v3/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
```

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 710.4 | 706.4 | -0.56% | slower | +35.35% | 0.36% | NO |
| 706.stockfish_r.2.4 | 757.5 | 735.2 | -2.95% | slower | +34.86% | 0.36% | NO |
| 708.sqlite_r.0.3 | 523.5 | 505.8 | -3.38% | slower | +34.14% | 1.41% | NO |
| 723.llvm_r.1.0 | 380.0 | 385.0 | +1.34% | faster (within noise) | +37.23% | 1.50% | NO |
| 753.ns3_r.2.0 | 421.8 | 412.0 | -2.32% | slower | +34.46% | 1.57% | NO |

Differing stats per checkpoint against `trial1-fast`: 706.stockfish_r.1.1: 2183, 706.stockfish_r.2.4: 1964, 708.sqlite_r.0.3: 2106, 723.llvm_r.1.0: 2407, 753.ns3_r.2.0: 1919.

**Determinism check (2026-09-27).** The same v3 binary (identical sha256) was rerun with
a quiet start (`trial5b-v3-r2`, load 0.08). Its stats are **bit-identical to the first
v3 run on 5/5**. The divergence from `trial1-fast` is therefore not run-to-run
nondeterminism: it is a deterministic function of how the binary was compiled.

| Checkpoint | v3 first run KIPS | v3 rerun KIPS | Rerun vs Trial 4 (bfd rerun) |
|---|---|---|---|
| 706.stockfish_r.1.1 | 706.4 | 718.4 | +1.13% |
| 706.stockfish_r.2.4 | 735.2 | 756.8 | −0.09% |
| 708.sqlite_r.0.3 | 505.8 | 520.6 | −0.55% |
| 723.llvm_r.1.0 | 385.0 | 388.0 | +2.11% |
| 753.ns3_r.2.0 | 412.0 | 415.0 | −1.61% |

**Verdict: rejected.**
1. **Results change**, deterministically. Every checkpoint diverges: simulated ticks,
   L1D hits and misses, DRAM traffic, and the instruction count at the stop point (a
   few instructions either way).
2. **It isn't measurably faster:** the first run was slower on 4/5 (−0.56% to −3.38%),
   the rerun faster on 2/5 (−1.61% to +2.11%). Both are inside the same-binary spread.

**Finding for part 2 (correctness, not speed):** the fork's simulation results depend on
the host code-generation target. `x86-64-v2` was bit-identical; `x86-64-v3` is not, and
it reproduces its own different results exactly on a rerun.
- FMA contraction is ruled out: it is disabled, and the 3 remaining FMAs are exactly
  rounded.
- `ctz`/`clz` of zero is ruled out: gem5's bit helpers guard zero
  (`src/base/bitfield.hh`), and the only raw builtins are in SVE code, which is unused.
- **Leading suspect:** a read of uninitialized or out-of-bounds memory whose contents
  depend on generated code.
  - **Confirmed uninitialized read (2026-09-27), but not the cause of the timing
    change (see the part-2 "Diagnostics" section):** `LoopPredictor::BranchInfo::loopPredUsed`.
    The constructor does not initialize it (`src/cpu/pred/loop_predictor.hh:150-161`).
    It is set only when the loop predictor is used (`loop_predictor.cc:298`), yet it is
    read on every prediction (`tage_sc_l.cc:419`, which sets the provider to LOOP) and
    in `updateStats` (`loop_predictor.cc:334`). Its value depends on what the allocator
    left in that heap slot.
  - The TAGE `BranchInfo` `new int[...]` arrays, first suspected here, are also left
    uninitialized. A code review during the hotspot follow-up found their reads guarded
    by `noSkip`. That check is by reading only.
- **Until this is fixed:** never mix gem5 binaries built with different `-march` in
  one experiment. The kratos2 build keeps the generic x86-64 target.

### Trial 6 — profile-guided optimization (PGO)

**Summary:** GCC PGO, trained on three SPEC checkpoints that are **not** in the test
suite, speeds up all five test checkpoints by 8.1–11.3% on top of Trial 4. Stats are
bit-identical. **Accepted by the gate.** Whether it belongs in the everyday build is a
workflow decision, discussed below.

**Key idea:** gem5 is front-end bound with a flat profile: many functions, heavy virtual
dispatch, and branches whose bias is known only at run time. PGO gives GCC real
branch probabilities, call counts and hot/cold information, which drive inlining, basic-
block layout, hot/cold function splitting and loop decisions. Code that never ran in
training keeps normal optimization, thanks to `-fprofile-partial-training`, so
workloads outside the training set are not penalized.

**Files and flags targeted:** no source change. Everything is in build dir `ARM_pgo`, on
top of the accepted Trial 4 configuration (`.fast`, tcmalloc, `ext/` at `-O3`,
`--with-lto --linker=bfd`).
1. **Instrumented build** (412 s; 750 MB binary, 74.2 MB `.text`):

   ```
   CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='-O3 -fprofile-generate' LINKFLAGS_EXTRA='-fprofile-generate' scons build/ARM_pgo/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
   ```

2. **Training:** `run_suite.sh build/ARM_pgo/gem5.fast pgo-train train` on the three
   training checkpoints (10M+30M each, concurrent). It wrote 2034 `.gcda` files
   (74.3 MB). Instrumented speed: 721.gcc_r.2.0 177.7 KIPS, wall 294.4s; 748.flightdm_r.2.2 229.0 KIPS, wall 212.7s; 767.nest_r.1.0 403.5 KIPS, wall 134.9s;
3. **Optimized build** in the same dir (266 s). No profile mismatch warnings; the
   binary has no gcov instrumentation; 73.2 MB binary, 34.84 MB `.text`. The code
   grows 17% over Trial 4's 29.85 MB because of profile-driven inlining and unrolling
   on hot paths.

   ```
   CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA='-O3 -fprofile-use -fprofile-partial-training -Wno-missing-profile' LINKFLAGS_EXTRA='-fprofile-use -fprofile-partial-training' scons build/ARM_pgo/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
   ```

**Test suite (disjoint from training):**

| Checkpoint | Previous KIPS | New KIPS | Change | Direction | Cumulative vs baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 710.4 | 789.6 | +11.15% | faster | +51.29% | 0.36% | yes |
| 706.stockfish_r.2.4 | 757.5 | 822.9 | +8.64% | faster | +50.96% | 0.36% | yes |
| 708.sqlite_r.0.3 | 523.5 | 566.0 | +8.13% | faster | +50.12% | 1.41% | yes |
| 723.llvm_r.1.0 | 380.0 | 419.5 | +10.42% | faster | +49.52% | 1.50% | yes |
| 753.ns3_r.2.0 | 421.8 | 469.3 | +11.27% | faster | +53.17% | 1.57% | yes |

**Verdict: accepted by the gate rule.** Stats are bit-identical on 5/5, and all five are
faster, by +8.13% to +11.27%.
- **Cumulative:** +49.5% to +53.2% over the `.opt` baseline.
- **It generalizes:** the gain appears on workloads the profile never saw (sqlite,
  stockfish, llvm, ns3; trained on flightdm, gcc, nest).

**Workflow cost:** a PGO build costs instrumented build + training + optimized build,
about 412 s + ~5 min + 266 s ≈ 16 min, against ~5.4 min for a plain LTO build.
- **Staleness is gradual.** When source files change, GCC drops the profile only for the
  functions whose code changed (they fall back to normal optimization under
  `-fprofile-partial-training`). The rest of the simulator keeps its profile, so
  retraining is occasional, not per build.
- **Decision (user, 2026-09-27):** the user asked whether the ~10% is worth this
  pipeline in an actively developed simulator, and chose **PGO for bulk-experiment
  binaries only**. Development builds use the Trial 4 recipe without PGO (mold is an
  option for fast relinks).

## Profile of the accepted build

**Binary:** `build/ARM_pgo/gem5.fast`, the Trial 6 recipe that is adopted for bulk runs.
It is profiled exactly as measured, with function-level symbols and no rebuild.

**Method:** `util/perf-opt/profile_region.sh` runs one checkpoint, pinned to core 1, with
the suite's 10M warmup + 30M detailed window. It attaches the profiler only when
`fs_run.py` prints its "(measured)" marker, so startup and checkpoint restore are
excluded; `perf` detaches when gem5 exits.
- **Checkpoints:** a high-IPC compute one, `706.stockfish_r.2.4`, and a low-IPC
  memory-heavy one, `723.llvm_r.1.0`.
- **Tools:** `perf stat -M PipelineL1,PipelineL2` for AMD top-down, `perf record -F 999`
  for self time, and AMD uProf 5.3 TBP (`-p PID`) as a cross-check.
- **Not collected:** call graphs (`perf record -g`) and IBS. The tables below are
  self time only; inclusive costs and precise per-instruction attribution are left to
  part 2.

### Where the host CPU loses time (AMD top-down, Zen 5)

| Metric | 706.stockfish_r.2.4 | 723.llvm_r.1.0 |
|---|---|---|
| Host IPC | 2.65 | 2.43 |
| Host instructions per simulated instruction | 15.4 K | 28.4 K |
| Front-end bound (bandwidth / latency) | **45.6%** (23.9 / 21.7) | **46.3%** (23.0 / 23.3) |
| Back-end bound (memory / CPU) | 17.3% (16.4 / 0.8) | 18.4% (17.5 / 0.9) |
| Bad speculation | 5.6% | 6.3% |
| Retiring | 31.2% | 28.7% |
| L1 instruction-cache misses per 1K host instructions | 7.5 | 7.6 |
| L1 data-cache misses per 1K host instructions | 33 | 31 |
| iTLB misses (whole region) | ~3.8 K | ~6.1 K |

- **Front end:** even with LTO and PGO, gem5 is **front-end bound on about 46% of issue
  slots**, split evenly between fetch bandwidth and latency. This matches published gem5
  profiling (30–42% on Xeon). Instruction-cache capacity and fetch bandwidth are the
  likely cause.
- **Address translation:** the iTLB row is perf's generic `iTLB-load-misses`, which on
  Zen counts misses in both the L1 and L2 iTLB, i.e. page walks. Those are negligible.
  L1 iTLB misses that hit in the L2 TLB were not counted. So page walks are ruled out,
  but not all translation cost; huge pages for code look unlikely to help and were not
  tried.
- **Back end:** the back-end share is data-cache misses, from pointer-heavy data
  structures.

### Hotspot functions (self time, measured region)

The profile is flat. The hottest function is about 6.5%, and the region touches 562
(stockfish) and 944 (llvm) distinct functions.

| # | Function (self time) | 706.stockfish_r.2.4 | 723.llvm_r.1.0 |
|---|---|---|---|
| 1 | `o3::CPU::tick` | 6.44% | 6.53% |
| 2 | `RefCountingPtr<o3::DynInst>::del` | 5.72% | 4.60% |
| 3 | `o3::IEW::tick` | 4.19% | 3.83% |
| 4 | `operator delete[]` | 3.68% | 3.31% |
| 5 | `operator new[]` | 3.27% | 3.37% |
| 6 | `o3::Fetch::fetch` | 3.75% | 2.84% |
| 7 | `bp::TAGEBase::updateHistories` | 2.53% | 4.02% |
| 8 | `o3::InstructionQueue::scheduleReadyInsts` | 3.56% | 2.75% |
| 9 | `o3::BAC::generateFetchTargets` | 1.36% | 4.57% |
| 10 | `bp::TAGE_SC_L_TAGE::calculateIndicesAndTags` | 2.53% | 3.03% |
| 11 | `o3::Fetch::buildInst` | 2.08% | 2.29% |
| 12 | `o3::InstructionQueue::wakeDependents` | 2.33% | 1.37% |
| 13 | `o3::Commit::commitInsts` | 2.23% | 1.36% |
| 14 | `o3::IEW::executeInsts [.cold]` | 2.06% | 1.46% |
| 15 | `o3::LSQUnit::read` | 1.94% | 1.42% |
| 16 | `o3::Rename::renameInsts` | 1.82% | 1.49% |
| 17 | `o3::IEW::dispatchInsts` | 1.91% | 1.31% |
| 18 | `bp::TAGE_SC_L_64KB_StatisticalCorrector::gPredictions` | 1.59% | 1.44% |
| 19 | `o3::InstructionQueue::insert` | 1.60% | 1.17% |
| 20 | `ArmISA::TLB::multiLookup` | 1.26% | 1.40% |
| 21 | `BaseCache::access` | 1.22% | 1.43% |
| 22 | `prefetch::Base::probeNotify` | 1.11% | 1.22% |
| 23 | `bp::BPredUnit::squashHistory` | 0.17% | 1.98% |
| 24 | `o3::Rename::renameDestRegs` | 1.26% | 0.88% |
| 25 | `o3::Commit::commit` | 1.14% | 0.93% |

- **uProf cross-check:** uProf TBP over llvm's region gives the same top ten, in nearly
  the same order: `CPU::tick`, `operator new[]`, `IEW::tick`, the DynInst release,
  `generateFetchTargets`, `scheduleReadyInsts`, `updateHistories`, tcmalloc's
  `tc_free_sized`, `calculateIndicesAndTags` and `Fetch::fetch`.
- **`IEW::executeInsts [.cold]` holds 1.5–2%, a PGO training gap.** PGO moved most of
  the function into the cold clone. Per `nm -S`, the PGO binary's hot part is 536 B and
  its `.cold` is 3372 B. In the non-PGO Trial 4 binary they are 2401 B and 59 B, and
  the 59 B is only exception-handling cleanup. So code the training runs rarely took is
  hot on the test workloads. Broader training may recover some of this; that is
  untested. (Corrected 2026-09-27: an earlier edit wrongly called this "not a PGO
  artifact" because it saw a `.cold` clone in both binaries without comparing sizes.)

### Self time by subsystem

| Subsystem | 706.stockfish_r.2.4 | 723.llvm_r.1.0 |
|---|---|---|
| Issue queue + IEW + FU pool (`o3/inst_queue.cc`, `o3/iew.cc`) | 19.3% | 15.2% |
| Heap alloc/free + DynInst refcount release | 14.7% | 13.1% |
| Branch prediction, TAGE-SC-L (`pred/tage_base.cc`, `tage_sc_l*.cc`, `bpred_unit.cc`) | 8.5% | 13.7% |
| Fetch + decode (`o3/fetch.cc`) | 9.1% | 8.6% |
| LSQ (`o3/lsq*.cc`) | 9.0% | 6.0% |
| O3 `CPU::tick` (`o3/cpu.cc`) | 7.1% | 7.0% |
| Rename | 6.2% | 4.8% |
| Commit + ROB | 5.7% | 4.0% |
| Caches, tags, replacement, packets | 3.8% | 6.4% |
| ARM TLB / MMU | 3.5% | 4.6% |
| Decoupled front end (`o3/bac.cc`) | 2.1% | 6.2% |
| Prefetchers (stride, SMS, BOP, FDP) | 1.3% | 1.6% |
| Event queue + simulate loop | 0.8% | 0.7% |
| DRAM controller + DRAMPower | 0.0% | 0.1% |
| Stats | 0.0% | 0.0% |

### Hand-off to part 2 (code-level work), ranked by expected payoff

1. **Per-instruction heap churn (13–15%).**
   - *What:* every fetched instruction heap-allocates a `DynInst` (with its arrays) and
     releases it through `RefCountingPtr::del`. TAGE heap-allocates a `BranchInfo` (with
     `new int[]` arrays) per prediction. The IQ and the dependency graph use `std::list`
     nodes and `new DepEntry`.
   - *Fix:* pooling `DynInst` (ROB-sized) and `BranchInfo` objects attacks this directly.
2. **Issue queue / IEW scheduling (15–19%):** `scheduleReadyInsts` (per-op-class priority
   queues), `wakeDependents`, `insert`, `executeInsts`, `dispatchInsts`.
3. **TAGE-SC-L (8.5–13.7%):** `updateHistories` and `calculateIndicesAndTags` update
   folded histories for all 36 tables. By code reading (unverified), the even-numbered
   tables' folded registers duplicate the odd ones and are never read. Also SC
   `gPredictions` and `squashHistory`.
4. **Decoupled front end (2–6%):** `generateFetchTargets` probes the BTB at every 4-byte
   address. It grows with branch mispredictions (6.2% on llvm).
5. **Set-associative lookups that return a vector by value** (TLB `multiLookup`, cache
   and BTB tags): one heap allocation per probe.
6. **Front-end boundness (~46%):** after part 2 shrinks the hot paths, post-link layout
   (BOLT, available in apt as `bolt-18`) is the remaining build-level lever.
7. **Correctness:** results depend on the host code-generation target (Trial 5b). The
   dependence is deterministic: a v3 binary reproduces its own results exactly. Find
   and fix the codegen-dependent behavior before any further codegen experiments.
   `LoopPredictor::BranchInfo::loopPredUsed` is uninitialized and should be fixed,
   but the part-2 diagnostics show it affects only branch-predictor statistics, not
   timing, so the cause of the timing change is still open (see "Diagnostics").
8. **Outside the KIPS metric:** 50–105 s per run go to startup and checkpoint restore
   (Baseline). That matters for bulk throughput, not for KIPS.

## Cluster port (kratos2)

**Goal:** rebuild the accepted recipe on the cluster, check that it reproduces the local
stats bit for bit, and measure its speedup on the cluster's own CPUs. The cluster checkout
is `rbdev` at `8d0dafc`, the same simulator source as `feat/opt`, so no push was needed.

**Build (login node, per the user's instruction, detached with `nice -n 10`):**

```
CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA="-O3" LINKFLAGS_EXTRA="-Wl,-rpath,/home/rahbera/agentic-cpu/lib" \
    scons build/ARM_rel/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
```

- **Toolchain:** g++-12 on the login node is 12.1.0 (12.4.0 locally). The build took
  1039 s, much of it SCons reading build scripts and probing compilers over NFS.
- **Shared libraries:** the login node links tcmalloc 2.9.1 and protobuf 3.12.4, which
  some compute nodes lack.
  - tcmalloc is missing on several node classes.
  - `libprotobuf.so.23` is missing on `safari-nexus1`. The first agentic validation
    failed there with "cannot open shared object file", before the user excluded that
    node.
  - Both libraries now live in `/home/rahbera/agentic-cpu/lib` on NFS. The binary's
    RUNPATH is the Python config dir, then `/usr/lib/x86_64-linux-gnu`, then that NFS
    dir. Nodes that have their own copy load it, and nodes without it fall back to the
    NFS copies.
- **Node exclusion:** every Slurm script now carries `#SBATCH --exclude=safari-nexus1`,
  on the user's instruction.

**Validation.** `slurm/compare-two.sbatch` runs the old cluster binary (A:
`build/ARM/gem5.opt`, gcc 11.4, no tcmalloc, no LTO) and the new one (B:
`build/ARM_rel/gem5.fast`) at the same time on one node, each pinned to its own
allocated CPU. The window is 10M + 30M.

| Checkpoint | Node (CPU) | A: old `.opt` KIPS | B: new `.fast` KIPS | Speedup | Stats |
|---|---|---|---|---|---|
| SPEC `723.llvm_r.1.0` | kratos0 (Xeon Gold 5118), separate physical cores | 82.4 | 117.0 | **+42.0%** | A and B each bit-identical to the local runs of the same variant |
| agentic `gin-2121/cpt.0` | kratos10, separate cores | 78.9 | 115.9 | **+46.9%** | identical except `numMiscRegReads` (the Trial 1 assert artifact); stats IPC 0.828 both (`virt_run.py` prints "IPC (measured)" 0.817) |
| SPEC `723.llvm_r.1.0` | kratos6 (Xeon Gold 5118), **SMT siblings 9/33** | 57.5 | 66.6 | +15.8% | A and B each bit-identical to the local runs of the same variant |

"Separate physical cores" means the two runs did not share a core with each other.
Whether other jobs ran on those cores' SMT siblings was not recorded.

- **Results matched across compilers and hosts, on what was tested:** on SPEC
  `723.llvm_r.1.0`, the cluster `.opt` (gcc 11.4) matches the local `.opt` (g++ 12.4),
  and the cluster `.fast` (g++ 12.1, with and without PGO) matches the local `.fast`
  (g++ 12.4), bit for bit. The agentic checkpoint was compared only between cluster
  nodes (kratos10 and kratos0, same build). One checkpoint is evidence, not proof,
  that results at the generic x86-64 target are independent of compiler version and
  host. Re-check before comparing local and cluster numbers on other workloads, since
  the codegen target does matter (Trial 5b).
- **SMT sharing hurts gem5 badly.** The cluster allocates by logical CPU
  (`SelectTypeParameters=CR_CPU_MEMORY`), so a job can share a physical core with
  another job. On the shared core, each gem5 ran 30% (`.opt`) to 43% (`.fast`) slower
  than on separate cores (the kratos0 run), and the new binary's advantage shrank from
  +42% to +16%. The
  front-end-bound workload suffers most from a sibling competing for fetch and decode.
  - **For clean speed measurements:** use `--hint=nomultithread`.
  - **For bulk throughput:** packing siblings still yields more total work per node,
    but each job runs slower. Budget wall time accordingly.

**PGO on the cluster (bulk-run binary).** The PGO pipeline was redone on the cluster,
because profiles are tied to the exact compiler (12.1 there, 12.4 here). The training
set is **agentic**, since bulk runs will be agentic. It is drawn with
`random.Random(20260927).sample(131 agentic checkpoints, 3)`, excluding the validation
checkpoint: `gson-1093/cpt.2` (Java), `ripgrep-2209/cpt.3` (Rust), `jq-2598/cpt.2` (C).

1. **Instrumented build** on the login node (1475 s):

   ```
   CC=gcc-12 CXX=g++-12 CCFLAGS_EXTRA="-O3 -fprofile-generate" \
       LINKFLAGS_EXTRA="-fprofile-generate -Wl,-rpath,/home/rahbera/agentic-cpu/lib" \
       scons build/ARM_pgo/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
   ```

2. **Training:** one Slurm job, 3 CPUs, on kratos3, running `slurm/pgo-train.sbatch` with
   the three checkpoints, 10M+30M each, under `virt_run.py`. It took 36 min and wrote
   2052 `.gcda` files.
3. **Optimized build**, in the same dir, with no profile mismatch warnings:

   ```
   CC=gcc-12 CXX=g++-12 \
       CCFLAGS_EXTRA="-O3 -fprofile-use -fprofile-partial-training -Wno-missing-profile" \
       LINKFLAGS_EXTRA="-fprofile-use -fprofile-partial-training -Wl,-rpath,/home/rahbera/agentic-cpu/lib" \
       scons build/ARM_pgo/gem5.fast -j32 --ignore-style --with-lto --linker=bfd
   ```

| Checkpoint (kratos0, separate physical cores) | Non-PGO `.fast` KIPS | PGO `.fast` KIPS | PGO gain | Stats |
|---|---|---|---|---|
| agentic `gin-2121/cpt.0` (not in training) | 84.7 | 101.1 | **+19.4%** | bit-identical to non-PGO, and to the kratos10 run |
| SPEC `723.llvm_r.1.0` (not in training) | 115.6 | 136.1 | **+17.7%** | bit-identical to local `trial1-fast` |

The agentic-trained profile helps the SPEC checkpoint too. On Skylake-SP the PGO gain
(+18–19%) is larger than on Zen 5 (+8–11%). The cluster PGO binary runs about 1.65×
faster than the old cluster `.opt` on SPEC `723.llvm_r` (136.1 vs 82.4 KIPS). Those two
numbers come from two different jobs, both on kratos0. The non-PGO `.fast`, which ran in
both jobs, measured 117.0 and 115.6 KIPS, so job-to-job variation is about 1%.

**Bulk-run binary:** `/home/rahbera/agentic-cpu/gem5/build/ARM_pgo/gem5.fast` (PGO,
agentic-trained). **Development binary:** `build/ARM_rel/gem5.fast` (the same recipe
without PGO). Keep `build/ARM/gem5.opt` for debugging (`--debug-flags`, asserts).

## Summary

| # | Lever | Verdict | Effect on the local test suite |
|---|---|---|---|
| 1 | `.fast` variant | accepted (user ruling) | +6.4–8.6% |
| 2 | tcmalloc | accepted | +21.2–23.0% |
| 3 | `ext/` at `-O3` | accepted narrowly; later shown to be layout noise | −1.8 … +3.4% |
| 4 | LTO (bfd; gold and mold compared) | accepted | +1.3–6.3% (quiet rerun) |
| 5a | `-march=x86-64-v2` | not adopted: no measurable effect | −3.4 … +1.3% vs the adopted bfd run; −1.2 … +3.0% vs the first run of that binary |
| 5b | `-march=x86-64-v3 -ffp-contract=off` | rejected: **changes results** (deterministically); not measurably faster | −3.4 … +1.3% (first run); −1.6 … +2.1% (rerun) |
| 6 | PGO | accepted, **for bulk-run binaries only** (user decision) | +8.1–11.3% |

- **Local cumulative:** the development recipe (1–4) is +35–39% over the `.opt`
  baseline; with PGO it is **+49.5–53.2%**. Stats are bit-identical throughout, except
  Trial 1's assert-inflated `numMiscRegReads`.
- **Noise:** the same binary run twice varied by up to 4.06%. Effects smaller than
  that (Trial 3, the linker choice in Trial 4, Trial 5a, 5b's speed) are not
  demonstrated in either direction. Trials 1, 2 and 6 are well outside it; Trial 4's
  LTO gain (+1.3–6.3%) is at its edge.
- **On kratos2:** the development recipe is +42% (SPEC) and +47% (agentic) over the old
  cluster `.opt`. PGO adds +18–19%, for about **1.65×** on SPEC against the old binary on
  the same node class (two separate jobs; see the cluster port).
- **Binaries:** locally, `build/ARM_lto/gem5.fast.bfd` (development) and
  `build/ARM_pgo/gem5.fast` (PGO). On kratos2, `build/ARM_rel/gem5.fast` (development)
  and `build/ARM_pgo/gem5.fast` (bulk runs, agentic-trained PGO).
- **Unused modules** were never the problem: nothing un-instantiated runs, and the
  profile shows no time in Ruby, SystemC or the GPU.
- **What gem5 spends its time on:** it is ~46% front-end bound. Its time goes to O3
  scheduling, per-instruction heap churn and TAGE-SC-L; that is part 2's work list.
- **Open correctness item:** results depend on the codegen target (Trial 5b),
  deterministically: a rerun of the v3 binary reproduced its own results exactly.
  `LoopPredictor::BranchInfo::loopPredUsed` is read uninitialized, but it changes
  only branch-predictor statistics, not timing; the cause is still open (see the
  part-2 "Diagnostics" section).

# Part 2: code-level optimizations

Part 1 changed only how gem5 is built. Part 2 changes the simulator's C++ source,
one hotspot at a time, under the same rule: a change is accepted only if it leaves every
stat bit-identical and makes most checkpoints faster. Every trial is logged, accepted or
not; the patch of every rejected trial is kept in `docs/perf-opt/patches/`.

## Part 2 preamble

### Starting point
- **Branch:** `feat/opt` at `16558499426048341effe8ea82bdf45bd70f11f1`. The simulator
  sources are still those of `rbdev` at `8d0dafc`; part 1 changed only docs and
  `util/perf-opt/`.
- **Targets:** the ranked list from the call-graph follow-up to the profile, kept
  outside the repo in `perf-opt-runs/profile/hotspot-deep-dive.md`. Seven read-only
  investigators (one per subsystem) read the source and the DWARF call-graph profiles
  of `723.llvm_r.1.0` and `706.stockfish_r.2.4`; an eighth agent de-duplicated their
  findings, spot-checked the top five and ranked them.
- **Scope (user instruction, 2026-09-27):** apply every target except those in
  TAGE-SC-L (`src/cpu/pred/tage*`, the statistical corrector and the loop predictor),
  which stay untouched. Targets that would change simulation results are out of scope.
- **Dashboard:** live status of every target, at
  https://claude.ai/artifact/YCXc8GVLA9iCgXSn6Mbkvz (private to the user).

### Evaluation build
- **Recipe:** the Trial 4 development recipe (`.fast`, tcmalloc, `ext/` at `-O3`, LTO,
  bfd), in a new build dir `ARM_p2`:

  ```
  CCFLAGS_EXTRA='-O3' util/perf-opt/build.sh ARM_p2 fast --with-lto --linker=bfd
  ```

- **No PGO:** a PGO build would need retraining after every source change, and a stale
  profile would blur the measurement. PGO is retrained once at the end, for the
  bulk-run binary.
- **Binaries are kept:** each accepted candidate is saved as
  `build/ARM_p2/gem5.fast.t<N>` and becomes the reference binary of the next trial.

### Protocol
- **Paired runs** (`util/perf-opt/paired_trial.sh`): each trial first reruns the current
  accepted binary on the test suite (`t<N>-ref`), then runs the candidate (`t<N>`).
  Both wait for a quiet machine first. Part 1 showed that the same binary can move by
  up to 4% between runs, and that a verdict could flip depending on which old run was
  the reference (Trial 5a). Comparing against a fresh run of the reference binary
  removes drift between trials from the verdict.
- **Gate (unchanged, per the user):** stats bit-identical to `trial1-fast` on 5/5
  checkpoints, with no exclusions, **and** at least 3/5 faster than the paired
  reference run. The reference run is also gated, as a sanity check.
- **Tests:** these are pure refactors, so the stats gate is the main correctness test.
  Where gem5 has a unit test for the touched code (for example
  `src/base/refcnt.test.cc`), it is built and run in a separate `ARM_ut` build dir.
- **Numbering:** part-2 trials continue part 1's numbering, from Trial 7.

## Part 2 baseline

- **Binary:** `build/ARM_p2/gem5.fast.base`, sha256 `cb947e52f8659c4a…`, built in 317 s
  with `.text` of 29.85 MB, the same size as Trial 4's bfd binary.
- **Two runs** (`p2-base-a`, `p2-base-b`) are **bit-identical to `trial1-fast` on all
  five checkpoints**. They started at load 0.85 and 0.94, after waiting 70 s and 180 s
  for the machine to settle after the build.

| Checkpoint | KIPS run a | KIPS run b | Part-2 baseline KIPS (mean) | Spread | Trial 4 (bfd rerun) |
|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 704.0 | 709.9 | 707.0 | 0.83% | 710.4 |
| 706.stockfish_r.2.4 | 769.9 | 741.9 | 755.9 | 3.70% | 757.5 |
| 708.sqlite_r.0.3 | 513.1 | 503.4 | 508.3 | 1.92% | 523.5 |
| 723.llvm_r.1.0 | 383.4 | 383.5 | 383.4 | 0.02% | 380.0 |
| 753.ns3_r.2.0 | 423.4 | 414.2 | 418.8 | 2.21% | 421.8 |

The spread (0.02–3.70%) is again larger than part 1's two-run figure and in line with
the same-binary spread found in Trial 4. That is why part 2 compares each candidate with
a fresh run of its reference.

## Part 2 trials

### Trial 7 — inline the `RefCountingPtr` release fast path

**Summary:** releasing a `RefCountingPtr` was always an out-of-line call, even for a
null pointer. Inlining the null test and the decrement, and keeping only the `delete`
out of line, speeds up all five checkpoints by 2.8–6.5% against the paired reference
run. Stats are bit-identical. **Accepted.**

**Key idea:** `RefCountingPtr::del()` carried `GEM5_NO_INLINE`, added upstream (#2686)
only to stop GCC's false `-Wuse-after-free` in the refcount unit test. Every
`DynInstPtr` destructor, assignment and reset therefore called `del()`. The O3 CPU
releases about 104 mostly-null `DynInstPtr` per simulated cycle, just by clearing its
inter-stage time buffers. In the profile, 73% of `del()`'s self time was call entry,
null test and return; the delete path was about 3%.

**Files targeted:** `src/base/refcnt.hh`. `del()` is now an ordinary inline function
that tests, decrements and calls a new `GEM5_NO_INLINE static destroy(T *)`, which only
does the `delete`. The false warning cannot return, because GCC still cannot see the
free next to the decrement.

- **Build:** 128 s (incremental). `.text` grew by 80 KB to 29.93 MB. GCC left 74
  out-of-line calls to `del<DynInst>`, at sites it judged cold.
- **Unit test:** `build/ARM_ut/base/refcnt.test.opt`, built with `--linker=mold` as in
  the upstream report: 8/8 pass, and no `use-after-free` warning in the build log.

| Checkpoint | Paired reference KIPS | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 705.3 | 744.5 | +5.55% | faster | +5.30% | 0.83% | yes |
| 706.stockfish_r.2.4 | 737.7 | 785.9 | +6.53% | faster | +3.96% | 3.70% | yes |
| 708.sqlite_r.0.3 | 513.4 | 527.9 | +2.82% | faster | +3.86% | 1.92% | yes |
| 723.llvm_r.1.0 | 371.1 | 382.8 | +3.15% | faster | −0.15% | 0.02% | yes |
| 753.ns3_r.2.0 | 431.1 | 444.4 | +3.07% | faster | +6.10% | 2.21% | yes |

**Verdict: accepted.** Stats are bit-identical to `trial1-fast` on 5/5 (the paired
reference run is identical too), and all five are faster than the paired reference,
by +2.82% to +6.53%. This is in line with the deep dive's estimate of 2.5–4%.
- **Why pairing matters here:** the reference binary is the part-2 baseline binary, yet
  its paired run measured llvm at 371.1 KIPS against a baseline mean of 383.4 (−3.2%).
  Against the old baseline mean, llvm would look unchanged (−0.15%). Against the run
  taken minutes earlier under the same conditions, it is +3.15%.
- **Binary:** `build/ARM_p2/gem5.fast.t7`, the reference for Trial 8.

### Trial 8 — zero the time-buffer slots in 64-byte pieces

**Summary:** after Trial 7, the per-cycle reset of the O3 time buffers is dominated by
`rep stosq`. Zeroing each slot in 64-byte pieces removed half of those instructions, but
the constructor that follows then compiled to `rep stosq` itself. Stats are
bit-identical, but only 2 of 5 checkpoints got faster. **Rejected.**

**Key idea:** `TimeBuffer::advance()` destroys the oldest slot, memsets all of it
(136–848 bytes per buffer; about 1.6 KB per simulated cycle over the five O3 buffers),
and placement-news a fresh `T`. GCC expands a fixed-size memset of that size into
`rep stosq`, whose startup cost is large for so few bytes. The profile put `rep stosq`
at 39% of `CPU::tick`'s self time. A loop of 64-byte `memset`s compiles to plain SSE
stores instead (checked with g++-12 on a standalone copy).

**Files targeted:** `src/cpu/timebuf.hh` (a new private `zero()` used by `advance()`).
Patch: `docs/perf-opt/patches/t08-timebuf-chunked-zero.patch`.

- **What the binary showed:** `CPU::tick` went from 10 `rep stosq` to 5. The remaining
  five are the placement-new constructors. With one whole-slot memset in front of them,
  GCC had dropped their null stores as redundant. Behind chunked zeroing it kept them,
  and emitted the 128-byte `DynInstPtr` array as `rep stosq` with an alignment prologue.
  A mock of `FetchStruct` reproduces this outside gem5.

| Checkpoint | Paired reference KIPS (T7) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 759.5 | 749.1 | −1.37% | slower | +5.96% | 0.83% | yes |
| 706.stockfish_r.2.4 | 794.2 | 774.0 | −2.55% | slower (within noise) | +2.39% | 3.70% | yes |
| 708.sqlite_r.0.3 | 544.8 | 535.8 | −1.65% | slower (within noise) | +5.42% | 1.92% | yes |
| 723.llvm_r.1.0 | 395.5 | 399.5 | +1.02% | faster | +4.20% | 0.02% | yes |
| 753.ns3_r.2.0 | 458.1 | 462.5 | +0.96% | faster (within noise) | +10.43% | 2.21% | yes |

**Verdict: rejected.** Stats are bit-identical on 5/5, but only 2/5 are faster (−2.55% to
+1.02%).
- **Lesson:** a code-level change to a memset only moves the `rep stosq` elsewhere,
  because GCC re-derives memsets from zeroing code. The next trial changes GCC's
  expansion strategy instead.
- **Drift:** the T7 binary's paired reference run here measured 2–3% above its own run
  in Trial 7, which again shows why each trial reruns its reference.

### Trial 8b — expand small memsets as vector-store loops (build flag)

**Summary:** telling GCC to expand fixed-size memsets of up to 2 KB as plain vector-store
loops, instead of `rep stosq`, removes every `rep stosq` from `CPU::tick` and 99% of them
from the binary. It speeds up 4 of 5 checkpoints (−1.75% to +4.11%) with stats
bit-identical. **Accepted.** From here on, the flag is part of the evaluation recipe.

**Key idea:** Trial 8 showed that GCC re-derives memsets from zeroing code, so the
expansion strategy itself has to change. `-mmemset-strategy=vector_loop:2048:noalign,
libcall:-1:noalign` makes every fixed-size memset up to 2048 bytes a loop of SSE stores
with no alignment prologue, and anything larger a call to glibc's `memset`. The flag
changes only how memsets are emitted, never what they write, so it cannot change
results. It covers the time-buffer reset, the placement-new constructors that follow it,
and every other small memset in gem5 (packets, requests, zero-initialized structs).

**Files and flags targeted:** no source change. `CCFLAGS_EXTRA` and `LINKFLAGS_EXTRA`
both get the flag, because LTO generates code at link time. Trial 8's source change
was not kept.

```
MS='-mmemset-strategy=vector_loop:2048:noalign,libcall:-1:noalign'
CCFLAGS_EXTRA="-O3 $MS" LINKFLAGS_EXTRA="$MS" util/perf-opt/build.sh ARM_p2 fast --with-lto --linker=bfd
```

- **Build:** 260 s (full rebuild, since the flags changed). `.text` grew by 96 KB to
  30.02 MB.
- **`rep stosq`:** 0 in `CPU::tick` (10 before), and 36 in the whole binary (3323 in the
  Trial 7 binary).

| Checkpoint | Paired reference KIPS (T7) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 731.2 | 748.5 | +2.38% | faster | +5.88% | 0.83% | yes |
| 706.stockfish_r.2.4 | 791.7 | 777.8 | −1.75% | slower (within noise) | +2.89% | 3.70% | yes |
| 708.sqlite_r.0.3 | 518.6 | 537.9 | +3.74% | faster | +5.84% | 1.92% | yes |
| 723.llvm_r.1.0 | 385.0 | 400.8 | +4.11% | faster | +4.52% | 0.02% | yes |
| 753.ns3_r.2.0 | 441.1 | 443.2 | +0.49% | faster (within noise) | +5.83% | 2.21% | yes |

**Verdict: accepted.** Stats are bit-identical on 5/5 (the paired reference run too), and
4/5 are faster than the paired Trial 7 run.
- **Caveat:** two of the gains (+0.49% and the −1.75% loss) are inside the noise. The
  clear gains are on llvm and sqlite, the two checkpoints with the most
  memory-system activity per instruction.
- **For the kratos2 recipe:** add the same flag to `CCFLAGS_EXTRA` and `LINKFLAGS_EXTRA`.
  It is a generic x86-64 code-generation option, not tied to the host CPU.
- **Binary:** `build/ARM_p2/gem5.fast.t8b`, the reference for the next trial.

### Trial 9 — trim the per-cycle IQ and IEW scans

**Summary:** five small changes that each avoid a scan the issue queue or IEW repeats
every cycle or every dispatched instruction. Stats are bit-identical, but only 2 of 5
checkpoints got faster (−1.25% to +2.35%). **Rejected.**

**Key idea:** this fork's IQ is split into 9 `IQUnit`s with 9 FU pools, and several
loops visit all of them, or all 89 ready queues, on every cycle or dispatch. The deep dive
measured the scans at about 1.5% of region time. Each change gives identical results by
construction:
1. `InstructionQueue::isFull(inst)` stops at the first IQ with room, instead of summing
   free entries over all nine.
2. Only FU pools that queued a free are processed each cycle. `InstructionQueue` keeps
   the list, and a pool is on it exactly while its own list of units to free is not
   empty. `FUPool::takeOverFrom()` is empty, so the list is never cleared except by
   processing it.
3. `hasReadyInsts()` returns `!listOrder.empty()`. An op class is on `listOrder` exactly
   while its ready queue is non-empty: every push adds it, every pop that empties the
   queue removes it, and `resetState()` clears both.
4. The resident-ghost counts (always 0 here) are summed as integers and added to the
   floating-point stat once, which gives the same value as adding them per IQ.
5. `IssueStruct::insts` is removed. It was never written (only `size` is), so the
   squash-cleanup loop over it did nothing. `printAvailableInsts()`, whose only call was
   commented out, went with it.

**Files targeted:** `src/cpu/o3/{inst_queue.hh,inst_queue.cc,fu_pool.hh,iew.hh,iew.cc,comm.hh}`.
Patch: `docs/perf-opt/patches/t09-iq-iew-scans.patch`. Built in 74 s.

| Checkpoint | Paired reference KIPS (T8b) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 772.6 | 765.6 | −0.90% | slower | +8.30% | 0.83% | yes |
| 706.stockfish_r.2.4 | 806.0 | 795.9 | −1.25% | slower (within noise) | +5.29% | 3.70% | yes |
| 708.sqlite_r.0.3 | 554.8 | 559.2 | +0.80% | faster (within noise) | +10.02% | 1.92% | yes |
| 723.llvm_r.1.0 | 408.0 | 404.3 | −0.90% | slower | +5.44% | 0.02% | yes |
| 753.ns3_r.2.0 | 457.2 | 467.9 | +2.35% | faster | +11.72% | 2.21% | yes |

**Verdict: rejected.** Stats are bit-identical on 5/5, but only 2/5 are faster than the
paired Trial 8b run.
- **Why:** the expected gain (about 1%) is smaller than the run-to-run noise, and none of
  the five checkpoints moved beyond it. Either the scans are cheaper than the static
  estimate or the effect is simply unmeasurable with five single runs.
- **The code changes are sound** and make the scheduler easier to follow. They could
  be revisited together with other IQ work, where the combined effect would be larger.

### Trial 10 — allocation-free BTB search in the decoupled front end

**Summary:** the fetch-target search probes the BTB at every 4-byte address it scans.
Each probe copied the set's candidate vector and called a `std::function` per way to
compute the tag. A new `SimpleBTB::probe()` walks the set in place and computes the tag
once. All five checkpoints are faster (+1.4% to +6.7%) with stats bit-identical.
**Accepted.**

**Key idea:** `BAC::generateFetchTargets` calls `BPredUnit::BTBValid` at each
`minInstSize` step until it finds a branch or reaches the fetch-target width, then
`BTBGetInst` for the branch it found. Both went to `AssociativeCache::findEntry`, which
copies `getPossibleEntries()` (a `std::vector` returned by value) and calls
`BTBEntry::match()` per way; `match()` calls the entry's `std::function` tag extractor.
The deep dive counted 106.9M steps on llvm against 32.5M on stockfish, and put 79% of
`generateFetchTargets` self time in this search.
- **Why the result cannot change:** `probe()` visits the same set's entries in the same
  way order and returns the first match. It computes the tag with the same indexing
  policy that every entry's extractor wraps (`genTagExtractor`). Like `findEntry()`, it
  touches no replacement state and no stats. `lookup()` (which does touch and count) is
  unchanged. A BTB whose indexing policy is not `BTBSetAssociative` falls back to
  `findEntry()`.

**Files targeted:** `src/cpu/pred/btb_entry.hh` (`BTBSetAssociative::possibleEntries()`
returns the set by reference; `BTBEntry::matchTag()`), `src/cpu/pred/simple_btb.{hh,cc}`
(`probe()`, used by `valid()`, `getInst()` and `findEntry()`). Built in 74 s.

| Checkpoint | Paired reference KIPS (T8b) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 751.8 | 780.3 | +3.80% | faster | +10.38% | 0.83% | yes |
| 706.stockfish_r.2.4 | 800.1 | 811.2 | +1.38% | faster (within noise) | +7.31% | 3.70% | yes |
| 708.sqlite_r.0.3 | 541.2 | 559.9 | +3.45% | faster | +10.15% | 1.92% | yes |
| 723.llvm_r.1.0 | 396.0 | 422.7 | +6.73% | faster | +10.23% | 0.02% | yes |
| 753.ns3_r.2.0 | 446.9 | 454.4 | +1.68% | faster (within noise) | +8.51% | 2.21% | yes |

**Verdict: accepted.** Stats are bit-identical on 5/5 (the paired reference too), and all
five are faster, by +1.38% to +6.73%.
- **Matches the profile:** llvm, the checkpoint with 3.3× more search steps and the
  most mispredictions, gains the most (+6.7%). The deep dive estimated 1.5–2.3% for llvm,
  so the real cost of the vector copy and per-way `std::function` calls was higher than
  modeled.
- **Binary:** `build/ARM_p2/gem5.fast.t10`, the reference for Trial 11.

### Trial 11 — rename: cheaper `canRename` and a deque for the rename history

**Summary:** two rename-stage changes, bundled because each alone is below the
run-to-run noise. `canRename` stops copying the instruction pointer and skips register
classes the instruction writes nothing to. The rename history moves from a `std::list`
(one heap node per renamed register) to a `std::deque`. Four of five checkpoints are
faster (+1.6% to +2.8%) with stats bit-identical. **Accepted.**

**Key idea:**
- **`UnifiedRenameMap::canRename`** took its `DynInstPtr` by value (a reference-count
  round trip) and asked every register class's free list for its size, even for
  classes with zero destinations. It now takes a `const DynInstPtr &` and skips any
  class with `numDestRegs == 0`. Since `0 > n` is false for unsigned `n`, that returns
  the same answer.
- **`Rename::historyBuffer`** was a `std::list<RenameHistory>`: one allocation per renamed
  destination register and one free when it commits or squashes. It is now a
  `std::deque`, which allocates in 512-byte blocks. Entries only ever enter at the front
  and leave from either end.
- **Two loops rewritten, identical order:** `doSquash` and `removeFromHistory` used list
  iterators in ways a deque does not allow. `removeFromHistory` took `--end()` before
  checking for empty, and stepped past `begin()` to stop. Both now work from the ends
  (`front()`/`pop_front()` for squashes, `back()`/`pop_back()` for commits) and process
  exactly the same entries in the same order.

**Files targeted:** `src/cpu/o3/rename_map.{hh,cc}`, `src/cpu/o3/rename.{hh,cc}`. Built in
74 s.

| Checkpoint | Paired reference KIPS (T10) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 753.8 | 765.8 | +1.59% | faster | +8.32% | 0.83% | yes |
| 706.stockfish_r.2.4 | 780.7 | 796.2 | +1.98% | faster (within noise) | +5.33% | 3.70% | yes |
| 708.sqlite_r.0.3 | 537.2 | 548.4 | +2.09% | faster | +7.89% | 1.92% | yes |
| 723.llvm_r.1.0 | 405.6 | 417.0 | +2.83% | faster | +8.77% | 0.02% | yes |
| 753.ns3_r.2.0 | 452.5 | 450.5 | −0.44% | slower (within noise) | +7.56% | 2.21% | yes |

**Verdict: accepted.** Stats are bit-identical on 5/5 (the paired reference too), and 4/5
are faster than the paired Trial 10 run.
- **Drift again:** the T10 binary's reference run here was 2–4% slower than its own
  candidate run in Trial 10 (for example llvm 405.6 against 422.7). That is why the
  cumulative column (against the part-2 baseline mean) understates the chained gain.
- **Binary:** `build/ARM_p2/gem5.fast.t11`, the reference for Trial 12.

### Trial 12 — `DynInst` allocations: list-backed `instResult` and a scratch PC

**Summary:** two changes that remove heap allocations per instruction, bundled. The
`instResult` queue's default `std::deque` allocated two blocks per `DynInst` even though
nothing fills it without a checker CPU. `mispredicted()` cloned the PC on the heap for
every executed control instruction. Stats are bit-identical, but only 2 of 5 checkpoints
got faster (−2.0% to +0.75%). **Rejected.**

**Key idea:**
- **`instResult`:** `std::queue<InstResult>` defaults to a `std::deque`, whose
  constructor allocates its map and first block. `setResult()` only records when the
  `RecordResult` flag is set (for a checker), so in these runs the queue stays empty.
  Backing it with `std::list`, which allocates nothing until used, removes two
  allocations and two frees per `DynInst` (1.1–1.6 `DynInst`s per committed
  instruction).
- **`mispredicted()`:** a new overload takes a caller-owned scratch PC, kept in IEW (one
  per CPU, so it only ever holds this CPU's PC type). `set()` updates it in place.
  ARM's `PCState::update()` copies every field that a clone would, so the result is
  unchanged.

**Files targeted:** `src/cpu/o3/dyn_inst.hh`, `src/cpu/o3/iew.{hh,cc}`. Patch:
`docs/perf-opt/patches/t12-dyninst-allocs.patch`. Built in 74 s.

| Checkpoint | Paired reference KIPS (T11) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 770.6 | 775.2 | +0.60% | faster (within noise) | +9.65% | 0.83% | yes |
| 706.stockfish_r.2.4 | 826.4 | 811.5 | −1.80% | slower (within noise) | +7.36% | 3.70% | yes |
| 708.sqlite_r.0.3 | 554.4 | 550.3 | −0.74% | slower (within noise) | +8.27% | 1.92% | yes |
| 723.llvm_r.1.0 | 425.7 | 428.9 | +0.75% | faster | +11.86% | 0.02% | yes |
| 753.ns3_r.2.0 | 473.1 | 463.7 | −2.00% | slower (within noise) | +10.71% | 2.21% | yes |

**Verdict: rejected.** Stats are bit-identical on 5/5, but only 2/5 are faster than the
paired Trial 11 run.
- **Why:** removing about four small allocations per instruction (roughly 20 host cycles
  each, against 15–28 K host instructions per simulated instruction) is worth well
  under 1%, and every change is inside the noise.
- **Lesson:** the deep dive's allocator estimates were already rescaled down once. With
  this protocol, allocation-only changes need to remove much more than a few
  allocations per instruction to be measurable.

### Trial 13 — set-associative lookups without copying the set

**Summary:** every lookup in a set-associative cache, TLB or predictor table copied its
set's candidate vector (a heap allocation), and cache lookups also called a
`std::function` per way to compute the tag. A new `possibleEntriesInPlace()` hands out
the set in place, and cache lookups compute the tag once. Stats are bit-identical, and 3
of 5 checkpoints are faster: the three memory-heavier ones. **Accepted, narrowly.**

**Key idea:** `IndexingPolicyTemplate::getPossibleEntries()` returns a
`std::vector<ReplaceableEntry*>` by value, and the hot users (`BaseTags::findBlock` for
every cache access and prefetcher probe, `AssociativeCache::findEntry` for prefetcher
tables, `ArmISA::TLB::Table::findEntry` for every TLB lookup) iterate over that copy.
- **New virtual accessor:** `possibleEntriesInPlace()` returns a pointer to the same
  vector, or `nullptr` if a policy computes its candidates. The default is `nullptr`,
  and the users then keep the copying path. The policies that store their sets override
  it: `SetAssociative`, `TaggedSetAssociative`, `TLBSetAssociative` and
  `BTBSetAssociative`. The entries and their order are unchanged.
- **Tag computed once:** `BaseTags::findBlock` computes the tag once with the indexing
  policy and compares it with a new `TaggedEntry::matchTag()`. `BaseSetAssoc`
  registers every block with `genTagExtractor(indexingPolicy)`, so each block's
  extractor returns exactly this value. `SectorTags` and `FALRU` have their own
  `findBlock` and are unaffected.
- **Victim selection too:** `AssociativeCache::findVictim` passes the in-place set to
  `getVictim()`, which takes the candidates by const reference.

**Files targeted:** `src/mem/cache/tags/indexing_policies/{base.hh,set_associative.hh,set_associative.cc}`,
`src/mem/cache/tags/{tagged_entry.hh,base.cc}`, `src/base/cache/associative_cache.hh`,
`src/arch/arm/{pagetable.hh,tlb.cc}`, `src/cpu/pred/btb_entry.hh`. Built in 122 s.

| Checkpoint | Paired reference KIPS (T11) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 795.0 | 778.1 | −2.13% | slower | +10.06% | 0.83% | yes |
| 706.stockfish_r.2.4 | 815.8 | 808.5 | −0.89% | slower (within noise) | +6.96% | 3.70% | yes |
| 708.sqlite_r.0.3 | 564.2 | 572.4 | +1.45% | faster (within noise) | +12.62% | 1.92% | yes |
| 723.llvm_r.1.0 | 420.1 | 431.3 | +2.68% | faster | +12.49% | 0.02% | yes |
| 753.ns3_r.2.0 | 462.2 | 465.0 | +0.61% | faster (within noise) | +11.04% | 2.21% | yes |

**Verdict: accepted by the rule.** Stats are bit-identical on 5/5, and 3/5 are faster
than the paired Trial 11 run. This is the minimum majority.
- **The split fits the change:** llvm, sqlite and ns3 make 0.48–0.89 instruction-TLB
  lookups per instruction (much of it fetch-directed prefetching) against 0.14–0.17
  for stockfish. They also make 1.2–1.6× more data-TLB and L1D lookups per
  instruction (from `trial1-fast` stats), and they are the three that got faster. The stockfish losses (−2.1%, −0.9%) are about the size of the noise.
  The mean over all five is +0.34%.
- **Binary:** `build/ARM_p2/gem5.fast.t13`, the reference for Trial 14.

### Trial 14 — LSQ: reference accessors, one allocation per request, hoisted forwarding scan

**Summary:** three changes to the load/store queue, bundled. The request accessors return
references instead of `shared_ptr` copies. Each `Request` is allocated together with its
reference count. The store-to-load forwarding scan reads the load's address range once.
All five checkpoints are faster (+0.7% to +5.5%) with stats bit-identical. **Accepted.**

**Key idea:**
- **Reference accessors:** `LSQRequest::req()` and `mainReq()` returned `RequestPtr`, a
  `std::shared_ptr<Request>`, by value. gem5 links pthreads, so every copy is an atomic
  increment plus an atomic decrement. `mainReq()` has about 39 call sites, several per
  memory access, and some inside the forwarding scan's per-store loop. Both now return
  `const RequestPtr &`, and `SplitDataRequest::mainReq()` returns its member. The one
  call site that binds the result to a reference uses it immediately.
- **One allocation per request:** `LSQRequest::addReq()` did `new Request(...)` and
  `_reqs.emplace_back(req)`, which allocates the `shared_ptr` control block
  separately. `std::make_shared<Request>` does both in one allocation. The local
  accessor lambda now captures `req.get()`, the same raw pointer as before.
- **Hoisted forwarding scan:** `LSQUnit::read()` recomputed the load's `getVaddr()`,
  `getSize()` and `isLLSC()` through `mainReq()` for every older store it scanned. They
  are read once before the scan, and only when the scan will run. Nothing in the loop
  changes the request before it returns.

**Files targeted:** `src/cpu/o3/lsq.{hh,cc}`, `src/cpu/o3/lsq_unit.cc`. Built in 85 s.

| Checkpoint | Paired reference KIPS (T13) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 759.6 | 776.1 | +2.17% | faster | +9.78% | 0.83% | yes |
| 706.stockfish_r.2.4 | 787.4 | 809.6 | +2.82% | faster (within noise) | +7.11% | 3.70% | yes |
| 708.sqlite_r.0.3 | 537.9 | 567.5 | +5.49% | faster | +11.65% | 1.92% | yes |
| 723.llvm_r.1.0 | 424.2 | 429.0 | +1.14% | faster | +11.89% | 0.02% | yes |
| 753.ns3_r.2.0 | 450.4 | 453.4 | +0.67% | faster (within noise) | +8.27% | 2.21% | yes |

**Verdict: accepted.** Stats are bit-identical on 5/5 (the paired reference too), and all
five are faster than the paired Trial 13 run, by +0.67% to +5.49%.
- **Larger than estimated:** the deep dive put these items at 0.4–1.3%. The atomic
  reference-count traffic was not in its allocator model, which counted only
  allocations and frees.
- **Binary:** `build/ARM_p2/gem5.fast.t14`, the reference for Trial 15.

### Trial 15 — reuse the hit block in the prefetcher's probe

**Summary:** on a cache hit, the prefetcher's `probeNotify` repeated the tag lookup that
`access()` had just done, to ask whether the block was prefetched. Passing the found
block along with the probe removes that lookup. Stats are bit-identical, but only 1 of 5
checkpoints got faster. **Rejected.**

**Key idea:** `CacheAccessProbeArg` gains an optional `CacheBlk *blk`, which
`BaseCache::recvTimingReq` sets on the `ppHit` notification. `prefetch::Base::probeNotify`
checks it with `blk->match()` and, if it matches, answers `hasBeenPrefetched` from it
directly. A set never holds two blocks with the same tag, so the result is the one the
lookup would return. `ppHit` fires before the block's prefetched flag is cleared, as
before. Misses and fills keep the full lookup.

**Files targeted:** `src/mem/cache/{cache_probe_arg.hh,base.cc}`,
`src/mem/cache/prefetch/base.cc`. Patch: `docs/perf-opt/patches/t15-probe-hint.patch`.
Built in 80 s.

| Checkpoint | Paired reference KIPS (T14) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 784.3 | 776.4 | −1.01% | slower | +9.82% | 0.83% | yes |
| 706.stockfish_r.2.4 | 821.3 | 814.7 | −0.80% | slower (within noise) | +7.78% | 3.70% | yes |
| 708.sqlite_r.0.3 | 555.9 | 567.5 | +2.08% | faster | +11.65% | 1.92% | yes |
| 723.llvm_r.1.0 | 427.0 | 417.2 | −2.29% | slower | +8.81% | 0.02% | yes |
| 753.ns3_r.2.0 | 465.2 | 457.0 | −1.76% | slower (within noise) | +9.12% | 2.21% | yes |

**Verdict: rejected.** Stats are bit-identical on 5/5, but only 1/5 is faster than the
paired Trial 14 run.
- **Why:** after Trial 13, a tag lookup no longer copies the set and computes its tag
  once, so the saved lookup is cheap. The deep dive expected this, putting the gain at
  0.3–0.5% after Trial 13 (from 0.9–1.3% before it).

### Trial 16 — call shared-library functions without PLT stubs (`-fno-plt`)

**Summary:** compiling with `-fno-plt` makes calls into shared libraries (tcmalloc's
`new`/`delete`, libstdc++'s list hooks) go through the GOT directly instead of through
PLT stubs. Stats are bit-identical, but every checkpoint moved by less than ±1.1%, and
only 2 of 5 were faster. **Rejected.**

**Key idea:** the profile put the PLT stubs at 1.7% of self time, since tcmalloc is a
shared library and gem5 allocates and frees constantly. `-fno-plt` replaces each
`call foo@plt` with `call *foo@GOTPCREL(%rip)`, which removes a jump per call.

**Files and flags targeted:** no source change. `-fno-plt` is added to `CCFLAGS_EXTRA`
and `LINKFLAGS_EXTRA`, on top of the Trial 8b recipe. Built in 250 s (full rebuild).
- **Effect on the binary:** PLT calls went from 241,734 to 1, and `.text` grew by
  400 KB to 30.42 MB, since each indirect call is a byte longer.

| Checkpoint | Paired reference KIPS (T14) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 791.7 | 790.4 | −0.17% | slower (within noise) | +11.81% | 0.83% | yes |
| 706.stockfish_r.2.4 | 830.7 | 836.9 | +0.76% | faster (within noise) | +10.72% | 3.70% | yes |
| 708.sqlite_r.0.3 | 573.8 | 572.7 | −0.19% | slower (within noise) | +12.67% | 1.92% | yes |
| 723.llvm_r.1.0 | 436.0 | 436.5 | +0.12% | faster | +13.84% | 0.02% | yes |
| 753.ns3_r.2.0 | 471.5 | 466.6 | −1.04% | slower (within noise) | +11.41% | 2.21% | yes |

**Verdict: rejected; no effect.** Stats are bit-identical on 5/5, and only 2/5 are faster.
All five changes are within ±1.04%.
- **Why:** a PLT stub is an indirect jump that the branch predictor learns, so on a
  modern core the stub costs about as much as the GOT-indirect call that replaces it.
  The 400 KB of extra code also works against a front-end-bound binary. The 1.7% of
  self time the profile gave the stubs mostly measures how often the allocator runs,
  not what the stub adds.

### Trial 17 — search a whole fetch-target window in one BTB call

**Summary:** a follow-up to Trial 10. The fetch-target search now asks the BTB once per
fetch target for the first branch in its window, instead of making one virtual call per
4-byte step and then looking the branch up again for its instruction. Stats are
bit-identical, and 4 of 5 checkpoints are faster. **Accepted by the rule, with a caveat
about noise.**

**Key idea:** `BranchTargetBuffer::findFirstBranch(tid, start, width, step, addr, inst)`
scans `start, start + step, …` up to and including the first address at least `width`
bytes past `start`, which is exactly the old loop's stop rule. It returns whether a
branch was found, its address, and its static instruction. The base class implements it
with `valid()` and `getInst()`, so other BTBs behave as before. `SimpleBTB` overrides it
with one `probe()` per address. `BAC::generateFetchTargets` calls it through a new
`BPredUnit::BTBFindFirstBranch` and no longer calls `BTBGetInst` for the branch it found.
Neither path touches replacement state or stats.

**Files targeted:** `src/cpu/pred/{btb.hh,simple_btb.hh,simple_btb.cc,bpred_unit.hh}`,
`src/cpu/o3/bac.cc`. Built in 259 s: the previous build used Trial 16's flags, so this
one recompiled everything.

| Checkpoint | Paired reference KIPS (T14) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 786.4 | 793.7 | +0.93% | faster | +12.26% | 0.83% | yes |
| 706.stockfish_r.2.4 | 841.6 | 827.8 | −1.65% | slower (within noise) | +9.50% | 3.70% | yes |
| 708.sqlite_r.0.3 | 583.5 | 590.2 | +1.15% | faster (within noise) | +16.12% | 1.92% | yes |
| 723.llvm_r.1.0 | 422.9 | 423.9 | +0.24% | faster | +10.56% | 0.02% | yes |
| 753.ns3_r.2.0 | 467.0 | 489.5 | +4.81% | faster | +16.88% | 2.21% | yes |

**Verdict: accepted by the rule.** Stats are bit-identical on 5/5 (the paired reference
too), and 4/5 are faster than the paired Trial 14 run.
- **Caveat:** the pattern does not match the mechanism. llvm scans about 3× more
  addresses per instruction than the others and should gain most, yet it moved only
  +0.24%, while ns3 moved +4.81%. The real effect is probably small (about 0.5–1%), and
  this result owes something to noise. The change is kept because it met the rule, it
  is correct by construction, and it simplifies the search loop.
- **Binary:** `build/ARM_p2/gem5.fast.t17`, the current best.

### Trial 18 — front-end bundle: FTQ reference counts, next-PC scratch, BTB tag mirror

**Summary:** three front-end changes, bundled. The fetch-target queue stops copying
`shared_ptr`s. BAC reuses one next-PC object per thread instead of cloning a PC per
fetch target. The BTB keeps a packed copy of every slot's valid bit, thread and tag, so
the window search reads one word per way instead of a 100-byte entry. Four of five
checkpoints are faster, llvm the most (+5.6%), and stats are bit-identical.
**Accepted.**

**Key idea:**
- **FTQ:** `FetchTargetPtr` is a `std::shared_ptr`, so every copy is an atomic
  increment and decrement (the lesson of Trial 14). `FTQ::insert()` took it by value,
  and `squash()` and `squashSanityCheck()` copied every queued target in their loops.
  They now use references. `readHead()` keeps returning a copy, because fetch keeps
  using the fetch target after popping it.
- **BAC:** `generateFetchTargets()` cloned the current PC on the heap for every fetch
  target (`next_pc`). It now updates a per-thread `nextFTPC` object with `set()`, which
  copies every field. `finalize()` and `predict()` copy from it and keep no pointer to
  it. The history record's target no longer goes through a throwaway clone
  (`set(hist->target, pc)` instead of `set(hist->target, unique_ptr(pc.clone()))`).
- **BTB tag mirror:** `SimpleBTB` keeps `tagMirror`, one `uint64_t` per slot in set-major
  order. A valid slot holds `1<<63 | tid<<47 | tag`; an invalid one holds 0.
  `probe()` compares the wanted key against the set's six words and touches the
  `BTBEntry` only on a hit. A slot equals the key exactly when `matchTag()` would be
  true. `update()` (the only insertion path, right after `insertEntry()`) and
  `memInvalidate()` (the only clearing path) keep it in step. It is enabled only when
  tags fit in 47 bits (`tag_bits = 18` here). Otherwise the Trial 13 path is used.
  With 12288 entries the mirror is 96 KB, against about 1.2 MB of `BTBEntry` objects.

**Files targeted:** `src/cpu/o3/{ftq.hh,ftq.cc,bac.hh,bac.cc}`,
`src/cpu/pred/{btb_entry.hh,simple_btb.hh,simple_btb.cc}`. Built in 86 s.

| Checkpoint | Paired reference KIPS (T17) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 787.5 | 782.5 | −0.64% | slower (within noise) | +10.68% | 0.83% | yes |
| 706.stockfish_r.2.4 | 808.4 | 818.0 | +1.18% | faster (within noise) | +8.21% | 3.70% | yes |
| 708.sqlite_r.0.3 | 569.1 | 585.1 | +2.81% | faster | +15.11% | 1.92% | yes |
| 723.llvm_r.1.0 | 412.9 | 436.0 | +5.61% | faster | +13.72% | 0.02% | yes |
| 753.ns3_r.2.0 | 455.0 | 468.5 | +2.97% | faster | +11.86% | 2.21% | yes |

**Verdict: accepted.** Stats are bit-identical on 5/5 (the paired reference too), and 4/5
are faster than the paired Trial 17 run.
- **The pattern fits the mechanism:** llvm, whose instruction footprint makes the BTB
  search walk the most sets, gains the most (+5.6%). The two stockfish checkpoints, with
  small hot loops whose BTB sets stay cached, are flat. The deep dive estimated the tag
  mirror alone at +0.4–1.0% on llvm; the combined effect is larger.
- **Binary:** `build/ARM_p2/gem5.fast.t18`, the current best.

### Trial 19 — build with `MaxWidth = 8`, `MaxThreads = 1`

**Summary:** after Trials 7 and 8b, what is left of `CPU::tick`'s own time is upkeep of
the inter-stage time buffers, and their size is set by `MaxWidth = 16` and
`MaxThreads = 4`. This configuration uses at most 8-wide stages and one thread. A build
with the bounds lowered to 8 and 1 is faster on all five checkpoints (+0.1% to +4.7%),
but it **changes simulation results**: about 2,000 stats differ on every checkpoint.
**Rejected.**

**Key idea:** `src/cpu/o3/limits.hh` took the two bounds from build macros
(`-DGEM5_O3_MAX_WIDTH=8 -DGEM5_O3_MAX_THREADS=1`), defaulting to 16 and 4. Every stage
checks its width against `MaxWidth` and `fatal()`s if it is exceeded, as does the
thread count against `MaxThreads`. Every other use of the two constants was checked
before the trial:
- **Array bounds:** most uses size per-cycle arrays.
- **Loops over thread slots:** several loops walk `MaxThreads` slots, including unused
  ones.
- **One name:** `LSQUnit::name()` prints `iew.lsq` instead of `iew.lsq.thread0` when
  `MaxThreads == 1`. That name reaches only debug and trace messages; stats are named
  `lsq0` by their stat group.

No code path uses either constant as a value that should change a single-thread,
8-wide simulation. The gate was expected to pass.

**Files and flags targeted:** `src/cpu/o3/limits.hh`, plus the two `-D` flags in
`CCFLAGS_EXTRA`. Patch: `docs/perf-opt/patches/t19-maxwidth-limits.patch`. Built in
249 s (full rebuild); `.text` shrank by 18 KB.

| Checkpoint | Paired reference KIPS (T18) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 779.8 | 816.4 | +4.70% | faster | +15.49% | 0.83% | NO |
| 706.stockfish_r.2.4 | 806.8 | 842.9 | +4.48% | faster | +11.51% | 3.70% | NO |
| 708.sqlite_r.0.3 | 574.8 | 586.1 | +1.97% | faster | +15.32% | 1.92% | NO |
| 723.llvm_r.1.0 | 434.7 | 435.2 | +0.10% | faster | +13.50% | 0.02% | NO |
| 753.ns3_r.2.0 | 480.4 | 500.7 | +4.23% | faster | +19.55% | 2.21% | NO |

Differing stats per checkpoint: 2177, 1958, 2127, 2403, 1910. They include `simTicks`,
L1D hits and misses, and on two checkpoints `simInsts` and `simOps` (the stop point
moves by one instruction).

**Verdict: rejected; simulation results change.** The paired reference run (the T18
binary) is identical to `trial1-fast`, as always.
- **This is a correctness finding, not a performance one.** For a configuration whose
  widths and thread count are within both sets of bounds, the two builds should
  simulate the same machine. They do not, by the same order of magnitude (about 2,000
  stats) as Trial 5b's `-march=x86-64-v3` build.
- **The likeliest cause** is the same in both cases: simulated behavior depends on
  memory whose contents the program never set, and which changes when code generation
  or object layout changes. The known instance is `LoopPredictor::BranchInfo::loopPredUsed`
  (Trial 5b), read on every prediction without being initialized. There may be others.
  Until this is found, **any change to object sizes or memory layout can change
  results**, and the gate will reject it even when it is correct.

### Trial 20 — pooled allocation for per-instruction objects

**Summary:** a small base class, `PooledNew<T>`, gives a class its own `operator new`
and `delete` that recycle freed objects through a per-thread free list. Applied to four
classes created and destroyed per instruction or per branch, it keeps stats
bit-identical and makes 3 of 5 checkpoints faster. **Accepted by the rule, narrowly.**

**Key idea:** tcmalloc's fast path is already a free list, but it takes about 20 host
cycles per allocate/free pair against a handful for a class-specific list. Only where
memory comes from changes; constructors, destructors and object lifetimes are exactly
as before, so behavior cannot change. Pooled classes:
- `ArmISA::PCState`, which the CPU clones several times per instruction (DynInst PCs,
  fetch-target PCs, BPU history targets).
- `o3::DependencyEntry`, about one per register dependence.
- `BPredUnit::PredictorHistory`, one per predicted branch.
- `o3::InstructionQueue::FUCompletion`, one event per multi-cycle operation.

Objects of a derived class with a different size fall back to the global heap. The
free list is `thread_local`.

**Files targeted:** `src/base/pooled_new.hh` (new), `src/arch/arm/pcstate.hh`,
`src/cpu/o3/{dep_graph.hh,inst_queue.hh}`, `src/cpu/pred/bpred_unit.hh`. Built in 249 s.

| Checkpoint | Paired reference KIPS (T18) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 794.4 | 807.8 | +1.69% | faster | +14.26% | 0.83% | yes |
| 706.stockfish_r.2.4 | 817.4 | 861.3 | +5.37% | faster | +13.95% | 3.70% | yes |
| 708.sqlite_r.0.3 | 575.0 | 600.9 | +4.51% | faster | +18.22% | 1.92% | yes |
| 723.llvm_r.1.0 | 444.2 | 434.1 | −2.26% | slower | +13.22% | 0.02% | yes |
| 753.ns3_r.2.0 | 500.7 | 484.8 | −3.18% | slower | +15.76% | 2.21% | yes |

**Verdict: accepted by the rule.** Stats are bit-identical on 5/5, and 3/5 are faster than
the paired Trial 18 run. The mean over all five is +1.2%, with swings in both directions
larger than the effect, so this is a small gain measured with a lot of noise.
- **Evidence for Trial 19:** pooling changes where tens of millions of heap objects
  live, and results stayed bit-identical, as they did for the allocation changes of
  Trials 12 and 14. So the layout-dependent behavior of Trials 5b and 19 does not follow
  heap allocation in general.
- **Binary:** `build/ARM_p2/gem5.fast.t20`, the current best.

### Diagnostics — why do Trials 5b and 19 change results?

These are not optimization trials. Each tests one hypothesis for the result changes of
Trial 5b (`-march=x86-64-v3`) and Trial 19 (`MaxWidth = 8`, `MaxThreads = 1`), using
compiler or allocator settings only; no source was changed for them. Each was built in
its own build directory from the Trial 20 sources, run once on the test suite, and
compared with `trial1-fast`.

| Diagnostic | What it changes | Result vs `trial1-fast` |
|---|---|---|
| `-ftrivial-auto-var-init=pattern` (build dir `ARM_diag`) | every uninitialized stack variable starts as a fixed garbage pattern | bit-identical on 5/5 |
| glibc malloc instead of tcmalloc (`--without-tcmalloc`, `ARM_diag2`) | heap allocator and heap layout | bit-identical on 5/5 |
| glibc malloc with `MALLOC_PERTURB_=165` | every new heap allocation starts filled with a garbage byte | 52–55 stats differ per checkpoint, all branch-predictor bookkeeping |

**What this shows:**
- **No uninitialized stack read matters:** filling every automatic variable with a
  pattern changes nothing.
- **Heap placement does not matter:** a different allocator (glibc), and pooling in
  Trial 20, keep results identical.
- **The uninitialized heap read is confirmed and is in the loop predictor.** Under
  `MALLOC_PERTURB_`, `loop_predictor.used` goes from 0 to 228,618 on llvm (and from
  2,646 to 102,856 on stockfish), and the TAGE provider counters (`longestMatchProvider`,
  `altMatchProvider`, …) shift. That is `LoopPredictor::BranchInfo::loopPredUsed` read
  uninitialized: garbage makes it look "used", which relabels the provider as LOOP
  (`tage_sc_l.cc:419`). With tcmalloc or unperturbed glibc the garbage happens to be 0.
- **But that read does not change timing.** `simTicks`, instruction counts and every
  cache and pipeline stat stay identical under `MALLOC_PERTURB_`. So `loopPredUsed` is a
  real bug in the loop predictor's statistics, but **not** the cause of the ~2,000-stat
  timing changes in Trials 5b and 19.
- **Still unexplained:** what makes Trial 19's width and thread bounds, and Trial 5b's
  code generation, change timing. Remaining candidates:
  - behavior that depends on the relative order of object addresses, such as iteration
    over containers keyed by pointer (address randomization shifts all addresses
    together and keeps their order);
  - a real semantic dependence on `MaxWidth` or `MaxThreads` that the code audit
    missed;
  - for Trial 5b only, floating-point or other code-generation-dependent arithmetic.

  Building with only one of the two bounds lowered would tell which of them matters.

### Trial 21 — pooled nodes for the pipeline's instruction lists

**Summary:** every in-flight instruction sits in several `std::list<DynInstPtr>`: the
CPU's instruction list, the ROB, the IQ and the memory-dependence unit. Each insertion
allocated a list node and each removal freed one. A pooling allocator recycles the nodes
instead. Four of five checkpoints are faster (+2.2% to +3.8%), with stats bit-identical.
**Accepted.**

**Key idea:** `PooledAllocator<T>` (next to `PooledNew` in `src/base/pooled_new.hh`) is a
standard allocator that serves single-element allocations, such as list nodes, from a
per-thread free list. All instances compare equal, so containers splice and swap as with
`std::allocator`. A new alias, `o3::DynInstList = std::list<DynInstPtr,
PooledAllocator<DynInstPtr>>`, replaces `std::list<DynInstPtr>` everywhere in the O3
CPU. Element order, iterator behavior and contents are unchanged; only where nodes come
from differs. The bundle also makes `CommitCPUStats::updateComCtrlStats` take its
`StaticInstPtr` by reference, which avoids a reference-count round trip per committed
control instruction.

**Files targeted:** `src/base/pooled_new.hh`, `src/cpu/o3/{dyn_inst_ptr.hh,dyn_inst.hh,cpu.hh,rob.hh,inst_queue.hh,mem_dep_unit.hh}`,
`src/cpu/base.{hh,cc}`. Built in 114 s.

| Checkpoint | Paired reference KIPS (T20) | New KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 798.3 | 828.7 | +3.80% | faster | +17.22% | 0.83% | yes |
| 706.stockfish_r.2.4 | 843.7 | 869.8 | +3.09% | faster (within noise) | +15.07% | 3.70% | yes |
| 708.sqlite_r.0.3 | 581.1 | 601.7 | +3.55% | faster | +18.38% | 1.92% | yes |
| 723.llvm_r.1.0 | 447.9 | 446.3 | −0.35% | slower | +16.40% | 0.02% | yes |
| 753.ns3_r.2.0 | 480.2 | 490.9 | +2.21% | faster (within noise) | +17.20% | 2.21% | yes |

**Verdict: accepted.** Stats are bit-identical on 5/5 (the paired reference too), and 4/5
are faster than the paired Trial 20 run.
- **Measurement note:** the reference run started on a machine that had been idle for
  about 20 minutes (load 0.07). A wait loop in the harness command had hung, since it
  matched its own command line, so no trial ran in that time. The candidate started at
  load 0.93, after the usual 60 s wait.
- **Binary:** `build/ARM_p2/gem5.fast.t21`, the current best.

### Fix — initialize `LoopPredictor::BranchInfo::loopPredUsed` (user approved)

**Summary:** the loop predictor's `BranchInfo` constructor initialized every member except
`loopPredUsed`, which is only ever set to `true` (when the loop predictor overrides
TAGE, `loop_predictor.cc:298`) and is read on every prediction. It now starts as `false`.
This is a correctness fix, not an optimization, approved by the user although it is
inside TAGE-SC-L.

**What the flag drives:** `tage_sc_l.cc:419` (provider relabelled as LOOP),
`LoopPredictor::updateStats` (`loop_predictor.used/correct/wrong`) and `ltage.cc:99`. The
diagnostics above showed that garbage in it changes these branch-predictor statistics
(on llvm, `loop_predictor.used` went from 0 to 228,618 under `MALLOC_PERTURB_`) but not
timing.

**Files targeted:** `src/cpu/pred/loop_predictor.hh`. `makeBranchInfo()` (`new BranchInfo()`)
is the only place a `BranchInfo` is created, and nothing derives from it.

**Verification:**

| Run | Result vs `trial1-fast` |
|---|---|
| Fixed build, part-2 recipe (tcmalloc), run `lpfix` | bit-identical on 5/5 |
| Fixed build, glibc malloc with `MALLOC_PERTURB_=165`, run `lpfix-perturb` | bit-identical on 5/5 (the unfixed build differed in 52–55 stats) |

- **No baseline changes:** with tcmalloc the uninitialized byte happened to read as 0, so
  no existing result changes, and every part-2 trial stays valid.
- **The dependence is gone:** with the heap deliberately filled with garbage, the stats
  are now stable.

### PGO retrained on the part-2 code

**Summary:** the campaign stopped after Trial 21 (user decision). PGO was then retrained
on the final part-2 sources with the part-2 recipe. On top of Trial 21 it is faster on
all five checkpoints, by +11.2% to +19.3%, with stats bit-identical. As in part 1, PGO is
for bulk-run binaries only (user decision, 2026-09-27).

**Recipe:** the Trial 6 procedure, with the part-2 flags, in its own build dir `ARM_p2pgo`:
1. **Instrumented build:** 422 s; 751 MB binary, 74.4 MB `.text`.

   ```
   MS='-mmemset-strategy=vector_loop:2048:noalign,libcall:-1:noalign'
   CCFLAGS_EXTRA="-O3 $MS -fprofile-generate" LINKFLAGS_EXTRA="$MS -fprofile-generate" \
       util/perf-opt/build.sh ARM_p2pgo fast --with-lto --linker=bfd
   ```

2. **Training:** `run_suite.sh build/ARM_p2pgo/gem5.fast p2-pgo-train train`, on the same
   three SPEC training checkpoints as Trial 6 (never used for evaluation). It wrote 2034
   `.gcda` files. Instrumented speed: gcc 199.2, flightdm 253.5, nest 423.9 KIPS.
3. **Optimized build:** 255 s. No profile-mismatch warnings and no gcov symbols. 73.3 MB
   binary, 34.95 MB `.text`.

   ```
   CCFLAGS_EXTRA="-O3 $MS -fprofile-use -fprofile-partial-training -Wno-missing-profile" \
       LINKFLAGS_EXTRA="$MS -fprofile-use -fprofile-partial-training" \
       util/perf-opt/build.sh ARM_p2pgo fast --with-lto --linker=bfd
   ```

| Checkpoint | Paired reference KIPS (T21) | PGO KIPS | Change | Direction | Cumulative vs part-2 baseline | Baseline noise | Stats identical |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 789.5 | 931.2 | +17.94% | faster | +31.71% | 0.83% | yes |
| 706.stockfish_r.2.4 | 811.9 | 968.6 | +19.31% | faster | +28.14% | 3.70% | yes |
| 708.sqlite_r.0.3 | 571.3 | 659.5 | +15.43% | faster | +29.75% | 1.92% | yes |
| 723.llvm_r.1.0 | 426.1 | 489.2 | +14.81% | faster | +27.60% | 0.02% | yes |
| 753.ns3_r.2.0 | 484.6 | 538.7 | +11.17% | faster | +28.64% | 2.21% | yes |

- **Larger than in part 1** (+8.1% to +11.3% on the Trial 4 code). Not investigated. A
  plausible reason: the part-2 changes made hot paths inlinable (for example the
  `RefCountingPtr` release and the BTB probe), which gives profile-driven inlining and
  layout more to work with.
- **Binary:** `build/ARM_p2pgo/gem5.fast.pgo` (local, SPEC-trained). The bulk-run binary
  on kratos2 must be retrained there: profiles are tied to the compiler (g++ 12.1 on the
  cluster), and bulk runs are agentic.

## Part 2 summary

The campaign stopped after Trial 21, at the user's decision. The remaining targets were
each estimated below 1%, under the per-trial noise floor. PGO was then retrained on the
final code, and the `loopPredUsed` fix was applied.

| Trial | Change | Verdict | Paired effect (faster / 5) |
|---|---|---|---|
| 7 | Inline the `RefCountingPtr` release fast path | accepted | +2.8 … +6.5% (5/5) |
| 8 | Chunked time-buffer zeroing | rejected: not faster | −2.6 … +1.0% (2/5) |
| 8b | `-mmemset-strategy=vector_loop:2048:noalign,libcall:-1:noalign` | accepted | −1.8 … +4.1% (4/5) |
| 9 | Trim per-cycle IQ/IEW scans | rejected: not faster | −1.3 … +2.4% (2/5) |
| 10 | Allocation-free BTB search | accepted | +1.4 … +6.7% (5/5) |
| 11 | Rename: `canRename` + history deque | accepted | −0.4 … +2.8% (4/5) |
| 12 | `DynInst` allocations (`instResult`, scratch PC) | rejected: not faster | −2.0 … +0.8% (2/5) |
| 13 | Set-associative lookups without copying | accepted, narrowly | −2.1 … +2.7% (3/5) |
| 14 | LSQ: reference accessors, `make_shared`, hoisted scan | accepted | +0.7 … +5.5% (5/5) |
| 15 | Reuse the hit block in the prefetcher probe | rejected: not faster | −2.3 … +2.1% (1/5) |
| 16 | `-fno-plt` | rejected: no effect | −1.0 … +0.8% (2/5) |
| 17 | BTB window search in one call | accepted (noisy) | −1.7 … +4.8% (4/5) |
| 18 | FTQ refcounts, next-PC scratch, BTB tag mirror | accepted | −0.6 … +5.6% (4/5) |
| 19 | `MaxWidth = 8`, `MaxThreads = 1` build | rejected: **changes results** | +0.1 … +4.7% (5/5), ~2,000 stats differ |
| 20 | `PooledNew` for per-instruction objects | accepted, narrowly | −3.2 … +5.4% (3/5) |
| 21 | Pooled nodes for the instruction lists | accepted | −0.4 … +3.8% (4/5) |
| fix | Initialize `loopPredUsed` | applied (correctness) | results unchanged |
| PGO | PGO retrained on the part-2 code (SPEC-trained) | bulk runs only | +11.2 … +19.3% (5/5) |

**End-to-end result.** The part-2 baseline binary, the final development binary (Trial 21
plus the fix) and the PGO binary were run back to back, each after the quiet-machine
wait. All three are bit-identical to `trial1-fast`.

| Checkpoint | Part-2 baseline KIPS | Final development KIPS | Change | Final PGO KIPS | Change |
|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 689.6 | 818.2 | +18.7% | 957.5 | +38.8% |
| 706.stockfish_r.2.4 | 723.2 | 859.0 | +18.8% | 1023.7 | +41.6% |
| 708.sqlite_r.0.3 | 515.3 | 603.0 | +17.0% | 676.3 | +31.2% |
| 723.llvm_r.1.0 | 383.2 | 445.3 | +16.2% | 514.7 | +34.3% |
| 753.ns3_r.2.0 | 425.4 | 491.8 | +15.6% | 569.5 | +33.9% |
| **Geomean** | | | **+17.3%** | | **+35.9%** |

- **Part 2 total:** the code changes make the development build **17.3% faster** (15.6–18.8%
  per checkpoint) than the Trial 4 recipe. With PGO, the bulk-run build is **35.9%
  faster** (31.2–41.6%).
- **Against part 1's baseline:** the part-1 `.opt` runs measured 280.6–545.1 KIPS. The
  final PGO binary runs 514.7–1023.7, about 1.8× on every checkpoint. This compares runs
  made hours apart, so it is approximate.
- **Chaining overstates.** Multiplying each accepted trial's paired gain gives +22.7%, but
  the direct measurement is +17.3%. A trial passes partly when noise favors it, so the
  accepted gains are biased upward. The direct back-to-back comparison is the number to
  quote.

**What worked:**
- Removing out-of-line calls on the hottest paths: `RefCountingPtr::del`, and the
  per-address virtual BTB calls.
- Atomic `shared_ptr` reference-count traffic, which the deep dive had not modeled (LSQ
  requests, fetch targets).
- `rep stosq` for small memsets, fixed with a build flag.
- Memory touched per BTB probe (the tag mirror).
- Allocation pooling, where many small pools add up (Trials 20 and 21).

**What did not:**
- Changes worth under about 1%: IQ scans, the prefetcher probe hint, `-fno-plt`, a few
  allocations per instruction. They are below what five single runs can resolve.

**Protocol lessons:**
- The same binary varies by 2–4% between runs, and machine state drifts over hours. Pair
  every candidate with a fresh run of its reference.
- Quote end-to-end numbers from one back-to-back comparison, not from chained trial
  gains.
- Bundle related small changes, so the effect is large enough to measure.

**Correctness:**
- **Open:** builds that change code generation (Trial 5b) or the O3 width and thread
  bounds (Trial 19) change timing results. The diagnostics rule out uninitialized stack
  reads and heap placement.
- **Fixed:** the uninitialized `loopPredUsed` read was real. It affected only
  branch-predictor statistics, and is now fixed.

**Build recipes (local, g++-12):**
- **Development:** `CCFLAGS_EXTRA="-O3 $MS" LINKFLAGS_EXTRA="$MS" ... --with-lto --linker=bfd`,
  with `MS` the memset-strategy flag above.
- **Bulk runs:** the same plus PGO (see "PGO retrained on the part-2 code").
- **kratos2:** the cluster needs the same flags, and PGO retrained on its own compiler
  with agentic checkpoints.

**Left for later (not attempted):**
- **The ARM MMU translation path:** about 5% of time after part 2, the largest non-TAGE
  block, mostly fetch-directed-prefetch translations.
- **TAGE-SC-L:** about 11%, excluded by the user.
- **Smaller items:** a ROB ring buffer, FDP ring buffers, a dense TLB side array, the
  remaining LSQ request allocations, in-place `DynInst` PCs, the ARM misc-register read
  fast path, commit-loop cleanups.

## Overall result: parts 1 and 2, local

The original campaign baseline (`build/ARM/gem5.opt`, the same binary as `baseline-a`,
sha256 `4a08fbe77e4560d8…`), the final development build and the final PGO build were
run back to back on the test suite, each after the quiet-machine wait (runs
`overall-opt`, `overall-dev`, `overall-pgo`).
- **Final development build:** `build/ARM_p2/gem5.fast.lpfix`, the part-2 code with the
  `loopPredUsed` fix and the part-2 recipe.
- **Final PGO build:** `build/ARM_p2pgo/gem5.fast.pgo`.

| Checkpoint | Original `.opt` KIPS | Final development KIPS | Speedup | Final PGO KIPS | Speedup |
|---|---|---|---|---|---|
| 706.stockfish_r.1.1 | 512.9 | 780.9 | 1.52× | 937.8 | 1.83× |
| 706.stockfish_r.2.4 | 532.7 | 809.5 | 1.52× | 988.4 | 1.86× |
| 708.sqlite_r.0.3 | 371.9 | 569.6 | 1.53× | 658.7 | 1.77× |
| 723.llvm_r.1.0 | 269.3 | 435.4 | 1.62× | 508.2 | 1.89× |
| 753.ns3_r.2.0 | 300.7 | 475.5 | 1.58× | 541.9 | 1.80× |
| **Geomean** | | | **1.55×** | | **1.83×** |

- **Stats:** both final builds match the original `.opt` run on every stat except
  `numMiscRegReads`, the counter that `.opt`'s asserts inflate (Trial 1). They are
  bit-identical to `trial1-fast`.
- **Where it comes from, for the development build:** about +35–39% from part 1's build
  levers and +17% from part 2's code changes and memset flag. PGO adds another +17.6%
  for bulk runs (1.828 / 1.554). The stage figures were measured in different sessions,
  so they do not multiply exactly to the 1.55× measured here.

## Cluster port of part 2 (kratos2)

**Setup:** `feat/opt` was pushed over ssh to the cluster clone (`/home/rahbera/agentic-cpu/gem5`,
not to GitHub) and checked out there, at `3f86388d`. Both binaries were built on the login
node (g++-12 12.1.0) with `slurm/build-p2.sh`, which encodes the part-2 recipe: LTO +
bfd, tcmalloc, the memset-strategy flag, and `-Wl,-rpath,/home/rahbera/agentic-cpu/lib`.
Part 1's binaries were kept for comparison: `build/ARM_rel` (development) and
`build/ARM_pgo` (bulk).
- **Development build:** `build/ARM_rel2/gem5.fast`, 790 s. It has no `rep stosq` in
  `CPU::tick`, and its RUNPATH ends with the NFS library directory.
- **PGO bulk-run build:** `build/ARM_pgo2/gem5.fast`.
  - Instrumented build: 1186 s.
  - Training: one 3-CPU job on kratos15 over the same three agentic checkpoints as part 1
    (`gson-1093/cpt.2`, `ripgrep-2209/cpt.3`, `jq-2598/cpt.2`), 10M + 30M each. It took
    35 min and wrote 2052 `.gcda` files.
  - Optimized build: 614 s, with no profile-mismatch warnings and no gcov symbols.

**Measurement fix:** the first development comparison put both runs on CPUs 18 and 50 of
kratos17. By the usual numbering on a two-socket, 64-CPU node these are the two
hyperthreads of one core (inferred, not read from the topology), and this happened
despite `--hint=nomultithread`. That run measured 89.0 against 94.5 KIPS on llvm.
`slurm/compare-two.sbatch` now asks for 4 CPUs and pins the two runs to CPUs on different
physical cores, read from `/sys/devices/system/cpu/cpuN/topology`. It prints the cores it
used. All numbers below are from separate cores.

| Comparison (same node, separate cores) | Checkpoint | Old KIPS | New KIPS | Change | Stats |
|---|---|---|---|---|---|
| Development: part-1 `ARM_rel` vs part-2 `ARM_rel2` (kratos17) | SPEC `723.llvm_r.1.0` | 149.6 | 171.7 | **+14.8%** | bit-identical, and identical to local `trial1-fast` |
| | agentic `gin-2121/cpt.0` | 113.0 | 128.0 | **+13.3%** | bit-identical |
| Bulk: part-1 `ARM_pgo` vs part-2 `ARM_pgo2` (kratos15) | SPEC `723.llvm_r.1.0` | 179.7 | 209.9 | **+16.8%** | bit-identical, and identical to local `trial1-fast` |
| | agentic `gin-2121/cpt.0` | 132.5 | 154.6 | **+16.7%** | bit-identical, and identical to part 1's cluster PGO run |

- **Part 2 on the cluster:** +13–15% for development builds and +17% for bulk-run builds,
  against part 1's cluster binaries. That is in line with the local +16–17% on these
  two checkpoints.
- **Binaries on kratos2:**
  - Bulk runs: `build/ARM_pgo2/gem5.fast` (agentic-trained PGO).
  - Development: `build/ARM_rel2/gem5.fast`.
  - Debugging: `build/ARM/gem5.opt` (old `rbdev` build).
  - Slurm scripts that still name `build/ARM/gem5.opt` (`restore-one.sbatch`) should
    point at `ARM_pgo2` for bulk runs.
