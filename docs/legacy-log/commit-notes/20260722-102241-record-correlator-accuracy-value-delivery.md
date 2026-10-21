# doc: Record correlator accuracy, value-delivery next step

- **Date:** 2026-07-22 01:40   ·   **Branch:** rbdev

## Goal
Record the correlator-isolation result and redirect the aliasing plan.

## Summary of changes
mrn-ideas 1b: the correlator names the producer 99.6% correctly, yet aliasing
fires on only 1,702 loads (200x gap) -- the loss is downstream value delivery,
not prediction. Retract the "give aliasing a confidence counter" next step
(gating a 99.6% predictor harder cannot help). New 1c: fix aliasing value
delivery -- deliver from the specific producing store instance, not a
rename-map arch-reg lookup.

## Files changed
- `docs/garfield/mrn-ideas.md` — record correlator 99.6%; retract confidence-counter step; add 1c value-delivery direction.
