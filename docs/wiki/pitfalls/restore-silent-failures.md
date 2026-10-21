---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[raw/external/2026-10-21-agentic-checkpoints-README]]"
tags: [checkpoints, restore, correctness]
---

# Restores that "work" and give wrong numbers

From the checkpoint archive's caveats ([[raw/external/2026-10-21-agentic-checkpoints-README]]).
None of these errors out.

1. **`--release kvm-host` must match the capture** (KVM). A mismatch
   restores and gives plausible, wrong numbers.
2. **The 16-bit ASID fix is mandatory** (fork commit 8d0dafc815). The
   capture CPU reports 16-bit ASIDs, while gem5 defaulted to 8-bit: any two
   address spaces sharing a low ASID byte (about one pair in 256) became one
   to the TLB, and a process executed another's pages (found as a SIGSEGV
   in the replay driver). Worse with long runs and many processes, i.e.
   agentic workloads. `virt_run.py` sets `board.have_large_asid_64 = True`.
3. **Keep each checkpoint's disk delta** (`cpt.<i>/board.realview.vio.vio.image.cow`).
   Without it the guest silently reads build-time file contents.
4. **Preserve hard links when copying** (`rsync -aHS`); the `store*.pmem`
   pairs are one inode.
5. **`mem_size` is a restore invariant** (16 GiB, 1 vCPU): changing it is
   fatal, at least.
6. **Uniform IPC across different tasks is a corruption signature**: it
   happened twice (a FEAT_DIT kernel storm at ~0.47, a PAuth writeback bug at
   ~0.48–0.50). Real spread: IPC 0.35–1.57 across checkpoints, up to 0.86
   within one task.
7. **Always `--progress-interval 10kHz`**, so a stalled restore shows.
8. **The replay is unpaced** (no model-wait idle): fine for compute, but
   not a deployed duty cycle ([[agentic-suite]]).
9. **GIC active-priority registers are not restored**: four dumps were
   taken with an interrupt active (fastlane-20958/cpt.0, gin-2121/cpt.2,
   gin-2121/cpt.4, ripgrep-2209/cpt.4); low severity, but know it before
   studying interrupt behaviour there.
10. **gem5 does not stop on a guest kernel panic** (empty symbol table), so
    require a positive guest signal: the landing task ([[validation-checks]]),
    `RPOINT_REPLAY_ROUND` markers advancing, no `undefined instruction`
    warnings.

Garfield hit the same class of problem in FS restores (see
[[garfield-lessons]]).
