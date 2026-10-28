// Shared data access, formatting, colours and small UI helpers.
// Every number shown in the Atlas comes from the JSON files written by atlas/build_atlas.py.

export const DATA = { meta: null, nodes: null, stories: null, activity: null, pipeline: null, pairs: new Map(), byName: new Map() };
/** `?shot=1` before the hash: a screenshot run; pages then skip scrolling, which headless Chrome does not paint. */
export const SHOT = new URLSearchParams(location.search).has("shot");
/** Toggle a segmented-control button and expose its state to assistive technology. */
export const setOn = (b, on) => { b.classList.toggle("on", !!on); if (b.tagName === "BUTTON") b.setAttribute("aria-pressed", String(!!on)); };

export const PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
export const OTHER = "#8a8984";
export const CATEGORY_ORDER = ["gateway", "media", "hobby", "support", "politics_news", "finance", "expertise"];
export const REDUCED_MOTION = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
export const isMobile = () => window.innerWidth < 860;

async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

export async function loadCore() {
  const [meta, nodes, stories, activity] = await Promise.all([
    getJSON("data/meta.json"), getJSON("data/nodes.json"), getJSON("data/stories.json"), getJSON("data/activity.json"),
  ]);
  Object.assign(DATA, { meta, nodes, stories, activity });
  nodes.forEach((n) => DATA.byName.set(n.name.toLowerCase(), n));
  return DATA;
}

export async function loadPipeline() {
  if (!DATA.pipeline) DATA.pipeline = await getJSON("data/pipeline.json");
  return DATA.pipeline;
}

/** Pair arrays for one period, cached. Pairs are stored in upper-triangle order (i < j). */
export async function loadPairs(pid) {
  if (DATA.pairs.has(pid)) return DATA.pairs.get(pid);
  const p = await getJSON(`data/pairs_${pid}.json`);
  p.validatedSet = new Set(p.validated);
  p.robustSet = p.robust ? new Set(p.robust) : null;
  p.avoidedSet = p.avoided ? new Set(p.avoided) : new Set();
  DATA.pairs.set(pid, p);
  return p;
}

export const S = () => DATA.nodes.length;
export function pairIndex(i, j) {
  if (i > j) [i, j] = [j, i];
  const n = S();
  return i * n - (i * (i + 1)) / 2 + (j - i - 1);
}
export function pairEnds(k) {
  const n = S();
  let i = 0, start = 0;
  while (start + (n - i - 1) <= k) { start += n - i - 1; i++; }
  return [i, i + 1 + (k - start)];
}

/** Everything known about a pair in one period. */
export function pairStats(p, i, j) {
  const k = pairIndex(i, j);
  const shared = p.shared[k], expected = p.expected[k];
  return {
    k, shared, expected, cosine: p.cosine[k],
    affinity: expected > 0 ? shared / expected : 0,
    validated: p.validatedSet.has(k),
    avoided: p.avoidedSet.has(k),
    robust: p.robustSet ? p.robustSet.has(k) : null,
    pHigh: p.p_high ? p.p_high[k] : null,
    pLow: p.p_low ? p.p_low[k] : null,
  };
}

/** Neighbours of node i, ranked by affinity among validated pairs, or by cosine among all pairs. */
export function neighbours(p, i, by = "affinity") {
  const out = [];
  for (let j = 0; j < S(); j++) {
    if (j === i) continue;
    const s = pairStats(p, i, j);
    if (by === "affinity" ? s.validated : by === "avoided" ? s.avoided : s.shared > 0) out.push({ j, ...s });
  }
  out.sort((a, b) => (by === "affinity" ? b.affinity - a.affinity : by === "avoided" ? a.affinity - b.affinity : b.cosine - a.cosine));
  return out;
}

// ---------- colours ----------
export function communityColor(c) {
  const comms = DATA.meta.communities;
  const rank = comms.findIndex((x) => x.id === c);
  return rank >= 0 && rank < PALETTE.length && comms[rank].size > 1 ? PALETTE[rank] : OTHER;
}
/** Frame categories are labels assigned before analysis, not findings: they get a visibly muted version of the palette. */
export const CATEGORY_PALETTE = PALETTE.map((hex) => {
  const n = parseInt(hex.slice(1), 16), mixc = (v) => Math.round(v * 0.62 + 150 * 0.38);
  return `#${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => mixc(v).toString(16).padStart(2, "0")).join("")}`;
});
export function categoryColor(cat) {
  // a frame category shares its colour with the detected community of the same name, so one name never has two colours
  const twin = DATA.meta && DATA.meta.communities.find((c) => c.label === categoryLabel(cat));
  if (twin) return communityColor(twin.id);
  const i = CATEGORY_ORDER.indexOf(cat);
  return i >= 0 ? CATEGORY_PALETTE[i] : OTHER;
}
export const categoryLabel = (cat) => DATA.meta.categories[cat] || cat;
export const communityLabel = (c) => (DATA.meta.communities.find((x) => x.id === c) || {}).label || `Cluster ${c}`;
export function hexToRgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// ---------- formatting ----------
export const fmtInt = (x) => (x == null ? "–" : Math.round(x).toLocaleString("en-US"));
export const fmtPct = (x, d = 0) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
export const fmtX = (x, d = 1) => (x == null ? "–" : `${x.toFixed(d)}×`);
/** "6 communities, plus 3 small groups and 1 isolate" from the summary, or the plain count. */
export function communitiesPhrase(sm) {
  const a = sm.anchor;
  if (a.communities_major == null) return `${a.communities} communities`;
  const extra = [a.small_groups ? `${a.small_groups} small group${a.small_groups > 1 ? "s" : ""}` : "", a.isolates ? `${a.isolates} isolate${a.isolates > 1 ? "s" : ""}` : ""].filter(Boolean);
  return `${a.communities_major} communities${extra.length ? ` (plus ${extra.join(" and ")})` : ""}`;
}
export function fmtP(p) {
  if (p == null) return "–";
  if (p < 1e-300) return "< 10⁻³⁰⁰";
  if (p >= 0.01) return p.toFixed(2);
  const e = Math.floor(Math.log10(p)), m = p / 10 ** e;
  return `${m.toFixed(1)}×10${sup(e)}`;
}
const sup = (n) => String(n).replace(/-/g, "⁻").replace(/\d/g, (d) => "⁰¹²³⁴⁵⁶⁷⁸⁹"[d]);
export function fmtCompact(x) {
  if (x == null) return "–";
  if (x >= 1e9) return `${(x / 1e9).toFixed(1)}B`;
  if (x >= 1e6) return `${(x / 1e6).toFixed(1)}M`;
  if (x >= 1e4) return `${Math.round(x / 1e3)}k`;
  return fmtInt(x);
}
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export function periodLabel(pid) {
  const p = DATA.meta.periods.find((x) => x.id === pid);
  return p ? p.label : pid;
}
export function monthLabel(m, long = false) {
  const d = new Date(Date.UTC(+m.slice(0, 4), +m.slice(5, 7) - 1, m.length > 7 ? +m.slice(8, 10) : 1));
  return d.toLocaleDateString("en-GB", { month: "short", year: long ? "numeric" : undefined, day: m.length > 7 ? "numeric" : undefined, timeZone: "UTC" });
}

// ---------- routing state ----------
export function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  return { route: parts[0] || "start", args: parts.slice(1), params: Object.fromEntries(new URLSearchParams(query)) };
}
export function hashFor(route, args = [], params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();
  return `#/${[route, ...args.map(encodeURIComponent)].join("/")}${q ? `?${q}` : ""}`;
}
/** Update the URL without re-rendering the page (so views stay shareable). */
export function replaceParams(route, args, params) {
  history.replaceState(null, "", hashFor(route, args, params));
}

// ---------- page API registry (lets the guided tour drive whichever page is mounted) ----------
// A page registers { name, ready: Promise, map?, select?, setView?, setPeriod?, focus?, flyTo?, reset?, goStep? }.
export const PAGE = { current: null, listeners: new Set() };
export function registerPage(api) {
  PAGE.current = api;
  PAGE.listeners.forEach((fn) => fn(api));
}
export function onPageReady(fn) { PAGE.listeners.add(fn); return () => PAGE.listeners.delete(fn); }
export async function currentPage(name, timeoutMs = 6000) {
  const ok = (api) => api && (!name || api.name === name);
  if (ok(PAGE.current)) { await PAGE.current.ready; return PAGE.current; }
  return new Promise((resolve) => {
    const t = setTimeout(() => { off(); resolve(null); }, timeoutMs);
    const off = onPageReady(async (api) => { if (ok(api)) { clearTimeout(t); off(); await api.ready; resolve(api); } });
  });
}

// ---------- tooltip ----------
const tip = () => document.getElementById("tooltip");
export function showTip(html, x, y) {
  const t = tip();
  t.innerHTML = html;
  t.hidden = false;
  const w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = `${Math.min(window.innerWidth - w - 8, x + 14)}px`;
  t.style.top = `${Math.max(8, Math.min(window.innerHeight - h - 8, y + 14))}px`;
}
export const hideTip = () => { const t = tip(); if (t) t.hidden = true; };

// ---------- search box ----------
export function searchBox(container, { placeholder = "Search a subreddit…", onPick, value = "" } = {}) {
  container.classList.add("search");
  container.innerHTML = `<input type="search" placeholder="${esc(placeholder)}" value="${esc(value)}" aria-label="${esc(placeholder)}" autocomplete="off"><ul hidden role="listbox"></ul>`;
  const input = container.querySelector("input"), list = container.querySelector("ul");
  let items = [], active = 0;
  const render = () => {
    const q = input.value.trim().toLowerCase().replace(/^r\//, "");
    if (!q) { list.hidden = true; return; }
    items = DATA.nodes.filter((n) => n.name.toLowerCase().includes(q))
      .sort((a, b) => (a.name.toLowerCase().startsWith(q) ? 0 : 1) - (b.name.toLowerCase().startsWith(q) ? 0 : 1) || b.users - a.users)
      .slice(0, 8);
    active = 0;
    list.innerHTML = items.length
      ? items.map((n, k) => `<li role="option" data-k="${k}" class="${k === 0 ? "active" : ""}"><span class="dot" style="background:${communityColor(n.community)}"></span>r/${esc(n.name)}<small>${esc(categoryLabel(n.category))}</small></li>`).join("")
      : `<li class="muted">r/${esc(q)} isn't one of the ${DATA.nodes.length} subreddits studied here</li>`;
    list.hidden = false;
  };
  const pick = (n) => { input.value = `r/${n.name}`; list.hidden = true; onPick && onPick(n); };
  input.addEventListener("input", render);
  input.addEventListener("focus", render);
  input.addEventListener("keydown", (e) => {
    if (list.hidden || !items.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length;
      list.querySelectorAll("li").forEach((li, k) => li.classList.toggle("active", k === active));
    } else if (e.key === "Enter") { e.preventDefault(); pick(items[active]); }
    else if (e.key === "Escape") { list.hidden = true; }
  });
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-k]");
    if (li) { e.preventDefault(); pick(items[+li.dataset.k]); }
  });
  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 120));
  return { set: (n) => { input.value = n ? `r/${n.name}` : ""; }, focus: () => input.focus() };
}

/** Horizontal bar list of neighbours (affinity), clickable. */
export function neighbourBars(list, { max = null, metric = "affinity", empty = "No surprising links in this period." } = {}) {
  if (!list.length) return `<div class="empty">${esc(empty)}</div>`;
  const top = max ? list.slice(0, max) : list;
  const val = (x) => (metric === "affinity" ? Math.log(Math.max(1.0001, x.affinity)) : metric === "avoided" ? -Math.log(Math.max(1e-3, x.affinity)) : x.cosine);
  const vmax = Math.max(...top.map(val));
  return `<div class="bars">${top.map((x) => {
    const n = DATA.nodes[x.j];
    const w = Math.max(3, (100 * val(x)) / vmax);
    return `<button class="bar-row" data-j="${x.j}" title="Open r/${esc(n.name)}">
      <span class="name"><span class="dot" style="background:${communityColor(n.community)}"></span>r/${esc(n.name)}</span>
      <span class="val">${metric === "cosine" ? x.cosine.toFixed(3) : fmtX(x.affinity, x.affinity < 1 ? 2 : 1)}</span>
      <span class="track"><span class="fill" style="width:${w}%;background:${metric === "avoided" ? "var(--text-muted)" : communityColor(n.community)}"></span></span>
      <span class="meta">${fmtInt(x.shared)} shared · ${fmtInt(x.expected)} expected</span>
    </button>`;
  }).join("")}</div>`;
}
export function wireBars(root, onClick) {
  root.querySelectorAll(".bar-row[data-j]").forEach((el) => el.addEventListener("click", () => onClick(+el.dataset.j)));
}

/** Plain-language verdict for one pair, used by Compare, drawers and stories. */
export function pairVerdict(s, aName, bName) {
  const sh = fmtInt(s.shared), ex = fmtInt(s.expected);
  if (s.validated) return `r/${esc(aName)} and r/${esc(bName)} share <b>${sh}</b> commenters where <b>${ex}</b> were expected from size and activity alone — <b>${fmtX(s.affinity, 1)}</b> chance. A surprising link${s.robust ? ", which also survives the stricter two-comment threshold" : ""}.`;
  if (s.avoided) return `r/${esc(aName)} and r/${esc(bName)} share only <b>${sh}</b> commenters where <b>${ex}</b> were expected — <b>${fmtX(s.affinity, 2)}</b> chance. Their audiences overlap <b>less</b> than size and activity would produce.`;
  return `r/${esc(aName)} and r/${esc(bName)} share ${sh} commenters where ${ex} were expected (${fmtX(s.affinity, 2)}): about what chance alone would produce. No surprising link.`;
}
