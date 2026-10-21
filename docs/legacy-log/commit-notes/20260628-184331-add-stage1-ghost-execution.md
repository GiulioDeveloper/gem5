# cpu-o3: Add Garfield Stage 1 ghost execution

- **Date:** 2026-06-28 18:43   ·   **Branch:** rbdev

## Goal

Stage 1 of the Garfield headroom plan (see `docs/garfield/README.md`): enable a
**ghost-execution datapath** in the O3 core where tagged uops consume **no OoO
issue-queue entry, no issue bandwidth, and no execution port**, while remaining
fully correct (they still execute, resolve, wake dependents, and retire in
order). Stage 1 tags **control (branch) uops**; the mechanism is stage-agnostic
so Stages 2/3 (memory-renamed, value-predicted uops) extend one policy function.
Gated by a config knob, **off by default**.

## Commits in this feature (on rbdev)

1. `cpu-o3: Add ghostPolicy for ghost-execution gating` — pure
   `ghostPolicy(isControl, cfg)` + GhostConfig + GTest.
2. `cpu-o3: Tag control uops as ghost at dispatch` — `IsGhost` flag,
   `ghostExec` param, IEW dispatch hook, `ghost.ghostInsts` stat, `se_run.py
   --ghost-exec`. (Inert: nothing reads the flag yet.)
3. `cpu-o3: Exempt ghost uops from IQ capacity` — `IQUnit::insert/remove`
   guards, `isFull()` never blocks a ghost, `residentGhosts`,
   `ghostIqEntriesAvoided`.
4. `cpu-o3: Exempt ghost uops from issue width and ports` —
   `scheduleReadyInsts` skips `getUnit()` and `total_issued` for ghosts;
   `ghostIssueSlotsAvoided` / `ghostFuAcquisitionsAvoided`; plus a `findIQ()`
   fix so a ghost gets a capable IQ even when the IQ is nominally full (mirrors
   the `isFull` override; without it a ghost dispatched into a non-ghost-full IQ
   asserted).

## Files

`src/cpu/o3/ghost_policy.{hh,cc,test.cc}` (new), `dyn_inst.hh` (IsGhost flag),
`BaseO3CPU.py` (ghostExec param), `iew.{hh,cc}` (ghostCfg + dispatch tagging),
`inst_queue.{hh,cc}` (capacity/issue/FU exemption + GhostStats + findIQ),
`SConscript` (source + GTest), `configs/garfield/arm/se_run.py` (--ghost-exec).

## Validation (FFT microbenchmark)

- **knob-off ≡ baseline**: every stat byte-identical to the pre-Stage-1 binary
  (verified at each task). The feature is truly inert when disabled.
- **Correctness keystone (full uncapped FFT, off vs on)**: both complete
  normally and commit **31,716,552** instructions with **identical** simOps and
  **identical guest output**. Ghosting changes only timing, never architecture.
- **Unit test**: `ghost_policy.test` (2 cases) passes.

## Measurement (full FFT, off vs on)

| Metric | knob-off | knob-on |
|---|---|---|
| numCycles | 12,565,425 | 12,584,481 (+0.15%) |
| IPC | 2.540 | 2.536 |

Freed by ghosting (knob-on): **7,994,629** IQ entry-cycles, **2,230,904** issue
slots, **2,230,904** FU acquisitions; **2,331,158** ghost uops (~7% of ops).

## Finding

Branch-ghosting frees substantial OoO resources at **essentially zero
performance cost** on FFT (−0.15%). FFT is memory / data-flow bound, so the
front-end OoO resources branches consume are not its bottleneck — freeing them
neither helps nor hurts at iso-OoO-size. (A capped 2M-inst warmup window showed
+1.3%, traced not to writeback contention — ghost writeback count is unchanged —
but to a small L1D-prefetcher timing perturbation; it washes out at full scale.)

Neutral perf + real freed resources is exactly the precondition for an
iso-performance OoO **downsizing** (power/area) win — to be confirmed by the
deferred OoO-size sweep. It also motivates the data-flow stages, which cover far
more uops and target the actual bottleneck.

## Out of scope (Stage 1, deliberately)

Writeback-bandwidth exemption; OoO-size/issue-width/FU sweeps; a real finite FIFO
ghost backend (Stage 1 is the infinitely-cheap accounting model); value
prediction / memory renaming (Stages 2/3 — the policy seam is in place).
