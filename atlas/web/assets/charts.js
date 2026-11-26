// Minimal SVG line chart: 2px lines, recessive grid, crosshair tooltip, legend + direct end labels (<= 4 series).
import { showTip, hideTip, esc } from "./core.js";

/**
 * @param {HTMLElement} el
 * @param {{labels:string[], series:{name:string,color:string,values:(number|null)[],dashed?:boolean,points?:boolean[]}[],
 *          format?:(v:number)=>string, events?:{x:string,label:string}[], height?:number, yMin?:number, logY?:boolean, xTickEvery?:number}} cfg
 */
export function lineChart(el, cfg) {
  const direct = cfg.directLabels !== false && cfg.series.length <= 4;
  const longest = direct ? Math.min(24, Math.max(...cfg.series.map((s) => s.name.length))) : 0;
  const W = Math.max(320, Math.round(el.clientWidth || 640)), H = cfg.height || 260, m = { t: 14, r: direct ? Math.round(12 + 6.4 * longest) : 16, b: 28, l: 52 };
  const fmt = cfg.format || ((v) => v.toLocaleString("en-US"));
  const all = cfg.series.flatMap((s) => s.values).filter((v) => v != null && isFinite(v));
  if (!all.length) { el.innerHTML = `<div class="empty">No data for this selection.</div>`; return; }
  const tf = cfg.logY ? Math.log : (v) => v;
  let lo = cfg.yMin != null ? cfg.yMin : Math.min(...all), hi = Math.max(...all);
  if (!cfg.logY && cfg.yMin == null) lo = Math.min(0, lo);
  if (hi === lo) hi = lo + 1;
  const tlo = tf(lo), thi = tf(hi) + (tf(hi) - tf(lo)) * 0.06;
  const n = cfg.labels.length;
  const x = (i) => m.l + (n === 1 ? 0.5 : i / (n - 1)) * (W - m.l - m.r);
  const y = (v) => m.t + (1 - (tf(v) - tlo) / (thi - tlo)) * (H - m.t - m.b);
  const ticks = niceTicks(lo, hi, 4, cfg.logY);
  const every = cfg.xTickEvery || Math.ceil(n / 8);
  const path = (vals) => {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (v == null || !isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    });
    return d;
  };
  const evs = (cfg.events || []).map((e) => ({ ...e, i: nearestIndex(cfg.labels, e.x) })).filter((e) => e.i != null);
  // direct labels, nudged apart vertically
  const ends = direct ? cfg.series.map((s) => {
    let i = s.values.length - 1; while (i >= 0 && (s.values[i] == null || !isFinite(s.values[i]))) i--;
    return i < 0 ? null : { s, yy: y(s.values[i]) };
  }).filter(Boolean).sort((a, b) => a.yy - b.yy) : [];
  for (let k = 1; k < ends.length; k++) if (ends[k].yy - ends[k - 1].yy < 14) ends[k].yy = ends[k - 1].yy + 14;

  el.classList.add("chart");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.ariaLabel || "line chart")}">
    <g class="grid">${ticks.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/>`).join("")}</g>
    <g class="axis">${ticks.map((t) => `<text x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end">${esc(fmt(t))}</text>`).join("")}
      ${cfg.labels.map((l, i) => (i % every === 0 || i === n - 1) && !(i === n - 1 && (n - 1) % every !== 0 && (n - 1) % every < every / 2)
        ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(cfg.tickFormat ? cfg.tickFormat(l) : l)}</text>` : "").join("")}</g>
    <g class="event">${evs.map((e, k) => `<line x1="${x(e.i)}" x2="${x(e.i)}" y1="${m.t}" y2="${H - m.b}"/><text x="${x(e.i) + 4}" y="${m.t + 10 + 13 * (k % 2)}">${esc(e.short ?? e.label)}</text>`).join("")}</g>
    <g class="series">${cfg.series.map((s) => `<path d="${path(s.values)}" stroke="${s.color}" ${s.dashed ? 'stroke-dasharray="5 4"' : ""}/>
      ${s.points ? s.values.map((v, i) => v == null ? "" : `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${s.points[i] ? s.color : "var(--surface-1)"}" stroke="${s.color}" stroke-width="2"/>`).join("") : ""}`).join("")}</g>
    <g class="axis">${ends.map((e) => `<text x="${W - m.r + 8}" y="${e.yy + 4}" style="fill:var(--text-secondary)">${esc(trunc(e.s.name, 24))}</text>`).join("")}</g>
    <g class="cross" visibility="hidden"><line y1="${m.t}" y2="${H - m.b}"/></g>
    <rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/>
  </svg>
  ${cfg.series.length >= 2 ? `<div class="chart-legend">${cfg.series.map((s) => `<span><i style="background:${s.color};${s.dashed ? "background:repeating-linear-gradient(90deg," + s.color + " 0 5px,transparent 5px 8px)" : ""}"></i>${esc(s.name)}</span>`).join("")}</div>` : ""}`;

  const svg = el.querySelector("svg"), cross = svg.querySelector(".cross"), line = cross.querySelector("line");
  svg.querySelector("rect").addEventListener("mousemove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / (W - m.l - m.r)) * (n - 1))));
    line.setAttribute("x1", x(i)); line.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    const ev = evs.filter((v) => v.i === i).map((v) => `<div class="muted">${esc(v.label)}</div>`).join("");
    showTip(`<b>${esc(cfg.tickFormat ? cfg.tickFormat(cfg.labels[i], true) : cfg.labels[i])}</b>${ev}${cfg.series.map((s) =>
      `<div class="t-row"><span><span class="dot" style="display:inline-block;background:${s.color}"></span> ${esc(s.name)}</span><span>${s.values[i] == null ? "–" : esc(fmt(s.values[i]))}${s.points ? (s.points[i] ? " ✓" : " ·") : ""}</span></div>`).join("")}`,
      e.clientX, e.clientY);
  });
  svg.querySelector("rect").addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
}

function trunc(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function nearestIndex(labels, x) {
  const k = labels.findIndex((l) => l >= x);
  return k < 0 ? null : k;
}
function niceTicks(lo, hi, count, log) {
  if (log) {
    const out = [];
    for (let p = Math.floor(Math.log10(lo)); p <= Math.ceil(Math.log10(hi)); p++) for (const f of [1, 2, 5]) {
      const v = f * 10 ** p; if (v >= lo * 0.999 && v <= hi * 1.06) out.push(v);
    }
    return out.length >= 2 ? out : [lo, hi];
  }
  const step0 = (hi - lo) / count, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((s) => s >= step0) || step0;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi * 1.0001; v += step) out.push(+v.toFixed(10));
  return out;
}

export const monthTick = (m, long) => {
  const [yy, mm] = m.split("-").map(Number);
  const d = new Date(Date.UTC(yy, mm - 1, mm && m.length > 7 ? Number(m.slice(8)) : 1));
  return d.toLocaleDateString("en-GB", long ? { day: m.length > 7 ? "numeric" : undefined, month: "short", year: "numeric", timeZone: "UTC" } : { month: "short", ...(m.length > 7 ? { day: "numeric" } : {}), timeZone: "UTC" });
};

/**
 * Horizontal bar chart. rows: [{label, value, color?, note?}], format(v) for the value label.
 */
export function barChart(el, { rows, format = (v) => v.toLocaleString("en-US"), max = null, ariaLabel = "bar chart" }) {
  const vmax = max || Math.max(...rows.map((r) => r.value), 1);
  el.classList.add("chart");
  el.innerHTML = `<div class="hbars" role="img" aria-label="${esc(ariaLabel)}">${rows.map((r) => `
    <div class="hbar-row">
      <span class="hbar-label">${esc(r.label)}</span>
      <span class="hbar-track"><span class="hbar-fill" style="width:${Math.max(1, (100 * r.value) / vmax).toFixed(1)}%;background:${r.color || "var(--accent)"}"></span></span>
      <span class="hbar-val">${esc(format(r.value))}${r.note ? `<small> ${esc(r.note)}</small>` : ""}</span>
    </div>`).join("")}</div>`;
}
