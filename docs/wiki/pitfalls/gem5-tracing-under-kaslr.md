---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [tracing, kaslr, gem5-features]
---

# gem5's built-in tracing does not work on these guests

The guest kernel runs with **KASLR**, and the checkpoints carry an **empty
kernel symbol table**. Everything in gem5 that names kernel code uses link
addresses from that table, so it is wrong or silent here. Checked against
the source:

| feature | problem |
|---|---|
| `enable_context_switch_stats_dump` (`arch/arm/linux/fs_workload.cc`) | hooks `__switch_to` at the unslid link address; panics at start-up with an empty table (`dumpStats not created!`); takes struct offsets from symbols only a gem5-patched kernel defines (otherwise warns once and reports pid 0 for every switch); reads through `TranslatingPortProxy`; dumps and resets all stats at every switch |
| `Exec`, `ExecSymbol` | ~94 bytes per instruction (~470 GB per 5G instructions), no task identity, symbols at link addresses, fetch tick on O3. Good as a short cross-check ([[validation-checks]]) |
| `function_trace` | same symbol table, silent when empty; no arguments, no task |
| probe points (`RetiredInstsPC`, `PcCountTracker`) | a PC and nothing else; a callback per instruction; `PcCountTracker` exits to Python on each hit |
| remote GDB stub | stops at every breakpoint; perturbs the TLB ([[functional-translation-perturbs]]) |
| m5ops, ftrace, `perf sched`, eBPF in the guest | need recapture of all 132 checkpoints and add work to the measured stream; guest clock, not ticks |

`BaseISA::getExecutingAsid()` is a related trap: on Arm it returns
`CONTEXTIDR`, which this kernel leaves at 0 ([[infinite-btb-model]]).

Recapturing with `nokaslr` would only simplify the slide derivation: the
same computation gives `swapper_pg_dir`'s address for the page walk. The
[[task-tracer]] is the answer.
