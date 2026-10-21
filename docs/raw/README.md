---
type: meta
status: current
updated: 2026-10-21
---

# raw: immutable sources

External source material that the wiki is built from. **Never edit a file
here.** Add new ones and ingest them ([[SCHEMA#Ingest (a new source, a finished run, or legacy material)]]).

| folder | what goes here |
|---|---|
| `papers/` | papers and articles (PDF or clipped markdown), named `<year>-<first-author>-<short-title>.<ext>` |
| `external/` | dated snapshots of documents that live outside this repo, such as the agentic checkpoint README in `/home/snapshots/gem5-ckpts/` or gem5-infra notes, named `<yyyy-mm-dd>-<what>.md` |
| `llm-wiki.md` | the LLM-wiki pattern this knowledge base follows |
