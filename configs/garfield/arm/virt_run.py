# Copyright (c) 2026 Technical University of Munich
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Garfield QEMU-virt FS detailed restore: QPoints snapshot -> Neoverse V2 IPC.

The QEMU_Virt sibling of ``fs_run.py``. It restores a QPoints-converted
QEMU snapshot (Track B) instead of an FS+KVM SimPoint checkpoint (Track A)
and reuses fs_run.py's validated switchable-restore machinery verbatim.
The deltas: the board is ``QemuVirtBoard`` (ArmBoard on the QEMU_Virt
platform, disk on the platform's virtio-mmio slot), and the workload is
explicit kernel/bootloader/disk paths -- no M5_PATH, no resource lookups,
no invocations.json.

Usage:
    ./build/ARM/gem5.opt --outdir=<out> configs/garfield/arm/virt_run.py \\
        --restore-dir <snapshot dir> --disk-img <prepped image> \\
        --warmup-insts 1000000 --detailed-insts 3000000
"""

import argparse
import os
import re
from pathlib import Path

import m5
from m5.objects import (
    ArmDefaultRelease,
    ArmExtension,
    ArmRelease,
    Armv8,
    CowDiskImage,
    FetchDirectedPrefetcher,
    QEMU_Virt,
    RawDiskImage,
    VirtIOBlock,
)
from m5.util import addToPath
from m5.util.convert import toFrequency

addToPath("../..")
# isort: split

from garfield.arm import (
    cache_hierarchy,
    neoverse_v2,
    sim_opts,
    task_trace,
)

from gem5.components.boards.arm_board import ArmBoard
from gem5.components.boards.mem_mode import MemMode
from gem5.components.processors.base_cpu_core import BaseCPUCore
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_core import SimpleCore
from gem5.components.processors.switchable_processor import (
    SwitchableProcessor,
)
from gem5.isas import ISA
from gem5.resources.resource import (
    BootloaderResource,
    DiskImageResource,
    KernelResource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.utils.override import overrides
from gem5.utils.requires import requires

GEM5_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BOOTLOADER = str(
    GEM5_ROOT / "system" / "arm" / "bootloader" / "arm64"
    / "boot_v2_qemu_virt.arm64"
)
DEFAULT_KERNEL = "/tmp/gem5_res/arm64-linux-kernel-6.8.12-1.0.0"



class QemuVirtBoard(ArmBoard):
    """ArmBoard on the QEMU_Virt platform. Two deltas from stock ArmBoard:
    the disk is the platform's virtio-mmio slot-31 device with the ring
    size the QEMU guest actually negotiated (1024: QEMU's legacy
    virtio-mmio reports QueueNumMax=1024 regardless of the device
    property), and no PCI device is ever attached."""

    @overrides(ArmBoard)
    def get_disk_device(self):
        return "/dev/vda"

    @overrides(ArmBoard)
    def _add_disk_to_board(self, disk_image):
        self._image = CowDiskImage(
            child=RawDiskImage(
                read_only=True, image_file=disk_image.get_local_path()
            ),
            read_only=False,
        )
        self.realview.vio[0].vio = VirtIOBlock(
            image=self._image, queueSize=1024
        )

    @overrides(ArmBoard)
    def _pre_instantiate(self, full_system=None):
        # Replicates ArmBoard._pre_instantiate WITHOUT the pci_devices
        # assignment: SimObject rejects assigning an EMPTY vector, and this
        # board attaches no PCI devices by design. Keep in sync with
        # gem5/components/boards/arm_board.py.
        root = super(ArmBoard, self)._pre_instantiate(
            full_system=full_system
        )
        self.workload.dtb_filename = self._get_dtb_filename()
        self.realview.setupBootLoader(
            self, self._get_dtb_filename(), self._bootloader
        )
        self.generateDtb(self._get_dtb_filename())
        return root


def parse_args():
    parser = argparse.ArgumentParser(
        description="Garfield QEMU-virt detailed restore (Track B)."
    )
    parser.add_argument("--restore-dir", type=str, default=None,
                        help="QPoints snapshot directory (contains m5.cpt). "
                        "Omit with --gen-ref to BOOT instead of restore.")
    parser.add_argument("--gen-ref", action="store_true",
                        help="Native-reference generation mode: boot the "
                        "guest on the ATOMIC core (no restore, no switch) "
                        "and checkpoint at the image's kernel-booted "
                        "marker. The resulting m5.cpt carries THIS "
                        "board's section names -- the tree gen_template "
                        "and all restores must share.")
    parser.add_argument("--disk-img", type=str, required=True,
                        help="The prepped guest image the snapshot was "
                        "taken against (referenced read-only).")
    parser.add_argument("--kernel", type=str, default=DEFAULT_KERNEL,
                        help="vmlinux (same bits the guest booted).")
    parser.add_argument("--bootloader", type=str,
                        default=DEFAULT_BOOTLOADER)
    parser.add_argument("--release", type=str, default="armv8",
                        choices=["armv8", "kvm-host"],
                        help="Restore CPU feature envelope. armv8: TCG "
                             "cortex-a57 snapshots (Gates 0-C). kvm-host: "
                             "KVM -cpu host,sve=off,pauth=off snapshots on "
                             "Neoverse-V1 -- ArmDefaultRelease minus the "
                             "masked features (PAuth, SVE/SME families); "
                             "DIT/SSBS are unconditional in this fork.")
    parser.add_argument("--settle-insts", type=int, default=0)
    parser.add_argument("--warmup-insts", type=int, default=int(1e6))
    parser.add_argument("--detailed-insts", type=int, default=int(5e6))
    parser.add_argument("--atomic-only", action="store_true",
                        help="Restore-verify mode: run the ATOMIC core only "
                             "(no switch, no detailed region) so long guest "
                             "windows are affordable; exit at "
                             "--atomic-max-insts committed instructions.")
    parser.add_argument("--atomic-max-insts", type=int, default=int(30e9))
    parser.add_argument("--stats-interval-insts", type=int, default=0,
                        help="Dump and reset stats every N committed "
                             "instructions of the detailed region, so "
                             "stats.txt holds one block per interval "
                             "(0: one dump for the whole region).")
    parser.add_argument("--tail-insts", type=int, default=0,
                        help="After the detailed region, switch back to the "
                             "ATOMIC core and run this many more "
                             "instructions (no stats). With --task-trace, "
                             "collects events that complete after the "
                             "region, e.g. a tool call it cut in half.")
    # --- shared knobs (machine / prefetcher / garfield), same as
    # fs_run.py and se_run.py -------------------------------------------
    sim_opts.add_common_args(
        parser,
        mem_size_default="16GiB",
        mem_size_help="Guest DRAM size (must cover the snapshot's RAM).",
    )
    task_trace.add_args(parser)
    return parser.parse_args()


args = parse_args()


def _pick_release(args):
    # Feature-envelope law: restore CPU features must EQUAL snapshot CPU
    # features (too few -> Undefined storms [DIT]; too many -> live PAuth
    # poisons unsigned frames / SME FA64 panics).
    if args.gen_ref:
        return ArmDefaultRelease()
    if args.release == "kvm-host":
        # Construct the extension list explicitly: ArmRelease.remove() on
        # a fresh instance mutates a TEMPORARY (the VectorParam default is
        # re-converted per access), so removals silently don't stick --
        # observed: FEAT_PAuth stayed live and the first kernel epilogue's
        # autiasp poisoned x30 (O3 commit-froze at 9830 insts on a wild
        # ret; the atomic settle survived only because its simpler fetch
        # path kept faulting-and-retrying visibly).
        drop = {"FEAT_PAuth", "FEAT_SVE", "FEAT_SVE2", "FEAT_SVE2p1",
                "FEAT_F32MM", "FEAT_F64MM", "FEAT_SME"}
        # NB: the class list holds ArmExtension OBJECTS -- compare by
        # str(), a raw `e not in drop` string-set filters nothing.
        return ArmRelease(extensions=[
            e for e in ArmDefaultRelease.extensions if str(e) not in drop])
    return Armv8()

requires(isa_required=ISA.ARM)


# ---- the detailed Neoverse V2 core (copied verbatim from fs_run.py -- keep
# in sync) -------------------------------------------------------------------
def make_neoverse_v2_core():
    # cpu_id=0 must match the ATOMIC settle core: m5.switchCpus /
    # BaseCPU::takeOverFrom asserts the swapped-in and swapped-out cores
    # share a cpuId.
    core = BaseCPUCore(neoverse_v2.NeoverseV2(cpu_id=0), isa=ISA.ARM)
    sim_opts.apply_core_knobs(core.core, args)
    return core


def make_atomic_core():
    AtomicClass = SimpleCore.cpu_class_factory(
        cpu_type=CPUTypes.ATOMIC, isa=ISA.ARM
    )
    core = BaseCPUCore(core=AtomicClass(cpu_id=0), isa=ISA.ARM)
    # Mirror make_neoverse_v2_core(): without this, --atomic-only runs (no
    # detailed core ever active) print no heartbeat at all and a multi-hour
    # restore is unobservable.
    core.core.progress_interval = args.progress_interval
    return core


# ---- cache hierarchy (copied verbatim from fs_run.py -- keep in sync) ------
class RestoreNeoverseV2CacheHierarchy(
    cache_hierarchy.NeoverseV2CacheHierarchy
):
    """The identical NeoverseV2 cache hierarchy, adapted for the switchable
    restore flow: the L1I FDP prefetchers are rebound to the detailed core
    they will actually run on (ports migrate on m5.switchCpus; the FDP's
    cpu pointer and MMU do not)."""

    def __init__(self, detailed_core, **kwargs):
        super().__init__(**kwargs)
        self._detailed_cpu = detailed_core.core

    def incorporate_cache(self, board):
        super().incorporate_cache(board)
        if not self._enable_fdp:
            return
        for l1i in self.l1icaches:
            for pf in l1i.prefetcher.prefetchers:
                if isinstance(pf, FetchDirectedPrefetcher):
                    pf.cpu = self._detailed_cpu
                    pf._mmus = [self._detailed_cpu.mmu]


# ---- restore switchable processor (copied verbatim from fs_run.py) ---------
class NeoverseV2RestoreProcessor(SwitchableProcessor):
    """start-key = Neoverse V2 (the detailed core we ultimately switch TO),
    switch-key = ATOMIC (primed active before m5.instantiate -- receives the
    checkpoint's ThreadContext)."""

    def __init__(self, detailed_core, atomic_core):
        self._start_key = "start"
        self._switch_key = "switch"
        self._current_is_start = True
        self._mem_mode = MemMode.ATOMIC
        switchable_cores = {
            self._start_key: [detailed_core],
            self._switch_key: [atomic_core],
        }
        super().__init__(
            switchable_cores=switchable_cores,
            starting_cores=self._start_key,
        )

    @overrides(SwitchableProcessor)
    def incorporate_processor(self, board):
        super().incorporate_processor(board=board)
        board.set_mem_mode(self._mem_mode)

    @overrides(SwitchableProcessor)
    def switch(self):
        if self._current_is_start:
            self.switch_to_processor(self._switch_key)
        else:
            self.switch_to_processor(self._start_key)
        self._current_is_start = not self._current_is_start

    def prime_switch_core_active(self):
        """Make the ATOMIC switch core the active one BEFORE
        m5.instantiate(), matching a checkpoint whose ThreadContext was
        serialized from a single active core."""
        self._current_cores = self._switchable_cores[self._switch_key]
        self._current_is_start = False
        for cores in self._switchable_cores.values():
            for core in cores:
                core.set_switched_out(core not in self._current_cores)


# ---- assemble the board ----------------------------------------------------
memory = sim_opts.make_memory(args)

detailed_core = make_neoverse_v2_core()

if args.gen_ref:
    # Reference generation: cacheless (fast atomic boot; restores
    # tolerate absent cache sections -- Track A precedent: KVM-generated
    # cacheless checkpoints restore into the full NeoverseV2 hierarchy).
    from gem5.components.cachehierarchies.classic.no_cache import NoCache

    cache = NoCache()
else:
    cache = RestoreNeoverseV2CacheHierarchy(
        detailed_core, **sim_opts.cache_kwargs(args)
    )

processor = NeoverseV2RestoreProcessor(detailed_core, make_atomic_core())

board = QemuVirtBoard(
    clk_freq=args.clk_freq,
    processor=processor,
    memory=memory,
    cache_hierarchy=cache,
    # Restores of TCG snapshots: the cortex-a57 envelope (Armv8 =
    # v8.0 + crypto). MORE features than the snapshot CPU = live
    # HINT-space instructions on unsigned state (the PAuth poison);
    # FEWER-but-advertised = enable-time faults (the SME/FA64 panic:
    # gem5's Armv8 release does not scrub SME ID fields, so gen-ref
    # BOOTS must use the default release, where SME is implemented).
    release=_pick_release(args),
    platform=QEMU_Virt(),
)

# 16-bit ASIDs (FEAT_ASID16). Every capture CPU we restore from reports
# ID_AA64MMFR0_EL1.ASIDBits = 2 -- Neoverse V1 under KVM and QEMU's TCG
# cortex-a57 alike -- so the guest kernel sets TCR_EL1.AS = 1 and allocates
# 16-bit ASIDs. ArmSystem defaults to 8-bit, and gem5 then reads the ASID from
# TTBR[55:48]: every pair of address spaces whose ASIDs share a low byte
# becomes ONE address space to the TLB, and a process translates through
# another's page tables. Same feature-envelope law as `release` above, on a
# parameter that is not part of the extension list. Caught 2026-09-19: a
# restored agentic checkpoint's CPython replay driver (ASID 0x4ec) hit the
# docker CLI's translations (ASID 0xeec), executed a Go text page and died of
# SIGSEGV, while the same state resumed under KVM completes the workload.
board.have_large_asid_64 = True

if not args.gen_ref and args.restore_dir is None:
    raise SystemExit("--restore-dir is required unless --gen-ref")

board.set_kernel_disk_workload(
    kernel=KernelResource(os.path.abspath(args.kernel)),
    disk_image=DiskImageResource(
        os.path.abspath(args.disk_img), root_partition="2"
    ),
    bootloader=BootloaderResource(os.path.abspath(args.bootloader)),
    checkpoint=Path(args.restore_dir) if args.restore_dir else None,
)

if args.gen_ref:
    # Boot on the ATOMIC (switch) core only; checkpoint at the first
    # kernel-booted hypercall and exit. Uses the same primed-atomic
    # arrangement as restores so the section tree is identical.
    from gem5.simulate.exit_handler import ExitHandler
    from gem5.utils.override import overrides as _ov

    class _StopAtKernelBooted(ExitHandler, hypercall_num=1):
        """Replace the stdlib id-1 handler (which continues) so run()
        returns at the image's kernel-booted marker."""
        def _process(self, simulator):
            pass
        def _exit_simulation(self):
            return True

    processor.prime_switch_core_active()
    simulator = Simulator(board=board)
    print(">>> gen-ref: booting to the kernel-booted marker (atomic) ...")
    simulator.run()   # stdlib exit handler for hypercall 1 returns control
    cpt = Path(m5.options.outdir) / f"cpt.{m5.curTick()}"
    m5.checkpoint(str(cpt))
    with open(cpt / "m5.cpt") as f:
        assert f.read().splitlines()[-1].startswith("version_tags="), \
            "reference m5.cpt truncated"
    print(f">>> gen-ref: reference checkpoint at {cpt}")
    raise SystemExit(0)

processor.prime_switch_core_active()

trace_banner = task_trace.attach(board, args) if args.task_trace else []

print("=== garfield QEMU-virt detailed restore (Track B) ===")
print(f"  core     : NeoverseV2 (ArmO3CPU) restore @ {args.clk_freq}")
for line in sim_opts.describe(args):
    print(line)
print(f"  restore  : {args.restore_dir}")
for line in trace_banner:
    print(line)
if args.atomic_only:
    print(f"  region   : ATOMIC-only max-insts={args.atomic_max_insts:,} "
          "(no switch, no detailed)")
else:
    print(
        f"  region   : settle={max(1, args.settle_insts):,} "
        f"warmup={args.warmup_insts:,} detailed={args.detailed_insts:,}"
        + (f" stats-every={args.stats_interval_insts:,}"
           if args.stats_interval_insts > 0 else "")
        + (f" tail={args.tail_insts:,}" if args.tail_insts > 0 else "")
    )


# ---- run: restore(ATOMIC) -> switch(Neoverse V2) -> warmup -> detailed -----
def _stopper():
    while True:
        yield True


simulator = Simulator(
    board=board, on_exit_event={ExitEvent.MAX_INSTS: _stopper()}
)

if args.atomic_only:
    # Restore-verify short-circuit (mirrors --gen-ref's early return): run
    # the ATOMIC settle core standalone for --atomic-max-insts committed
    # instructions and stop there -- no switch to the detailed core, no
    # warmup, no detailed region. This is what makes a whole guest
    # workload (e.g. a DaCapo benchmark run to its own completion message)
    # affordable: the detailed O3 core is far too slow for that horizon,
    # but atomic is fast enough to let the guest print its own pass/fail
    # verdict, which is the end-to-end correctness sign-off for a restored
    # checkpoint.
    print(f">>> instantiate + restore {args.restore_dir}; ATOMIC-only run "
          f"{args.atomic_max_insts:,} insts (max) ...")
    simulator.schedule_max_insts(args.atomic_max_insts)
    simulator.run()
    print(
        f"Exiting @ tick {m5.curTick()} because "
        f"{simulator.get_last_exit_event_cause()}."
    )
    print(f"Insts (ATOMIC)     : {simulator.get_instruction_count()}")
    raise SystemExit(0)

settle = max(1, args.settle_insts)
print(f">>> instantiate + restore {args.restore_dir}; ATOMIC settle "
      f"{settle:,} ...")
simulator.schedule_max_insts(settle)
simulator.run()
print(f">>> restored; insts={simulator.get_instruction_count()}")

print(">>> switch ATOMIC -> Neoverse V2 (detailed) ...")
simulator.switch_processor()

if args.warmup_insts > 0:
    print(f">>> Neoverse V2 warmup {args.warmup_insts:,} insts "
          "(unmeasured) ...")
    simulator.schedule_max_insts(args.warmup_insts)
    simulator.run()

print(f">>> Neoverse V2 detailed {args.detailed_insts:,} insts (measured) ...")
m5.stats.reset()
insts0 = detailed_core.get_total_instructions()
tick0 = m5.curTick()
if args.stats_interval_insts > 0:
    # One stats block per interval: run N instructions, dump, reset.
    # intervals.csv gives each block's absolute tick range and its range of
    # the global committed-instruction count (all cores since the restore,
    # the same count --task-trace stamps on its events), so stats blocks
    # and trace events can be joined.
    def _global_insts():
        return sum(core.get_total_instructions()
                   for cores in processor._switchable_cores.values()
                   for core in cores)

    with open(Path(m5.options.outdir) / "intervals.csv", "w") as f:
        f.write("block,tick_start,tick_end,insts_start,insts_end\n")
        done = 0
        block = 0
        while done < args.detailed_insts:
            n = min(args.stats_interval_insts, args.detailed_insts - done)
            t0, g0 = m5.curTick(), _global_insts()
            simulator.schedule_max_insts(n)
            simulator.run()
            m5.stats.dump()
            m5.stats.reset()
            f.write(f"{block},{t0},{m5.curTick()},{g0},{_global_insts()}\n")
            f.flush()   # readable while the run is still going
            done += n
            block += 1
else:
    simulator.schedule_max_insts(args.detailed_insts)
    simulator.run()
tick1 = m5.curTick()
insts1 = detailed_core.get_total_instructions()
if args.stats_interval_insts <= 0:
    m5.stats.dump()


# ---- best-effort summary from the just-dumped stats.txt --------------------
def _summarize():
    stats_path = Path(m5.options.outdir) / "stats.txt"
    if not stats_path.exists():
        return
    txt = stats_path.read_text()
    wanted = [
        r"processor\.start\.core.*\bipc\b",
        r"processor\.start\.core.*\bcpi\b",
        r"processor\.start\.core.*numCycles\b",
        r"processor\.start\.core.*(committedInsts|commitStats0\.numInsts)\b",
        r"^simInsts\b",
        r"^simSeconds\b",
    ]
    print("==== DETAILED-REGION STATS SUMMARY ====")
    for line in txt.splitlines():
        for pat in wanted:
            if re.search(pat, line):
                print("  " + " ".join(line.split()))
                break


if args.stats_interval_insts <= 0:
    _summarize()

region_insts = insts1 - insts0
region_ticks = tick1 - tick0
region_cycles = (region_ticks / 1e12) * toFrequency(args.clk_freq)
ipc = region_insts / region_cycles if region_cycles > 0 else 0.0

print(
    f"Exiting @ tick {m5.curTick()} because "
    f"{simulator.get_last_exit_event_cause()}."
)
print(f"Region insts       : {region_insts}")
print(f"Region cycles      : {region_cycles:.0f}")
print(f"IPC (measured)     : {ipc:.3f}")
print("Full stats in m5out/stats.txt")

if args.tail_insts > 0:
    print(f">>> switch Neoverse V2 -> ATOMIC tail {args.tail_insts:,} insts "
          "(unmeasured) ...")
    simulator.switch_processor()
    simulator.schedule_max_insts(args.tail_insts)
    simulator.run()
    print(f"Tail insts         : {args.tail_insts}")
