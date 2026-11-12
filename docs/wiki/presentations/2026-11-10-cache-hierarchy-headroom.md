---
type: presentation
status: current
updated: 2026-11-10
sources:
  - https://claude.ai/artifact/XerHSEe8yAKWx29QVQzedy
  - runs/sweep/20261104-1115-base/compare-1B-all/
  - runs/sweep/20261104-1115-compare-all/
  - runs/sweep/20261106-2004-compare/
tags: [presentations, limit-study, cache, tlb]
---

# Deck: Cache Hierarchy Headroom (2026-11-10)

A short deck of the perfect-cache limit studies on the 27 agentic tasks.
Link: https://claude.ai/artifact/XerHSEe8yAKWx29QVQzedy (private; share it
from its Share menu). Built from [[2026-11-02-perfect-l2]],
[[2026-11-03-perfect-l1i]] and [[2026-11-06-perfect-l1d]]; the user edited
it after the first build.

## Slides (current version)

| # | title | content |
|---|---|---|
| 1 | Cache Hierarchy Headroom | cover: perfect L1I, L1D, L2 and TLB on the Neoverse V2 model; provisional |
| 2 | Configurations \| 4 independent switches | what each switch models; 27 tasks × 1B windows |
| 3 | IPC Comparison | geomean IPC bars vs base (1.009): pTLB +4.3%, pL1I +9.6%, pL1I+pTLB +13.8%, pL1D +43.2%, pL2 +48.2%, pL1D+pTLB +48.8%, pL2+pTLB +49.6%, pL1D+pL1I +58.8% |
| 4 | Top-Down Breakdown | stacked mean slot shares per configuration (base FE 42.5 / BE 34.5 / bad spec 8.2 / retiring 14.9; pL1I FE 37.6; pL1D FE 54.3, BE 13.7; pL2 FE 50.4, BE 15.5); marked work in progress ([[top-down-accounting]]) |

## Observations on the slides

- Slide 3: the data side (L1D, L2) gains far more than the code side (L1I);
  address translation adds roughly on top of both.
- Slide 4 (user's reading): perfect L1I barely moves front-end bound, unlike
  perfect L1D and L2, which remove most back-end stalls and leave the front
  end as the limit. Possible cause, not verified: the fetch latency and width
  of the Neoverse V2 model ([[2026-11-03-perfect-l1i#Width 8 and a 1-cycle perfect L1I (2026-11-09)]]).

## Notes

- **Perfect L2 (+48.2%) is above perfect L1D (+43.2%).** The L2 also covers
  instruction misses beyond the L2. Not yet explained, and the perfect-L2
  page has no Results section yet: its numbers are in
  `runs/sweep/20261104-1115-compare-all/compare_geomean.csv`.
- **Shares vs absolute slots.** Per instruction, front-end-bound slots
  fall about 19% with pL1I, 11% with pL1D and 20% with pL2 (mean share /
  geomean IPC, rough). So perfect L2 removes as much front-end time as
  perfect L1I does. Slide 4 speaks in shares; the speaker notes say this.
- **Slides cut from the first build:** a 4.5× statement slide, the top-down
  table (base → pL1D: front-end bound 42.5% → 54.3%, back-end 34.5% →
  13.7%), per-task IPC and top-down violins, and caveats. The two violin
  PNGs are still uploaded to the deck. Regenerate them with
  `slide_violins.py` ([[general-guidance]]) into `runs/perfect-slides/`.
