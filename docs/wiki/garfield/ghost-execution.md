---
type: garfield
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/README]]"
  - "[[legacy-log/commit-notes/20260628-184331-add-stage1-ghost-execution]]"
tags: [garfield, ghost, headroom, o3]
---

# Garfield Stage 1: ghost execution

**What it is:** an O3 accounting mode (`--ghost-exec`, off by default) in
which tagged uops consume **no OoO issue-queue entry, no issue bandwidth
and no execution port**, while still executing, waking dependents and
retiring in order. Stage 1 tagged all control (branch) uops; the policy
(`src/cpu/o3/ghost_policy.*`) was meant to extend to memory-renamed and
value-predicted uops. Part of [[garfield-overview]].

## Methodology ideas worth keeping

- **Gate on coverage, not eligibility.** Ghosting every *eligible* uop
  (value prediction is eligible for almost every uop) would give a
  meaningless ceiling; use what a real predictor actually predicts.
- **Assume predicted = correct** for a ceiling: then no front-end ground
  truth is needed, so the study is single-pass. gem5 O3 resolves at
  execute and ships **no oracle or perfect predictor**; two-pass trace
  replay was rejected because the passes desync once timing changes
  (relevant to the agentic BTB oracle idea, [[questions]]).
- **Ghost ≠ skip the compute.** The value is still produced; only resource
  accounting changes. The benefit is purely subtractive on the OoO pool.
- **Read headroom as a resource-vs-performance curve** (sweep IQ/port
  sizes with ghosting on and off), not a single number.
- It is an upper bound by construction: no misprediction recovery cost, and
  branch ghosting is optimistic because the BP predicts every branch.

## Result (FFT microbenchmark, 2026-06-28)

| | ghost off | ghost on |
|---|---|---|
| cycles | 12,565,425 | 12,584,481 (+0.15%) |
| IPC | 2.540 | 2.536 |
| freed | | 7,994,629 IQ entry-cycles, 2,230,904 issue slots and FU acquisitions; 2,331,158 ghost uops (~7%) |

- Knob off: every stat byte-identical to the pre-feature binary; on vs off:
  identical committed instructions and guest output.
- Resources freed at essentially zero cost; FFT is data-flow bound, so
  freeing branch resources neither helps nor hurts at iso-size. A short
  2M window showed +1.3%, traced to a prefetcher timing perturbation that
  washed out at full length (a single short window misled again).
- The OoO-size sweep (the actual go/no-go) was deferred and never run; the
  project moved on to building real MRN.

The execute-at-fetch run-ahead substrate built earlier (validating ~30K
libc start-up instructions byte-exact) was parked (commit 3b51476db4).
