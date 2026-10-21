# configs: Share sim knobs between fs_run and se_run

- **Date:** 2026-07-20 11:30   ·   **Branch:** rbdev

## Goal
fs_run.py and se_run.py declared the same ~110 lines of argparse knobs and
the same knob-application logic verbatim, so the two drivers could silently
drift apart. Pull everything that describes the *machine* into one module and
leave only the run-mode-specific knobs in each driver.

## Summary of changes
New `sim_opts.py` owns `MEM_FACTORIES`, `--clk-freq`/`--mem-type`/`--mem-size`,
`--progress-interval`, the three prefetcher-ablation flags, and the nine
garfield flags (`--ghost-exec`, `--use-mrn`, `--mrn-*`), plus the helpers that
consume them: `add_common_args()`, `make_memory()`, `cache_kwargs()`,
`make_mrn()`, `apply_core_knobs()` and `describe()`.

`cache_kwargs()` returns a dict rather than a built hierarchy so fs_run can
still feed the kwargs to its `RestoreNeoverseV2CacheHierarchy` subclass.
`--mem-size` is parameterized (SE 4GiB, FS 16GiB-must-match-checkpoint) since
that is the one default the two modes genuinely disagree on.

Verified no behaviour change: the CLI flag sets are byte-identical before and
after (24 for se, 26 for fs), and `config.ini` regenerated for both baseline
and MRN-mode-C against cpt.721.gcc_r.0.3 matches the config from the validated
50M sweep on every line except the two that embed `--outdir`.

fs_run.py also picks up three pre-existing clang-format/black fixes that the
formatter applies to any touched file.

## Files changed
- `configs/garfield/arm/sim_opts.py` — new module holding the shared knobs and the helpers that turn them into objects.
- `configs/garfield/arm/fs_run.py` — drop the duplicated knobs; call `sim_opts.add_common_args()` and the helpers. 602 -> 466 lines.
- `configs/garfield/arm/se_run.py` — same, keeping `--binary`/`--args`/`--workload`/`--num-cores`/`--max-insts`. 310 -> 178 lines.
