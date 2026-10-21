---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
tags: [tlb, mmu, perturbation, tracer]
---

# gem5's functional translation is not side-effect free

**The trap:** reading guest virtual memory through `TranslatingPortProxy`
looks harmless, but `ArmISA::MMU::getTE` does its first TLB lookup with
`functional = false` even for a functional translation. So the read
**updates TLB replacement state and statistics, and on an L1 miss can fill
the L1 from the L2 TLB** (`TLB::multiLookup`).

**Measured:** the first version of the [[task-tracer]] used it. An O3 pair
(gin-2121, 1M + 5M) without the tracer was identical; with it IPC moved
0.635 → 0.649 and 5,377 stats lines differed (TLB, walker, caches, branch
predictor).

**Fix used:** walk the guest page tables in software and read through
`System::physProxy`. Fixing `getTE` itself would change every SE-mode
result in the fork (SE syscall emulation translates functionally all the
time), so it was left alone.

**Also affected:** the remote GDB stub (`base/remote_gdb.cc`) reads through
`TranslatingPortProxy` too, so inspecting a run with it perturbs it.

**Lesson:** any observer must pass the no-perturbation check
([[validation-checks]]) before its runs are used.
