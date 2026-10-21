# doc: Record 1a fleet sweep and drop mode labels

- **Date:** 2026-07-21 22:47   ·   **Branch:** rbdev

## Goal
Record the 190-checkpoint sweep result for the 1a branch in the MRN idea log,
and bring the doc in line with the naming rule (no "Mode B" / "Mode C").

## Summary of changes
Add the fleet result to `docs/garfield/mrn-ideas.md`: geomean speedup 1.0001
across 190 checkpoints (up from 0.985 pre-1a), 61/190 beat 1.0, with the
"accurate but not latency-critical" caveat (cppcheck 0.985 at 98% acc). Rename
the doc's conversational "Mode B" -> value forwarding / value path and "Mode
C" -> producer aliasing / alias path to match the code cleanup, keeping the
1a/1b section numbers as document structure.

## Files changed
- `docs/garfield/mrn-ideas.md` — fleet sweep result added; "Mode B/C" replaced with descriptive terms.
