---
type: gem5
status: current
updated: 2026-11-06
sources:
  - src/mem/cache/base.cc
  - src/mem/packet.cc
  - src/mem/packet.hh
  - src/mem/coherent_xbar.cc
  - src/mem/mem_ctrl.cc
  - src/mem/snoop_filter.cc
  - src/cpu/o3/lsq_unit.cc
  - src/cpu/o3/iew.cc
tags: [gem5, memory, cache, functional, limit-study]
---

# Functional memory access and masked writes

A functional access (`sendFunctional`) reads or writes the current value
of memory at once, with no timing, coherence, LRU or stats side effects.
Reads are safe while timing traffic is in flight. Writes are safe too,
**except with masked writes** (SVE/SME predicated stores): the classic
cache path has two gaps there. Our perfect-structure limit studies all
rest on functional access (`--perfect-l1i`, `--perfect-tlb`,
[[2026-11-06-perfect-l1d]]). The analysis is from reading the code
(2026-11-06), not from a failing run.

## The three access modes

| mode | call | behaviour | used for |
|---|---|---|---|
| timing | `sendTimingReq` / `recvTimingResp` | event by event; can be refused (retry); changes coherence, LRU, MSHRs, stats | detailed simulation (O3) |
| atomic | `sendAtomic` | one call, returns an estimated latency; changes cache state | fast-forward, warm-up |
| functional | `sendFunctional` | the current value, now; no state change | loaders, gdb, syscall emulation, our perfect-structure switches |

## Why functional access must search everywhere

While timing traffic is in flight, the newest value of a byte can be in
any of these places:

- a dirty L1 block;
- an MSHR target (a store that missed and waits for its fill);
- the write buffer (a writeback or an uncacheable write);
- a port queue (a fill response on its way up);
- the same places one level down;
- another cache (L1I, IO cache), reached through crossbar snoops;
- memory.

`BaseCache::functionalAccess` checks the block, then the cpu-side port
queue, the MSHRs, the write buffer and the mem-side queue.
`CoherentXBar::recvFunctional` forwards the access to every snooper and
checks its own queued ports.

- **A read** collects bytes as it goes (`bytesValid`). It stops when a
  dirty owner or a queued packet covers it. It searches from the CPU
  outwards, so the first copy it meets is the newest.
- **A write** must update every copy. `Packet::trySatisfyFunctional`
  never reports a write as done, so it always reaches memory. On the way
  it **patches queued packets**: a queued timed write is a future
  overwrite, and if it were not patched it would land later and undo the
  functional write.
- **DRAM write queue:** `MemCtrl` applies a timed write to the backing
  store when it accepts it, not when it services it. So a queued DRAM
  write never overwrites a later functional write.
- **Coherence state is not changed.** That is harmless after a write,
  because memory holds the value too. A later writeback of a dirty line
  carries the patched data.

## Masked writes

An SVE contiguous predicated store (`ST1*`; `wren_code` in
`src/arch/arm/isa/templates/sve_mem.isa`) or an SME store is issued as
**one** packet as wide as the vector, plus a per-byte enable vector. A
`false` entry means "leave this byte alone". `Packet::isMaskedWrite` is a
`WriteReq` whose request has a `false` entry. Scalar and NEON stores pass
no mask. SVE scatter stores issue one access per element with an all-true
mask.

**The timing path honours the mask everywhere it applies a write**
(`Packet::writeData` / `writeDataToBlock`): a cache hit, MSHR targets after
the fill, memory. The functional path does not, in two places:

1. **The functional write is itself masked.** When it patches a cache
   block or a queued packet, `trySatisfyFunctional` `memcpy`s the whole
   overlap and ignores its own mask. The meaningless bytes of inactive
   lanes overwrite valid cached data. Memory is right (`writeData`), so
   caches and memory disagree, silently: `getConstPtr` has no
   masked-write assert.
2. **The functional write meets a queued masked write.**
   `trySatisfyFunctional(PacketPtr other)` `warn`s ("Trying to check
   against a masked write, skipping") and does not patch it. When the
   queued write lands later, its older bytes overwrite the newer ones.
   The same skip affects functional reads: they can miss newer data held
   in a queued masked write.

Where a timed masked write can be queued: L1D MSHR targets (a store miss;
the main case), the L1D write buffer and its mem-side queue (uncacheable
stores). Crossbars pass requests straight through; their queues hold
responses only.

**When the second gap gives a wrong value.** It takes a timed masked store
that is older than a functional store to the same bytes and is still in
flight. Arm runs with `needsTSO` off, so the store queue does not wait for
older stores to complete (`LSQUnit::writebackStores`).

1. An older masked store goes timed, misses, and waits in an MSHR.
2. A younger store goes functional. It updates the L2 and memory, but the
   MSHR target is skipped.
3. The fill arrives and the waiting target is applied. The older bytes
   win, and the younger store is lost.

**Why upstream never hit either gap.** Functional writes come from
loaders and debuggers, which never send masked writes. They also almost
never run while an SVE store to the same bytes is in flight.

**Fixes.**

- **Gap 1 (fixed in our tree, 2026-11-06):** the write branch of
  `Packet::trySatisfyFunctional` now copies only the enabled bytes, as
  `writeData` does. Not yet exercised by a run (no masked write reached it
  on the agentic restores).
- **Gap 2, writes:** copy the bytes into the queued packet's buffer. Its
  own mask keeps the result right. The buffer must be reached without
  `getPtr`, which asserts `!isMaskedWrite()`.
- **Gap 2, reads:** harder, because `bytesValid` would have to respect the
  queued packet's mask.

**In our runs:** the agentic restores remove `FEAT_SVE*` and `FEAT_SME`
(`virt_run.py --release kvm-host`), so no masked write exists there.
Whether SPEC (`fs_run.py`, `ArmDefaultRelease.for_kvm()`) emits SVE
stores is not checked.

## Related

- Functional accesses do not apply atomic operations: a functional
  `SwapReq` is treated as a plain read by `trySatisfyFunctional` and
  `AbstractMemory::functionalAccess`. The perfect L1D does read, functor,
  write itself ([[2026-11-06-perfect-l1d]]).
- Store-exclusives and atomics in the O3 are non-speculative:
  `insertNonSpec` in `IEW`; commit asserts that a store-exclusive has
  completed. So no younger store is written back while one of them is in
  flight.
- Arm's exclusive monitor has a CPU-side part (`MISCREG_LOCKFLAG` /
  `LOCKADDR`; `lockedWriteHandler` in `src/arch/arm/isa.cc` fails a
  store-exclusive before it is sent). It also has a cache-side part
  (`CacheBlk::checkWrite`, which sets `req->setExtraData`).
- A store-exclusive that misses in a classic cache always fails
  (`BaseCache::access`, "complete miss on store conditional").
- Filling a cache line functionally bypasses the crossbar snoop filters
  (`L2XBar`, `SystemXBar`). Evicting that line later panics in
  `SnoopFilter` ("requestor ... is not a holder"), and DMA snoops never
  reach the line. See [[2026-11-06-perfect-l1d]].
- [[memory-system]], [[simulation-core]], [[functional-translation-perturbs]]
  (functional *translation* is not side-effect free).
