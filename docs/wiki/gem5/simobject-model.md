---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
tags: [gem5, simobject, python, c++]
---

# The SimObject model

Every simulated component is a **SimObject**, declared in two places that
the build stitches together. Adding or changing one means editing three
things: the `.py` description, the C++ class, and the `SConscript`. A
parameter added in Python does not exist for C++ until the generated
struct is rebuilt.

1. **Python description.** A `*.py` file (e.g. `src/cpu/BaseCPU.py`) with a
   class derived from `SimObject` (`src/python/m5/SimObject.py`). It declares
   `type`, `cxx_class`, `cxx_header`, parameters `Param.<Type>(...)` /
   `VectorParam.<Type>` (`src/python/m5/params.py`) and ports
   (`RequestPort` / `ResponsePort`). It holds no behaviour.
2. **C++ implementation.** `.hh`/`.cc` (e.g. `src/cpu/base.{hh,cc}`) with a
   class derived from the C++ `SimObject` (`src/sim/sim_object.hh`). **Its
   constructor takes `const <Name>Params &`**, and the `PARAMS(<Name>)` macro
   gives a typed `params()` accessor.
3. **Build glue.** Register the `.py` in the directory's `SConscript` with
   `SimObject('Foo.py', sim_objects=['Foo'], enums=['Bar'])`. At build time
   `build_tools/` generates `build/<CONFIG>/params/Foo.hh` (the `FooParams`
   struct and a `create()` factory), `enums/`, and the pybind11 glue.

At run time the Python config instantiates `Foo(...)`, pybind11 marshals the
parameters into `FooParams`, and `FooParams::create()` calls
`new Foo(params)`. See [[scons-codegen]] for the build side and
[[python-layers]] for the config side.

Examples in this fork: `ArmLinuxTaskTracer` ([[task-tracer]]) and
`InfiniteBTB` ([[infinite-btb-model]]).
