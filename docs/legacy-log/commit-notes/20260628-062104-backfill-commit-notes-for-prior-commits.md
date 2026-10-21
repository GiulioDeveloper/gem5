# doc: Backfill commit-notes for prior commits

- **Date:** 2026-06-28 06:21   ·   **Branch:** rbdev

## Goal
Propagate the history of this fork to the parallel clones. The 10 commits made
before the commit-notes convention existed had no notes; without them, a clone
that pulls this branch can't get the catch-up briefing the `git-pull` skill
provides. Backfill a note for each so the whole project history is covered.

## Summary of changes
Add one note under `docs/commit-notes/` for each of the 10 prior commits authored
on this fork (`7ef5c6ac` … `dc0903ce`), each carrying that commit's real
header, date, and branch plus a Goal/Summary/Files-changed drawn from its message
and diff. These are added in this single commit rather than injected into the
original commits: embedding a note in a past commit would require rewriting
history (new SHAs for every commit), which would diverge the very clones this is
meant to serve. The notes propagate identically either way.

## Files changed
- `docs/commit-notes/20260627-122058-disable-hdf5-to-avoid-anaconda-libhdf5-cpp-link.md` — note for `scons: Disable HDF5 …` (7ef5c6ac).
- `docs/commit-notes/20260627-122128-embed-python-lib-dir-as-rpath-in-gem5-binaries.md` — note for `scons: Embed Python lib dir as rpath …` (d38ac1ab).
- `docs/commit-notes/20260627-122129-add-build-gem5-sh-wrapper-for-the-anaconda-build.md` — note for `scons: Add build-gem5.sh wrapper …` (e4d3f28f).
- `docs/commit-notes/20260627-122708-add-claude-code-setup-to-enable-ai-driven.md` — note for `misc: Add Claude Code setup …` (9d4de5a1).
- `docs/commit-notes/20260627-124736-ignore-runs-for-local-run-scripts-and-configs.md` — note for `misc: Ignore runs/ …` (3a920bc6).
- `docs/commit-notes/20260627-165244-add-garfield-arm-neoverse-v2-se-config.md` — note for `configs: Add garfield ARM Neoverse V2 SE config` (360b14ca).
- `docs/commit-notes/20260627-183429-add-missing-floatmultacc-fu-to-neoverse-v2.md` — note for `configs: Add missing FloatMultAcc FU …` (d46da4c2).
- `docs/commit-notes/20260627-184014-cover-aarch64-op-classes-in-neoverse-v2-fus.md` — note for `configs: Cover AArch64 op classes …` (131fbf79).
- `docs/commit-notes/20260627-202307-add-rob-head-deadlock-detector.md` — note for `cpu-o3,stdlib: Add ROB-head deadlock detector` (3efcd5b7).
- `docs/commit-notes/20260627-211217-improve-cpu-progress-heartbeat-ipc-kips.md` — note for `cpu,configs: Improve CPU progress heartbeat …` (dc0903ce).
