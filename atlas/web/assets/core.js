// Shared data access, formatting, colours and small UI helpers.
// Every number shown in the Atlas comes from the JSON files written by atlas/build_atlas.py.

export const DATA = { meta: null, nodes: null, stories: null, activity: null, pairs: new Map(), byName: new Map() };

export const PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
export const OTHER = "#8a8984";
export const CATEGORY_ORDER = ["gateway", "media", "hobby", "support", "politics_news", "finance", "expertise"];

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

/** Pair arrays for one period, cached. Pairs are stored in upper-triangle order (i < j). */
export async function loadPairs(pid) {
  if (DATA.pairs.has(pid)) return DATA.pairs.get(pid);
  const p = await getJSON(`data/pairs_${pid}.json`);
  p.validatedSet = new Set(p.validated);
  p.robustSet = p.robust ? new Set(p.robust) : null;
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
    robust: p.robustSet ? p.robustSet.has(k) : null,
  };
}

/** Neighbours of node i, ranked by affinity among validated pairs, or by cosine among all pairs. */
export function neighbours(p, i, by = "affinity") {
  const out = [];
  for (let j = 0; j < S(); j++) {
    if (j === i) continue;
    const s = pairStats(p, i, j);
    if (by === "affinity" ? s.validated : s.shared > 0) out.push({ j, ...s });
  }
  out.sort((a, b) => (by === "affinity" ? b.affinity - a.affinity : b.cosine - a.cosine));
  return out;
}

// ---------- colours ----------
export function communityColor(c) {
  const comms = DATA.meta.communities;
  const rank = comms.findIndex((x) => x.id === c);
  return rank >= 0 && rank < PALETTE.length && comms[rank].size > 1 ? PALETTE[rank] : OTHER;
}
export function categoryColor(cat) {
  const i = CATEGORY_ORDER.indexOf(cat);
  return i >= 0 ? PALETTE[i] : OTHER;
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
export function fmtCompact(x) {
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

// ---------- routing state ----------
export function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  return { route: parts[0] || "discover", args: parts.slice(1), params: Object.fromEntries(new URLSearchParams(query)) };
}
export function hashFor(route, args = [], params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();
  return `#/${[route, ...args.map(encodeURIComponent)].join("/")}${q ? `?${q}` : ""}`;
}
/** Update the URL without re-rendering the page (so views stay shareable). */
export function replaceParams(route, args, params) {
  history.replaceState(null, "", hashFor(route, args, params));
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
export const hideTip = () => { tip().hidden = true; };

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
      : `<li class="muted">No subreddit in the frame matches “${esc(q)}”</li>`;
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
  return { set: (n) => { input.value = n ? `r/${n.name}` : ""; } };
}

/** Horizontal bar list of neighbours (affinity), clickable. */
export function neighbourBars(list, { onClick, max = null, metric = "affinity" } = {}) {
  if (!list.length) return `<div class="empty">No validated surprising links in this period.</div>`;
  const top = max ? list.slice(0, max) : list;
  const vmax = Math.max(...top.map((x) => (metric === "affinity" ? Math.log(x.affinity) : x.cosine)));
  return `<div class="bars">${top.map((x) => {
    const n = DATA.nodes[x.j];
    const v = metric === "affinity" ? Math.log(x.affinity) : x.cosine;
    const w = Math.max(3, (100 * v) / vmax);
    return `<div class="bar-row" data-j="${x.j}" title="r/${esc(n.name)}">
      <div class="name"><span class="dot" style="background:${communityColor(n.community)}"></span>r/${esc(n.name)}</div>
      <div class="val">${metric === "affinity" ? fmtX(x.affinity) : x.cosine.toFixed(3)}</div>
      <div class="track"><div class="fill" style="width:${w}%;background:${communityColor(n.community)}"></div></div>
      <div class="meta">${fmtInt(x.shared)} shared · ${fmtInt(x.expected)} expected</div>
    </div>`;
  }).join("")}</div>`;
}
export function wireBars(root, onClick) {
  root.querySelectorAll(".bar-row[data-j]").forEach((el) => el.addEventListener("click", () => onClick(+el.dataset.j)));
}
