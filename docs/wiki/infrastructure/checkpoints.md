---
type: howto
status: current
updated: 2026-10-21
sources:
  - "[[raw/external/2026-10-21-agentic-checkpoints-README]]"
  - "[[legacy-log/agentic/task-tracing-guide]]"
  - configs/garfield/arm/virt_run.py
  - configs/garfield/arm/fs_run.py
tags: [checkpoints, restore, fs]
---

# Checkpoints and restores

**Where:** outside the repo, in `/home/snapshots/gem5-ckpts` (every run
script reads the root from `CKPTS`):

| suite | path | restore script |
|---|---|---|
| [[agentic-suite]] | `rpoint_ckpts/agentic/` (`images/`, `kernel/`, `bootloader/`, `checkpoints/agentic-<task>/cpt.<i>/`) | `configs/garfield/arm/virt_run.py` (QEMU-virt board) |
| [[spec-cpu-2026]] | `fs_ckpts/spec26/` (`ckpts/<bench>/<inv>/cpt.*`, `restore_resources/`) | `configs/garfield/arm/fs_run.py` (VExpress board; kernel through `GEM5_RESOURCE_DIR`) |

Both run the same guest kernel binary (same md5), so the [[task-tracer]]
works on both.

## Restore flow (both scripts)

Prime the **atomic** core active → `m5.instantiate(<checkpoint>)` →
`--settle-insts` on atomic → switch to the [[neoverse-v2]] O3 core →
`--warmup-insts` (unmeasured) → `m5.stats.reset()` → `--detailed-insts`
(measured, optionally in [[stats-blocks]]) → dump. `virt_run.py` adds
`--atomic-only` / `--atomic-max-insts` (trace only, fast) and
`--tail-insts` (back to atomic after the region, still traced). How to pick
the numbers: [[window-placement]], [[warmup-and-skip]].

The agentic common arguments:

```sh
AGENTIC=${CKPTS:-/home/snapshots/gem5-ckpts}/rpoint_ckpts/agentic
COMMON="--disk-img $AGENTIC/images/rpoint-ubuntu-24.04-v21.img \
  --kernel $AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0 \
  --bootloader $AGENTIC/bootloader/boot_v2_qemu_virt.arm64 \
  --release kvm-host --progress-interval 10kHz"
```

- `--kernel` and `--bootloader` must be real AArch64 ELFs (the vmlinux, not
  the `-Image`), although a restore uses neither: the memory image *is* the
  booted guest. The kernel symbol table in each `m5.cpt` is empty on
  purpose (KASLR), so expect `Kernel symbol table is empty` warnings, and
  **gem5 will not stop on a guest kernel panic**.
- Speeds: atomic about 1.6–1.9 MIPS; O3 about 95–200 KIPS.
- Each run holds the checkpoint's in-use guest memory, 2.5–22 GB
  ([[sweep-memory-exhaustion]]).

## Provenance and landing

Each `cpt.<i>/provenance.json` records the capture, including `landing`
(exception level, PC, task comm/pid, `kaslr_slide`) for 22 of the 27 local
`cpt.0`. The landing check ([[validation-checks]]) confirms a restore resumes
in that task. `board.terminal` shows the guest's `RPOINT_REPLAY_ROUND <n>`
markers ([[opencode-harness#Rounds]]).

## Restore mechanics

`fs_run.py` came from Garfield and `virt_run.py` reuses its machinery:
atomic core primed active, `cpu_id=0` on both cores, the L1I FDP prefetcher
rebound to the O3 core after the switch, only non-zero memory chunks
materialised on restore. Why each is needed:
[[garfield-lessons#FS restores]] (still used by both drivers).
A stuck restore: [[simulation-hangs]].

## Restore requirements

The checkpoints need this fork (the `QEMU_Virt` platform and the 16-bit
ASID fix, commit 8d0dafc815); stock gem5 cannot restore them. Several
mistakes restore "fine" and give wrong numbers:
[[restore-silent-failures]].
