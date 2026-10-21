---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
tags: [gem5, python, stdlib, config]
---

# The two Python layers, and running a simulation

A simulation is a **config script run by the gem5 binary**, not by
`python`:

```sh
./build/ARM/gem5.opt [--debug-flags=Exec] [--outdir=runs/x] <config.py> [script args]
```

gem5 options (`--outdir`, `--debug-flags`, `--stats-file`) come before the
script, and the script's own options after it. `gem5.opt` embeds CPython and
`exec`s the script.

- **`m5`** (`src/python/m5/`) holds the low-level bindings and the kernel
  interface. `m5.instantiate()` builds the C++ object tree from the Python
  config, and can be called only once. `m5.simulate()` runs the event loop
  and returns an exit event. `src/python/m5/objects/` exposes the generated
  SimObject classes.
- **`gem5`** (`src/python/gem5/`) is the **standard library** ("stdlib"),
  the modern way to write configs. A system is composed from a `Board`, a
  `Processor`, a `CacheHierarchy` and a `MemorySystem`, whose abstract bases
  are under `src/python/gem5/components/`. The `Simulator` class
  (`src/python/gem5/simulate/simulator.py`) drives it: it wraps
  `m5.instantiate()` and `m5.simulate()` in a loop of exit-event handlers.
  `obtain_resource("...")` downloads and caches binaries, kernels and disk
  images from resources.gem5.org.
- **Workload modes:**
  - **SE** (syscall emulation, `set_se_binary_workload(...)`) runs a bare
    binary, with its system calls handled by gem5.
  - **FS** (full system, `set_kernel_disk_workload(...)`) boots a real
    kernel and disk image. Everything in the agentic work is FS, restored
    from checkpoints ([[checkpoints]]).
- **Examples:**
  - `configs/example/gem5_library/` holds the current stdlib examples.
  - `configs/learning_gem5/` holds the tutorials.
  - `configs/deprecated/` is the legacy style; avoid it.
  - This fork's drivers are in `configs/garfield/arm/` ([[neoverse-v2]]).
