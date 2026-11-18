---
type: presentation
status: current
updated: 2026-11-10
sources:
  - https://claude.ai/artifact/XerHSEe8yAKWx29QVQzedy
  - analysis_scripts/presentations/
tags: [presentations, slides]
---

# Presentations: general guidance

How we make slide decks of the project's results. Decks are Claude Slides
artifacts. Each one gets a page in `presentations/` that holds its link,
content, sources and observations. Example: [[2026-11-10-cache-hierarchy-headroom]].

## Writing slides

- **Titles are neutral.** They name what the slide shows, not what to
  conclude: "IPC Comparison", "Configurations | 4 independent switches",
  "Cache Hierarchy Headroom". Avoid claim titles such as "The data side
  holds most of the headroom".
- **Observations go in the body,** under the figure, as one or two short
  bullets ("Data side shows much more improvement").
- **Keep decks short.** One figure or table per slide. The first deck was
  cut from 8 slides to 3.
- **Every number traces to the wiki or a `runs/` path.** Put the source in
  a 24px footer, and say on the cover that results are provisional
  ([[SCHEMA#Findings are provisional]]).
- Detail and caveats go in the speaker notes.

## Figures (`analysis_scripts/presentations/`)

- `slide_bars.py COMPARE_DIR --sweeps ... --names ... --colors ...`
  prints native bar rows (name, bar, `+43.2%`) from `compare_geomean.csv`,
  ready to paste into a slide. The bars stay editable.
- `slide_violins.py COMPARE_DIR -m ipc [-m ...] --sweeps ... -o X.png`
  draws per-checkpoint ratio violins in the style of `sweep_compare.py
  --pdf`, for a few metrics at slide size (1664 px wide by default). Run it
  with `runs/venv/bin/python` (matplotlib). Upload the PNG as a deck asset.
- Top-down (TMA) stacks, bottom to top: Retiring, Bad speculation,
  Front-end bound, Back-end bound. The legend uses the same order, and so
  do the colours: dark `#16202B`, grey `#C3CBD3`, blue `#3A6EA5`, orange
  `#D9772B`.
- Don't put the full `violins*.png` grids on slides: 35 panels are
  unreadable at slide size.
- Colours follow the sweep's position in the comparison, so they match its
  `compare.html`.

## Working with decks

- The deck artifact is the record. It isn't rebuilt from the wiki (unlike
  [[publish]] outputs), and the user edits it directly. Read the live
  version before changing it, and change only the slides asked for.
- Don't log deck work in [[log]]. The deck's own page is the only record.
- Look used so far: Space Grotesk headings, IBM Plex Sans text, dark
  `#16202B`, light `#F6F5F0`, blue `#3A6EA5` front-end side, orange
  `#D9772B` memory side.
