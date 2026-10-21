---
type: pitfall
status: current
updated: 2026-10-21
sources:
  - "[[legacy-log/research-log/agentic/2026-10-16-infinite-btb]]"
  - "[[legacy-log/garfield/infinite-btb]]"
tags: [btb, stats, front-end]
---

# In decoupled mode `btb.misses` is always 0

**The trap:** with the [[decoupled-front-end]], BAC calls the BTB's
`lookup` only after `valid` has found the branch, so `btb.lookups` equals
hits and **`btb.misses` stays 0, for every BTB type**. A missed branch never
reaches `lookup`: fetch meets it at predecode with no history and BAC makes
a not-taken placeholder.

**Use instead:** `branchPred.mispredictDueToBTBMiss_0` (the placeholder
was wrong; the cost-relevant one), `branchPred.BTBMispredicted`, and the
unconditional types of `bac.noHistByType` ([[btb]]). With `--disable-fdp`
`btb.misses` is meaningful (fmt-3901: 42.4M over 400M instructions).

**Where it still bites:** `window_view.py`'s "BTB misses" row (`btb_mpki`
from `btb.misses`) reads 0 on decoupled runs. The sweep's `btb_mispred_pki`
and `trace_analysis.py`'s `btb_mpki` use `mispredictDueToBTBMiss` and are
right. Open decision: [[questions]].

**Second lesson:** an earlier note claimed all three `branchPred` stats
were 0 too. That was generalised from the first two of 2,000 blocks of one
run, which happened to be 0; summed over the run, redis had 667K BTB-miss
mispredicts. Check a stat over a whole run before declaring it broken.
