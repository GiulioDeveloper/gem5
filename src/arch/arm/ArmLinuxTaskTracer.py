# LICENSE-PLACEHOLDER: GARFIELD-LICENSE-TBD

from m5.params import *
from m5.proxy import *
from m5.SimObject import SimObject


class ArmLinuxTaskTracer(SimObject):
    """Trace an AArch64 Linux guest's scheduling and process lifecycle.

    Installs read-only PC events on kernel functions (context switch, fork,
    exec, rename, exit, file write) and writes one JSON object per event,
    stamped with the tick and the global committed-instruction count. The
    struct offsets must match the guest kernel exactly; derive them from the
    vmlinux with configs/garfield/arm/kernel_layout.py.
    """

    type = "ArmLinuxTaskTracer"
    cxx_header = "arch/arm/linux/task_tracer.hh"
    cxx_class = "gem5::ArmISA::LinuxTaskTracer"

    system = Param.System(Parent.any, "System whose threads are traced")
    vmlinux = Param.String("Guest kernel ELF, used for its symbol table")
    kaslr_slide = Param.UInt64(
        0xFFFFFFFFFFFFFFFF,
        "Expected runtime minus link-time address of the guest kernel "
        "(KASLR). The tracer always derives the slide from guest memory; "
        "if this is set, a different derived value is fatal.",
    )
    output = Param.String(
        "tasktrace.jsonl", "Output file, relative to the gem5 outdir"
    )

    task_pid = Param.Unsigned("offsetof(task_struct, pid)")
    task_tgid = Param.Unsigned("offsetof(task_struct, tgid)")
    task_comm = Param.Unsigned("offsetof(task_struct, comm)")
    task_comm_len = Param.Unsigned("sizeof(task_struct.comm)")
    task_group_leader = Param.Unsigned("offsetof(task_struct, group_leader)")
    task_real_parent = Param.Unsigned("offsetof(task_struct, real_parent)")
    task_mm = Param.Unsigned("offsetof(task_struct, mm)")
    task_flags = Param.Unsigned("offsetof(task_struct, flags)")
    task_tasks = Param.Unsigned("offsetof(task_struct, tasks)")
    task_thread_node = Param.Unsigned("offsetof(task_struct, thread_node)")
    task_nsproxy = Param.Unsigned("offsetof(task_struct, nsproxy)")
    task_cgroups = Param.Unsigned("offsetof(task_struct, cgroups)")
    file_f_path = Param.Unsigned("offsetof(file, f_path)")
    path_dentry = Param.Unsigned("offsetof(path, dentry)")
    dentry_d_name = Param.Unsigned("offsetof(dentry, d_name)")
    dentry_d_parent = Param.Unsigned("offsetof(dentry, d_parent)")
    qstr_name = Param.Unsigned("offsetof(qstr, name)")
    pt_regs_regs = Param.Unsigned("offsetof(pt_regs, regs)")
    list_next = Param.Unsigned("offsetof(list_head, next)")

    write_process = Param.String(
        "opencode",
        "Record write() payloads only from threads of this process "
        "(thread-group leader name); empty disables write tracing",
    )
    write_prefix = Param.String(
        "",
        "Record a write only if its payload starts with this string "
        "(empty: every write of write_process)",
    )
    write_files = VectorParam.String(
        ["cgroup.procs"],
        "Record writes to files with these names from any process (with "
        "the default, the moment a task is moved into a cgroup, e.g. "
        "OpenCode's tools fence)",
    )
    read_process = Param.String(
        "opencode",
        "Record read() calls (file, size, offset; not the data) of threads "
        "of this process; empty disables read tracing",
    )
    snapshot = Param.Bool(
        True,
        "At start-up, record every process and thread alive in the guest",
    )
    max_write_bytes = Param.Unsigned(
        65536, "Longest write payload recorded (longer ones are truncated)"
    )
    max_string_bytes = Param.Unsigned(
        4096, "Longest exec path or argv string recorded"
    )
    max_argv = Param.Unsigned(64, "Most argv entries recorded per exec")
