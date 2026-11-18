---
type: presentation
status: current
updated: 2026-11-17
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
| 3 | IPC Comparison | geomean IPC bars vs base (1.010), replay infra excluded: pTLB +4.6%, pL1I +8.5%, pL1I+pTLB +13.5%, pL1D +43.5%, pL2 +47.6%, pL1D+pTLB +49.1%, pL2+pTLB +49.1%, pL1D+pL1I +58.4% |
| 4 | Top-Down Breakdown | stacked mean slot shares per configuration (base FE 41.9 / BE 34.0 / bad spec 8.8 / retiring 15.2; pL1I FE 37.4; pL1D FE 53.8, BE 12.9; pL2 FE 50.0, BE 14.7); marked work in progress ([[top-down-accounting]]) |
| 5 | Investigating the model | what was off in the gem5 V2 front end: fetch/decode 6 micro-ops into 8-wide rename (real V2: 6 instructions decoded, 8 MOPs from the MOP cache); a fetch bubble per new L1I line even on hits (real V2 reads ahead); checks fe8 and l1i1 ([[2026-11-05-front-end-width]]) |
| 6 | Investigating the model - Results | IPC and top-down for base, fe8 (+1.1%), fe8-l1i1 (+3.4%; FE 24.3, BE 47.2) and pL1I (+8.5%), fe8-pl1i1 (+12.5%; FE 18.0, BE 50.6); WIP ([[2026-11-03-perfect-l1i]]) |

## Observations on the slides

- Slide 3: the data side (L1D, L2) gains far more than the code side (L1I);
  address translation adds roughly on top of both.
- Slide 6: width 8 and a 1-cycle hit cut front-end bound 41.9% → 24.3% for
  +3.4% IPC; the freed slots mostly become back-end stalls; on a perfect L1I
  they add +3.7% (front-end bound 18.0%).
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
  fall about 18% with pL1I, 11% with pL1D and 19% with pL2 (mean share /
  geomean IPC, rough; no-infra values). So perfect L2 removes as much front-end time as
  perfect L1I does. Slide 4 speaks in shares; the speaker notes say this.
- **Top-down predates the rename fix** (2026-11-13, [[top-down-accounting]]):
  every sweep here overstates front-end bound, by up to 7.6 points at the
  base median. Slides 4 and 6 say so in the notes; rerun before final numbers.
- **Slides cut from the first build:** a 4.5× statement slide, the top-down
  table (base → pL1D: front-end bound 42.5% → 54.3%, back-end 34.5% →
  13.7%), per-task IPC and top-down violins, and caveats. The two violin
  PNGs are still uploaded to the deck. Regenerate them with
  `slide_violins.py` ([[general-guidance]]) into `runs/perfect-slides/`.

## Without replay infra (2026-11-16)

The deck's numbers are whole-window values, replay infra included. Since
2026-11-16 the comparisons leave the replay infra and the idle task out of
agentic values by default ([[sweeps]]).
`runs/sweep/20261104-1115-base/compare-1B-all/` was rebuilt that way
(`runs/sweep/resummarise-noinfra.sh`; the old one is in
`compare-1B-all-v5/`). Geomean IPC (`compare_geomean.csv`): base 1.010
(was 1.009), pTLB +4.6% (+4.3%), pL1I +8.5% (+9.6%), pL1I+pTLB +13.5%
(+13.8%), pL1D +43.5% (+43.2%), pL2 +47.6% (+48.2%), pL1D+pTLB +49.1%
(+48.8%), pL2+pTLB +49.1% (+49.6%), pL1D+pL1I +58.4% (+58.8%). Top-down
means, base / pL1I / pL1D / pL2: front-end bound 41.9 / 37.4 / 53.8 /
50.0%, back-end bound 34.0 / 36.3 / 12.9 / 14.7%. The ranking and the
reading of slides 3–4 do not change. Rebuilt with `--with-infra`, all 43
aggregates of the old comparison come out identical, so the shifts come
only from the exclusion. Two checkpoints (axios-5892, bat-2835) are 94–97%
infra by instructions; their values now rest on 30–55M instructions.
New figures: `runs/perfect-slides-noinfra/` (`ipc_bars.html` from
`slide_bars.py`, `ipc_violins.png`, `topdown_violins.png`). The deck
itself was updated to these values on 2026-11-17 (slides 2-5; slide 5 from
`runs/sweep/20261112-1720-compare-15cfg/`, which matches `compare-1B-all`).

