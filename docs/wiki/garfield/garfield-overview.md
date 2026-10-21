---
type: garfield
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/garfield/README]]"
  - "[[legacy-log/garfield/mrn-ideas]]"
  - "[[legacy-log/research-log/MRN/2026-07-28-cost-side-criticality-closure]]"
  - "[[legacy-log/research-log/VP/2026-08-05-evtage]]"
  - "[[legacy-log/research-log/VP/2026-08-05-mrn-vp-composition]]"
  - "[[legacy-log/research-log/VP/2026-08-15-eves-estride-composition]]"
  - "[[legacy-log/commit-notes/20260628-184331-add-stage1-ghost-execution]]"
tags: [garfield, reference, closed]
---

# Garfield (closed reference project)

**What it was:** the first research project on this fork (branch `rbdev`,
2026-06-27 to 2026-08-15). It asked whether **accurately predicted
instructions can be executed lazily on a cheap in-order backend**, freeing
the scarce out-of-order resources of a Neoverse V2-class core for the
instructions that need them. It is **closed**; it stays here as a source
of O3 pitfalls, methodology and reusable infrastructure
([[garfield-lessons]]). The current project is [[overview]].

## The idea

- **Hypothesis:** an accurately predicted instruction is detached from the
  control- and data-flow graphs (its consumers proceed on the prediction),
  so it becomes noncritical and could run late, in the slack.
- **Design target:** a split backend, OoO issue queue for critical
  instructions plus an in-order FIFO for predicted ones, with "lazy" ports
  where critical instructions win contention.
- **Gate:** a *ghost execution* headroom study: predicted instructions cost
  no OoO IQ entry and no port. The key methodological move was **real
  predictor coverage, predictions assumed correct**: no ground truth needed,
  so single-pass and oracle-free.
- **Plan:** three stages, cheapest first: branches → memory renaming → value
  prediction.

## What actually happened

| stage | page | outcome |
|---|---|---|
| 1. ghost branches | [[ghost-execution]] | ghosting all branch uops on an FFT microbenchmark freed ~8M IQ entry-cycles and ~2.2M issue slots at **−0.15% IPC**: resources freed, no speedup at iso-size. The OoO-size sweep that would show a downsizing win was never run. |
| 2. memory renaming (MRN) | [[memory-renaming]] | became a real speculation mechanism (forward a load's value at rename, verify, squash), not a ghost study. Final: value-file rendezvous, **geomean 1.0092** over 190 SPEC CPU 2026 checkpoints. Chapter closed 2026-07-28. |
| 3. value prediction (VP) | [[value-prediction]] | a VP framework in O3 plus LVP (1.0093), VTAGE (1.0194 loads / 1.0171 all), **E-VTAGE all-instructions 1.0238** (best), EVES with E-Stride (worse). VP subsumes 88% of MRN. Last report 2026-08-15. |

The project drifted from "measure the headroom for a lazy backend" to
"build the best data-dependency-breaking speculation"; the lazy backend
itself was never built or measured beyond Stage 1.

## Code still in the tree (all off by default)

| flag | code |
|---|---|
| `--ghost-exec` | `src/cpu/o3/ghost_policy.*`, IQ/issue exemptions in `inst_queue.cc` |
| `--use-mrn`, `--mrn-*` | `src/cpu/o3/mem_rename_*`, rename/LSQ/commit hooks |
| `--use-vp`, `--vp-*`, `--vtage-*`, `--evtage-*`, `--eves-*` | `src/cpu/o3/vp/` (framework + LVP, VTAGE, E-VTAGE, EVES/E-Stride), with the papers in `src/cpu/o3/vp/papers/` |

Plus infrastructure every current run uses: the [[neoverse-v2]] configs in
`configs/garfield/arm/`, `fs_run.py` ([[checkpoints]]), `sim_opts.py`, the
ROB-head watchdog and the FDP hang fix ([[simulation-hangs]]).

## Methodology (Garfield era)

190 SPEC CPU 2026 SimPoint checkpoints (26 benchmarks × SimPoints, "43
workloads" = benchmark × input), FS restore, **10M warm-up + 50M
detailed**, per-checkpoint IPC speedup, geomean over the 190, S-curves and
loser-tail analysis. Not the same set or windows as the agentic-era sweeps
([[spec-cpu-2026]], [[warmup-and-skip]]).

> [!conflict] ROB size in the Garfield reports
> The MRN report says "512-ROB class", the EVES report "256-entry ROB, 2MiB
> LLC". `configs/garfield/arm/neoverse_v2.py` has had `numROBEntries = 320`
> since the config was created (commit 360b14ca7f), and the 2 MiB cache is
> the private L2. The config is authoritative; the reports are wrong.

> [!conflict] Stale status in the north-star README
> [[legacy-log/garfield/README]] still says "Next: Stage 1" and "benchmark
> set: FFT microbenchmark". Both are superseded by the table above.
> [[legacy-log/garfield/mrn-ideas]] mixes eras: its "fleet status 1.0001,
> 61/190" is from before the rendezvous redesign; the closed configuration is
> 1.0092.

> [!warning] All Garfield O3 numbers predate the L2 TLB fix
> Every Garfield run had the L2 TLB disconnected ([[l2-tlb-disconnected]]).
> Relative results (mechanism on vs off, same config) stand; absolute IPC
> and TLB figures are not comparable with agentic-era runs.
