# doc: Add E-VTAGE design spec (EVES stage 1)

- **Date:** 2026-08-04 22:50   ·   **Branch:** vp

## Goal
Stage 1 of the EVES adoption: E-VTAGE's update policy at fixed
storage geometry, testing Seznec's own ablation finding that the
per-class probability policy -- not the table structures -- carries
the gain (4.202 -> 3.710 IPC without it).

## Summary of changes
Design spec grounded in the actual CVP-1 submission source
(microarch.org/cvp1, Seznec.tar.gz) rather than the paper's endpoint
summary: verbatim K32 confidence-increment exponent (with the load
bracket collapse and VT0 trial-doubling), the structurally-different
allocation exponent with both landing arms (tagged scan + the
base-way arm that alone owns the zero-operand-ALU seed-to-7),
MedConf semantics with the outer operand gate scoping, the exact
punish arms (c==7 -> {5, u=1}; else {0, u=0}), unconditional value
overwrite on wrong, UPDATEU gating (exploration credit on
not-delivered-correct + deterministic u++ at saturation), TICK
(NA - 5*ALL), burst guard counting every renamed instruction
(default off), tagged 2-way skewed base. The verify/commit split of
CVP's single-site mispredict work is fully specified via punishApplied
/ medConfPending entry bits with a pinned lifecycle endpoint, and the
no-livelock bound is stated exactly (threshold >= 6: never re-armed;
<= 5: at most one extra wrong delivery). Three-lens adversarial
review -> 28 findings, all closed with source-verified
transcriptions. Declared deviations: level-classes instead of
latency thresholds, integer-non-flag operand counting, iso-geometry
(not iso-area) A/B with the tagged-base confound reporting duty.

## Files changed
- `docs/superpowers/specs/2026-08-04-evtage-design.md` — the spec
  (new).
