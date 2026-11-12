---
type: howto
status: current
updated: 2026-11-12
sources:
  - analysis_scripts/tasktrace/pc_trace.py
  - "[[2026-11-12-jit-code-versions]]"
  - run_scripts/tasktrace/pc-trace.sh
  - runs/old-tests/traced-test/
  - src/cpu/exetrace.cc
tags: [trace, pc, footprint, tracer]
---

# PC trace: every committed instruction, compactly, with its task

**What it is:** gem5's own `Exec` trace, reduced on the fly to one short
line per committed instruction (its PC only when it is not the previous
PC + 4, plus the mnemonic), with task markers joined from the
[[task-tracer]]. It rebuilds the exact committed PC stream, so it supports
instruction footprint by process, unique branches (taken or not) and PC
repeat distance, computed offline. Since 2026-11-12 (format v2) it also
keeps each instruction's encoding where it is new at its PC, so code
rewritten at run time (JIT) shows; that needs gem5's `ExecEncoding` flag
([[#Encodings and code versions]]). Otherwise it uses the existing `Exec`
debug flags and the existing tracer. On a 2M-instruction gin-2121
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

The same trace on a window in stats blocks, or on every run of a sweep:
`PC_TRACE=1` with `o3-window.sh`, `spec-window.sh`, `sweep.sh` or
`smart_sweep.sh` (all share `run_scripts/tasktrace/pc-trace-lib.sh`;
`PC_TRACE_LEVEL` sets the zstd level, default 9). The whole run is traced,
settle and warm-up included. Checked on a gin-2121 O3 window (200K warm-up,
1M detailed, 2026-11-02): 1.22M instructions in a 77 KB trace. Its speed cost
on O3 has not been measured.

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
#	pc_trace	v2
#	kaslr_slide	0x36f7e8800000
#	switch_pc	0xffffb6f86985d6dc
#	task	0	1235	1290	u	opencode	Bun Pool 0
fffffbfffddf6408 b	14000001     ← PC given: not previous PC + 4; encoding new here
subs	f10007de                    ← PC = previous + 4
b.ne	54ffffc1
fffffbfffddf6408 b               ← jump target; encoding as last seen at this PC
subs
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
  `("inst", pc, mnemonic)`; with `encodings=True`, `("inst", pc,
  mnemonic, encoding)`.
- `\t<hex>` after the mnemonic (v2): the instruction's 32-bit encoding,
  given when it differs from the last one seen under the same decode key,
  or none was ([[#Encodings and code versions]]). v1 traces (before
  2026-11-12) have none and still read.

## How the join works: by PC

The tracer reports a switch once per pass through `__switch_to`, when its
first instruction is next to commit, and the Exec trace holds only
committed instructions. So the n-th
line at `__switch_to`'s address (its link address from `nm` on the guest
vmlinux, plus the KASLR slide from the task trace's `start` event; written
into the header as `switch_pc`) is the n-th switch, and the marker goes
right before it. This works on the atomic and O3 cores and across switches
between them. The reducer warns about a switch PC with no event, events
left over at the end, or a switch tick earlier than its Exec line's tick.

Ticks cannot be used on O3: its Exec lines carry the **fetch** tick, while
the tracer stamps a commit-time tick (4 ns and 99 ns later for the two
switches of the O3 check below). On the atomic core the two ticks are equal.

**Why some switch ticks are earlier than their Exec tick (O3).** O3's commit
stage services PC events after it commits an instruction and advances its
PC ([[task-tracer]]; `src/cpu/o3/commit.cc`, the `pcEventQueue.service` call
after `advancePC`). So the `__switch_to` hook fires when the `bl` into it
commits, while `__switch_to`'s first instruction is the next to commit. That
instruction is normally fetched long before, but when the fetch of the call
target is late (an L1I, iTLB or BTB miss on `__switch_to`, cold after
roughly 0.7M instructions of other code) the `bl` can commit before it is
fetched, and the switch tick is earlier than the Exec (fetch) tick. The
reducer counts these as "switch ticks before their Exec tick". They are rare
and follow the front end: on the 15G rubocop runs 68 (baseline), 46
(infinite BTB + L2 TLB), 38 (×4 caches), 16 (×8), 17 (both + ×4) and 1
(both + ×8) of about 20K switches each. The join is by PC count, so it is
unaffected (every slice still matches, see Validation); only a marker's tick
can be a few cycles before its instruction's fetch. The cause is read from
the code and fits the per-configuration counts; no individual case was
traced.

Streaming: the tracer writes and flushes the switch event before the
instruction commits and gem5 prints its Exec line, so the event is in
`tasktrace.jsonl` when the reducer reaches the line. Lines before the first
switch are held in memory until that switch names their owner (its `prev`).
`--vmlinux` defaults to the agentic kernel, which the SPEC guests share.

## Exec flags: use the lean set

`--debug-flags=ExecEnable,ExecUser,ExecKernel,ExecMacro,ExecEncoding` (what
the launcher uses; `ExecEncoding` since 2026-11-12, without it the trace
has no encodings). With `ExecMicro` off, `exetrace.cc` prints each architectural
instruction once (the macro-op at its last micro-op); with it on, the
micro-op lines (`0x….  0`, `. 1`) are dropped by the reducer anyway.

> [!warning] `ExecFaulting` adds instructions that did not commit
> The full `Exec` compound flag includes `ExecFaulting`, which prints an
> instruction that faults (e.g. a page-faulting `stp`) before the exception
> vector; it then executes again after the handler. In the
> `runs/old-tests/traced-test` sample this added 3 instructions to 2,000,004. The lean
> set leaves it out, and the live trace then matches the tracer's
> instruction counts exactly (1,756,030 before the first switch).

## Validation (2026-10-23, gin-2121 cpt.0)

| check | result |
|---|---|
| atomic, 2M instructions: expand the PC trace, compare with the source Exec trace | identical, 2,000,004 instructions PC for PC (`verify`) |
| atomic: instructions between switches vs the tracer's `insts` | equal (1/1 complete slice) |
| atomic, live pipe run vs the stored sample | identical apart from the sample's 3 faulting lines |
| O3, 1 + 0.5M warm-up + 2M detailed (`runs/old-tests/traced-test/o3-check`): expand vs Exec trace | identical, 2,538,421 instructions; both switches on `switch_pc` |
| O3: instructions between switches vs the tracer's `insts` | equal once NOPs are excluded (O3's count leaves them out; `verify` reports both) |
| O3 on rubocop-13560 (1 + 1M + 20M), live through the pipe | 62 switch events, 62 switch markers, no warnings; all 61 complete slices equal to the tracer's count without NOPs |
| O3, 15G instructions (rubocop, all six runs; four after the stall split): instructions between switches vs the tracer's `insts` (`check_pc_slices.sh`) | every complete slice equal without NOPs (20,213–22,631 per run, none different). The reducer's "switch ticks before their Exec tick" warning (1–68 per run) does not affect the pairing (why it appears: above) |
| rechecked 2026-11-02 | o3-check `verify`: identical, 2,538,421 instructions, its complete slice equal; rubocop-smoke: 61/61 slices equal, 62/62 markers on `switch_pc`; rubocop-15G `normal` (68 warnings): 20,213 slices equal, 0 different |
| footprint pass, 2026-10-27: count check at every marker | 0 off on O3 (o3-check, rubocop-smoke, launcher-check, rubocop cache8x) and on the atomic `fifo-check`; the stored atomic sample is off at its first switch by its 3 faulting lines (see the warning above) |
| size | 2.3 MB of raw text with no mnemonics (run-length) → this format 10.6 MB raw, 138 KB zstd-9 (113 KB zstd-19) |

## Encodings and code versions

A PC can hold different instructions over time: a JIT writes and patches
code (OpenCode's JavaScriptCore), the kernel patches itself. The guest does
not run per-line cache maintenance after writing code (the `CTR_EL0` value
OpenCode uses has IDC = DIC = 1), so the trace cannot learn from flushes
which code changed ([[2026-11-12-jit-code-versions]]); the encodings show
it directly.

- **gem5:** `ExecEncoding` (`src/cpu/exetrace.cc`) prints `E=<bytes>`
  before the disassembly: `StaticInst::asBytes()` as one little-endian
  word. On Arm that is the `ExtMachInst`, the encoding in the low 32 bits
  and decoder state above (`E=0000000414000001` is `b` `14000001`); the
  reducer keeps the low 32 bits. Off by default; in `ExecAll`, not in
  `Exec`.
- **Decode key:** kernel code by PC alone; user code by PC and the tgid of
  the current marker, -1 for the instructions between the first and
  second marker (those before the first switch, whose owner the reducer
  learns only at that switch). The reducer writes an encoding when it is
  new or changed under its key, so every encoding is rebuilt from the
  trace alone, without exec events. On the 30M check: 340,661 encodings
  written, the trace 1.76 MB (0.059 bytes per instruction).
- **Checks** (2026-11-12, rubocop-13560, atomic 30M): `verify` rebuilds PC,
  mnemonic and encoding of every instruction (30,000,001 identical); every
  taken direct branch's encoded offset gives its next PC (2,570,748, 0
  wrong); all NOPs `d503201f`.
- The reducer stops on a mnemonic starting with `E=` (gem5 pads the
  disassembly; a first regex read the encoding as the mnemonic, and
  `verify` could not see it because both sides parsed alike).

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
  line footprint as a multiple of each cache size. The sizes are a
  parameter, `--caches LEVEL:SIZE,...` (since 2026-11-02); the default is
  the [[neoverse-v2]] L1I and L2 at ×1/×4/×8 (64K/256K/512K, 2M/8M/16M).
  The pass saves the list in `caches.json`, which `--summary-only` and the
  report reuse; changing it needs a new pass, since the LRU capacities
  are counted in the pass. The summary's short tables show the smallest
  and largest size of each level.
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
- **Per thread, per bin** (`thread_bins.csv`, since 2026-10-30): a long
  thread's footprint grows with the length of what it ran, so the pass
  also cuts each thread's stream into bins of N instructions (`--bins`,
  default 100M, 500M, 1G) and counts distinct instructions, lines (code
  size, user and kernel) and branches by type, and distinct taken
  branches, in each bin. Two cuts: **own**, every N of the thread's own
  instructions (the same amount of work for every thread), and **run**,
  windows of N instructions of the whole run (what a sweep window or a
  cache sees in that time; a thread with little time in a window shows
  little code there). The value reported is the mean over the thread's
  whole bins, each weighted by its instructions (for own bins all
  weights are equal), with the largest bin's values. Only whole bins
  count (own: the thread reached N; run: the window ended before the
  trace did); a thread with none, shorter than one bin, reports its
  partial bin, which is its whole stream (`partial_only`). Checked on a
  20M-instruction prefix against a brute-force count, both cuts, all
  threads without an exec; a bin larger than the stream reproduces
  `threads.csv` exactly. `report.html` switches between the whole stream
  and the bins (and the cut); the code-size, fit and branch columns
  follow it, the repeat distances and misses stay whole-stream, and a
  growth plot shows the picked threads' code size and distinct taken
  branches against the bin size, with the cache sizes and the baseline
  BTB's 12K entries as references.
- **Code versions** (v2 traces, since 2026-11-12): per address space (a
  process instance, or the kernel) the pass keeps each PC's encodings in
  first-seen order. Every later encoding is a new instruction with its own
  key, and the line it is in becomes a new line, at most once per visit
  (the stream entering and leaving the line reads one snapshot). Distinct
  instructions, lines and branches, the LRU stacks, repeat distances and
  bins then count rewritten code as new code; pages (TLB reach) and the
  kernel code counted on behalf of a group stay by address. `rw_` columns
  give the part from later versions: `rw_insts`, `rw_lines`, `rw_br`;
  `rw_pcs` (PCs with several encodings), `rw_flips` (a PC going back to an
  earlier encoding), `rw_lines_lb` (per line, the most encodings at one PC
  minus one: a lower bound on the line versions; `rw_insts` is an upper
  bound), `*_rw_cold` (cold misses on rewritten lines). `summary.md` has a
  *Rewritten code* section when there are any. On a v1 trace every PC has
  one version and the output is the same as before (every old column
  identical on a 300M-line prefix of the 15G rubocop trace);
  `--mnemonic-versions` takes the mnemonic as the encoding there, a lower
  bound that misses JIT patching (new immediates and branch targets keep
  the mnemonic). Checked against a hand-made trace with known rewrites.
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
- JIT code can reuse an address for different code: on v1 traces the
  footprint counts addresses touched per address space, not distinct
  code; v2 traces count each encoding at a PC ([[#Encodings and code
  versions]]). A rewrite is seen only when the new code runs at a PC that
  already ran in the same address space.
- `report.html` has fixed axes (code 4 KiB–64 MiB, repeat distance up to
  2^25 instructions and 2^22 lines, widened to twice the largest cache);
  values beyond them sit at the edge. The BTB line (12K entries,
  `NeoverseV2_BTB`) is still fixed in `pc_footprint_report.py`.
- Bins are cut by the pass's own instruction count, which includes NOPs
  (the tracer's O3 count does not); negligible at 100M.
- The bins cost memory and time: on rubocop cache8x the pass went from 43
  min and 7.8 GB to 51 min and 12.8 GB (2026-10-30). `--bins ""` turns
  them off.
- `report.html` is ~2.8 MB with the bins. Before 2026-10-30 its "All
  numbers" table never rendered (its default sort key named no column).
