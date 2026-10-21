---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
tags: [gem5, build, scons]
---

# Build-system code generation

Every source directory has an `SConscript` that registers its contents
through exported helpers. **The build does not see a new file until it is
registered there.**

| helper | registers |
|---|---|
| `Source('x.cc', tags=[...])` | a C++ source file |
| `SimObject('Foo.py', sim_objects=[...], enums=[...])` | a SimObject description ([[simobject-model]]) |
| `DebugFlag('Foo', "desc")`, `CompoundFlag('All', ['A','B'])` | generates `debug/Foo.hh`. Enables `DPRINTF(Foo, ...)` and `--debug-flags=Foo` (a gem5 option, given before the config script) |
| `GTest('x.test', 'x.test.cc', 'x.cc')` | a unit test ([[testing]]) |
| `PySource('pkg', 'x.py')` | Python marshalled into the binary |
| `SourceLib`, `Executable`, `ProtoBuf` | libraries, executables, protobuf sources |

`SConsopts` files run feature detection (`gem5_scons.Configure`) before the
`SConscript` files. They fill `env['CONF']`, so sources can be registered
conditionally.

The infrastructure lives in `site_scons/gem5_scons/` (builders, the KConfig
wrapper, source tagging), and the generators in `build_tools/`. Generated
C++ goes under `build/<CONFIG>/`. **Never edit the generated files.**
