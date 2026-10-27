---
type: pitfall
status: open
updated: 2026-10-27
sources:
  - "[[2026-10-23-rubocop-15g-cache-btb-tlb]]"
  - runs/rubocop-15G/normal/stall/
tags: [guest, kernel, el2, hvc, smccc, trng, hang, checkpoint]
---

# The guest hangs in the EL2 hyp stub at its first RNG reseed

> [!warning] Provisional: to investigate
> The hang is observed (four of six rubocop runs, same tick), but the
> explanation below is a working hypothesis from one checkpoint's PC
> trace, not a confirmed root cause. Not yet done: reproduce it on other
> checkpoints, confirm in the guest that the HVC is the TRNG call (the
> SMCCC function ID in x0), see why the stub loops (an exception taken
> again on every pass is a guess), and test a fix. Until then, treat the
> mechanism, the "first RNG reseed" timing and the fix options as open,
> and cutting the hang off ([[long-runs#3. Cut off a guest stall]]) as a
> workaround, not a resolution.

**The trap:** a long restore of an agentic checkpoint stops doing useful
work a fixed simulated time after the restore (tick ≈ 4.6228e12 for
rubocop-13560 cpt.0) and never recovers. gem5 keeps running at ~0.008 IPC
and ~22K instructions/s, the progress line looks alive, the task tracer
goes silent, and `--detailed-insts` is reached only after many more hours
of meaningless instructions. Nothing errors. The ROB-head watchdog does
not fire because instructions keep committing ([[simulation-hangs]]).

## Likely mechanism (hypothesis from the PC trace, 2026-10-25)

1. `crng_reseed`, the kernel RNG's periodic reseed, runs as delayed work in
   an unbound kworker (`kworker/u2:N`), on a timer. Hence the same
   simulated time in every configuration, whatever the guest was doing.
2. It calls `extract_entropy` → `arch_get_random_seed_longs`, which on
   arm64 asks the firmware TRNG through SMCCC with the conduit from
   `arm_smccc_1_1_get_conduit`: an **HVC**. The checkpoints were made
   under KVM, which implements the TRNG call, so the guest found it
   available at boot.
3. Under gem5 the HVC traps to EL2, where the kernel's own hyp stub is
   installed (`__hyp_stub_vectors`, link address `0xffff800081068000`,
   physical `0x41068000`). Execution goes to +0x400 (synchronous from a
   lower EL), falls through the stub's function checks, and ends at +0x200
   (synchronous at the current EL), where it commits `adrp; add` forever:
   720M iterations, the whole 1.44G-instruction stall of the `normal` run.
   Probably an exception taken again on every pass (no `ExecFaulting` in
   the trace to show it).

What is established is only the observation: seen in all four rubocop
runs that reached it
([[2026-10-23-rubocop-15g-cache-btb-tlb]]): the last tracer event is always a
switch into `kworker/u2:2` or `kworker/u2:3` at 4.6227–4.6228e12.

## How to spot it

- The task trace's last event is long before the end of the run.
- The progress line shows IPC ≈ 0.008 with a constant ~2,500 instructions
  per 100 µs.
- The PC trace (or an Exec trace) shows PCs around `0x4106_8xxx`.

## Consequences

- Any detailed or atomic run that crosses a checkpoint's next reseed
  deadline measures this loop. 400M-instruction windows last 0.1–0.5
  simulated seconds, so they hit it only if they start near the deadline;
  long runs hit it for certain (the reseed interval grows to 60 s).
- The deadline depends on the checkpoint's uptime, so it differs per
  checkpoint.

## Fix options (not done)

- Make the guest not use the TRNG HVC: e.g. a kernel without
  `CONFIG_ARM_SMCCC_TRNG`-style arch seeding, or a boot where gem5's
  firmware/PSCI node reports no TRNG; the checkpoint's probed state would
  have to change, so likely new checkpoints.
- Implement the SMCCC TRNG call (or return NOT_SUPPORTED) for HVC at EL2 in
  gem5, so the stub is not reached.
- Meanwhile (workaround): cut analyses at the last tracer event and stop
  runs that go past it (`analysis_scripts/tasktrace/split_stall.sh`).
