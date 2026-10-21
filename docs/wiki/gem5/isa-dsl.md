---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
tags: [gem5, isa]
---

# ISAs and the `.isa` DSL

Each ISA lives in `src/arch/<isa>/` (`arm mips power riscv sparc x86 amdgpu
null`). Instruction decoding and semantics are written in a custom DSL
(`src/arch/<isa>/isa/*.isa`) that `src/arch/isa_parser/` compiles to C++. To
add or change an instruction, edit the `.isa` `decode` tree or `format`
blocks and rebuild.

Each ISA has the same set of files (`isa.cc`, `decoder.cc`, `tlb.cc`,
`process.cc`, `faults.cc`). The ISA-independent interfaces are in
`src/arch/generic/`, for example `src/arch/generic/mmu.hh`, where this fork
added the `currentAsid` hook ([[infinite-btb-model]]).

Fork-specific Arm code:

| path | what it is |
|---|---|
| `src/arch/arm/linux/task_tracer.{hh,cc}` | the [[task-tracer]] |
| `src/arch/arm/mmu.{hh,cc}` | the ASID query used by the [[infinite-btb-model]] |
| commit 8d0dafc815 | restoring QEMU-virt checkpoints with 16-bit ASIDs ([[checkpoints]]) |
