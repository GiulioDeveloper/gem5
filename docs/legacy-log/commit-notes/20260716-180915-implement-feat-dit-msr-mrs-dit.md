# arch-arm: Implement FEAT_DIT (MSR/MRS DIT)

- **Date:** 2026-07-16 18:09   ·   **Branch:** rbdev

## Goal
Let the simulated ARM CPU execute `MSR/MRS DIT` (PSTATE.DIT, FEAT_DIT).
Needed for FS+KVM checkpointing: the KVM host (Neoverse-V1) implements
FEAT_DIT, so the guest kernel patches `MSR DIT` into its exception-entry
path; the simulated CPU previously hit that as an Undefined Instruction on
restore, derailing kernel entry before it set SP_EL0=current and causing an
infinite PAN Data-Abort storm (all SPEC FS+KVM checkpoints captured kernel
idle, not the benchmark). See docs/gem5-kvm-feature-mismatch.md in the
workloadzoo repo for the full write-up.

## Summary of changes
Add FEAT_DIT as a functional no-op timing bit, mirroring PAN/UAO. The
`CPSR.dit` bit (bit 24) and `ID_AA64PFR0.dit` field already existed; this
wires the decode, the misc-reg, and the ID advertisement. DIT is
EL0-accessible (allPrivileges, like NZCV), unlike PAN/UAO.

## Files changed
- `src/arch/arm/regs/misc.hh` — add `MISCREG_DIT` enum entry + `"dit"` in miscRegName[].
- `src/arch/arm/regs/misc.cc` — `InitReg(MISCREG_DIT).allPrivileges()`; sysreg map row S3_3_C4_C2_5; advertise `ID_AA64PFR0_EL1.dit=1`.
- `src/arch/arm/insts/misc64.cc` — MSR-immediate `MISCREG_DIT` -> (imm&1)<<24 in miscRegImm().
- `src/arch/arm/isa/formats/aarch64.isa` — decode MSR DIT immediate (op1=3/op2=2) to MsrImm64.
- `src/arch/arm/isa.cc` — read/write PSTATE.DIT (bit 24) via MISCREG_DIT aliasing CPSR.
