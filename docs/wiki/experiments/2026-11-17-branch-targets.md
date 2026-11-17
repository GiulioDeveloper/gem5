---
type: experiment
status: open
updated: 2026-11-17
sources:
  - runs/jit-footprint/rubocop-1g/footprint-targets/summary.md
  - runs/jit-footprint/rubocop-1g/footprint-targets/branches.tsv
  - runs/jit-footprint/rubocop-1g/footprint-targets/branch_targets.csv
  - runs/rubocop-15G/cache8x/footprint-targets/
  - runs/branch-targets-check/
  - analysis_scripts/tasktrace/pc_footprint.cc
  - analysis_scripts/tasktrace/pc_footprint.py
tags: [agentic, rubocop, branches, btb, indirect, pc-trace, footprint]
---

# Distinct targets per branch (rubocop)

## Question

How many distinct targets does each branch have, on average and weighted
by how often it runs? It bears on the BTB (one entry per target), the
indirect predictor and the return stack. Asked by the user on 2026-11-17.

## Setup

- The footprint pass ([[pc-trace#Footprint, hit rates and branches]]) now
  keeps, per static branch, its executions, taken executions and distinct
  taken targets, and writes them to `branches.tsv` (one row per branch).
  `pc_footprint.py` aggregates them into `branch_targets.csv` and a
  *Branch targets* section of `summary.md`.
- **Static branch:** a branch instruction in its address space (a process
  instance, or the kernel), as in the rest of the pass. On a v2 trace a
  rewritten branch (a later code version) is a branch of its own.
- **Target:** the next committed PC when it is not PC + 4. An exception
  entry right after a branch is not a target; the branch's successor is
  read at the matching `eret` instead (below).
- **Averages over the branches taken at least once:**
  - *mean*: every branch counts once;
  - *taken-weighted*: each branch weighted by its taken executions, i.e.
    the target count a BTB or indirect-predictor lookup meets;
  - *exec-weighted*: weighted by all its executions.
- **Per thread** (`threads.csv`, the *Branches* section of
  `report.html`): the same per type, counted in each thread's own stream
  (kernel code included). Check on the 1G window: the threads' taken
  executions sum to the per-branch totals exactly, for every type, and
  each thread's taken-branch count equals the pass's existing one. On the
  15G trace (v1) taken executions also sum exactly, but OpenCode's main
  thread counts 0.1–0.5% more taken branches per type than the existing
  column: without encodings a PC the JIT rewrote keeps one key, and the
  two counts take its type from different first sightings (the process's
  first as a branch vs the thread's first at all).
- **no_return:** every branch type except `ret*` and `eret*`: what the BTB
  and the indirect predictor handle. The return stack handles returns.
- **Runs:**
  - 1G rubocop window on the atomic core, v2 trace with encodings:
    `runs/jit-footprint/rubocop-1g/footprint-targets/` (3.5 min, 1.8 GB);
  - the 15G rubocop trace of the cache8x run (v1, no encodings):
    `runs/rubocop-15G/cache8x/footprint-targets/` (58 min, 14.4 GB, with
    the per-thread counts). A first pass without them gave byte-identical
    `groups.tsv`, `instances.tsv`, `branch_targets.csv`, `summary.md`,
    the same `branches.tsv` rows and the same old `threads.csv` columns;
    it was replaced.

### Exceptions after a branch (fixed in the pass, 2026-11-17)

The first version of the count gave 0.5% of conditional branches and 1.7%
of `bl`s two targets. Two of the pass's assumptions were wrong:

- **EL0 entry:** with KPTI, an exception taken from user code enters the
  trampoline vectors' fixmap alias (`0xfffffbfffddf6400`/`…6480` in this
  trace), not `vectors` or `__bp_harden_el1_vectors`, which were the only
  tables the pass excluded. So an IRQ or page fault right after a user
  branch counted as a taken branch to the vector. This also set the
  *taken ever* flag of the older outputs.
- **Hidden outcome:** excluding the entry is not enough either. When a
  `bl`'s target page faults on its first fetch, the branch was taken, but
  the trace shows the vector, not the target.

Now:
- any transfer from user code into the kernel is an exception entry, and
  the pass learns the trampoline table it enters;
- a jump into a vector table counts as a new exception entry only when it
  comes from outside the tables, so the trampoline's branch-history
  clearing loop and its `ret` into `vectors` are ordinary branches;
- each thread keeps a stack of its exception entries, and an `eret` pops
  the newest one; if that entry followed a branch, the `eret`'s target is
  the branch's successor (taken when it is not PC + 4).

On the 1G window: 39,736 exception entries, 13,257 right after a branch,
13,256 resolved at their `eret` (10,836 taken), and 78 `eret`s with no
entry (new threads returning from fork). No conditional branch, `b` or
`bl` has more than one target since the fix. Against the original pass,
only the *taken ever* columns changed: 242 fewer conditional branches
(taken only by an interrupt) and 2 more returns, out of ~311K.

> [!warning] Signals
> A signal delivered on the return from an exception that followed a
> branch makes the `eret` go to the handler, which would count as one
> extra target of that branch. Not measured; it needs that coincidence,
> so it should be rare.

**Check (before the exception fix):** a brute-force Python count over a
30M-line prefix (`runs/branch-targets-check/brute.py`), keyed by the
marker's tgid with the same exception rule as the pass at the time.
- Identical on 19 of 31 (process, type) rows: branches, executions, taken
  executions, summed targets and summed targets × taken.
- The other 12 rows are opencode and git. For the two together,
  executions and taken executions are identical; only the branch and
  target counts differ. The pass starts a new address space at each exec
  and gives the code after the exec to the new name; the brute force does
  not, and opencode's fork children exec git.
- The existing outputs (`groups.tsv`, `threads.tsv` and the rest) were
  byte-identical before the exception fix.

## Results

### 1G rubocop window (atomic, v2)

From `runs/jit-footprint/rubocop-1g/footprint-targets/summary.md`:

| code | type | branches taken | mean | taken-weighted | exec-weighted | >1 target | max |
|---|---|---|---|---|---|---|---|
| all | all | 310,971 | 1.35 | 11.40 | 8.87 | 4.2% | 11,202 |
| all | no_return | 278,600 | 1.04 | 1.22 | 1.16 | 0.8% | 422 |
| all | indirect (`blr`, `br`) | 16,185 | 1.68 | 9.66 | 9.57 | 13.7% | 422 |
| all | indirect_call | 12,952 | 1.39 | 6.82 | 6.82 | 7.5% | 422 |
| all | indirect_jump | 3,233 | 2.84 | 12.98 | 12.62 | 38.2% | 226 |
| all | return | 32,369 | 3.68 | 55.17 | 55.17 | 33.8% | 1,806 |
| all | cond, direct, call | 262,415 | 1.00 | 1.00 | 1.00 | 0% | 1 |
| user | no_return | 262,962 | 1.04 | 1.24 | 1.18 | 0.8% | 422 |
| kernel | no_return | 15,638 | 1.01 | 1.09 | 1.07 | 0.4% | 74 |

The "all" row is dominated by returns and by the kernel's two `eret`s
(11,202 and ~76 targets: every user PC the kernel returns to).

Mean / taken-weighted targets per process:

| process | taken executions | no_return | indirect | return |
|---|---|---|---|---|
| opencode | 63.0M | 1.04 / 1.20 | 1.47 / 11.87 | 5.30 / 65.00 |
| [kernel] | 19.8M | 1.01 / 1.09 | 1.76 / 4.99 | 2.39 / 43.35 |
| docker | 10.6M | 1.03 / 1.28 | 1.99 / 9.24 | 4.17 / 80.22 |
| git | 2.6M | 1.04 / 1.08 | 1.71 / 2.26 | 2.71 / 8.94 |

Distribution of indirect branches (share of branches ever taken; share of
taken executions in brackets):

| type | 1 | 2 | 3-4 | 5-8 | 9-16 | 17-64 | 65+ |
|---|---|---|---|---|---|---|---|
| indirect_call | 92.5 (55.4) | 4.4 (20.4) | 1.7 (2.9) | 0.8 (3.6) | 0.3 (1.1) | 0.3 (14.4) | 0.1 (2.1) |
| indirect_jump | 61.8 (25.3) | 22.8 (15.2) | 5.7 (33.7) | 4.7 (5.1) | 2.4 (5.6) | 2.2 (9.2) | 0.3 (6.0) |
| return | 66.2 (25.5) | 15.8 (14.6) | 8.8 (11.4) | 4.6 (11.2) | 2.5 (8.3) | 1.6 (10.7) | 0.6 (18.3) |

### 15G rubocop (cache8x, v1)

From `runs/rubocop-15G/cache8x/footprint-targets/summary.md` (pass with
the final exception rule, 56 min, 13.4 GB). 15.2G instructions:

| code | type | branches taken | mean | taken-weighted | exec-weighted | >1 target | max |
|---|---|---|---|---|---|---|---|
| all | no_return | 2,615,008 | 1.04 | 2.04 | 1.71 | 0.9% | 422 |
| all | indirect | 115,201 | 1.83 | 18.78 | 18.68 | 19.4% | 422 |
| all | indirect_call | 81,308 | 1.66 | 7.09 | 7.09 | 13.0% | 422 |
| all | indirect_jump | 33,893 | 2.25 | 24.61 | 24.35 | 34.7% | 380 |
| all | return | 347,446 | 3.68 | 125.67 | 125.67 | 32.8% | 2,599 |
| user | no_return | 2,595,942 | 1.04 | 2.23 | 1.82 | 0.9% | 422 |
| kernel | no_return | 19,066 | 1.02 | 1.11 | 1.08 | 0.5% | 90 |

Mean / taken-weighted targets per process:

| process | taken executions | no_return | indirect | return |
|---|---|---|---|---|
| opencode | 876.1M | 1.05 / 1.63 | 1.58 / 23.30 | 5.99 / 202.97 |
| [kernel] | 299.9M | 1.02 / 1.11 | 1.82 / 5.58 | 2.54 / 47.38 |
| bundle (Ruby) | 203.8M | 1.08 / 4.71 | 2.92 / 22.12 | 6.36 / 36.12 |
| docker | 145.8M | 1.03 / 1.28 | 1.99 / 9.24 | 4.17 / 80.26 |
| gem (Ruby) | 55.1M | 1.06 / 4.38 | 2.54 / 20.15 | 7.29 / 34.16 |
| git | 42.0M | 1.04 / 1.07 | 1.73 / 2.29 | 2.71 / 8.69 |
| ruby | 31.4M | 1.06 / 3.97 | 2.45 / 17.31 | 6.23 / 31.69 |
| python3 | 24.7M | 1.09 / 4.68 | 1.66 / 14.96 | 2.34 / 25.39 |

> [!note] No encodings in this trace
> A branch the JIT rewrote in place keeps its key, so the new target
> counts as a second target: the cause of the few conditional, `b` and
> `bl` branches with more than one target (at most 3, 20 and 4; 0.0% of
> them). The 1G v2 window has none.

## Conclusions (provisional, one rubocop run)

- Counted once per branch, targets are close to one: 1.04 per branch
  outside returns in both the 1G window and the 15G run. Weighted by taken
  executions they are 1.22 (1G) and 2.04 (15G), because the few branches
  with many targets are hot; over 15G the hot indirect branches gather
  more targets (indirect jumps 13 → 25, returns 55 → 126 weighted).
- The Ruby interpreter (`bundle`, `gem`, `ruby`) and Python weight to
  4–4.7 targets outside returns against 1.6 for OpenCode and 1.1 for the
  kernel: interpreter dispatch through few indirect branches with many
  targets (not checked against their code).
- Indirect branches are where the targets are: most have one target, but
  the hot ones have many. Weighted by taken executions, an indirect call
  has 6.8 targets and an indirect jump 13. About 45% of indirect-call
  executions and 75% of indirect-jump executions come from branches with
  more than one target, which a BTB entry alone cannot predict.
- Returns average 55 targets weighted by execution (OpenCode 65, docker
  80), against 3.7 per return: hot shared functions with many callers.
  This is the return stack's job, not the BTB's.

## Decisions

- 2026-11-17: targets counted in the footprint pass rather than a separate
  tool, so they share its address spaces, code versions and exec handling;
  one row per static branch in `branches.tsv`, so other weightings need no
  new pass.
- 2026-11-17: averages over branches taken at least once (a never-taken
  branch has no target); both the plain and the weighted means reported,
  weighted by taken and by all executions.
- 2026-11-17: exception entries after a branch are resolved at their
  `eret` (above) rather than dropped. Dropping them would lose the taken
  `bl`s whose target faults, common in short-lived processes.

## Open

- Targets over time: how many of a branch's targets are live within a
  window (what a finite BTB or indirect predictor holds), not over the
  whole run.
- ~~`report.html` does not show the target columns.~~ Done 2026-11-17
  (*Branches* section, per thread).
- Rerun the footprint of the 15G study with the fixed exception rule:
  its *taken ever* counts include branches "taken" only by an exception
  entry (on the 1G window, 0.2% of conditional branches).
