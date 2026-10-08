# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

gem5 is a modular, event-driven computer-system architecture simulator. The C++ core implements the
simulated hardware; Python drives configuration and the simulation loop (the gem5 binary embeds a
CPython interpreter). Understanding the **Python↔C++ boundary** is the key to working here.

## This fork: the Garfield project

This is a private research fork (branch `rbdev`). The active research effort is **Garfield** —
exploring whether accurately-speculated (noncritical) instructions can be executed *lazily* on a
cheap in-order backend, freeing the scarce out-of-order resources of a Neoverse V2 core for the
instructions that actually need them. Before any design work, the idea is gated on a "ghost
execution" **headroom study**. **Read [`docs/garfield/README.md`](docs/garfield/README.md)** for the
goal, the core hypothesis, the headroom methodology (assume *predicted = correct*), the three-stage
plan (branches → memory renaming → value prediction), and the pitfalls — before touching any
Garfield-related code.

## Building

gem5 uses **SCons**. Builds are parameterized by a config name that selects ISA(s) and the Ruby
coherence protocol at *compile time* — there is no runtime ISA/protocol switching.

> **On hosts without Anaconda (e.g. gferraro's workstation), a bare `scons` works** with the system
> Python and protobuf. Only hosts that run with the Anaconda base env active (the original dev host
> and the cluster) need `./build-gem5.sh`. See **Host build environment (Anaconda)** at the end of
> this section.

```sh
scons build/ALL/gem5.opt -j$(nproc)     # all ISAs, optimized binary (most common dev build)
scons build/X86/gem5.opt -j$(nproc)     # single ISA (faster compile)
scons build/RISCV/gem5.debug            # RISC-V, debug build
```

- `build/<CONFIG>/` — the build directory. `<CONFIG>` must match a file in `build_opts/`
  (e.g. `ALL`, `X86`, `ARM`, `RISCV`, `NULL`, `X86_MESI_Two_Level`, `ARM_MOESI_hammer`). Each
  `build_opts/` file is a KConfig **defconfig** setting `USE_*_ISA`, `RUBY`, `PROTOCOL`, etc.
- Build **variants** (the binary suffix):
  - `.opt` — `-O3` **with** debug symbols and `TRACING_ON=1` (DPRINTF works). Default for dev/tests.
  - `.debug` — `-O0 -ggdb3`, asserts + tracing on. Use under gdb.
  - `.fast` — `-O3`, `NDEBUG`, **tracing off**. Fastest; no DPRINTF, no asserts.
- Reconfigure a build dir with KConfig instead of editing `build_opts/`:
  `scons setconfig build/X86 RUBY=y PROTOCOL=MESI_Two_Level` · `scons menuconfig build/X86`.
  See `KCONFIG.md`. Config values land in `env['CONF']`, are exposed to C++ as `#include "config/foo.hh"`,
  and to config scripts via `m5.defines.buildEnv`.
- IDE intellisense: `scons build/X86/compile_commands.json` generates `compile_commands.json`.
- Out-of-tree source: the `EXTRAS=/path1:/path2` variable pulls external dirs (with their own
  `SConscript`/`Kconfig`) into the build without modifying the tree.

### Host build environment (Anaconda)

**Only relevant on hosts that build with the Anaconda base env active** (the original dev host and
the cluster). Anaconda collides with the system dev libraries there, and `build-gem5.sh` pins the
toolchain to Anaconda consistently. Hosts without Anaconda (no `~/anaconda3`) just run `scons`
directly; `build-gem5.sh` detects this and falls back to the system toolchain. The underlying
issues and their committed fixes (useful if the toolchain ever changes or a build breaks):

- **Embedded Python** — gem5 links Anaconda's `libpython3.13.so.1.0`, which lives only in
  `~/anaconda3/lib` and is built without an rpath. It must be on the loader path at *build* time
  (configure links a test binary). `SConstruct`'s `config_embedded_python()` now embeds an **rpath**
  to that dir, so the binary *runs* without `LD_LIBRARY_PATH` — important for Slurm batch shells,
  which don't source `~/.bashrc`. The co-located libprotobuf/abseil are covered by the same rpath.
- **protobuf** — use Anaconda's `protoc` (5.29.3) **and** its headers/lib together (`PROTOC` +
  `PKG_CONFIG_PATH`). Do **not** use the system protobuf: a stale 2019 protobuf **3.3.0** under
  `/usr/local` (headers, libs, `.pc`, and `/usr/local/bin/protoc`) shadows the apt 3.21.12 headers,
  because `/usr/local/include` precedes `/usr/include` and apt's `.pc` adds no `-I`.
- **HDF5** — disabled by default in `src/base/stats/SConsopts`. Anaconda's `libhdf5_cpp` is on the
  link line (via `-L~/anaconda3/lib`) and shadows the system one that `hdf5.cc` compiled against →
  undefined-symbol link errors. It's an optional stats format; set `GEM5_ENABLE_HDF5=1` to re-enable
  where a consistent HDF5 exists.
- **scons two-pass** — after `--config=force`, the first pass can compile everything and exit 0
  *without linking* `gem5.opt`; a second pass links it. `build-gem5.sh` runs the second pass for you.

**On the cluster**, rebuild with `ANACONDA=/cluster/path/anaconda3 ./build-gem5.sh` — the rpath is
recomputed at build time, so the binary runs there with no env setup. Don't copy the binary between
hosts (rpath + glibc/libstdc++ skew); rebuild instead.

## Testing

```sh
# C++ unit tests (GoogleTest), keyed off *.test.cc files:
scons build/ALL/unittests.opt                       # build + run all unit tests
scons build/ALL/base/bitunion.test.opt              # build one test binary...
./build/ALL/base/bitunion.test.opt                  # ...then run it
./build/ALL/base/bitunion.test.opt --gtest_list_tests
./build/ALL/base/bitunion.test.opt --gtest_filter=BitUnionData.NormalBitfield

# Python unit tests (need a gem5 binary first):
./build/ALL/gem5.opt tests/run_pyunit.py

# System-level / regression tests (ext/testlib framework, gem5-specific code in tests/gem5):
cd tests
./main.py run                                       # "quick" suite for X86/ARM/RISCV (builds gem5 first; hours)
./main.py run --length=long                         # or very-long
./main.py run -j$(nproc) -t 4                        # -j = compile threads, -t = parallel suites
./main.py list -q --suites                          # list suite UIDs
./main.py run --skip-build --uid <SuiteUID>          # run one suite (must use --skip-build)
./main.py rerun                                      # rerun only suites that failed last run
```

See `TESTING.md`. Test resources (disk images, binaries) auto-download to `tests/gem5/resources/`.

## Style & contribution conventions

- **Branch off `develop`, not `stable`.** `stable` only holds releases. (This checkout may be on `stable`.)
- **pre-commit is mandatory** and mirrors CI: `pip install pre-commit && pre-commit install`. It runs
  black, isort, `clang-format` (`util/run-git-clang-format.py`), the gem5 style checker
  (`util/git-pre-commit.py`), and a commit-message checker (`util/git-commit-msg.py`).
- **C++**: 79-col lines, 4-space indent (no tabs), no trailing whitespace. `UpperCamelCase` classes,
  `lowerCamelCase` methods/members, `_leadingUnderscore` for members exposing a public accessor,
  `snake_case` locals and function params. `.clang-format` is authoritative.
- **Python**: black with `line-length = 79`, isort, PEP 8 naming. When a file's existing convention
  differs, match the surrounding code.
- **Commit messages**: header is `tag[,tag]: short description`, **≤65 chars**. Tags name the modified
  component(s) and must come from `MAINTAINERS.yaml` (e.g. `arch-riscv:`, `mem-cache:`, `stdlib:`,
  `configs:`, `cpu:`, `misc:`, `tests:`). Body lines ≤72 chars. See `CONTRIBUTING.md`.

## Architecture: the SimObject model (most important concept)

Every simulated component is a **SimObject**, declared in *two* places that the build system stitches
together. Get this contract right and most else follows:

1. **Python description** — a `*.py` file (e.g. `src/cpu/BaseCPU.py`) with a class inheriting
   `SimObject` (`src/python/m5/SimObject.py`). It declares metadata `type`, `cxx_class`, `cxx_header`,
   configuration `Param.<Type>(...)` / `VectorParam.<Type>` (see `src/python/m5/params.py`), and ports
   (`RequestPort`/`ResponsePort`). It does **not** contain behavior.
2. **C++ implementation** — `.hh`/`.cc` (e.g. `src/cpu/base.{hh,cc}`) with a class inheriting the C++
   `SimObject` (`src/sim/sim_object.hh`). **Its constructor must take `const <Name>Params &`** and it
   uses the `PARAMS(<Name>)` macro to get a typed `params()` accessor.
3. **Build glue** — register the `.py` in that directory's `SConscript` with
   `SimObject('Foo.py', sim_objects=['Foo'], enums=['Bar'])`. At build time `build_tools/` scripts
   generate `build/<CONFIG>/params/Foo.hh` (the `FooParams` struct + a `create()` factory),
   `enums/`, and pybind11 glue. The flow at runtime: Python config instantiates `Foo(...)` →
   pybind11 marshals params into `FooParams` → `FooParams::create()` calls `new Foo(params)`.

So **adding/changing a SimObject means editing the `.py`, the C++ class, and the `SConscript`** — a
param added in Python is invisible until it also appears in the C++ struct (regenerated by rebuilding).

## Architecture: build-system code generation

`SConscript` files (one per source dir) register everything via exported helpers — new files are
invisible to the build until registered:

- `Source('x.cc', tags=[...])` — a C++ source file. `SimObject(...)` — see above.
- `DebugFlag('Foo', "desc")` / `CompoundFlag('All', ['A','B'])` — generates `debug/Foo.hh`; enables
  `DPRINTF(Foo, ...)` and the runtime `--debug-flags=Foo` switch.
- `GTest('x.test', 'x.test.cc', 'x.cc')` — a unit test (the `*.test.cc` convention).
- `PySource('pkg', 'x.py')` — Python marshalled into the binary. `SourceLib`, `Executable`, `ProtoBuf`.
- `SConsopts` files run feature detection (`gem5_scons.Configure`) before `SConscript` files, populating
  `env['CONF']` so sources can be registered conditionally.

Build infrastructure lives in `site_scons/gem5_scons/` (builders, KConfig wrapper, source tagging) and
generators in `build_tools/`. Generated C++ headers/source live under `build/<CONFIG>/` — never edit them.

## Architecture: the two Python layers

- **`m5`** (`src/python/m5/`) — low-level bindings and the simulation kernel interface.
  `import m5`; `m5.instantiate()` builds the C++ object tree from the Python config (once);
  `m5.simulate()` runs the event loop and returns an exit event. `src/python/m5/objects/` exposes the
  generated SimObject Python classes.
- **`gem5`** (`src/python/gem5/`) — the **standard library** ("stdlib"), the modern way to write configs.
  Compose a system from `Board`, `Processor`, `CacheHierarchy`, and `MemorySystem` components
  (abstract bases under `src/python/gem5/components/`), then drive it with the `Simulator` class
  (`src/python/gem5/simulate/simulator.py`), which wraps `m5.instantiate()`/`m5.simulate()` and an
  exit-event handler loop. `obtain_resource("...")` (`src/python/gem5/resources/`) downloads/caches
  binaries, kernels, and disk images from resources.gem5.org.

**Running a simulation** = running a config *script through the gem5 binary* (not via `python`):

```sh
./build/X86/gem5.opt [--debug-flags=Exec -d m5out] <config.py> [script args]
```

`gem5.opt` embeds CPython and `exec`s the config script. Workloads come in two modes set on the board:
**SE** (syscall emulation, `set_se_binary_workload(...)`) runs a bare binary with syscalls trapped to
gem5; **FS** (full system, `set_kernel_disk_workload(...)`) boots a real kernel + disk image.

- `configs/example/gem5_library/` — **current** stdlib examples (start here).
- `configs/learning_gem5/` — tutorials. `configs/deprecated/` — legacy direct-instantiation style (avoid).

## Architecture: simulation core, ISAs, memory

- **Event-driven core** (`src/sim/eventq.hh`): a global `EventQueue` orders `Event`s by `(Tick, priority)`.
  `curTick()` is the global clock. SimObjects `schedule()` events; common helpers are
  `EventFunctionWrapper` and `MemberEventWrapper<&Cls::method>`. `Tick`/`Cycles` are in `src/base/types.hh`.
- **Ports & packets** (`src/mem/port.hh`, `src/mem/packet.hh`): components connect `RequestPort`↔
  `ResponsePort`; memory traffic is `Packet`s over Atomic/Timing/Functional protocols. `SimObject::getPort`
  resolves a named port. `src/base/` holds reused infra: `statistics::Group` (stats), `DPRINTF` tracing
  (`src/base/trace.hh`), `panic`/`fatal`/`warn`, `AddrRange`, serialization (`Serializable`/`Drainable`).
- **ISAs** (`src/arch/<isa>/`, ISAs: `arm mips power riscv sparc x86 amdgpu null`): instruction decode and
  semantics are written in a custom `.isa` DSL (`src/arch/<isa>/isa/*.isa`) compiled to C++ by
  `src/arch/isa_parser/`. To add/modify an instruction, edit the `.isa` `decode` tree / `format` blocks and
  rebuild. Per-ISA files follow a pattern (`isa.cc`, `decoder.cc`, `tlb.cc`, `process.cc`, `faults.cc`);
  ISA-agnostic interfaces live in `src/arch/generic/`.
- **Memory system** has two stacks:
  - **Classic** (`src/mem/cache/`, `src/mem/*xbar*`, `src/mem/mem_ctrl.*`) — composable caches/crossbars,
    simple coherence. Used by the stdlib classic hierarchies (`components/cachehierarchies/classic/`).
  - **Ruby** (`src/mem/ruby/`) — detailed coherence. Protocols are written in the **SLICC** DSL
    (`.sm` state-machine + `.slicc` files in `src/mem/ruby/protocol/`) and compiled to C++ by
    `src/mem/slicc/`. The active protocol is fixed at build time by `PROTOCOL` (e.g. `MESI_Two_Level`,
    `MOESI_hammer`, `CHI`) — which is why protocol-specific `build_opts/` configs like
    `X86_MESI_Two_Level` exist. To change a protocol, edit its `.sm` files and rebuild that config.

## Source tree

`src/` (C++ core, Python wrappers, stdlib) · `build_opts/` (build configs) · `build_tools/` (codegen) ·
`site_scons/` (SCons infra) · `configs/` (example config scripts) · `tests/` (regressions; framework in
`ext/testlib/`) · `ext/` (bundled third-party) · `util/` (tooling: `m5` guest util, trace decoders,
checkpoint upgraders, clang-format/commit hooks) · `system/` (firmware sources).

**Run scripts:** put run/launch scripts and the configs used for runs in `runs/` (gitignored) so
they can be vetted and run manually — keep them out of the tracked tree. Use `/tmp` only for
throwaway build artifacts.
