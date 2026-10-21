# configs: Move virt_run onto shared sim_opts knobs

- **Date:** 2026-07-26 17:30   ·   **Branch:** rbdev

## Goal
Bring the QEMU-virt restore script onto the same shared-knob surface as
fs_run.py and se_run.py: common knobs come from sim_opts.py; virt_run.py
defines only its QEMU-restore-specific arguments.

## Summary of changes
Deleted virt_run.py's duplicated argparser block (clk-freq, mem-type,
mem-size, progress-interval, prefetch/FDP ablations, ghost-exec, and the
entire stale MRN block -- which referenced parameters deleted in the
legacy-path amputation plus one that never existed on this branch, so
--use-mrn there had been broken) and its private MEM_FACTORIES map.
Now: sim_opts.add_common_args() in parse_args, apply_core_knobs() on the
detailed core, make_memory()/cache_kwargs() at board assembly, and
describe() in the banner -- identical wiring to fs_run.py. Virt-specific
args kept: restore-dir, gen-ref, disk-img, kernel, bootloader, release,
settle/warmup/detailed-insts, atomic-only, atomic-max-insts (the latter
two fresh from the ARM-box merge). Net -46 lines. This also closes the
legacy-deletion review's outstanding finding on virt_run.py.

Verified: parser exercised end-to-end via gem5.opt --help (all virt +
shared args present); no dead-param references remain anywhere in
configs/.

## Files changed
- `configs/garfield/arm/virt_run.py` — shared knobs via sim_opts; MRN block, duplicated machine knobs, and MEM_FACTORIES removed.
