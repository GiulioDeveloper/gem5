# cpu-o3,configs: Add flush-weighted ledger to the stability gate

- **Date:** 2026-07-28 01:09   ·   **Branch:** rbdev

## Goal
Test whether penalizing wrong last-value forwards in proportion to their
measured squash cost separates schedule-critical bindings (sqlite.2.1) from
address-churners (the >1% losers). This is the strongest form of cost-side
criticality: the exact realized flush, per binding, replaces the gate's
count-based earning test.

## Summary of changes
The stability gate's sparing decision becomes a cost-benefit ledger behind
`lvFlushLedger` (default OFF; `--mrn-lv-flush-ledger`): a binding is spared
from the two-strike disable while lvCorrects x lvBenefitPerCorrect
(`--mrn-lv-benefit-per-correct`, the one free parameter b) covers the
accumulated flush cost of its address-changed wrongs (per-instance clamp
511; 32-bit saturating lvFlushCost on the SlcEntry). trainVerify gains a
`flushed` argument fed by the verify sites' already-computed squash count.
New stat lvEarningSpared counts strikes held by the earning/ledger test.
20/20 unit tests (3 new: ledger spares cheap-wrong earner, disables
expensive wrongs with clamping, off-mode reproduces count behavior);
default-off bit-identity on 750.sealcrypto_r.0.2 (3,566 shared stats).

**Result: NEGATIVE, with a measured root cause** (b swept over 128x on 14
checkpoints, runs/mrn_ledger_sweep). The b axis only interpolates between
the count-gate and no-gate endpoints: b <= 0.5 reproduces the count-gate
(losers +0.77%, sqlite.2.1 -10.6%); b >= 8 restores sqlite exactly but
un-rescues every loser. Root cause: sqlite's schedule-critical bindings
earn only ~7-13 corrects per cheap (53-inst) wrong while vpr.0.2's junk
churners earn up to ~450 per equally-cheap wrong -- the populations are
inverted on the cost-benefit plane, so no uniform benefit credit can order
them. Bonus hazard: at isolated b values (1 and 8) a marginal binding
duty-cycles across the spare/strike boundary and re-triggers StoreSet
poisoning on vpr.2.0 (conflictingLoads x6.5, IPC -18.6%). Cost-side
criticality is closed; the separating signal must be benefit-side.

Known wrinkle for future gate work (pre-existing, unfixed to keep the code
identical to what was measured): slcAllocate does not clear the gate/ledger
fields, so a recycled SLC entry inherits the evicted PC's history.

## Files changed
- `src/cpu/o3/mem_rename_valuefile.hh` — lvFlushLedger/lvBenefitPerCorrect
  config, SlcEntry::lvFlushCost, trainVerify flushed param, lastStrikeSpared.
- `src/cpu/o3/mem_rename_valuefile.cc` — ledger debit (clamp 511, sat-32)
  and the cost-denominated earning test.
- `src/cpu/o3/mem_rename_predictor.hh` — vfTrainVerify pass-through,
  lvEarningSpared stat.
- `src/cpu/o3/mem_rename_predictor_sim.cc` — params into MrnVfConfig,
  ADD_STAT.
- `src/cpu/o3/MemRenamePredictor.py` — lvFlushLedger, lvBenefitPerCorrect.
- `configs/garfield/arm/sim_opts.py` — --mrn-lv-flush-ledger,
  --mrn-lv-benefit-per-correct.
- `src/cpu/o3/mem_rename_valuefile.test.cc` — three ledger tests.
- `src/cpu/o3/lsq_unit.cc` — pass the measured squash into vfTrainVerify at
  the value-wrong verify site.
