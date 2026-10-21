# cpu,configs: Improve CPU progress heartbeat (IPC, KIPS)

- **Date:** 2026-06-27 21:12   ·   **Branch:** rbdev

## Goal
Make the CPU progress heartbeat a reliable simulation-liveness signal in every
build variant, showing both IPC and a wall-clock host rate.

## Summary of changes
Rework `CPUProgressEvent::process()` into a single always-printed line so IPC
shows in every build variant (it was behind `#ifndef NDEBUG`), fix the IPC format
(`%0.8d` on a double → `%.3f`), and add a host rate (KIPS = simulated instructions
this interval per real second) via `base/time.hh`. Expose it from the garfield
driver with a `--progress-interval` flag (default `0Hz` = off) that sets
`BaseCPU.progress_interval`.

## Files changed
- `src/cpu/base.cc` — single always-printed heartbeat line; IPC format fix;
  host-KIPS computation via `time.hh`.
- `src/cpu/base.hh` — heartbeat state for the interval/host-rate computation.
- `configs/garfield/arm/se_run.py` — `--progress-interval` flag wiring
  `BaseCPU.progress_interval`.
