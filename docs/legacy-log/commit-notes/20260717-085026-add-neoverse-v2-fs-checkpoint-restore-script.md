# configs: Add Neoverse V2 FS checkpoint restore script

- **Date:** 2026-07-17 08:50   ·   **Branch:** rbdev

## Goal
Give the FS+KVM SPEC checkpoints the same detailed-simulation entry point that
se_run.py provides for SE mode: restore a checkpoint into the Neoverse V2 core +
cache hierarchy and run a warmup/measured region, with the Garfield MRN and
ghost-exec knobs exposed.

## Summary of changes
New configs/garfield/arm/fs_run.py, the FS sibling of se_run.py. It reuses the
existing definitions rather than restating them: the core comes from
`neoverse_v2.NeoverseV2` and the cache hierarchy from
`cache_hierarchy.NeoverseV2CacheHierarchy` -- no microarchitecture parameters are
duplicated. Only restore-specific behaviour is added:

  * `cpu_id=0` on both cores (m5.switchCpus/BaseCPU::takeOverFrom asserts the
    swapped-in and swapped-out cores share a cpuId);
  * `NeoverseV2RestoreProcessor`: a SwitchableProcessor primed with the ATOMIC
    core active so the checkpoint deserializes into it, then switched to the
    Neoverse V2 core (which flips the board to timing mode and hands over
    architectural state);
  * `RestoreNeoverseV2CacheHierarchy`: the same hierarchy, but rebinding each L1I
    FetchDirectedPrefetcher's cpu/MMU pointers to the detailed core, since those
    do not migrate across the switch and would otherwise train off the ATOMIC
    settle core.

Workload parameters are auto-loaded from the SimPoint invocation manifest, so a
run needs only the checkpoint, benchmark and inv.

## Files changed
- `configs/garfield/arm/fs_run.py` — new FS checkpoint restore runner: NeoverseV2 core/cache reused from neoverse_v2.py + cache_hierarchy.py, atomic-primed switchable restore, FDP rebind, MRN/ghost-exec knobs, warmup + measured region and a stats summary.
