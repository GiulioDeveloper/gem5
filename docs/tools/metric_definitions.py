#!/usr/bin/env python3
"""Write the metric definitions twice from one content list: the wiki page
docs/wiki/infrastructure/metric-definitions.md and the published page
docs/wiki/_publish/metric-definitions.html.

    python3 docs/tools/metric_definitions.py <commit> <build date>

The content is below: edit it here, never in the two outputs. Inline code
is written with backticks in both. Keep it in step with
analysis_scripts/tasktrace/window_view.py (METRICS, topdown, cache_values)
and sweep_summary.py (SWITCHES, SCHED).
"""

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki/infrastructure/metric-definitions.md"
HTML = ROOT / "wiki/_publish/metric-definitions.html"
STYLE_FROM = ROOT / "wiki/_publish/top-down-guide.html"

LEDE = ("How every number in the sweep comparison table and the window view "
        "is computed: which gem5 statistics it reads, the formula, what it "
        "leaves out, and where it can mislead.")

# Prefixes used in the stat columns.
PREFIXES = [
    ("`core.`", "`board.processor.start.core.`"),
    ("`l1i.`, `l1d.`, `l2.`",
     "`board.cache_hierarchy.l1icaches.`, `.l1dcaches.`, `.l2caches.`"),
    ("`::inst`, `::data`",
     "the L2's per-requester value, `::processor.start.core.inst` and "
     "`::processor.start.core.data`: requests that came from the L1I and "
     "from the L1D"),
]

CONVENTIONS = [
    ("Stats blocks and the window value",
     "A run dumps and resets its statistics every `--stats-interval-insts` "
     "instructions (200K in the sweeps), so `stats.txt` holds one block per "
     "interval. A metric's window value is its formula applied to the "
     "statistics summed over all blocks of the detailed window. It is never "
     "the mean of the block values: window IPC is total instructions over "
     "total cycles."),
    ("Instructions (`insts`)",
     "From `intervals.csv`: gem5's committed-instruction count, which on "
     "the O3 core leaves out NOPs and instruction prefetches. "
     "`core.commitStats0.numInsts` includes NOPs (about 2% in one checked "
     "window), so the two are not mixed in one ratio."),
    ("Cycles",
     "`core.numCycles` of the block. It leaves out the time the guest sits "
     "in WFI (those cycles go to `quiesceCycles`). IPC and every per-cycle "
     "share describe the core while it runs, not wall time."),
    ("A statistic gem5 did not print",
     "gem5 leaves a statistic out of a block while it is zero. A missing "
     "statistic reads as 0. A metric none of whose statistics ever appears "
     "is not shown; one that is zero in every block is not shown either, "
     "except the top-down and cache-hierarchy rows."),
    ("PKI",
     "Events per 1000 committed instructions: the summed count × 1000 / "
     "`insts`."),
    ("% cycles",
     "The summed count / `core.numCycles`. For the back-end rows the count "
     "is an event the pipeline bumps once per stalled cycle."),
    ("Wrong-path work",
     "Unless a row says it is counted at commit, it includes instructions "
     "and accesses that were later squashed. Every cache statistic does."),
    ("The comparison table",
     "Per suite, column A is the baseline and the other columns are changes "
     "against it. For rates and counts: the geometric mean of A's window "
     "values, and the geometric mean of each checkpoint's ratio to A, shown "
     "as a change (ratio − 1). A checkpoint where either value is zero has "
     "no ratio and is left out (\"excl. n\"); a mean over fewer than half "
     "the checkpoints is not shown. For the top-down and cache-hierarchy "
     "rows, whose parts add up: the plain mean over checkpoints and the "
     "difference from A, in percentage points or cycles. Plain means are "
     "not weighted by a checkpoint's accesses or instructions."),
    ("Slice categories and edge blocks (agentic)",
     "A category's value uses only the slices of that category. Its cycles "
     "are the slices' simulated time over the clock period, so they include "
     "WFI. Its event counts are shared out from the stats blocks by "
     "instruction overlap, so a short slice inherits part of its "
     "neighbours' events. With edge blocks dropped, every metric is "
     "recomputed over the remaining blocks; around isolated switches only, "
     "a kept block may hold a switch and is shared out the same way."),
    ("Replay infra excluded (agentic default)",
     "By default an agentic value is over every slice but the replay "
     "infra's and the idle task's, computed as for a category: cycles are "
     "simulated time (idle is left out, so WFI is not in them), and the "
     "events of a block shared with infra or idle are shared out by "
     "instruction overlap. With the infra included, it is the whole window "
     "(the core's numCycles, which exclude WFI). The page gives the "
     "coverage: the stats blocks and the share of the work the values are "
     "over."),
]

# (label, key, unit, stats, formula, notes)
GROUPS = [
    ("Throughput", "throughput", [
        ("IPC", "ipc", "insts/cycle", "`core.numCycles`; `insts`",
         "`insts` / `numCycles`",
         "WFI time is not in the cycles. NOPs are not in the instructions."),
        ("User-mode share", "user_share", "% insts",
         "`core.commitStats0.numUserInsts`, `core.commitStats0.numInsts`",
         "`numUserInsts` / `numInsts`",
         "Counted at commit. Both counts include NOPs."),
        ("Fetch rate", "fetch_rate", "insts/cycle",
         "`core.fetchStats0.numInsts`", "`numInsts` fetched / `numCycles`",
         "Wrong-path instructions are included, so it can exceed IPC by "
         "much."),
    ]),
    ("Front end", "frontend", [
        ("L1I misses", "l1i_mpki", "PKI", "`l1i.overallMisses::total`",
         "misses × 1000 / `insts`",
         "Counts fetch requests for a line, not instructions. A request that "
         "joins a miss or prefetch already in flight counts as a miss. "
         "Wrong-path fetches are included."),
        ("iTLB misses", "itlb_mpki", "PKI", "`core.mmu.itb.misses`",
         "misses × 1000 / `insts`",
         "With FDP on this is mostly prefetch lookups: a prefetch "
         "translation that misses is counted and then dropped (median "
         "agentic 37 PKI with FDP, 2.9 without). Compare it only between "
         "runs with the same FDP setting; use completed instruction walks "
         "for the demand side."),
        ("I-cache stall cycles", "icache_stall", "% cycles",
         "`core.fetchStats0.icacheStallCycles`",
         "stall cycles / `numCycles`",
         "Cycles fetch waited on the instruction cache. It is a fetch-stage "
         "count, not a measure of lost throughput."),
    ]),
    ("Bad speculation", "badspec", [
        ("Conditional mispredicts", "br_mpki", "PKI",
         "`core.branchPred.condIncorrect`", "count × 1000 / `insts`",
         "Conditional branches only. Indirect and return mispredicts are "
         "not in it."),
        ("BTB-miss mispredicts", "btb_mispred_pki", "PKI",
         "`core.branchPred.mispredictDueToBTBMiss_0::total`",
         "count × 1000 / `insts`",
         "The plain `btb.misses` statistic is 0 with the decoupled front "
         "end; use this row."),
        ("Squashed per committed", "squashed", "ratio",
         "`core.commit.commitSquashedInsts`, `core.commitStats0.numInsts`",
         "squashed / committed",
         "Instructions squashed in the ROB, over committed instructions "
         "(NOPs included)."),
    ]),
    ("Memory", "memory", [
        ("L1D misses", "l1d_mpki", "PKI", "`l1d.overallMisses::total`",
         "misses × 1000 / `insts`",
         "Every access that did not find its line: new misses, accesses "
         "joining a miss in flight, ownership requests, software "
         "prefetches. Wrong-path loads are included. The *Cache hierarchy* "
         "rows separate these."),
        ("L2 misses", "l2_mpki", "PKI", "`l2.overallMisses::total`",
         "misses × 1000 / `insts`",
         "All requesters: instruction, data, the L1 prefetchers and "
         "page-table walks. Prefetch requests are in it, so it is not a "
         "demand miss rate."),
        ("dTLB misses", "dtlb_mpki", "PKI", "`core.mmu.dtb.misses`",
         "misses × 1000 / `insts`", "L1 data TLB. An L2 TLB hit costs no "
         "time in this model."),
        ("Page-walk requests", "walks_pki", "PKI", "`core.mmu.walker.walks`",
         "requests × 1000 / `insts`",
         "Requests, not walks: includes requests squashed before a walk "
         "started and requests merged into a walk in flight. About 4× the "
         "completed walks."),
        ("Completed page walks (all, data, instruction)",
         "walks_done_pki, walks_done_d_pki, walks_done_i_pki", "PKI",
         "`core.mmu.walker.requestOrigin_Completed::Data`, `::Inst`",
         "completed × 1000 / `insts`", "The walk count to use."),
        ("L1D miss latency, L1I miss latency", "l1d_lat, l1i_lat", "cycles",
         "`l1d.overallMissLatency::total`, `l1d.overallMisses::total` "
         "(`l1i.` likewise); the block's cycles and ticks",
         "(`overallMissLatency` / `overallMisses`) × `numCycles` / ticks",
         "Mean over all misses, joined ones included. The tick-to-cycle "
         "conversion uses `numCycles`, so in a window with WFI the latency "
         "comes out too small (axios-5892 and bat-2835 in the baseline "
         "sweep: 31 and 33 cycles against 65 to 204 for the others). The "
         "AMAT rows convert with the clock period and do not have this "
         "error."),
    ]),
    ("Back end", "backend", [
        ("ROB full", "rob_full", "% cycles", "`core.rename.ROBFullEvents`",
         "events / `numCycles`", "Rename stalls on a full ROB."),
        ("IQ full", "iq_full", "% cycles", "`core.iew.iqFullEvents`",
         "events / `numCycles`", "Dispatch stalls on a full issue queue."),
        ("LSQ full", "lsq_full", "% cycles", "`core.iew.lsqFullEvents`",
         "events / `numCycles`",
         "Dispatch stalls on a full load or store queue."),
    ]),
]

CACHE_INTRO = [
    "Two sides: **instruction** (demand accesses of the L1I: fetch requests "
    "for one line, not instructions) and **data** (demand accesses of the "
    "L1D: loads and stores). Page-table walks go through the MMU cache and "
    "are on neither side.",
    "gem5's classic cache counts a *demand* access as a hit or a miss. A "
    "miss either allocates a miss-status holding register (MSHR) and sends "
    "one request to the level below (an **MSHR miss**, here a *new miss*), "
    "or finds an MSHR already outstanding for its line and waits on it (an "
    "**MSHR hit**, here *in flight*). The outstanding MSHR can belong to an "
    "earlier demand miss or to a prefetch.",
]

CACHE_SYMBOLS = [
    ("`H1`, `M1`", "`demandHits::total`, `demandMisses::total` of the L1I "
     "or L1D"),
    ("`J1`, `N1`", "`demandMshrHits::total` (in flight), "
     "`demandMshrMisses::total` (new misses); `M1` = `J1` + `N1`"),
    ("`T1`", "`demandMissLatency::total`: per missing access, its arrival "
     "at the L1 to its response, summed (ticks)"),
    ("`U1`", "`demandMshrMissLatency::total`: per new miss, its arrival to "
     "the fill, before the L1's response latency (ticks)"),
    ("`h2`, `m2`, `j2`, `n2`, `t2`, `u2`",
     "the same six statistics of the L2 for the side's requester "
     "(`l2.demandHits::inst` or `::data`, and so on)"),
    ("`o2`", "ownership requests the L2 got from the L1D: `l2.InvalidateReq`"
     ", `l2.UpgradeReq` and `l2.SCUpgradeReq`, `.hits::data` + "
     "`.misses::data`"),
    ("`W`, `TW`", "`l1d.WriteLineReq.mshrMisses::total` and "
     "`l1d.WriteLineReq.mshrMissLatency::total`: new L1D misses of stores "
     "that write a whole line"),
    ("`P`", "clock period in ticks: `clock` of `[board.clk_domain]` in "
     "`config.ini` (333)"),
    ("`ℓ1`, `ℓ2`", "hit latency in cycles, from `config.ini`: the larger of "
     "`tag_latency` and `data_latency` (their sum with "
     "`sequential_access`). L1I 1 in these sweeps, L1D 4, L2 11"),
    ("`r1`, `r2`", "`response_latency` of the L1 and the L2 (cycles)"),
    ("`A`", "`H1` + `M1`: the side's demand accesses"),
    ("`R`", "`h2` + `m2` + `o2`: what the L1's new misses became at the L2"),
]

# (label, keys, formula, what it is, leaves out / pitfalls)
CACHE_NODES = [
    ("Served by the L1", "res_l1_i, res_l1_d", "`H1` / `A`",
     "The L1's demand hit rate. Measured.",
     "A line a prefetcher brought in counts as a hit, so with prefetchers "
     "on the hit rate includes their effect."),
    ("In flight to the L1", "res_l1fly_i, res_l1fly_d", "`J1` / `A`",
     "Accesses that missed on a line the L1 was already fetching and "
     "waited for that fill. They make no request to the L2. Measured.",
     "Where the awaited line comes from (L2 or memory) is not known per "
     "access. With prefetchers on these are mostly accesses that arrive "
     "while a prefetch is still under way; the line then appears in no "
     "demand L2 or memory count."),
    ("Served by the L2", "res_l2_i, res_l2_d", "`N1` / `A` × `h2` / `R`",
     "New L1 misses that hit in the L2.",
     "The L1's new misses and the L2's requests are the same requests, "
     "counted on both sides, so the share is exact up to their difference "
     "(see *How exact*)."),
    ("In flight to the L2", "res_l2fly_i, res_l2fly_d",
     "`N1` / `A` × `j2` / `R`",
     "New L1 misses that joined a miss or prefetch the L2 already had "
     "outstanding.",
     "The fill they wait for always comes from memory, so for provenance "
     "read this together with *Served by memory*. Without prefetchers it "
     "is nearly zero, because each L1 already merges its requests per "
     "line. With the L2 prefetcher on it is mostly requests landing on a "
     "prefetch."),
    ("Served by memory", "res_mem_i, res_mem_d", "`N1` / `A` × `n2` / `R`",
     "New L1 misses that were also new L2 misses.", "None beyond the "
     "above."),
    ("Ownership only (data)", "res_own_d", "`N1` / `A` × `o2` / `R`",
     "Stores whose L1D miss moved no data. Either the store, or the stores "
     "waiting on one MSHR together, cover a whole line: the L1D asks only "
     "for ownership (`InvalidateReq`; `DC ZVA`, as memset and the kernel's "
     "page clearing use, is the common source). Or the store hits a line "
     "the L1D holds read-only (`UpgradeReq`).",
     "At the L1D both are counted as ordinary demand misses. At the L2 "
     "neither is a demand request. An invalidation that misses in the L2 "
     "is answered by the memory bus, not by DRAM."),
    ("L2 hit rate", "l2_hit_i, l2_hit_d", "`h2` / (`h2` + `m2`)",
     "Of the L2's demand requests from that side.",
     "Ownership requests are not in it. Requests from the L1 prefetchers "
     "are under their own requester and not in it either."),
    ("AMAT", "amat_i, amat_d",
     "(`A`·`ℓ1` + `T1`/`P` − `M1`·`ℓ1`) / `A`",
     "Average time of a demand access as the L1 sees it: the hit latency "
     "for every access, plus each missing access's measured wait past it.",
     "See *What AMAT leaves out*."),
    ("L1 lookup", "amat_l1_i, amat_l1_d", "`ℓ1`",
     "The configured hit latency.",
     "Assumed, not measured: gem5 prints no hit latency in these runs."),
    ("L1 in flight", "amat_l1fly_i, amat_l1fly_d",
     "(`T1`/`P` − `Tnew` − `J1`·`ℓ1`) / `A`, with `Tnew` = `U1`/`P` + "
     "`N1`·`r1`",
     "The waits of the accesses that joined an outstanding L1 miss or "
     "prefetch. `Tnew` is the time of the new misses: gem5 adds the "
     "response latency to the first access's miss latency but not to the "
     "MSHR's.",
     "Measured, as a difference of two measured sums."),
    ("Memory", "amat_mem_i, amat_mem_d",
     "(`u2`/`P` + `n2`·`r2` − `n2`·`ℓ2`) / `A`",
     "The time the L2's new misses for this side took past the L2's "
     "lookup: what the L2 itself waited on memory.", "Measured at the L2."),
    ("L2 in flight", "amat_l2fly_i, amat_l2fly_d",
     "(`t2`/`P` − `u2`/`P` − `n2`·`r2` − `j2`·`ℓ2`) / `A`",
     "The time requests of this side waited in the L2 on a miss or "
     "prefetch it already had outstanding.", "Measured at the L2."),
    ("Ownership (data)", "amat_own_d",
     "`N1`·`o2`/`R` × (`TW`/`P` + `W`·`r1` − `W`·`ℓ1`) / `W` / `A`",
     "The ownership requests, each at the mean time of a whole-line write "
     "miss of the L1D.",
     "Measured for single whole-line stores (`W`); the same mean is "
     "assumed for stores that only together cover a line and for upgrades "
     "(in gin-2121 without prefetchers `W` is 1.63M of 2.11M ownership "
     "requests). Zero when the window has no whole-line store."),
    ("L2", "amat_l2_i, amat_l2_d",
     "(`Tnew` − `N1`·`ℓ1`) / `A` − memory − L2 in flight − ownership",
     "The rest of the new misses' time: the way from the L1 to the L2 and "
     "back and the L2's lookup, paid by every new miss whether the L2 has "
     "the line or not.",
     "A remainder, so it also holds what the other parts miss. In a single "
     "stats block a request that straddles the block edge can make the "
     "other parts exceed the L1's time; they are then scaled to fit and "
     "this part is 0."),
    ("Blocked (L1I, L1D, L2)", "blk_l1i, blk_l1d, blk_l2",
     "Σ `blockedCycles::no_mshrs`, `::no_targets`, `::no_wbuffers` / "
     "`core.numCycles`",
     "Share of cycles the cache accepted no new request. An access that "
     "arrives then is refused and retried by the core.",
     "Cache clock cycles over core cycles; they differ only in windows "
     "with WFI. The blocked time is a property of the cache, not a wait "
     "per access: it does not say how many accesses were waiting."),
    ("Blocked by cause", "blk_*_mshr, blk_*_tgt, blk_*_wb",
     "`blockedCycles::no_mshrs` (no free MSHR), `::no_targets` (an MSHR's "
     "target list is full: 8 accesses per MSHR in the L1D), "
     "`::no_wbuffers` (no free write buffer), each / `core.numCycles`",
     "The parts of the row above; they add up to it.",
     "gem5 credits a whole blocked period to the cause that clears last, "
     "so a period that began for one cause and ended for another is "
     "counted under the second."),
]

CACHE_EXACT = [
    "**Hits, in-flight and new misses are exact.** `M1` = `J1` + `N1` "
    "holds with no remainder (gin-2121, no prefetch, data: 44,960,829 = "
    "28,167,170 + 16,793,659).",
    "**New L1 misses against L2 requests.** Instruction side: 13,192,502 "
    "new L1I misses, 13,192,327 L2 requests. Data side: 16,793,659 new L1D "
    "misses − 2,078,056 invalidations − 30,999 upgrades + 83,325 atomics, "
    "load-exclusives and software prefetches (not demand at the L1D, "
    "demand reads at the L2) = 14,767,929, against 14,759,278 L2 demand "
    "requests: 0.06% apart.",
    "**The time split.** Fitted per stats block, the L1's new-miss time "
    "equals the L2's own miss latency plus a fixed cost per request: 14.9 "
    "cycles per L2 hit and 2.2 on top of the L2's miss latency per L2 miss "
    "(instruction), 18.2 and 5.1 (loads); the total residual is 0.02% and "
    "0.21% (gin-2121, no prefetch). So *Memory* is what the L2 measured, "
    "and the few cycles of path per L2 miss are in *L2*.",
    "Source of all three: `runs/no-prefetch/reference/"
    "gin-2121-nopf.cache-stats.txt`, summed over "
    "`runs/sweep/20261113-1805-fe8-l1i1-nopf/agentic/gin-2121`.",
]

CACHE_OUT = [
    "**Time before the cache accepts an access.** A miss latency starts "
    "when the cache takes the request. While the L1D is blocked the core "
    "retries, and that wait is in no cache statistic. The *Blocked* rows "
    "show when this matters: the L1D is blocked for 5.9% of cycles on "
    "average in the agentic suite with prefetchers and 12.8% without; in "
    "736.ocio_r, 40% and 82% "
    "(`runs/sweep/20261113-1805-compare-nopf/compare.view.json`). Data "
    "AMAT is understated there.",
    "**Wrong-path accesses are counted** like any other. In gin-2121 "
    "without prefetchers the L1D saw 242.4M load accesses and 224.5M loads "
    "committed, some of which were forwarded from a store and never "
    "reached the cache.",
    "**Forwarded loads are absent.** They make no cache access, so \"per "
    "access\" is not \"per load\".",
    "**Atomics, load-exclusives and software prefetches** are not demand "
    "accesses at the L1D and are not in `A` (1.1M atomic hits against "
    "365.9M demand hits in gin-2121).",
    "**AMAT is not pipeline cost.** Misses overlap. A store accesses the "
    "cache after it commits, so its wait holds a store-queue entry, not "
    "the pipeline; loads and stores are in one data bar.",
    "**Translation time** (TLB misses, page walks) is before the access "
    "and not in it.",
    "**With a perfect L1** the side has no accesses and shows N/A. With a "
    "perfect L2 the parts of the new misses show N/A; the L1 shares and "
    "the AMAT total remain.",
]

TD_INTRO = [
    "Shares of the rename slots (`core.topDown.level1.slots` = rename width "
    "× cycles), recomputed from gem5's counters so they can be summed over "
    "blocks, and checked block by block against gem5's own formulas "
    "(`core.topDown.*`). The reasons, the differences from Yasin's paper "
    "and the known problems are in the Top-Down Guide; only the formulas "
    "are repeated here.",
    "`S` = `core.topDown.level1.slots`; `w` = `S` / `core.topDown.cycles`; "
    "`rn.` = `core.rename.`; `td.` = `core.topDown.`.",
]
TD_ROWS = [
    ("Retiring", "td_retiring", "`core.commitStats0.numOps` / `S`"),
    ("Bad speculation", "td_badspec",
     "(`rn.renamedInsts` − `numOps` + `rn.refillBubbles` + `w` × "
     "`rn.status::Squashing`) / `S`"),
    ("Front-end bound", "td_frontend", "`rn.fetchBubbles` / `S`"),
    ("Back-end bound", "td_backend",
     "1 − retiring − bad speculation − front-end bound"),
    ("Branch mispredicts", "td_bs_branch",
     "bad speculation × `core.iew.branchMispredicts` / "
     "(`branchMispredicts` + `core.iew.memOrderViolationEvents`)"),
    ("Machine clears", "td_bs_clears",
     "bad speculation − branch mispredicts"),
    ("Fetch latency", "td_fe_latency", "`rn.fetchLatencyBubbles` / `S`"),
    ("Branch resteers (part of fetch latency)", "td_fe_resteer",
     "`rn.resteerBubbles` / `S`"),
    ("Fetch bandwidth", "td_fe_bandwidth",
     "front-end bound − fetch latency"),
    ("Serialize", "td_be_serialize",
     "`w` × `rn.status::SerializeStall` / `S`"),
    ("Memory bound", "td_be_memory",
     "(back-end bound − serialize) × (`td.loadStallCycles` + "
     "`td.storeStallCycles`) / `td.execStallCycles`"),
    ("Core bound", "td_be_core",
     "back-end bound − serialize − memory bound"),
    ("L1D bound", "td_mem_l1",
     "memory bound × (`loadStallCycles` − `td.loadStallL1Miss`) / (load + "
     "store stall cycles)"),
    ("L2 bound", "td_mem_l2",
     "memory bound × (`loadStallL1Miss` − `td.loadStallL2Miss`) / (load + "
     "store stall cycles)"),
    ("Past L2", "td_mem_ext",
     "memory bound × `loadStallL2Miss` / (load + store stall cycles)"),
    ("Store bound", "td_mem_store",
     "memory bound × `storeStallCycles` / (load + store stall cycles)"),
]
TD_NOTES = [
    "Runs made before the 2026-11-13 fix report front-end bound too high "
    "and back-end bound too low; do not compare shares across that date.",
    "Memory bound understates what a perfect L1D saves (it predicted +14% "
    "for agentic and +17% for SPEC against +43% and +47% measured).",
    "A split with no events puts its parent's share in its last part.",
]

SCHED_INTRO = (
    "From the guest task trace (`tasktrace.jsonl`), not from gem5 "
    "statistics. Agentic runs only have enough switches to read; the "
    "values are the same at every edge setting.")
SCHED_ROWS = [
    ("Context switches; process, thread, kernel-thread switches",
     "switches, switch_process, switch_thread, switch_kernel",
     "per M insts", "switch events of the trace, by kind",
     "count / (`insts` / 10⁶)",
     "Kind by thread group: another process, another thread of the same "
     "process, or to or from a kernel thread."),
    ("Switch frequency", "switch_khz", "kHz",
     "switch events; the window's ticks",
     "count / milliseconds of simulated time",
     "Per slice category: switches into it over its own time. Simulated "
     "time includes WFI."),
    ("Time between switches", "switch_gap", "µs",
     "switch events; the window's ticks", "simulated time / count",
     "Per slice category: the mean time one of its slices runs."),
    ("Scheduler instructions", "sched_share", "% insts",
     "trace events at `__schedule` and `__switch_to`",
     "instructions between the two / `insts`",
     "The scheduler's direct cost only: not the switch's tail, nor the "
     "trap that led to it."),
    ("Time share, instruction share (per slice category)",
     "time_share", "% time, % insts", "the scheduling slices",
     "the category's ticks (instructions) / the window's",
     "A slice goes to the category of the task switched in. Idle time is "
     "in \"Other\"."),
]


def to_html(text):
    # Code spans first, so emphasis marks inside them stay literal.
    parts = re.split(r"(`[^`]+`)", html.escape(text, quote=False))
    for i, part in enumerate(parts):
        if part.startswith("`"):
            parts[i] = f"<code>{part[1:-1]}</code>"
        else:
            part = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", part)
            parts[i] = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", part)
    return "".join(parts)


def md_cell(text):
    return text.replace("|", "\\|")


def keys_md(keys):
    return ", ".join(f"`{k.strip()}`" for k in keys.split(","))


def write_wiki(date):
    o = []
    a = o.append
    a("---\ntype: entity\nstatus: current\n"
      f"updated: {date}\nsources:\n"
      "  - analysis_scripts/tasktrace/window_view.py\n"
      "  - analysis_scripts/tasktrace/sweep_summary.py\n"
      "  - analysis_scripts/tasktrace/sweep_compare.py\n"
      "  - src/mem/cache/base.cc\n"
      "  - src/mem/cache/cache.cc\n"
      "  - runs/no-prefetch/reference/\n"
      "  - docs/tools/metric_definitions.py\n"
      "tags: [metrics, stats, cache, amat, top-down, sweep, viewer]\n---\n")
    a("# Metric definitions\n")
    a(LEDE + " Generated by `docs/tools/metric_definitions.py`, which also "
      "writes the published page ([[publish]], `metric-definitions`): edit "
      "the content there, not here. The code is `window_view.py` "
      "(`METRICS`, `topdown`, `cache_values`) and `sweep_summary.py`; the "
      "pages that show the metrics are in [[viewers]] and [[sweeps]].\n")
    a("## Conventions\n")
    a("Prefixes in the stat columns:\n")
    for short, full in PREFIXES:
        a(f"- {short}: {full}")
    a("")
    for head, body in CONVENTIONS:
        a(f"- **{head}.** {body}")
    a("\nRelated: [[aggregating-metrics]], [[instruction-counts]], "
      "[[numcycles-excludes-wfi]], [[o3-wrong-path-counting]], "
      "[[comparing-configurations]].\n")
    for title, _, rows in GROUPS[:4]:
        a(f"## {title}\n")
        a("| metric | key | unit | gem5 stats | formula | leaves out, "
          "pitfalls |\n|---|---|---|---|---|---|")
        for label, key, unit, stats, formula, notes in rows:
            a("| " + " | ".join(md_cell(x) for x in (
                label, keys_md(key), unit, stats, formula, notes)) + " |")
        a("")
    a("Pitfall pages: [[fdp-inflates-itlb-misses]], "
      "[[walk-requests-vs-completed]], [[btb-miss-stat-zero-decoupled]].\n")
    a("## Cache hierarchy\n")
    for p in CACHE_INTRO:
        a(p + "\n")
    a("Symbols (statistics summed over the window; `1` is the side's L1, "
      "`2` the L2):\n")
    a("| symbol | meaning |\n|---|---|")
    for s, m in CACHE_SYMBOLS:
        a(f"| {md_cell(s)} | {md_cell(m)} |")
    a("")
    a("| metric | key | formula | what it is | leaves out, pitfalls |\n"
      "|---|---|---|---|---|")
    for label, keys, formula, what, notes in CACHE_NODES:
        a("| " + " | ".join(md_cell(x) for x in (
            label, keys_md(keys), formula, what, notes)) + " |")
    a("\nThe served-from rows add up to 100% and the AMAT parts to AMAT.\n")
    a("### How exact\n")
    for p in CACHE_EXACT:
        a(f"- {p}")
    a("\n### What AMAT leaves out\n")
    for p in CACHE_OUT:
        a(f"- {p}")
    a("")
    title, _, rows = GROUPS[4]
    a(f"## {title}\n")
    a("| metric | key | unit | gem5 stats | formula | leaves out, "
      "pitfalls |\n|---|---|---|---|---|---|")
    for label, key, unit, stats, formula, notes in rows:
        a("| " + " | ".join(md_cell(x) for x in (
            label, keys_md(key), unit, stats, formula, notes)) + " |")
    a("\n## Top-down\n")
    for p in TD_INTRO:
        a(p.replace("the Top-Down Guide", "[[top-down-accounting]]") + "\n")
    a("| metric | key | formula |\n|---|---|---|")
    for label, key, formula in TD_ROWS:
        a(f"| {label} | `{key}` | {md_cell(formula)} |")
    a("")
    for p in TD_NOTES:
        a(f"- {p}")
    a("\nEvidence for the notes: [[2026-11-13-top-down-microbenchmarks]], "
      "[[2026-11-12-spec-400m-sweeps]].\n")
    a("## Scheduling (agentic)\n")
    a(SCHED_INTRO + "\n")
    a("| metric | key | unit | source | formula | notes |\n"
      "|---|---|---|---|---|---|")
    for label, key, unit, src, formula, notes in SCHED_ROWS:
        a("| " + " | ".join(md_cell(x) for x in (
            label, keys_md(key), unit, src, formula, notes)) + " |")
    a("\n## Not on the comparison page\n")
    a("`window_view.METRICS` also defines issue rate, BTB misses, FTQ "
      "full, decode blocked, all mispredicts, fetch squashing, "
      "memory-order violations, rename blocked, registers full, LQ and SQ "
      "occupancy and the Garfield shares. They appear in the window view "
      "only and are described there by their tooltips.\n")
    WIKI.write_text("\n".join(o))


def table(head, rows, cls=""):
    out = ['<div class="tablewrap"><table' + (f' class="{cls}"' if cls else "")
           + "><thead><tr>"]
    out += [f"<th>{html.escape(h)}</th>" for h in head]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def keys_html(keys):
    return " ".join(f"<code>{html.escape(k.strip())}</code>"
                    for k in keys.split(","))


def simple_group(rows):
    return "".join(
        f'<div class="node"><h3>{html.escape(label)}</h3>'
        f'<div class="ids">{keys_html(key)} · {html.escape(unit)}</div><dl>'
        f"<dt>Stats</dt><dd>{to_html(stats)}</dd>"
        f"<dt>Formula</dt><dd>{to_html(formula)}</dd>"
        f'<dt class="pit">Notes</dt><dd>{to_html(notes)}</dd></dl></div>'
        for label, key, unit, stats, formula, notes in rows)


def write_html(commit, date):
    src = STYLE_FROM.read_text()
    style = src[src.index("<style>"):src.index("</style>") + len("</style>")]
    links = src[src.index("<link"):src.index("<style>")]
    toc = [("conv", "Conventions")]
    toc += [(a, t) for t, a, _ in GROUPS[:4]]
    toc += [("cache", "Cache hierarchy"), ("exact", "How exact"),
            ("out", "What AMAT leaves out"), ("backend", "Back end"),
            ("td", "Top-down"), ("sched", "Scheduling"), ("code", "Code")]
    o = []
    a = o.append
    a("<title>Metric Definitions</title>\n"
      '<meta name="claude:viewport-fit-sides" content="cover">\n'
      + links + style)
    a('<div class="wrap"><nav class="toc" aria-label="Contents">'
      '<div class="label">Contents</div><ol>'
      + "".join(f'<li><a href="#{i}">{html.escape(t)}</a></li>'
                for i, t in toc) + "</ol></nav><main><div class=\"doc\">")
    a('<header class="masthead"><div class="eyebrow">gem5 fork · branch '
      "gfdev · sweep comparison and window view</div>"
      "<h1>Metric Definitions</h1>"
      f'<p class="lede">{html.escape(LEDE)}</p>'
      f'<div class="build">Built from the project wiki on {date} from the '
      f"tree at {html.escape(commit)}. Source: docs/wiki/infrastructure/"
      "metric-definitions.md (content in docs/tools/metric_definitions.py)."
      " The code that computes the metrics: analysis_scripts/tasktrace/"
      "window_view.py and sweep_summary.py. This page is generated: fix "
      "the content, then rebuild.</div></header>")
    a('<h2 id="conv">Conventions</h2>')
    a("<p>Statistic names are shortened with these prefixes.</p>")
    a(table(["Written", "Stands for"],
            [(to_html(s), to_html(f)) for s, f in PREFIXES]))
    for head, body in CONVENTIONS:
        a(f"<h3>{to_html(head)}</h3><p>{to_html(body)}</p>")
    for title, anchor, rows in GROUPS[:4]:
        a(f'<h2 id="{anchor}">{html.escape(title)}</h2>')
        a(simple_group(rows))
    a('<h2 id="cache">Cache hierarchy</h2>')
    for p in CACHE_INTRO:
        a(f"<p>{to_html(p)}</p>")
    a("<h3>Symbols</h3><p>Statistics summed over the window; "
      "<code>1</code> is the side's L1, <code>2</code> the L2.</p>")
    a(table(["Symbol", "Meaning"],
            [(to_html(s), to_html(m)) for s, m in CACHE_SYMBOLS]))
    a('<div class="tree">access ─┬─ L1 hit ............................ '
      "L1\n"
      "         └─ L1 miss ─┬─ joins an outstanding L1 MSHR ... L1 in "
      "flight\n"
      "                     └─ new miss, one request to the L2\n"
      "                          ├─ L2 hit ................... L2\n"
      "                          ├─ joins an outstanding L2 MSHR  L2 in "
      "flight\n"
      "                          ├─ new L2 miss .............. memory\n"
      '                          └─ <span class="m">no data needed (data '
      "side)</span> ... ownership</div>")
    a("<h3>Served from</h3><p>Shares of the side's demand accesses. They "
      "add up to 100%.</p>")
    for label, keys, formula, what, notes in CACHE_NODES:
        if label == "AMAT":
            a("<h3>Access time</h3><p>In core cycles per demand access. "
              "The parts add up to AMAT.</p>")
        if label.startswith("Blocked (L1I"):
            a("<h3>Blocked cycles</h3>")
        a(f'<div class="node"><h3>{html.escape(label)}</h3>'
          f'<div class="ids">{keys_html(keys)}</div><dl>'
          f"<dt>Formula</dt><dd>{to_html(formula)}</dd>"
          f"<dt>What</dt><dd>{to_html(what)}</dd>"
          f'<dt class="pit">Notes</dt><dd>{to_html(notes)}</dd></dl></div>')
    a('<h2 id="exact">How exact</h2><ul>'
      + "".join(f"<li>{to_html(p)}</li>" for p in CACHE_EXACT) + "</ul>")
    a('<h2 id="out">What AMAT leaves out</h2><ul>'
      + "".join(f"<li>{to_html(p)}</li>" for p in CACHE_OUT) + "</ul>")
    title, anchor, rows = GROUPS[4]
    a(f'<h2 id="{anchor}">{html.escape(title)}</h2>')
    a(simple_group(rows))
    a('<h2 id="td">Top-down</h2>')
    for p in TD_INTRO:
        a(f"<p>{to_html(p)}</p>")
    a(table(["Metric", "Key", "Formula"],
            [(html.escape(lab), f"<code>{k}</code>", to_html(f))
             for lab, k, f in TD_ROWS]))
    a('<div class="note"><strong>Reading rules.</strong><ul>'
      + "".join(f"<li>{to_html(p)}</li>" for p in TD_NOTES) + "</ul></div>")
    a('<h2 id="sched">Scheduling</h2>')
    a(f"<p>{to_html(SCHED_INTRO)}</p>")
    a(simple_group(SCHED_ROWS))
    a('<h2 id="code">Code</h2>')
    a(table(["What", "Where"], [
        ("Metric list and formulas",
         "<code>analysis_scripts/tasktrace/window_view.py</code>: "
         "<code>METRICS</code>, <code>topdown()</code>, "
         "<code>cache_values()</code>, <code>blocked_metrics()</code>"),
        ("Cycle conversions of the cache statistics",
         "<code>window_view.py</code>: <code>derive_cache_stats()</code>"),
        ("Rows shown, switch metrics, slice categories",
         "<code>analysis_scripts/tasktrace/sweep_summary.py</code>"),
        ("Aggregates of the comparison table",
         "<code>analysis_scripts/tasktrace/sweep_compare.py</code>"),
        ("gem5's cache statistics",
         "<code>src/mem/cache/base.cc</code> (definitions), "
         "<code>src/mem/cache/cache.cc</code> (miss requests, latencies)"),
        ("A reference set of the cache statistics",
         "<code>runs/no-prefetch/reference/</code>"),
    ]))
    a("<footer>Generated from the project wiki. Numbers quoted on this "
      "page are from single runs and sweeps named beside them; they are "
      "examples, not results.</footer></div></main></div>")
    HTML.write_text("\n".join(o) + "\n")


if __name__ == "__main__":
    write_wiki(sys.argv[2])
    write_html(sys.argv[1], sys.argv[2])
    print(WIKI, HTML)
