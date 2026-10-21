# doc: Add the E-Stride (EVES Stage 2) design spec

- **Date:** 2026-08-14 23:55   ·   **Branch:** vp

## Goal
Specify the port of CVP-1 EVES's Enhanced Stride predictor and the
EVES composition (E-Stride + the shipped E-VTAGE) before
implementation. The spec is source-verbatim against the contest code
(cvp8KB/mypredictor.cc), with every deviation declared, after a
paper-vs-code verification pass found the paper's prose wrong in
several places (arbitration mechanism, two confidence fractions).

## Summary of changes
New spec: params-free EStrideTable core (verbatim 48-entry geometry,
probabilistic confidence/allocation, 0xffff sentinel demotion, global
SafeStride owned by the table); a framework per-PC in-flight
occurrence counter (exact, replacing CVP's ring scan; rename ++ /
commit-train -- / squash-walk -- with a DynInst flag for exactly-once
closure); a new EvesVP SimObject (--use-vp eves) with source-exact
arbitration — including the source's low-confidence VTAGE value
overwrite of a confident stride prediction — behind a default-off
ablation param; verify/train routing; stats; GTest and bit-identity
gates; probe-16 -> 190 evaluation plan. Also an erratum in the
E-VTAGE spec: CVP's 128-inst blackout suppresses the whole VTAGE
contribution (value and flag), not only the flag — unobservable in
Stage 1, behavioral in the composition.

## Files changed
- `docs/superpowers/specs/2026-08-14-estride-design.md` — the new
  E-Stride + EVES composition design spec (12 sections).
- `docs/superpowers/specs/2026-08-04-evtage-design.md` — erratum note
  in the burst-guard section correcting the CVP blackout-scope
  parenthetical, pointing at the new spec's §5.
