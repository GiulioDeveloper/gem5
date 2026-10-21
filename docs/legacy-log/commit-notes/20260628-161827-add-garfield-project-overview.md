# doc: Add Garfield project overview

- **Date:** 2026-06-28 16:18   ·   **Branch:** rbdev

## Goal
Capture the Garfield research project's intent in one durable, discoverable
place — the north-star document a new contributor (human or agent) should read
before touching Garfield code — and link it from CLAUDE.md.

## Summary of changes
Adds `docs/garfield/README.md`, the project overview:

- **What Garfield is** — lazy execution of speculatively-resolved, *noncritical*
  instructions (the lazy-cat namesake).
- **Core hypothesis** — an accurate control-flow (branch) or data-flow (value
  prediction, memory renaming, Constable-style) prediction *detaches* an
  instruction from the program's CFG/DFG, so its execution latency no longer
  gates end-to-end performance.
- **Two exploitation levers** — a split issue backend (scarce OoO IQ + cheap
  in-order FIFO) and lazy execution-port prioritization.
- **Headroom methodology** — a "ghost execution" study: predicted uops cost
  zero OoO IQ entries and zero OoO execution ports; the benefit is the freed
  resources handed to critical instructions (purely subtractive — the ghost's
  own timing is unchanged, never early). Key move: *assume predicted = correct*,
  which removes any need for front-end ground truth → single-pass, oracle-free.
- **Eligibility vs coverage** — gate ghosting on a real predictor's coverage,
  not on eligibility (VP eligibility ≈ every register-producing uop).
- **Three-stage plan** — branches (no new predictor) → memory renaming → value
  prediction.
- **Pitfalls** and **rejected alternatives** (two-pass replay; the now-parked
  execute-at-fetch run-ahead engine, preserved on branch `execute-at-fetch`).

Also adds a "This fork: the Garfield project" pointer to the overview from
CLAUDE.md.

## Files changed
- `docs/garfield/README.md` — new project overview / north-star doc.
- `CLAUDE.md` — add the Garfield section linking the overview.
