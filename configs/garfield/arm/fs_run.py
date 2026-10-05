# Copyright (c) 2025 Technical University of Munich
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

"""Garfield ARM FS checkpoint-restore simulation driver.

The full-system checkpoint-restore sibling of ``se_run.py``. It assembles the
*identical* Neoverse V2-class out-of-order ARM core with its full cache
hierarchy (L1I/L1D 64KiB, L2 2MiB; prefetchers + FDP on by default) and a
single-channel DDR5 memory, but instead of a syscall-emulation workload it
RESTORES a gem5 full-system SimPoint checkpoint (produced by the QPoints
``fskvm_ckpt/fs_ckpt.py`` FS+KVM generator) and runs a detailed Neoverse V2
region on it.

The restore machinery mirrors ``tools/simpoint/restore_o3.py`` (the working,
validated FS-restore config): ArmBoard + VExpress_GEM5_V1 + ArmDefaultRelease +
``set_kernel_disk_workload`` (kernel + the shared disk image), and a
``SwitchableProcessor`` whose ATOMIC core is primed active *before*
``m5.instantiate(<checkpoint>)`` (the checkpoint was taken with the ATOMIC
switch core active and the KVM start core switched out, so the restore config
has NO KVM core: an ATOMIC start-for-restore + the detailed Neoverse V2 core).
The only thing that swaps versus ``restore_o3.py`` is the detailed core -- a
generic O3 there, the garfield Neoverse V2 here -- and the cache hierarchy
(``NeoverseV2CacheHierarchy``). VERIFIED restore invariant: only the guest RAM
SIZE and the ArmBoard / VExpress platform must match the checkpoint; the CPU
model, cache hierarchy, and DRAM model are free (gem5 merges interleaved DRAM
into one backing store and only checks the range SIZE on restore), so a
single-channel DDR5 at the checkpoint's 16GiB restores cleanly.

Flow: prime ATOMIC active -> m5.instantiate(<checkpoint>) + tiny ATOMIC settle
-> switch ATOMIC -> Neoverse V2 -> WARMUP_INSTS (unmeasured; warms the cold
caches/predictors) -> m5.stats.reset() -> DETAILED_INSTS (measured) ->
m5.stats.dump() -> report IPC.

Usage:
    export GEM5_RESOURCE_DIR=/tmp/gem5_res    # kernel/bootloader/disk resources
    ./build/ARM/gem5.opt --outdir=/tmp/out configs/garfield/arm/fs_run.py \\
        --restore-dir <cpt.dir> --benchmark 999.specrand_r --inv 0 \\
        --warmup-insts 1000000 --detailed-insts 3000000
"""

import argparse
import json
import os
import re
import shlex
from pathlib import Path

import m5
from m5.objects import (
    ArmDefaultRelease,
    FetchDirectedPrefetcher,
    VExpress_GEM5_V1,
)
from m5.util import addToPath
from m5.util.convert import toFrequency

addToPath("../..")
# isort: split

from garfield.arm import (
    cache_hierarchy,
    neoverse_v2,
    sim_opts,
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
    DiskImageResource,
    obtain_resource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.utils.override import overrides
from gem5.utils.requires import requires

# The kernel / bootloader / disk-image resources live under GEM5_RESOURCE_DIR;
# default it to the mass-gen location if the caller has not set it.
os.environ.setdefault("GEM5_RESOURCE_DIR", "/tmp/gem5_res")

HERE = Path(__file__).resolve().parent
# tools/simpoint/invocations.json in the workloadzoo drives the (benchmark, inv)
# -> workload lookup, byte-identical to how restore_o3.py finds it.
INVOCATIONS_JSON = Path(
    "/home/ubuntu/work/garfield/gem5-workloadzoo/tools/simpoint/invocations.json"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Garfield ARM Neoverse V2 FS checkpoint-restore simulation."
    )
    # --- checkpoint / workload -------------------------------------------
    parser.add_argument(
        "--restore-dir",
        type=str,
        required=True,
        help="gem5 FS SimPoint checkpoint directory to restore (the cpt.* dir "
        "containing m5.cpt).",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="bench",
        help="Benchmark name, e.g. 999.specrand_r. Naming; also keys the "
        "invocations.json workload lookup.",
    )
    parser.add_argument(
        "--inv",
        type=str,
        default="0",
        help="Invocation index. Naming; also keys the invocations.json "
        "workload lookup.",
    )
    parser.add_argument(
        "--disk-img",
        type=str,
        default="/tmp/gem5_res/spec_shared_root.img",
        help="Shared root filesystem disk image (must be the image the "
        "checkpoint was generated against).",
    )
    # --- detailed region -------------------------------------------------
    parser.add_argument(
        "--settle-insts",
        type=int,
        default=0,
        help="ATOMIC insts to run after restore before the switch (settle; "
        "0 -> a minimum of 1).",
    )
    parser.add_argument(
        "--warmup-insts",
        type=int,
        default=int(1e6),
        help="Neoverse V2 UNMEASURED warmup insts (warms the cold "
        "caches/predictors) before the measured region.",
    )
    parser.add_argument(
        "--detailed-insts",
        type=int,
        default=int(5e6),
        help="Neoverse V2 MEASURED insts (stats.reset .. stats.dump).",
    )
    # The machine / prefetcher / garfield knobs are shared with se_run.py.
    # The DRAM model is free on restore; only the SIZE must match.
    sim_opts.add_common_args(
        parser,
        mem_size_default="16GiB",
        mem_size_help="Guest RAM capacity. MUST match the checkpoint "
        "(mass-gen checkpoints are 16GiB).",
    )
    return parser.parse_args()


args = parse_args()

requires(isa_required=ISA.ARM)


# ---- workload lookup: prefer invocations.json by (benchmark, inv) ----------
# The guest is already past this on restore, but the run-script is kept
# byte-identical to the generator so the board config stays consistent.
def load_invocation(benchmark, inv):
    try:
        entries = json.loads(INVOCATIONS_JSON.read_text())
    except Exception as e:
        print(f"  (invocations.json unavailable: {e!r}; using placeholders)")
        return "bench", [], ""
    for e in entries:
        if str(e.get("benchmark")) == benchmark and str(e.get("inv")) == str(
            inv
        ):
            return (
                os.path.basename(e["binary"]),
                e.get("args", []),
                e.get("stdin", "") or "",
            )
    print(
        f"  (no invocations.json entry for benchmark={benchmark} inv={inv}; "
        "using placeholders)"
    )
    return "bench", [], ""


binary, workload_args, stdin = load_invocation(args.benchmark, args.inv)
workdir = f"/home/gem5/{args.benchmark}/{args.inv}"

_cmd = (
    "./" + binary + (" " + shlex.join(workload_args) if workload_args else "")
)
if stdin:
    _cmd += " < " + shlex.quote(stdin)
RUN_SCRIPT = f"""#!/bin/bash
set -x
echo "GUEST: uname=$(uname -srm) nproc=$(nproc)  benchmark={args.benchmark} inv={args.inv}"
cd {shlex.quote(workdir)} || {{ echo "GUEST: no workdir {workdir}"; exit 1; }}
ls -la
M5BIN="$(command -v m5 || command -v gem5-bridge || echo /home/gem5/m5)"
echo "GUEST: m5 tool = $M5BIN"
echo "GUEST: ANCHOR (m5 workbegin) then exec: {_cmd}"
"$M5BIN" workbegin
exec {_cmd}
"""


# ---- the detailed Neoverse V2 core (identical knobs to se_run.py) ----------
def make_neoverse_v2_core():
    # cpu_id=0 must match the ATOMIC settle core: m5.switchCpus /
    # BaseCPU::takeOverFrom asserts the swapped-in and swapped-out cores share
    # a cpuId (see restore_o3.py, which primes both cores at cpu_id=0).
    core = BaseCPUCore(neoverse_v2.NeoverseV2(cpu_id=0), isa=ISA.ARM)
    sim_opts.apply_core_knobs(core.core, args)
    return core


def make_atomic_core():
    AtomicClass = SimpleCore.cpu_class_factory(
        cpu_type=CPUTypes.ATOMIC, isa=ISA.ARM
    )
    return BaseCPUCore(core=AtomicClass(cpu_id=0), isa=ISA.ARM)


# ---- cache hierarchy: identical NeoverseV2 hierarchy, FDP rebound for switch -
class RestoreNeoverseV2CacheHierarchy(
    cache_hierarchy.NeoverseV2CacheHierarchy
):
    """The identical NeoverseV2 cache hierarchy, adapted for the switchable
    restore flow.

    ``incorporate_cache`` runs *after* the ATOMIC switch core is primed active,
    so the cache PORTS bind to the ATOMIC settle core -- which is correct: the
    ATOMIC core runs the post-restore settle through the caches, and
    ``m5.switchCpus``/``takeOverFrom`` migrates those port bindings to the
    Neoverse V2 core on the switch. The L1I FDP prefetcher, however, trains off
    a fixed ``cpu`` pointer (and MMU) that do NOT migrate on the switch, so we
    rebind each FDP to the detailed Neoverse V2 core it will actually run on.
    """

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
                    # Retrain off the detailed core (its O3 FTQ probes fire
                    # only once it is switched in) and translate via its MMU.
                    pf.cpu = self._detailed_cpu
                    pf._mmus = [self._detailed_cpu.mmu]


# ---- restore switchable processor: start=Neoverse V2, switch=ATOMIC --------
class NeoverseV2RestoreProcessor(SwitchableProcessor):
    """start-key = Neoverse V2 (the detailed core we ultimately switch TO),
    switch-key = ATOMIC (primed active before m5.instantiate -- receives the
    checkpoint's ThreadContext). Same object paths (board.processor.start.core /
    .switch.core) and start/switch key names as the fs_ckpt.py generator."""

    def __init__(self, detailed_core, atomic_core):
        self._start_key = "start"
        self._switch_key = "switch"
        self._current_is_start = True
        # The core ACTIVE at m5.instantiate() (after priming) is ATOMIC, so the
        # board must be in ATOMIC memory mode for the restore; switching to the
        # Neoverse V2 core flips it to timing automatically via m5.switchCpus.
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
        """Make the ATOMIC switch core the active/switched-in one BEFORE
        m5.instantiate(), matching a checkpoint taken with ATOMIC active (the
        KVM start core serialized no ThreadContext). See fs_ckpt.py."""
        self._current_cores = self._switchable_cores[self._switch_key]
        self._current_is_start = False
        for cores in self._switchable_cores.values():
            for core in cores:
                core.set_switched_out(core not in self._current_cores)


# ---- assemble the board (ArmBoard + VExpress, per restore_o3.py) -----------
memory = sim_opts.make_memory(args)

detailed_core = make_neoverse_v2_core()

cache = RestoreNeoverseV2CacheHierarchy(
    detailed_core, **sim_opts.cache_kwargs(args)
)

processor = NeoverseV2RestoreProcessor(detailed_core, make_atomic_core())

board = ArmBoard(
    clk_freq=args.clk_freq,
    processor=processor,
    memory=memory,
    cache_hierarchy=cache,
    release=ArmDefaultRelease.for_kvm(),
    platform=VExpress_GEM5_V1(),
)

kernel = obtain_resource("arm64-linux-kernel-6.8.12", resource_version="1.0.0")
bootl = obtain_resource(
    "arm64-bootloader-foundation", resource_version="2.0.0"
)
disk = DiskImageResource(
    local_path=os.path.abspath(args.disk_img), root_partition="2"
)
board.set_kernel_disk_workload(
    kernel=kernel,
    disk_image=disk,
    bootloader=bootl,
    readfile_contents=RUN_SCRIPT,
    checkpoint=Path(args.restore_dir),
)

# Prime the ATOMIC switch core active BEFORE instantiate (restore contract).
processor.prime_switch_core_active()


print("=== garfield ARM FS restore machine ===")
print(
    f"  core     : NeoverseV2 (ArmO3CPU) restore @ {args.clk_freq} "
    f"(ATOMIC start-for-restore)"
)
for line in sim_opts.describe(args):
    print(line)
print(f"  workload : {args.benchmark} inv={args.inv}  ({binary})")
print(f"  restore  : {args.restore_dir}")
print(
    f"  region   : settle={max(1, args.settle_insts):,} "
    f"warmup={args.warmup_insts:,} detailed={args.detailed_insts:,}"
)


# ---- run: restore(ATOMIC) -> switch(Neoverse V2) -> warmup -> detailed -----
def _stopper():
    # every schedule_max_insts returns control from simulator.run()
    while True:
        yield True


simulator = Simulator(
    board=board, on_exit_event={ExitEvent.MAX_INSTS: _stopper()}
)

# (1) instantiate + restore the checkpoint; run a tiny ATOMIC settle so the
#     restored state is live and drainable before the CPU handover.
settle = max(1, args.settle_insts)
print(
    f">>> instantiate + restore {args.restore_dir}; ATOMIC settle {settle:,} ..."
)
simulator.schedule_max_insts(settle)
simulator.run()
print(f">>> restored; insts={simulator.get_instruction_count()}")

# (2) switch ATOMIC(switch) -> Neoverse V2(start); m5.switchCpus flips the
#     system to timing memory mode automatically.
print(">>> switch ATOMIC -> Neoverse V2 (detailed) ...")
simulator.switch_processor()

# (3) Neoverse V2 UNMEASURED warmup (warms the cold caches / predictors)
if args.warmup_insts > 0:
    print(
        f">>> Neoverse V2 warmup {args.warmup_insts:,} insts (unmeasured) ..."
    )
    simulator.schedule_max_insts(args.warmup_insts)
    simulator.run()

# (4) reset stats, run the MEASURED detailed region, dump stats
print(f">>> Neoverse V2 detailed {args.detailed_insts:,} insts (measured) ...")
m5.stats.reset()
insts0 = detailed_core.get_total_instructions()
tick0 = m5.curTick()
simulator.schedule_max_insts(args.detailed_insts)
simulator.run()
tick1 = m5.curTick()
insts1 = detailed_core.get_total_instructions()
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
