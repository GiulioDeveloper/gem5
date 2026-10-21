---
type: meta
status: current
updated: 2026-10-21
---

# Wiki schema

How this knowledge base is laid out and maintained. It follows the LLM-wiki
pattern ([[raw/llm-wiki]]): raw sources stay immutable, the LLM writes and
maintains the wiki, and this file is the contract between the two. The user
and the LLM change this file together when a convention stops working.

## Layers (the Obsidian vault is `docs/`)

| folder | owner | editable | what it holds |
|---|---|---|---|
| `docs/raw/` | user | **never** (append new files only) | external sources: papers (`papers/`), snapshots of external docs (`external/`), the llm-wiki note |
| `docs/legacy-log/` | frozen | **never** | the pre-wiki notebooks: research logs, Garfield docs, specs/plans, the old tracing guide, commit notes. Historic record, *not* strict truth: claims there may be stale or wrong. See [[legacy-log/README]] |
| `docs/wiki/` | LLM | yes (by the LLM) | everything below |

Code, run scripts and analysis scripts stay in the repo tree; wiki pages
describe them and point at them by path (`src/cpu/pred/infinite_btb.cc`).
Run outputs live in `runs/` (gitignored, local to the host): cite them by
path, knowing they are not versioned.

## Wiki folders

| folder | page type | one page per |
|---|---|---|
| `overview.md` | overview | — the current thesis on agentic-workload CPU behaviour |
| `questions.md` | overview | — open questions and candidate experiments |
| `workloads/` | entity | workload suite or notable workload (agentic suite, SPEC CPU 2026, outlier tasks) |
| `hardware/` | entity / concept | modelled structure or mechanism (Neoverse V2 config, decoupled front end, BTB, TLBs, InfiniteBTB) |
| `infrastructure/` | howto / entity | tool or workflow we built (task tracer, trace format, sweeps, viewers, checkpoints) |
| `experiments/` | experiment | study or sweep: question, setup, results, conclusions, run paths |
| `findings/` | finding | cross-cutting claim with its evidence ("agentic windows are front-end bound") |
| `methodology/` | method | how we measure (windows, warm-up, aggregation, validation checks) |
| `pitfalls/` | pitfall | simulator or analysis trap that has bitten us or would |
| `gem5/` | gem5 | gem5 itself: building, testing, SimObjects, code generation, core, ISAs, memory |
| `garfield/` | garfield | reference: one synthesis page per Garfield stage plus lessons learned |

Special files: `index.md` (catalog), `log.md` (timeline), `publish.md`
(registry of human-facing outputs), this `SCHEMA.md`.

## Page conventions

- **File names** are kebab-case and unique across the vault, so a bare
  `[[name]]` resolves (`hardware/infinite-btb.md` → `[[infinite-btb]]`).
- **Frontmatter** on every page:

  ```yaml
  ---
  type: overview | entity | concept | howto | experiment | finding | method | pitfall | gem5 | garfield | meta
  status: current | draft | open | superseded
  updated: 2026-10-21          # date of the last content change
  sources:                     # what the page rests on
    - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
    - runs/sweep/20261019-compare-5way/
  tags: [front-end, btb]
  ---
  ```

- **Links** are Obsidian wikilinks: `[[page]]`, `[[page#Heading]]`,
  `[[page|text]]`. Link to legacy and raw files by vault path:
  `[[legacy-log/garfield/README]]`. Link generously: the first mention of
  any concept that has (or deserves) a page is a link. A link to a page that
  does not exist yet is allowed; it marks a gap for lint to report.
- **Lead with the answer.** The first paragraph says what the page
  concludes or what the thing is; detail and history follow.
- **Every number has a source**: a wiki experiment page, a legacy or raw
  file, a `runs/` path or a commit. Say when a number is from one window or
  one checkpoint.
- **Contradictions are flagged, never silently resolved**:

  ```markdown
  > [!conflict] ROB size
  > [[legacy-log/research-log/MRN/2026-07-26-value-file-rendezvous]] says 512,
  > `configs/garfield/arm/neoverse_v2.py` sets 320. The config is authoritative.
  ```

- **Superseded claims stay, marked**: `> [!superseded] by [[page]] (date)`,
  with a line on why. Pages are not deleted; a superseded page gets
  `status: superseded` and a pointer to its replacement.
- **Interpretation is labelled** as such ("not verified", "likely"), apart
  from what a run measured.
- Keep pages focused: split a page when it covers two things a reader would
  look up separately. Prefer tables for results.

## Findings are provisional

`findings/` pages (and the thesis in `overview.md`) are **working
hypotheses**, not established facts. They rest on a few sweeps, often one
window per checkpoint, and are expected to change. Rules:

- Every finding page opens with the *Provisional finding* callout, states
  its claim, its confidence and the reason, and lists its caveats.
- Readers (including other agents) must not cite a finding as truth: check
  the experiment pages and runs behind it, and say how strong it is.
- When new data disagrees, update the finding (or mark it superseded) in the
  same piece of work, and log it. Weakening a finding is as valuable as
  strengthening one.
- Experiment pages record what was measured; findings interpret it. Keep
  the two apart.

## Experiment pages

New studies are recorded here, not in dated notebooks. One page per study
in `experiments/`, named `<yyyy-mm-dd>-<slug>.md` (start date), with these
sections:

1. **Question** — what it measures and why.
2. **Setup** — config flags, checkpoints, window sizes, commit, run paths.
3. **Results** — tables; each figure with its run path.
4. **Conclusions** — what changed in our understanding; link the
   findings pages that were created or updated.
5. **Decisions** — design choices made along the way, newest last, each
   with its reason.
6. **Open** — what is left; mirror it into `questions.md`.

The page is updated as the study runs; `log.md` holds the timeline.

## Operations

### Ingest (a new source, a finished run, or legacy material)

1. Read the source; discuss the key takeaways with the user when the source
   is substantial.
2. Write or update the primary page (experiment, entity, howto, ...).
3. Update every page the source touches: findings, pitfalls, methodology,
   hardware, workloads, `overview.md`, `questions.md`. Flag conflicts.
4. Update `index.md` and append a `log.md` entry.
5. Run lint (below) and fix what it reports for the touched pages.

### Query

Read `index.md`, then the relevant pages; answer with `[[links]]` as
citations. If the answer is a reusable synthesis (a comparison, an analysis,
a new connection), file it as a page and log it.

### Lint

`python3 docs/tools/wiki_lint.py` reports broken links, orphan pages,
missing or malformed frontmatter, pages missing from `index.md`, links into
`legacy-log/` that do not resolve, and stale published outputs. Then the LLM
reviews by reading: contradictions between pages, claims superseded by newer
results, concepts mentioned on several pages without their own page, gaps
worth an experiment. Log each lint pass.

### Publish (human-facing material)

The wiki is written for the LLM to maintain; people get generated outputs.
Outputs are **HTML artifacts**, built from a named set of wiki pages and
never edited by hand: fixes go into the wiki, then the output is rebuilt.

1. Pick or add an entry in `publish.md`: name, audience, source pages.
2. Read the source pages and write one linear, self-contained document for
   that audience (a user guide, a findings report, ...). The page states
   which wiki pages and which commit it was built from, and the build date.
3. Write the HTML to `docs/wiki/_publish/<name>.html` (tracked: it is the
   build record) and publish it with the Artifact tool. Rebuilding from the
   same file path, or passing the recorded URL, keeps the link stable.
4. Update the entry in `publish.md` (URL, built date, commit) and log it.

Lint flags an output as stale when one of its source pages has an `updated`
date after the output's build date.

## log.md format

Append-only, newest last. Each entry starts with

```
## [yyyy-mm-dd] <kind> | <title>
```

where `<kind>` is one of `ingest`, `experiment`, `query`, `lint`,
`publish`, `restructure`, `fix`. The body lists the pages created or
changed and anything the user decided. `grep '^## \[' docs/wiki/log.md`
gives the timeline.

## Commits

Commit messages are the per-commit record (no commit notes since
2026-10-21). A commit that changes behaviour the wiki describes updates the
affected pages in the same commit, or the next one with a log entry.
