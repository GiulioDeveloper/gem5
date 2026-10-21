# cpu-o3,configs: Default EVES to the confidence-gated overwrite

- **Date:** 2026-08-15 12:50   ·   **Branch:** vp

## Goal
Ship the 190-checkpoint A/B winner as the EvesVP default: gating the
E-VTAGE value overwrite on VTAGE confidence beats the CVP-1
source-verbatim write-order overwrite by +3.6% geomean (1.0165 vs
0.9812 vs base; composition report). User-ratified amendment to the
spec's arbitration fork.

## Summary of changes
vtageOverwriteRequiresConfidence now defaults True. The CLI ablation
switch inverts accordingly: --eves-vtage-overwrite-verbatim opts back
into the source's overwrite (the old
--eves-vtage-overwrite-requires-confidence switch is gone; it was
introduced this campaign and never shipped beyond it). The
EvesArbiterIn POD default flips to match. Verified by determinism:
vpstride under the new default reproduces the old confidence-gated
run bit-for-bit, and under the new verbatim flag reproduces the old
default run bit-for-bit (0 differing stats keys both ways); 21/21
E-Stride GTests green. Spec S2/S12 amended (dated); the report's
next-step 1 marked resolved.

## Files changed
- `src/cpu/o3/vp/ValuePredictor.py` — EvesVP param default True, help
  rewritten.
- `configs/garfield/arm/sim_opts.py` — flag replaced by
  --eves-vtage-overwrite-verbatim; factory forwards its negation.
- `src/cpu/o3/vp/eves_arbiter.hh` — POD default true; doc comment
  updated with the A/B outcome and report pointer.
- `docs/superpowers/specs/2026-08-14-estride-design.md` — dated
  amendments in S2 (param + CLI) and S12 (fork list).
- `docs/research-log/VP/2026-08-15-eves-estride-composition.md` —
  next-step 1 marked resolved.
