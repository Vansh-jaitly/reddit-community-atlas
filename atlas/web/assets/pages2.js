// Compare, Discoveries (stories), How it's made (pipeline) and Scope & limits (about) pages.
import {
  DATA, loadPairs, loadPipeline, neighbours, pairStats, pairEnds, communityColor, categoryColor, categoryLabel, communityLabel,
  fmtInt, fmtPct, fmtX, fmtP, fmtCompact, esc, periodLabel, monthLabel, hashFor, replaceParams, searchBox, pairVerdict, registerPage,
  isMobile, REDUCED_MOTION, communitiesPhrase, setOn, SHOT,
} from "./core.js";
import { AtlasMap } from "./map.js";
import { lineChart, barChart, monthTick } from "./charts.js";
import { legendHTML } from "./pages.js";

const node = (name) => (name ? DATA.byName.get(String(name).toLowerCase()) : null);
const link = (n) => `<a href="#/explore/${encodeURIComponent(n.name)}">r/${esc(n.name)}</a>`;
const months = () => DATA.meta.periods.filter((p) => p.kind === "month").map((p) => p.id);
const quarters = () => DATA.meta.summary.quarters;
const scrollTo = (el) => el && !SHOT && el.scrollIntoView({ behavior: REDUCED_MOTION ? "auto" : "smooth", block: "start" });

// ======================================================================
// Compare
// ======================================================================
export function renderCompare(main, { params }) {
  const mode = params.mode === "periods" ? "periods" : "pair";
  main.innerHTML = `<div class="page">
    <div class="eyebrow">Compare &amp; time travel</div>
    <h1 style="font-size:34px;margin-bottom:14px">${mode === "pair" ? "How close are two communities — and does it last?" : "What changed between two periods?"}</h1>
    <div class="seg" id="c-mode" style="margin-bottom:22px"><button data-m="pair" class="${mode === "pair" ? "on" : ""}">Two communities</button><button data-m="periods" class="${mode === "periods" ? "on" : ""}">Two periods</button></div>
    <div id="c-body"></div></div>`;
  main.querySelectorAll("#c-mode button").forEach((b) => b.addEventListener("click", () => { location.hash = hashFor("compare", [], { mode: b.dataset.m === "periods" ? "periods" : null }); }));
  return mode === "pair" ? comparePair(main.querySelector("#c-body"), params) : comparePeriods(main.querySelector("#c-body"), params);
}

function comparePair(box, params) {
  let a = node(params.a), b = node(params.b);
  box.innerHTML = `<div class="toolbar"><div class="field" style="flex:1;max-width:340px"><label>First subreddit</label><div id="c-a"></div></div>
    <div class="field" style="flex:1;max-width:340px"><label>Second subreddit</label><div id="c-b"></div></div></div><div id="c-out" style="margin-top:22px"></div>`;
  const go = () => { replaceParams("compare", [], { a: a && a.name, b: b && b.name }); draw(); };
  searchBox(box.querySelector("#c-a"), { value: a ? `r/${a.name}` : "", onPick: (n) => { a = n; go(); } });
  searchBox(box.querySelector("#c-b"), { value: b ? `r/${b.name}` : "", onPick: (n) => { b = n; go(); } });
  const out = box.querySelector("#c-out");
  let ready = Promise.resolve();

  async function draw() {
    if (!a || !b || a.id === b.id) {
      const sug = DATA.stories.stories.find((s) => s.id === "neighbours");
      const ex = sug ? sug.metrics.top_links.slice(0, 5) : [];
      out.innerHTML = `<div class="empty">${a && b ? "Pick two different subreddits." : "Pick two subreddits to compare."}
        ${ex.length ? `<div style="margin-top:12px">Try: ${ex.map((x) => `<a href="${hashFor("compare", [], { a: x.a, b: x.b })}">r/${esc(x.a)} vs r/${esc(x.b)}</a>`).join(" · ")}</div>` : ""}</div>`;
      out.querySelectorAll("a").forEach((el) => el.addEventListener("click", (e) => { e.preventDefault(); const q = new URLSearchParams(el.getAttribute("href").split("?")[1]); a = node(q.get("a")); b = node(q.get("b")); box.querySelector("#c-a input").value = `r/${a.name}`; box.querySelector("#c-b input").value = `r/${b.name}`; go(); }));
      return;
    }
    const all = await loadPairs("all");
    const qs = quarters(), ms = months();
    const qp = await Promise.all(qs.map(loadPairs));
    const mp = await Promise.all(ms.map(loadPairs));
    const s = pairStats(all, a.id, b.id);
    const rows = [["all", all], ...qs.map((q, k) => [q, qp[k]])].map(([pid, p]) => ({ pid, ...pairStats(p, a.id, b.id), ua: p.users[a.id], ub: p.users[b.id] }));
    const na = neighbours(all, a.id), nb = neighbours(all, b.id);
    const nbMap = new Map(nb.map((x) => [x.j, x]));
    const common = na.filter((x) => nbMap.has(x.j)).map((x) => ({ j: x.j, a: x.affinity, b: nbMap.get(x.j).affinity })).sort((u, v) => Math.min(v.a, v.b) - Math.min(u.a, u.b));
    const status = (r) => (r.validated ? `<span class="tag ok">surprising</span>` : r.avoided ? `<span class="tag low">fewer than chance</span>` : `<span class="tag">within chance</span>`);
    out.innerHTML = `
      <div class="panel verdict ${s.validated ? "ok" : s.avoided ? "low" : ""}">${pairVerdict(s, a.name, b.name)}
        <div class="muted" style="font-size:12.5px;margin-top:8px">Whole window. Test: one-sided Poisson against the expected overlap, false discovery rate 1% over all pairs${s.pHigh != null ? ` · p (more than chance) = ${fmtP(s.pHigh)} · p (fewer than chance) = ${fmtP(s.pLow)}` : ""}.</div></div>
      <div class="section grid2" style="margin-top:18px">
        <div class="panel"><div class="chart-title">Affinity month by month</div><div class="chart-sub">Filled point = significant that month. 1.0× = chance.</div><div id="c-chart"></div></div>
        <div class="panel"><div class="chart-title">By period</div><table class="data"><thead><tr><th>Period</th><th class="r">Shared</th><th class="r">Expected</th><th class="r">Affinity</th><th>Status</th></tr></thead><tbody>
          ${rows.map((r) => `<tr><td>${esc(periodLabel(r.pid))}</td><td class="r">${fmtInt(r.shared)}</td><td class="r">${fmtInt(r.expected)}</td><td class="r">${fmtX(r.affinity, 2)}</td><td>${status(r)}</td></tr>`).join("")}
        </tbody></table>
        <div class="chart-sub" style="margin-top:12px">Commenters over the whole window: ${link(a)} ${fmtInt(rows[0].ua)} · ${link(b)} ${fmtInt(rows[0].ub)}</div></div>
      </div>
      <div class="section panel"><div class="chart-title">Communities both are surprisingly close to</div>
        <div class="chart-sub">Validated with both over the whole window, ranked by the weaker of the two links.</div>
        ${common.length ? `<table class="data"><thead><tr><th>Subreddit</th><th>Community</th><th class="r">with r/${esc(a.name)}</th><th class="r">with r/${esc(b.name)}</th></tr></thead><tbody>${common.slice(0, 12).map((c) => `<tr><td>${link(DATA.nodes[c.j])}</td><td><span class="dot" style="display:inline-block;background:${communityColor(DATA.nodes[c.j].community)}"></span> ${esc(communityLabel(DATA.nodes[c.j].community))}</td><td class="r">${fmtX(c.a)}</td><td class="r">${fmtX(c.b)}</td></tr>`).join("")}</tbody></table>` : `<div class="empty">${s.validated ? "They are surprisingly close to each other and to no third community in common: a pair of their own." : "No third community is surprisingly close to both."}</div>`}</div>
      <div class="cta-row" style="margin-top:18px"><a class="btn" href="${hashFor("atlas", [], { sel: a.id })}">Show r/${esc(a.name)} on the map</a><a class="btn" href="${hashFor("atlas", [], { sel: b.id })}">Show r/${esc(b.name)} on the map</a></div>`;
    const st = mp.map((p) => pairStats(p, a.id, b.id));
    lineChart(out.querySelector("#c-chart"), {
      labels: ms, tickFormat: (m, long) => monthTick(m, long), format: (v) => fmtX(v, 2), yMin: 0,
      series: [{ name: `r/${a.name} – r/${b.name}`, color: "#3987e5", values: st.map((x) => (x.expected > 0 ? x.affinity : null)), points: st.map((x) => x.validated) },
               { name: "chance (1.0×)", color: "#8e8d86", dashed: true, values: ms.map(() => 1) }],
    });
  }
  ready = draw();
  registerPage({ name: "compare", get ready() { return ready; }, setPair: (x, y) => { a = node(x); b = node(y); go(); } });
  return null;
}

function comparePeriods(box, params) {
  const qs = quarters();
  const ids = DATA.meta.periods.filter((p) => p.kind !== "pooled").map((p) => p.id);
  let p1 = ids.includes(params.p1) ? params.p1 : qs[0], p2 = ids.includes(params.p2) ? params.p2 : qs.at(-1);
  const opts = (sel) => DATA.meta.periods.filter((p) => p.kind !== "pooled").map((p) => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.label)}</option>`).join("");
  box.innerHTML = `<div class="toolbar">
      <div class="field"><label for="c-p1">Before</label><select id="c-p1">${opts(p1)}</select></div>
      <div class="field"><label for="c-p2">After</label><select id="c-p2">${opts(p2)}</select></div></div>
    <div class="kpis" id="c-kpis"></div><p class="muted" id="c-base" style="margin-top:12px"></p>
    <div class="split-maps section" style="margin-top:20px">
      <div class="map-wrap" id="c-m1"><div class="map-host" style="position:absolute;inset:0"></div><span class="chip tag-float" id="c-t1"></span></div>
      <div class="map-wrap" id="c-m2"><div class="map-host" style="position:absolute;inset:0"></div><span class="chip tag-float" id="c-t2"></span></div></div>
    <div class="section grid2"><div class="panel"><div class="chart-title">Strongest links that appeared</div><div class="chart-sub" id="c-gsub"></div><div id="c-gained"></div></div>
      <div class="panel"><div class="chart-title">Strongest links that disappeared</div><div class="chart-sub" id="c-lsub"></div><div id="c-lost"></div></div></div>`;
  const onSel = (i) => { m1.select(i, { fly: false }); m2.select(i, { fly: false }); };
  const m1 = new AtlasMap(box.querySelector("#c-m1 .map-host"), { communityLabels: false, labelThreshold: 12, onSelect: onSel });
  const m2 = new AtlasMap(box.querySelector("#c-m2 .map-host"), { communityLabels: false, labelThreshold: 12, onSelect: onSel });
  let ready = Promise.resolve();
  async function draw() {
    replaceParams("compare", [], { mode: "periods", p1, p2 });
    const [a, b] = await Promise.all([loadPairs(p1), loadPairs(p2)]);
    const A = new Set(a.validated), B = new Set(b.validated);
    const kept = [...A].filter((k) => B.has(k)), gained = [...B].filter((k) => !A.has(k)), lost = [...A].filter((k) => !B.has(k));
    const jac = kept.length / (A.size + B.size - kept.length);
    box.querySelector("#c-kpis").innerHTML = `
      <div class="stat"><b>${fmtInt(A.size)} → ${fmtInt(B.size)}</b><span>surprising links</span></div>
      <div class="stat"><b>${fmtInt(kept.length)}</b><span>persisted</span></div>
      <div class="stat"><b>${fmtInt(gained.length)}</b><span>appeared</span></div>
      <div class="stat"><b>${fmtInt(lost.length)}</b><span>disappeared</span></div>
      <div class="stat"><b>${jac.toFixed(2)}</b><span>overlap (Jaccard)</span></div>`;
    const mj = Object.values(DATA.meta.summary.month_edge_jaccard), qj = Object.values(DATA.meta.summary.quarter_edge_jaccard);
    const adjacent = (list) => list.includes(p1) && list.includes(p2) && Math.abs(list.indexOf(p2) - list.indexOf(p1)) === 1;
    const consecutive = adjacent(DATA.meta.summary.quarters) || adjacent(DATA.meta.summary.months);
    box.querySelector("#c-base").textContent = `Most links persist; the ones that appear or disappear are mostly near the significance cut-off. For reference, consecutive months keep ${Math.min(...mj).toFixed(2)}–${Math.max(...mj).toFixed(2)} of their links (Jaccard) and consecutive quarters ${Math.min(...qj).toFixed(2)}–${Math.max(...qj).toFixed(2)}${consecutive ? "" : "; these two periods are not consecutive, so expect somewhat less overlap"}. Changes smaller than that are normal churn, not news.`;
    box.querySelector("#c-t1").innerHTML = `<span class="dot" style="background:#d95926"></span>${esc(periodLabel(p1))} · the 12 strongest links that later disappeared`;
    box.querySelector("#c-t2").innerHTML = `<span class="dot" style="background:#3987e5"></span>${esc(periodLabel(p2))} · the 12 strongest links that appeared`;
    await Promise.all([m1.show({ period: p1 }), m2.show({ period: p2 })]);
    // "strongest" needs support: rank only links with expected >= 5 so a 3-vs-0.2 pair cannot top the list
    const rank = (list, p) => list.filter((k) => p.expected[k] >= 5).map((k) => ({ k, aff: p.shared[k] / p.expected[k], shared: p.shared[k], expected: p.expected[k] })).sort((u, v) => v.aff - u.aff);
    const g = rank(gained, b), l = rank(lost, a);
    m1.setFocus(null, l.slice(0, 12).map((x) => pairEnds(x.k)), "rgb(217,89,38)");
    m2.setFocus(null, g.slice(0, 12).map((x) => pairEnds(x.k)), "rgb(57,135,229)");
    box.querySelector("#c-gsub").textContent = `Significant in ${periodLabel(p2)} but not in ${periodLabel(p1)}; affinity in ${periodLabel(p2)}.`;
    box.querySelector("#c-lsub").textContent = `Significant in ${periodLabel(p1)} but not in ${periodLabel(p2)}; affinity in ${periodLabel(p1)}.`;
    const list = (arr) => arr.length ? `<div class="pill-list">${arr.slice(0, 12).map((x) => {
      const [i, j] = pairEnds(x.k);
      return `<a href="${hashFor("compare", [], { a: DATA.nodes[i].name, b: DATA.nodes[j].name })}"><span>r/${esc(DATA.nodes[i].name)} – r/${esc(DATA.nodes[j].name)}</span><span>${fmtX(x.aff)} · ${fmtInt(x.shared)} of ${fmtInt(x.expected)}</span></a>`;
    }).join("")}</div>` : `<div class="empty">None.</div>`;
    box.querySelector("#c-gained").innerHTML = list(g);
    box.querySelector("#c-lost").innerHTML = list(l);
  }
  box.querySelector("#c-p1").addEventListener("change", (e) => { p1 = e.target.value; ready = draw(); });
  box.querySelector("#c-p2").addEventListener("change", (e) => { p2 = e.target.value; ready = draw(); });
  ready = draw();
  registerPage({ name: "compare", get ready() { return ready; } });
  return () => { m1.destroy(); m2.destroy(); };
}

// ======================================================================
// Discoveries (guided stories)
// ======================================================================
const TAKEAWAYS = {
  popularity: "A raw shared-audience map mostly measures size. Compare what a pair shares with what chance predicts before calling two communities close.",
  neighbours: "The same test that finds surprising neighbours also finds strangers. Which audiences meet is a fact in the data; why is not.",
  connectors: "The communities that bridge this map are mid-sized and topical; clusters differ in how sealed they are; the giants keep every surprising link inside their own cluster.",
  crowds: "Crowds leave a clear trace in the counts, but a changed affinity is not by itself a changed behaviour: check the share of commenters who actually cross over.",
};

function investigateActions(st) {
  const m = st.metrics, acts = [];
  const explore = (name, label) => node(name) && acts.push({ label: label || `Open r/${name}`, href: `#/explore/${encodeURIComponent(node(name).name)}` });
  const compare = (x, y, label) => node(x) && node(y) && acts.push({ label: label || `Compare r/${x} and r/${y}`, href: hashFor("compare", [], { a: node(x).name, b: node(y).name }) });
  if (st.id === "popularity") { if (m.giant_pair) compare(m.giant_pair.a, m.giant_pair.b); explore(m.example); acts.push({ label: "See the raw hairball", href: hashFor("atlas", [], { view: "raw" }) }); }
  else if (st.id === "neighbours") { const t = m.top_links[0]; compare(t.a, t.b); if (m.country && m.country.same_topic_across_border) { const x = m.country.same_topic_across_border[0]; compare(x.a, x.b, `Compare r/${x.a} and r/${x.b} (the control)`); } if (m.lowest_pairs && m.lowest_pairs[0]) compare(m.lowest_pairs[0].a, m.lowest_pairs[0].b, `Compare r/${m.lowest_pairs[0].a} and r/${m.lowest_pairs[0].b}`); explore(t.a); }
  else if (st.id === "connectors") { const c = m.connectors; explore(c[0].name); acts.push({ label: `Show r/${c[0].name}'s links on the map`, href: hashFor("atlas", [], { sel: node(c[0].name).id }) }); if (m.giants) explore(m.giants.name); }
  else if (st.id === "crowds") { const k = Object.keys(m.crypto_pair_affinity)[0].split("|"); compare(k[0], k[1]); explore(k[0]); if (m.starwars) explore(m.starwars.name); acts.push({ label: `Compare ${monthLabel(m.baseline_month, true)} with ${monthLabel(m.months.at(-1), true)}`, href: hashFor("compare", [], { mode: "periods", p1: m.baseline_month, p2: m.months.at(-1) }) }); }
  acts.push({ label: "Open the map", href: "#/atlas" });
  return acts;
}

export function renderStories(main, { args, params }) {
  const stories = DATA.stories.stories;
  if (!args[0]) return renderStoriesIndex(main);
  const story = stories.find((s) => s.id === args[0]) || stories[0];
  const nSteps = story.steps.length + 1;                 // + the takeaway step
  const step0 = parseInt(params.step, 10);
  let step = Number.isFinite(step0) ? Math.max(0, Math.min(nSteps - 1, step0)) : 0;
  main.innerHTML = `<div class="story-layout">
    <div class="map-wrap" id="s-wrap"><div class="map-host" style="position:absolute;inset:0"></div><div class="map-note" id="s-note"></div></div>
    <aside class="story-panel">
      <div class="story-tabs">${stories.map((s, k) => `<button data-id="${s.id}" class="${s.id === story.id ? "on" : ""}">${k + 1}. ${esc(s.title)}</button>`).join("")}</div>
      <div class="story-body" id="s-body"></div>
      <div class="story-nav"><div class="pips">${Array.from({ length: nSteps }, (_, k) => `<i data-k="${k}"></i>`).join("")}</div>
        <button class="btn" id="s-prev">← Back</button><button class="btn primary" id="s-next">Next →</button></div>
    </aside></div>`;
  const map = new AtlasMap(main.querySelector(".map-host"), { onSelect: (i) => map.select(i) });
  const wrap = main.querySelector("#s-wrap");
  main.querySelectorAll(".story-tabs button").forEach((b) => b.addEventListener("click", () => { location.hash = `#/stories/${b.dataset.id}`; }));
  main.querySelector("#s-prev").addEventListener("click", () => go(step - 1));
  main.querySelector("#s-next").addEventListener("click", () => {
    if (step < nSteps - 1) go(step + 1);
    else { const k = stories.indexOf(story); location.hash = k < stories.length - 1 ? `#/stories/${stories[k + 1].id}` : "#/atlas"; }
  });
  let ready = Promise.resolve();

  async function go(k) {
    step = Math.max(0, Math.min(nSteps - 1, k));
    replaceParams("stories", [story.id], { step: step || null });
    const last = step === nSteps - 1;
    const s = last ? { ...story.steps.at(-1), view: "adjusted", text: null } : story.steps[step];
    main.querySelectorAll(".pips i").forEach((el, j) => setOn(el, j === step));
    main.querySelector("#s-prev").disabled = step === 0;
    main.querySelector("#s-next").textContent = !last ? "Next →" : (stories.indexOf(story) < stories.length - 1 ? "Next discovery →" : "Open the map →");
    const period = s.view === "timeline" ? (DATA.meta.periods.some((p) => p.id === s.period) ? s.period : "all") : s.period || "all";
    const overlay = wrap.querySelector(".timeline-overlay");
    if (overlay) overlay.remove();
    if (s.colorBy) map.setColorBy(s.colorBy);
    await map.show({ period, view: s.view === "raw" ? "raw" : "adjusted" });
    map.select(null, { fly: false });
    const focus = s.view === "raw" ? null : (s.focus && s.focus.length ? s.focus : null);   // the raw view must show every line
    map.setFocus(focus, s.edges || (s.edge ? [s.edge] : null));
    map.setCallouts((s.callouts || (s.edge ? s.edge : [])).map((id) => ({ id })));
    if (s.select != null && !s.edge) map.select(s.select, { fly: false });
    if (focus && focus.length) map.flyTo(focus, 0.3); else map.reset();
    main.querySelector("#s-note").textContent = `${periodLabel(period)} · ${s.view === "raw" ? "raw overlap" : s.view === "timeline" && !last ? "monthly commenters (chart); map behind shows surprising links" : "surprising links only"}`;
    if (s.view === "timeline" && !last) timeline(s);
    body(s, last);
    if (isMobile()) scrollTo(main.querySelector(".story-panel"));
  }

  function timeline(s) {
    const el = document.createElement("div");
    el.className = "timeline-overlay";
    const m = story.metrics, ms = m.months;
    const idx = (arr) => arr.map((v) => (arr[0] ? (100 * v) / arr[0] : null));
    let src, title, cmpName;
    if (s.group === "marvel") { src = m.marvel_monthly_authors; title = "The Infinity War crowd"; cmpName = "movies"; }
    else if (s.group === "starwars" && m.starwars) { src = { [m.starwars.name]: m.starwars.monthly_authors }; title = "The Last Jedi crowd"; cmpName = "movies"; }
    else { src = m.crypto_monthly_authors; title = "The crypto exodus"; cmpName = "investing"; }
    const series = Object.keys(src).slice(0, 3).map((name, k) => ({ name: `r/${name}`, color: ["#3987e5", "#d95926", "#199e70"][k], values: idx(src[name]) }));
    if (m.comparison_monthly_authors && m.comparison_monthly_authors[cmpName]) series.push({ name: `r/${cmpName}`, color: "#c98500", values: idx(m.comparison_monthly_authors[cmpName]) });
    series.push({ name: `all ${DATA.nodes.length} subreddits`, color: "#8e8d86", dashed: true, values: idx(m.frame_monthly_authors) });
    el.innerHTML = `<div class="eyebrow">Monthly commenters, indexed to ${esc(monthTick(ms[0], true))} = 100</div>
      <h2 style="font-size:24px">${title}</h2>
      <div id="s-tl" style="max-width:900px"></div>
      <button class="btn" id="s-close" style="align-self:flex-start">Show the map</button>`;
    wrap.appendChild(el);
    const evs = (m.events || []).filter((e) => e.group === s.group).map((e) => ({ x: e.date.slice(0, 7), label: e.label, short: e.label.split(" (")[0] }));
    if (s.group === "starwars" && m.starwars) evs.push({ x: m.starwars.release.slice(0, 7), label: "The Last Jedi US release", short: "The Last Jedi" });
    lineChart(el.querySelector("#s-tl"), { labels: ms, tickFormat: (x, long) => monthTick(x, long), format: (v) => v.toFixed(0), height: 300, yMin: 0, series, events: evs, ariaLabel: "Monthly commenters indexed to the first month" });
    el.querySelector("#s-close").addEventListener("click", () => el.remove());
  }

  function body(s, last) {
    const box = main.querySelector("#s-body");
    const k = stories.indexOf(story);
    const note = story.caveats && story.caveats.length ? story.caveats[0] : null;
    box.innerHTML = `<div class="eyebrow">Discovery ${k + 1} of ${stories.length} · ${last ? "takeaway" : `step ${step + 1} of ${nSteps - 1}`}</div>
      <h2>${esc(story.title)}</h2><p class="q">${esc(story.question)}</p>
      ${last ? `<div class="takeaway"><div class="eyebrow">What to remember</div><p>${esc(story.takeaway || TAKEAWAYS[story.id] || story.headline)}</p></div>
        <div class="investigate"><div class="eyebrow">Investigate it yourself</div>${investigateActions(story).map((a) => `<a class="btn small" href="${a.href}">${esc(a.label)}</a>`).join("")}</div>`
        : `<div class="step-text">${esc(s.text)}</div>${note ? `<p class="note"><b>Note</b> ${esc(note)}</p>` : ""}`}
      <details class="evidence" ${last || step > 0 ? "open" : ""}><summary>The evidence</summary><div id="s-evidence"></div></details>
      <details class="caveats-box" ${last ? "open" : ""}><summary>What this does not show</summary><ul class="caveats">${story.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></details>
      ${!last ? `<a class="btn ghost" style="margin-top:14px" href="${hashFor("atlas", [], { period: s.view === "timeline" || !s.period || s.period === "all" ? null : s.period, view: s.view === "raw" ? "raw" : null, sel: s.select })}">Keep exploring from here →</a>` : ""}`;
    evidence(box.querySelector("#s-evidence"), s);
  }

  function evidence(el, s) {
    const m = story.metrics;
    const pairLink = (a, b, label) => `<a href="${hashFor("compare", [], { a, b })}">${label || `r/${esc(a)} – r/${esc(b)}`}</a>`;
    if (story.id === "popularity") {
      const row = (x) => `<a href="#/explore/${encodeURIComponent(x.name)}"><span>r/${esc(x.name)}${x.gateway ? '<span class="hub">hub</span>' : ""}</span><span>${fmtX(x.affinity, 2)}</span></a>`;
      const g = m.giant_pair;
      el.innerHTML = `<div class="kpis" style="margin:0 0 14px"><div class="stat"><b>${fmtPct(m.hub_share_cosine)}</b><span>of a topical subreddit's 10 closest neighbours are hubs, by raw overlap</span></div>
        <div class="stat"><b>${fmtPct(m.hub_share_affinity)}</b><span>after adjusting for size and activity</span></div>
        ${m.zero_overlap_count != null ? `<div class="stat"><b>${m.zero_overlap_count} of ${DATA.nodes.length}</b><span>subreddits whose two top-five lists share no name</span></div>` : ""}</div>
        ${g ? `<table class="data"><thead><tr><th>The largest pair that is never a surprising link</th><th class="r">Shared</th><th class="r">Expected</th><th class="r">Affinity</th></tr></thead><tbody>
          <tr><td>${pairLink(g.a, g.b)}<div class="muted" style="font-size:12px">${g.periods_validated} of ${g.periods_tested} periods significant · by quarter ${Object.values(g.affinity_by_quarter).map((v) => fmtX(v, 2)).join(", ")}</div></td><td class="r">${fmtInt(g.shared)}</td><td class="r">${fmtInt(g.expected)}</td><td class="r">${fmtX(g.affinity, 2)}</td></tr></tbody></table>` : ""}
        <div class="grid2" style="gap:12px;margin-top:12px"><div class="list-col"><h4>r/${esc(m.example)} · raw overlap</h4><div class="pill-list">${m.example_cosine_neighbours.map(row).join("")}</div></div>
        <div class="list-col"><h4>r/${esc(m.example)} · adjusted</h4><div class="pill-list">${m.example_affinity_neighbours.map(row).join("")}</div></div></div>
        <p class="muted" style="font-size:12.5px;margin-top:8px">Numbers are affinity (shared ÷ expected) over the whole window; 1.0× = what chance alone would give. r/${esc(m.biggest)} holds ${fmtPct(m.biggest_share_of_commenters)} of all commenters, so its affinity is capped near ${fmtX(m.biggest_affinity_ceiling_median, 1)} by construction.</p>`;
    } else if (story.id === "neighbours") {
      const c = m.country || {};
      const prow = (x, note) => `<tr class="clickable" data-a="${esc(x.a)}" data-b="${esc(x.b)}"><td>r/${esc(x.a)} – r/${esc(x.b)}${note ? `<div class="muted" style="font-size:12px">${esc(note)}</div>` : ""}</td><td class="r">${fmtInt(x.shared)}</td><td class="r">${fmtInt(x.expected)}</td><td class="r">${fmtX(x.affinity, 2)}</td><td>${x.validated ? '<span class="tag ok">surprising</span>' : x.avoided ? '<span class="tag low">fewer than chance</span>' : '<span class="tag">within chance</span>'}</td></tr>`;
      el.innerHTML = `${c.same_country ? `<div class="chart-title">Country and topic, with a control</div><table class="data"><thead><tr><th>Pair</th><th class="r">Shared</th><th class="r">Expected</th><th class="r">Affinity</th><th>Status</th></tr></thead><tbody>
          ${c.same_country.map((x) => prow(x, `same country, different topic · significant in ${x.validated_periods} of ${c.periods} periods`)).join("")}
          ${c.same_topic_across_border.map((x) => prow(x, "same topic, different country")).join("")}
          ${c.to_us_default.map((x) => prow(x, "national subreddit vs the US-default forum")).join("")}</tbody></table>` : ""}
        <div class="chart-title" style="margin-top:14px">Strongest cross-category links (lowest quarterly affinity)</div>
        <table class="data"><thead><tr><th>Link</th><th class="r">Shared · expected</th><th class="r">Lowest quarter</th></tr></thead><tbody>${m.top_links.slice(0, 6).map((x) =>
          `<tr class="clickable" data-a="${esc(x.a)}" data-b="${esc(x.b)}"><td>r/${esc(x.a)} – r/${esc(x.b)}<div class="muted" style="font-size:12px">${esc(categoryLabel(x.cat_a))} × ${esc(categoryLabel(x.cat_b))}</div></td><td class="r">${fmtInt(x.shared_all)} · ${fmtInt(x.expected_all)}</td><td class="r">${fmtX(x.min_affinity)}</td></tr>`).join("")}</tbody></table>
        ${m.lowest_pairs && m.lowest_pairs.length ? `<div class="chart-title" style="margin-top:14px">Audiences that keep apart (expected ≥ 100)</div>
        <table class="data"><thead><tr><th>Pair</th><th class="r">Shared</th><th class="r">Expected</th><th class="r">Affinity</th></tr></thead><tbody>${m.lowest_pairs.slice(0, 6).map((x) =>
          `<tr class="clickable" data-a="${esc(x.a)}" data-b="${esc(x.b)}"><td>r/${esc(x.a)} – r/${esc(x.b)}<div class="muted" style="font-size:12px">below half of expectation in ${x.quarters_below_half} of ${DATA.meta.summary.quarters.length} quarters</div></td><td class="r">${fmtInt(x.shared)}</td><td class="r">${fmtInt(x.expected)}</td><td class="r">${fmtX(x.affinity, 2)}</td></tr>`).join("")}</tbody></table>` : ""}
        ${m.ideology && m.ideology.pairs ? `<p class="muted" style="font-size:12.5px;margin-top:10px">Political test: ${m.ideology.pairs} pairs among ${m.ideology.subreddits.map((s) => "r/" + esc(s)).join(", ")} — ${m.ideology.validated} above chance, ${m.ideology.below_chance} below; weakest ${fmtX(m.ideology.min_affinity, 2)}, median ${fmtX(m.ideology.median_affinity, 2)}.</p>` : ""}
        <p class="muted" style="font-size:12.5px;margin-top:8px">${m.robust_cross_category_links} cross-category links are significant in every quarter at both activity thresholds. "Fewer than chance": lower-tail test at the same 1% false-discovery rate, at most half the expected overlap, expected ≥ 20. Click a row to compare.</p>`;
      el.querySelectorAll("tr[data-a]").forEach((tr) => tr.addEventListener("click", () => { location.hash = hashFor("compare", [], { a: tr.dataset.a, b: tr.dataset.b }); }));
    } else if (story.id === "connectors") {
      el.innerHTML = `<table class="data"><thead><tr><th>Subreddit</th><th class="r">Clusters</th><th class="r">Score</th></tr></thead><tbody>${m.connectors.slice(0, 6).map((c) =>
        `<tr class="clickable" data-n="${esc(c.name)}"><td>r/${esc(c.name)}${c.gateway ? '<span class="hub">hub</span>' : ""}<div class="muted" style="font-size:12px">${esc(categoryLabel(c.category))} · ${c.degree} links</div></td><td class="r">${c.communities_reached}</td><td class="r">${c.participation_min.toFixed(2)}</td></tr>`).join("")}</tbody></table>
        <p class="muted" style="font-size:12.5px;margin:8px 0 14px">Score = lowest participation coefficient across quarters (0 = all links inside one cluster, towards 1 = spread evenly); subreddits with at least ${m.min_degree} links.</p>
        ${m.outward ? `<div class="chart-title">How sealed is each cluster?</div><table class="data"><thead><tr><th>Cluster</th><th class="r">Links leaving it</th><th class="r">vs size alone</th></tr></thead><tbody>${m.outward.map((o) =>
          `<tr><td><span class="dot" style="display:inline-block;background:${communityColor(o.id)}"></span> ${esc(o.community)}<div class="muted" style="font-size:12px">${o.members} subreddits · ${fmtInt(o.links_inside)} inside, ${fmtInt(o.links_outward)} outward</div></td><td class="r">${fmtPct(o.outward_share)}</td><td class="r">${fmtX(o.outward_vs_expected, 2)}</td></tr>`).join("")}</tbody></table>
          <p class="muted" style="font-size:12.5px;margin-top:8px">"vs size alone": the share of links leaving the cluster divided by what a random rewiring that keeps every subreddit's number of links would give.</p>` : ""}
        ${m.giants ? `<p class="muted" style="font-size:12.5px;margin-top:8px">r/${esc(m.giants.name)}: ${m.giants.links_inside_bloc} surprising links, all inside ${esc(m.giants.bloc)}; above expectation with ${m.giants.above_expectation_inside_bloc} of the other ${m.giants.bloc_size - 1} members of that cluster and below expectation with ${m.giants.below_expectation_outside_bloc} of ${m.giants.outside_bloc_count} communities outside it.</p>` : ""}`;
      el.querySelectorAll("tr[data-n]").forEach((tr) => tr.addEventListener("click", () => { location.hash = `#/explore/${encodeURIComponent(tr.dataset.n)}`; }));
    } else if (story.id === "crowds") {
      const ms = m.months, grp = s && s.group, PAL = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"];
      const tick = (x, long) => monthTick(x, long);
      const tendency = m.tendency ? `<p class="muted" style="font-size:12.5px;margin-top:10px">Across ${m.tendency.n_subreddits} communities with at least five stable ties (${fmtInt(m.tendency.n_stable_ties)} ties): growth vs affinity drift ρ = ${m.tendency.spearman_growth_vs_affinity_trend}; growth vs raw-overlap drift ρ = ${m.tendency.spearman_growth_vs_cosine_trend}. Baseline: the whole frame changed ${(100 * m.frame_change_since_baseline).toFixed(0)}% over the same months.</p>` : "";
      if (grp === "starwars" && m.starwars) {
        const sw = m.starwars, partners = Object.keys(sw.partner_affinity);
        el.innerHTML = `<div class="chart-title">r/${esc(sw.name)} with its fandom neighbours</div>
          <div class="chart-sub">Affinity (shared ÷ expected) by month; the dip is the release month, when ${fmtPct(sw.new_share_dec, 0)} of r/${esc(sw.name)}'s commenters were new to it.</div><div id="s-aff"></div>
          <div class="chart-sub" style="margin-top:12px">Share of r/${esc(sw.name)} commenters who also posted in each neighbour.</div><div id="s-rate"></div>${tendency}`;
        const evs = [{ x: sw.release.slice(0, 7), label: "The Last Jedi US release", short: "The Last Jedi" }];
        lineChart(el.querySelector("#s-aff"), { labels: ms, tickFormat: tick, format: (v) => fmtX(v), yMin: 0, height: 220, series: partners.map((p, k) => ({ name: `r/${p}`, color: PAL[k % PAL.length], values: sw.partner_affinity[p] })), events: evs, ariaLabel: `Affinity between r/${sw.name} and its neighbours by month` });
        lineChart(el.querySelector("#s-rate"), { labels: ms, tickFormat: tick, format: (v) => fmtPct(v, 0), yMin: 0, height: 200, series: partners.map((p, k) => ({ name: `also in r/${p}`, color: PAL[k % PAL.length], values: sw.partner_cross_rate[p] })), events: evs, ariaLabel: `Share of r/${sw.name} commenters also active in each neighbour` });
      } else if (grp === "marvel" && m.marvel) {
        const mv = m.marvel, [ca, cb] = mv.pair;
        el.innerHTML = `<div class="chart-title">r/${esc(ca)} – r/${esc(cb)}: affinity and cross-posting</div>
          <div class="chart-sub">Affinity (shared ÷ expected) fell in the release months while the share of commenters crossing between the two did not.</div><div id="s-aff"></div><div id="s-rate" style="margin-top:12px"></div>${tendency}`;
        const evs = m.events.filter((e) => e.group === "marvel").map((e) => ({ x: e.date.slice(0, 7), label: e.label, short: "Infinity War" }));
        lineChart(el.querySelector("#s-aff"), { labels: ms, tickFormat: tick, format: (v) => fmtX(v), yMin: 0, height: 220, directLabels: false, series: [{ name: "affinity", color: PAL[0], values: mv.affinity }, { name: "affinity, ≥2 comments", color: PAL[0], dashed: true, values: mv.affinity_min2 }], events: evs, ariaLabel: `Affinity between r/${ca} and r/${cb} by month` });
        lineChart(el.querySelector("#s-rate"), { labels: ms, tickFormat: tick, format: (v) => fmtPct(v, 0), yMin: 0, height: 200, directLabels: false, series: [{ name: `r/${ca} commenters also in r/${cb}`, color: PAL[1], values: mv.cross_rate_ab }, { name: `r/${cb} commenters also in r/${ca}`, color: PAL[2], values: mv.cross_rate_ba }], events: evs, ariaLabel: `Share of commenters crossing between r/${ca} and r/${cb}` });
      } else {
        const cp = Object.keys(m.crypto_pair_affinity)[0], [ca, cb] = cp.split("|");
        el.innerHTML = `<div class="chart-title">r/${esc(ca)} – r/${esc(cb)}: two ways to look at the same months</div>
          <div class="chart-sub">Affinity (shared ÷ expected) against the share of each community's commenters who also posted in the other.</div><div id="s-aff"></div><div id="s-rate" style="margin-top:12px"></div>${tendency}`;
        const evs = m.events.filter((e) => e.group === "crypto").map((e) => ({ x: e.date.slice(0, 7), label: e.label, short: "" }));
        lineChart(el.querySelector("#s-aff"), { labels: ms, tickFormat: tick, format: (v) => fmtX(v), yMin: 0, height: 220, directLabels: false, series: [{ name: "affinity", color: PAL[0], values: m.crypto_pair_affinity[cp] }, { name: "affinity, ≥2 comments", color: PAL[0], dashed: true, values: m.crypto_pair_affinity_min2[cp] }], events: evs, ariaLabel: `Affinity between r/${ca} and r/${cb} by month` });
        if (m.crypto_cross_rate_ab) lineChart(el.querySelector("#s-rate"), { labels: ms, tickFormat: tick, format: (v) => fmtPct(v, 0), yMin: 0, height: 200, directLabels: false, series: [{ name: `r/${ca} commenters also in r/${cb}`, color: PAL[1], values: m.crypto_cross_rate_ab }, { name: `r/${cb} commenters also in r/${ca}`, color: PAL[2], values: m.crypto_cross_rate_ba }, { name: "raw overlap (cosine)", color: "#8e8d86", dashed: true, values: m.crypto_pair_cosine }], events: evs, ariaLabel: `Share of commenters crossing between r/${ca} and r/${cb}` });
      }
    } else {
      el.innerHTML = `<pre class="mono" style="white-space:pre-wrap">${esc(JSON.stringify(m, null, 1).slice(0, 1500))}</pre>`;
    }
  }
  ready = go(step);
  registerPage({ name: "stories", map, get ready() { return ready; }, goStep: (k) => (ready = go(k)) });
  return () => map.destroy();
}

function renderStoriesIndex(main) {
  const stories = DATA.stories.stories;
  main.innerHTML = `<div class="page">
    <div class="eyebrow">Discoveries</div><h1 style="font-size:36px;margin-bottom:10px">What the map reveals</h1>
    <p class="lede">Each discovery is a short guided walk: the map moves, the evidence sits beside it, and the caveats are spelled out. Every number is computed by the pipeline that built the atlas.</p>
    <div class="cards" style="margin-top:26px">${stories.map((s, k) => `
      <a class="card" href="#/stories/${s.id}"><span class="n">Discovery ${k + 1}</span><h3>${esc(s.title)}</h3><p>${esc(s.question)}</p><span class="go">Walk through it →</span></a>`).join("")}</div>
    <div class="section"><h2>Headlines</h2><div class="headlines">${stories.map((s) => `<div class="panel"><b>${esc(s.title)}</b><p style="margin:6px 0 0">${esc(s.headline)}</p></div>`).join("")}</div></div>
  </div>`;
  registerPage({ name: "stories", ready: Promise.resolve() });
  return null;
}

// ======================================================================
// How it's made (technical walkthrough)
// ======================================================================
const STAGES = [
  { id: "archive", short: "Archive", title: "Reddit comments from a public archive" },
  { id: "clean", short: "Clean", title: "Cleaning and filtering" },
  { id: "bipartite", short: "People × places", title: "The user–subreddit matrix" },
  { id: "raw_overlap", short: "Raw overlap", title: "Raw overlap: the hairball" },
  { id: "expected", short: "Expected", title: "What chance would produce" },
  { id: "validated", short: "Surprising links", title: "Keeping only the surprising" },
  { id: "communities", short: "Communities", title: "Communities and connectors" },
  { id: "temporal", short: "Time", title: "Comparing periods" },
  { id: "publish", short: "Publish", title: "Published findings" },
];
const badge = (kind) => ({ pre: `<span class="badge pre">precomputed by the Python pipeline</span>`, live: `<span class="badge live">computed in your browser</span>`, hist: `<span class="badge hist">historical result (V1)</span>` }[kind]);
const testsFor = (pl, files) => pl.tests.filter((t) => files.includes(t.file));

export function renderPipeline(main, { params }) {
  main.innerHTML = `<div class="page"><div class="eyebrow">How it's made</div>
    <h1 style="font-size:36px;margin-bottom:10px">From ${fmtCompact(DATA.meta.cleaning_report.reduce((a, r) => a + +r.rows_raw, 0))} comments to one question per pair of communities</h1>
    <p class="lede">The atlas is a static website: nothing runs on a server. A Python pipeline (<code>atlas/build_atlas.py</code>) turns the cleaned comments into the data files the browser reads. This page walks through each stage with real counts, a worked example and the tests that guard it.</p>
    <div class="badges" style="margin:14px 0 24px">${badge("pre")} ${badge("live")} ${badge("hist")}</div>
    <div class="stage-track" id="stage-track" role="tablist">${STAGES.map((s, k) => `<button role="tab" data-id="${s.id}" aria-selected="false"><span class="num">${k + 1}</span><span>${esc(s.short)}</span></button>`).join("")}</div>
    <div class="stage-panel panel" id="stage-panel"><div class="empty">Loading pipeline facts…</div></div>
  </div>`;
  const track = main.querySelector("#stage-track"), panel = main.querySelector("#stage-panel");
  let stage = STAGES.some((s) => s.id === params.stage) ? params.stage : "archive";
  let pl = null;
  const ready = loadPipeline().then((p) => { pl = p; open(stage); }).catch((e) => { panel.innerHTML = `<div class="empty">Pipeline facts are not built yet (${esc(e.message)}). Run <code>python atlas/build_atlas.py</code>.</div>`; });
  track.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => open(b.dataset.id)));
  track.addEventListener("keydown", (e) => {
    const i = STAGES.findIndex((s) => s.id === stage);
    if (e.key === "ArrowRight" && i < STAGES.length - 1) open(STAGES[i + 1].id);
    if (e.key === "ArrowLeft" && i > 0) open(STAGES[i - 1].id);
  });

  function open(id) {
    stage = id;
    replaceParams("pipeline", [], { stage: id !== "archive" ? id : null });
    track.querySelectorAll("button").forEach((b) => { const on = b.dataset.id === id; b.setAttribute("aria-selected", String(on)); b.classList.toggle("on", on); b.tabIndex = on ? 0 : -1; });
    if (!pl) return;
    const k = STAGES.findIndex((s) => s.id === id), meta = STAGES[k], st = pl.stages;
    const S = DATA.meta.summary;
    const sec = (title, html) => `<section class="stage-sec"><h4>${title}</h4>${html}</section>`;
    const tests = (files) => { const t = testsFor(pl, files); return t.length ? `<ul class="tests">${t.map((x) => `<li><code>${esc(x.name)}</code>${x.doc ? ` — ${esc(x.doc)}` : ""}</li>`).join("")}</ul>` : `<p class="muted">No dedicated unit test; covered by the end-to-end run and the artifact consistency tests.</p>`; };
    let html = "";
    if (id === "archive") {
      const a = st.archive;
      html = sec("Input", `<p>Public Reddit comments from <b>${esc(a.source)}</b>, ${monthLabel(a.months[0], true)} – ${monthLabel(a.months.at(-1), true)} (${a.quarters.join(", ")}). Comments in this archive end in August 2022; the window processed here is ${a.months.length} months.</p>`)
        + sec("Transformation", `<p>DuckDB reads the Parquet shards over HTTPS and keeps only comments in the <b>${a.frame_subreddits}</b>-subreddit frame, chosen by a fixed rule before any analysis (25 per topical category + 20 front-page hubs, each with ≥ 2,000 comments in three calibration months). Usernames are replaced by a salted SHA-256 hash inside the query; comment text is never stored.</p>`)
        + sec("Output", `<table class="data"><thead><tr><th>Quarter</th><th>Status</th><th class="r">Raw comments</th></tr></thead><tbody>${a.coverage.map((c) => `<tr><td>${esc(periodLabel(c.quarter))}</td><td>${esc(c.status)}</td><td class="r">${fmtInt(c.rows)}</td></tr>`).join("")}</tbody></table>`)
        + sec("Why this step", `<p>A frame fixed before analysis prevents picking communities that happen to tell a good story, and hashing at collection keeps the project privacy-preserving by design.</p>`)
        + sec("Tested by", tests(["test_frame_case_sensitivity.py"]))
        + sec("If it were wrong", `<p>Subreddit names in the archive vary in case (r/cooking vs r/Cooking). A case-sensitive filter silently dropped 23 frame members in an early run; the fetch now matches case-insensitively and asserts 170/170 coverage per quarter.</p>`);
    } else if (id === "clean") {
      const c = st.clean;
      html = sec("Input", `<p><b>${fmtInt(c.raw_comments)}</b> raw comments by ${fmtInt(c.users_raw)} accounts (summed over quarters).</p>`)
        + sec("Transformation", `<ul>${c.rules.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`)
        + sec("Output", `<div class="kpis"><div class="stat"><b>${fmtInt(c.kept_comments)}</b><span>comments kept (${fmtPct(c.kept_share, 2)})</span></div><div class="stat"><b>${fmtInt(c.users_kept)}</b><span>account-quarters kept</span></div><div class="stat"><b>${c.bots_removed}</b><span>bot-like accounts removed</span></div></div>`)
        + sec("Why this step", `<p>Accounts with one or two comments add noise without evidence of membership; a handful of bots that comment everywhere would link every pair of communities by themselves.</p>`)
        + sec("Tested by", tests(["test_clean_bot_logic.py", "test_manual_review_stage.py"]))
        + sec("If it were wrong", `<p>An earlier version deleted every high-volume account, which removed exactly the people most active across communities. The rule now removes an account only when it is both very high-volume <em>and</em> spread across half the frame.</p>`);
    } else if (id === "bipartite") {
      const b = st.bipartite;
      html = sec("Input", `<p>${fmtInt(c2(st).kept_comments)} cleaned comments.</p>`)
        + sec("Transformation", `<p>Collapse comments into a presence matrix: one row per person, one column per subreddit, a 1 where that person commented at least once in the window. Duplicate records are merged; a person's <b>breadth</b> is the number of subreddits they appear in.</p>`)
        + sec("Output", `<div class="kpis"><div class="stat"><b>${fmtInt(b.users)}</b><span>people</span></div><div class="stat"><b>${b.subreddits}</b><span>subreddits</span></div><div class="stat"><b>${fmtInt(b.presence_links)}</b><span>person–subreddit links</span></div><div class="stat"><b>${b.median_breadth}</b><span>median breadth</span></div></div>
          <div class="chart-title" style="margin-top:14px">Who links the communities? ${badge("pre")}</div><div class="chart-sub">People by breadth (number of our subreddits they comment in), and how many subreddit pairs each group connects by itself: a person active in k places links k(k−1)/2 pairs.</div><div id="p-breadth"></div>
          <p class="muted" style="font-size:12.5px">The single widest account comments in ${b.max_breadth} subreddits and alone links ${fmtInt(b.pairs_linked_by_max_breadth_user)} pairs.</p>`)
        + sec("Why this step", `<p>Everything downstream is a statement about this matrix: who is where. It contains no text, no votes and no replies.</p>`)
        + sec("Tested by", tests(["test_affinity.py"]).replace("</ul>", "</ul>"))
        + sec("If it were wrong", `<p>Unmerged duplicate records inflate breadth beyond the number of subreddits and make the model unsolvable; a test checks that duplicates collapse and that an unmerged matrix is rejected.</p>`);
    } else if (id === "raw_overlap") {
      const r = st.raw_overlap;
      html = sec("Input", `<p>The presence matrix.</p>`)
        + sec("Transformation", `<p>Count, for each pair of subreddits, how many people commented in both. V1 of this project normalised that count by community size (cosine similarity) and used it directly.</p>`)
        + sec("Output", `<div class="kpis"><div class="stat"><b>${fmtInt(r.pairs_sharing_any)}</b><span>of ${fmtInt(r.pairs_total)} pairs share ≥ 1 commenter (${fmtPct(r.cosine_density, 2)})</span></div><div class="stat"><b>${fmtInt(r.pairs_sharing_any_if_only_narrow_users)}</b><span>would still be linked if only people active in ≤ 5 subreddits counted</span></div></div>`)
        + sec("Why this step", `<p>It is the obvious map and the historical baseline ${badge("hist")}. Its failure — ${fmtPct(DATA.meta.validation.v1_modularity_audit ? DATA.meta.validation.v1_modularity_audit["2018Q1"].density : r.cosine_density, 2)} density, four communities, six possible bridge positions — is what motivated the rest of the pipeline.</p>`)
        + sec("Tested by", tests(["test_community_detection.py"]))
        + sec("If it were wrong", `<p>It is not wrong, it is uninformative: a shared commenter is almost guaranteed between any two large communities. Treating that as closeness confuses size with relationship.</p>`);
    } else if (id === "expected") {
      const e = st.expected, t = pl.toy;
      html = sec("The idea", `<p><b>Intuitively:</b> we ask whether two communities share more commenters than we would expect after accounting for how big each community is and how many places their users comment in.</p>
          <p><b>Technically:</b> the ${esc(e.model)} is a maximum-entropy random network in which every person keeps their breadth and every subreddit keeps its number of commenters <em>on average</em>, and everything else is random. Fitting it gives a probability p(u,s) that person u comments in subreddit s; the expected number of shared commenters for a pair is</p>
          <div class="formula">${esc(e.formula)}</div>
          <p>People with the same breadth get the same probabilities, so the fit has only <b>${fmtInt(e.unknowns)}</b> unknowns however many people there are. The fitted model reproduces every breadth and every community size to within ${e.fit_max_error} (maximum absolute error).</p>`)
        + sec(`A toy example ${badge("pre")}`, toyHTML(t))
        + sec("Tested by", tests(["test_affinity.py"]))
        + sec("Checked against", `<p>The reference implementation (<code>bicm</code> ${esc(DATA.meta.validation.bicm_crosscheck.bicm_version)}) on a ${fmtInt(DATA.meta.validation.bicm_crosscheck.sample_users)}-person sample of ${esc(DATA.meta.validation.bicm_crosscheck.quarter)}: fitted probabilities differ by at most ${DATA.meta.validation.bicm_crosscheck.fit_max_abs_prob_difference.toExponential(1)}.</p>`)
        + sec("If it were wrong", `<p>If the model did not reproduce breadths and sizes, expected overlaps would be biased and the next stage would create false links; the degree-constraint test and the reference cross-check guard exactly that.</p>`);
    } else if (id === "validated") {
      const v = st.validated;
      html = sec("Input", `<p>Observed and expected shared commenters for all ${fmtInt(st.raw_overlap.pairs_total)} pairs.</p>`)
        + sec("Transformation", `<p>For each pair, a one-sided Poisson test of the observed count against its expectation gives a p-value. With ${fmtInt(st.raw_overlap.pairs_total)} tests, even a 1% chance per pair would create about ${fmtInt(0.01 * st.raw_overlap.pairs_total)} false links, so the Benjamini–Hochberg procedure controls the false discovery rate at ${fmtPct(v.alpha, 0)}. A pair that passes is a <b>surprising link</b>; its <b>affinity</b> is observed ÷ expected. The same test in the other direction flags pairs that share far <em>fewer</em> commenters than expected.</p>`)
        + sec("Output", `<div class="kpis"><div class="stat"><b>${fmtInt(v.validated_pairs)}</b><span>surprising links (${fmtPct(v.density, 1)} of pairs)</span></div><div class="stat"><b>${fmtInt(v.robust_pairs)}</b><span>also pass with a ≥ 2-comment threshold</span></div><div class="stat"><b>${fmtInt(v.avoided_pairs)}</b><span>pairs sharing far fewer than expected</span></div><div class="stat"><b>${v.isolated_subreddits}</b><span>subreddits with no surprising link</span></div></div>
          <div class="chart-title" style="margin-top:16px">Two real pairs, side by side ${badge("pre")}</div><div class="chart-sub">Shared commenters against the model's expectation, and who those shared commenters are.</div><div class="grid2" id="p-examples"></div>`)
        + sec("Why this step", `<p>It turns a count into a judgement with a known error rate, and separates "big" from "close".</p>`)
        + sec("Tested by", tests(["test_affinity.py"]))
        + sec("Checked against", `<p>Our implementation and the reference package validate the identical ${fmtInt(DATA.meta.validation.bicm_crosscheck.validated_ours)} links on the test sample. Exact Poisson-binomial p-values for the ${DATA.meta.validation.bicm_crosscheck.exact_poisson_binomial_pairs_checked} pairs nearest the cut-off would add ${DATA.meta.validation.bicm_crosscheck.exact_flips_gained} links and remove ${DATA.meta.validation.bicm_crosscheck.exact_flips_lost}: the approximation is slightly conservative.</p>`)
        + sec("If it were wrong", `<p>Without the multiple-testing correction the map would carry hundreds of false links; without an effect-size floor on the lower tail, every very large pair would be "significantly" different by a trivial margin.</p>`);
    } else if (id === "communities") {
      const c = st.communities;
      html = sec("Input", `<p>The surprising-link network with log-affinity weights.</p>`)
        + sec("Transformation", `<p>${esc(c.method)}. Communities are detected on the whole window and used as a fixed colouring; each quarter and month is also partitioned on its own to measure stability. A subreddit's <b>participation coefficient</b> (0 = all links inside its own community, towards 1 = spread evenly) is its connector score.</p>`)
        + sec("Output", `<div class="kpis"><div class="stat"><b>${communitiesPhrase(DATA.meta.summary)}</b><span>detected on the whole window</span></div><div class="stat"><b>${c.weighted_modularity}</b><span>weighted modularity</span></div><div class="stat"><b>${c.seed_ari}</b><span>agreement across 20 seeds (ARI)</span></div><div class="stat"><b>${c.sensitivity_ari}</b><span>agreement under the stricter threshold</span></div></div>
          <div class="pill-list" style="margin-top:12px;max-width:520px">${Object.entries(c.labels).map(([id, lab]) => `<span style="display:flex;gap:8px;padding:5px 8px"><span class="dot" style="background:${communityColor(+id)}"></span>${esc(lab)}</span>`).join("")}</div>`)
        + sec("Why this step", `<p>Communities make the map readable and give the connector role a reference. They are a summary, not ground truth.</p>`)
        + sec("Tested by", tests(["test_community_detection.py", "test_brokerage.py"]))
        + sec("If it were wrong", `<p>V1 reported community quality with an <em>unweighted</em> modularity (${DATA.meta.validation.v1_modularity_audit ? DATA.meta.validation.v1_modularity_audit["2018Q1"].stored_unweighted_q : "−0.004"}) on a weighted graph; the weighted value was ${DATA.meta.validation.v1_modularity_audit ? DATA.meta.validation.v1_modularity_audit["2018Q1"].weighted_q : "0.125"}. The reported statistic is now the one the algorithm optimises, and a test checks it. ${badge("hist")}</p>`);
    } else if (id === "temporal") {
      const t = st.temporal;
      html = sec("Input", `<p>Surprising-link networks for ${t.periods} periods: the whole window, ${quarters().length} quarters and ${months().length} months, each fitted separately.</p>`)
        + sec("Transformation", `<p>Link sets are compared with Jaccard overlap; pairs are followed month by month with their affinity and significance; audiences are counted weekly and monthly, with the share of newcomers.</p>`)
        + sec("Output", `<table class="data"><thead><tr><th>Consecutive quarters</th><th class="r">Links kept (Jaccard)</th></tr></thead><tbody>${Object.entries(t.quarter_edge_jaccard).map(([k, v]) => `<tr><td>${esc(k.replace("->", " → "))}</td><td class="r">${v.toFixed(3)}</td></tr>`).join("")}</tbody></table>
          <p class="muted" style="font-size:12.5px;margin-top:8px">Consecutive months keep ${Math.min(...Object.values(t.month_edge_jaccard)).toFixed(2)}–${Math.max(...Object.values(t.month_edge_jaccard)).toFixed(2)} of their links. That churn is the baseline against which any "change" must be judged.</p>`)
        + sec("Why this step", `<p>A relationship that only exists in one month is not worth a story; the stories use links that hold across quarters and thresholds, and report event-related changes as associations.</p>`)
        + sec("Tested by", tests(["test_atlas_artifacts.py"]))
        + sec("If it were wrong", `<p>Comparing periods with different archive completeness would manufacture change; the coverage report and the churn baseline are shown so that small changes are not over-read.</p>`);
    } else {
      html = sec("What the browser does", `<p>It reads the files below and ranks, filters and draws. ${badge("live")} Nothing is fitted or tested in the browser; p-values, expectations, communities and story numbers are all read from the files. ${badge("pre")}</p>`)
        + sec("Artifacts", `<table class="data"><thead><tr><th>File</th><th class="r">Size</th><th>SHA-256 (first 12)</th></tr></thead><tbody>${pl.artifacts.map((f) => `<tr><td><code>${esc(f.file)}</code></td><td class="r">${fmtCompact(f.bytes)}B</td><td class="mono">${esc(f.sha256)}</td></tr>`).join("")}</tbody></table>
          <p class="muted" style="font-size:12.5px">Built ${esc(pl.generated_at)}${pl.git_commit ? ` from commit <code>${esc(pl.git_commit)}</code>` : ""}. Regenerate with <code>python atlas/build_atlas.py</code>; the published files contain subreddit-level aggregates only, which a test checks.</p>`)
        + sec("The test suite", `<p>${pl.tests.length} automated tests across ${Object.keys(pl.test_modules).length} modules. Run <code>python -m pytest tests/</code>.</p><ul class="tests">${Object.entries(pl.test_modules).map(([f, d]) => `<li><code>${esc(f)}</code> (${pl.tests.filter((t) => t.file === f).length})${d ? ` — ${esc(d)}` : ""}</li>`).join("")}</ul>`)
        + sec("Reproduce", `<pre class="formula">python data_curation/run_pipeline.py --start 2017 10 --end 2018 9   # fetch + clean (needs a private salt)
python atlas/build_atlas.py                                         # every file above, ~7 minutes
python -m pytest tests/                                             # the tests
python atlas/serve.py                                               # open the atlas</pre>`);
    }
    panel.innerHTML = `<div class="stage-head"><span class="eyebrow">Stage ${k + 1} of ${STAGES.length}</span><h2>${esc(meta.title)}</h2></div>${html}
      <div class="stage-foot"><button class="btn" ${k === 0 ? "disabled" : ""} data-go="${k > 0 ? STAGES[k - 1].id : ""}">← ${k > 0 ? esc(STAGES[k - 1].short) : ""}</button><button class="btn primary" ${k === STAGES.length - 1 ? "disabled" : ""} data-go="${k < STAGES.length - 1 ? STAGES[k + 1].id : ""}">${k < STAGES.length - 1 ? esc(STAGES[k + 1].short) : ""} →</button></div>`;
    panel.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => b.dataset.go && open(b.dataset.go)));
    if (id === "bipartite") {
      const b = st.bipartite;
      const users = b.breadth_histogram.reduce((a, x) => a + x.users, 0), pairs = b.breadth_histogram.reduce((a, x) => a + x.pairs_linked, 0);
      panel.querySelector("#p-breadth").innerHTML = `<div class="grid2" style="gap:14px"><div><div class="chart-sub">Share of people</div><div id="p-b1"></div></div><div><div class="chart-sub">Share of pair-links created</div><div id="p-b2"></div></div></div>`;
      barChart(panel.querySelector("#p-b1"), { rows: b.breadth_histogram.map((x) => ({ label: `${x.breadth} subreddits`, value: x.users / users, color: "#3987e5" })), format: (v) => fmtPct(v, 1), max: 1, ariaLabel: "share of people by breadth" });
      barChart(panel.querySelector("#p-b2"), { rows: b.breadth_histogram.map((x) => ({ label: `${x.breadth} subreddits`, value: x.pairs_linked / pairs, color: "#d95926" })), format: (v) => fmtPct(v, 1), max: 1, ariaLabel: "share of pair links by breadth" });
    }
    if (id === "validated") panel.querySelector("#p-examples").innerHTML = pl.examples.map(exampleHTML).join("");
    if (!REDUCED_MOTION && params.stage) scrollTo(panel);
  }
  registerPage({ name: "pipeline", ready, openStage: (id) => open(id) });
  return null;
}
const c2 = (st) => st.clean;

function exampleHTML(e) {
  const maxv = Math.max(e.shared, e.expected);
  const nb = e.shared_users_by_breadth, tot = nb.reduce((a, x) => a + x.n, 0);
  return `<div class="example ${e.validated ? "ok" : ""}">
    <div class="pc-names"><span>r/${esc(e.a)}</span><i>×</i><span>r/${esc(e.b)}</span></div>
    <div class="muted" style="font-size:12.5px">${fmtInt(e.users_a)} and ${fmtInt(e.users_b)} commenters</div>
    <div class="ex-bars"><div><span>observed shared</span><i style="width:${(100 * e.shared / maxv).toFixed(1)}%;background:${e.validated ? "#199e70" : "#8a8984"}"></i><b>${fmtInt(e.shared)}</b></div><div><span>expected by chance</span><i style="width:${(100 * e.expected / maxv).toFixed(1)}%;background:#55544f"></i><b>${fmtInt(e.expected)}</b></div></div>
    <div class="ex-facts"><span>affinity <b>${fmtX(e.affinity, 2)}</b></span><span>p (more than chance) <b>${fmtP(e.p_high)}</b></span><span>${e.validated ? `<span class="tag ok">surprising link</span>` : `<span class="tag">within chance</span>`}${e.robust ? ` <span class="tag ok">robust</span>` : ""}</span></div>
    <div class="chart-sub" style="margin-top:10px">The ${fmtInt(e.shared)} shared commenters, by how many of our subreddits they comment in (median ${e.shared_users_median_breadth})</div>
    <div class="mini-hist">${nb.map((x) => `<div><i style="height:${Math.max(2, 100 * x.n / Math.max(...nb.map((y) => y.n))).toFixed(0)}%"></i><span>${esc(x.breadth)}</span><small>${fmtPct(x.n / tot, 0)}</small></div>`).join("")}</div>
  </div>`;
}

function toyHTML(t) {
  const W = 420, H = 230, lx = 60, rx = 360, uy = (k) => 22 + k * 27, sy = (k) => 40 + k * 50;
  const lines = t.matrix.flatMap((row, u) => row.map((v, s) => (v ? `<line x1="${lx + 28}" y1="${uy(u)}" x2="${rx - 28}" y2="${sy(s)}" stroke="#55544f" stroke-width="1.2"/>` : "")).filter(Boolean)).join("");
  const users = t.users.map((u, k) => `<g><circle cx="${lx}" cy="${uy(k)}" r="9" fill="#3987e5"/><text x="${lx - 16}" y="${uy(k) + 4}" text-anchor="end" fill="#c3c2b7" font-size="11">${u} · ${t.user_breadth[k]}</text><text x="${lx + 16}" y="${uy(k) + 4}" fill="#8e8d86" font-size="10">${t.fitted_probabilities[k].map((p) => p.toFixed(2)).join(" ")}</text></g>`).join("");
  const subs = t.subreddits.map((s, k) => `<g><circle cx="${rx}" cy="${sy(k)}" r="13" fill="#d95926"/><text x="${rx}" y="${sy(k) + 4}" text-anchor="middle" fill="#fff" font-size="12" font-weight="700">${s}</text><text x="${rx + 20}" y="${sy(k) + 4}" fill="#c3c2b7" font-size="11">${t.subreddit_size[k]} people</text></g>`).join("");
  return `<div class="grid2" style="gap:16px;align-items:start"><div><svg viewBox="0 0 ${W} ${H}" class="toy" role="img" aria-label="toy bipartite network">${lines}${users}${subs}</svg>
      <p class="muted" style="font-size:12px">Left: people with their breadth and, in grey, the fitted probabilities p(u,A) p(u,B) p(u,C) p(u,D). Right: four subreddits with their sizes.</p></div>
    <div><table class="data"><thead><tr><th>Pair</th><th class="r">Shared</th><th class="r">Expected</th><th class="r">Affinity</th></tr></thead><tbody>${t.pairs.map((p) => `<tr><td>${p.a} – ${p.b}</td><td class="r">${p.shared}</td><td class="r">${p.expected.toFixed(2)}</td><td class="r">${p.affinity.toFixed(2)}×</td></tr>`).join("")}</tbody></table>
      <p class="muted" style="font-size:12px;margin-top:8px">u7 comments everywhere and links every pair by itself; the model expects that and does not count it as a surprise. With eight people no pair is statistically significant; with millions, the same calculation separates size from relationship.</p></div></div>`;
}

// ======================================================================
// Scope & limits (about)
// ======================================================================
export function renderAbout(main, { params }) {
  const M = DATA.meta, sm = M.summary, v = M.validation;
  const cl = M.cleaning_report;
  const tot = (k) => cl.reduce((a, r) => a + Number(r[k] || 0), 0);
  const cc = v.bicm_crosscheck, v1 = v.v1_modularity_audit;
  const vig = (DATA.stories.validity_notes || [])[0];
  const qs = sm.quarters;
  const TOC = [["scope", "Scope"], ["data", "Data"], ["validation", "Validation"], ["evolution", "How the project evolved"], ["labels", "A label the network corrected"], ["privacy", "Privacy & ethics"], ["limits", "What we can and cannot conclude"], ["downloads", "Downloads"]];
  main.innerHTML = `<div class="page about"><nav class="toc" aria-label="On this page">${TOC.map(([id, t]) => `<a href="#/about?section=${id}" data-sec="${id}">${t}</a>`).join("")}</nav><div class="prose">
    <div class="eyebrow">Scope &amp; limits</div>
    <h1 style="font-size:36px;margin-bottom:12px">What this atlas is, and is not</h1>
    <p class="lede">One sample of Reddit, one year, one kind of trace. Everything here is reproducible, and everything here has limits.</p>

    <h3 id="scope">Scope: what was analysed</h3>
    <p><b>${sm.subreddits} subreddits</b> (150 topical across six categories + 20 front-page “gateway” hubs, chosen by a fixed rule before any analysis) ·
      <b>${sm.months.length} months</b>, ${esc(monthTick(sm.months[0], true))} – ${esc(monthTick(sm.months.at(-1), true))} (quarters ${qs.map(periodLabel).join(", ")}).</p>
    <p>The submitted proposal planned a longer 2019–2025 window. Comments are only available from this archive up to August 2022, and this bounded first study processed the ${sm.months.length} months above. Nothing here describes Reddit as a whole: the frame is a sample, and overlaps with communities outside it are not observed.</p>

    <h3 id="data">Data and cleaning</h3>
    <table class="data"><thead><tr><th>Quarter</th><th class="r">Raw comments</th><th class="r">After cleaning</th><th class="r">Retained</th><th class="r">Commenters</th><th class="r">Bot accounts removed</th></tr></thead><tbody>
      ${cl.map((r) => `<tr><td>${esc(periodLabel(r.quarter))}</td><td class="r">${fmtInt(+r.rows_raw)}</td><td class="r">${fmtInt(+r.rows_clean)}</td><td class="r">${fmtPct(r.rows_clean / r.rows_raw, 1)}</td><td class="r">${fmtInt(+r.users_clean)}</td><td class="r">${fmtInt(+r.hard_bots_removed)}</td></tr>`).join("")}
      <tr><td><b>Total</b></td><td class="r"><b>${fmtInt(tot("rows_raw"))}</b></td><td class="r"><b>${fmtInt(tot("rows_clean"))}</b></td><td class="r"><b>${fmtPct(tot("rows_clean") / tot("rows_raw"), 2)}</b></td><td class="r">${fmtInt(sm.users_total)} distinct</td><td class="r">${fmtInt(tot("hard_bots_removed"))}</td></tr>
    </tbody></table>
    <p class="muted" style="font-size:13px">Coverage: ${M.coverage_report.map((r) => `${esc(periodLabel(r.quarter))} ${esc(r.status)}`).join(" · ")} — every frame subreddit observed in every quarter. Cleaning keeps accounts with ≥5 comments in a quarter and removes very high-volume accounts active in at least half of the frame (bots). The stored fields are a hashed author id, the subreddit, a timestamp and a moderator flag; there is no comment text and no reply structure. The full method, with real counts at every stage, is on the <a href="#/pipeline">How it's made</a> page.</p>

    <h3 id="validation">How we checked it</h3>
    <ul>
      ${cc ? `<li><b>Against the reference implementation.</b> On a ${fmtInt(cc.sample_users)}-account sample of ${esc(periodLabel(cc.quarter))} the atlas code and the published <code>bicm</code> package (v${esc(cc.bicm_version)}) validate the same ${fmtInt(cc.validated_ours)} links (overlap ${cc.validated_jaccard.toFixed(3)}); fitted probabilities differ by at most ${cc.fit_max_abs_prob_difference.toExponential(1)}.</li>
      <li><b>Exactness of the test.</b> The Poisson test approximates the exact Poisson-binomial distribution. On the ${cc.exact_poisson_binomial_pairs_checked} pairs nearest the cut-off the exact test would add ${cc.exact_flips_gained} links and remove ${cc.exact_flips_lost}: the approximation is slightly conservative.</li>` : ""}
      <li><b>Threshold sensitivity.</b> Counting only accounts with ≥${sm.sensitivity_min_comments} comments in a subreddit keeps ${fmtPct(sm.robust_share.all)} of the whole-window links (${qs.map((q) => fmtPct(sm.robust_share[q])).join(" / ")} per quarter); community assignments agree at ARI ${sm.anchor.sensitivity_ari}.</li>
      <li><b>Window length.</b> The default view pools all ${sm.months.length} months. Pooled affinities run lower than quarterly ones (the expected overlap grows with pooled breadth) and pooled density higher (${fmtPct(sm.validated_density.all, 1)} vs ${qs.map((q) => fmtPct(sm.validated_density[q], 1)).join(" / ")} by quarter), so compare like with like: the discoveries quote quarters or months when they talk about change.</li>
      <li><b>Stability over time.</b> Consecutive quarters share ${Object.values(sm.quarter_edge_jaccard).map((x) => x.toFixed(2)).join(", ")} of their links (Jaccard); consecutive months ${Math.min(...Object.values(sm.month_edge_jaccard)).toFixed(2)}–${Math.max(...Object.values(sm.month_edge_jaccard)).toFixed(2)}.</li>
      <li><b>Automated tests</b> cover degree constraints, duplicate records, empty communities, structureless data (no false links), pure popularity (no hub links), planted communities, the lower tail, weighted modularity, and the published files (every story number recomputes; no account identifiers).</li>
    </ul>

    <h3 id="evolution">How the project evolved</h3>
    <ol class="evolution">
      <li><b>Proposal.</b> Do cross-community <i>bridge positions</i> persist while the people occupying them change?</li>
      <li><b>V1 on real data</b> (preserved at git tag <code>v1-baseline</code>). The raw cosine network was ${v1 ? fmtPct(v1["2018Q1"].density, 2) : "99.85%"} dense; it yielded four communities and therefore only six possible bridge positions, all saturated. The bridge question could not be measured with that lens.</li>
      <li><b>Audit.</b> V1 reported community quality as ${v1 ? v1["2018Q1"].stored_unweighted_q : "−0.004"}, an unweighted modularity; the weighted value of the same partition was ${v1 ? v1["2018Q1"].weighted_q : "0.125"}. V1's communities were real but weak.</li>
      <li><b>Re-representation.</b> The literature on bipartite projections pointed to null-model validation; on this data it gives a sparse, stable map that the reference implementation reproduces exactly.</li>
      <li><b>The atlas.</b> Bridges survive as the connector role; the temporal interest survives as the crowd discoveries. <b>The submitted question is not answered here:</b> testing whether bridge positions outlast their occupants would need link-level bridge positions on the validated network and a matched occupant-turnover null, which remains future work.</li>
    </ol>

    ${vig ? `<h3 id="labels">A label the network corrected</h3>${DATA.stories.label_mismatch ? `<p>Frame categories come from a keyword rule written before the analysis. For ${DATA.stories.label_mismatch.count} of ${sm.subreddits} subreddits the network disagrees with that rule (${esc(DATA.stories.label_mismatch.definition)}); for example ${DATA.stories.label_mismatch.examples.slice(0, 5).map((x) => `r/${esc(x.name)} (${esc(categoryLabel(x.frame))} → ${esc(categoryLabel(x.network))})`).join(", ")}.</p>` : ""}<p>r/${esc(vig.name)} was filed under “${esc(categoryLabel(vig.label))}” by our keyword rule. Its strongest surprising overlaps are ${vig.neighbours.map((x) => `r/${esc(x.name)} (${fmtX(x.affinity)})`).join(", ")}, and its activity peaks in ${esc(monthTick(vig.peak_month, true))}${vig.neighbours.some((x) => x.name === "Cooking") ? " — the pattern of a smoked-food community, not a quit-smoking one" : ""}. Frame categories come from a rule and can be wrong; the detected communities are the data's own answer.</p>` : ""}

    <h3 id="privacy">Privacy and ethics</h3>
    <p>The data are public comments. Usernames are replaced by salted SHA-256 hashes during collection and the salt is never committed; no text is stored. Everything published in the atlas is a subreddit-level aggregate — counts of commenters and shared commenters — so no account can be looked up, and a test checks that no identifier reaches the published files. Mental-health and support communities appear only in aggregate, like everything else.</p>

    <h3 id="limits">What we can and cannot conclude</h3>
    <div class="grid2 limits">
      <div class="panel ok"><h4>We can show</h4><ul><li>Which subreddit pairs share more (or fewer) commenters than size and activity explain, with a known false-discovery rate.</li><li>That these links form stable topical communities and connector roles.</li><li>That audiences changed around dated events, and how affinity moved with them.</li></ul></div>
      <div class="panel low"><h4>We cannot claim</h4><ul><li>Why audiences overlap: there is no text, so no topics, motives or sentiment.</li><li>That events caused the changes: these are associations in time.</li><li>Anything about Reddit as a whole: a fixed sample of ${sm.subreddits} subreddits, ${sm.months.length} months, commenters only, from an archive with known gaps (Gaffney &amp; Matias, 2018), so counts are lower bounds.</li><li>Friendship, conversation or influence: a shared commenter is co-presence, nothing more.</li></ul></div>
    </div>

    <h3 id="downloads">Downloads</h3>
    <p><a href="exports/atlas_nodes.csv">Nodes (CSV)</a> · ${["all", ...qs].map((pid) => `<a href="exports/atlas_edges_${pid}.csv">Edges ${esc(periodLabel(pid))} (CSV)</a> · <a href="exports/atlas_network_${pid}.gexf">GEXF</a>`).join(" · ")}</p>
    <p class="muted" style="font-size:12.5px">Built ${esc(M.generated_at)}${M.git_commit ? ` from commit ${esc(M.git_commit)}` : ""}. Final report: <code>docs/FINAL_REPORT.pdf</code>. Regenerate everything with <code>python atlas/build_atlas.py</code>.</p>
  </div></div>`;
  const toc = main.querySelector(".toc");
  toc.querySelectorAll("a").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); replaceParams("about", [], { section: a.dataset.sec }); scrollTo(main.querySelector(`#${a.dataset.sec}`)); }));
  const jump = (id) => { const el = main.querySelector(`#${id}`); if (el) setTimeout(() => scrollTo(el), 50); };
  if (params.section) jump(params.section);
  registerPage({ name: "about", ready: Promise.resolve(), scrollTo: jump });
  return null;
}
