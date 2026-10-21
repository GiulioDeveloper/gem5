# doc: Spec MRN value/alias path separation

- **Date:** 2026-07-21 23:15   ·   **Branch:** rbdev

## Goal
Design doc for making the MRN value-forwarding and producer-aliasing paths
independent (each enable/disable-able), retiring the mrnMode enum / unified().

## Summary of changes
Approved brainstorming spec: the paths already own disjoint data structures;
only the rename trigger and config couple them. Two independent bool params
replace mrnMode; rename.cc gets two independent triggers (aliasing-first);
per-path training is gated so a disabled path stops maintaining its tables.
Scope is structural only -- no aliasing confidence counter this step.

## Files changed
- `docs/superpowers/specs/2026-07-21-mrn-path-separation-design.md` — the design spec.
