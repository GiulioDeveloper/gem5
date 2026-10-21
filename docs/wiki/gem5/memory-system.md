---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
tags: [gem5, memory, cache, ruby]
---

# Memory system: classic vs Ruby

gem5 has two memory stacks:

- **Classic** (`src/mem/cache/`, `src/mem/*xbar*`, `src/mem/mem_ctrl.*`):
  caches and crossbars that compose freely, with simple coherence. The
  stdlib classic hierarchies (`components/cachehierarchies/classic/`) use it,
  and so does the fork's Neoverse V2 hierarchy
  (`configs/garfield/arm/cache_hierarchy.py`, [[neoverse-v2]]).
- **Ruby** (`src/mem/ruby/`): detailed coherence. Protocols are written in
  the **SLICC** DSL (`.sm` state machines and `.slicc` files in
  `src/mem/ruby/protocol/`) and compiled to C++ by `src/mem/slicc/`. The
  protocol is fixed at build time by `PROTOCOL` ([[building]]), which is why
  there are protocol-specific `build_opts/` such as `X86_MESI_Two_Level`. To
  change a protocol, edit its `.sm` files and rebuild that config.

The TLB hierarchy is part of the MMU in `src/arch/arm/`, not of the memory
system. See [[tlb-hierarchy]].
