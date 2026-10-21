# doc: Record value-file rendezvous outcome

- **Date:** 2026-07-25 17:55   ·   **Branch:** rbdev

## Goal
Close research-log item 1c (aliasing value delivery) with the implemented
resolution and measured results, so future sessions do not re-litigate it.

## Summary of changes
mrn-ideas.md 1c: NEXT -> DONE. Records the structural root cause (SQ
populated at dispatch, same-iteration store never visible at rename), the
value-file rendezvous resolution (deposit at store rename / read at load
rename, SC learning at address resolution, gen tags, confidence), and the
measurements: mrnrec +125% IPC with zero mispredicts, gcc alias-only +0.66%
(44,831 aliases @95.1%), full model +9.35%. Points to the spec and names
the follow-ups (190-ckpt sweep; fold+delete legacy value path/correlator).

## Files changed
- `docs/garfield/mrn-ideas.md` — 1c section rewritten as DONE with results.
