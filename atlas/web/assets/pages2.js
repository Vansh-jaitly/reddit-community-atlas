// Compare, Stories and Methods pages.
import {
  DATA, loadPairs, neighbours, pairStats, pairEnds, communityColor, categoryColor, categoryLabel, communityLabel,
  fmtInt, fmtPct, fmtX, fmtCompact, esc, periodLabel, hashFor, replaceParams, searchBox,
} from "./core.js";
import { AtlasMap } from "./map.js";
import { lineChart, monthTick } from "./charts.js";

const node = (name) => (name ? DATA.byName.get(String(name).toLowerCase()) : null);
const link = (n) => `<a href="#/explore/${encodeURIComponent(n.name)}">r/${esc(n.name)}</a>`;
const months = () => DATA.meta.periods.filter((p) => p.kind === "month").map((p) => p.id);
const quarters = () => DATA.meta.summary.quarters;

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

  async function draw() {
    if (!a || !b || a.id === b.id) {
      const sug = DATA.stories.stories.find((s) => s.id === "neighbours");
      const ex = sug ? sug.metrics.top_links.slice(0, 5) : [];
      out.innerHTML = `<div class="empty">${a && b ? "Pick two different subreddits." : "Pick two subreddits to compare."}
        ${ex.length ? `<div style="margin-top:12px">Try: ${ex.map((x) => `<a href="${hashFor("compare", [], { a: x.a, b: x.b })}">r/${esc(x.a)} vs r/${esc(x.b)}</a>`).join(" · ")}</div>` : ""}</div>`;
      out.querySelectorAll("a").forEach((el) => el.addEventListener("click", (e) => { e.preventDefault(); location.hash = el.getAttribute("href"); location.reload(); }));
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
    const verdict = s.validated
      ? `r/${esc(a.name)} and r/${esc(b.name)} share <b>${fmtInt(s.shared)}</b> commenters where <b>${fmtInt(s.expected)}</b> were expected — <b>${fmtX(s.affinity)}</b> chance, a validated surprising link${s.robust ? " that also survives the stricter two-comment threshold" : ""}.`
      : `r/${esc(a.name)} and r/${esc(b.name)} share ${fmtInt(s.shared)} commenters where ${fmtInt(s.expected)} were expected (${fmtX(s.affinity, 2)}) — <b>not</b> more than chance would produce.`;
    out.innerHTML = `
      <div class="panel" style="font-size:17px;line-height:1.55">${verdict}</div>
      <div class="section grid2" style="margin-top:18px">
        <div class="panel"><div class="chart-title">Affinity month by month</div><div class="chart-sub">Filled point = significant that month. 1.0× = chance.</div><div id="c-chart"></div></div>
        <div class="panel"><div class="chart-title">By period</div><table class="data"><thead><tr><th>Period</th><th class="r">Shared</th><th class="r">Expected</th><th class="r">Affinity</th><th>Significant</th></tr></thead><tbody>
          ${rows.map((r) => `<tr><td>${esc(periodLabel(r.pid))}</td><td class="r">${fmtInt(r.shared)}</td><td class="r">${fmtInt(r.expected)}</td><td class="r">${fmtX(r.affinity, 2)}</td><td>${r.validated ? "yes" : "no"}</td></tr>`).join("")}
        </tbody></table>
        <div class="chart-sub" style="margin-top:12px">Commenters over the whole window: ${link(a)} ${fmtInt(rows[0].ua)} · ${link(b)} ${fmtInt(rows[0].ub)}</div></div>
      </div>
      <div class="section panel"><div class="chart-title">Communities both are surprisingly close to</div>
        <div class="chart-sub">Validated with both over the whole window, ranked by the weaker of the two links.</div>
        ${common.length ? `<table class="data"><thead><tr><th>Subreddit</th><th>Community</th><th class="r">with r/${esc(a.name)}</th><th class="r">with r/${esc(b.name)}</th></tr></thead><tbody>${common.slice(0, 10).map((c) => `<tr><td>${link(DATA.nodes[c.j])}</td><td><span class="dot" style="display:inline-block;background:${communityColor(DATA.nodes[c.j].community)}"></span> ${esc(communityLabel(DATA.nodes[c.j].community))}</td><td class="r">${fmtX(c.a)}</td><td class="r">${fmtX(c.b)}</td></tr>`).join("")}</tbody></table>` : `<div class="empty">No shared surprising neighbours.</div>`}</div>`;
    const st = mp.map((p) => pairStats(p, a.id, b.id));
    lineChart(out.querySelector("#c-chart"), {
      labels: ms, tickFormat: (m, long) => monthTick(m, long), format: (v) => fmtX(v, 2), yMin: 0,
      series: [{ name: `r/${a.name} – r/${b.name}`, color: "#3987e5", values: st.map((x) => (x.expected > 0 ? x.affinity : null)), points: st.map((x) => x.validated) },
               { name: "chance (1.0×)", color: "#8e8d86", dashed: true, values: ms.map(() => 1) }],
    });
  }
  draw();
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
      <div class="map-wrap" id="c-m1"><div class="map-host" style="position:absolute;inset:0"></div><span class="chip tag" id="c-t1"></span></div>
      <div class="map-wrap" id="c-m2"><div class="map-host" style="position:absolute;inset:0"></div><span class="chip tag" id="c-t2"></span></div></div>
    <div class="section grid2"><div class="panel"><div class="chart-title">Strongest links that appeared</div><div class="chart-sub" id="c-gsub"></div><div id="c-gained"></div></div>
      <div class="panel"><div class="chart-title">Strongest links that disappeared</div><div class="chart-sub" id="c-lsub"></div><div id="c-lost"></div></div></div>`;
  const m1 = new AtlasMap(box.querySelector("#c-m1 .map-host"), { communityLabels: false, labelThreshold: 12, onSelect: (i) => { m1.select(i, { fly: false }); m2.select(i, { fly: false }); } });
  const m2 = new AtlasMap(box.querySelector("#c-m2 .map-host"), { communityLabels: false, labelThreshold: 12, onSelect: (i) => { m1.select(i, { fly: false }); m2.select(i, { fly: false }); } });
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
    box.querySelector("#c-base").textContent = `For reference: consecutive months keep ${Math.min(...mj).toFixed(2)}–${Math.max(...mj).toFixed(2)} of their links (Jaccard), consecutive quarters ${Math.min(...qj).toFixed(2)}–${Math.max(...qj).toFixed(2)}. Changes smaller than that are normal churn, not news.`;
    box.querySelector("#c-t1").innerHTML = `<span class="dot" style="background:#d95926"></span>${esc(periodLabel(p1))} · strongest 60 links that later disappeared`;
    box.querySelector("#c-t2").innerHTML = `<span class="dot" style="background:#3987e5"></span>${esc(periodLabel(p2))} · strongest 60 links that appeared`;
    await Promise.all([m1.show({ period: p1 }), m2.show({ period: p2 })]);
    const rank = (list, p) => list.map((k) => ({ k, aff: p.shared[k] / p.expected[k], shared: p.shared[k] })).sort((u, v) => v.aff - u.aff);
    const g = rank(gained, b), l = rank(lost, a);
    m1.setFocus(null, l.slice(0, 60).map((x) => pairEnds(x.k)), "rgb(217,89,38)");
    m2.setFocus(null, g.slice(0, 60).map((x) => pairEnds(x.k)), "rgb(57,135,229)");
    box.querySelector("#c-gsub").textContent = `Significant in ${periodLabel(p2)} but not in ${periodLabel(p1)}; affinity in ${periodLabel(p2)}.`;
    box.querySelector("#c-lsub").textContent = `Significant in ${periodLabel(p1)} but not in ${periodLabel(p2)}; affinity in ${periodLabel(p1)}.`;
    const list = (arr) => arr.length ? `<div class="pill-list">${arr.slice(0, 10).map((x) => {
      const [i, j] = pairEnds(x.k);
      return `<a href="${hashFor("compare", [], { a: DATA.nodes[i].name, b: DATA.nodes[j].name })}"><span>r/${esc(DATA.nodes[i].name)} – r/${esc(DATA.nodes[j].name)}</span><span>${fmtX(x.aff)}</span></a>`;
    }).join("")}</div>` : `<div class="empty">None.</div>`;
    box.querySelector("#c-gained").innerHTML = list(g);
    box.querySelector("#c-lost").innerHTML = list(l);
  }
  box.querySelector("#c-p1").addEventListener("change", (e) => { p1 = e.target.value; draw(); });
  box.querySelector("#c-p2").addEventListener("change", (e) => { p2 = e.target.value; draw(); });
  draw();
  return () => { m1.destroy(); m2.destroy(); };
}

// ======================================================================
// Guided stories
// ======================================================================
export function renderStories(main, { args, params }) {
  const stories = DATA.stories.stories;
  const story = stories.find((s) => s.id === args[0]) || stories[0];
  let step = Math.max(0, Math.min(story.steps.length - 1, +(params.step || 0)));
  main.innerHTML = `<div class="story-layout">
    <div class="map-wrap" id="s-wrap"><div class="map-host" style="position:absolute;inset:0"></div><div class="map-note" id="s-note"></div></div>
    <aside class="story-panel">
      <div class="story-tabs">${stories.map((s, k) => `<button data-id="${s.id}" class="${s.id === story.id ? "on" : ""}">${k + 1}. ${esc(s.title)}</button>`).join("")}</div>
      <div class="story-body" id="s-body"></div>
      <div class="story-nav"><div class="pips">${story.steps.map((_, k) => `<i data-k="${k}"></i>`).join("")}</div>
        <button class="btn" id="s-prev">← Back</button><button class="btn primary" id="s-next">Next →</button></div>
    </aside></div>`;
  const map = new AtlasMap(main.querySelector(".map-host"), { onSelect: (i) => map.select(i) });
  const wrap = main.querySelector("#s-wrap");
  main.querySelectorAll(".story-tabs button").forEach((b) => b.addEventListener("click", () => { location.hash = `#/stories/${b.dataset.id}`; }));
  main.querySelector("#s-prev").addEventListener("click", () => go(step - 1));
  main.querySelector("#s-next").addEventListener("click", () => {
    if (step < story.steps.length - 1) go(step + 1);
    else { const k = stories.indexOf(story); location.hash = k < stories.length - 1 ? `#/stories/${stories[k + 1].id}` : "#/atlas"; }
  });

  async function go(k) {
    step = Math.max(0, Math.min(story.steps.length - 1, k));
    replaceParams("stories", [story.id], { step: step || null });
    const s = story.steps[step];
    main.querySelectorAll(".pips i").forEach((el, j) => el.classList.toggle("on", j === step));
    main.querySelector("#s-prev").disabled = step === 0;
    main.querySelector("#s-next").textContent = step < story.steps.length - 1 ? "Next →" : (stories.indexOf(story) < stories.length - 1 ? "Next story →" : "Open the Atlas →");
    const period = s.view === "timeline" ? (DATA.meta.periods.some((p) => p.id === s.period) ? s.period : "all") : s.period || "all";
    const overlay = wrap.querySelector(".timeline-overlay");
    if (overlay) overlay.remove();
    await map.show({ period, view: s.view === "raw" ? "raw" : "adjusted" });
    map.select(null, { fly: false });
    map.setFocus(s.focus && s.focus.length ? s.focus : null, s.edges || (s.edge ? [s.edge] : null));
    // A step about one specific link emphasises that link instead of selecting a node (selection shows all its links).
    if (s.select != null && !s.edge) map.select(s.select, { fly: false });
    if (s.focus && s.focus.length) map.flyTo(s.focus, 0.3); else map.reset();
    main.querySelector("#s-note").textContent = `${periodLabel(period)} · ${s.view === "raw" ? "raw overlap" : "surprising links only"}`;
    if (s.view === "timeline") timeline(s);
    body(s);
  }

  function timeline(s) {
    const el = document.createElement("div");
    el.className = "timeline-overlay";
    const m = story.metrics, ms = m.months;
    const grp = s.group === "marvel" ? Object.keys(m.marvel_monthly_authors) : Object.keys(m.crypto_monthly_authors);
    const src = s.group === "marvel" ? m.marvel_monthly_authors : m.crypto_monthly_authors;
    const cmpName = s.group === "marvel" ? "movies" : "investing";
    const idx = (arr) => arr.map((v) => (arr[0] ? (100 * v) / arr[0] : null));
    const series = grp.slice(0, 3).map((name, k) => ({ name: `r/${name}`, color: ["#3987e5", "#d95926", "#199e70"][k], values: idx(src[name]) }));
    if (m.comparison_monthly_authors[cmpName]) series.push({ name: `r/${cmpName}`, color: "#c98500", values: idx(m.comparison_monthly_authors[cmpName]) });
    series.push({ name: "all 170 subreddits", color: "#8e8d86", dashed: true, values: idx(m.frame_monthly_authors) });
    el.innerHTML = `<div class="eyebrow">Monthly commenters, indexed to ${esc(monthTick(ms[0], true))} = 100</div>
      <h2 style="font-size:24px">${s.group === "marvel" ? "The Infinity War crowd" : "The crypto exodus"}</h2>
      <div id="s-tl" style="max-width:900px"></div>
      <button class="btn" id="s-close" style="align-self:flex-start">Show the map</button>`;
    wrap.appendChild(el);
    lineChart(el.querySelector("#s-tl"), {
      labels: ms, tickFormat: (x, long) => monthTick(x, long), format: (v) => v.toFixed(0), height: 300, yMin: 0,
      series, events: m.events.filter((e) => e.group === s.group).map((e) => ({ x: e.date.slice(0, 7), label: e.label, short: e.label.split(" (")[0] })),
      ariaLabel: "Monthly commenters indexed to the first month",
    });
    el.querySelector("#s-close").addEventListener("click", () => el.remove());
  }

  function body(s) {
    const box = main.querySelector("#s-body");
    box.innerHTML = `<div class="eyebrow">Story ${stories.indexOf(story) + 1} of ${stories.length} · step ${step + 1} of ${story.steps.length}</div>
      <h2>${esc(story.title)}</h2><p class="q">${esc(story.question)}</p>
      <div class="step-text">${esc(s.text)}</div>
      <div id="s-evidence"></div>
      <ul class="caveats">${story.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
      <a class="btn" style="margin-top:14px" href="${hashFor("atlas", [], { period: s.view === "timeline" || !s.period || s.period === "all" ? null : s.period, view: s.view === "raw" ? "raw" : null, sel: s.select })}">Keep exploring from here →</a>`;
    evidence(box.querySelector("#s-evidence"));
  }

  function evidence(el) {
    const m = story.metrics;
    if (story.id === "popularity") {
      const row = (x) => `<a href="#/explore/${encodeURIComponent(x.name)}"><span>r/${esc(x.name)}${x.gateway ? '<span class="hub">hub</span>' : ""}</span><span>${fmtX(x.affinity, 2)}</span></a>`;
      el.innerHTML = `<div class="kpis" style="margin:0 0 14px"><div class="stat"><b>${fmtPct(m.hub_share_cosine)}</b><span>hub share of top-10, raw</span></div>
        <div class="stat"><b>${fmtPct(m.hub_share_affinity)}</b><span>hub share, adjusted</span></div></div>
        <div class="grid2" style="gap:12px"><div class="list-col"><h4>r/${esc(m.example)} · raw</h4><div class="pill-list">${m.example_cosine_neighbours.map(row).join("")}</div></div>
        <div class="list-col"><h4>r/${esc(m.example)} · adjusted</h4><div class="pill-list">${m.example_affinity_neighbours.map(row).join("")}</div></div></div>
        <p class="muted" style="font-size:12.5px;margin-top:8px">Numbers are affinity (shared ÷ expected) over the whole window.</p>`;
    } else if (story.id === "neighbours") {
      el.innerHTML = `<table class="data"><thead><tr><th>Link</th><th class="r">Min / quarter</th></tr></thead><tbody>${m.top_links.slice(0, 8).map((x) =>
        `<tr class="clickable" data-a="${esc(x.a)}" data-b="${esc(x.b)}"><td>r/${esc(x.a)} – r/${esc(x.b)}<div class="muted" style="font-size:12px">${esc(categoryLabel(x.cat_a))} × ${esc(categoryLabel(x.cat_b))}</div></td><td class="r">${fmtX(x.min_affinity)}</td></tr>`).join("")}</tbody></table>
        <p class="muted" style="font-size:12.5px;margin-top:8px">${m.robust_cross_category_links} cross-category links are significant in every quarter at both thresholds. Click one to compare.</p>`;
      el.querySelectorAll("tr[data-a]").forEach((tr) => tr.addEventListener("click", () => { location.hash = hashFor("compare", [], { a: tr.dataset.a, b: tr.dataset.b }); }));
    } else if (story.id === "connectors") {
      el.innerHTML = `<table class="data"><thead><tr><th>Subreddit</th><th class="r">Clusters</th><th class="r">Score</th></tr></thead><tbody>${m.connectors.slice(0, 8).map((c) =>
        `<tr class="clickable" data-n="${esc(c.name)}"><td>r/${esc(c.name)}<div class="muted" style="font-size:12px">${esc(categoryLabel(c.category))}</div></td><td class="r">${c.communities_reached}</td><td class="r">${c.participation_min.toFixed(2)}</td></tr>`).join("")}</tbody></table>
        <p class="muted" style="font-size:12.5px;margin-top:8px">Score = lowest participation coefficient across quarters. Hubs average ${m.hub_mean_participation.toFixed(2)}; topical communities ${m.topical_mean_participation.toFixed(2)}.</p>`;
      el.querySelectorAll("tr[data-n]").forEach((tr) => tr.addEventListener("click", () => { location.hash = `#/explore/${encodeURIComponent(tr.dataset.n)}`; }));
    } else if (story.id === "crowds") {
      const ms = m.months;
      const cp = Object.keys(m.crypto_pair_affinity)[0], mk = Object.keys(m.marvel_pair_affinity)[0];
      el.innerHTML = `<div class="chart-title">Affinity month by month</div><div class="chart-sub">Dashed: same calculation counting only users with ≥2 comments in a subreddit.</div><div id="s-aff"></div>
        <p class="muted" style="font-size:12.5px;margin-top:8px">General tendency across all communities: ρ = ${m.general_tendency.spearman_large_swings} for ${m.general_tendency.n_large_swings} month-to-month audience swings above 25% (ρ = ${m.general_tendency.spearman_all_steps} over all ${m.general_tendency.n_steps} steps).</p>`;
      const series = [{ name: cp.replace("|", " – "), color: "#3987e5", values: m.crypto_pair_affinity[cp] }, { name: "≥2 comments", color: "#3987e5", dashed: true, values: m.crypto_pair_affinity_min2[cp] }];
      if (mk) series.push({ name: mk.replace("|", " – "), color: "#d95926", values: m.marvel_pair_affinity[mk] }, { name: "≥2 comments ", color: "#d95926", dashed: true, values: m.marvel_pair_affinity_min2[mk] });
      lineChart(el.querySelector("#s-aff"), { labels: ms, tickFormat: (x, long) => monthTick(x, long), format: (v) => fmtX(v), yMin: 0, height: 300, series, directLabels: false,
        events: m.events.map((e) => ({ x: e.date.slice(0, 7), label: e.label, short: "" })) });
    }
  }
  go(step);
  return () => map.destroy();
}

// ======================================================================
// Methods & data
// ======================================================================
export function renderMethods(main) {
  const M = DATA.meta, sm = M.summary, v = M.validation;
  const cl = M.cleaning_report;
  const tot = (k) => cl.reduce((a, r) => a + Number(r[k] || 0), 0);
  const cc = v.bicm_crosscheck, v1 = v.v1_modularity_audit;
  const vig = (DATA.stories.validity_notes || [])[0];
  const qs = sm.quarters;
  main.innerHTML = `<div class="page"><div class="prose">
    <div class="eyebrow">Methods &amp; data</div>
    <h1 style="font-size:36px;margin-bottom:12px">How the Atlas is built</h1>
    <p class="lede">A reproducible pipeline turns ${fmtCompact(tot("rows_raw"))} raw Reddit comments into one question per pair of communities: do they share more commenters than their size and their users' activity would predict?</p>

    <h3>Scope: what was analysed</h3>
    <p><b>${sm.subreddits} subreddits</b> (150 topical across six categories + 20 front-page “gateway” hubs, chosen by a fixed rule before any analysis) ·
      <b>${sm.months.length} months</b>, ${esc(monthTick(sm.months[0], true))} – ${esc(monthTick(sm.months.at(-1), true))} (quarters ${qs.map(periodLabel).join(", ")}).
      The original proposal planned a longer 2019–2025 window; comments are only available from this archive up to Aug 2022, and the bounded first study processed these ${sm.months.length} months. Nothing here describes Reddit as a whole.</p>
    <table class="data"><thead><tr><th>Quarter</th><th class="r">Raw comments</th><th class="r">After cleaning</th><th class="r">Retained</th><th class="r">Commenters</th><th class="r">Bot accounts removed</th></tr></thead><tbody>
      ${cl.map((r) => `<tr><td>${esc(periodLabel(r.quarter))}</td><td class="r">${fmtInt(+r.rows_raw)}</td><td class="r">${fmtInt(+r.rows_clean)}</td><td class="r">${fmtPct(r.rows_clean / r.rows_raw, 1)}</td><td class="r">${fmtInt(+r.users_clean)}</td><td class="r">${fmtInt(+r.hard_bots_removed)}</td></tr>`).join("")}
      <tr><td><b>Total</b></td><td class="r"><b>${fmtInt(tot("rows_raw"))}</b></td><td class="r"><b>${fmtInt(tot("rows_clean"))}</b></td><td class="r"><b>${fmtPct(tot("rows_clean") / tot("rows_raw"), 2)}</b></td><td class="r">${fmtInt(sm.users_total)} distinct</td><td class="r">${fmtInt(tot("hard_bots_removed"))}</td></tr>
    </tbody></table>
    <p class="muted" style="font-size:13px">Coverage: ${M.coverage_report.map((r) => `${esc(r.quarter)} ${esc(r.status)}`).join(" · ")} — every frame subreddit observed in every quarter. Cleaning keeps accounts with ≥5 comments in a quarter and removes very high-volume accounts active in at least half of the frame (bots).</p>

    <h3>Pipeline</h3>
    <div class="flow">
      <div><b>Arctic Shift archive</b><span>Pushshift-derived comments</span></div><i>→</i>
      <div><b>Fetch</b><span>170 subreddits, salted hashes</span></div><i>→</i>
      <div><b>Clean</b><span>activity floor, bot filter</span></div><i>→</i>
      <div><b>User × subreddit matrix</b><span>who commented where</span></div><i>→</i>
      <div><b>Expected overlap</b><span>BiCM</span></div><i>→</i>
      <div><b>Surprising links</b><span>FDR ${sm.alpha * 100}%</span></div><i>→</i>
      <div><b>Communities &amp; roles</b><span>Leiden, participation</span></div><i>→</i>
      <div><b>Atlas JSON</b><span>aggregates only</span></div>
    </div>

    <h3>The relationship measure</h3>
    <p>Raw overlap (cosine similarity of commenter sets) links ${fmtPct(sm.cosine_density.all, 1)} of all pairs over the whole window: every person who comments in several places connects all of them, so big communities look close to everything. Instead each pair is compared with what chance would give:</p>
    <div class="formula">expected(a,b) = Σ_users p(u→a) · p(u→b)<br>affinity(a,b) = shared commenters / expected</div>
    <p>The probabilities come from the <b>Bipartite Configuration Model</b> (Saracco et al., 2015): a random Reddit in which every account keeps its number of subreddits and every subreddit keeps its number of commenters, but who comments where is shuffled. A link is drawn only when the observed count is improbably high (one-sided Poisson test, Benjamini–Hochberg false discovery rate ${sm.alpha * 100}% over all ${fmtInt(sm.subreddits * (sm.subreddits - 1) / 2)} pairs). That keeps ${fmtPct(sm.validated_density.all, 1)} of pairs over the whole window and ${qs.map((q) => fmtPct(sm.validated_density[q], 1)).join(" / ")} per quarter.</p>
    <p>Communities: Leiden (modularity, γ = 1) on log-affinity weights, best of 20 seeds — ${sm.anchor.communities} communities, weighted modularity ${sm.anchor.weighted_modularity}, mean agreement between seeds (ARI) ${sm.anchor.seed_ari}. Connector score: participation coefficient (Guimerà &amp; Amaral, 2005).</p>

    <h3>How we checked it</h3>
    <ul>
      ${cc ? `<li><b>Against the reference implementation.</b> On a ${fmtInt(cc.sample_users)}-account sample of ${esc(cc.quarter)} the Atlas code and the published <code>bicm</code> package (v${esc(cc.bicm_version)}) validate the same ${fmtInt(cc.validated_ours)} links (overlap ${cc.validated_jaccard.toFixed(3)}); fitted probabilities differ by at most ${cc.fit_max_abs_prob_difference.toExponential(1)}. An exact Poisson-binomial test on the ${cc.exact_poisson_binomial_pairs_checked} pairs nearest the cut-off would add ${cc.exact_flips_gained} links and remove ${cc.exact_flips_lost}: the approximation is slightly conservative.</li>` : ""}
      <li><b>Threshold sensitivity.</b> Counting only accounts with ≥${sm.sensitivity_min_comments} comments in a subreddit keeps ${qs.map((q) => fmtPct(sm.robust_share[q])).join(" / ")} of each quarter's links; community assignments agree at ARI ${sm.anchor.sensitivity_ari}.</li>
      <li><b>Stability over time.</b> Consecutive quarters share ${Object.values(sm.quarter_edge_jaccard).map((x) => x.toFixed(2)).join(" and ")} of their links (Jaccard); consecutive months ${Math.min(...Object.values(sm.month_edge_jaccard)).toFixed(2)}–${Math.max(...Object.values(sm.month_edge_jaccard)).toFixed(2)}.</li>
      <li><b>Automated tests</b> cover degree constraints, duplicate records, empty communities, structureless data (no false links), pure popularity (no hub links) and planted communities.</li>
    </ul>

    <h3>How the project evolved</h3>
    <p>The submitted question was whether cross-community <i>bridge positions</i> persist while the people occupying them change. The first pipeline (V1, preserved in the repository at tag <code>v1-baseline</code>) used the raw cosine network: it came out ${v1 ? fmtPct(v1["2018Q1"].density, 2) : "99.85%"} dense, found only 4 communities and therefore only 6 possible bridge positions, all saturated — too few to test the hypothesis. V1 also reported community quality as ${v1 ? v1["2018Q1"].stored_unweighted_q : "−0.004"}; a later audit showed that number ignored edge weights (weighted modularity of the same partition: ${v1 ? v1["2018Q1"].weighted_q : "0.125"}). The Atlas keeps the bridge idea as the connector view and replaces the measurement lens.</p>
    ${vig ? `<h3>What the network taught us about our own labels</h3><p>r/${esc(vig.name)} was filed under “${esc(categoryLabel(vig.label))}” by our keyword rule. Its strongest surprising overlaps are ${vig.neighbours.map((x) => `r/${esc(x.name)} (${fmtX(x.affinity)})`).join(", ")}, and its activity peaks in ${esc(monthTick(vig.peak_month, true))}${vig.neighbours.some((x) => x.name === "Cooking")
      ? " — the pattern of a barbecue (smoked food) community rather than a quit-smoking one. The network flags a likely misclassification that the label alone would hide."
      : ". Compare that with its label before trusting the category."}</p>` : ""}

    <h3>Privacy and ethics</h3>
    <p>Usernames are replaced by salted SHA-256 hashes during collection; no text is stored. Everything published in the Atlas is a subreddit-level aggregate — counts of commenters and shared commenters — so no account can be looked up. Support communities (mental and physical health) are shown only in aggregate like everything else.</p>

    <h3>Limitations</h3>
    <ul>
      <li>Commenters only: lurkers and voters are invisible, and comments deleted before archiving are missing (Gaffney &amp; Matias, 2018). Counts are lower bounds.</li>
      <li>A fixed sample of ${sm.subreddits} subreddits: overlaps with communities outside the frame are not observed.</li>
      <li>Co-commenting is not conversation, friendship or influence; no comment text was collected, so motives and topics cannot be inferred.</li>
      <li>Events are dated externally. Changes around them are associations, not causal effects.</li>
      <li>Communities are a summary, not ground truth; their exact number changes with thresholds (ARI ${sm.anchor.sensitivity_ari} under the stricter threshold).</li>
    </ul>

    <h3>Downloads</h3>
    <p><a href="exports/atlas_nodes.csv">Nodes (CSV)</a> · ${["all", ...qs].map((pid) => `<a href="exports/atlas_edges_${pid}.csv">Edges ${esc(periodLabel(pid))} (CSV)</a> · <a href="exports/atlas_network_${pid}.gexf">GEXF</a>`).join(" · ")}</p>
    <p class="muted" style="font-size:12.5px">Built ${esc(M.generated_at)}${M.git_commit ? ` from commit ${esc(M.git_commit)}` : ""}. Regenerate with <code>python atlas/build_atlas.py</code>.</p>
  </div></div>`;
  return null;
}
