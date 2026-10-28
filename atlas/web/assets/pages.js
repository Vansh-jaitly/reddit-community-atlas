// Discoveries, Atlas and Explore pages.
import {
  DATA, loadPairs, neighbours, pairStats, communityColor, categoryColor, categoryLabel, communityLabel,
  fmtInt, fmtPct, fmtX, fmtCompact, esc, periodLabel, hashFor, replaceParams, searchBox, neighbourBars, wireBars,
  CATEGORY_ORDER,
} from "./core.js";
import { AtlasMap } from "./map.js";
import { lineChart, monthTick } from "./charts.js";

const periodOptions = (sel, kinds = ["pooled", "quarter", "month"]) => {
  const groups = { pooled: "Whole window", quarter: "Quarters", month: "Months" };
  return kinds.map((k) => `<optgroup label="${groups[k]}">${DATA.meta.periods.filter((p) => p.kind === k)
    .map((p) => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</optgroup>`).join("");
};
const totalClean = () => DATA.meta.cleaning_report.reduce((a, r) => a + Number(r.rows_clean || 0), 0);
const windowLabel = () => `${monthTick(DATA.meta.summary.months[0], true)} – ${monthTick(DATA.meta.summary.months.at(-1), true)}`;

// ======================================================================
// Discoveries
// ======================================================================
export function renderDiscover(main) {
  const sm = DATA.meta.summary;
  const stories = DATA.stories.stories;
  main.innerHTML = `
  <section class="hero">
    <div>
      <div class="eyebrow">CSE3729 · Computational Social Media Analysis</div>
      <h1>What really connects Reddit's communities? <em>Beyond the hairball.</em></h1>
      <p class="lede">We followed <b>${fmtCompact(totalClean())}</b> comments by <b>${fmtCompact(sm.users_total)}</b> commenters across
        <b>${sm.subreddits}</b> subreddits (${windowLabel()}) and asked which communities share far more of their audience than
        their size and their users' activity would predict.</p>
      <div class="stats">
        <div class="stat"><b>${sm.subreddits}</b><span>subreddits in a stratified frame</span></div>
        <div class="stat"><b>${sm.months.length}</b><span>months of comments</span></div>
        <div class="stat"><b>${fmtPct(sm.cosine_density.all, 2)}</b><span>pairs linked by raw overlap</span></div>
        <div class="stat"><b>${fmtPct(sm.validated_density.all, 1)}</b><span>pairs with surprising overlap</span></div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <a class="btn primary" href="#/atlas">Open the Atlas →</a>
        <a class="btn" href="#/stories/${stories[0].id}">Start with the first story</a>
      </div>
    </div>
    <div class="hero-map" id="hero-map">
      <div class="map-host" style="position:absolute;inset:0"></div>
      <div class="toggle seg"><button data-v="raw">Raw overlap</button><button data-v="adjusted" class="on">Adjusted</button></div>
      <div class="caption" id="hero-cap"></div>
    </div>
  </section>
  <div class="page" style="padding-top:8px">
    <div class="section" style="margin-top:0">
      <h2>Four discoveries</h2>
      <p class="sub">Each story is computed from the data when the Atlas is built. Open one to walk through the evidence on the map, then keep exploring from where it ends.</p>
      <div class="cards">${stories.map((s, k) => `
        <a class="card" href="#/stories/${s.id}">
          <span class="n">Story ${k + 1}</span><h3>${esc(s.title)}</h3><p>${esc(s.question)}</p><span class="go">Walk through the evidence →</span>
        </a>`).join("")}</div>
    </div>
    <div class="section grid3">
      <div class="panel"><h3 style="font-size:16px;margin-bottom:6px">Circles are subreddits</h3><p class="secondary" style="margin:0">Size shows how many people commented there in the selected period. Colour shows the community it was grouped into.</p></div>
      <div class="panel"><h3 style="font-size:16px;margin-bottom:6px">Lines are surprising overlaps</h3><p class="secondary" style="margin:0">Two subreddits are linked only if they share far more commenters than chance predicts, given how big each one is and how many places their users comment.</p></div>
      <div class="panel"><h3 style="font-size:16px;margin-bottom:6px">“3.5×” means</h3><p class="secondary" style="margin:0">three and a half times as many shared commenters as expected. 1.0× is what chance alone would produce.</p></div>
    </div>
  </div>`;
  const host = main.querySelector(".map-host");
  const map = new AtlasMap(host, { interactive: false, labelThreshold: 13 });
  const cap = main.querySelector("#hero-cap");
  const show = async (v) => {
    main.querySelectorAll(".toggle button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
    await map.show({ period: "all", view: v });
    cap.textContent = v === "raw"
      ? `Raw overlap: ${fmtInt(map.graph.size)} links — almost every pair shares someone.`
      : `Adjusted: ${fmtInt(map.graph.size)} links that beat chance by a wide margin.`;
  };
  main.querySelectorAll(".toggle button").forEach((b) => b.addEventListener("click", () => show(b.dataset.v)));
  show("adjusted");
  return () => map.destroy();
}

// ======================================================================
// Atlas
// ======================================================================
export function renderAtlas(main, { params }) {
  const st = { period: params.period || "all", view: params.view || "adjusted", color: params.color || "community",
               sel: params.sel != null ? +params.sel : null, comm: params.comm != null ? +params.comm : null };
  main.innerHTML = `
  <div class="map-wrap" id="atlas">
    <div class="map-host" style="position:absolute;inset:0"></div>
    <aside class="rail">
      <div><h1>The Atlas</h1><p class="hint" style="margin:4px 0 0">Hover a circle to see its links, click to open it.</p></div>
      <div class="field"><label for="a-search">Find a subreddit</label><div id="a-search"></div></div>
      <div class="field"><label for="a-period">Period</label><select id="a-period">${periodOptions(st.period)}</select></div>
      <div class="field"><label>Links</label><div class="seg" id="a-view"><button data-v="adjusted">Surprising overlap</button><button data-v="raw">Raw overlap</button></div></div>
      <div class="field"><label>Colour by</label><div class="seg" id="a-color"><button data-v="community">Detected community</button><button data-v="category">Frame category</button></div></div>
      <div class="field"><label id="a-legend-title">Communities</label><div class="legend" id="a-legend"></div></div>
    </aside>
    <aside class="drawer closed" id="a-drawer" aria-live="polite"></aside>
    <div class="zoom"><button data-z="1.5" aria-label="Zoom in">+</button><button data-z="0.67" aria-label="Zoom out">−</button><button data-z="0" aria-label="Reset view">⟲</button></div>
    <div class="map-note" id="a-note"></div>
  </div>`;
  const wrap = main.querySelector("#atlas");
  const map = new AtlasMap(main.querySelector(".map-host"), { onSelect: (i) => select(i) });
  const drawer = main.querySelector("#a-drawer"), note = main.querySelector("#a-note");
  const search = searchBox(main.querySelector("#a-search"), { onPick: (n) => select(n.id) });

  const sync = () => replaceParams("atlas", [], { period: st.period !== "all" ? st.period : null, view: st.view !== "adjusted" ? st.view : null,
    color: st.color !== "community" ? st.color : null, sel: st.sel, comm: st.comm });

  function legend() {
    const box = main.querySelector("#a-legend");
    main.querySelector("#a-legend-title").textContent = st.color === "community" ? "Detected communities (click to isolate)" : "Frame categories";
    if (st.color === "community") {
      box.innerHTML = DATA.meta.communities.map((c) => `<button data-c="${c.id}" class="${st.comm === c.id ? "on" : ""}">
        <span class="dot" style="background:${communityColor(c.id)}"></span>${esc(c.label)}<small>${c.size}</small></button>`).join("");
      box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        st.comm = st.comm === +b.dataset.c ? null : +b.dataset.c;
        map.setCommunityFilter(st.comm); legend(); sync();
      }));
    } else {
      const counts = Object.fromEntries(CATEGORY_ORDER.map((c) => [c, DATA.nodes.filter((n) => n.category === c).length]));
      box.innerHTML = CATEGORY_ORDER.map((c) => `<button disabled style="cursor:default"><span class="dot" style="background:${categoryColor(c)}"></span>${esc(categoryLabel(c))}<small>${counts[c]}</small></button>`).join("");
    }
  }
  function segs() {
    main.querySelectorAll("#a-view button").forEach((b) => b.classList.toggle("on", b.dataset.v === st.view));
    main.querySelectorAll("#a-color button").forEach((b) => b.classList.toggle("on", b.dataset.v === st.color));
  }
  async function draw() {
    segs();
    const p = await map.show({ period: st.period, view: st.view });
    if (!p) return;
    const sm = DATA.meta.summary;
    note.textContent = st.view === "raw"
      ? `${periodLabel(st.period)} · raw overlap: ${fmtInt(map.graph.size)} links (${fmtPct(map.graph.size / (DATA.nodes.length * (DATA.nodes.length - 1) / 2), 2)} of all pairs) — size dominates`
      : `${periodLabel(st.period)} · ${fmtInt(map.graph.size)} surprising links (${fmtPct(sm.validated_density[st.period], 1)} of pairs, FDR ${sm.alpha * 100}%)`;
    if (st.sel != null) renderDrawer();
  }
  async function renderDrawer() {
    const i = st.sel;
    if (i == null) { drawer.classList.add("closed"); wrap.classList.remove("with-drawer"); return; }
    const n = DATA.nodes[i];
    const p = await loadPairs(st.period);
    const nb = neighbours(p, i, "affinity");
    const cos = neighbours(p, i, "cosine").slice(0, 5);
    drawer.innerHTML = `<button class="close" aria-label="Close">×</button>
      <div class="eyebrow">${esc(periodLabel(st.period))}</div>
      <h2>r/${esc(n.name)}</h2>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 14px">
        <span class="chip" title="Category assigned by the sampling frame"><span class="dot" style="background:${categoryColor(n.category)}"></span>Frame: ${esc(categoryLabel(n.category))}</span>
        <span class="chip" title="Community detected from surprising overlaps"><span class="dot" style="background:${communityColor(n.community)}"></span>Cluster: ${esc(communityLabel(n.community))}</span>
      </div>
      <div class="kpis" style="margin:0 0 16px;gap:22px">
        <div class="stat"><b style="font-size:22px">${fmtCompact(p.users[i])}</b><span>commenters</span></div>
        <div class="stat"><b style="font-size:22px">${nb.length}</b><span>surprising links</span></div>
        <div class="stat"><b style="font-size:22px">${n.participation.toFixed(2)}</b><span>connector score</span></div>
      </div>
      <div class="chart-title">Strongest surprising overlaps</div>
      <div class="chart-sub">Shared commenters ÷ expected. Click one to move there.</div>
      <div id="d-bars">${neighbourBars(nb, { max: 8 })}</div>
      <div class="chart-title" style="margin-top:18px">By raw overlap it would look closest to</div>
      <div class="pill-list" style="margin-top:6px">${cos.map((x) => `<a href="${hashFor("atlas", [], { period: st.period, sel: x.j })}"><span>r/${esc(DATA.nodes[x.j].name)}${DATA.nodes[x.j].category === "gateway" ? '<span class="hub">hub</span>' : ""}</span><span>${x.validated ? fmtX(x.affinity) : `${fmtX(x.affinity, 2)} n.s.`}</span></a>`).join("")}</div>
      <div style="display:flex;gap:8px;margin-top:18px;flex-wrap:wrap">
        <a class="btn primary" href="#/explore/${encodeURIComponent(n.name)}">Full profile</a>
        <a class="btn" href="${hashFor("compare", [], { a: n.name })}">Compare…</a>
      </div>`;
    drawer.querySelector(".close").addEventListener("click", () => select(null));
    wireBars(drawer, (j) => select(j));
    drawer.querySelectorAll(".pill-list a").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); select(+new URLSearchParams(a.getAttribute("href").split("?")[1]).get("sel")); }));
    drawer.classList.remove("closed"); wrap.classList.add("with-drawer");
  }
  function select(i) {
    st.sel = i;
    map.select(i);
    search.set(i == null ? null : DATA.nodes[i]);
    renderDrawer(); sync();
  }

  main.querySelector("#a-period").addEventListener("change", (e) => { st.period = e.target.value; draw(); sync(); });
  main.querySelectorAll("#a-view button").forEach((b) => b.addEventListener("click", () => { st.view = b.dataset.v; draw(); sync(); }));
  main.querySelectorAll("#a-color button").forEach((b) => b.addEventListener("click", () => {
    st.color = b.dataset.v; if (st.color === "category") { st.comm = null; map.setCommunityFilter(null); }
    map.setColorBy(st.color); segs(); legend(); sync();
  }));
  main.querySelectorAll(".zoom button").forEach((b) => b.addEventListener("click", () => (+b.dataset.z ? map.zoom(+b.dataset.z) : map.reset())));
  map.setColorBy(st.color);
  map.setCommunityFilter(st.comm);
  legend();
  draw().then(() => { if (st.sel != null) { map.select(st.sel); search.set(DATA.nodes[st.sel]); } });
  return () => map.destroy();
}

// ======================================================================
// Explore (subreddit profile)
// ======================================================================
export function renderExplore(main, { args, params }) {
  const n = args[0] ? DATA.byName.get(args[0].toLowerCase()) : null;
  if (!n) return renderExploreIndex(main, args[0]);
  const period = params.period || "all";
  const i = n.id;
  main.innerHTML = `<div class="page">
    <div class="toolbar"><div class="field" style="flex:1;max-width:360px"><label>Another subreddit</label><div id="e-search"></div></div>
      <div class="field" style="max-width:220px"><label for="e-period">Relationships in</label><select id="e-period">${periodOptions(period, ["pooled", "quarter"])}</select></div>
      <a class="btn" href="${hashFor("atlas", [], { sel: i, period: period !== "all" ? period : null })}">Show on map</a>
      <a class="btn" href="${hashFor("compare", [], { a: n.name })}">Compare…</a></div>
    <div class="profile-head">
      <div><div class="eyebrow">Subreddit profile</div><h1>r/${esc(n.name)}</h1></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;padding-bottom:8px">
        <span class="chip"><span class="dot" style="background:${categoryColor(n.category)}"></span>Frame category: ${esc(categoryLabel(n.category))}</span>
        <span class="chip"><span class="dot" style="background:${communityColor(n.community)}"></span>Detected community: ${esc(communityLabel(n.community))}</span>
      </div>
    </div>
    <div class="kpis" id="e-kpis"></div>
    <div class="section grid2">
      <div class="panel"><div class="chart-title">Strongest surprising overlaps</div>
        <div class="chart-sub">Validated links ranked by affinity (shared ÷ expected commenters), ${esc(periodLabel(period))}.</div><div id="e-bars"></div></div>
      <div class="panel"><div class="chart-title">What popularity would have shown instead</div>
        <div class="chart-sub">Top neighbours by raw cosine overlap vs by adjusted affinity. Front-page hubs are tagged.</div>
        <div class="grid2" id="e-hid" style="gap:12px"></div></div>
    </div>
    <div class="section panel"><div class="chart-title">Weekly commenters</div><div class="chart-sub">Distinct accounts commenting each week (first and last weeks are partial).</div><div id="e-weekly"></div></div>
    <div class="section panel"><div class="chart-title">How its strongest relationships moved month by month</div>
      <div class="chart-sub">Affinity with its three strongest overall neighbours. Filled points: significant that month; hollow: not significant.</div><div id="e-monthly"><div class="empty">Loading monthly networks…</div></div></div>
    <div class="section panel"><div class="chart-title">Connector role by quarter</div>
      <div class="chart-sub">Participation coefficient: 0 = all surprising links stay inside its own community; towards 1 = spread evenly across communities.</div><div id="e-role"></div></div>
  </div>`;
  searchBox(main.querySelector("#e-search"), { onPick: (m) => { location.hash = hashFor("explore", [m.name], { period: period !== "all" ? period : null }); } });
  main.querySelector("#e-period").addEventListener("change", (e) => { location.hash = hashFor("explore", [n.name], { period: e.target.value !== "all" ? e.target.value : null }); });

  (async () => {
    const p = await loadPairs(period);
    const nb = neighbours(p, i, "affinity");
    const cos = neighbours(p, i, "cosine");
    const reached = new Set(nb.map((x) => DATA.nodes[x.j].community));
    main.querySelector("#e-kpis").innerHTML = `
      <div class="stat"><b>${fmtInt(p.users[i])}</b><span>commenters (${esc(periodLabel(period))})</span></div>
      <div class="stat"><b>${nb.length}</b><span>surprising links</span></div>
      <div class="stat"><b>${reached.size}</b><span>communities reached</span></div>
      <div class="stat"><b>${nb.length ? fmtX(nb[0].affinity) : "–"}</b><span>strongest affinity${nb.length ? ` (r/${esc(DATA.nodes[nb[0].j].name)})` : ""}</span></div>`;
    const bars = main.querySelector("#e-bars");
    bars.innerHTML = neighbourBars(nb, { max: 12 });
    wireBars(bars, (j) => { location.hash = hashFor("explore", [DATA.nodes[j].name], { period: period !== "all" ? period : null }); });
    const col = (title, list, by) => `<div class="list-col"><h4>${title}</h4><div class="pill-list">${list.slice(0, 8).map((x) => {
      const m = DATA.nodes[x.j];
      return `<a href="#/explore/${encodeURIComponent(m.name)}"><span>r/${esc(m.name)}${m.category === "gateway" ? '<span class="hub">hub</span>' : ""}</span><span>${by === "cos" ? x.cosine.toFixed(3) : fmtX(x.affinity)}</span></a>`;
    }).join("")}</div></div>`;
    main.querySelector("#e-hid").innerHTML = col("Raw overlap (cosine)", cos, "cos") + col("Adjusted affinity", nb, "aff");

    const A = DATA.activity;
    lineChart(main.querySelector("#e-weekly"), {
      labels: A.weeks, series: [{ name: `r/${n.name}`, color: communityColor(n.community), values: A.weekly_authors[i] }],
      format: (v) => fmtCompact(v), tickFormat: (w, long) => monthTick(w, long), xTickEvery: 6,
      events: DATA.meta.events.map((e) => ({ x: e.date, label: e.label, short: "" })), ariaLabel: `Weekly commenters in r/${n.name}`,
    });

    const all = await loadPairs("all");
    const top3 = neighbours(all, i, "affinity").slice(0, 3);
    const months = DATA.meta.periods.filter((x) => x.kind === "month").map((x) => x.id);
    const mp = await Promise.all(months.map((m) => loadPairs(m)));
    const box = main.querySelector("#e-monthly");
    if (!top3.length) box.innerHTML = `<div class="empty">r/${esc(n.name)} has no surprising links over the whole window.</div>`;
    else lineChart(box, {
      labels: months, tickFormat: (m, long) => monthTick(m, long), format: (v) => fmtX(v), yMin: 0,
      series: top3.map((x, k) => {
        const st = mp.map((pp) => pairStats(pp, i, x.j));
        return { name: `r/${DATA.nodes[x.j].name}`, color: ["#3987e5", "#d95926", "#199e70"][k], values: st.map((s) => (s.expected > 0 ? s.affinity : null)), points: st.map((s) => s.validated) };
      }),
      ariaLabel: `Monthly affinity of r/${n.name} with its strongest neighbours`,
    });
    const qs = DATA.meta.summary.quarters;
    main.querySelector("#e-role").innerHTML = `<table class="data"><thead><tr><th>Quarter</th><th class="r">Participation</th><th class="r">Rank among ${DATA.nodes.length}</th></tr></thead><tbody>${qs.map((q) => {
      const vals = DATA.nodes.map((m) => m.participation_by_quarter[q]);
      const rank = 1 + vals.filter((v) => v > n.participation_by_quarter[q]).length;
      return `<tr><td>${esc(periodLabel(q))}</td><td class="r">${n.participation_by_quarter[q].toFixed(2)}</td><td class="r">${rank}</td></tr>`;
    }).join("")}</tbody></table>`;
  })();
  return null;
}

function renderExploreIndex(main, missing) {
  const conn = DATA.stories.stories.find((s) => s.id === "connectors");
  const picks = ["personalfinance", "Bitcoin", "marvelstudios", "CanadaPolitics", "depression", "Python", "smoking", "AskReddit"].filter((x) => DATA.byName.has(x.toLowerCase()));
  main.innerHTML = `<div class="page">
    <div class="eyebrow">Subreddit explorer</div><h1 style="font-size:36px;margin-bottom:10px">Pick a community</h1>
    ${missing ? `<p class="muted">“${esc(missing)}” is not in the 170-subreddit frame.</p>` : ""}
    <p class="lede">Search any of the ${DATA.nodes.length} subreddits to see what it shares an unusually large audience with, how that compares with raw overlap, and how its activity and relationships moved month by month.</p>
    <div style="max-width:460px;margin:22px 0" id="x-search"></div>
    <div class="section"><h2>Good places to start</h2><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">${picks.map((p) => {
      const n = DATA.byName.get(p.toLowerCase());
      return `<a class="chip" style="font-size:14px;padding:6px 12px" href="#/explore/${encodeURIComponent(n.name)}"><span class="dot" style="background:${communityColor(n.community)}"></span>r/${esc(n.name)}</a>`;
    }).join("")}</div></div>
    ${conn ? `<div class="section"><h2>Top connectors</h2><div class="pill-list" style="max-width:520px;margin-top:10px">${conn.metrics.connectors.map((c) => `<a href="#/explore/${encodeURIComponent(c.name)}"><span>r/${esc(c.name)}</span><span>${c.participation_min.toFixed(2)}</span></a>`).join("")}</div></div>` : ""}
  </div>`;
  searchBox(main.querySelector("#x-search"), { onPick: (n) => { location.hash = `#/explore/${encodeURIComponent(n.name)}`; } });
  return null;
}
