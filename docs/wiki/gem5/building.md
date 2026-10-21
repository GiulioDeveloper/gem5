---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
  - build-gem5.sh
tags: [gem5, build]
---

# Building gem5

Part of [[gem5-overview]].

gem5 builds with **SCons**. The build config name picks the ISA(s) and the
Ruby coherence protocol **at compile time**. There is no ISA or protocol
switching at run time. For this fork's work the build is
`scons build/ARM/gem5.opt -j$(nproc)`: the Neoverse V2 model and the
[[task-tracer]] are Arm.

```sh
scons build/ARM/gem5.opt -j$(nproc)     # what the agentic work uses
scons build/ALL/gem5.opt -j$(nproc)     # all ISAs
scons build/RISCV/gem5.debug            # RISC-V, debug build
```

- `build/<CONFIG>/` is the build directory. `<CONFIG>` must match a file in
  `build_opts/`, for example `ALL`, `X86`, `ARM`, `RISCV`, `NULL`,
  `X86_MESI_Two_Level` or `ARM_MOESI_hammer`. Each such file is a KConfig
  **defconfig** that sets `USE_*_ISA`, `RUBY`, `PROTOCOL` and so on.
- **Variants** (the binary's suffix):
  - `.opt`: `-O3` with debug symbols and `TRACING_ON=1`, so DPRINTF works.
    This is the default for development and tests.
  - `.debug`: `-O0 -ggdb3`, asserts and tracing on. Use it under gdb.
  - `.fast`: `-O3`, `NDEBUG`, tracing off. Fastest, but no DPRINTF and no
    asserts.
- **Reconfiguring.** Use KConfig instead of editing `build_opts/`:
  `scons setconfig build/X86 RUBY=y PROTOCOL=MESI_Two_Level`, or
  `scons menuconfig build/X86`. See `KCONFIG.md`. The values land in
  `env['CONF']`. C++ sees them through `#include "config/foo.hh"`, and
  config scripts through `m5.defines.buildEnv`.
- **IDE support:** `scons build/X86/compile_commands.json`.
- **Out-of-tree sources:** `EXTRAS=/path1:/path2` adds external directories,
  each with its own `SConscript` and `Kconfig`.

## Note: `build-gem5.sh`

A bare `scons` works on the current hosts. `build-gem5.sh` is left over
from hosts that built with an Anaconda base env active, which clashed with
the system libraries (embedded Python, protobuf, HDF5). It falls back to
plain `scons` when there is no Anaconda. The full story is in CLAUDE.md at
commit 99aeb0d7f6, if it is ever needed again.
