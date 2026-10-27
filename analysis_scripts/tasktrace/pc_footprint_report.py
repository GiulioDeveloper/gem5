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
and distinct branches by type. Below: the miss ratio curves (the share of
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
    from pc_footprint import BRANCHES, CACHES, LINE, key_of, thread_hists, \
        thread_label
    with open(out / "threads.csv") as f:
        rows = list(csv.DictReader(f))
    hists = thread_hists(out)
    keys = [key_of(label) for label, _ in CACHES]

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
    meta = {"caches": [{"label": label, "bytes": size, "lines": size // LINE}
                       for label, size in CACHES],
            "branches": list(BRANCHES)}
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
      instruction lines only, no prefetch. Click rows to compare their curves below.</p>
  </header>

  <section>
    <div class="controls">
      <label for="sortBy">Order by
        <select id="sortBy">
          <option value="insts">instructions</option>
          <option value="code_kib">code size</option>
          <option value="branches">distinct branches</option>
          <option value="mpki0">misses at 64K</option>
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
    <h2>Miss ratio curves</h2>
    <p>Share of accesses whose repeat distance is at least <i>x</i>: the miss
      ratio of a fully associative LRU cache holding <i>x</i> instructions or lines.
      The floor on the right is first-time accesses (cold). Vertical lines: the L1I and
      L2 sizes, in instructions (4 bytes each) or 64-byte lines.</p>
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

// ---- state --------------------------------------------------------------
const picked = new Map();          // thread id -> slot index
function pick(id) {
  if (picked.has(id)) { picked.delete(id); return; }
  if (picked.size >= SLOTS.length) return;
  const used = new Set(picked.values());
  picked.set(id, [...SLOTS.keys()].find(i => !used.has(i)));
}
[...D.threads].sort((a, b) => b.insts - a.insts).slice(0, 4).forEach(t => pick(t.id));
let fullSort = {key: 'insts', dir: -1};
// Hidden process names; kernel threads are one entry.
const KTHREADS = '[kernel threads]';
const procOf = t => t.kthread ? KTHREADS : t.process;
let hidden = new Set();
// Code size, distinct instructions and footprint multiples in the chosen mode.
const MODES = {all: ['code_kib', 'uniq_insts'], u: ['u_code_kib', 'u_uniq_insts'],
               k: ['k_code_kib', 'k_uniq_insts']};
const codeKib = t => t[MODES[$('codeMode').value][0]];
const codeInsts = t => t[MODES[$('codeMode').value][1]];
const codeXs = t => t.x.map(x => x == null || !t.code_kib ? null : x * codeKib(t) / t.code_kib);
const modeLabel = () => ({all: 'user + kernel', u: 'user', k: 'kernel'})[$('codeMode').value];
function prefs() { try { return JSON.parse(localStorage.getItem('fpView') || '{}'); } catch { return {}; } }
function savePrefs() {
  try { localStorage.setItem('fpView', JSON.stringify({sortBy: $('sortBy').value,
    topN: $('topN').value, minInsts: $('minInsts').value, codeMode: $('codeMode').value,
    hidden: [...hidden]})); } catch {}
}
const p0 = prefs();
for (const k of ['sortBy', 'topN', 'minInsts', 'codeMode']) if (p0[k]) $(k).value = p0[k];
if (Array.isArray(p0.hidden)) hidden = new Set(p0.hidden);

function visible() {
  const f = $('filter').value.trim().toLowerCase();
  const min = +$('minInsts').value;
  return D.threads.filter(t => t.insts >= min && !hidden.has(procOf(t)) &&
    (!f || t.label.toLowerCase().includes(f)));
}
function shown() {
  const key = $('sortBy').value, n = $('topN').value;
  const val = key === 'code_kib' ? codeKib : t => t[key];
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
const codeX = LOG(4, 65536, W);                  // KiB
const pcX = LOG(1, 2 ** 25, W);                   // distinct instructions + 1
const lineX = LOG(1, 2 ** 22, W);                 // distinct lines + 1
const capKib = CAPS.map(c => c.bytes / 1024);
const capPc = CAPS.map(c => c.bytes / 4);
const capLine = CAPS.map(c => c.lines);
const TICK = new Set([0, 2, 3, 5]);               // labelled: 64K, 512K, 2M, 16M
const TICK_ROW = new Set([0, 3, 5]);              // narrow row axes: 64K, 2M, 16M

function gridLines(xs, scale) {
  return xs.map((v, i) => `<line x1="${scale(v)}" x2="${scale(v)}" y1="0" y2="${H}" stroke="var(--rule)" stroke-width="1" ${TICK.has(i) ? '' : 'stroke-dasharray="2 2"'}/>`).join('');
}
function axisSvg(xs, scale, unit) {
  const labels = xs.map((v, i) => TICK_ROW.has(i) ? `<text x="${scale(v)}" y="11" text-anchor="middle">${CAPS[i].label.split(' ')[1]}</text>` : '').join('');
  return `<svg width="${W}" height="16" viewBox="0 0 ${W} 16" aria-hidden="true">${labels}<text x="0" y="11" text-anchor="start" style="fill:var(--ink-2)">${unit}</text></svg>`;
}
// User code (blue) and kernel code (orange) as dots, their sum as a tick;
// the mode picks which of them are drawn.
function codeSvg(t) {
  const mode = $('codeMode').value;
  const dot = (kib, col) => kib > 0
    ? `<circle cx="${codeX(kib)}" cy="${H/2}" r="4.5" fill="var(${col})" stroke="var(--surface)" stroke-width="2"/>` : '';
  const xt = codeX(t.code_kib);
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" data-tip="code" data-id="${t.id}">
    ${gridLines(capKib, codeX)}
    <line x1="0" x2="${codeX(codeKib(t))}" y1="${H/2}" y2="${H/2}" stroke="var(--grid)" stroke-width="2"/>
    ${mode === 'all' ? `<line x1="${xt}" x2="${xt}" y1="${H/2-7}" y2="${H/2+7}" stroke="var(--ink)" stroke-width="2"/>` : ''}
    ${mode !== 'u' ? dot(t.k_code_kib, '--s2') : ''}${mode !== 'k' ? dot(t.u_code_kib, '--s1') : ''}
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
  t.br.forEach((n, i) => {
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
  const max = Math.max(1, ...rows.map(t => t.branches));
  const head = `<thead><tr>
    <th>Thread<br><span class="k">process thread (pid)</span></th>
    <th style="text-align:right">Instructions<br><span class="k">user · kernel</span></th>
    <th style="text-align:right">Code size<br><span class="k">user · kernel</span></th>
    <th>${axisSvg(capKib, codeX, 'KiB')}</th>
    <th><div class="cells">${CAPS.map(c => `<div class="cellhead">${c.label.replace(' ', '<br>')}</div>`).join('')}</div>
      <span class="k">${modeLabel()} code ÷ cache size</span></th>
    <th>Repeat distance, per instruction<br>${axisSvg(capPc, pcX, '')}</th>
    <th>Repeat distance, per line<br>${axisSvg(capLine, lineX, '')}</th>
    <th>Distinct branches by type<br><span class="k">scale: ${fmtInt(max)} at full width</span></th>
    <th style="text-align:right">Branches<br><span class="k">taken</span></th>
  </tr></thead>`;
  const body = rows.map(t => {
    const slot = picked.get(t.id);
    const sw = slot == null ? 'transparent' : `var(${SLOTS[slot]})`;
    return `<tr data-id="${t.id}" tabindex="0" class="${slot == null ? '' : 'picked'}" aria-selected="${slot != null}">
      <td><div class="who"><i class="swatch" style="background:${sw}"></i><span title="${esc(t.label)}">${esc(t.label)}</span></div></td>
      <td class="num" style="text-align:right" data-tip="insts" data-id="${t.id}">${fmtCount(t.insts - t.k_insts)} <span class="k">·</span> ${fmtCount(t.k_insts)} ${splitBar(t.insts - t.k_insts, t.k_insts)}</td>
      <td class="num" style="text-align:right" data-tip="code" data-id="${t.id}">${fmtKib(t.u_code_kib)} <span class="k">·</span> ${fmtKib(t.k_code_kib)}</td>
      <td>${codeSvg(t)}</td>
      <td><div class="cells">${codeXs(t).map(x => x == null ? '<div class="cell"></div>' : fitCell(x)).join('')}</div></td>
      <td>${distSvg(t, 'pc', pcX, capPc)}</td>
      <td>${distSvg(t, 'line', lineX, capLine)}</td>
      <td>${brSvg(t, max)}</td>
      <td class="num" style="text-align:right">${fmtCount(t.branches)} <span class="k">${fmtCount(t.branchesTaken)}</span></td>
    </tr>`;
  }).join('');
  $('strip').innerHTML = head + `<tbody>${body}</tbody>`;
  const n = visible().length;
  $('stripLegend').innerHTML =
    `<span>${rows.length} of ${n} threads shown${hidden.size ? ` (${hidden.size} processes hidden)` : ''}.</span>` +
    `<span><svg width="44" height="12"><rect x="12" y="1" width="18" height="10" rx="3" fill="var(--s1)" fill-opacity=".85"/><line x1="12" x2="12" y1="0" y2="12" stroke="var(--ink)" stroke-width="2"/><line x1="30" x2="42" y1="6" y2="6" stroke="var(--ink-3)" stroke-width="2"/><line x1="42" x2="42" y1="2" y2="10" stroke="var(--ink-3)" stroke-width="2"/></svg>repeat distance: median, box to 90th, whisker to 99th percentile (dashed: past the cold misses)</span>` +
    `<span><i style="background:var(--s1)"></i>user</span><span><i style="background:var(--s2)"></i>kernel</span>` +
    `<span><svg width="10" height="12"><line x1="5" x2="5" y1="0" y2="12" stroke="var(--ink)" stroke-width="2"/></svg>user + kernel code</span>` +
    `<span>gridlines: L1I 64K / 256K / 512K, L2 2M / 8M / 16M</span>` +
    BR.map((b, i) => `<span><i style="background:var(${SLOTS[i]})"></i>${BRLABEL[b]}</span>`).join('');
}

// ---- curves -----------------------------------------------------------------
const CW = 560, CH = 300, PAD = {l: 52, r: 12, t: 10, b: 34};
const YMIN = 1e-5;
function curveSvg(el, v) {
  const xmax = v === 'pc' ? 2 ** 25 : 2 ** 22;
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
    if (TICK.has(i)) g += `<text x="${x}" y="${CH - PAD.b + 26}" text-anchor="middle">${CAPS[i].label.split(' ')[1]}</text>`;
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

// ---- full table -----------------------------------------------------------
const COLS = [
  ['thread', t => t.label, t => t.label],
  ['process', t => procOf(t), t => procOf(t)],
  ['instructions', t => t.insts, t => fmtInt(t.insts)],
  ['user insts', t => t.insts - t.k_insts, t => fmtInt(t.insts - t.k_insts)],
  ['kernel insts', t => t.k_insts, t => fmtInt(t.k_insts)],
  ['kernel %', t => t.k_insts / t.insts, t => (t.k_insts / t.insts * 100).toFixed(1)],
  ['distinct insts', t => t.uniq_insts, t => fmtInt(t.uniq_insts)],
  ['user distinct', t => t.u_uniq_insts, t => fmtInt(t.u_uniq_insts)],
  ['kernel distinct', t => t.k_uniq_insts, t => fmtInt(t.k_uniq_insts)],
  ['code KiB', t => t.code_kib, t => fmtInt(t.code_kib)],
  ['user KiB', t => t.u_code_kib, t => fmtInt(t.u_code_kib)],
  ['kernel KiB', t => t.k_code_kib, t => fmtInt(t.k_code_kib)],
  ...CAPS.map((c, i) => ['× ' + c.label, t => t.x[i], t => fmtX(t.x[i])]),
  ...CAPS.map((c, i) => ['user × ' + c.label, t => t.x[i] * t.u_code_kib / t.code_kib, t => fmtX(t.x[i] * t.u_code_kib / t.code_kib)]),
  ...CAPS.map((c, i) => ['MPKI ' + c.label, t => t.mpki[i], t => f2(t.mpki[i])]),
  ['shared MPKI L1I 64K', t => t.smpki[0], t => f2(t.smpki[0])],
  ['shared MPKI L2 2M', t => t.smpki[3], t => f2(t.smpki[3])],
  ['cold MPKI', t => t.line_cold * t.accesses / t.insts * 10, t => f2(t.line_cold * t.accesses / t.insts * 10)],
  ...['p50', 'p90', 'p99'].map((p, i) => ['inst dist ' + p, t => t.q.pc[i] ?? Infinity, t => fmtD(t.q.pc[i])]),
  ...['p50', 'p90', 'p99'].map((p, i) => ['line dist ' + p, t => t.q.line[i] ?? Infinity, t => fmtD(t.q.line[i])]),
  ['branches', t => t.branches, t => fmtInt(t.branches)],
  ['taken', t => t.branchesTaken, t => fmtInt(t.branchesTaken)],
  ['kernel branches', t => t.k_br, t => fmtInt(t.k_br)],
  ...BR.map((b, i) => [BRLABEL[b] + ' (taken)', t => t.br[i], t => `${fmtInt(t.br[i])} (${fmtInt(t.brt[i])})`]),
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
  if (kind === 'code')
    return head + `<table class="num"><tr><td></td><td>code</td><td>distinct insts</td></tr>
      <tr><td>user</td><td>${fmtKib(t.u_code_kib)}</td><td>${fmtInt(t.u_uniq_insts)}</td></tr>
      <tr><td>kernel</td><td>${fmtKib(t.k_code_kib)}</td><td>${fmtInt(t.k_uniq_insts)}</td></tr>
      <tr><td>total</td><td>${fmtKib(t.code_kib)}</td><td>${fmtInt(t.uniq_insts)}</td></tr></table>`;
  if (kind === 'insts')
    return head + `<table class="num"><tr><td>user</td><td>${fmtInt(t.insts - t.k_insts)}</td><td>${((1 - t.k_insts / t.insts) * 100).toFixed(1)}%</td></tr>
      <tr><td>kernel</td><td>${fmtInt(t.k_insts)}</td><td>${(t.k_insts / t.insts * 100).toFixed(1)}%</td></tr>
      <tr><td>total</td><td>${fmtInt(t.insts)}</td><td></td></tr></table>committed instructions`;
  if (kind === 'br')
    return head + `<table class="num">${BR.map((b, i) => `<tr><td><i class="swatch" style="display:inline-block;background:var(${SLOTS[i]})"></i> ${BRLABEL[b]}</td><td>${fmtInt(t.br[i])}</td><td>taken ${fmtInt(t.brt[i])}</td></tr>`).join('')}
      <tr><td><b>all</b></td><td>${fmtInt(t.branches)}</td><td>taken ${fmtInt(t.branchesTaken)}</td></tr></table>kernel: ${fmtInt(t.k_br)}`;
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
  if (svg) {
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
function toggleRow(tr) { pick(+tr.dataset.id); renderStrip(); renderCurves(); }
$('strip').addEventListener('click', e => { const tr = e.target.closest('tbody tr'); if (tr) toggleRow(tr); });
$('strip').addEventListener('keydown', e => {
  const tr = e.target.closest('tbody tr');
  if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); toggleRow(tr); }
});
for (const id of ['sortBy', 'topN', 'minInsts', 'codeMode'])
  $(id).addEventListener('change', () => { savePrefs(); renderStrip(); renderFull(); });
$('filter').addEventListener('input', () => { renderStrip(); renderFull(); });

$('title').textContent = M.run + ': code footprint by thread';
const kernelInsts = D.threads.reduce((a, t) => a + t.k_insts, 0);
$('totals').innerHTML = `<span><b>${fmtCount(M.insts)}</b> instructions</span>` +
  `<span><b>${D.threads.length}</b> threads</span>` +
  `<span><b>${Math.round(kernelInsts / M.insts * 100)}%</b> in the kernel</span>` +
  `<span>caches: <b>${CAPS.map(c => c.label).join(' · ')}</b></span>`;
renderProcs(); renderStrip(); renderCurves(); renderFull();
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
