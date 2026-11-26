// Reply-network component for the Findings section: a precomputed, anonymised core (≤150 users) rendered with sigma.js.
// Colour by cluster, tone or self-declared camp; isolate a cluster; highlight brokers; inspect a user's ties.
import { PALETTE, esc, showTip, hideTip } from "./core.js";

const SigmaCls = window.Sigma && (window.Sigma.Sigma || window.Sigma.default || window.Sigma);
const GraphCls = window.graphology && (window.graphology.Graph || window.graphology);
const BG = [22, 22, 21];
const DIM = "#2c2c2a";
export const GROUP_COLORS = { left: "#d95926", right: "#3987e5", centre: "#c98500", red: "#d95926", blue: "#3987e5", purple: "#9085e9", black: "#8e8d86" };

function mix(rgb, a) {
  const f = Math.max(0, Math.min(1, a));
  const c = rgb.map((v, i) => Math.max(0, Math.min(255, Math.round(BG[i] + (v - BG[i]) * f))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
export const toneColor = (v) => (v == null ? "#8e8d86" : v <= -0.05 ? mix([217, 89, 38], 0.45 + Math.min(0.55, -v)) : v >= 0.05 ? mix([57, 135, 229], 0.45 + Math.min(0.55, v)) : "#8e8d86");
export const clusterColor = (c) => (c < PALETTE.length ? PALETTE[c] : "#6f6e68");   // the eight largest clusters get colours; smaller ones are grey

export class FocusNet {
  constructor(el, { onSelect = null } = {}) {
    this.el = el;
    this.onSelect = onSelect;
    this.graph = new GraphCls({ type: "undirected", multi: false });
    this.canvas = document.createElement("div");
    this.canvas.style.cssText = "position:absolute;inset:0";
    el.appendChild(this.canvas);
    this.mode = "community"; this.focus = null; this.brokers = false; this.selected = null; this.hovered = null; this.net = null; this.destroyed = false;
    this.renderer = new SigmaCls(this.graph, this.canvas, {
      renderLabels: true, allowInvalidContainer: true, labelRenderedSizeThreshold: 9, labelFont: getComputedStyle(document.body).fontFamily,
      labelSize: 11, labelWeight: "500", labelColor: { color: "#d8d7d0" }, defaultEdgeType: "line", zIndex: true, minCameraRatio: 0.15, maxCameraRatio: 2.5,
      enableEdgeHoverEvents: false, nodeReducer: (k, d) => this.nodeReducer(k, d), edgeReducer: (k, d) => this.edgeReducer(k, d),
    });
    const r = this.renderer;
    r.on("enterNode", ({ node, event }) => { this.hovered = node; this.refresh(); this.tip(node, event); });
    r.on("leaveNode", () => { this.hovered = null; this.refresh(); hideTip(); });
    r.on("clickNode", ({ node }) => { this.select(this.selected === node ? null : node); });
    r.on("clickStage", () => this.select(null));
  }

  show(net, brokerIds = null) {
    this.net = net; this.selected = null; this.hovered = null; this.focus = null;
    this.graph.clear();
    const maxDeg = Math.max(1, ...net.nodes.map((n) => n.degree));
    net.nodes.forEach((n) => this.graph.addNode(n.id, { x: n.x, y: 1 - n.y, size: 3 + 11 * Math.sqrt(n.degree / maxDeg), label: n.id, data: n }));
    net.edges.forEach((e) => { if (!this.graph.hasEdge(e.s, e.t)) this.graph.addEdge(e.s, e.t, { w: e.w, size: 0.6 + Math.min(3, Math.log2(e.w + 1)) }); });
    // the highlighted brokers are the Brokers table's rows (full-network rule) when the page passes them; the core-only rule is the fallback
    this.brokerIds = brokerIds ? new Set([...brokerIds].filter((id) => this.graph.hasNode(id)))
      : new Set(net.nodes.filter((n) => n.participation >= 0.6 && n.reached >= 3).sort((a, b) => b.betweenness - a.betweenness).slice(0, 5).map((n) => n.id));
    this.refresh();
    this.renderer.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 0 });
  }

  setMode(m) { this.mode = m; this.refresh(); }
  setFocus(c) { this.focus = c; this.refresh(); }
  setBrokers(b) { this.brokers = b; this.refresh(); }
  select(id) { this.selected = id; this.refresh(); if (this.onSelect) this.onSelect(id ? this.graph.getNodeAttribute(id, "data") : null); }
  reset() { this.renderer.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 400 }); }
  refresh() { if (!this.destroyed) this.renderer.refresh(); }
  destroy() { this.destroyed = true; hideTip(); try { this.renderer.kill(); } catch (e) { /* already gone */ } }

  colorOf(d) {
    if (this.mode === "sentiment") return toneColor(d.sentiment);
    if (this.mode === "group") return d.group ? (GROUP_COLORS[d.group] || "#8e8d86") : "#56554f";
    return clusterColor(d.community);
  }
  active(id, d) {
    if (this.selected) return id === this.selected || this.graph.areNeighbors(id, this.selected);
    if (this.focus != null) return d.community === this.focus;
    return true;
  }
  nodeReducer(id, attrs) {
    const d = attrs.data, res = { ...attrs };
    const act = this.active(id, d);
    res.color = act ? this.colorOf(d) : DIM;
    res.zIndex = act ? 2 : 0;
    const broker = this.brokers && this.brokerIds.has(id);
    if (broker && act) { res.size = attrs.size * 1.35; res.forceLabel = true; res.zIndex = 3; }
    if (id === this.selected || id === this.hovered) { res.highlighted = true; res.forceLabel = true; res.zIndex = 4; }
    if (!act) res.label = "";
    return res;
  }
  edgeReducer(key, attrs) {
    const [a, b] = this.graph.extremities(key);
    const da = this.graph.getNodeAttribute(a, "data"), db = this.graph.getNodeAttribute(b, "data");
    const res = { ...attrs };
    const actA = this.active(a, da), actB = this.active(b, db);
    if (this.selected && (a === this.selected || b === this.selected)) { res.color = mix([240, 239, 236], 0.9); res.size = attrs.size * 1.6; res.zIndex = 3; return res; }
    if (this.hovered && (a === this.hovered || b === this.hovered)) { res.color = mix([240, 239, 236], 0.7); res.zIndex = 2; return res; }
    if (!actA || !actB) { res.color = mix([80, 80, 78], 0.35); res.zIndex = 0; return res; }
    if (this.brokers && (this.brokerIds.has(a) || this.brokerIds.has(b))) { res.color = mix([201, 133, 0], 0.8); res.zIndex = 2; return res; }
    if (this.mode === "community" && da.community === db.community) { res.color = mix(hex(clusterColor(da.community)), 0.45); return res; }
    res.color = mix([160, 159, 150], 0.4);
    return res;
  }
  tip(id, event) {
    const d = this.graph.getNodeAttribute(id, "data");
    const rect = this.el.getBoundingClientRect();
    const rows = [["Cluster", `${d.community + 1}`], ["Reply ties", `${d.degree} users · ${d.strength} replies`], ["Betweenness", d.betweenness.toFixed(3)],
      ["Participation", d.participation.toFixed(2)], ["Clusters reached", d.reached]];
    if (d.sentiment != null) rows.push(["Mean tone", (d.sentiment >= 0 ? "+" : "") + d.sentiment.toFixed(2)]);
    if (d.group) rows.push(["Camp", d.group]);
    showTip(`<div class="t-title">${esc(id)}${this.brokerIds.has(id) ? ' <span class="hub">broker</span>' : ""}</div>${rows.map(([k, v]) => `<div class="t-row"><span>${k}</span><span>${esc(String(v))}</span></div>`).join("")}`,
      rect.left + event.x, rect.top + event.y);
  }
}
