---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
  - TESTING.md
tags: [gem5, testing]
---

# Testing gem5

gem5 has three levels of test: C++ unit tests (GoogleTest, `*.test.cc` next
to the source), Python unit tests (run through a gem5 binary), and
system-level regressions (`ext/testlib`, gem5-specific parts in
`tests/gem5`). For checks specific to this fork's measurement
infrastructure (no perturbation, determinism, landing), see
[[validation-checks]].

```sh
# C++ unit tests
scons build/ALL/unittests.opt                    # build and run all
scons build/ALL/base/bitunion.test.opt           # build one test...
./build/ALL/base/bitunion.test.opt               # ...and run it
./build/ALL/base/bitunion.test.opt --gtest_filter=BitUnionData.NormalBitfield

# Python unit tests (need a gem5 binary)
./build/ALL/gem5.opt tests/run_pyunit.py

# Regressions
cd tests
./main.py run                          # "quick" suite for X86/ARM/RISCV; builds gem5 first; hours
./main.py run --length=long
./main.py run -j$(nproc) -t 4          # -j compile threads, -t parallel suites
./main.py list -q --suites
./main.py run --skip-build --uid <SuiteUID>
./main.py rerun                        # only the suites that failed last time
```

Test resources (disk images, binaries) download into
`tests/gem5/resources/`. See `TESTING.md` for the full reference.
