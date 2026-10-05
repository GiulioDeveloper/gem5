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

"""Garfield QEMU-virt FS boot/checkpoint driver (QPoints M2b).

Boots Linux on the ``QEMU_Virt`` platform -- gem5's model of QEMU's
``-machine virt,gic-version=3`` -- and can take or restore checkpoints on
it. Its purpose in the QPoints pipeline:

  1. produce the NATIVE gem5-25.1 reference checkpoint whose ``m5.cpt``
     structure (physmem store layout + SimObject sections) the QPoints
     template must emit, and
  2. iterate on restoring QPoints-generated checkpoints against the same
     platform until they boot.

Unlike ``fs_run.py`` (VExpress + stdlib ArmBoard), this uses the classic
``configs/example/arm/devices.py`` SimpleSystem because the platform is
custom. Kernel/bootloader/disk are explicit paths -- no M5_PATH lookups.

Examples:
    # native boot under KVM, checkpoint triggered by the boot script
    gem5.opt virt_fs.py --cpu kvm --kernel <vmlinux> --disk-image <img> \\
        --script ckpt.sh

    # structural reference checkpoint after 1ms of atomic simulation
    gem5.opt virt_fs.py --cpu atomic --kernel <vmlinux> \\
        --disk-image <img> --cpt-tick 1000000000

    # restore attempt
    gem5.opt virt_fs.py --cpu atomic --kernel <vmlinux> \\
        --disk-image <img> --restore <cpt.dir>
"""

import argparse
import os
import sys
from pathlib import Path

import m5
from m5.objects import (
    ArmFsLinux,
    CowDiskImage,
    QEMU_Virt,
    RawDiskImage,
    Root,
    VirtIOBlock,
)
from m5.util import addToPath

GEM5_ROOT = Path(__file__).resolve().parents[3]
addToPath(str(GEM5_ROOT / "configs"))
addToPath(str(GEM5_ROOT / "configs" / "example" / "arm"))

import devices
from common import MemConfig

DEFAULT_BOOTLOADER = str(
    GEM5_ROOT
    / "system"
    / "arm"
    / "bootloader"
    / "arm64"
    / "boot_v2_qemu_virt.arm64"
)

cpu_choices = ["atomic"] + (["kvm"] if devices.have_kvm else [])


def create(args):
    if args.script and not os.path.isfile(args.script):
        print(f"Error: bootscript {args.script} does not exist")
        sys.exit(1)

    # KVM CPUs bypass the memory system entirely; atomic_noncaching keeps
    # the two modes checkpoint-compatible.
    mem_mode = "atomic_noncaching" if args.cpu == "kvm" else "atomic"

    system = devices.SimpleSystem(
        caches=False,
        mem_size=args.mem_size,
        platform=QEMU_Virt(),
        mem_mode=mem_mode,
        workload=ArmFsLinux(object_file=args.kernel),
        readfile=args.script,
    )

    MemConfig.config_mem(args, system)

    # The disk is the QEMU-virt virtio-mmio slot 31 device (see QEMU_Virt).
    # queueSize must equal the ring size the GUEST negotiated under QEMU.
    # That is 1024 -- NOT QEMU's virtio-blk queue-size property (256):
    # QEMU's legacy virtio-mmio transport reports QueueNumMax=1024
    # (VIRTQUEUE_MAX_SIZE) regardless of the device property, the guest
    # driver takes it, and QEMU resizes the vring. The legacy avail/used
    # ring offsets are functions of the queue size, so a mismatch makes
    # gem5 parse a restored guest's ring at the wrong addresses (symptom:
    # "Unsupported IO request" with garbage types, or a crash in
    # consumeDescriptor). Verified against the memory dump: with the
    # 1024-entry layout avail.idx == used.idx == the dumped _last_avail.
    system.realview.vio[0].vio = VirtIOBlock(
        image=CowDiskImage(
            child=RawDiskImage(image_file=args.disk_image), read_only=False
        ),
        queueSize=1024,
    )

    # m5ops_base is set by QEMU_Virt.setupBootLoader (platform-owned).

    if args.cpu != "kvm":
        # Match the QEMU-TCG cortex-a57 feature envelope (v8.0 + crypto).
        # A restore CPU with MORE features than the snapshot CPU is
        # poison: e.g. the 6.8 kernel's HINT-space PACIASP/AUTIASP are
        # NOPs on a57 but LIVE with FEAT_PAuth -- the first AUTIASP on an
        # unsigned pre-restore frame poisons the return pointer (bit 62)
        # and the kernel oopses at a wild PC. Mirror image of the DIT
        # lesson: restore features == snapshot features, both directions.
        from m5.objects import Armv8

        system.release = Armv8()

    system.connect()

    cluster_class = (
        devices.KvmCluster if args.cpu == "kvm" else devices.AtomicCluster
    )
    system.cpu_cluster = [
        cluster_class(system, args.num_cores, args.cpu_freq, "1.0V")
    ]
    system.addCaches(False, last_cache_level=2)

    if args.cpu == "kvm":
        from m5.objects import (
            ArmDefaultRelease,
            KvmVM,
        )

        system.kvm_vm = KvmVM()
        system.release = ArmDefaultRelease.for_kvm()

        # Use gem5's simulated GIC instead of the in-kernel vGIC. The
        # host's vGIC rejects gem5's GIC state on sync (read-only ID
        # fields like PRIbits differ per host GIC implementation), and a
        # QPoints restore needs the simulated model's state anyway.
        # (fs_bigLITTLE.py also strips the generic_timer DT node here, but
        # that leaves arm64 Linux with no arch timer -- it hangs before
        # any console output. Keep the node.)
        system.realview.gic.simulate_gic = True

    system.realview.setupBootLoader(system, None, boot_loader=args.bootloader)

    if args.dtb:
        system.workload.dtb_filename = args.dtb
    else:
        system.workload.dtb_filename = os.path.join(
            m5.options.outdir, "system.dtb"
        )
        system.generateDtb(system.workload.dtb_filename)

    kernel_cmd = [
        "console=ttyAMA0",
        "norandmaps",
        f"root={args.root_device}",
        "rw",
    ]
    if args.kernel_cmd_extra:
        kernel_cmd.append(args.kernel_cmd_extra)
    system.workload.command_line = " ".join(kernel_cmd)

    return system


def run(args):
    cptdir = m5.options.outdir

    if args.cpt_tick:
        event = m5.simulate(args.cpt_tick)
        print(f"Simulated to tick {m5.curTick()} ({event.getCause()})")
        cpt_dir = os.path.join(cptdir, f"cpt.{m5.curTick()}")
        m5.checkpoint(cpt_dir)
        print(f"Structural checkpoint written to {cpt_dir}")
        sys.exit(0)

    # The gem5 disk images' m5/gem5-bridge tooling issues NEW-STYLE
    # hypercall m5ops; each surfaces as a simulate() exit with a hypercall
    # id (see src/python/gem5/simulate/exit_handler.py for the id map):
    #   1 kernel booted, 2 boot script started -> keep simulating
    #   3 boot script finished                 -> stop
    #   7 checkpoint                           -> write cpt.<tick>, continue
    while True:
        event = m5.simulate()
        exit_msg = event.getCause()
        hcall = event.getHypercallId()
        if exit_msg == "checkpoint" or hcall == 7:
            print(f"Dropping checkpoint at tick {m5.curTick()}")
            cpt_dir = os.path.join(cptdir, f"cpt.{m5.curTick()}")
            m5.checkpoint(cpt_dir)
            print("Checkpoint done.")
        elif hcall == 1 and args.cpt_on_boot:
            # "Kernel booted" marker from the image's early init: root is
            # mounted and userspace has started, but systemd hasn't run --
            # good enough for a reference checkpoint without paying for a
            # full atomic-mode distro boot (hours).
            cpt_dir = os.path.join(cptdir, f"cpt.{m5.curTick()}")
            m5.checkpoint(cpt_dir)
            print(f"Boot checkpoint written to {cpt_dir}; exiting")
            break
        elif hcall in (1, 2, 4, 5):
            print(f"hypercall {hcall} @ {m5.curTick()}; continuing")
        elif hcall == 3:
            print(f"boot script finished @ {m5.curTick()}")
            break
        else:
            print(
                f"{exit_msg} (code {event.getCode()}, "
                f"hypercall {hcall}) @ {m5.curTick()}"
            )
            break

    sys.exit(event.getCode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kernel",
        type=str,
        required=True,
        help="Path to the (vmlinux) kernel binary",
    )
    parser.add_argument(
        "--bootloader",
        type=str,
        default=DEFAULT_BOOTLOADER,
        help="Path to the gem5 bootloader binary",
    )
    parser.add_argument(
        "--disk-image",
        type=str,
        required=True,
        help="Path to the root disk image",
    )
    parser.add_argument(
        "--root-device",
        type=str,
        default="/dev/vda2",
        help="Kernel root= device (default: /dev/vda2)",
    )
    parser.add_argument(
        "--dtb",
        type=str,
        default=None,
        help="DTB file (default: autogenerate)",
    )
    parser.add_argument(
        "--script", type=str, default="", help="m5 readfile boot script"
    )
    parser.add_argument(
        "--cpu", type=str, choices=cpu_choices, default="atomic"
    )
    parser.add_argument("--cpu-freq", type=str, default="2GHz")
    parser.add_argument("--num-cores", type=int, default=1)
    parser.add_argument(
        "--mem-size",
        type=str,
        default="16GiB",
        help="RAM size (QPoints launches QEMU with 16GiB)",
    )
    parser.add_argument(
        "--mem-type", default="DDR3_1600_8x8", help="Memory model type"
    )
    parser.add_argument("--mem-channels", type=int, default=1)
    parser.add_argument("--mem-ranks", type=int, default=None)
    parser.add_argument(
        "--kernel-cmd-extra",
        type=str,
        default="",
        help="Extra kernel command-line text",
    )
    parser.add_argument(
        "--restore",
        type=str,
        default=None,
        help="Restore from this checkpoint directory",
    )
    parser.add_argument(
        "--cpt-tick",
        type=int,
        default=None,
        help="Simulate this many ticks, checkpoint, exit",
    )
    parser.add_argument(
        "--cpt-on-boot",
        action="store_true",
        help="Checkpoint at the image's 'kernel booted' "
        "marker (hypercall 1) and exit",
    )
    args = parser.parse_args()

    root = Root(full_system=True)
    root.system = create(args)

    if args.cpu == "kvm":
        # KVM cores run decoupled from the event queue; use a coarse
        # simulation quantum.
        m5.ticks.fixGlobalFrequency()
        root.sim_quantum = m5.ticks.fromSeconds(
            m5.util.convert.toLatency("1ms")
        )

    if args.restore is not None:
        m5.instantiate(args.restore)
    else:
        m5.instantiate()

    run(args)


if __name__ == "__m5_main__":
    main()
