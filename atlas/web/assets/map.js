// AtlasMap: one sigma.js renderer over the fixed Atlas layout.
//   raw      = every pair sharing at least one commenter (cosine weight)
//   surprise = the same edges, grey when within chance and coloured when validated
//   adjusted = only pairs validated against the activity-adjusted expectation
import {
  DATA, loadPairs, pairEnds, communityColor, categoryColor, showTip, hideTip,
  fmtX, fmtInt, esc, communityLabel, categoryLabel, pairStats, REDUCED_MOTION,
} from "./core.js";

const SigmaCls = window.Sigma && (window.Sigma.Sigma || window.Sigma.default || window.Sigma);
const GraphCls = window.graphology && (window.graphology.Graph || window.graphology);
const DIM_NODE = "#2c2c2a";
const BG = [22, 22, 21];

/** Opaque colour = rgb mixed over the map background. sigma's WebGL blending expects premultiplied
 *  colours, so translucent rgba() edges would render at full brightness; pre-mixing avoids that. */
function mix(rgb, a) {
  const c = rgb.map((v, i) => Math.max(0, Math.min(255, Math.round(BG[i] + (v - BG[i]) * Math.max(0, Math.min(1, a))))));   // a channel outside 0–255 makes sigma fall back to its default colour
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
const hexRgb = (hex) => { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const anim = (ms) => (REDUCED_MOTION ? 0 : ms);

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
    this.el.innerHTML = `<div class="map-canvas"></div><div class="map-labels" aria-hidden="true"></div><div class="map-callouts" aria-hidden="true"></div>`;
    this.canvas = this.el.querySelector(".map-canvas");
    this.labelLayer = this.el.querySelector(".map-labels");
    this.calloutLayer = this.el.querySelector(".map-callouts");
    this.colorBy = "community";
    this.view = "adjusted";
    this.period = "all";
    this.focus = null;          // Set of node ids to emphasise
    this.focusEdges = null;     // Set of "i-j" keys to emphasise
    this.focusEdgeColor = "rgb(240,239,236)";
    this.selected = null;
    this.hovered = null;
    this.communityFilter = null;
    this.callouts = [];
    this.graph = new GraphCls({ type: "undirected", multi: false });
    for (const n of DATA.nodes) {
      this.graph.addNode(String(n.id), { x: n.x, y: n.y, size: 4, label: n.name, color: communityColor(n.community) });
    }
    this.renderer = new SigmaCls(this.graph, this.canvas, {
      renderLabels: true,
      allowInvalidContainer: true,   // a hidden or zero-size host must never throw; it renders once it has a size
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
    this.renderer.on("afterRender", () => { this.drawCommunityLabels(); this.drawCallouts(); });
    this.applyColors();
  }

  // ---------- data ----------
  async show({ period = this.period, view = this.view } = {}) {
    this.period = period; this.view = view;
    const p = await loadPairs(period);
    if (this.destroyed || this.period !== period || this.view !== view) return null;    // page left, or a newer request superseded this one
    this.pairs = p;
    this.graph.clearEdges();
    const maxUsers = Math.max(...p.users);
    DATA.nodes.forEach((n, i) => {
      const s = 2.2 + 13 * Math.sqrt((p.users[i] || 0) / maxUsers);
      this.graph.setNodeAttribute(String(i), "size", s * this.opts.sizeScale);
    });
    const validated = p.validatedSet;
    let lmax = 0;
    for (const k of p.validated) lmax = Math.max(lmax, Math.log(p.shared[k] / p.expected[k]));
    const addValidated = (k, i, j) => {
      const w = Math.log(p.shared[k] / p.expected[k]) / lmax;
      const ci = DATA.nodes[i].community, cj = DATA.nodes[j].community;
      const same = ci === cj;
      const color = same ? mix(hexRgb(communityColor(ci)), 0.3 + 0.5 * w) : mix([150, 149, 141], 0.1 + 0.2 * w);
      this.graph.addEdgeWithKey(`${i}-${j}`, String(i), String(j), { size: same ? 0.4 + 2.2 * w : 0.25 + 1.2 * w, color, k, validated: true, zIndex: 1 });
    };
    if (view === "adjusted") {
      for (const k of p.validated) { const [i, j] = pairEnds(k); addValidated(k, i, j); }
    } else {
      let cmax = 0;
      for (const c of p.cosine) if (c > cmax) cmax = c;
      for (let k = 0; k < p.shared.length; k++) {
        if (p.shared[k] <= 0) continue;
        const [i, j] = pairEnds(k);
        if (view === "surprise" && validated.has(k)) { addValidated(k, i, j); continue; }
        const w = p.cosine[k] / cmax;
        const grey = view === "surprise" ? mix([120, 119, 112], 0.1 + 0.16 * w) : mix([200, 199, 190], 0.12 + 0.5 * w);
        this.graph.addEdgeWithKey(`${i}-${j}`, String(i), String(j), { size: 0.2 + 1.2 * w, color: grey, k, validated: false, zIndex: 0 });
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
    if (this.selected != null && fly) this.flyTo([this.selected], 0.45, this.opts.flyOffset ? this.opts.flyOffset() : null);
    this.refresh();
  }
  /** Pin short text labels next to nodes: [{id, text, tone?}] */
  setCallouts(list) { this.callouts = list || []; this.calloutIds = new Set(this.callouts.map((c) => Number(c.id))); this.drawCallouts(); this.refresh(); }
  clearState() { this.selected = null; this.hovered = null; this.focus = null; this.focusEdges = null; this.communityFilter = null; this.callouts = []; this.refresh(); }

  /** Recompute the emphasised node set once, then redraw (reducers read the cached set). */
  refresh() { if (this.destroyed) return; this._act = this.activeSet(); this.renderer.refresh(); }

  neighbourSet(i) {
    const s = new Set([i]);
    this.graph.forEachNeighbor(String(i), (nb) => {
      if (this.view !== "surprise" || this.graph.getEdgeAttribute(this.graph.edge(String(i), nb), "validated")) s.add(Number(nb));
    });
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
    if (this.calloutIds && this.calloutIds.has(id)) { res.label = ""; res.forceLabel = false; }   // the callout already names it
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
        else if (this.view === "surprise" && !data.validated) res.hidden = true;
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
  /** Centre the camera on a set of nodes. `offset` = {dx, dy} in pixels moves where they land (dx > 0: left of centre, dy > 0: above). */
  flyTo(ids, minRatio = 0.25, offset = null) {
    const pts = ids.map((i) => this.renderer.getNodeDisplayData(String(i))).filter(Boolean);
    if (!pts.length) return;
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    const ratio = Math.min(1.1, Math.max(minRatio, span * 1.35));
    let target = { x: cx, y: cy, ratio };
    if (offset && (offset.dx || offset.dy)) {
      // the framed-graph point that would sit `offset` pixels from the centre once the nodes are centred becomes the new centre
      const { width, height } = this.renderer.getDimensions();
      const p = this.renderer.viewportToFramedGraph({ x: width / 2 + (offset.dx || 0), y: height / 2 + (offset.dy || 0) }, { cameraState: { x: cx, y: cy, ratio, angle: 0 } });
      target = { x: p.x, y: p.y, ratio };
    }
    this.renderer.getCamera().animate(target, { duration: anim(650) });
  }
  reset() { this.renderer.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1, angle: 0 }, { duration: anim(500) }); }
  zoom(f) { const c = this.renderer.getCamera(); c.animate({ ratio: c.ratio / f }, { duration: anim(250) }); }

  // ---------- overlays ----------
  drawCommunityLabels() {
    if (!this.opts.communityLabels || this.colorBy === "category") { this.labelLayer.innerHTML = ""; return; }
    const act = this._act;
    this.labelLayer.innerHTML = DATA.meta.communities.filter((c) => c.size > 1).map((c) => {
      const members = DATA.nodes.filter((n) => n.community === c.id);
      const xs = members.map((n) => n.x), ys = members.map((n) => n.y);
      const vp = this.renderer.graphToViewport({ x: xs.reduce((a, b) => a + b, 0) / xs.length, y: ys.reduce((a, b) => a + b, 0) / ys.length });
      const dim = act && !members.some((n) => act.has(n.id));
      return `<div style="left:${vp.x}px;top:${vp.y}px;opacity:${dim ? 0.15 : 0.9}"><i style="background:${communityColor(c.id)}"></i>${esc(c.label)}</div>`;
    }).join("");
  }
  drawCallouts() {
    if (!this.callouts.length) { this.calloutLayer.innerHTML = ""; return; }
    this.calloutLayer.innerHTML = this.callouts.map((c) => {
      const d = this.renderer.getNodeDisplayData(String(c.id));
      if (!d) return "";
      const vp = this.renderer.framedGraphToViewport({ x: d.x, y: d.y });
      // keep the label inside the stage: a callout nudged in from the edge is still readable, a clipped one is not
      const { width, height } = this.renderer.getDimensions();
      const x = Math.max(100, Math.min(width - 100, vp.x)), y = Math.max(30, Math.min(height - 30, vp.y));
      return `<div class="callout ${c.tone || ""}" style="left:${x}px;top:${y}px"><b>r/${esc(DATA.nodes[c.id].name)}</b>${c.text ? `<span>${esc(c.text)}</span>` : ""}</div>`;
    }).join("");
    // second pass: nudge any callout whose box still overflows the stage
    const L = this.calloutLayer.getBoundingClientRect();
    this.calloutLayer.querySelectorAll(".callout").forEach((el) => {
      const r = el.getBoundingClientRect(), left = parseFloat(el.style.left);
      if (r.left < L.left + 4) el.style.left = `${left + (L.left + 4 - r.left)}px`;
      else if (r.right > L.right - 4) el.style.left = `${left - (r.right - (L.right - 4))}px`;
    });
  }

  // ---------- events ----------
  bindEvents() {
    const r = this.renderer;
    r.on("enterNode", ({ node, event }) => {
      this.hovered = Number(node);
      this.refresh();
      const n = DATA.nodes[this.hovered];
      const rect = this.el.getBoundingClientRect();
      const deg = this.view === "surprise" ? this.neighbourSet(this.hovered).size - 1 : this.graph.degree(node);
      let pairLine = "";
      if (this.selected != null && this.selected !== this.hovered && this.pairs) {
        const s = pairStats(this.pairs, this.selected, this.hovered);
        pairLine = `<div class="t-row"><span>with r/${esc(DATA.nodes[this.selected].name)}</span><span>${s.validated ? fmtX(s.affinity) : s.avoided ? `${fmtX(s.affinity, 2)} (fewer than chance)` : "within chance"}</span></div>`;
      }
      showTip(`<b>r/${esc(n.name)}</b><div class="muted">${esc(categoryLabel(n.category))} · ${esc(communityLabel(n.community))}</div>
        <div class="t-row"><span>Commenters (${esc(this.period === "all" ? "all months" : this.period)})</span><span>${fmtInt(this.pairs ? this.pairs.users[n.id] : n.users)}</span></div>
        <div class="t-row"><span>${this.view === "raw" ? "Pairs sharing ≥1 commenter" : "Surprising links"}</span><span>${deg}</span></div>${pairLine}
        <div class="muted" style="margin-top:4px">Click to open</div>`,
        rect.left + event.x, rect.top + event.y);
    });
    r.on("leaveNode", () => { this.hovered = null; this.refresh(); hideTip(); });
    r.on("clickNode", ({ node }) => { this.opts.onSelect && this.opts.onSelect(Number(node)); });
    r.on("clickStage", () => { this.opts.onSelect && this.opts.onSelect(null); });
  }

  destroy() { this.destroyed = true; hideTip(); this.renderer.kill(); }
}

/** Overview-only map (no hover/click), used in the hero and small multiples. */
export function staticMap(container, opts = {}) {
  return new AtlasMap(container, { interactive: false, labelThreshold: 11, ...opts });
}
