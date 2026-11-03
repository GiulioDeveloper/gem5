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

"""Simulation knobs shared by every garfield ARM run-mode driver.

``se_run.py`` (syscall emulation) and ``fs_run.py`` (full-system checkpoint
restore) build the *same* Neoverse V2 machine and differ only in how the
workload gets in front of it. Everything that describes the machine rather
than the run mode lives here so the drivers cannot drift apart:

  * the DRAM model presets (``MEM_FACTORIES``) and ``--clk-freq`` /
    ``--mem-type`` / ``--mem-size``,
  * the front-end / prefetcher ablation switches (``--disable-fdp``,
    ``--disable-l1d-prefetch``, ``--disable-l2-prefetch``) and the limit
    studies (``--infinite-btb``, ``--infinite-tlb``, ``--perfect-tlb``,
    ``--cache-scale``, ``--perfect-l2``, ``--perfect-l1i``),
  * ``--progress-interval``,
  * the garfield knobs (``--ghost-exec`` and the ``--use-mrn`` / ``--mrn-*``
    memory-rename-predictor family).

A driver registers them with :func:`add_common_args`, then turns the parsed
namespace into objects with :func:`make_memory`, :func:`cache_kwargs` and
:func:`apply_core_knobs`. Run-mode-specific knobs (the workload, the
checkpoint, the region lengths) stay in the driver that owns them.
"""

import argparse

from m5.objects import (
    EvesVP,
    EVtageVP,
    LastValueVP,
    MemRenamePredictor,
    VtageVP,
)

from m5.util.convert import toFrequency

from garfield.arm.neoverse_v2 import (
    L1I,
    L2,
    NeoverseV2_InfiniteBTB,
    NeoverseV2_InfiniteL2TLB,
)

from gem5.components.memory.simple import SingleChannelSimpleMemory
from gem5.components.memory.single_channel import (
    DIMM_DDR5_4400,
    DIMM_DDR5_6400,
    DIMM_DDR5_8400,
    SingleChannelDDR4_2400,
)

MEM_FACTORIES = {
    "DDR4_2400": SingleChannelDDR4_2400,
    "DDR5_4400": DIMM_DDR5_4400,
    "DDR5_6400": DIMM_DDR5_6400,
    "DDR5_8400": DIMM_DDR5_8400,
}


def add_common_args(
    parser,
    mem_size_default="16GiB",
    mem_size_help="Guest RAM capacity.",
):
    """Register the shared simulation knobs on ``parser``.

    ``mem_size_default`` / ``mem_size_help`` are parameterized because the
    run modes disagree: SE picks its own DRAM size freely, while an FS
    restore MUST match the size baked into the checkpoint.
    """
    machine = parser.add_argument_group("machine")
    machine.add_argument(
        "--clk-freq",
        type=str,
        default="3GHz",
        help="Core/board clock frequency.",
    )
    machine.add_argument(
        "--mem-type",
        type=str,
        default="DDR5_6400",
        choices=list(MEM_FACTORIES.keys()),
        help="DRAM model preset.",
    )
    machine.add_argument(
        "--mem-size",
        type=str,
        default=mem_size_default,
        help=mem_size_help,
    )
    machine.add_argument(
        "--progress-interval",
        type=str,
        default="0Hz",
        help="CPU progress-heartbeat frequency (e.g. 1kHz); 0Hz disables.",
    )

    prefetch = parser.add_argument_group("prefetcher / front-end ablation")
    prefetch.add_argument(
        "--disable-fdp",
        action="store_true",
        help="Disable the decoupled front-end + L1I FDP prefetcher.",
    )
    prefetch.add_argument(
        "--infinite-btb",
        action="store_true",
        help="Replace the BTB with an unbounded, ASID-separated one "
        "(limit study; docs/wiki/hardware/infinite-btb-model.md).",
    )
    prefetch.add_argument(
        "--infinite-tlb",
        action="store_true",
        help="Replace the shared L2 TLB with a 1M-entry one (limit "
        "study; docs/wiki/hardware/infinite-l2-tlb.md).",
    )
    prefetch.add_argument(
        "--perfect-tlb",
        action="store_true",
        help="Serve every demand TLB miss with a zero-time functional "
        "walk: translations always hit (limit study; "
        "docs/wiki/experiments/2026-11-02-perfect-l2.md). Prefetch "
        "translations still drop on a miss.",
    )
    prefetch.add_argument(
        "--cache-scale",
        type=int,
        default=1,
        choices=(1, 2, 4, 8, 16),
        help="Multiply the L1I, L1D and L2 sizes by N, keeping their "
        "associativity and latencies (capacity limit study).",
    )
    prefetch.add_argument(
        "--perfect-l2",
        action="store_true",
        help="Remove the L2 and serve every L1 miss from a fixed-latency "
        "memory at --perfect-l2-cycles, behind a bus timed like the L2 "
        "crossbar: an L2 that always hits (limit study; "
        "docs/wiki/experiments/2026-11-02-perfect-l2.md). Replaces "
        "--mem-type.",
    )
    prefetch.add_argument(
        "--perfect-l2-cycles",
        type=int,
        default=max(L2.tag_latency, L2.data_latency),
        help="Latency of the --perfect-l2 memory in core cycles "
        "(default: the L2 hit latency).",
    )
    prefetch.add_argument(
        "--perfect-l1i",
        action="store_true",
        help="Serve every fetch with a functional read delivered after "
        "--perfect-l1i-cycles: an L1I that always hits, leaving all L2 "
        "capacity and bandwidth to data (limit study; "
        "docs/wiki/experiments/2026-11-03-perfect-l1i.md). Detaches the "
        "FDP prefetcher; the decoupled front end stays on.",
    )
    prefetch.add_argument(
        "--perfect-l1i-cycles",
        type=int,
        default=max(L1I.tag_latency, L1I.data_latency),
        help="Latency of a --perfect-l1i read in core cycles "
        "(default: the L1I hit latency).",
    )
    prefetch.add_argument(
        "--disable-l1d-prefetch",
        action="store_true",
        help="Disable the L1D Stride+SMS prefetcher stack.",
    )
    prefetch.add_argument(
        "--disable-l2-prefetch",
        action="store_true",
        help="Disable the L2 BOP prefetcher.",
    )

    garfield = parser.add_argument_group("garfield")
    garfield.add_argument(
        "--ghost-exec",
        action="store_true",
        help="Garfield: ghost-execute control uops (skip OoO IQ entry, "
        "issue bandwidth, execution port).",
    )
    garfield.add_argument(
        "--use-mrn",
        action="store_true",
        help="Garfield: attach the memory-rename predictor (MRN). When "
        "absent, MRN stays disabled (NULL).",
    )
    garfield.add_argument(
        "--mrn-conf-bits",
        type=int,
        default=4,
        help="MRN confidence-counter width in bits.",
    )
    garfield.add_argument(
        "--mrn-conf-threshold",
        type=int,
        default=8,
        help="MRN minimum confidence required to predict.",
    )
    garfield.add_argument(
        "--vp-before-mrn",
        action="store_true",
        help="Flip the rename consumption ladder: VP claims first, MRN "
        "value-forwarding only takes loads VP left unclaimed. "
        "Incompatible with --mrn-alias.",
    )
    garfield.add_argument(
        "--mrn-alias",
        action="store_true",
        help="Enable the MRN producer-aliasing path (off by default). "
        "Independent of value forwarding; when both are on, aliasing takes "
        "priority.",
    )
    garfield.add_argument(
        "--mrn-lv-stability-target",
        type=int,
        default=0,
        help="Address-instability hysteresis: consecutive same-line "
        "executes required to re-enable last-value forwarding after two "
        "strikes (0 = gate disabled).",
    )
    garfield.add_argument(
        "--mrn-lv-flush-ledger",
        action="store_true",
        help="Replace the stability gate's count-based earning test "
        "with the flush-weighted ledger (spared while corrects x "
        "benefit-per-correct covers accumulated measured flush cost).",
    )
    garfield.add_argument(
        "--mrn-lv-benefit-per-correct",
        type=float,
        default=1.0,
        help="Ledger benefit credited per correct verify, in "
        "flushed-instruction equivalents.",
    )
    garfield.add_argument(
        "--mrn-vf-no-producer-value",
        action="store_true",
        help="Value-file correlation: disable forwarding the producer "
        "physreg's value when it is already ready at the load's rename "
        "(on by default).",
    )
    garfield.add_argument(
        "--mrn-vf-no-last-value",
        action="store_true",
        help="Value-file correlation: disable forwarding the last value "
        "from a self-bound cell (on by default).",
    )
    garfield.add_argument(
        "--use-vp",
        type=str,
        choices=["lvp", "vtage", "evtage", "eves"],
        default=None,
        metavar="TYPE",
        help="Garfield: attach a value predictor of the given type "
        "(lvp = last-value predictor; vtage = VTAGE, PC x history "
        "tagged prediction; evtage = E-VTAGE, CVP-1 EVES's per-class "
        "probabilistic update policy at the same table geometry; "
        "eves = full EVES (E-VTAGE + E-Stride)). Absent = VP disabled "
        "(NULL).",
    )
    garfield.add_argument(
        "--vp-all-insts",
        action="store_true",
        help="VP scope: predict all eligible instructions, not only loads.",
    )
    garfield.add_argument(
        "--vp-entries",
        type=int,
        default=4096,
        help="VP table entries.",
    )
    garfield.add_argument(
        "--vp-assoc",
        type=int,
        default=4,
        help="VP table associativity.",
    )
    garfield.add_argument(
        "--vp-conf-bits",
        type=int,
        default=4,
        help="VP confidence-counter width in bits.",
    )
    garfield.add_argument(
        "--vp-conf-threshold",
        type=int,
        default=15,
        help="VP minimum confidence required to predict (minimum 1).",
    )
    garfield.add_argument(
        "--vp-conf-decrement",
        action="store_true",
        help="Decrement (rather than reset) VP confidence on a value "
        "mismatch, clamped below the confidence threshold.",
    )
    garfield.add_argument(
        "--vtage-conf-threshold",
        type=int,
        default=7,
        help="VTAGE minimum confidence required to predict (minimum "
        "1; HPCA'14 default is saturation, 7).",
    )
    garfield.add_argument(
        "--vtage-hist-lengths",
        type=_vtage_hist_lengths,
        default=None,
        metavar="L1,L2,...",
        help="VTAGE per-tagged-component history lengths, shortest to "
        "longest (comma-separated, each in [1, 128], strictly "
        "increasing); also sets numTagged to the list's length. "
        "Absent = the HPCA'14 default geometry (2,4,8,16,32,64).",
    )
    garfield.add_argument(
        "--evtage-burst-guard",
        type=int,
        default=0,
        metavar="WINDOW",
        help="E-VTAGE / EVES burst-misprediction guard window in "
        "renamed instructions (0 = off, the ratified-fork default; "
        "128 = CVP-1 EVES's own behavior). E-VTAGE's own guard stays "
        "locked off (fatal_if); only EVES honors a nonzero window.",
    )
    garfield.add_argument(
        "--evtage-conf-threshold",
        type=int,
        default=7,
        help="E-VTAGE / EVES minimum confidence required to predict "
        "(minimum 1; CVP-1 default is saturation, 7). Note the "
        "confidence-increment gate is per-class probabilistic "
        "(design doc S1), not a fixed per-transition rate, so "
        "reaching the default threshold takes materially longer than "
        "plain VTAGE's FPC.",
    )
    garfield.add_argument(
        "--evtage-hist-lengths",
        type=_vtage_hist_lengths,
        default=None,
        metavar="L1,L2,...",
        help="E-VTAGE / EVES per-tagged-component history lengths, "
        "shortest to longest (same validation as "
        "--vtage-hist-lengths); also sets numTagged to the list's "
        "length. Absent = E-VTAGE's own default geometry "
        "(2,4,8,16,32,64).",
    )
    garfield.add_argument(
        "--eves-vtage-overwrite-verbatim",
        action="store_true",
        help="EVES arbitration ablation: restore the CVP-1 source's "
        "write-order overwrite (a VTAGE tag hit overwrites the stride "
        "value even below confidence). Default off: the overwrite "
        "requires E-VTAGE confidence, the 190-checkpoint A/B winner.",
    )
    return parser


def _vtage_hist_lengths(text):
    """Parse --vtage-hist-lengths: comma-separated ints, each in
    [1, 128], strictly increasing."""
    try:
        lengths = [int(tok) for tok in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected comma-separated integers, got {text!r}"
        )
    for length in lengths:
        if not 1 <= length <= 128:
            raise argparse.ArgumentTypeError(
                f"history length {length} outside [1, 128]"
            )
    if any(b <= a for a, b in zip(lengths, lengths[1:])):
        raise argparse.ArgumentTypeError(
            f"history lengths must be strictly increasing, got {text!r}"
        )
    return lengths


def make_memory(args):
    """The single-channel DRAM selected by --mem-type / --mem-size, or the
    fixed-latency memory standing in for the L2 under --perfect-l2."""
    if args.perfect_l2:
        # Whole ticks per cycle, as gem5 rounds the clock period, so
        # responses land on clock edges.
        period_ps = round(1e12 / toFrequency(args.clk_freq))
        return SingleChannelSimpleMemory(
            latency=f"{args.perfect_l2_cycles * period_ps}ps",
            latency_var="0ns",
            bandwidth="1TiB/s",
            size=args.mem_size,
        )
    return MEM_FACTORIES[args.mem_type](size=args.mem_size)


def cache_kwargs(args):
    """The NeoverseV2CacheHierarchy ablation kwargs implied by ``args``.

    Returned as a dict rather than a built hierarchy so a driver can feed
    them to a subclass (the FS restore wraps the hierarchy to rebind FDP).
    """
    return {
        # Under --perfect-l1i nothing reads the L1I; FDP would only push
        # instruction lines into the L2.
        "enable_fdp": not (args.disable_fdp or args.perfect_l1i),
        "enable_l1d_prefetch": not args.disable_l1d_prefetch,
        "enable_l2_prefetch": not args.disable_l2_prefetch,
        "cache_scale": args.cache_scale,
        "perfect_l2": args.perfect_l2,
    }


def make_mrn(args):
    """The MemRenamePredictor described by the --mrn-* knobs, or None."""
    if not args.use_mrn:
        return None
    return MemRenamePredictor(
        confBits=args.mrn_conf_bits,
        confThreshold=args.mrn_conf_threshold,
        enableProducerAliasing=args.mrn_alias,
        vfForwardProducerValue=not args.mrn_vf_no_producer_value,
        vfForwardLastValue=not args.mrn_vf_no_last_value,
        lvStabilityTarget=args.mrn_lv_stability_target,
        lvFlushLedger=args.mrn_lv_flush_ledger,
        lvBenefitPerCorrect=args.mrn_lv_benefit_per_correct,
    )


def make_vp(args):
    """The value predictor selected by --use-vp, or None."""
    if args.use_vp is None:
        return None
    if args.use_vp == "vtage":
        kwargs = {}
        if args.vtage_hist_lengths is not None:
            kwargs["historyLengths"] = args.vtage_hist_lengths
            kwargs["numTagged"] = len(args.vtage_hist_lengths)
        return VtageVP(
            onlyLoads=not args.vp_all_insts,
            confThreshold=args.vtage_conf_threshold,
            **kwargs,
        )
    if args.use_vp == "evtage":
        kwargs = {}
        if args.evtage_hist_lengths is not None:
            kwargs["historyLengths"] = args.evtage_hist_lengths
            kwargs["numTagged"] = len(args.evtage_hist_lengths)
        return EVtageVP(
            onlyLoads=not args.vp_all_insts,
            burstGuardWindow=args.evtage_burst_guard,
            confThreshold=args.evtage_conf_threshold,
            **kwargs,
        )
    if args.use_vp == "eves":
        kwargs = {}
        if args.evtage_hist_lengths is not None:
            kwargs["historyLengths"] = args.evtage_hist_lengths
            kwargs["numTagged"] = len(args.evtage_hist_lengths)
        return EvesVP(
            onlyLoads=not args.vp_all_insts,
            burstGuardWindow=args.evtage_burst_guard,
            confThreshold=args.evtage_conf_threshold,
            vtageOverwriteRequiresConfidence=(
                not args.eves_vtage_overwrite_verbatim
            ),
            **kwargs,
        )
    assert args.use_vp == "lvp"
    return LastValueVP(
        onlyLoads=not args.vp_all_insts,
        entries=args.vp_entries,
        assoc=args.vp_assoc,
        confBits=args.vp_conf_bits,
        confThreshold=args.vp_conf_threshold,
        confDecrementOnWrong=args.vp_conf_decrement,
    )


def apply_core_knobs(cpu, args):
    """Apply the shared per-core knobs to one ArmO3CPU (Neoverse V2)."""
    if args.disable_fdp:
        cpu.decoupledFrontEnd = False
    if args.infinite_btb:
        cpu.branchPred.btb = NeoverseV2_InfiniteBTB()
    if args.infinite_tlb and args.perfect_tlb:
        raise SystemExit(
            "--infinite-tlb has no effect under --perfect-tlb: no TLB "
            "lookup misses"
        )
    if args.infinite_tlb:
        cpu.mmu.l2_shared = NeoverseV2_InfiniteL2TLB()
    cpu.mmu.perfect_tlb = args.perfect_tlb
    cpu.perfectICache = args.perfect_l1i
    cpu.perfectICacheLatency = args.perfect_l1i_cycles
    cpu.progress_interval = args.progress_interval
    cpu.ghostExec = args.ghost_exec
    mrn = make_mrn(args)
    if mrn is not None:
        cpu.memRenamePredictor = mrn
    vp = make_vp(args)
    if vp is not None:
        cpu.valuePred = vp
    if args.vp_before_mrn:
        if args.mrn_alias:
            raise SystemExit(
                "--vp-before-mrn is incompatible with --mrn-alias: the "
                "producer-alias path diverts renaming before the VP "
                "decision exists"
            )
        cpu.vpBeforeMrn = True


def _mrn_banner(args):
    """MRN banner fragment naming the active consumption modes."""
    if not args.use_mrn:
        return "off"
    modes = []
    if args.mrn_alias:
        modes.append("alias")
    if not args.mrn_vf_no_producer_value:
        modes.append("producerValue")
    if not args.mrn_vf_no_last_value:
        modes.append("lastValue")
    return (
        f"on ({'+'.join(modes) if modes else 'none'}) "
        f"confThreshold={args.mrn_conf_threshold}"
    )


def _vp_banner(args):
    """VP banner fragment naming the predictor and scope."""
    if not args.use_vp:
        return "off"
    scope = "all-insts" if args.vp_all_insts else "loads-only"
    return f"{args.use_vp} ({scope}) confThreshold={args.vp_conf_threshold}"


def _l2tlb_banner(args):
    """L2 TLB banner fragment."""
    if args.perfect_tlb:
        return "perfect"
    return "1M" if args.infinite_tlb else "2K"


def describe(args):
    """The machine banner lines implied by the shared knobs."""
    if args.perfect_l2:
        l2 = f"L2 perfect ({args.perfect_l2_cycles} cyc)"
        l2pf = "none"
        dram = f"perfect-L2 SimpleMemory @ {args.mem_size}"
    else:
        l2 = f"L2 {2 * args.cache_scale}MiB"
        l2pf = "off" if args.disable_l2_prefetch else "on"
        dram = f"{args.mem_type} @ {args.mem_size}"
    l1d = f"{64 * args.cache_scale}KiB"
    if args.perfect_l1i:
        l1 = f"L1I perfect ({args.perfect_l1i_cycles} cyc), L1D {l1d}"
    else:
        l1 = f"L1I/L1D {l1d}"
    fdp_off = args.disable_fdp or args.perfect_l1i
    return [
        f"  caches   : {l1}, {l2} | "
        f"FDP={'off' if fdp_off else 'on'}, "
        f"L1Dpf={'off' if args.disable_l1d_prefetch else 'on'}, "
        f"L2pf={l2pf}, "
        f"BTB={'infinite' if args.infinite_btb else 'neoverse-v2'}, "
        f"L2TLB={_l2tlb_banner(args)}",
        f"  dram     : {dram}",
        f"  mrn      : "
        f"{_mrn_banner(args)}"
        f"  ghostExec={args.ghost_exec}",
        f"  vp       : {_vp_banner(args)}",
    ]
