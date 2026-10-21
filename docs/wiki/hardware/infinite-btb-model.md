---
type: entity
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/infinite-btb]]"
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
  - src/cpu/pred/infinite_btb.cc
tags: [btb, limit-study, simobject]
---

# InfiniteBTB: unbounded, ASID-separated BTB

**What it is:** a BTB for limit studies that never evicts, never aliases
and keeps every address space apart, so the only misses left are the first
taken occurrence of each branch (compulsory misses). Enable with
`--infinite-btb` on any driver that calls `sim_opts.apply_core_knobs`
(`virt_run.py`, `fs_run.py`, `se_run.py`); the banner shows `BTB=infinite`.
Result: +3.0% IPC on the median agentic window, nothing on SPEC
([[btb-tlb-limits]]).

## Design

- **Storage:** `unordered_map<Space, unordered_map<Addr, Entry>>`, Entry =
  target `PCState` + `StaticInstPtr`, keyed by the full PC. O(1), no sets,
  no replacement, no tag truncation. A huge `SimpleBTB` was not an option:
  `AssociativeCache` scans every way and copies the set's pointer vector on
  each lookup, and BAC probes about every 4 bytes of each fetch target.
- **Address spaces** (`spaceOf`): PC bit 63 set → one shared kernel table
  (an OS-layout assumption: Linux on arm64, x86-64, RISC-V); user code → its
  ASID; user code without an ASID → `NoAsidSpace` (plain VA). `tid` (the SMT
  slot) is not part of the key.
- **The ASID comes from a generic MMU hook**, so the BTB has no ISA code:
  `BaseMMU::currentAsid(tc)` (`src/arch/generic/mmu.hh`, default `nullopt`);
  the Arm override (`src/arch/arm/mmu.cc`) runs the TLB's own
  `CachedState::updateMiscReg` on a *local* copy, so no MMU state or stat
  changes and it inherits the 16-bit ASID setting. The O3 CPU hands thread
  contexts to the BTB through `BPredUnit::setThreadContext`; other CPU
  models do not yet (the BTB warns and falls back to VA tagging).
  `BaseISA::getExecutingAsid()` was not usable: on Arm it returns
  `CONTEXTIDR`, which this guest kernel leaves at 0 (no
  `CONFIG_PID_IN_CONTEXTIDR`).
- **KPTI:** each process uses an ASID pair (user = kernel | 1), so the
  Neoverse V2 variant sets `ignoreAsidLsb = True`. The default is `False`
  because without KPTI it would merge processes.
- The ASID is read from **committed** state, cached once per tick: for a
  few cycles after a context switch BAC may probe with the previous ASID.
- No latency or bandwidth model (neither has `SimpleBTB`), no ASID-rollover
  handling, no JIT handling. It is a limit on capacity and aliasing, not a
  realistic large-BTB design. Works with `--disable-fdp` too.

## Statistics (`branchPred.btb.*`)

| stat | meaning |
|---|---|
| `newEntries` | first-time inserts: compulsory misses **plus wrong-path inserts** (31% in one check) |
| `kernelEntries` / `userEntries` / `noAsidEntries` | split by space; `noAsidEntries` should be 0 on O3/Arm |
| `entries`, `addressSpaces` | **live values** of the current table size, not reset by `m5.stats.reset()` |
| `staleEncodings` | different encoding at the same (space, PC): JIT rewrite or ASID reuse |
| `staleTargets` | changed target of a *direct* branch: also a stale entry |

Counters count per stats block (`newEntries` = branches first seen in that
block), while the table survives resets.

## Validation (2026-10-16)

- **Inserts = unique taken branches + wrong path.** gin-2121, 2M O3
  instructions, `--disable-fdp`, commit trace + BTB log: 8,739 of 8,743
  unique taken PCs inserted (the other 4 jump to PC+4); the 3,883 extra
  inserts are all wrong-path. axios-5892, 20M instructions: 33,954 of
  33,970, again all extras wrong-path.
- **Address spaces match processes.** axios-5892: `addressSpaces = 7` =
  the 6 user processes the [[task-tracer]] saw + kernel; no PC in two
  spaces. Without `ignoreAsidLsb` it would be about 13.
- **Default BTB unperturbed:** the fmt-3901 baseline rerun with the new
  plumbing is bit-identical to the 2026-10-14 sweep.
- **Footprint:** fmt-3901, 20K entries after warm-up, 150K after 400M
  instructions (about 12× the 12K baseline); no stale or ASID-less entries;
  4–11 address spaces. Memory: tens of MB per run.

## Future work

- **Pass-1/pass-2 oracle** to remove compulsory misses too: dump
  `(space, PC, encoding)` of every branch in one run, preload it in the
  next ([[questions]]).
- ASID-rollover and invalidation hooks if the stale stats ever call for
  them; `setThreadContext` from Minor and the simple CPUs; `currentAsid` for
  RISC-V (`satp.ASID`) and x86 (PCID).
