# doc: MRN value-file rendezvous predictor design spec

- **Date:** 2026-07-25 12:10   ·   **Branch:** rbdev

## Goal
Design a replacement for the alias path's binding + store-instance-finding
mechanism, modeled on Tyson & Austin memory renaming (MICRO-30 1997; table
structure per Reinman et al., ICS 1999 §2.3): Store/Load Cache + Value File +
Store Cache + verify-trained confidence. Motivated by measurements: the
last-writer-wins correlator is 58.6% accurate, only 0.28% of predictions
become enforced aliases, and the store-queue instance hunt structurally
returns a prior iteration's store.

## Summary of changes
New spec docs/superpowers/specs/2026-07-25-mrn-valuefile-rendezvous-design.md.
Key decisions: store deposits its data physreg into a per-static-store Value
File cell at RENAME (in-order -> deposit always the correct instance; nothing
at decode); load reads the cell at rename; Store Cache learns addr->cell
bindings at address resolution with a program-order overwrite guard; loads
rebind on probe mismatch, self-bind + last-value on probe miss (covers
constant loads); generation tags on VF cells detect dangling SLC/SC
references after LRU reallocation; consumption = alias if producer not ready,
value-forward if ready or last-value; confidence in the load's SLC entry,
shadow-verified below threshold; no table rollback on squash. Dependence
distance 1 is the explicit design point. Experiments: gcc checkpoint first,
then mrncomm/mrnrec microbenchmarks, then the 190-checkpoint sweep.

## Files changed
- `docs/superpowers/specs/2026-07-25-mrn-valuefile-rendezvous-design.md` — the design spec (structures, five dataflow events, consumption/verify/confidence, code organization, test plan, success criteria).
