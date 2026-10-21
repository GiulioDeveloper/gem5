# cpu-o3: Add MRN squash-reason counters

- **Date:** 2026-07-20 11:35   ·   **Branch:** rbdev

## Goal
MRN's resolution counters did not close. On 721.gcc_r.2.0 (50M detailed,
mode C), 30.6% of predictions resolved to nothing: predictionsMade /
forwardsValue / forwardsAlias increment at *rename*, but predictionsCorrect /
mispredicts only increment inside LSQUnit::writeback(), so a forwarded load
squashed before it completes its access was counted as made and never
resolved. That silently understated accuracy (correct/made gives 80.6% mean
across the 190-checkpoint sweep where correct/(correct+mispredicts) gives
91.6%) and hid a real cost: those forwards consumed rename bandwidth and
physregs before being discarded.

## Summary of changes
Every MRN prediction now resolves exactly once — correct, mispredict, or
squashed-with-a-reason — so both per-path identities close:

    forwardsValue == predictionsCorrect + mispredicts      + squashedValue::total
    forwardsAlias == aliasVerifyCorrect + aliasMispredicts + squashedAlias::total

Five reasons (Branch, MemOrder, MrnValue, MrnAlias, Other). The reason cannot
be recovered at the squash site — IEW::squashDueToMemOrder is shared by real
memory-order violations and both MRN mispredict paths — so it is plumbed from
the initiator through IEWStruct to Commit to the ROB. Traps, interrupts,
ReExec, HTM, TC writes, drain and squash-after collapse into Other; they
measure 0.0% on every checkpoint tested.

Two counting sites are required, not one. ROB::doSquash() covers instructions
in the ROB; CPU::squashInstIt() covers instructions renamed but never
inserted into the ROB. Commit::getInsts() looks like the natural home for the
second but is dead code for it — Commit::commit() skips getInsts() entirely
while squashing, which is exactly when those instructions are dropped.

The new MrnResolved bit, not the instruction's squashed status, is what makes
this exactly-once. Gating on isSquashed() fails in both directions: squash()
resets squashIt to the tail so overlapping squashes re-walk entries, and a
multi-cycle squash lets LSQUnit::squash pre-mark the whole load-queue range.

Validated on five checkpoints spanning the coverage range (sqlite 19%,
cpython 0.9%, omnetpp 0.04%, lbm 0%, gcc 5.8%): both identities close at
exactly +0 on every one. On 721.gcc_r.2.0 the new counters reproduce the
previously-unexplained population exactly — 478,212 value and 18,098 alias,
matching the numbers derived by subtraction from the pre-change stats.txt. A
baseline (no-MRN) run registers no MRN stats at all.

First result: MRN mispredicts, not branch mispredicts, are the dominant
destroyer of in-flight MRN predictions. On gcc, mrnValue + mrnAlias account
for 87.2% of squashed value-path forwards against 11.6% for branch.

## Files changed
- `src/cpu/o3/mrn_squash_reason.hh` — new standalone header: the MrnSquashReason enum and its stat-subname table, kept free of other O3 includes so rob/iew/comm can all include it.
- `src/cpu/o3/dyn_inst.hh` — add the MrnResolved flag and its accessors beside Mrned/isMrned().
- `src/cpu/o3/lsq_unit.cc` — set MrnResolved on all four resolution arms (both correct and both mispredict, the latter because squashDueToMemOrder is inclusive); pass the reason at the two MRN squash sites.
- `src/cpu/o3/iew.hh`, `src/cpu/o3/iew.cc` — squashDueToMemOrder() takes an MrnSquashReason; squashDueToBranch records Branch; both write it to the time buffer.
- `src/cpu/o3/comm.hh` — carry mrnSquashReason[] in IEWStruct alongside squashedSeqNum.
- `src/cpu/o3/commit.cc` — record the reason on the ROB before each of the two rob->squash() calls (squashAll -> Other, IEW-driven -> the time-buffer value).
- `src/cpu/o3/rob.hh`, `src/cpu/o3/rob.cc` — store the reason; count squashed unresolved MRN loads in doSquash().
- `src/cpu/o3/cpu.hh`, `src/cpu/o3/cpu.cc` — expose getMemRenamePred() publicly (iew is protected); count in squashInstIt() the loads that never reached the ROB.
- `src/cpu/o3/mem_rename_predictor.hh`, `src/cpu/o3/mem_rename_predictor_sim.cc` — noteSquashedPrediction() plus the two statistics::Vector stats with per-reason subnames and totals.
- `docs/superpowers/specs/2026-07-20-mrn-squash-counters-design.md` — design spec, including the validation findings and the two rejected counting-site alternatives.
