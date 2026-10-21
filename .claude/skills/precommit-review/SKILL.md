---
name: precommit-review
description: >-
  Review the staged changes in this gem5 repo for code-quality gates that must
  hold before every commit. Invoke this immediately BEFORE running `git commit`
  (the git-commit skill calls it automatically). Its primary, mandatory gate is
  the naming rule: no conversational or session-specific names — arbitrary mode
  letters, ad-hoc numbered taxonomies, private jargon — may be left in code,
  comments, identifiers, or param help text. Use whenever committing here, or
  when the user asks to "review before commit" / "check the staged changes".
---

# Pre-commit code review (gem5 / Garfield)

A lightweight gate run on the **staged diff** before every commit. It is not a
full review; it enforces a small set of rules that are cheap to check and
expensive to let slip. **The naming rule is mandatory and blocking.**

## How to run it

1. Look only at what is being committed: `git diff --cached`. Do **not** flag
   pre-existing lines the diff doesn't touch — this gate is about what *this
   commit* adds, so legacy naming elsewhere is out of scope (clean it in a
   dedicated pass, not here).
2. Apply each gate below to the added/changed lines.
3. Report findings as a short list, each with `file:line`, the offending term,
   and a concrete standard replacement. If there are none, say so explicitly.
4. **If the naming gate finds anything, the commit must not proceed** until the
   author fixes it (or explicitly overrides — see Overrides). Report, then stop
   and hand back to the author / the git-commit flow.

## Gate 1 — Naming (mandatory, blocking)

**Rule of thumb:** would a competent engineer who was *not* part of the
conversation that produced this code understand the name from the code alone?
If no, it is not a standard term and must not be committed.

Conversational / session-specific naming is the common failure here. It reads
fine to the author because they lived the discussion, and is opaque to everyone
else. Flag, in code / comments / identifiers / param help / stat descriptions:

- **Arbitrary letter or number labels** standing in for a concept: `mode A`,
  `mode B`, `mode C`, `mode (C)`, `option 2`, `variant C.1`, `case B.3`,
  `the 1a fix`. Also the parenthesized and mid-sentence forms — `... the
  aliasing path (C) ...`, `a later mode (C)` — which a naive `mode [abc]`
  grep misses; search for the bare letter in parentheses too. These carry no
  microarchitectural or domain meaning. Replace with what the thing *does*:
  `mode B` → `value forwarding` / `the value path`; `mode C` → `producer
  aliasing` / `the alias path`; `C.1` → the actual mechanism it names.
- **Private jargon / nicknames** from discussion that never got a real
  definition in the code: internal shorthand, a reviewer's initials, a ticket's
  pet name, "the thing we talked about".
- **Roadmap/stage references** that only resolve against an external plan:
  bare `Stage 2`, `phase 3`, unless the same comment says what the stage *is*.

Not flagged (these ARE standard / defined in-repo): documented project acronyms
whose definition lives in the tree (e.g. `MRN` = memory-rename predictor,
defined in the wiki under `docs/wiki/`, or for Garfield terms in
`docs/legacy-log/garfield/`), established architecture terms (ROB, LSQ, rename,
physreg, squash), and public API identifiers whose names are already shipped
(param values, enum spellings) — for those, flag only the *explanatory comment*
if it leans on conversational terms, and note the API rename as a separate
follow-up rather than breaking the interface in a cleanup commit.

When unsure whether a term is standard: it isn't. Prefer the descriptive name.

## Gate 2 — Leftover scaffolding (blocking)

Flag anything that looks like temporary investigation code that shouldn't ship:
`XXX`/`TEMP`/`TEMPORARY`/`DEBUG` markers, `DPRINTF` added purely to trace a
one-off, diagnostic-only stats or fields whose comment says "diagnostic" with
no consumer, and commented-out code. Keep genuinely useful diagnostics, but
make sure their comment justifies keeping them.

## Gate 3 — Obvious correctness/consistency (advisory)

Quick, cheap checks only; deeper review belongs to `/code-review`. Note (do not
necessarily block on): a stat/field added but never incremented/read, an
accounting identity the commit message claims but the diff doesn't close, a
comment that contradicts the code it sits above.

## Output format

```
precommit-review: <N> finding(s)
  [Gate 1 naming]  path/to/file.cc:123
      "mode C" — replace with "producer aliasing" / "the alias path"
  [Gate 2 scaffolding]  path/to/file.hh:45
      "XXX TEMP counter" — remove or justify
  ...
```
or, when clean:
```
precommit-review: clean (naming, scaffolding, consistency gates pass)
```

## Overrides

The author may consciously accept a finding (e.g. a param value that is already
shipped API). Record the reason in one line and proceed; never silently ignore
a naming finding.
