# cpu-o3: Add params-free E-VTAGE core tables

- **Date:** 2026-08-05 03:40   ·   **Branch:** vp

## Goal
EVES Stage-1 Task 1: the E-VTAGE policy core in isolation -- the
per-class probabilistic confidence/allocation machinery that
Seznec's ablation identifies as the predictor's essence.

## Summary of changes
EVtageTables (fork of VtageTables; originals byte-identical):
classifier-driven confidence gate (verbatim K32 exponent with the
load bracket collapse and base-provider trial doubling), the exact
punish arms (c==7 -> {5, u=1}; else {0, u=0}) split across
verify-site correctivePunish and commit train via punishApplied/
medConfPending entry bits with the pinned delivered-wrong endpoint,
unconditional value overwrite on wrong trains, the K32 allocation
gate (outer operand gate, E' body with multiplied-LOWVAL bracket,
MedConf deterministic body) with both landing arms, UPDATEU
exploration credit + deterministic u++ at saturation, 2-bit u, TICK
(NA - 5*ALL), tagged 2-way skewed base with legal no-provider
lookups, burst-guard window predicate, injectable RNG throughout.
Review round (source-fidelity + mutation lenses, 11 findings): fixed
a critical allocation-landing off-by-one from a misreading of CVP's
bank layout (banks 0 AND 1 are the skewed base's two ways; the first
tagged table is our VT1) that had left VT1 as dead storage with the
test fixtures pinning the bug -- the spec's DEP = r+1 rule was
correct throughout; plus six mutation-survivor pins (E'-vs-E
discrimination, exact-saturation trigger, u=1 assignment, TICK
coefficient, skew distinctness, E_u truth table), a maskFires doc
fix, and a well-defined lowVal replacing signed-overflow UB. 54
GTests, every targeted mutant re-injected and confirmed killed.

## Files changed
- `src/cpu/o3/vp/evtage_tables.{hh,cc}` — the core.
- `src/cpu/o3/vp/evtage_tables.test.cc` — 54 GTests.
- `src/cpu/o3/vp/SConscript` — Source + GTest registration.
