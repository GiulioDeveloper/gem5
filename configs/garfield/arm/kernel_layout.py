# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD

"""Struct field offsets of a guest Linux kernel, read from its vmlinux.

The task tracer (ArmLinuxTaskTracer) reads task_struct and friends straight
out of guest memory, so it needs the field offsets of the exact kernel the
guest booted. They come from the vmlinux's DWARF, evaluated by gdb: the
expression `&((struct T *)0)->a.b` follows anonymous unions and nested
members, which a hand-written DWARF walk would have to reimplement.

Kernels built with CONFIG_DEBUG_INFO_REDUCED (-femit-struct-debug-baseonly)
only carry the layout of some structs; the fields below are restricted to
ones such a kernel still describes (task_struct, file, dentry, qstr,
pt_regs). A
missing field is fatal: a guessed offset would produce plausible garbage.

Standalone use prints the layout as JSON:

    python3 configs/garfield/arm/kernel_layout.py <vmlinux>
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile

# tracer parameter name -> gdb expression yielding the byte offset.
OFFSETS = {
    "task_pid": "&((struct task_struct *)0)->pid",
    "task_tgid": "&((struct task_struct *)0)->tgid",
    "task_comm": "&((struct task_struct *)0)->comm",
    "task_group_leader": "&((struct task_struct *)0)->group_leader",
    "task_real_parent": "&((struct task_struct *)0)->real_parent",
    "task_mm": "&((struct task_struct *)0)->mm",
    "task_flags": "&((struct task_struct *)0)->flags",
    "task_tasks": "&((struct task_struct *)0)->tasks",
    "task_thread_node": "&((struct task_struct *)0)->thread_node",
    "task_nsproxy": "&((struct task_struct *)0)->nsproxy",
    "task_cgroups": "&((struct task_struct *)0)->cgroups",
    "file_f_path": "&((struct file *)0)->f_path",
    "dentry_d_name": "&((struct dentry *)0)->d_name",
    "dentry_d_parent": "&((struct dentry *)0)->d_parent",
    "qstr_name": "&((struct qstr *)0)->name",
    "pt_regs_regs": "&((struct pt_regs *)0)->regs",
}
SIZES = {
    "task_comm_len": "sizeof(((struct task_struct *)0)->comm)",
}
# struct path is only declared in a reduced-debug-info kernel. Its layout,
# { struct vfsmount *mnt; struct dentry *dentry; }, has not changed since
# Linux 2.6, so the dentry pointer is taken to follow the mount pointer.
# struct list_head is likewise only declared; its layout
# { struct list_head *next, *prev; } is fixed kernel-wide.
ASSUMED = {
    "path_dentry": 8,
    "list_next": 0,
}

_VALUE = re.compile(r"^\$(\d+) = (\d+)$")


def extract(vmlinux, gdb=None):
    """Return {param name: int} for every OFFSETS/SIZES entry plus ASSUMED.

    Raises RuntimeError naming every field gdb could not resolve.
    """
    gdb = gdb or shutil.which("gdb")
    if gdb is None:
        raise RuntimeError("gdb not found on PATH; needed to read vmlinux")
    names = list(OFFSETS) + list(SIZES)
    exprs = list(OFFSETS.values()) + list(SIZES.values())
    with tempfile.NamedTemporaryFile("w", suffix=".gdb") as script:
        for expr in exprs:
            script.write(f"print (unsigned long)({expr})\n")
        script.flush()
        # gdb keeps going after a failed print, so one run reports every
        # missing field; values are matched back by their $N history index.
        out = subprocess.run(
            [gdb, "-nx", "-batch", "-x", script.name, vmlinux],
            capture_output=True,
            text=True,
            check=False,
        )
    values = {}
    for line in out.stdout.splitlines():
        m = _VALUE.match(line.strip())
        if m:
            values[int(m.group(1))] = int(m.group(2))
    # A failed print does not consume a history number, so successes are
    # numbered consecutively; any failure therefore shifts the mapping and
    # is detected by the count check below.
    if len(values) != len(exprs):
        raise RuntimeError(
            f"gdb resolved {len(values)} of {len(exprs)} kernel fields in "
            f"{vmlinux}:\n{out.stderr.strip()}"
        )
    layout = {name: values[i + 1] for i, name in enumerate(names)}
    layout.update(ASSUMED)
    return layout


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <vmlinux>")
    print(json.dumps(extract(sys.argv[1]), indent=1, sort_keys=True))
