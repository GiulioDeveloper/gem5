---
type: gem5
status: current
updated: 2026-10-21
sources:
  - "CLAUDE.md at commit 24f434b18f"
tags: [gem5, events, ports, stats]
---

# Simulation core: events, ports, base infrastructure

gem5 is event-driven. A global `EventQueue` (`src/sim/eventq.hh`) orders
`Event`s by `(Tick, priority)`, and `curTick()` is the global clock (1 tick
= 1 ps in our configs). SimObjects `schedule()` events. The usual helpers
are `EventFunctionWrapper` and `MemberEventWrapper<&Cls::method>`. `Tick`
and `Cycles` are defined in `src/base/types.hh`.

- **Ports and packets** (`src/mem/port.hh`, `src/mem/packet.hh`):
  components connect `RequestPort` ↔ `ResponsePort`, and memory traffic is
  `Packet`s carried by the Atomic, Timing or Functional protocols.
  `SimObject::getPort` resolves a named port.
- **Reused infrastructure** in `src/base/`:
  - `statistics::Group` for stats;
  - `DPRINTF` tracing (`src/base/trace.hh`);
  - `panic` / `fatal` / `warn`;
  - `AddrRange`;
  - serialization (`Serializable`, `Drainable`).
- **Stats:** `m5.stats.dump()` / `reset()` produce `stats.txt` blocks. The
  fork's `--stats-interval-insts` dumps a block every N committed
  instructions ([[stats-blocks]]).

See also [[isa-dsl]] for the ISAs and [[memory-system]] for the memory
system.
