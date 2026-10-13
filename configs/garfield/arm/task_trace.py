# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD

"""Attach the guest task tracer (ArmLinuxTaskTracer) to a restore.

The tracer needs two things about the guest kernel: its KASLR slide, which
RPoint records per checkpoint in provenance.json (`landing.kaslr_slide`),
and its struct layout, read from the vmlinux by kernel_layout.py.
"""

import json
from pathlib import Path

from m5.objects import ArmLinuxTaskTracer

from garfield.arm import kernel_layout


def add_args(parser):
    group = parser.add_argument_group("guest task trace")
    group.add_argument(
        "--task-trace",
        action="store_true",
        help="Trace guest context switches, forks, execs, renames, exits "
        "and the write() payloads of --task-trace-process into "
        "<outdir>/tasktrace.jsonl.",
    )
    group.add_argument(
        "--task-trace-slide",
        type=lambda s: int(s, 0),
        default=None,
        help="Expected guest kernel KASLR slide; the tracer derives the "
        "slide from guest memory and stops if it differs. Default: "
        "landing.kaslr_slide from <restore-dir>/provenance.json, if any.",
    )
    group.add_argument(
        "--task-trace-process",
        default="opencode",
        help="Process whose write() calls are recorded with file path and "
        "payload (OpenCode's event log and session storage), and whose "
        "read() calls are recorded with file path, size and offset; empty "
        "to disable both.",
    )


def kaslr_slide(restore_dir):
    """The slide RPoint's landing labeller recorded, or None.

    The tracer derives the slide from guest memory itself; a recorded value
    only cross-checks it.
    """
    prov = Path(restore_dir) / "provenance.json"
    try:
        return int(json.loads(prov.read_text())["landing"]["kaslr_slide"], 16)
    except (OSError, KeyError, TypeError, ValueError):
        return None


def attach(board, args):
    """Add the tracer to board; return banner lines describing it."""
    slide = args.task_trace_slide
    if slide is None:
        slide = kaslr_slide(args.restore_dir)
    layout = kernel_layout.extract(args.kernel)
    kwargs = {} if slide is None else {"kaslr_slide": slide}
    board.task_tracer = ArmLinuxTaskTracer(
        vmlinux=str(Path(args.kernel).resolve()),
        write_process=args.task_trace_process,
        read_process=args.task_trace_process,
        **kwargs,
        **layout,
    )
    expected = "none" if slide is None else f"{slide:#x}"
    return [
        f"  tasktrace: slide derived from guest memory (expected: "
        f"{expected}) write-process={args.task_trace_process or '(off)'}"
    ]
