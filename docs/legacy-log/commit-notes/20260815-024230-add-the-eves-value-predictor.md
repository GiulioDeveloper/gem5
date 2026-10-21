# cpu-o3,configs: Add the EVES value predictor (E-VTAGE + E-Stride)

- **Date:** 2026-08-15 02:42   ·   **Branch:** vp

## Goal
Task 3 of the E-Stride/EVES design: the `EvesVP` SimObject composing
the already-landed `EStrideTable` core (Task 2) and the owned
`EVtageTables` instance behind the CVP-1 write-order arbitration
(`evesArbitrate()`, eves_arbiter.hh), plus the CLI/config plumbing and
the guard-capable `usesInflightCounts()`/`notifyRenamedInst` hooks'
first real coverage.

## Summary of changes
`eves.{hh,cc}`: `EvesVP` owns an `EStrideTable` and an `EVtageTables`
(same injected-RNG idiom as `EVtageVP`/`VtageVP`), overrides
`trainsAtCommit()`/`usesHistory()`/`usesInflightCounts()` all true.
Three token flag bits (63/62/61: stridePredicted, vtageConfident,
deliveredByVtage) sit above `EVtageTables`'s own packed token; the
ctor `fatal_if`s the token geometry (`ceilLog2` recompute of the
index-field width) against a 61-bit budget. `predictImpl` runs the
stride lookup then the VTAGE lookup then `evesArbitrate()`, exactly
as the CVP-1 source's write-order mechanism (stride first, VTAGE
overwrites even below confidence in verbatim mode). `trainImpl` trains
VTAGE then E-Stride, folding stride outcomes into the EvesStats
surface (28 scalars, one vector, one histogram).
`correctiveResetImpl` routes the SafeStride penalty / lastWrongMark
reset / VTAGE corrective punish off the three flag bits per spec S6 --
a stride-supplied wrong gets no VTAGE punish and reports live (no
staleness question asked). `ValuePredictor.py` duplicates all ten
`EVtageVP` params verbatim (declared drift risk, spec S2) plus
`vtageOverwriteRequiresConfidence`; `sim_opts.py` adds the `eves`
`--use-vp` choice and `--eves-vtage-overwrite-requires-confidence`,
sharing `--evtage-burst-guard`/`-conf-threshold`/`-hist-lengths` with
the `evtage` arm (spec S2 amended in this commit to match: no separate
`--eves-burst-guard`). `evtage.{hh,cc}`'s comment-only rewording (the
rename feed exists but E-VTAGE's own guard stays locked off) was
already discharged in an earlier commit -- untouched here.

Gates: full build clean, `--help` runs; 5/5 GTest binaries green
(21+4+15+32+54); four boot smokes (vpchase, all four `--use-vp eves`
variants) rc=0, `predictionsMade > 0`, inflight closure identity
(`inflightIncrements == inflightDecTrain + inflightDecSquash`) exact
(0 diff) on all four. Directed routing smokes (branchsort/vpalu,
`--evtage-conf-threshold 1`): `deliveredWrongByVtage ==
vtageCorrectivePunishes + correctiveResetStale` and `predictionsWrong
== deliveredWrongByVtage + deliveredWrongByStride` hold exactly on
every run (both pair counters at the SAME verify site, so they never
straddle a later pipeline stage), including one crafted with
`--eves-vtage-overwrite-requires-confidence` to force real
stride-supplied wrongs (561 of them, correctly routed with zero VTAGE
punishes).

The other two closure checks are NOT verify-site-only and show two
DIFFERENT, unrelated residuals -- corrected here after an initial
mis-attribution that applied one mechanism to both:

- Inflight closure is exact (0 diff) on all four boot smokes, but
  shows a small NEGATIVE residual (-7/-7/-10, out of populations up
  to 1.3M) on the three hostile, fully-drained runs
  (eves_hostile_all/eves_hostile_all_ablation/eves_vpalu). Root-
  caused via temporary per-seqNum instrumentation (reverted, not part
  of this commit): `roi.h`'s `ROI_BEGIN()` calls `m5_reset_stats(0,0)`,
  zeroing the gem5 Stat counters (including `inflightIncrements`)
  while a handful of already-renamed, VP-eligible instructions from
  the pre-ROI setup phase are still in flight; their later
  commit/squash decrements land after the reset with no matching
  pre-reset increment left in the (now-zeroed) counter, producing a
  negative apparent residual. The underlying algorithmic state (the
  `VpInflightCounted` flag, the per-key map) is untouched by the reset
  and balances to exactly zero at true process exit (confirmed: raw,
  reset-immune counters summed to inc=245374 ==
  decTrain(227259)+decSquash(18115), zero panics on a strict
  per-instruction pairing invariant). Boot smokes show no residual
  because their pre-ROI setup has negligible VP-eligible activity to
  straddle the reset.
- `predictionsCorrect == deliveredCorrectByVtage +
  deliveredCorrectByStride` shows a DIFFERENT, POSITIVE residual --
  NOT the reset mechanism above (a reset zeros the earlier-site term
  and would produce a negative gap, the opposite sign). Even the boot
  smokes show a small nonzero gap here: eves_loads/eves_guard128
  diff=3 (of predictionsCorrect=49860); eves_all diff=467 (of 52585);
  eves_ablation diff=0 (of 98947) despite eves_ablation's own
  predictionsSquashed=34/squashedInsts=106 being no smaller than
  eves_loads's 16/106 (raw squash volume alone does not predict this
  residual -- see the precise scoping below). True cause:
  `predictionsCorrect` counts at the verify site; `deliveredCorrectBy*`
  counts at commit-train, which runs only for instructions that
  actually commit. A prediction that verifies correct and is then
  squashed by an OLDER redirect (branch/VP/memory-order mispredict) or
  whose instruction faults at commit never reaches commit-train, so it
  is counted in `predictionsCorrect` but in neither
  `deliveredCorrectByVtage` nor `deliveredCorrectByStride` -- a term
  that does not drain at exit (those instructions never commit, by
  definition). It is positive exactly when some verified-correct
  prediction is squashed or faults before commit; zero when no such
  victim occurs -- likely, but not guaranteed, at negligible squash
  pressure (a run can squash plenty of instructions without ever
  killing a verified-correct prediction, as eves_ablation's 0 diff
  above shows). This exonerates the S6 routing code: mis-routing
  would preserve the sum (move counts between the two
  `deliveredCorrectBy*` buckets), not shrink it; only never-trained
  instructions can shrink it.

Bit-identity re-gate 5/5 (`lvp`, `vtage`, `evtage`, `evtage_all`,
`mrn_vp`) IDENTICAL modulo new zero stats.

## Files changed
- `src/cpu/o3/vp/eves.hh`, `eves.cc` — the `EvesVP` SimObject: token
  flags, owned `EStrideTable`/`EVtageTables`, predict/train/corrective-
  reset routing, EvesStats surface (28 scalars + allocation-class
  vector + in-flight histogram).
- `src/cpu/o3/vp/ValuePredictor.py`, `SConscript` — `EvesVP` params
  (duplicated E-VTAGE geometry + `vtageOverwriteRequiresConfidence`)
  + build registration.
- `configs/garfield/arm/sim_opts.py` — `eves` `--use-vp` choice,
  `--eves-vtage-overwrite-requires-confidence`, the `make_vp` arm.
- `docs/superpowers/specs/2026-08-14-estride-design.md` — S2 amended:
  the shared `--evtage-burst-guard` replaces the planned separate
  `--eves-burst-guard` flag.
