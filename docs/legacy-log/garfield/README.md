# Garfield — Lazy Execution of Noncritical Instructions

> The north-star document for the Garfield research project on this fork
> (branch `rbdev`). Read this before working on any Garfield-related code.

## TL;DR

Garfield asks whether **accurately-speculated instructions can be executed
*lazily* on a cheap backend**, freeing the scarce out-of-order (OoO) resources
of a modern core for the instructions that actually need them. The bet: **equal
performance at lower power/area, or more performance within the same budget.**

Before building anything, we model the **headroom** with an idealized "ghost
execution" study. If the ceiling is negligible, the project stops there.

## The name

Garfield, the lazy cat. *Garfield instructions* are the ones the machine can
afford to run lazily — the speculated, noncritical ones — whenever there is
slack.

## The core hypothesis

Computer architecture has produced extremely accurate **control-flow
predictors** (branch predictors) and **data-flow predictors** (value
prediction, memory renaming, and recent work such as **Constable**, ISCA 2024).

When such a predictor accurately predicts an instruction's outcome, that
instruction's effect on the program's **control-flow graph (CFG)** or
**data-flow graph (DFG)** is *already known at the front end*. Its consumers can
proceed on the predicted direction/value without waiting for it to execute.
Therefore:

> An accurately predicted instruction is **detached** from the CFG/DFG and
> becomes **noncritical** — its own execution latency no longer contributes to
> the program's end-to-end latency.

Predictions can of course be wrong, and recovery is a real cost — see
[Pitfalls](#pitfalls--threats-to-validity). For the headroom study we
deliberately assume accuracy is perfect and measure the *ceiling*.

## The idea: a split, lazy backend

If the hypothesis holds, noncritical (accurately-predicted) instructions don't
need the full out-of-order machinery. Garfield exploits this with two coupled
levers:

1. **Placement (split issue).** A traditional OoO issue queue co-exists with a
   simple in-order **FIFO** issue queue. At the front end (fetch/rename) each
   instruction is *steered*: critical (unpredicted) → OoO IQ; noncritical
   (predicted) → FIFO. This conserves the scarce, power-hungry OoO IQ entries
   for instructions that actually benefit from out-of-order scheduling. The FIFO
   queue is simpler and far lower-power.

2. **Prioritization (lazy ports).** When an execution port is contended,
   **critical instructions win the port**; noncritical instructions defer and
   execute lazily in the slack. This is the namesake behavior.

Coupled, the machine spends its expensive scheduling/issue/port resources only
where out-of-order actually buys something, and lazily drains everything else →
**same performance at less power, or more performance in the same power/area
budget.**

## Why a headroom study first

This is a speculative idea; we must show the opportunity exists before designing
a real split backend. The go/no-go gate is a **"ghost execution" headroom
model**:

> Model a backend where accurately-predicted instructions cost **zero OoO IQ
> entries and zero OoO execution ports** (they "ghost" through). Measure
> performance/power vs. baseline. Meaningful benefit → proceed; negligible →
> discard the idea.

### The key methodological move: assume *predicted = correct*

A naive oracle ("perfectly predict everything *eligible*, then ghost it") is
wrong, because **eligibility differs per predictor**:

| Predictor        | Eligible uops                              |
|------------------|--------------------------------------------|
| Branch predictor | branch uops                                |
| Memory renaming  | load uops                                  |
| Value prediction | **every register-producing uop** (~all)    |

Ghosting all *eligible* uops would ghost nearly the entire stream (because VP
eligibility is almost universal) and produce a wildly inflated, meaningless
ceiling.

Instead we use **real predictors with realistic coverage, but assume every
prediction they make is correct.** A real value predictor only fires when
confident (coverage typically **~20%** of uops); we take exactly the uops it
predicts and treat them as correctly predicted → ghost them.

This yields a profound simplification:

> Because we assume every prediction is correct, **we never need to know whether
> a prediction is actually correct** — so we never need an instruction's ground
> truth at the front end. We only need to know *whether the predictor produced
> an output* (its coverage decision), which the predictor already knows at
> fetch/rename from its own state.

The study is therefore **single-pass and oracle-free**: no run-ahead engine, no
two-pass trace. (See [Rejected methodologies](#methodologies-considered-and-rejected).)

Branches remain somewhat inflated: a branch predictor predicts *every* branch
regardless of confidence, so "ghost all branches" is optimistic. Accepted for a
first cut; branches are a minority of uops.

### Ghost = drop OoO resource demand, *not* early execution

A ghosted instruction's real value is **still computed** — gem5's normal
functional execution produces it — so architectural state stays correct and we
never have to trust predicted bits for correctness. "Ghost" means exactly one
thing: the instruction **does not allocate an OoO issue-queue entry and does not
occupy an OoO execution port**. Its *own* execution timing is **not**
accelerated — we never resolve it early. It may even resolve **late**, on the
cheap in-order backend, and by the core hypothesis that lateness does not matter,
because the instruction was already resolved speculatively at the front end and
is detached from the CFG/DFG. The entire benefit comes from the **freed OoO
issue-queue entries and execution ports becoming available to the critical
instructions** — the study is purely *subtractive* on the scarce OoO pool, never
*additive* on the ghost's own speed. (An implementation that skipped the
computation would corrupt architectural state — do not.)

### Reading the result: a curve, not a number

The Garfield win is "free up scarce OoO IQ/ports," so the headroom is a
**resource-vs-performance curve**, not a single number:

1. Hold OoO IQ/port counts at realistic Neoverse V2 sizes, ghost the predicted
   uops, measure IPC **and** OoO IQ/port occupancy.
2. Sweep OoO IQ size / port count with ghosting **on vs off**.

The payoff appears as **iso-performance at a smaller OoO IQ / fewer ports**
(power/area win) or **higher IPC at the same IQ** (if the IQ was the
bottleneck). If the curve doesn't shift, the idea is dead.

## The three-stage plan

Each stage adds a class of ghost instructions and measures the incremental
headroom. Ordered cheapest-first.

- **Stage 1 — Branches (no new predictor).** Use the existing Neoverse V2 branch
  predictor. Mark all branch uops ghost: zero OoO IQ entry, zero OoO port. Needs
  only an O3 timing-model change — *zero new predictors* — so it yields a first
  data point immediately.

- **Stage 2 — Memory renaming.** Implement memory renaming (predict a load's
  value via store→load forwarding). Treat every load it predicts as correct →
  ghost it.

- **Stage 3 — Value prediction.** Implement a realistic, confidence-gated value
  predictor. Treat every uop it predicts as correct → ghost it. Highest impact
  (broadest eligibility) but gated to realistic coverage.

**gem5 predictor status:** the branch predictor is already state-of-the-art
(TAGE / LTAGE / perceptron families in `src/cpu/pred/`). **Value prediction and
memory renaming do not exist in gem5** and must be implemented.

## Pitfalls & threats to validity

- **Eligibility inflation.** VP eligibility = all register-producing uops;
  ghosting by *eligibility* instead of *coverage* inflates the ceiling to
  meaninglessness. → Always gate on real predictor coverage.
- **Branch inflation.** The BP predicts every branch regardless of confidence,
  so ghosting all branches is optimistic. Read Stage 1 as a loose upper bound.
- **This is an upper bound, by construction.** Assuming predictions correct
  removes all misprediction-recovery cost. In a real machine, lazily resolving a
  *mispredicted* branch on the cheap backend would *delay* recovery and hurt
  performance. The ghost study ignores this on purpose — valid for a go/no-go
  (if even the ceiling is negligible, stop), provided we always report it as a
  ceiling.
- **Ghost ≠ skip compute.** The real value must still be produced; only
  accounting changes.
- **Headroom ≠ achievable.** A positive ceiling justifies building the realistic
  design (with recovery, a finite cheap backend, steering mistakes); it does not
  promise that number.
- **Predictor-history perturbation.** Ghost timing changes the schedule, which
  in a real machine perturbs predictor history and wrong-path volume. Standard
  headroom simplification to ignore for a bound.

## Methodologies considered and rejected

- **Two-pass trace replay** (record outcomes in pass 1, replay in pass 2).
  **Rejected:** the passes desync once pass 2's ghosting changes timing — the
  recorded oracle no longer lines up with the diverging speculative stream.
  (This is also the community's approach for a perfect branch predictor; it does
  not generalize cleanly to data-flow ghosting.)
- **Live execute-at-fetch run-ahead engine** — a non-perturbing functional core
  that computes each instruction's ground truth one step ahead and validates at
  commit. Built earlier in this project as a substrate (see *Current status*).
  **Not needed** once we adopt *assume-predicted-correct*, because that removes
  the need for front-end ground truth. **Parked.** Revive only if we later want
  a *realistic-accuracy* variant (ghost only predictions that are actually
  correct), which does require ground truth.

### Background: why gem5 makes oracles subtle

gem5's O3 core resolves instructions at **execute**, not at fetch
("execute-at-execute"). Consequently gem5 ships **no oracle/perfect predictor**
of any kind — even a perfect *branch* predictor is nontrivial (the community
resorts to two-pass trace replay; confirmed via the gem5-users list and an empty
`grep` for `perfect|oracle` in `src/cpu/pred/`). Garfield's headroom study
sidesteps all of this by never needing front-end ground truth.

## Current status

- **Neoverse V2 O3 core config + tooling** on `rbdev` (`configs/garfield/arm/`).
- An **execute-at-fetch run-ahead substrate** was built and mostly works
  (validates ~30K libc-startup insts byte-exact), but is now **parked** — the
  *assume-predicted-correct* methodology makes it unnecessary for the headroom
  study. Details in `docs/superpowers/specs` & `plans` and commit `3b51476db4`.
- **Next:** Stage 1 — ghost branch uops in the O3 timing model and produce the
  first headroom curve.

## Open questions

- **Ghost backend cost (first cut):** *infinitely cheap* (zero-cost FIFO — the
  absolute ceiling, simplest) vs. a *finite in-order FIFO* (one port, realistic
  depth) from the start.
- Exact **OoO IQ / port sweep ranges** for the V2 model.
- **Power/area model** to translate IQ/port savings into a power number.
- **Benchmark set** for the headroom (currently the FFT microbenchmark; need a
  representative suite).
