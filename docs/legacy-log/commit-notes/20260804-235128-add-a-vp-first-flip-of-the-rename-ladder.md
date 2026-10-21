# cpu-o3,configs: Add a VP-first flip of the rename ladder

- **Date:** 2026-08-05 00:30   ·   **Branch:** vp

## Goal
The committed-optimized experiments showed 88.2% of MRN's take is
VP-coverable and the MRN-first stack is slightly slower than VTAGE
alone. Flip the rename consumption ladder so the (more accurate,
broader) value predictor claims first and MRN value-forwarding only
takes loads VP left unclaimed.

## Summary of changes
New BaseO3CPU bool param vpBeforeMrn (default False = existing
MRN-first order). Rename's two consumption blocks are restructured
around one consume_value_pred lambda: flipped order runs VP before
the MRN value-forward consumption, which is now additionally gated
on !vpPredicted (inert in default order: the flag cannot be set
there yet). The MRN producer-alias path cannot follow the flip (it
diverts the destination map before the VP decision exists);
sim_opts rejects --vp-before-mrn with --mrn-alias. CLI:
--vp-before-mrn. Gates: default-order stats value-identical to the
pre-change mrn_vtage_all run on 707.ntest_r.0.3; flipped smoke on
the same checkpoint moves the contested loads to VP (MRN take
1.86M -> 0.47M, VP 9.21M -> 10.60M, total optimized unchanged,
IPC +0.4%).

## Files changed
- `src/cpu/o3/BaseO3CPU.py` — vpBeforeMrn param.
- `src/cpu/o3/rename.hh` — the member.
- `src/cpu/o3/rename.cc` — ladder restructure around
  consume_value_pred.
- `configs/garfield/arm/sim_opts.py` — --vp-before-mrn + the alias
  incompatibility check.
