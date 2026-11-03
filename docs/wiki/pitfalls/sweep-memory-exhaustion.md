---
type: pitfall
status: current
updated: 2026-11-03
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
  - run_scripts/tasktrace/smart_sweep.sh
  - src/mem/physical.cc
tags: [sweep, memory, host]
---

# Parallel sweeps can OOM-kill the whole session

**What happened (2026-10-16 to 2026-10-19):** three `sweep.sh` (infinite
BTB, infinite TLB, both; `PAR=4` each) were killed three times. systemd-oomd
killed the whole terminal scope (58 processes, a 58.5 GB peak), including
the shell and a Claude session. The sweeps walk checkpoints in the same
order, so a resume restored the same heavy task several times at once.

**Memory per run** = the checkpoint's in-use guest memory, reached within
~30 s of the restore and then flat: most agentic tasks 2.5–6 GB
(fastlane 2.8, carbon 3.0, fmt-3901 3.2, core 3.8, babel 5.7),
**docusaurus-9897 ≈ 11 GB, nushell-13831 22.2 GB**. The compressed memory
image size does not predict it: both heavy tasks have 3.7 GB of images, but
nushell expands to twice docusaurus. The limit-study structures add about
0.2 GB; per-run analyses peak at 1.1 GB.

**What to do:** use `smart_sweep.sh` ([[sweeps]]). It gates every launch on
available memory minus what running runs still need, from measured peaks
(`run_scripts/tasktrace/mem_peaks.tsv`, tracked in git). Its first version (estimate from image size,
check only at launch) was not enough and was itself OOM-killed.

**Since 2026-11-03** it also:
- counts every gem5 on the host, including other users' (the machine is
  shared with a second user, whose runs were invisible to the gate before);
- holds launches while the kernel reports memory pressure;
- caps each run in its own systemd user scope, with no swap. A run that
  outgrows its cap is killed alone, and the terminal, the other runs and
  the other user's work stay up.

**How a gem5 run dies of memory.** gem5 maps guest memory with
`MAP_NORESERVE` (`src/mem/physical.cc`), so pages are taken only when
touched and an allocation never fails inside gem5. Short of memory, the
kernel kills it with SIGKILL: no clean exit and no final stats dump.
`stats.txt` ends at the last finished block, and the launcher exits 137
(`pipefail`). Without a per-run cap, the kill comes from systemd-oomd (the
whole terminal scope, after 20 s above 50% pressure on the user's service
tree) or from the kernel's global OOM killer (the largest process on the
host, whoever owns it).
