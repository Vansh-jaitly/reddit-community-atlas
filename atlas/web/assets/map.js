// AtlasMap: one sigma.js renderer over the fixed Atlas layout.
// Raw view = every pair sharing at least one commenter (cosine weight).
// Adjusted view = only pairs validated against the activity-adjusted expectation.
import {
  DATA, loadPairs, pairEnds, communityColor, categoryColor, showTip, hideTip,
  fmtX, fmtInt, esc, communityLabel, categoryLabel, pairStats,
} from "./core.js";

const SigmaCls = window.Sigma && (window.Sigma.Sigma || window.Sigma.default || window.Sigma);
const GraphCls = window.graphology && (window.graphology.Graph || window.graphology);
const DIM_NODE = "#2c2c2a";
const BG = [22, 22, 21];

/** Opaque colour = rgb mixed over the map background. sigma's WebGL blending expects premultiplied
 *  colours, so translucent rgba() edges would render at full brightness; pre-mixing avoids that. */
function mix(rgb, a) {
  const c = rgb.map((v, i) => Math.round(BG[i] + (v - BG[i]) * Math.max(0, Math.min(1, a))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
const hexRgb = (hex) => { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };

/** Dark label box for hovered/selected nodes (sigma's default box is white, which hides light text). */
function drawHover(ctx, data, settings) {
  const size = settings.labelSize, label = data.label || "";
  ctx.font = `600 ${size}px ${settings.labelFont}`;
  const w = ctx.measureText(label).width, x = data.x + data.size + 5, y = data.y;
  ctx.beginPath();
  ctx.arc(data.x, data.y, data.size + 2.5, 0, Math.PI * 2);
  ctx.lineWidth = 2; ctx.strokeStyle = "#f0efec"; ctx.stroke();
  if (!label) return;
  const h = size + 10;
  ctx.fillStyle = "rgba(34,34,32,0.96)";
  ctx.strokeStyle = "#4a4a45"; ctx.lineWidth = 1;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y - h / 2, w + 14, h, 6); else ctx.rect(x, y - h / 2, w + 14, h);
  ctx.fill(); ctx.stroke();
  ctx.fillStyle = "#f0efec";
  ctx.fillText(label, x + 7, y + size / 3);
}

export class AtlasMap {
  constructor(container, opts = {}) {
    this.opts = { interactive: true, communityLabels: true, labelThreshold: 7, onSelect: null, sizeScale: 1, ...opts };
    this.el = container;
    this.el.innerHTML = `<div class="map-canvas"></div><div class="map-labels"></div>`;
    this.canvas = this.el.querySelector(".map-canvas");
    this.labelLayer = this.el.querySelector(".map-labels");
    this.colorBy = "community";
    this.view = "adjusted";
    this.period = "all";
    this.focus = null;          // Set of node ids to emphasise
    this.focusEdges = null;     // Set of "i-j" keys to emphasise
    this.selected = null;
    this.hovered = null;
    this.communityFilter = null;
    this.edgeMode = null;       // optional {gained:Set,lost:Set} used by Compare
    this.graph = new GraphCls({ type: "undirected", multi: false });
    for (const n of DATA.nodes) {
      this.graph.addNode(String(n.id), { x: n.x, y: n.y, size: 4, label: n.name, color: communityColor(n.community) });
    }
    this.renderer = new SigmaCls(this.graph, this.canvas, {
      renderLabels: true,
      labelRenderedSizeThreshold: this.opts.labelThreshold,
      labelFont: getComputedStyle(document.body).fontFamily,
      labelSize: 12,
      labelWeight: "500",
      labelColor: { color: "#d8d7d0" },
      defaultEdgeType: "line",
      zIndex: true,
      minCameraRatio: 0.08,
      maxCameraRatio: 3,
      enableEdgeClickEvents: false,
      enableEdgeHoverEvents: false,
      hoverRenderer: drawHover,
      nodeReducer: (key, data) => this.nodeReducer(key, data),
      edgeReducer: (key, data) => this.edgeReducer(key, data),
    });
    if (this.opts.interactive) this.bindEvents();
    this.renderer.on("afterRender", () => this.drawCommunityLabels());
    this.applyColors();
  }

  // ---------- data ----------
  async show({ period = this.period, view = this.view } = {}) {
    this.period = period; this.view = view;
    const p = await loadPairs(period);
    if (this.period !== period || this.view !== view) return;    // a newer request superseded this one
    this.pairs = p;
    this.graph.clearEdges();
    const maxUsers = Math.max(...p.users);
    DATA.nodes.forEach((n, i) => {
      const s = 2.2 + 13 * Math.sqrt((p.users[i] || 0) / maxUsers);
      this.graph.setNodeAttribute(String(i), "size", s * this.opts.sizeScale);
    });
    if (view === "raw") {
      let cmax = 0;
      for (const c of p.cosine) if (c > cmax) cmax = c;
      for (let k = 0; k < p.shared.length; k++) {
        if (p.shared[k] <= 0) continue;
        const [i, j] = pairEnds(k);
        const w = p.cosine[k] / cmax;
        this.graph.addEdgeWithKey(`${i}-${j}`, String(i), String(j), {
          size: 0.2 + 1.2 * w, color: mix([200, 199, 190], 0.12 + 0.5 * w), k, base: true,
        });
      }
    } else {
      let lmax = 0;
      for (const k of p.validated) lmax = Math.max(lmax, Math.log(p.shared[k] / p.expected[k]));
      for (const k of p.validated) {
        const [i, j] = pairEnds(k);
        const w = Math.log(p.shared[k] / p.expected[k]) / lmax;
        const ci = DATA.nodes[i].community, cj = DATA.nodes[j].community;
        // Links inside a community take its colour; the many cross-community links stay faint so they read as texture.
        const same = ci === cj;
        const color = same ? mix(hexRgb(communityColor(ci)), 0.3 + 0.5 * w) : mix([150, 149, 141], 0.1 + 0.2 * w);
        this.graph.addEdgeWithKey(`${i}-${j}`, String(i), String(j), { size: same ? 0.4 + 2.2 * w : 0.25 + 1.2 * w, color, k, base: true });
      }
    }
    this.refresh();
    return p;
  }

  setColorBy(mode) { this.colorBy = mode; this.applyColors(); }
  applyColors() {
    DATA.nodes.forEach((n) => this.graph.setNodeAttribute(String(n.id), "color",
      this.colorBy === "category" ? categoryColor(n.category) : communityColor(n.community)));
    this.refresh();
  }

  setFocus(ids, edges = null, edgeColor = "rgb(240,239,236)") {
    this.focusEdgeColor = edgeColor;
    this.focus = ids && ids.length ? new Set(ids.map(Number)) : null;
    this.focusEdges = edges && edges.length ? new Set(edges.map(([a, b]) => (a < b ? `${a}-${b}` : `${b}-${a}`))) : null;
    this.refresh();
  }
  setCommunityFilter(c) { this.communityFilter = c; this.refresh(); }
  select(i, { fly = true } = {}) {
    this.selected = i == null ? null : Number(i);
    if (this.selected != null && fly) this.flyTo([this.selected], 0.45);
    this.refresh();
  }

  /** Recompute the emphasised node set once, then redraw (reducers read the cached set). */
  refresh() { this._act = this.activeSet(); this.renderer.refresh(); }

  neighbourSet(i) {
    const s = new Set([i]);
    this.graph.forEachNeighbor(String(i), (nb) => s.add(Number(nb)));
    return s;
  }

  // ---------- reducers ----------
  activeSet() {
    if (this.hovered != null) return this.neighbourSet(this.hovered);
    if (this.selected != null) return this.neighbourSet(this.selected);
    if (this.focus) return this.focus;
    if (this.communityFilter != null) return new Set(DATA.nodes.filter((n) => n.community === this.communityFilter).map((n) => n.id));
    return null;
  }
  nodeReducer(key, data) {
    const id = Number(key);
    const act = this._act;
    const res = { ...data };
    if (act && !act.has(id)) { res.color = DIM_NODE; res.label = ""; res.zIndex = 0; }
    else if (act) { res.zIndex = 2; res.forceLabel = act.size <= 24; }
    if (id === this.selected || id === this.hovered) { res.highlighted = true; res.forceLabel = true; res.zIndex = 3; }
    return res;
  }
  edgeReducer(key, data) {
    const res = { ...data };
    const [a, b] = key.split("-").map(Number);
    const act = this._act;
    if (this.focusEdges && this.hovered == null && this.selected == null) {
      if (this.focusEdges.has(key)) { res.color = this.focusEdgeColor; res.size = Math.max(2, data.size * 1.5); res.zIndex = 3; }
      else if (act && !(act.has(a) && act.has(b))) res.hidden = true;
      else res.color = mix([140, 139, 132], 0.08);
      return res;
    }
    if (act) {
      const center = this.hovered != null ? this.hovered : this.selected;
      if (center != null) {
        if (a !== center && b !== center) res.hidden = true;
        else { res.size = Math.max(1.2, data.size * 1.5); res.color = this.brighten(data.color); res.zIndex = 2; }
      } else if (!(act.has(a) && act.has(b))) res.hidden = true;
    }
    return res;
  }

  /** Emphasised version of a pre-mixed edge colour (used for the hovered/selected node's links). */
  brighten(rgb) {
    const c = rgb.match(/\d+/g).map(Number);
    return mix(c.map((v, i) => BG[i] + (v - BG[i]) * 3), 1);
  }

  // ---------- camera ----------
  flyTo(ids, minRatio = 0.25) {
    const pts = ids.map((i) => this.renderer.getNodeDisplayData(String(i))).filter(Boolean);
    if (!pts.length) return;
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    const ratio = Math.min(1.1, Math.max(minRatio, span * 1.35));
    this.renderer.getCamera().animate({ x: cx, y: cy, ratio }, { duration: 650 });
  }
  reset() { this.renderer.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1, angle: 0 }, { duration: 500 }); }
  zoom(f) { const c = this.renderer.getCamera(); c.animate({ ratio: c.ratio / f }, { duration: 250 }); }

  // ---------- overlays ----------
  drawCommunityLabels() {
    if (!this.opts.communityLabels) { this.labelLayer.innerHTML = ""; return; }
    const groups = this.colorBy === "category"
      ? [...new Set(DATA.nodes.map((n) => n.category))].map((c) => ({ key: c, label: categoryLabel(c), color: categoryColor(c), members: DATA.nodes.filter((n) => n.category === c) }))
      : DATA.meta.communities.filter((c) => c.size > 1).map((c) => ({ key: c.id, label: c.label, color: communityColor(c.id), members: DATA.nodes.filter((n) => n.community === c.id) }));
    const act = this._act;
    this.labelLayer.innerHTML = groups.map((g) => {
      if (this.colorBy === "category") return "";   // categories are spread across the map; the legend carries them
      const xs = g.members.map((n) => n.x), ys = g.members.map((n) => n.y);
      const vp = this.renderer.graphToViewport({ x: xs.reduce((a, b) => a + b, 0) / xs.length, y: ys.reduce((a, b) => a + b, 0) / ys.length });
      const dim = act && !g.members.some((n) => act.has(n.id));
      return `<div style="left:${vp.x}px;top:${vp.y}px;opacity:${dim ? 0.15 : 0.9}"><i style="background:${g.color}"></i>${esc(g.label)}</div>`;
    }).join("");
  }

  // ---------- events ----------
  bindEvents() {
    const r = this.renderer;
    r.on("enterNode", ({ node, event }) => {
      this.hovered = Number(node);
      this.refresh();
      const n = DATA.nodes[this.hovered];
      const rect = this.el.getBoundingClientRect();
      const deg = this.graph.degree(node);
      let pairLine = "";
      if (this.selected != null && this.selected !== this.hovered && this.pairs) {
        const s = pairStats(this.pairs, this.selected, this.hovered);
        pairLine = `<div class="t-row"><span>with r/${esc(DATA.nodes[this.selected].name)}</span><span>${s.validated ? fmtX(s.affinity) : "not significant"}</span></div>`;
      }
      showTip(`<b>r/${esc(n.name)}</b><div class="muted">${esc(categoryLabel(n.category))} · ${esc(communityLabel(n.community))}</div>
        <div class="t-row"><span>Commenters (${esc(this.period === "all" ? "all months" : this.period)})</span><span>${fmtInt(this.pairs ? this.pairs.users[n.id] : n.users)}</span></div>
        <div class="t-row"><span>${this.view === "raw" ? "Pairs sharing ≥1 commenter" : "Surprising links"}</span><span>${deg}</span></div>${pairLine}`,
        rect.left + event.x, rect.top + event.y);
    });
    r.on("leaveNode", () => { this.hovered = null; this.refresh(); hideTip(); });
    r.on("clickNode", ({ node }) => { this.opts.onSelect && this.opts.onSelect(Number(node)); });
    r.on("clickStage", () => { this.opts.onSelect && this.opts.onSelect(null); });
  }

  destroy() { hideTip(); this.renderer.kill(); }
}

/** Overview-only map (no hover/click), used in the hero and small multiples. */
export function staticMap(container, opts = {}) {
  return new AtlasMap(container, { interactive: false, labelThreshold: 11, ...opts });
}
