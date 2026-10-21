---
type: garfield
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/VP/2026-08-03-last-value-predictor]]"
  - "[[legacy-log/research-log/VP/2026-08-04-vtage]]"
  - "[[legacy-log/research-log/VP/2026-08-05-evtage]]"
  - "[[legacy-log/research-log/VP/2026-08-05-mrn-vp-composition]]"
  - "[[legacy-log/research-log/VP/2026-08-15-eves-estride-composition]]"
  - src/cpu/o3/vp/
tags: [garfield, value-prediction, o3, vtage, eves]
---

# Garfield Stage 3: value prediction (VP)

**What it is:** an algorithm-agnostic value-prediction framework in O3
(`src/cpu/o3/vp/`, `--use-vp`): predict at **rename**, train at writeback
(or commit), verify and squash inclusively (MRN's recovery). Each predictor
is one SimObject on a shared base (modelled on gem5's prefetcher
framework). Best result: **E-VTAGE, all integer instructions, geomean
1.0238** over 190 SPEC CPU 2026 checkpoints. Part of
[[garfield-overview]]. Reference papers in `src/cpu/o3/vp/papers/`
(VTAGE HPCA'14, EVES).

## Results (geomean speedup, 190 checkpoints, 10M + 50M)

| predictor | loads only | all instructions | note |
|---|---|---|---|
| LVP (last value) | 1.0093 | 1.0053 | matches MRN's 1.0092 from one PC-indexed table; losers separated from winners only by mispredict volume |
| VTAGE | 1.0194 | 1.0171 | 6.3× fewer wrong predictions (1.84M → 292K) at 99.92% accuracy; beats LVP-all on 150/190 |
| VTAGE, dense-64 history `{2,4,6,11,20,36,64}` | 1.0212 | 1.0181 | best history series |
| **E-VTAGE** (EVES per-class confidence policy on VTAGE) | | **1.0238** | +0.55% over iso-history VTAGE, 28% fewer wrongs: predicts *more* loads, *fewer* non-loads (placement, not volume) |
| EVES = E-VTAGE + E-Stride, verbatim arbitration | | 0.9812 | a CVP source quirk (VTAGE hit overwrites stride without a confidence check) widened in the port |
| EVES, confidence-gated arbitration | | 1.0165 | E-Stride adds +2.6 points of coverage at 99.2% accuracy and still loses: ~70 flushed instructions per wrong × 2.35M wrongs > the saving from 282.5M corrects |
| MRN + VP stacked (either order) | | 1.0152 / 1.0139 | slower than VP alone (1.0171); 88.2% of MRN's committed instructions are VP-covered anyway |

## Lessons

- **Coverage is not speedup.** E-Stride and MRN stacking both added
  coverage and lost IPC; E-VTAGE won with *less* coverage, better placed.
- **Trace-driven headlines do not transfer** to a real OoO pipeline (CVP's
  infinite-window, fixed-penalty model vs inclusive squashes, wrong path,
  speculative history). E-Stride was the dominant EVES partner in CVP-1 and
  a loser here.
- **A pure scheduling side-effect loser exists:** under LVP 736.ocio_r.2.0
  lost 2.6% with only 12 wrong predictions.
- **Wrong-path training (the doomed window):** for ~2 cycles between a
  squash being signalled and its victims being marked, doomed instructions
  passed verify/train and trained wrong-path values, inflating
  `predictionsCorrect` and once closing a livelock. Fixed with a per-thread
  pending-squash low-water mark in IEW; a `fatal_if` forbids VP with a
  configured `squashWidth` ([[o3-wrong-path-counting]]).
- **Five defects caught by review before any run** of VTAGE, each of which
  would have silently corrupted results: a commit-train / writeback-verify
  livelock, two generations of µop-key aliasing, history restore skipped
  when the squash victim is at the ROB head, and the FS ifetch-fault noop
  zeroing the whole history on every page-fault trap.
- **A base-gem5 hang surfaced:** the FDP block walk wrapped past MaxAddr
  ([[simulation-hangs]]).
- Count at the **commit site** (`committedVpPredicted`, `committedMrned`:
  committed implies correct) rather than the verify site, which reads 3–5%
  high from wrong-path corrects.
- Probe sets must be suite-balanced: a 16-checkpoint probe without
  stockfish was far too kind to EVES-verbatim (0.9985 vs 0.9812 at 190).

More in [[garfield-lessons]].
