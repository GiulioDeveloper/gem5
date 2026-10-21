---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-08-task-tracer]]"
  - configs/garfield/arm/neoverse_v2.py
tags: [tlb, config, stale-results]
---

# The L2 TLB was disconnected before 2026-10-13

**What happened:** `NeoverseMMU` (`configs/garfield/arm/neoverse_v2.py`)
overrode `itb` and `dtb` without `next_level=Parent.l2_shared`, which the
base `ArmMMU` sets. In `config.ini` both L1 TLBs had `next_level=Null` and
`mmu.l2_shared.accesses` was 0, so **every L1 TLB miss went straight to a
page walk** (34K walks per 1M instructions in a gin-2121 window). Fixed on
2026-10-13 (commit 054bb4126c): both point at `l2_shared`.

**What it affects:**
- Every O3 result from before 2026-10-13: the early agentic windows
  ([[2026-10-08-tool-call-windows]]) and **every Garfield result**
  ([[garfield-overview]]). Their iTLB/dTLB miss and page-walk figures, and
  to a lesser degree their IPC, are not comparable with later runs.
- The sweeps from 2026-10-14 on are after the fix.

**How to spot this class of bug:** a stat that should be non-zero is
exactly 0 (`l2_shared.accesses`); check `config.ini` for `next_level` and
similar proxy parameters after subclassing a stock SimObject and overriding
its children.
