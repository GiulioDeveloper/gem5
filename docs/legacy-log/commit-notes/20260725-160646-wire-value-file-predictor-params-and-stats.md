# cpu-o3,configs: Wire value-file predictor params and stats

- **Date:** 2026-07-25 16:06   ·   **Branch:** rbdev

## Goal
Task 2 of the value-file rendezvous predictor build-out: wire Task 1's
params-free `MrnValueFileTables` core (`src/cpu/o3/mem_rename_valuefile.
{hh,cc}`) into the `MemRenamePredictor` SimObject, per
`.superpowers/sdd/task-2-brief.md`. Adds the `value_file` correlation
enum value and its params, a `vfTables` member with stat-counting
wrapper methods, and the garfield CLI plumbing to select it. No
rename/LSQ call sites are added here -- Tasks 3-4 call the wrapper
methods by the exact names fixed in the brief.

## Summary of changes
`MemRenamePredictor.py`: `MrnCorrelation.vals` gains `"value_file"`
with an updated enum comment describing the rendezvous model. Added
`vfEntries`, `slcEntries`, `slcAssoc`, `scEntries`, `scAssoc`,
`scGranularityBytes`, `vfForwardProducerValue`, `vfForwardLastValue`
params with the brief's exact defaults and descriptive help text.

`mem_rename_predictor.hh`/`mem_rename_predictor_sim.cc`: added a
`vfTables` (`MrnValueFileTables`) member built from a `MrnVfConfig`
brace-initialized positionally from the new params (field order
matches Task 1's struct), plus `_useValueFile`, `_vfForwardProducerValue`,
`_vfForwardLastValue`. Added the `VfMode` enum
(`VfModeAlias`/`VfModeProducerValue`/`VfModeLastValue`/`VfModeCount`)
and the accessors/wrapper methods from the brief's interface list
(`valueFileEnabled`, `vfForwardProducerValue`, `vfForwardLastValue`,
`vfStoreRename`, `vfLoadRename`, `vfStoreAddrResolved`,
`vfLoadAddrResolved`, `vfLoadDataResolved`, `vfTrainVerify`,
`vfNotePredictMade`, `vfNotePredictOutcome`, `vfNotePredictSquashed`,
`vfNoteBelowConf`, `vfNoteShadow`, `vfNoteShadowSkipped`). Each wrapper
bumps its stat then delegates to `vfTables`, following the existing
style at `mem_rename_predictor.hh:203-243`.

`vfLoadAddrResolved` classifies the returned `MrnVfProbeResult`: a
`SameBinding` or `Rebound` outcome counts as an SC probe hit
(`Rebound` also counts `vfRebinds`); a `SelfBound` or
`AlreadySelfBound` outcome counts as a miss (`SelfBound` also counts
`vfSelfBinds`); `scHitDeadChannel` is counted separately as a
diagnostic overlay on top of the hit/miss split, matching the "treated
as a miss" note in Task 1's header comment. `vfLoadRename` does not
count below-confidence suppression itself -- `vfNoteBelowConf()` is a
standalone method for the caller (Task 3) to invoke once it inspects
the returned `bound`/`confident` fields, per the brief's explicit
note.

Added the four `statistics::Vector` stats (`vfPredictMade/Correct/
Wrong/Squashed`, `.init(VfModeCount)`, subnames `{"alias",
"producerValue", "lastValue"}`, `flags(statistics::total)`) and all 13
scalars from the brief's list, each with a descriptive ADD_STAT help
string following the file's existing pattern.

`sim_opts.py`: `--mrn-correlation` gains the `"value-file"` choice;
added `--mrn-vf-no-producer-value` / `--mrn-vf-no-last-value`
(`store_true`, mirroring the existing `--mrn-no-value-forward`
polarity) and wired them into `make_mrn()`. `_mrn_banner()` now always
appends `correlation=<...>` and the two knob states so a run's log
banner shows which correlation source and value-file forwarding modes
are active.

`SConscript`: the header now transitively includes
`cpu/o3/mem_rename_valuefile.hh` (for `PhysRegIdPtr` in the wrapper
signatures), so `mem_rename_predictor.test` needed the same extra
link-time sources `mem_rename_valuefile.test` already required
(`mem_rename_valuefile.cc`, `reg_class.cc`, `sim/bufval.cc`) --
`base/debug.cc` was left out since the `with_tag('gem5 trace')` tag on
this target already supplies it (adding it too caused a duplicate-
definition link error).

## Verification
- `scons build/ARM/gem5.opt` links cleanly (also discharges Task 1's
  pending full-link check).
- `mem_rename_valuefile.test.opt`: 13/13 pass.
- `mem_rename_predictor.test.opt`: 7/7 pass (unaffected -- it only
  exercises the pre-existing params-free `MrnTables` core).
- `se_run.py --use-mrn --mrn-correlation value-file --max-insts
  100000`: runs to completion; banner reads `mrn : on (value)
  correlation=value-file vfProducerValue=True vfLastValue=True`; all
  new `vf*` stats appear in `stats.txt` (zero, as expected -- no call
  sites wired yet).

## Files changed
- `src/cpu/o3/MemRenamePredictor.py` -- `value_file` enum value + new params.
- `src/cpu/o3/mem_rename_predictor.hh` -- `vfTables` member, `VfMode` enum, wrapper methods, new stats.
- `src/cpu/o3/mem_rename_predictor_sim.cc` -- ctor param wiring, ADD_STATs, vector init/subnames.
- `src/cpu/o3/SConscript` -- extra link sources for `mem_rename_predictor.test`.
- `configs/garfield/arm/sim_opts.py` -- `--mrn-correlation value-file`, the two `--mrn-vf-*` flags, `make_mrn`, `_mrn_banner`.
