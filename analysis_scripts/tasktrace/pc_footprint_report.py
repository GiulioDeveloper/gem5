"""Per-thread code footprint report: one self-contained HTML page from a
pc_footprint.py output directory (threads.csv and thread_hist.tsv).

usage:
  python3 analysis_scripts/tasktrace/pc_footprint_report.py <run>/footprint
      [-o report.html]

pc_footprint.py writes it at the end of every pass. One row per thread:
instructions and code size (distinct 64-byte lines), each split between
user and kernel mode, the code against the L1I and L2 sizes (user plus
kernel, user only or kernel only), the code as a multiple of each size, the repeat
distance per instruction address and per line (median to 99th percentile),
and distinct branches by type. The code size, distinct instructions and
branches can be shown over the whole stream or per bin of 100M, 500M or
1G instructions (thread_bins.csv: the mean over the thread's bins, cut by
its own instructions or by the run's), with a plot of how they grow with
the bin size. Below: the miss ratio curves (the share of
accesses whose repeat distance is at least x, which is the miss ratio of a
fully associative LRU cache of x) of the threads picked in the rows, and a
sortable table of every number. Processes can be hidden by name. No network access needed except for fonts.
"""

import argparse
import csv
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load(out):
    from pc_footprint import BRANCHES, LINE, ends, firsts, key_of, \
        load_caches, thread_hists, thread_label
    with open(out / "threads.csv") as f:
        rows = list(csv.DictReader(f))
    hists = thread_hists(out)
    caches = load_caches(out)
    keys = [key_of(label) for label, _ in caches]

    def num(x):
        return None if x in ("", None) else float(x)

    threads = []
    for r in rows:
        tid = int(r["thread"])
        t = {"id": tid, "pid": int(r["pid"]), "tgid": int(r["tgid"]),
             "process": r["process"], "comm": r["comm"],
             "kthread": int(r["kthread"]),
             "label": thread_label({"kthread": int(r["kthread"]),
                                    "comm": r["comm"],
                                    "process": r["process"],
                                    "pid": r["pid"]}),
             "insts": int(r["insts"]), "k_insts": int(r["k_insts"]),
             "uniq_insts": int(r["uniq_insts"]),
             "u_uniq_insts": int(r["u_uniq_insts"]),
             "k_uniq_insts": int(r["k_uniq_insts"]),
             "code_kib": float(r["code_kib"]),
             "u_code_kib": float(r["u_code_kib"]),
             "k_code_kib": float(r["k_code_kib"]),
             "accesses": int(r["line_accesses"]),
             "pc_cold": num(r["pc_cold_pct"]),
             "line_cold": num(r["line_cold_pct"]),
             "x": [num(r[f"x_{k}"]) for k in keys],
             "hit": [num(r[f"priv_hit_pct_{k}"]) for k in keys],
             "mpki": [num(r[f"priv_mpki_{k}"]) for k in keys],
             "smpki": [num(r[f"shared_mpki_{k}"]) for k in keys],
             "br": [int(r[f"br_{b}"]) for b in BRANCHES],
             "brt": [int(r[f"br_{b}_taken"]) for b in BRANCHES],
             "k_br": int(r["k_branches"]),
             "h": {v: hists.get(tid, {}).get(v, []) for v in ("pc", "line")}}
        threads.append(t)
    # Per bin: {cut: {label: values}}, from thread_bins.csv when present.
    bins, sizes = {}, {}
    if (out / "thread_bins.csv").exists():
        with open(out / "thread_bins.csv") as f:
            for r in csv.DictReader(f):
                # Means, rounded to keep the page small. The largest bin
                # is per value: user and kernel maxima can be different bins.
                v = {k: round(float(r[k]), 1) for k in (
                    "code_kib", "u_code_kib", "k_code_kib", "uniq_insts",
                    "u_uniq_insts", "k_uniq_insts", "branches",
                    "branches_taken")}
                v.update({"n": int(r["bins"]), "p": int(r["partial_only"]),
                          "w": int(r["insts"]),
                          "br": [round(float(r[f"br_{b}"]), 1)
                                 for b in BRANCHES],
                          "max_u_kib": int(r["max_u_lines"]) * LINE / 1024,
                          "max_k_kib": int(r["max_k_lines"]) * LINE / 1024,
                          "max_br": int(r["max_branches"])})
                v["branchesTaken"] = v.pop("branches_taken")
                bins.setdefault(int(r["thread"]), {}).setdefault(
                    r["cut"], {})[r["bin"]] = v
                sizes[r["bin"]] = int(r["bin_insts"])
    for t in threads:
        t["b"] = bins.get(t["id"], {})
    meta = {"bins": [{"label": k, "insts": v} for k, v in
                     sorted(sizes.items(), key=lambda kv: kv[1])],
            # end: the smallest or largest of its level (labelled on the
            # axes); first: the smallest of its level.
            "caches": [{"label": label, "level": label.split(" ")[0],
                        "size": label.split(" ")[1], "bytes": size,
                        "lines": size // LINE, "end": c in ends(caches),
                        "first": c in firsts(caches)}
                       for c in caches for label, size in [c]],
            "branches": list(BRANCHES),
            # Baseline BTB (NeoverseV2_BTB): entries are installed for
            # taken branches only, so it compares with distinct taken ones.
            "btb_entries": 12 * 1024}
    return meta, threads


def write_report(out, path=None):
    out = Path(out)
    path = Path(path) if path else out / "report.html"
    meta, threads = load(out)
    run = out.resolve().parent
    meta["run"] = f"{run.parent.name}/{run.name}"
    meta["insts"] = sum(t["insts"] for t in threads)
    data = json.dumps({"meta": meta, "threads": threads},
                      separators=(",", ":")).replace("</", "<\\/")
    page = (TEMPLATE.replace("@@TITLE@@",
                             html.escape(f"{meta['run']} thread footprint"))
            .replace("@@DATA@@", data))
    path.write_text(page)
    print(path, file=sys.stderr)
    return path


TEMPLATE = r"""<title>@@TITLE@@</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Layout: a header with the run's totals, then one aligned row per thread
   (a strip of small charts on shared axes), the miss ratio curves of the
   picked threads, and the full table. */
:root {
  --bg: #fbfbfa; --surface: #ffffff; --ink: #121417; --ink-2: #50545b;
  --ink-3: #868a91; --rule: #e4e5e7; --grid: #eceded; --hover: #f2f4f7;
  --pick: #e9f1fc;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100;
  --s5: #e87ba4; --s6: #008300; --s7: #6250d6; --s8: #e34948;
  --cool: #2a78d6; --warm: #d03b3b; --mid: #f0efec; --dot: #2a78d6;
  --font: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161718; --surface: #1c1d1f; --ink: #eeeff0; --ink-2: #b4b7bc;
    --ink-3: #82868c; --rule: #2e3033; --grid: #26282a; --hover: #232528;
    --pick: #1d2a3b;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
    --s5: #d55181; --s6: #008300; --s7: #9085e9; --s8: #e66767;
    --cool: #3987e5; --warm: #e66767; --mid: #383835; --dot: #5598e7;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #161718; --surface: #1c1d1f; --ink: #eeeff0; --ink-2: #b4b7bc;
  --ink-3: #82868c; --rule: #2e3033; --grid: #26282a; --hover: #232528;
  --pick: #1d2a3b;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
  --s5: #d55181; --s6: #008300; --s7: #9085e9; --s8: #e66767;
  --cool: #3987e5; --warm: #e66767; --mid: #383835; --dot: #5598e7;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font: 14px/1.45 var(--font);
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 24px 48px; }
main { max-width: 1680px; margin: 0 auto; display: grid; gap: 28px; }
h1 { font-size: 22px; font-weight: 600; margin: 0; text-wrap: balance; }
h2 { font-size: 16px; font-weight: 600; margin: 0 0 4px; }
p { margin: 0; max-width: 72ch; color: var(--ink-2); }
.mono, .num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
header { display: grid; gap: 8px; }
.eyebrow { font: 500 11px/1 var(--mono); letter-spacing: .08em;
  text-transform: uppercase; color: var(--ink-3); }
.totals { display: flex; flex-wrap: wrap; gap: 6px 24px; color: var(--ink-2); }
.totals b { color: var(--ink); font-weight: 500; font-family: var(--mono); }
.controls { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; }
.controls label { display: flex; gap: 6px; align-items: center; color: var(--ink-2); font-size: 13px; }
select, input[type=search] { font: 13px var(--font); color: var(--ink);
  background: var(--surface); border: 1px solid var(--rule); border-radius: 6px;
  padding: 5px 8px; }
input[type=search] { width: 200px; }
select:focus-visible, input:focus-visible, button:focus-visible,
tr:focus-visible { outline: 2px solid var(--s1); outline-offset: 1px; }
.scroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: 8px;
  background: var(--surface); }
section { display: grid; gap: 10px; min-width: 0; }
table { border-collapse: collapse; width: 100%; }
.strip th { font: 500 11px/1.3 var(--font); color: var(--ink-2); text-align: left;
  vertical-align: bottom; padding: 10px 8px 4px; white-space: nowrap;
  border-bottom: 1px solid var(--rule); background: var(--surface);
  position: sticky; top: 0; z-index: 1; }
.strip td { padding: 3px 8px; border-bottom: 1px solid var(--grid);
  white-space: nowrap; vertical-align: middle; }
.strip tbody tr { cursor: pointer; }
.strip tbody tr:hover { background: var(--hover); }
.strip tbody tr.picked { background: var(--pick); }
.who { display: flex; gap: 8px; align-items: center; max-width: 280px; }
.who span { overflow: hidden; text-overflow: ellipsis; }
.swatch { width: 10px; height: 10px; border-radius: 3px; flex: none;
  border: 1px solid var(--rule); }
.k { color: var(--ink-3); font-size: 12px; }
.cells { display: flex; gap: 2px; }
.cell { width: 46px; height: 20px; border-radius: 3px; display: grid;
  place-items: center; font: 11px var(--mono); font-variant-numeric: tabular-nums; }
.cellhead { width: 46px; text-align: center; font: 500 10px var(--mono); }
svg { display: block; overflow: visible; }
svg text { font: 10px var(--mono); fill: var(--ink-3); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px;
  color: var(--ink-2); }
.legend span { display: inline-flex; gap: 5px; align-items: center; }
.legend i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.curves { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr));
  gap: 16px; }
.panel { background: var(--surface); border: 1px solid var(--rule);
  border-radius: 8px; padding: 12px 12px 8px; display: grid; gap: 6px; min-width: 0; }
.panel h3 { margin: 0; font-size: 13px; font-weight: 600; }
.panel .note { font-size: 12px; color: var(--ink-3); }
.full th { font: 500 11px/1.3 var(--font); color: var(--ink-2); padding: 8px 8px;
  text-align: right; white-space: nowrap; border-bottom: 1px solid var(--rule);
  cursor: pointer; user-select: none; position: sticky; top: 0; background: var(--surface); }
.full th:first-child, .full td:first-child { text-align: left; }
.full th[aria-sort] { color: var(--ink); }
.full td { padding: 3px 8px; text-align: right; border-bottom: 1px solid var(--grid);
  font: 12px var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
.full td:first-child { font-family: var(--font); }
.full tbody tr:hover { background: var(--hover); }
.fullwrap { max-height: 70vh; overflow: auto; }
details.procs { border: 1px solid var(--rule); border-radius: 8px; background: var(--surface);
  padding: 8px 12px; }
details.procs summary { cursor: pointer; color: var(--ink-2); font-size: 13px; }
details.procs summary b { color: var(--ink); font-weight: 500; }
.chiprow { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.chip { font: 12px var(--font); color: var(--ink); background: var(--surface);
  border: 1px solid var(--rule); border-radius: 999px; padding: 3px 10px; cursor: pointer;
  display: inline-flex; gap: 6px; align-items: baseline; }
.chip .k { font-size: 11px; font-family: var(--mono); }
.chip[aria-pressed="false"] { color: var(--ink-3); text-decoration: line-through;
  background: var(--bg); border-style: dashed; }
.chip:hover { border-color: var(--ink-3); }
.chip.act { font-weight: 500; }
.split { display: inline-flex; width: 44px; height: 6px; border-radius: 3px; overflow: hidden;
  vertical-align: middle; gap: 1px; background: var(--surface); }
.split i { display: block; height: 100%; }
.short { font: 10px var(--mono); color: var(--ink-3); border: 1px dashed var(--ink-3);
  border-radius: 3px; padding: 0 3px; flex: none; }
select:disabled { color: var(--ink-3); }
#tip { position: fixed; pointer-events: none; z-index: 20; background: var(--surface);
  color: var(--ink); border: 1px solid var(--rule); border-radius: 6px;
  box-shadow: 0 4px 16px rgb(0 0 0 / .12); padding: 8px 10px; font-size: 12px;
  line-height: 1.5; max-width: 340px; }
#tip b { font-weight: 600; }
#tip .num { font-size: 11.5px; }
#tip table td { padding: 0 6px 0 0; }
@media (prefers-reduced-motion: no-preference) { .strip tbody tr { transition: background .12s; } }
</style>

<main>
  <header>
    <div class="eyebrow">Instruction footprint per thread · PC trace</div>
    <h1 id="title"></h1>
    <div class="totals" id="totals"></div>
    <p>Each thread's committed stream on its own: its user code plus the kernel code
      run while it was current. Cache comparisons are fully associative LRU,
      instruction lines only, no prefetch. Code size, distinct instructions and branches
      can be taken over the whole stream or per bin of N instructions, averaged over
      the bins: the bins are cut by the thread's own instructions (the same amount of
      work for every thread) or by the run's (fixed windows, as a sweep window sees
      them). Repeat distances and misses are always over the whole stream.
      Click rows to compare their curves below.</p>
  </header>

  <section>
    <div class="controls">
      <label for="sortBy">Order by
        <select id="sortBy">
          <option value="insts">instructions</option>
          <option value="code_kib">code size</option>
          <option value="branches">distinct branches</option>
          <option value="mpki0">misses at the first cache</option>
          <option value="pc90">repeat distance, 90th pct</option>
        </select></label>
      <label for="topN">Show
        <select id="topN">
          <option value="25">top 25</option>
          <option value="50" selected>top 50</option>
          <option value="100">top 100</option>
          <option value="all">all</option>
        </select></label>
      <label for="filter">Filter
        <input type="search" id="filter" placeholder="process or thread name"></label>
      <label for="codeMode">Code counted
        <select id="codeMode">
          <option value="all">user + kernel</option>
          <option value="u">user only</option>
          <option value="k">kernel only</option>
        </select></label>
      <label for="binSize">Footprint over
        <select id="binSize"><option value="whole">whole stream</option></select></label>
      <label for="binCut">bins cut by
        <select id="binCut">
          <option value="own">thread's own instructions</option>
          <option value="run">run windows</option>
        </select></label>
      <label for="minInsts">At least
        <select id="minInsts">
          <option value="0">any</option>
          <option value="1e6" selected>1M instructions</option>
          <option value="1e8">100M instructions</option>
        </select></label>
    </div>
    <details class="procs" id="procBox">
      <summary>Processes: <b id="procSummary"></b></summary>
      <div class="chiprow">
        <button type="button" class="chip act" id="procAll">Show all</button>
        <button type="button" class="chip act" id="procNone">Hide all</button>
      </div>
      <div class="chiprow" id="procChips"></div>
    </details>
    <div class="scroll"><table class="strip" id="strip"></table></div>
    <div class="legend" id="stripLegend"></div>
  </section>

  <section>
    <h2>Footprint growth with the bin size</h2>
    <p>The picked threads' code size and distinct taken branches per bin, averaged over
      the bins, against the bin size; the last point is the whole stream (the thread's
      instructions when cut by its own count, the run's when cut by run windows). A flat
      line is a program whose code is all in use at any time; a rising one keeps
      reaching new code as it runs. Threads shorter than a bin have no point at it.</p>
    <div class="legend" id="growLegend"></div>
    <div class="curves">
      <div class="panel"><h3>Code size</h3>
        <div class="note" id="growCodeNote"></div>
        <svg id="growCode" viewBox="0 0 560 300" role="img" aria-label="Code size per bin against the bin size"></svg></div>
      <div class="panel"><h3>Distinct taken branches</h3>
        <div class="note">line: the baseline BTB's entries (installed for taken branches only)</div>
        <svg id="growBr" viewBox="0 0 560 300" role="img" aria-label="Distinct taken branches per bin against the bin size"></svg></div>
    </div>
  </section>

  <section>
    <h2>Miss ratio curves</h2>
    <p>Share of accesses whose repeat distance is at least <i>x</i>: the miss
      ratio of a fully associative LRU cache holding <i>x</i> instructions or lines.
      The floor on the right is first-time accesses (cold). Vertical lines: the cache
      sizes, in instructions (4 bytes each) or 64-byte lines.</p>
    <div class="legend" id="curveLegend"></div>
    <div class="curves">
      <div class="panel"><h3>Per instruction address</h3>
        <div class="note">x: distinct instructions since the same PC last committed</div>
        <svg id="curvePc" viewBox="0 0 560 300" role="img" aria-label="Miss ratio by repeat distance per instruction"></svg></div>
      <div class="panel"><h3>Per 64-byte line</h3>
        <div class="note">x: distinct lines since the same line was last fetched</div>
        <svg id="curveLine" viewBox="0 0 560 300" role="img" aria-label="Miss ratio by repeat distance per line"></svg></div>
    </div>
  </section>

  <section>
    <h2>All numbers</h2>
    <p>The threads above, every column. Click a heading to sort. MPKI: misses per
      1,000 instructions of the thread, private (the thread alone in the cache) or
      shared (the whole interleaved stream). Repeat distance in distinct instructions or lines.</p>
    <div class="scroll fullwrap"><table class="full" id="full"></table></div>
  </section>
</main>
<div id="tip" hidden></div>
<script type="application/json" id="data">@@DATA@@</script>
<script>
(() => {
const D = JSON.parse(document.getElementById('data').textContent);
const M = D.meta, CAPS = M.caches, BR = M.branches;
const SLOTS = ['--s1','--s2','--s3','--s4','--s5','--s6','--s7','--s8'];
const BRLABEL = {cond:'conditional', direct:'direct b', call:'call bl',
  indirect_call:'indirect call', indirect_jump:'indirect jump',
  return:'return', exception_return:'eret'};
const $ = id => document.getElementById(id);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// ---- numbers ----------------------------------------------------------
const fmtInt = n => Math.round(n).toLocaleString('en-US');
function fmtCount(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'G';
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e5 ? 0 : 1) + 'K';
  return String(Math.round(n));
}
function fmtKib(k) {
  if (k >= 1024) return (k / 1024).toFixed(k >= 10240 ? 1 : 2) + ' MiB';
  return k.toFixed(k >= 100 ? 0 : 1) + ' KiB';
}
const fmtX = x => x == null ? '' : x >= 10 ? x.toFixed(0) + '×' : x >= 1 ? x.toFixed(1) + '×' : x.toFixed(2) + '×';
const fmtD = d => d == null ? 'cold' : fmtCount(d);
const f2 = x => x == null ? '' : x.toFixed(2);

// Quantile of the repeat distance d, log-interpolated in its bucket
// (bucket b: d + 1 in [2^(b-1), 2^b)); null when it falls among the cold.
function quant(h, total, p) {
  let need = p * total, cum = 0;
  for (const [b, n] of h) {
    if (cum + n >= need) return 2 ** (b - 1) * 2 ** ((need - cum) / n) - 1;
    cum += n;
  }
  return null;
}
// Miss ratio at capacity 2^b (share of accesses with d + 1 >= 2^b), one
// point per bucket boundary, starting at capacity 1.
function curve(h, total) {
  const pts = [[1, 1]]; let cum = 0;
  for (const [b, n] of h) { cum += n; pts.push([2 ** b, 1 - cum / total]); }
  return pts;
}
for (const t of D.threads) {
  t.branches = t.br.reduce((a, b) => a + b, 0);
  t.branchesTaken = t.brt.reduce((a, b) => a + b, 0);
  t.q = {};
  for (const [v, tot] of [['pc', t.insts], ['line', t.accesses]])
    t.q[v] = [0.5, 0.9, 0.99].map(p => quant(t.h[v], tot, p));
  t.mpki0 = t.mpki[0];
  t.pc90 = t.q.pc[1] == null ? Infinity : t.q.pc[1];
}

// Footprint values over the whole stream; per bin they come from t.b.
for (const t of D.threads)
  t.W = {code_kib: t.code_kib, u_code_kib: t.u_code_kib, k_code_kib: t.k_code_kib,
    uniq_insts: t.uniq_insts, u_uniq_insts: t.u_uniq_insts, k_uniq_insts: t.k_uniq_insts,
    br: t.br, branches: t.branches, branchesTaken: t.branchesTaken, n: null, p: 0};
const BINS = M.bins || [];
document.querySelector('#sortBy [value=mpki0]').textContent = 'misses at ' + CAPS[0].label;
$('binSize').innerHTML += BINS.map(b => `<option value="${b.label}">${b.label} bins</option>`).join('');
const binned = () => $('binSize').value !== 'whole';
// The footprint values shown: whole stream, or the mean over the bins.
function act(t) {
  if (!binned()) return t.W;
  const c = t.b[$('binCut').value];
  return (c && c[$('binSize').value]) || t.W;
}
const binDesc = () => binned()
  ? `mean per ${$('binSize').value} (${$('binCut').value === 'own' ? 'own' : 'run'} bins)`
  : 'whole stream';

// ---- state --------------------------------------------------------------
const picked = new Map();          // thread id -> slot index
function pick(id) {
  if (picked.has(id)) { picked.delete(id); return; }
  if (picked.size >= SLOTS.length) return;
  const used = new Set(picked.values());
  picked.set(id, [...SLOTS.keys()].find(i => !used.has(i)));
}
[...D.threads].sort((a, b) => b.insts - a.insts).slice(0, 4).forEach(t => pick(t.id));
let fullSort = {key: 'instructions', dir: -1};
// Hidden process names; kernel threads are one entry.
const KTHREADS = '[kernel threads]';
const procOf = t => t.kthread ? KTHREADS : t.process;
let hidden = new Set();
// Code size, distinct instructions and footprint multiples in the chosen mode.
const MODES = {all: ['code_kib', 'uniq_insts'], u: ['u_code_kib', 'u_uniq_insts'],
               k: ['k_code_kib', 'k_uniq_insts']};
const codeKib = t => act(t)[MODES[$('codeMode').value][0]];
const codeInsts = t => act(t)[MODES[$('codeMode').value][1]];
const codeXs = t => { const k = codeKib(t); return CAPS.map(c => k ? k / (c.bytes / 1024) : null); };
const modeLabel = () => ({all: 'user + kernel', u: 'user', k: 'kernel'})[$('codeMode').value];
function prefs() { try { return JSON.parse(localStorage.getItem('fpView') || '{}'); } catch { return {}; } }
function savePrefs() {
  try { localStorage.setItem('fpView', JSON.stringify({sortBy: $('sortBy').value,
    topN: $('topN').value, minInsts: $('minInsts').value, codeMode: $('codeMode').value,
    binSize: $('binSize').value, binCut: $('binCut').value,
    hidden: [...hidden]})); } catch {}
}
const p0 = prefs();
for (const k of ['sortBy', 'topN', 'minInsts', 'codeMode', 'binSize', 'binCut'])
  if (p0[k] && [...$(k).options].some(o => o.value === p0[k])) $(k).value = p0[k];
$('binCut').disabled = !binned();
if (Array.isArray(p0.hidden)) hidden = new Set(p0.hidden);

function visible() {
  const f = $('filter').value.trim().toLowerCase();
  const min = +$('minInsts').value;
  return D.threads.filter(t => t.insts >= min && !hidden.has(procOf(t)) &&
    (!f || t.label.toLowerCase().includes(f)));
}
function shown() {
  const key = $('sortBy').value, n = $('topN').value;
  const val = key === 'code_kib' ? codeKib : key === 'branches' ? t => act(t).branches : t => t[key];
  const v = visible().sort((a, b) => (val(b) - val(a)) || (b.insts - a.insts));
  return n === 'all' ? v : v.slice(0, +n);
}

// ---- process filter ------------------------------------------------------
const PROCS = (() => {
  const m = new Map();
  for (const t of D.threads) {
    const p = procOf(t), e = m.get(p) || {name: p, threads: 0, insts: 0};
    e.threads++; e.insts += t.insts; m.set(p, e);
  }
  return [...m.values()].sort((a, b) => b.insts - a.insts);
})();
function renderProcs() {
  $('procChips').innerHTML = PROCS.map(p =>
    `<button type="button" class="chip" data-proc="${esc(p.name)}" aria-pressed="${!hidden.has(p.name)}"
      title="${p.threads} threads, ${fmtInt(p.insts)} instructions">${esc(p.name)}
      <span class="k">${fmtCount(p.insts)}</span></button>`).join('');
  const off = PROCS.filter(p => hidden.has(p.name));
  $('procSummary').textContent = off.length
    ? `${PROCS.length - off.length} of ${PROCS.length} shown; hidden: ${off.slice(0, 6).map(p => p.name).join(', ')}${off.length > 6 ? ', …' : ''}`
    : `all ${PROCS.length} shown`;
}
function procsChanged() { savePrefs(); renderProcs(); renderStrip(); renderFull(); }
$('procChips').addEventListener('click', e => {
  const b = e.target.closest('[data-proc]'); if (!b) return;
  const n = b.dataset.proc;
  hidden.has(n) ? hidden.delete(n) : hidden.add(n);
  procsChanged();
});
$('procAll').addEventListener('click', () => { hidden.clear(); procsChanged(); });
$('procNone').addEventListener('click', () => { hidden = new Set(PROCS.map(p => p.name)); procsChanged(); });

// ---- strip: one row per thread -------------------------------------------
const LOG = (lo, hi, w) => v => Math.max(0, Math.min(w, (Math.log2(Math.max(v, lo)) - Math.log2(lo)) / (Math.log2(hi) - Math.log2(lo)) * w));
const W = 200, H = 20;
const capKib = CAPS.map(c => c.bytes / 1024);
const capPc = CAPS.map(c => c.bytes / 4);
const capLine = CAPS.map(c => c.lines);
// The axes reach at least twice the largest cache.
const codeX = LOG(4, Math.max(65536, 2 * Math.max(...capKib)), W);    // KiB
const PC_MAX = Math.max(2 ** 25, 2 * Math.max(...capPc));
const LINE_MAX = Math.max(2 ** 22, 2 * Math.max(...capLine));
const pcX = LOG(1, PC_MAX, W);                    // distinct instructions + 1
const lineX = LOG(1, LINE_MAX, W);                // distinct lines + 1
// Labelled: the smallest and largest of each level; on the narrow row
// axes, the smallest of each level and the largest overall.
const TICK = new Set(CAPS.flatMap((c, i) => c.end ? [i] : []));
const bigCap = capKib.indexOf(Math.max(...capKib));
const TICK_ROW = new Set(CAPS.flatMap((c, i) => c.first || i === bigCap ? [i] : []));
// "L1I 64K / 512K, L2 2M / 16M" for the given caches.
const capList = pick => [...new Set(CAPS.map(c => c.level))].map(lv => {
  const cs = CAPS.filter(c => c.level === lv && pick(c));
  return cs.length ? `${lv} ${cs.map(c => c.size).join(' / ')}` : '';
}).filter(Boolean).join(', ');

function gridLines(xs, scale) {
  return xs.map((v, i) => `<line x1="${scale(v)}" x2="${scale(v)}" y1="0" y2="${H}" stroke="var(--rule)" stroke-width="1" ${TICK.has(i) ? '' : 'stroke-dasharray="2 2"'}/>`).join('');
}
function axisSvg(xs, scale, unit) {
  const labels = xs.map((v, i) => TICK_ROW.has(i) ? `<text x="${scale(v)}" y="11" text-anchor="middle">${CAPS[i].size}</text>` : '').join('');
  return `<svg width="${W}" height="16" viewBox="0 0 ${W} 16" aria-hidden="true">${labels}<text x="0" y="11" text-anchor="start" style="fill:var(--ink-2)">${unit}</text></svg>`;
}
// User code (blue) and kernel code (orange) as dots, their sum as a tick;
// the mode picks which of them are drawn.
function codeSvg(t) {
  const mode = $('codeMode').value, a = act(t);
  const dot = (kib, col) => kib > 0
    ? `<circle cx="${codeX(kib)}" cy="${H/2}" r="4.5" fill="var(${col})" stroke="var(--surface)" stroke-width="2"/>` : '';
  const xt = codeX(a.code_kib);
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" data-tip="code" data-id="${t.id}">
    ${gridLines(capKib, codeX)}
    <line x1="0" x2="${codeX(codeKib(t))}" y1="${H/2}" y2="${H/2}" stroke="var(--grid)" stroke-width="2"/>
    ${mode === 'all' ? `<line x1="${xt}" x2="${xt}" y1="${H/2-7}" y2="${H/2+7}" stroke="var(--ink)" stroke-width="2"/>` : ''}
    ${mode !== 'u' ? dot(a.k_code_kib, '--s2') : ''}${mode !== 'k' ? dot(a.u_code_kib, '--s1') : ''}
    <rect width="${W}" height="${H}" fill="transparent"/></svg>`;
}
function splitBar(u, k) {
  const tot = u + k || 1;
  return `<span class="split" aria-hidden="true"><i style="width:${u / tot * 100}%;background:var(--s1)"></i><i style="width:${k / tot * 100}%;background:var(--s2)"></i></span>`;
}
function distSvg(t, v, scale, caps) {
  const [p50, p90, p99] = t.q[v];
  const end = d => d == null ? W : scale(d + 1);
  const a = end(p50), b = end(p90), c = end(p99);
  const cold = p99 == null;
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" data-tip="${v}" data-id="${t.id}">
    ${gridLines(caps, scale)}
    <line x1="${b}" x2="${c}" y1="${H/2}" y2="${H/2}" stroke="var(--ink-3)" stroke-width="2" ${cold ? 'stroke-dasharray="3 2"' : ''}/>
    <line x1="${c}" x2="${c}" y1="${H/2-4}" y2="${H/2+4}" stroke="var(--ink-3)" stroke-width="2"/>
    <rect x="${a}" y="${H/2-5}" width="${Math.max(2, b - a)}" height="10" rx="3" fill="var(--s1)" fill-opacity=".85"/>
    <line x1="${a}" x2="${a}" y1="${H/2-7}" y2="${H/2+7}" stroke="var(--ink)" stroke-width="2"/>
    <rect width="${W}" height="${H}" fill="transparent"/></svg>`;
}
function brSvg(t, max) {
  const BW = 180; let x = 0, segs = '';
  act(t).br.forEach((n, i) => {
    if (!n) return;
    const w = n / max * BW;
    segs += `<rect x="${x}" y="4" width="${Math.max(w - (w > 3 ? 2 : 0), 0.8)}" height="12" fill="var(${SLOTS[i]})"/>`;
    x += w;
  });
  return `<svg width="${BW}" height="${H}" viewBox="0 0 ${BW} ${H}" data-tip="br" data-id="${t.id}">${segs}<rect width="${BW}" height="${H}" fill="transparent"/></svg>`;
}
// Fit: code / cache size, diverging around 1 (blue fits, red exceeds).
function fitCell(x) {
  const s = Math.max(-1, Math.min(1, Math.log2(x) / 6));
  const pct = Math.round(Math.abs(s) * 85);
  const col = s < 0 ? 'var(--cool)' : 'var(--warm)';
  const ink = pct > 50 ? '#fff' : 'var(--ink)';
  return `<div class="cell" style="background:color-mix(in oklab, ${col} ${pct}%, var(--mid));color:${ink}">${fmtX(x)}</div>`;
}

function renderStrip() {
  const rows = shown();
  const max = Math.max(1, ...rows.map(t => act(t).branches));
  const head = `<thead><tr>
    <th>Thread<br><span class="k">process thread (pid)</span></th>
    <th style="text-align:right">Instructions<br><span class="k">user · kernel</span></th>
    <th style="text-align:right">Code size<br><span class="k">user · kernel, ${binDesc()}</span></th>
    <th>${axisSvg(capKib, codeX, 'KiB')}</th>
    <th><div class="cells">${CAPS.map(c => `<div class="cellhead">${c.label.replace(' ', '<br>')}</div>`).join('')}</div>
      <span class="k">${modeLabel()} code ÷ cache size</span></th>
    <th>Repeat distance, per instruction (whole stream)<br>${axisSvg(capPc, pcX, '')}</th>
    <th>Repeat distance, per line<br>${axisSvg(capLine, lineX, '')}</th>
    <th>Distinct branches by type<br><span class="k">scale: ${fmtInt(max)} at full width</span></th>
    <th style="text-align:right">Branches<br><span class="k">taken</span></th>
  </tr></thead>`;
  const body = rows.map(t => {
    const slot = picked.get(t.id);
    const sw = slot == null ? 'transparent' : `var(${SLOTS[slot]})`;
    const a = act(t);
    const short = binned() && a.p ? `<span class="short" title="shorter than one ${$('binSize').value} bin: values of its one partial bin, the whole stream">&lt;${$('binSize').value}</span>` : '';
    return `<tr data-id="${t.id}" tabindex="0" class="${slot == null ? '' : 'picked'}" aria-selected="${slot != null}">
      <td><div class="who"><i class="swatch" style="background:${sw}"></i><span title="${esc(t.label)}">${esc(t.label)}</span>${short}</div></td>
      <td class="num" style="text-align:right" data-tip="insts" data-id="${t.id}">${fmtCount(t.insts - t.k_insts)} <span class="k">·</span> ${fmtCount(t.k_insts)} ${splitBar(t.insts - t.k_insts, t.k_insts)}</td>
      <td class="num" style="text-align:right" data-tip="code" data-id="${t.id}">${fmtKib(a.u_code_kib)} <span class="k">·</span> ${fmtKib(a.k_code_kib)}</td>
      <td>${codeSvg(t)}</td>
      <td><div class="cells">${codeXs(t).map(x => x == null ? '<div class="cell"></div>' : fitCell(x)).join('')}</div></td>
      <td>${distSvg(t, 'pc', pcX, capPc)}</td>
      <td>${distSvg(t, 'line', lineX, capLine)}</td>
      <td>${brSvg(t, max)}</td>
      <td class="num" style="text-align:right">${fmtCount(a.branches)} <span class="k">${fmtCount(a.branchesTaken)}</span></td>
    </tr>`;
  }).join('');
  $('strip').innerHTML = head + `<tbody>${body}</tbody>`;
  const n = visible().length;
  $('stripLegend').innerHTML =
    `<span>${rows.length} of ${n} threads shown${hidden.size ? ` (${hidden.size} processes hidden)` : ''}.</span>` +
    `<span><svg width="44" height="12"><rect x="12" y="1" width="18" height="10" rx="3" fill="var(--s1)" fill-opacity=".85"/><line x1="12" x2="12" y1="0" y2="12" stroke="var(--ink)" stroke-width="2"/><line x1="30" x2="42" y1="6" y2="6" stroke="var(--ink-3)" stroke-width="2"/><line x1="42" x2="42" y1="2" y2="10" stroke="var(--ink-3)" stroke-width="2"/></svg>repeat distance: median, box to 90th, whisker to 99th percentile (dashed: past the cold misses)</span>` +
    `<span><i style="background:var(--s1)"></i>user</span><span><i style="background:var(--s2)"></i>kernel</span>` +
    `<span><svg width="10" height="12"><line x1="5" x2="5" y1="0" y2="12" stroke="var(--ink)" stroke-width="2"/></svg>user + kernel code</span>` +
    `<span>gridlines: ${capList(() => true)}</span>` +
    (binned() ? `<span><span class="short">&lt;${$('binSize').value}</span> shorter than one bin</span>` : '') +
    BR.map((b, i) => `<span><i style="background:var(${SLOTS[i]})"></i>${BRLABEL[b]}</span>`).join('');
}

// ---- curves -----------------------------------------------------------------
const CW = 560, CH = 300, PAD = {l: 58, r: 12, t: 10, b: 34};
const YMIN = 1e-5;
function curveSvg(el, v) {
  const xmax = v === 'pc' ? PC_MAX : LINE_MAX;
  const sx = x => PAD.l + Math.log2(Math.max(1, x)) / Math.log2(xmax) * (CW - PAD.l - PAD.r);
  const sy = y => PAD.t + (Math.log10(1) - Math.log10(Math.max(YMIN, y))) / (0 - Math.log10(YMIN)) * (CH - PAD.t - PAD.b);
  const caps = v === 'pc' ? capPc : capLine;
  let g = '';
  for (let e = 0; e >= -5; e--) {
    const y = sy(10 ** e);
    g += `<line x1="${PAD.l}" x2="${CW - PAD.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/>`;
    g += `<text x="${PAD.l - 6}" y="${y + 3}" text-anchor="end">${['100%','10%','1%','0.1%','0.01%','0.001%'][-e]}</text>`;
  }
  caps.forEach((c, i) => {
    const x = sx(c);
    g += `<line x1="${x}" x2="${x}" y1="${PAD.t}" y2="${CH - PAD.b}" stroke="var(--rule)" ${TICK.has(i) ? '' : 'stroke-dasharray="3 3"'}/>`;
    if (TICK.has(i)) g += `<text x="${x}" y="${CH - PAD.b + 26}" text-anchor="middle">${CAPS[i].size}</text>`;
  });
  for (let e = 0; e <= Math.log2(xmax); e += 4)
    g += `<text x="${sx(2 ** e)}" y="${CH - PAD.b + 13}" text-anchor="middle">${fmtCount(2 ** e)}</text>`;
  const sel = [...picked.entries()].map(([id, slot]) => [D.threads.find(t => t.id === id), slot]).filter(([t]) => t);
  let lines = '';
  for (const [t, slot] of sel) {
    const pts = curve(t.h[v], v === 'pc' ? t.insts : t.accesses);
    const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join('');
    const last = pts[pts.length - 1];
    lines += `<path d="${d}L${sx(xmax).toFixed(1)},${sy(last[1]).toFixed(1)}" fill="none" stroke="var(${SLOTS[slot]})" stroke-width="2" stroke-linejoin="round"/>`;
  }
  el.innerHTML = g + lines +
    `<line id="${el.id}X" x1="0" x2="0" y1="${PAD.t}" y2="${CH - PAD.b}" stroke="var(--ink-3)" visibility="hidden"/>` +
    `<rect x="${PAD.l}" y="${PAD.t}" width="${CW - PAD.l - PAD.r}" height="${CH - PAD.t - PAD.b}" fill="transparent" data-curve="${v}"/>`;
  el._scale = {sx, xmax, sel, v};
}
function renderCurves() {
  curveSvg($('curvePc'), 'pc');
  curveSvg($('curveLine'), 'line');
  const sel = [...picked.entries()];
  $('curveLegend').innerHTML = sel.length
    ? sel.map(([id, slot]) => `<span><i style="background:var(${SLOTS[slot]})"></i>${esc(D.threads.find(t => t.id === id).label)}</span>`).join('')
    : '<span>Click thread rows above to draw their curves (up to 8).</span>';
}

// ---- footprint growth --------------------------------------------------------
// One line per picked thread: the mean per bin at each bin size it filled,
// then the whole stream, at x = the thread's instructions (own cut) or the
// run's (run windows).
function growPoints(t, key) {
  const cut = $('binCut').value, c = t.b[cut] || {};
  const pts = BINS.filter(b => c[b.label] && !c[b.label].p).map(b => [b.insts, c[b.label][key], b.label]);
  pts.push([cut === 'own' ? t.insts : M.insts, t.W[key], 'whole']);
  return pts.filter(([x, y]) => y > 0).sort((a, b) => a[0] - b[0]);
}
function growSvg(el, key, ylo, yhi, refs) {
  const xlo = 1e6, xhi = 1e11;
  const sx = x => PAD.l + (Math.log10(Math.max(xlo, x)) - 6) / 5 * (CW - PAD.l - PAD.r);
  const sy = y => PAD.t + (Math.log10(yhi) - Math.log10(Math.max(ylo, Math.min(yhi, y)))) / (Math.log10(yhi) - Math.log10(ylo)) * (CH - PAD.t - PAD.b);
  const pow10 = ['1', '10', '100', '1K', '10K', '100K', '1M', '10M', '100M', '1G', '10G', '100G'];
  const yt = key === 'code_kib'
    ? [[1, '1 KiB'], [16, '16 KiB'], [256, '256 KiB'], [4096, '4 MiB'], [65536, '64 MiB']]
    : [1, 2, 3, 4, 5, 6, 7].map(e => [10 ** e, pow10[e]]).filter(([v]) => v >= ylo && v <= yhi);
  let g = '';
  for (const [v, label] of yt) {
    g += `<line x1="${PAD.l}" x2="${CW - PAD.r}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--grid)"/>`;
    g += `<text x="${PAD.l - 6}" y="${sy(v) + 3}" text-anchor="end">${label}</text>`;
  }
  for (let e = 6; e <= 11; e++)
    g += `<text x="${sx(10 ** e)}" y="${CH - PAD.b + 13}" text-anchor="middle">${pow10[e]}</text>`;
  BINS.forEach((b, i) => {   // labels alternate in height: the bins sit close together
    g += `<line x1="${sx(b.insts)}" x2="${sx(b.insts)}" y1="${PAD.t}" y2="${CH - PAD.b}" stroke="var(--rule)" stroke-dasharray="3 3"/>` +
      `<text x="${sx(b.insts) + 3}" y="${PAD.t + 9 + (i % 2) * 12}" text-anchor="start">${b.label}</text>`;
  });
  for (const [v, label] of refs)
    g += `<line x1="${PAD.l}" x2="${CW - PAD.r}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--ink-3)" stroke-dasharray="4 3"/>` +
      `<text x="${CW - PAD.r - 2}" y="${sy(v) - 3}" text-anchor="end">${label}</text>`;
  g += `<text x="${(PAD.l + CW - PAD.r) / 2}" y="${CH - PAD.b + 28}" text-anchor="middle" style="fill:var(--ink-2)">instructions per bin (whole stream: all of them)</text>`;
  let marks = '';
  for (const [id, slot] of picked) {
    const t = D.threads.find(t => t.id === id); if (!t) continue;
    const pts = growPoints(t, key), col = `var(${SLOTS[slot]})`;
    marks += `<path d="${pts.map(([x, y], i) => `${i ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join('')}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>`;
    marks += pts.map(([x, y, l]) => `<circle cx="${sx(x)}" cy="${sy(y)}" r="${l === 'whole' ? 4.5 : 3.5}" fill="${l === 'whole' ? 'var(--surface)' : col}" stroke="${col}" stroke-width="2" data-grow="${id}|${l}|${key}"/>`).join('');
  }
  el.innerHTML = g + marks;
}
function renderGrowth() {
  const has = BINS.length > 0;
  growSvg($('growCode'), 'code_kib', 1, 65536,
    CAPS.filter(c => c.end).map(c => [c.bytes / 1024, c.first ? c.label : c.size]));
  $('growCodeNote').textContent = `user + kernel, KiB; lines: ${capList(c => c.end)}`;
  growSvg($('growBr'), 'branchesTaken', 10, 1e7, [[M.btb_entries, `BTB ${fmtCount(M.btb_entries)}`]]);
  $('growLegend').innerHTML = !has ? '<span>No bins in this output (rerun pc_footprint.py).</span>'
    : `<span>${$('binCut').value === 'own' ? "bins cut by the thread's own instructions" : 'bins cut by run windows'} (switch above)</span>` +
      `<span><svg width="12" height="12"><circle cx="6" cy="6" r="4" fill="var(--surface)" stroke="var(--ink-2)" stroke-width="2"/></svg>whole stream</span>` +
      [...picked.entries()].map(([id, slot]) => `<span><i style="background:var(${SLOTS[slot]})"></i>${esc(D.threads.find(t => t.id === id).label)}</span>`).join('');
}

// ---- full table -----------------------------------------------------------
const COLS = [
  ['thread', t => t.label, t => t.label],
  ['process', t => procOf(t), t => procOf(t)],
  ['instructions', t => t.insts, t => fmtInt(t.insts)],
  ['user insts', t => t.insts - t.k_insts, t => fmtInt(t.insts - t.k_insts)],
  ['kernel insts', t => t.k_insts, t => fmtInt(t.k_insts)],
  ['kernel %', t => t.k_insts / t.insts, t => (t.k_insts / t.insts * 100).toFixed(1)],
  ['bins', t => binned() ? act(t).n + (act(t).p ? 0.5 : 0) : 0, t => !binned() ? '' : act(t).p ? 'partial' : String(act(t).n)],
  ['distinct insts', t => act(t).uniq_insts, t => fmtInt(act(t).uniq_insts)],
  ['user distinct', t => act(t).u_uniq_insts, t => fmtInt(act(t).u_uniq_insts)],
  ['kernel distinct', t => act(t).k_uniq_insts, t => fmtInt(act(t).k_uniq_insts)],
  ['code KiB', t => act(t).code_kib, t => fmtInt(act(t).code_kib)],
  ['user KiB', t => act(t).u_code_kib, t => fmtInt(act(t).u_code_kib)],
  ['kernel KiB', t => act(t).k_code_kib, t => fmtInt(act(t).k_code_kib)],
  ...CAPS.map((c, i) => ['× ' + c.label, t => act(t).code_kib * 1024 / c.bytes, t => fmtX(act(t).code_kib * 1024 / c.bytes)]),
  ...CAPS.map((c, i) => ['user × ' + c.label, t => act(t).u_code_kib * 1024 / c.bytes, t => fmtX(act(t).u_code_kib * 1024 / c.bytes)]),
  ['whole code KiB', t => t.code_kib, t => fmtInt(t.code_kib)],
  ...CAPS.map((c, i) => ['MPKI ' + c.label, t => t.mpki[i], t => f2(t.mpki[i])]),
  ...CAPS.flatMap((c, i) => c.first ? [['shared MPKI ' + c.label, t => t.smpki[i], t => f2(t.smpki[i])]] : []),
  ['cold MPKI', t => t.line_cold * t.accesses / t.insts * 10, t => f2(t.line_cold * t.accesses / t.insts * 10)],
  ...['p50', 'p90', 'p99'].map((p, i) => ['inst dist ' + p, t => t.q.pc[i] ?? Infinity, t => fmtD(t.q.pc[i])]),
  ...['p50', 'p90', 'p99'].map((p, i) => ['line dist ' + p, t => t.q.line[i] ?? Infinity, t => fmtD(t.q.line[i])]),
  ['branches', t => act(t).branches, t => fmtInt(act(t).branches)],
  ['taken', t => act(t).branchesTaken, t => fmtInt(act(t).branchesTaken)],
  ['kernel branches (whole)', t => t.k_br, t => fmtInt(t.k_br)],
  ...BR.map((b, i) => [BRLABEL[b], t => act(t).br[i], t => fmtInt(act(t).br[i])]),
  ...BR.map((b, i) => [BRLABEL[b] + ' taken (whole)', t => t.brt[i], t => fmtInt(t.brt[i])]),
];
function renderFull() {
  const ci = COLS.findIndex(c => c[0] === fullSort.key);
  const get = COLS[ci][1];
  const rows = visible().sort((a, b) => {
    const x = get(a), y = get(b);
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * fullSort.dir;
  });
  $('full').innerHTML = `<thead><tr>${COLS.map(c => `<th data-key="${esc(c[0])}"${c[0] === fullSort.key ? ` aria-sort="${fullSort.dir > 0 ? 'ascending' : 'descending'}"` : ''}>${esc(c[0])}${c[0] === fullSort.key ? (fullSort.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>` +
    `<tbody>${rows.map(t => `<tr>${COLS.map(c => `<td>${esc(c[2](t))}</td>`).join('')}</tr>`).join('')}</tbody>`;
}
$('full').addEventListener('click', e => {
  const th = e.target.closest('th'); if (!th) return;
  const k = th.dataset.key;
  fullSort = {key: k, dir: fullSort.key === k ? -fullSort.dir : (k === 'thread' ? 1 : -1)};
  renderFull();
});

// ---- tooltips ----------------------------------------------------------------
const tip = $('tip');
function tipFor(kind, t) {
  const head = `<b>${esc(t.label)}</b><br>`;
  const a = act(t);
  const binNote = !binned() ? 'whole stream'
    : a.p ? `shorter than one ${$('binSize').value} bin: its partial bin (${fmtCount(a.w)} instructions)`
    : `mean over ${a.n} ${$('binSize').value} bins (${$('binCut').value === 'own' ? "the thread's own instructions" : 'run windows'}), ${fmtCount(a.w)} instructions in them`;
  if (kind === 'code')
    return head + `<table class="num"><tr><td></td><td>code</td><td>distinct insts</td>${binned() ? '<td>largest bin</td>' : ''}</tr>
      <tr><td>user</td><td>${fmtKib(a.u_code_kib)}</td><td>${fmtInt(a.u_uniq_insts)}</td>${binned() ? `<td>${fmtKib(a.max_u_kib)}</td>` : ''}</tr>
      <tr><td>kernel</td><td>${fmtKib(a.k_code_kib)}</td><td>${fmtInt(a.k_uniq_insts)}</td>${binned() ? `<td>${fmtKib(a.max_k_kib)}</td>` : ''}</tr>
      <tr><td>total</td><td>${fmtKib(a.code_kib)}</td><td>${fmtInt(a.uniq_insts)}</td></tr></table>${binNote}` +
      (binned() ? `<br>whole stream: ${fmtKib(t.code_kib)}` : '');
  if (kind === 'insts')
    return head + `<table class="num"><tr><td>user</td><td>${fmtInt(t.insts - t.k_insts)}</td><td>${((1 - t.k_insts / t.insts) * 100).toFixed(1)}%</td></tr>
      <tr><td>kernel</td><td>${fmtInt(t.k_insts)}</td><td>${(t.k_insts / t.insts * 100).toFixed(1)}%</td></tr>
      <tr><td>total</td><td>${fmtInt(t.insts)}</td><td></td></tr></table>committed instructions`;
  if (kind === 'br')
    return head + `<table class="num">${BR.map((b, i) => `<tr><td><i class="swatch" style="display:inline-block;background:var(${SLOTS[i]})"></i> ${BRLABEL[b]}</td><td>${fmtInt(a.br[i])}</td>${binned() ? '' : `<td>taken ${fmtInt(t.brt[i])}</td>`}</tr>`).join('')}
      <tr><td><b>all</b></td><td>${fmtInt(a.branches)}</td><td>taken ${fmtInt(a.branchesTaken)}</td></tr></table>${binNote}` +
      (binned() ? `<br>largest bin: ${fmtInt(a.max_br)}; whole stream: ${fmtInt(t.branches)}` : `<br>kernel: ${fmtInt(t.k_br)}`);
  const q = t.q[kind], unit = kind === 'pc' ? 'instructions' : 'lines';
  const cold = kind === 'pc' ? t.pc_cold : t.line_cold;
  let s = head + `<table class="num"><tr><td>median</td><td>${fmtD(q[0])}</td></tr><tr><td>90th</td><td>${fmtD(q[1])}</td></tr>
    <tr><td>99th</td><td>${fmtD(q[2])}</td></tr><tr><td>cold</td><td>${cold.toFixed(3)}%</td></tr></table>distinct ${unit} since last use`;
  if (kind === 'line')
    s += `<br><table class="num">${CAPS.map((c, i) => `<tr><td>${c.label}</td><td>hits ${(t.hit[i] ?? 0).toFixed(2)}%</td><td>${f2(t.mpki[i])} MPKI</td></tr>`).join('')}</table>`;
  return s;
}
function place(e) {
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
  tip.style.left = Math.max(8, x) + 'px'; tip.style.top = Math.max(8, y) + 'px';
}
document.addEventListener('mousemove', e => {
  const svg = e.target.closest && e.target.closest('[data-tip]');
  const cv = e.target.dataset && e.target.dataset.curve;
  const gr = e.target.dataset && e.target.dataset.grow;
  if (gr) {
    const [id, l, key] = gr.split('|'), t = D.threads.find(t => t.id === +id);
    const r = l === 'whole' ? t.W : t.b[$('binCut').value][l];
    tip.innerHTML = `<b>${esc(t.label)}</b><br>${l === 'whole' ? 'whole stream' : `mean per ${l} bin, ${r.n} bins`}<br>` +
      `<span class="num">${key === 'code_kib' ? fmtKib(r.code_kib) + ' of code' : fmtInt(r.branchesTaken) + ' distinct taken branches'}</span>`;
    tip.hidden = false; place(e);
  } else if (svg) {
    const t = D.threads.find(t => t.id === +svg.dataset.id);
    tip.innerHTML = tipFor(svg.dataset.tip, t); tip.hidden = false; place(e);
  } else if (cv) {
    const el = e.target.ownerSVGElement, s = el._scale;
    const pt = el.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const p = pt.matrixTransform(el.getScreenCTM().inverse());
    const frac = (p.x - PAD.l) / (CW - PAD.l - PAD.r);
    const b = Math.max(0, Math.round(frac * Math.log2(s.xmax)));
    const xl = el.querySelector('#' + el.id + 'X');
    xl.setAttribute('x1', s.sx(2 ** b)); xl.setAttribute('x2', s.sx(2 ** b)); xl.setAttribute('visibility', 'visible');
    const unit = s.v === 'pc' ? 'instructions' : 'lines';
    const kib = s.v === 'pc' ? 2 ** b * 4 / 1024 : 2 ** b * 64 / 1024;
    tip.innerHTML = `<b>capacity ${fmtCount(2 ** b)} ${unit}</b> (${fmtKib(kib)})<table class="num">` +
      s.sel.map(([t, slot]) => {
        const pts = curve(t.h[s.v], s.v === 'pc' ? t.insts : t.accesses);
        const at = pts.filter(([x]) => x <= 2 ** b).pop();
        return `<tr><td><i class="swatch" style="display:inline-block;background:var(${SLOTS[slot]})"></i> ${esc(t.label)}</td><td>${(at[1] * 100).toFixed(3)}%</td></tr>`;
      }).join('') + '</table>miss ratio';
    tip.hidden = false; place(e);
  } else {
    tip.hidden = true;
    document.querySelectorAll('[id$="X"]').forEach(l => l.setAttribute('visibility', 'hidden'));
  }
});

// ---- wiring -----------------------------------------------------------------
function toggleRow(tr) { pick(+tr.dataset.id); renderStrip(); renderCurves(); renderGrowth(); }
$('strip').addEventListener('click', e => { const tr = e.target.closest('tbody tr'); if (tr) toggleRow(tr); });
$('strip').addEventListener('keydown', e => {
  const tr = e.target.closest('tbody tr');
  if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); toggleRow(tr); }
});
for (const id of ['sortBy', 'topN', 'minInsts', 'codeMode', 'binSize', 'binCut'])
  $(id).addEventListener('change', () => {
    $('binCut').disabled = !binned();
    savePrefs(); renderStrip(); renderGrowth(); renderFull();
  });
$('filter').addEventListener('input', () => { renderStrip(); renderFull(); });

$('title').textContent = M.run + ': code footprint by thread';
const kernelInsts = D.threads.reduce((a, t) => a + t.k_insts, 0);
$('totals').innerHTML = `<span><b>${fmtCount(M.insts)}</b> instructions</span>` +
  `<span><b>${D.threads.length}</b> threads</span>` +
  `<span><b>${Math.round(kernelInsts / M.insts * 100)}%</b> in the kernel</span>` +
  `<span>caches: <b>${CAPS.map(c => c.label).join(' · ')}</b></span>` +
  (BINS.length ? `<span>bins: <b>${BINS.map(b => b.label).join(' · ')}</b></span>` : '');
renderProcs(); renderStrip(); renderCurves(); renderGrowth(); renderFull();
})();
</script>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("footprint", type=Path,
                    help="a pc_footprint.py output directory")
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()
    write_report(args.footprint, args.out)


if __name__ == "__main__":
    main()
