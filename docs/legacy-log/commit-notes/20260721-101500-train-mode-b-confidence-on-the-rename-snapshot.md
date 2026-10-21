# cpu-o3: Train mode-B confidence on the rename snapshot

- **Date:** 2026-07-21 10:15   ·   **Branch:** rbdev

## Goal
Mode-B (value) MRN was a net loss because its confidence counter was trained
on a signal that is ~1/3 noise. `predict()` reads the value file at rename;
`commitLoad()` trained by comparing the value file AS OF COMMIT -- by which
point the producing store has refreshed the slot. For a changing store->load
recurrence the training therefore reports a spurious match every iteration and
saturates confidence on exactly the loads the forward gets wrong. Measured
(shadow probe, 50M): 43% of gcc commit-time "matches" had a wrong rename
snapshot; 23% on sqlite.

## Summary of changes
Train confidence against the value the prediction actually used at rename, not
the commit-time value file. Every predictor-eligible integer load snapshots
its bound-slot value at rename (new `MrnTables::peek`, confidence-independent,
same hardware read predict() already does) and carries it to commit;
`commitLoad` trains on `snap_value == realValue`. A just-bound or rebinding
occurrence has no rename-time prediction, so it is left as bound rather than
rewarded or punished.

Behind `trainOnRenameSnapshot` (default True) with `--mrn-train-commit-value`
to restore the old comparison for A/B. The control arm reproduces the
committed alias-gate build exactly (gcc mispredicts 313,898).

A/B at 10M warmup / 50M detailed vs the no-MRN baseline:

  721.gcc_r.2.0     0.9459 -> 1.0064   (net loss -> net GAIN)
  708.sqlite_r.2.2  0.9385 -> 0.9999   (net loss -> break-even)

Mispredicts fell 95% / 91% (gcc 313,898 -> 15,426), squashed insts 95% / 92%
(gcc 33.8M -> 1.75M), verified accuracy 72->98% / 93->99%. Coverage dropped
modestly (gcc 5.78->4.37%) as the mispredicting recurrences stopped
forwarding. First time in the investigation MRN is not a net loss.

Two new unit tests pin the behaviour at the core level: the same changing
recurrence stays unconfident under snapshot training and builds false
confidence under the legacy comparison.

Hardware-cost note (docs/garfield/mrn-ideas.md, deferred): the model carries a
64-bit snapshot per eligible load; real hardware would carry a ~4-bit
value-file generation counter instead (bump-on-change), which is logically
equivalent and needs no value in the pipeline. Training is commit-time with no
timing effect, so this does not affect the IPC results either way.

## Files changed
- `src/cpu/o3/mem_rename_predictor.hh` — `peek()`; `commitLoad` gains train_on_snapshot/snap_valid/snap_value; `_trainOnSnapshot` member + `trainOnSnapshot()`; wrapper plumbing.
- `src/cpu/o3/mem_rename_predictor.cc` — const `loadFind` + `peek`; `commitLoad` trains on the snapshot when stable, else leaves confidence as bound.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — initialize `_trainOnSnapshot` from the new param.
- `src/cpu/o3/MemRenamePredictor.py` — `trainOnRenameSnapshot` param (default True), documented.
- `src/cpu/o3/rename.cc` — capture the confidence-independent peek snapshot into the DynInst for every eligible integer load.
- `src/cpu/o3/commit.cc` — pass the snapshot to `commitLoad`.
- `src/cpu/o3/dyn_inst.hh` — `MrnSnapValid` flag + `_mrnSnapValue` carrying the rename snapshot to commit.
- `src/cpu/o3/mem_rename_predictor.test.cc` — rework tests for the snapshot contract (peek-then-commit helper); add two ChangingRecurrence tests contrasting snapshot vs legacy training.
- `configs/garfield/arm/sim_opts.py` — `--mrn-train-commit-value` to restore the old behaviour.
- `docs/garfield/mrn-ideas.md` — new MRN idea doc: 1a (this, validated), 1b (independent gates, deferred), the generation-counter hardware follow-up, value-file invalidation, and resolved/refuted findings.
