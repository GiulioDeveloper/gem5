# cpu-o3: Add Garfield Stage 2C memory renaming mode C (producer aliasing)

- **Date:** 2026-06-30 16:37   ·   **Branch:** stage2c-producer-alias (merged to rbdev)

## Goal

Stage 2C of the Garfield plan (see `docs/garfield/README.md`): extend the merged MRN mode B
(value snapshot) into a **unified predictor where C ⊇ B**. At a confident integer load's rename,
**alias** its consumers to the in-flight producing store's data physical register (mode C); when no
in-flight producer exists, fall back to the mode-B **value snapshot**. The gem5-native realization
of Tyson & Austin's "reservation-station index when in-flight, value when retired." Load is
**always executed and verified**; recovery is **full squash**. Gated by `--mrn-mode unified`,
**off / value-only stay byte-identical to baseline**.

## Commits in this feature (on stage2c-producer-alias → rbdev)

1. `cpu-o3: Add physreg refcount for MRN producer aliasing` (`4fc0e8db7a`) — `refCount` on PhysRegId
   (mirrors `numPinnedWrites`); `getReg` sets 1; the two runtime free sites (`removeFromHistory`,
   `freeingInProgress` squash drain) release only at 0. Non-aliased regs go 1→0 ⇒ byte-identical.
2. `cpu-o3,configs: Add MRN mode C (producer aliasing)` (`81f1383f97`) — unified predictor +
   correlator + rename-map aliasing + deferred verify + B/C stats + knobs.

## How it works

- **Correlator (C.1, default `mrnCorrelation=lsq_forward`):** learns `loadPC→storePC` from the LSQ
  store→load forward event (`LSQUnit::read`). `store_set` is a stub. `LSQ::findYoungestStoreByPC`
  confirms an in-flight producer exists.
- **Rename alias (`renameDestRegs`):** the producer physreg is the **current rename-map mapping of
  the producing store's data register** — *not* the physreg an older in-SQ store captured. This is
  the crux: the same-iteration producing store is not in the SQ yet at the load's rename, so using a
  found (older) store's captured physreg gives a stale value — correct only for stable values
  (mrncomm), wrong for a changing recurrence (mrnrec). The benchmarks are `slot=X; X=slot`
  recurrences where the store's data reg == the load's dest reg, so the alias keeps the load's
  single mapping to the producer (no refcount bump) and the load executes into a private reg for
  verification. `doSquash` skips marking the live producer ready (gated on `aliased`).
- **Verify (`lsq_unit.cc`):** at `MAX(load-resolve, producer-resolve)` — immediate for value (B),
  deferred (pending-verify list, drained at producer writeback) for alias (C). Mismatch → reset
  confidence + `squashDueToMemOrder`.

## Validation (N=2,000,000)

| Workload | off | value-only (B) | unified (C) |
|---|---|---|---|
| **mrnrec** (changing-value recurrence) | 1.00× | **0.951×** | **2.247×** (100% alias acc, 0 mispred) |
| **mrncomm** (stable store→load) | 1.00× | 2.493× | 2.493× |

- **Golden checks all pass:** mrnrec benefits from **C, not B** (the case B structurally cannot do);
  mrncomm benefits from **both**; **off byte-identical** to the pre-2C baseline (mrncomm + mrnrec);
  **checksums identical** off / value-only / unified on every workload (verify+squash keeps
  speculation architecturally invisible).
- **FP safety:** matmul/stream under unified — `forwardsAlias=0` (int-only guard) and **no panic**,
  checksums identical off vs unified.
- **Unit test:** `mem_rename_predictor.test` 5/5.

## Finding

Mode C delivers exactly what mode B cannot: on a **changing-value** store→load recurrence (mrnrec),
B mispredicts every forward (−5%), but C aliases the load to the in-flight producer register so the
dependent recurrence (the multiply) reads the producer directly and the store→load **memory
round-trip leaves the critical path** — **2.25× at 100% accuracy**. On a stable value (mrncomm) C
matches B (2.49×). Producer-register aliasing is the right tool for tight in-flight recurrences;
value snapshotting (B) remains the tool for stable, longer-distance communication.

## Out of scope (Stage 2C, deliberately)

`store_set` correlator (stub — `lsq_forward` is the default and the measured path); SP/GP and
confidence tuning sweep; vector-load aliasing (int-only by design); the latent commit-map/private-reg
dangling-window cleanup (benign on these workloads — verify+squash preserve architectural state);
Stage 3 (value prediction) and ghosting MRN-ed loads.
