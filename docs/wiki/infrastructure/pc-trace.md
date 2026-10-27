---
type: howto
status: current
updated: 2026-10-27
sources:
  - analysis_scripts/tasktrace/pc_trace.py
  - run_scripts/tasktrace/pc-trace.sh
  - runs/traced-test/
  - src/cpu/exetrace.cc
tags: [trace, pc, footprint, tracer]
---

# PC trace: every committed instruction, compactly, with its task

**What it is:** gem5's own `Exec` trace, reduced on the fly to one short
line per committed instruction (its PC only when it is not the previous
PC + 4, plus the mnemonic), with task markers joined from the
[[task-tracer]]. It rebuilds the exact committed PC stream, so it supports
instruction footprint by process, unique branches (taken or not) and PC
repeat distance, computed offline. No gem5 change: it uses the existing
`Exec` debug flags and the existing tracer. On a 2M-instruction gin-2121
window it is **138 KB** (zstd level 9) against 30 MB for the gzipped
`Exec` trace.

## Running it

```sh
run_scripts/tasktrace/pc-trace.sh gin-2121 2000000      # TASK MAX_INSTS [virt_run args]
O3="1 20000000 400000000" run_scripts/tasktrace/pc-trace.sh gin-2121 0   # SETTLE WARMUP DETAILED on O3
```

The atomic core is the default: the committed stream does not depend on
timing, and it is several times faster. `O3=` runs a detailed window
instead; the whole run is traced, settle and warm-up included. gem5 writes the
Exec trace into a named pipe in the output directory and
`pc_trace.py reduce` reads it, so the full trace is never stored. Output:
`pc_trace.zst`, `pc_trace.log` (counts per task), `tasktrace.jsonl`, and
`stats.tsv.zst` (the stats as a values-only table, [[stats-blocks]];
`KEEP_STATS=1` also keeps `stats.txt`). Measured: about **560K instructions/s** on the host (the plain
atomic core is about 1.7M/s), so roughly 12 minutes per 400M instructions.

On an existing Exec trace file (plain, `.gz` or `.zst`):

```sh
python3 analysis_scripts/tasktrace/pc_trace.py reduce <run>/exec.gz \
    -o <run>/pc_trace.zst --tasktrace <run>/tasktrace.jsonl
python3 analysis_scripts/tasktrace/pc_trace.py verify <run>/exec.gz \
    <run>/pc_trace.zst --tasktrace <run>/tasktrace.jsonl
```

Python 3.14+ (built-in `compression.zstd`); `PY=` picks another
interpreter for the launcher. `GEM5_OPTS` passes gem5 options (default
`--stats-file=stats.txt?desc=False`); extra arguments after the positional
ones go to `virt_run.py` (e.g. `--stats-interval-insts 10000000`).

**Measured cost on O3** (rubocop-13560, 1 + 1M + 20M, 1M blocks,
2026-10-23): **181K instructions/s** in the detailed region, gem5 peak RSS
2.7 GB, `pc_trace.zst` **0.041 bytes per instruction**, `stats.txt` about
315 KB per block without descriptions, `tasktrace.jsonl` about 2.5 KB per
M instructions. So 15G detailed instructions take about 23 hours, about
0.6 GB of PC trace, and 0.5 GB of stats in 10M blocks.

**Measured on 15G-instruction O3 runs** (rubocop, six configurations,
200K blocks, 2026-10-23): 124–176K instructions/s, gem5 RSS growing to
~8.6 GB, PC trace 0.37–0.54 GB per run (~0.035 bytes per instruction),
stats 20–22 GB of text → 0.23–0.27 GB as a table
([[2026-10-23-rubocop-15g-cache-btb-tlb]]).

## Format

```
#	pc_trace	v1
#	kaslr_slide	0x405244c00000
#	task	0	1235	1308	u	opencode	JITWorker
fffffbfffddf6480 msr          ← PC given: not previous PC + 4
movz                          ← PC = previous + 4
b
subs
b.ne
fffffbfffddf6488 b            ← jump target; the line before it jumped
#	task	209306074077	1235	1303	u	opencode	JITWorker
```

- A line with an address is a jump target, an exception vector, or the
  first line after a marker. The line before an addressed line is the
  instruction that transferred control (or was interrupted).
- `#\ttask\t<tick>\t<tgid>\t<pid>\t<u|k>\t<process>\t<comm>`: every
  instruction after it, until the next marker, ran as that task. The first
  marker (tick 0) is the first switch's `prev`, which owns everything before
  it (the rule of [[trace-analysis#Who ran when]]). A trace with no switch
  gets `not recorded`.
- Kernel vs user mode: PC bit 63. Reading in Python:
  `pc_trace.read_pc_trace(path)` yields `("task", fields)` and
  `("inst", pc, mnemonic)`.

## How the join works: by PC

The tracer reports a switch when the first instruction of `__switch_to`
commits, and the Exec trace holds only committed instructions. So the n-th
line at `__switch_to`'s address (its link address from `nm` on the guest
vmlinux, plus the KASLR slide from the task trace's `start` event; written
into the header as `switch_pc`) is the n-th switch, and the marker goes
right before it. This works on the atomic and O3 cores and across switches
between them. The reducer warns about a switch PC with no event, events
left over at the end, or a switch tick earlier than its Exec line's tick.

Ticks cannot be used on O3: its Exec lines carry the **fetch** tick, while
the tracer stamps the commit tick (4 ns and 99 ns earlier for the two
switches of the O3 check below). On the atomic core the two ticks are equal.

Streaming: the tracer writes and flushes the switch event before the
instruction commits and gem5 prints its Exec line, so the event is in
`tasktrace.jsonl` when the reducer reaches the line. Lines before the first
switch are held in memory until that switch names their owner (its `prev`).
`--vmlinux` defaults to the agentic kernel, which the SPEC guests share.

## Exec flags: use the lean set

`--debug-flags=ExecEnable,ExecUser,ExecKernel,ExecMacro` (what the launcher
uses). With `ExecMicro` off, `exetrace.cc` prints each architectural
instruction once (the macro-op at its last micro-op); with it on, the
micro-op lines (`0x….  0`, `. 1`) are dropped by the reducer anyway.

> [!warning] `ExecFaulting` adds instructions that did not commit
> The full `Exec` compound flag includes `ExecFaulting`, which prints an
> instruction that faults (e.g. a page-faulting `stp`) before the exception
> vector; it then executes again after the handler. In the
> `runs/traced-test` sample this added 3 instructions to 2,000,004. The lean
> set leaves it out, and the live trace then matches the tracer's
> instruction counts exactly (1,756,030 before the first switch).

## Validation (2026-10-23, gin-2121 cpt.0)

| check | result |
|---|---|
| atomic, 2M instructions: expand the PC trace, compare with the source Exec trace | identical, 2,000,004 instructions PC for PC (`verify`) |
| atomic: instructions between switches vs the tracer's `insts` | equal (1/1 complete slice) |
| atomic, live pipe run vs the stored sample | identical apart from the sample's 3 faulting lines |
| O3, 1 + 0.5M warm-up + 2M detailed (`runs/traced-test/o3-check`): expand vs Exec trace | identical, 2,538,421 instructions; both switches on `switch_pc` |
| O3: instructions between switches vs the tracer's `insts` | equal once NOPs are excluded (O3's count leaves them out; `verify` reports both) |
| O3 on rubocop-13560 (1 + 1M + 20M), live through the pipe | 62 switch events, 62 switch markers, no warnings; all 61 complete slices equal to the tracer's count without NOPs |
| O3, 15G instructions (rubocop, all six runs; four after the stall split): instructions between switches vs the tracer's `insts` (`check_pc_slices.sh`) | every complete slice equal without NOPs (20,213–22,631 per run, none different). The reducer's "switch ticks before their Exec tick" warning (46–68 per run) does not affect the pairing |
| footprint pass, 2026-10-27: count check at every marker | 0 off on O3 (o3-check, rubocop-smoke, launcher-check, rubocop cache8x) and on the atomic `fifo-check`; the stored atomic sample is off at its first switch by its 3 faulting lines (see the warning above) |
| size | 2.3 MB of raw text with no mnemonics (run-length) → this format 10.6 MB raw, 138 KB zstd-9 (113 KB zstd-19) |

## Footprint, hit rates and branches

```sh
python3 analysis_scripts/tasktrace/pc_footprint.py <run>    # → <run>/footprint/ (summary.md, report.html, footprint.csv, instances.csv, threads.csv)
python3 analysis_scripts/tasktrace/pc_footprint_report.py <run>/footprint   # rebuild report.html only
```

One pass in C++ (`pc_footprint.cc`, built with g++ on first use): 43 min
and 7.8 GB on 15.2G instructions (rubocop cache8x, 2026-10-27).

- **Processes:** a process instance ("PID") is a tgid between execs
  (threads share it). Execs are placed at their exact instruction: the pass
  counts instructions from each switch marker the way the tracer does, and
  at every marker checks that the count equals the switch event's (0
  mismatches on rubocop cache8x). The tracer's count leaves NOPs out on O3
  and includes them on the atomic core; the pass keeps both counts and
  takes the one the first switch matches (stderr: `NOPs counted` or `not
  counted`). Before 2026-10-27 it always left NOPs out, which on an atomic
  trace would have placed execs early by the NOPs before them; the O3
  results were not affected. Fork children that run a little of the parent's code
  before their exec are flagged (`pre_exec_fork`) and left out of the
  per-name statistics. Kernel code (PC bit 63) is the group `[kernel]` with
  global addresses, and is also counted per process it ran for (the
  current task, kernel threads included).
- **Three views of user code:** *per PID* (`instances.csv`); *per name,
  each process separate* (a name's processes summed; the same address in
  two runs counts twice); *per name, aggregated* (`m_` columns: all
  processes of a name share one address space, so code repeated at the
  same address counts once and stays cached between runs). The aggregated
  view stands for code shared through the page cache only where binaries
  load at fixed addresses; with ASLR it barely shrinks (`overlap` =
  aggregated / summed footprint). There are no physical addresses, so
  shared libraries are never shared across processes.
- **Footprint:** distinct instructions, 64-byte lines and 4 KiB pages; the
  line footprint as a multiple of each L1I/L2 size (64K/256K/512K,
  2M/8M/16M, the [[neoverse-v2]] sizes at ×1/×4/×8).
- **LRU stack distance** per line access (a fetch that moves to another
  line): the number of distinct lines touched since the line's previous
  access (Fenwick tree over access slots). A fully associative LRU cache of
  C lines hits when the distance is < C. Reported as misses per 1,000
  instructions, cold misses separately, in two views: *private* (the
  group's code alone) and *shared* (the interleaved stream, as the core
  sees it). Instruction lines only: in the real L2, data competes for the
  same capacity, and gem5's caches have prefetchers and finite
  associativity.
- **Per thread** (`threads.csv`, `report.html`): a thread is a pid within
  a process instance (an exec starts a new one) or a kernel thread. Its
  stream is everything committed while it was current, user code and
  kernel code, on its own: distinct instructions and lines (user and
  kernel apart), the LRU stack distance per line (private and shared, as
  above) and the **repeat distance per instruction address**: distinct
  instructions committed since the same PC last committed (a stack
  distance per PC; `thread_hist.tsv` holds both histograms, log2
  buckets). `report.html` is one self-contained page: a row per thread
  with instructions and code size split between user and kernel mode,
  code size against the cache sizes, code ÷ cache size (user + kernel,
  user only or kernel only), repeat
  distance percentiles (median, 90th, 99th) per instruction and per line,
  and distinct branches by type; miss ratio curves of the threads picked;
  a sortable table; processes can be hidden by name (kernel threads are
  one entry).
- **Branches:** distinct addresses of `b.cond`/`cbz`/`cbnz`/`tbz`/`tbnz`
  (cond), `b`, `bl`, `blr*`, `br*`, `ret*`, `eret*`; *taken* when the next
  instruction is not at PC + 4. A transfer into the kernel's EL1 vector
  tables (`vectors`, `__bp_harden_el1_vectors`) is an exception and does
  not count.

## Limits

- Committed instructions only: no wrong-path fetch.
- A window with no switch has its whole stream `not recorded`
  (the tracer names a task only when it switches).
- The atomic core's schedule differs from O3's, so event positions differ
  ([[window-placement]]); stream statistics should not.
- JIT code can reuse an address for different code: footprint counts
  addresses touched per address space, not distinct code.
- `report.html` has fixed axes (code 4 KiB–64 MiB, repeat distance up to
  2^25 instructions and 2^22 lines); values beyond them sit at the edge.
  The cache sizes are the [[neoverse-v2]] L1I and L2 at ×1/×4/×8
  (`CACHES` in `pc_footprint.py`).
