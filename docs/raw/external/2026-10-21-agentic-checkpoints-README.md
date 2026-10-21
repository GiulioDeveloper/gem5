# Agentic RPoint checkpoints — SWE-bench-Multilingual

gem5 full-system checkpoints of an **OpenCode coding agent** (GLM-5.2 via OpenRouter)
solving SWE-bench-Multilingual tasks, captured with RPoint (QEMU/KVM → gem5) on an AWS
Graviton3 `c7g.metal` box, 2026-09-20/21.

The agent is **replayed model-free** inside the guest: the live episode was recorded once,
and the checkpointed run serves the recorded model responses back from disk. No network, no
provider, no credentials — what runs under gem5 is the agent's *execution*: the harness, the
tool calls, the compilers and test suites it drives.

```
agentic/
├── README.md                       this file
├── images/
│   ├── rpoint-ubuntu-24.04-v21.img the ONE guest image every checkpoint restores against
│   ├── ...img.tasks.json           the 36 trajectories the image carries
│   └── ...img.provision.log        the offline provisioning boot that built it
├── kernel/                         the 6.8.12 guest kernel (vmlinux + extracted Image)
├── bootloader/
│   └── boot_v2_qemu_virt.arm64     the QEMU-virt bootloader, prebuilt from the fork
└── checkpoints/
    └── agentic-<task>/
        ├── campaign.json           the capture: seed, planned vs actual offsets, trigger
        ├── _boot/serial.log        the guest console of the capture run
        ├── _window/timing.tsv      the timing run that measured this task's agent window
        └── cpt.<i>/                one checkpoint
```

## What is here

**27 tasks, 132 checkpoints**, every one restored and validated in gem5 before archiving
(details under "Provenance"). Nine languages: C, C++, Rust, Go, Java, PHP, Ruby,
JavaScript, TypeScript.

Each task's dumps are **stratified over its agent loop**: the loop length was measured per
task first (`_window/timing.tsv`), then 5 dumps were placed at random offsets spread over
that window, in *guest running time*. Startup and grading are deliberately excluded — the
window runs from the agent's first tool round (`RPOINT_REPLAY_ROUND 1`) to the moment the
harness exits (`RPOINT_REPLAY_AGENT_END`).

Agent loops span **7.1 s to 1589.6 s** — a factor of 224 — which is why the window is
measured per task rather than assumed.

**Three tasks have 4 dumps, not 5** (`nushell-13831`, `preact-3763`, `immutable-js-2006`):
that run's agent loop ended before the last offset, so sampling stopped. Those dumps are
sound; there are simply fewer of them. `campaign.json` records the run as `complete-short`.

## Restoring one

You need the **gem5 fork**, not upstream:

```
repo    git@github.com:rahulbera/gem5.git
commit  8d0dafc8154f039cffa0924fc0e25a9fdabb39ba      <- pin THIS, not the branch
tree    09244ef41ce346a934e2ad4a05f7fe93cf9d6ad8      <- what actually matters
        ("arm: restore QEMU-virt checkpoints with 16-bit ASIDs", 2026-09-20)
base    gem5 25.1.0.1
```

**Use the commit, not `rbdev`.** That branch moves; these 132 checkpoints were captured and
validated against exactly the tree above, and the restore contract is version-sensitive in
ways that fail silently (see caveats 1, 2 and 5). To get it:

```sh
git clone git@github.com:rahulbera/gem5.git && cd gem5
git checkout 8d0dafc8154f039cffa0924fc0e25a9fdabb39ba
git rev-parse HEAD^{tree} # must print 09244ef41ce346a934e2ad4a05f7fe93cf9d6ad8

CC=gcc-14 CXX=g++-14 scons build/ARM/gem5.opt
```

*Earlier copies of this README pinned commit `7c41a81c138ac2dc9562366644de8fbf5df25792`.* On
2026-09-25 that commit was rewritten to edit **only its message**, and `7c41a81` is no longer
reachable from any branch. `8d0dafc` has the identical tree (`09244ef4…`), so everything
validated against `7c41a81` holds for `8d0dafc`. Check the tree hash, not the commit hash.

**The QEMU-virt bootloader is not committed** (only its source, `boot.S` + `makefile`). A
prebuilt copy is in `bootloader/`, and `virt_run.py` refuses to start without one. To rebuild
it (on an x86 host, install the cross compiler first: `apt install gcc-aarch64-linux-gnu`):

```sh
make -C system/arm/bootloader/arm64 boot_v2_qemu_virt.arm64
```

Two fork-specific things matter: the `QEMU_Virt` platform model (upstream has no machine
matching what QEMU's `virt` presents), and the ASID fix below. **Stock gem5 cannot restore
these checkpoints**, and neither can a later `rbdev` unless you have checked that nothing in
the restore path changed.

```sh
GEM5=/path/to/gem5
CFG=$GEM5/configs/garfield/arm/virt_run.py          # in the fork, not in gem5-infra
AGENTIC=/path/to/agentic                            # this directory
IMG=$AGENTIC/images/rpoint-ubuntu-24.04-v21.img
KERNEL=$AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0   # the vmlinux, NOT the -Image
BOOTLOADER=$AGENTIC/bootloader/boot_v2_qemu_virt.arm64

$GEM5/build/ARM/gem5.opt --outdir=OUT $CFG \
    --restore-dir $AGENTIC/checkpoints/agentic-gin-2121/cpt.0 \
    --disk-img $IMG \
    --kernel $KERNEL \
    --bootloader $BOOTLOADER \
    --release kvm-host \
    --progress-interval 10kHz \
    --settle-insts 0 --warmup-insts 1000000 --detailed-insts 20000000
```

**`--kernel` and `--bootloader` must name real files, even though a restore uses neither
file's contents.** The checkpoint's memory image *is* the booted guest: DRAM (`store1.pmem`)
and flash bank 0, where gem5 places the bootloader (`store0.pmem`), both come back from the
checkpoint. gem5 writes
the kernel and bootloader into memory only when booting, never on a restore. But
`virt_run.py` still opens both files at startup and exits if either is missing. Its default
`--kernel` is `/tmp/gem5_res/...`, which will not exist on your host. Both files must be
AArch64 ELFs: pass the `vmlinux`, not the `-Image`.

The kernel's *symbols* are not used either. The guest runs with KASLR, so `vmlinux` addresses
do not match the running kernel. Each `m5.cpt` therefore carries an **empty** kernel symbol
table on purpose, and gem5 installs none of its kernel hooks. Expect warnings like
`Could not add Kernel Panic event handler` and `Kernel symbol table is empty` on every
restore; they are by design. The consequence is that **gem5 will not stop on a guest kernel
panic**, so the guest-console checks under "Verifying a restore" are the only safeguard.

`kernel/` also serves the other direction: booting the image under QEMU, or capturing new
checkpoints from it (`-kernel arm64-linux-kernel-6.8.12-1.0.0-Image`).

The task is **baked into the checkpoint** — no `rpoint.task=` token is needed at restore.
That token selects the trajectory at *capture* time; by the checkpoint it is already the
guest's running state.

A 1M-warmup + 20M-detailed O3 window takes **~3–5 minutes** per checkpoint on a Graviton3
(measured 105–163 KIPS, 174–286 s wall).

## Caveats — read before trusting a number

1. **`--release kvm-host` must match the capture regime.** These were captured under KVM. A
   mismatch does **not** error: it restores and produces plausible numbers that are wrong.
2. **The 16-bit ASID fix is mandatory** (fork commit `8d0dafc815`, formerly `7c41a81c13`,
   "arm: restore QEMU-virt checkpoints with 16-bit ASIDs"). The capture CPU reports
   `ID_AA64MMFR0_EL1.ASIDBits = 2`, so the guest kernel sets `TCR_EL1.AS = 1` and allocates
   16-bit ASIDs, while gem5's `ArmSystem` defaulted to 8-bit and read the ASID from
   `TTBR[55:48]`. Any two address
   spaces whose ASIDs share a low byte (about one pair in 256) then become **one** address
   space to the TLB, and a process can execute another's pages. This was found here: a
   restored checkpoint's Python driver executed a Go binary's page and died of SIGSEGV while
   the QEMU oracle of the same state passed. Exposure grows with run length and process
   count, so an agent workload is the worst case.
3. **Keep the disk delta.** Each `cpt.<i>/board.realview.vio.vio.image.cow` is that dump's
   guest disk state, loaded by `CowDiskImage` at restore. Without it the guest reads
   build-time file contents for any block it re-reads — silently (directory entries simply
   vanish). Do not separate it from its checkpoint.
4. **Preserve hard links when copying.** `store0.pmem` / `system.physmem.store0.pmem` (and
   the `store1` pair) are the same inode. Copy with **`rsync -aHS`**; an earlier archive
   lost the links and doubled on disk.
5. **`mem_size` is a restore invariant**: these are 16 GiB, 1 vCPU guests. Changing it
   fatals ("Memory range size has changed").
6. **Suspiciously uniform IPC across different tasks is a corruption signature**, not a
   result — it has happened twice in this project's history (a FEAT_DIT kernel storm at
   ~0.47, a PAuth writeback bug at ~0.48–0.50). For reference, these checkpoints span
   **IPC 0.35–1.57**, with up to 0.86 spread *within* a single task. If a sweep comes back
   flat, suspect the restore before the workload.
7. **Always pass `--progress-interval 10kHz`** so a stalled restore is visible rather than
   silently slow.
8. **The replay is unpaced.** Model-wait idle is *not* reproduced: the recorded
   request-to-response latencies exist in the source runs but were not replayed, so these
   timelines are agent-loop **compute**, not deployed wall-clock. The checkpoints therefore
   never land inside an inference stall — intended here, but it means they do not represent
   a deployed agent's duty cycle. Measured busy fraction across these 27 tasks: median 0.46,
   range 0.09–0.96.
9. **GIC active-priority registers are not restored** (`icc_apr` is extracted by nothing, so
   gem5 sees zero). Four of the 132 dumps were taken with an interrupt active
   (`fastlane-20958/cpt.0`, `gin-2121/cpt.2`, `gin-2121/cpt.4`, `ripgrep-2209/cpt.4`). Traced
   consequence for this guest (`DS=1`, EL1 non-secure Linux): interrupts still deactivate
   correctly on EOI; what is lost is the running priority, so gem5 may deliver a
   lower-priority interrupt inside a window where hardware would mask it. Low severity, and
   narrow because Linux runs handlers with `PSTATE.I` set — but know it before drawing
   conclusions from interrupt behaviour in those four.
10. **Re-rendering needs QEMU 8.2.2.** Each `cpt.<i>/migration.stream` is retained, so a
    checkpoint can be re-rendered without recapture (`create_snapshot.py --skip-dump`). The
    vendored migration-stream parser misparses other QEMU versions' vmstate layouts.

## Verifying a restore

Do not accept "it didn't crash". Require a **positive guest signal**:

- `cpt.<i>/provenance.json` names what was on the CPU at the dump (`landing`: exception
  level, PC, task comm/pid). Check the restore resumes in that task.
- Watch `board.terminal` for the guest's own markers (`RPOINT_REPLAY_ROUND <n>`) advancing
  past the in-flight tool call.
- Check `undefined instruction` warnings and kernel errors are absent — all 132 restored
  with zero of each at archive time.

## Provenance

Every checkpoint here was, before archiving: captured from a replay that had been proven to
reproduce its live recording byte-for-byte; restored in gem5 on the O3 core and confirmed
clean; and copied with its file inventory compared against the source under `LC_ALL=C`.

The tooling, the per-task state (run ids, receipts, measured windows, validation verdicts)
and the full campaign journal live in the **gem5-infra** repo:

```
repo    git@github.com:rahulbera/gem5-infra.git
commit  e8fa0eb57c523d517334c3ed8f8b0be2c1ec8ae7      <- the tree these were archived from
```

Under that commit:

```
infra/rpoint/bench/agentic-replay/campaign/    the drivers and per-task state
infra/rpoint/docs/workloads/agentic/           the journal: 32 issues, with evidence
infra/rpoint/docs/wiki/                        RPoint's reference manual
```

Start with `docs/workloads/agentic/swe-bench-multilingual/README.md` for the task table and
the per-task windows, round counts, sizes and IPC ranges; `cross-cutting.md` for everything
that went wrong and how it was diagnosed.

**Not captured:** wave 4 of the planned 36 (9 tasks) — recorded and replay-verified, but
deliberately not checkpointed. Its trajectories are in the image, so it can be captured at
any time without re-recording.
