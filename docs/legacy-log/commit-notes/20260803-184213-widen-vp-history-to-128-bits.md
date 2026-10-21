# cpu-o3,configs: Widen VP history to 128 bits

- **Date:** 2026-08-04 19:10   ·   **Branch:** vp

## Goal
Enable the history-length study (VTAGE report Next Step 2: the
provider-correct distribution is flat out to L=64 with an 11% share
at the longest component -- the truncated-series signature).

## Summary of changes
VpHistSnapshot's GHR becomes a two-word 128-bit pair (bit 0 newest;
word-crossing shift); the fold reads bits through a histBit helper;
history lengths validated to 128; the token tag field widened to a
fixed 20 bits (rank-7 tags reach 19) with a geometry assert. New CLI
--vtage-hist-lengths (comma list, strictly increasing, numTagged
derived) for series variants without new params. Three new GTests
(word-boundary shift, long-history fold window at L=100, rank-7
token round-trip); suite 32/32. Hard gates passed: GoldenTokens
UNCHANGED (bit semantics for L <= 64 proven identical) and a full
721.gcc_r.0.3 checkpoint rerun byte-identical to the committed
Stage-IV sweep stats (all 65 valuePred lines md5-equal, IPC
identical). Study driver + probe set documented in
runs/vp_hist_study/ (gitignored).

## Files changed
- `src/cpu/o3/vp/vp_history.hh` — 128-bit snapshot pair.
- `src/cpu/o3/vp/vtage_tables.{hh,cc}` — histBit fold, 128 bound,
  20-bit token tag field + assert.
- `src/cpu/o3/vp/vtage_tables.test.cc` — three new pins + mechanical
  struct updates.
- `src/cpu/o3/vp/ValuePredictor.py`, `configs/garfield/arm/
  sim_opts.py` — --vtage-hist-lengths plumbing + validation.
