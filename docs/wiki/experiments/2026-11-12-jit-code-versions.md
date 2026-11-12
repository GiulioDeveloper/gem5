---
type: experiment
status: current
updated: 2026-11-12
sources:
  - runs/jit-footprint/sync_counts.tsv
  - runs/jit-footprint/raw-exec/
  - runs/jit-footprint/synth/
  - runs/jit-footprint/regress/
  - runs/jit-footprint/rubocop-1g/
  - runs/rubocop-15G/cache8x/pc_trace.zst
  - src/cpu/exetrace.cc
  - analysis_scripts/tasktrace/pc_trace.py
  - analysis_scripts/tasktrace/pc_footprint.cc
tags: [agentic, jit, footprint, icache, branches, pc-trace]
---

# JIT code versions: one PC, several instructions

The instruction footprint so far counted code by address. JIT code (OpenCode
runs JavaScriptCore inside Bun) can put different instructions at the same
address over time, so a PC can stand for several instructions and a branch
for several branches. The PC trace now records each instruction's encoding
where it is new at its PC (format v2, [[pc-trace#Encodings and code
versions]]), and the footprint pass counts every later encoding at a PC as
a new instruction, and its line as a new line. Validated end to end. On a
1G-instruction rubocop window rewriting in place is rare: 38 PCs, all in
OpenCode's main thread, against 236 calls of its cache-flush routine, so
the JIT mostly writes new code at new addresses, which address-based
counting already sees; the footprint and branch counts change by less than
0.01% (one window, atomic core).

## Question

Does rewritten code change the footprint and branch counts of
[[2026-10-26-rubocop-instruction-footprint]]? First: does the trace show
the guest synchronising the caches after writing code, and could that tell
which code changed?

## Setup

- Sync instructions: the 15.2G-instruction PC trace of
  `runs/rubocop-15G/cache8x` (v1, mnemonics only), scanned per process and
  mode (`runs/jit-footprint/sync_scan.cc`, 8.5 min).
- gem5: new debug flag `ExecEncoding` (`src/cpu/exetrace.cc`): prints
  `E=<bytes>` before the disassembly, the instruction's bytes as the ISA
  stores them (`StaticInst::asBytes`; on Arm the `ExtMachInst`, encoding in
  the low 32 bits). Off by default; part of `ExecAll`, not of `Exec`.
- Raw check run: rubocop-13560, atomic, 30M instructions, raw Exec trace
  with `ExecEncoding` and `ExecResult` (`runs/jit-footprint/raw-exec.sh`,
  2 min).
- Real run: rubocop-13560, atomic, 1G instructions, through
  `pc-trace.sh` (the live pipe, the launcher's flags now include
  `ExecEncoding`): `runs/jit-footprint/rubocop-1g/`.

## Results

### Cache maintenance in the trace (15G rubocop)

| | count |
|---|---|
| calls of OpenCode's cache-flush routine (`0x24210a0`) | 4,022 |
| …main thread 1235 / JITWorker 1263 / 1264 / thread 1908 | 1,819 / 1,557 / 608 / 38 |
| user-mode `ic` / `msr` (would be `ic ivau`) in OpenCode | 0 / about 2 |
| user-mode `dc` in OpenCode | 2.46M |

- The routine has the shape of compiler-rt's `__clear_cache`: it tests the
  IDC and DIC bits of a cached `CTR_EL0` and skips the `dc cvau` loop on
  IDC and the `ic ivau` loop on DIC. All 4,022 calls run the same 9
  instructions (`dsb ish`, `isb`): no per-line maintenance, so the trace
  cannot tell which code was written.
- The cached value is `0xb444c004` (raw run, `ExecResult`): IDC = DIC = 1.
  gem5's own `CTR` has both clear (`0x8444c004`;
  `src/arch/arm/regs/misc.cc`, `MISCREG_CTR`). The value looks like a real
  Neoverse-class `CTR_EL0` (bit 31 RES1, DIC, IDC, line sizes 64 B,
  PIPT). Hypothesis, not checked: Bun read it under KVM on the host before
  the checkpoint, and never reads it again (the cached-value test is taken
  on every call).
- User-mode `dc` is memset's `dc zva`: all 3,195 in the 30M raw window.
- So detecting rewrites from the instructions themselves (their encodings)
  is the only route; the flush calls only mark when code was installed.

### Validation

| check | result |
|---|---|
| raw 30M run: `pc_trace.py verify` (PC, mnemonic and encoding of every instruction, rebuilt from the v2 trace) | identical, 30,000,001 instructions; 49/49 slices equal to the tracer's count |
| encodings vs the stream (`runs/jit-footprint/check_encodings.py`): taken direct branches (b, bl, b.cond, cbz, tbz) whose encoded offset gives the next PC | 2,570,748 of 2,570,748 (365 more interrupted into an exception vector); 0 mnemonic mismatches; all 332,215 NOPs `d503201f` |
| hand-made trace with two rewrites, two flips back and a branch re-pointed (`runs/jit-footprint/synth/`) | every count as worked out by hand (distinct instructions 8, of which 2 later versions; lines 4, 1 later version; 10 line accesses, 4 cold, 1 on a rewritten line; LRU hits at 2 and 4 lines) |
| v1 trace, old pass (HEAD) vs new, 300M-line prefix of the 15G rubocop trace (`runs/jit-footprint/regress/`) | every old column of all six TSVs identical; the new columns all zero |
| an encoding-parsing bug found on the way | the first regex took `E=…` as the mnemonic (gem5 pads the disassembly); `verify` passed because both sides parsed alike. Fixed, and the reducer now stops on a mnemonic starting with `E=` |

Trace size: the raw 30M window is 1.76 MB as v2 (340,661 encodings
written, 0.059 bytes per instruction).

### Rewrites seen

30M raw window: 4 PCs rewritten, all in OpenCode's main thread, all in one
64-byte line of JIT code: a `movz`/`movk`/`movk` triple loading a new
48-bit constant and a `bl` re-pointed to a new target (JavaScriptCore
repatching). Each kept its mnemonic, so a mnemonic-based detection
(`--mnemonic-versions` on v1 traces) would have missed all four.

1G run (`runs/jit-footprint/rubocop-1g/`, atomic, 1,000,000,001
instructions, 1,600 switches, 17 execs; trace 31.6 min at 528K
instructions/s, reducer and gem5 peak 3.5 GB; trace 34.5 MB, 0.035 bytes
per instruction, the same as v1; pass 214 s and 1.8 GB):

| | OpenCode (all its instances) |
|---|---|
| instructions | 693.7M |
| calls of the cache-flush routine | 236 |
| PCs rewritten / later versions / flips back | 38 / 41 / 0 |
| distinct instructions, versioned (address only) | 916,875 (916,834) |
| line versions (lower bound) | 17 (17) |
| code, KiB, versioned (address only) | 5,056 (5,055) |
| distinct branches / of which later versions | 163,647 / 17 |
| cold misses on rewritten lines | 17 (0.00002 per 1,000 instructions) |

All in the main thread (pid 1235); no other process and no kernel code
rewrote a PC. The reducer counted 41 encoding changes, the same as the
pass's later versions.

## Conclusions (provisional)

- The guest does not run per-line cache maintenance for its JIT code
  (IDC = DIC = 1 in the value Bun cached), so code changes cannot be found
  from flushes; encodings find them exactly.
- JIT patching keeps mnemonics (new immediates, new branch targets): the
  encoding is needed, the mnemonic is not enough.
- In this window the JIT installs code (236 flush calls) almost always at
  fresh addresses: rewriting in place touches 38 PCs, so counting by
  address undercounts OpenCode's code and branches by under 0.01%. The
  earlier footprint and branch numbers
  ([[2026-10-26-rubocop-instruction-footprint]]) stand on this evidence,
  which is one 1G window on the atomic core, early in the run; a longer
  stretch (more JIT tiers, code GC and reuse of freed addresses) could
  differ.

## Decisions

- 2026-11-12: one encoding map per address space (process instance, or the
  kernel), keyed by PC, the encodings seen as the value in first-seen
  order; every later encoding is a new instruction (user's choice: a PC
  with two instructions counts twice). A flip back to an earlier encoding
  reuses its version.
- 2026-11-12: a line's version goes up at most once per visit (the stream
  entering and leaving the line), since a visit reads one snapshot; the
  first rule (once per new encoding) counted 4 versions for the 4 PCs
  rewritten together in the raw window. Lower bound kept as a check (per
  line, the most encodings at one PC, minus one).
- 2026-11-12: pages are not versioned (rewriting code does not change
  translations); kernel code counted on behalf of a group is by address.
- 2026-11-12: gem5 prints `asBytes()` unchanged (the generic `size()` is
  fatal for micro-ops); the reducer keeps the low 32 bits.
- 2026-11-12: the reducer writes an encoding only where it is new under
  its decode key (the PC; for user code with the marker's tgid), so a
  reader rebuilds every encoding from the trace alone; v1 traces still
  read.

## Open

- Whether to redo the 15G rubocop trace as v2 (about a day on O3, roughly
  8 h on the atomic core at the 1G run's rate) to check the
  rewrite rate over a long run (code GC, address reuse).
- Where `CTR_EL0 = 0xb444c004` comes from (the KVM-host hypothesis), and
  whether the guest should see gem5's value instead: with DIC = 0, Bun
  would run `ic ivau` per line after writing code.
- Fork children start with an empty encoding map (a new address space,
  as before); copying the parent's would matter only if the parent's code
  had been rewritten before the fork.
- `report.html` does not show the rewrite columns yet.
