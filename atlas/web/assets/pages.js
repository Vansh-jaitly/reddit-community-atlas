// Start (scroll-driven opening), Atlas (explorer) and Explore (subreddit profile) pages.
import {
  DATA, loadPairs, loadPipeline, neighbours, pairStats, communityColor, categoryColor, categoryLabel, communityLabel,
  fmtInt, fmtPct, fmtX, fmtCompact, esc, periodLabel, hashFor, replaceParams, searchBox, neighbourBars, wireBars,
  registerPage, isMobile, CATEGORY_ORDER, REDUCED_MOTION, setOn, communitiesPhrase,
} from "./core.js";
import { AtlasMap } from "./map.js";
import { lineChart, monthTick } from "./charts.js";
import { startTour } from "./tour.js";

const periodOptions = (sel, kinds = ["pooled", "quarter", "month"]) => {
  const groups = { pooled: "Whole window", quarter: "Quarters", month: "Months" };
  return kinds.map((k) => `<optgroup label="${groups[k]}">${DATA.meta.periods.filter((p) => p.kind === k)
    .map((p) => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</optgroup>`).join("");
};
const totalClean = () => DATA.meta.cleaning_report.reduce((a, r) => a + Number(r.rows_clean || 0), 0);
const windowLabel = () => `${monthTick(DATA.meta.summary.months[0], true)} – ${monthTick(DATA.meta.summary.months.at(-1), true)}`;
const story = (id) => DATA.stories.stories.find((s) => s.id === id);

/** The legend used wherever a map appears. */
export function legendHTML(compact = false) {
  return `<div class="legend-grid ${compact ? "compact" : ""}">
    <div><i class="lg-node"></i><span><b>Circle</b> one subreddit; size = commenters in the period</span></div>
    <div><i class="lg-edge"></i><span><b>Line</b> the two share more commenters than chance predicts; thicker = further beyond chance</span></div>
    <div><i class="lg-comm"></i><span><b>Colour</b> the community a subreddit was grouped into by its links</span></div>
    <div><i class="lg-dist"></i><span><b>Distance</b> is a layout convenience, not a measurement</span></div>
  </div>`;
}

// ======================================================================
// Start
// ======================================================================
export function renderStart(main) {
  const sm = DATA.meta.summary;
  const stories = DATA.stories.stories;
  const A = story("popularity"), B = story("neighbours");
  const lead = B && B.metrics.top_links[0];
  const big = A ? DATA.byName.get(A.metrics.biggest.toLowerCase()) : null;
  const ex = A ? DATA.byName.get(A.metrics.example.toLowerCase()) : null;
  const pa = lead ? DATA.byName.get(lead.a.toLowerCase()) : null, pb = lead ? DATA.byName.get(lead.b.toLowerCase()) : null;

  main.innerHTML = `
  <section class="scrolly" id="scrolly">
    <div class="scrolly-stage" aria-hidden="true">
      <div class="map-host"></div>
      <div class="stage-caption" id="stage-cap"></div>

    </div>
    <div class="scrolly-steps">
      <article class="step" data-step="0">
        <div class="eyebrow">Beyond the hairball · a Reddit community atlas</div>
        <h1>Two communities share thousands of commenters.<br><em>Are their audiences unusually connected?</em></h1>
        <p class="lede">Sometimes. Mostly not. Big communities share people with everyone, so the raw number says little. This atlas follows <b>${fmtCompact(totalClean())}</b> comments by <b>${fmtCompact(sm.users_total)}</b> people across <b>${sm.subreddits}</b> subreddits (${windowLabel()}) and asks, for every pair, whether the overlap is more than size and activity would produce.</p>
        <div class="pair-cards" id="pair-cards"></div>
        <div class="cta-row"><button class="btn primary" id="cta-tour">Take the 5-minute tour</button><a class="btn" href="#/atlas">Open the atlas</a></div>
        <div class="scroll-hint muted">Scroll to see how the map is made ↓</div>
      </article>
      <article class="step" data-step="1">
        <div class="eyebrow">Step 1 · the obvious map</div>
        <h2>Link every pair that shares a commenter, and almost everything connects</h2>
        <p><b>${fmtPct(sm.cosine_density.all, 2)}</b> of all pairs are linked. One person who comments in many communities links all of them to each other, and a few very active people do most of the linking.<span id="omnivore"></span></p>
        <p class="muted">A map like this mostly shows which communities are big.</p>
      </article>
      <article class="step" data-step="2">
        <div class="eyebrow">Step 2 · ask what chance would produce</div>
        <h2>For each pair, how many commenters would they share by chance alone?</h2>
        <p>Imagine a shuffled Reddit in which every person keeps their number of communities and every community keeps its number of commenters, but who comments where is random. That gives an <b>expected</b> overlap for every pair. <span class="lg-inline grey">Grey</span> lines share about that much. <span class="lg-inline color">Coloured</span> lines share far more.</p>
      </article>
      <article class="step" data-step="3">
        <div class="eyebrow">Step 3 · keep only the surprising</div>
        <h2>What remains is a readable map with ${communitiesPhrase(sm)}</h2>
        <p><b>${fmtPct(sm.validated_density.all, 1)}</b> of pairs share more commenters than chance predicts (a 1% false-discovery rate over all ${fmtInt(sm.subreddits * (sm.subreddits - 1) / 2)} pairs). Grouping subreddits by those links gives communities that mostly follow topics, with a few telling exceptions.</p>
        ${legendHTML()}
      </article>
      <article class="step" data-step="4">
        <div class="eyebrow">What the map reveals</div>
        <h2>${stories.length} discoveries, each with its evidence</h2>
        <div class="cards" id="start-cards">${stories.map((s, k) => `
          <a class="card" href="#/stories/${s.id}"><span class="n">Discovery ${k + 1}</span><h3>${esc(s.title)}</h3><p>${esc(s.question)}</p><span class="go">See the evidence →</span></a>`).join("")}</div>
        <div class="cta-row"><button class="btn primary" id="cta-tour-2">Take the guided tour</button><a class="btn" href="#/pipeline">How the numbers are made</a><a class="btn ghost" href="#/about">Scope &amp; limits</a></div>
      </article>
    </div>
  </section>`;

  const host = main.querySelector(".map-host");
  const map = new AtlasMap(host, { interactive: false, labelThreshold: 12 });
  const cap = main.querySelector("#stage-cap");
  const pairCards = async () => {
    const p = await loadPairs("all");
    const cards = [];
    if (big && ex) cards.push({ a: big, b: ex, s: pairStats(p, big.id, ex.id), tone: "plain" });
    if (pa && pb) cards.push({ a: pa, b: pb, s: pairStats(p, pa.id, pb.id), tone: "surprise" });
    main.querySelector("#pair-cards").innerHTML = cards.map((c) => `
      <a class="pair-card ${c.tone}" href="${hashFor("compare", [], { a: c.a.name, b: c.b.name })}">
        <div class="pc-names"><span>r/${esc(c.a.name)}</span><i>×</i><span>r/${esc(c.b.name)}</span></div>
        <div class="pc-nums"><div><b>${fmtInt(c.s.shared)}</b><span>shared commenters</span></div><div><b>${fmtInt(c.s.expected)}</b><span>expected by chance</span></div><div class="pc-aff"><b>${fmtX(c.s.affinity, c.s.affinity < 1.5 ? 2 : 1)}</b><span>${c.s.validated ? "surprising" : "what chance gives"}</span></div></div>
      </a>`).join("");
    return cards;
  };
  const STEPS = [
    { view: "adjusted", cap: "The four subreddits from the question. Lines are surprising shared audiences.",
      apply: (cards) => { const ids = cards.flatMap((c) => [c.a.id, c.b.id]); map.setFocus(ids, cards.filter((c) => c.s.validated).map((c) => [c.a.id, c.b.id])); map.setCallouts(cards.flatMap((c, k) => [{ id: c.a.id, tone: k ? "below" : "above" }, { id: c.b.id, tone: k ? "below" : "above" }])); map.flyTo(ids, 0.5); } },
    { view: "raw", cap: `Raw overlap: ${fmtPct(sm.cosine_density.all, 2)} of pairs linked.`, apply: () => { map.clearState(); map.reset(); } },
    { view: "surprise", cap: "Grey = about what chance predicts · colour = far more than chance.", apply: () => { map.clearState(); map.reset(); } },
    { view: "adjusted", cap: `${fmtInt(sm.validated_edges.all)} surprising links · ${sm.anchor.communities} communities.`, apply: () => { map.clearState(); map.reset(); }, legend: true },
    { view: "adjusted", cap: "Pick a discovery, or take the tour.", apply: () => { map.clearState(); map.reset(); } },
  ];
  let cards = [], current = -1, pending = null;
  async function setStep(k) {
    if (k === current) return;
    current = k;
    const s = STEPS[k];
    const token = (pending = {});
    await map.show({ view: s.view, period: "all" });
    if (pending !== token) return;
    s.apply(cards);
    cap.textContent = s.cap;
    main.querySelectorAll(".step").forEach((el, j) => el.classList.toggle("is-active", j === k));
  }
  const ready = (async () => {
    cards = await pairCards();
    try {
      const pl = await loadPipeline();
      const h = pl.stages.bipartite.breadth_histogram, users = h.reduce((a, b) => a + b.users, 0), pairs = h.reduce((a, b) => a + b.pairs_linked, 0);
      const wide = h.filter((b) => parseInt(b.breadth, 10) > 20);
      const wu = wide.reduce((a, b) => a + b.users, 0), wp = wide.reduce((a, b) => a + b.pairs_linked, 0);
      main.querySelector("#omnivore").innerHTML = ` People active in more than ${parseInt(wide[0].breadth, 10) - 1} of these subreddits are <b>${fmtPct(wu / users, 1)}</b> of commenters but create <b>${fmtPct(wp / pairs, 0)}</b> of all the links drawn.`;
    } catch { /* pipeline facts are optional here */ }
    await setStep(0);
  })();
  const io = new IntersectionObserver((entries) => {
    const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (vis) setStep(+vis.target.dataset.step);
  }, { threshold: [0.35, 0.6], rootMargin: isMobile() ? "-40% 0px -20% 0px" : "-25% 0px -25% 0px" });
  main.querySelectorAll(".step").forEach((el) => io.observe(el));
  main.querySelector("#cta-tour").addEventListener("click", startTour);
  main.querySelector("#cta-tour-2").addEventListener("click", startTour);
  registerPage({ name: "start", ready, map, scrollTo: (k) => { const el = main.querySelector(`.step[data-step="${k}"]`); if (el) el.scrollIntoView({ behavior: REDUCED_MOTION ? "auto" : "smooth", block: "start" }); } });
  return () => { io.disconnect(); map.destroy(); };
}

// ======================================================================
// Atlas (explorer)
// ======================================================================
export function renderAtlas(main, { params }) {
  const VIEWS = { adjusted: "Surprising links", surprise: "Chance vs surprise", raw: "Raw overlap" };
  // URL arguments are untrusted: an unknown period, node or community falls back to the overview instead of throwing
  const validPeriod = (p) => (p && DATA.meta.periods.some((x) => x.id === p) ? p : "all");
  const validNode = (v) => (v != null && Number.isInteger(+v) && DATA.nodes[+v] ? +v : null);
  const st = { period: validPeriod(params.period), view: VIEWS[params.view] ? params.view : "adjusted", color: params.color === "category" ? "category" : "community",
               sel: validNode(params.sel), comm: params.comm != null && Number.isInteger(+params.comm) && DATA.meta.communities.some((c) => c.id === +params.comm) ? +params.comm : null };
  main.innerHTML = `
  <div class="map-wrap" id="atlas">
    <div class="map-host" style="position:absolute;inset:0"></div>
    <button class="btn rail-toggle" id="a-rail-toggle" aria-expanded="false" aria-controls="a-rail">Controls</button>
    <aside class="rail" id="a-rail">
      <div class="rail-head"><h1>The atlas</h1><button class="btn ghost small" id="a-help" aria-expanded="false">How to read it</button></div>
      <div class="help-pop" id="a-help-pop" hidden>${legendHTML()}<p class="muted" style="margin:10px 0 0;font-size:12.5px">Hover a circle to see its links; click to open it. Everything shown is read from the published data files, not computed live.</p></div>
      <div class="field"><label for="a-search">Find a subreddit</label><div id="a-search"></div></div>
      <div class="field"><label for="a-period">Period</label><select id="a-period">${periodOptions(st.period)}</select></div>
      <div class="field"><label>Lines</label><div class="seg vertical" id="a-view">${Object.entries(VIEWS).map(([k, v]) => `<button data-v="${k}">${v}</button>`).join("")}</div><div class="hint" id="a-view-hint"></div></div>
      <div class="field"><label>Colour by</label><div class="seg" id="a-color"><button data-v="community" title="Leiden communities detected on the surprising links">Groups found in the data</button><button data-v="category" title="The keyword categories we assigned before any analysis">Our labels before analysis</button></div></div>
      <div class="field"><label id="a-legend-title">Communities</label><div class="legend" id="a-legend"></div></div>
      <button class="btn" id="a-overview" hidden>← Back to overview</button>
    </aside>
    <aside class="drawer closed" id="a-drawer" aria-live="polite"></aside>
    <div class="zoom"><button data-z="1.5" aria-label="Zoom in">+</button><button data-z="0.67" aria-label="Zoom out">−</button><button data-z="0" aria-label="Reset view">⟲</button></div>
    <div class="map-note" id="a-note"></div>
  </div>`;
  const wrap = main.querySelector("#atlas");
  const map = new AtlasMap(main.querySelector(".map-host"), {
    onSelect: (i) => select(i),
    // land a selected node beside the drawer (desktop) or above the bottom sheet (phones), never under them
    flyOffset: () => (isMobile() ? { dy: 0.28 * wrap.clientHeight } : { dx: 190 }),
  });
  const drawer = main.querySelector("#a-drawer"), note = main.querySelector("#a-note"), overviewBtn = main.querySelector("#a-overview");
  const search = searchBox(main.querySelector("#a-search"), { onPick: (n) => select(n.id) });
  const rail = main.querySelector("#a-rail"), railToggle = main.querySelector("#a-rail-toggle");
  railToggle.addEventListener("click", () => { const open = rail.classList.toggle("open"); railToggle.setAttribute("aria-expanded", String(open)); });
  const help = main.querySelector("#a-help"), helpPop = main.querySelector("#a-help-pop");
  help.addEventListener("click", () => { helpPop.hidden = !helpPop.hidden; help.setAttribute("aria-expanded", String(!helpPop.hidden)); });

  const sync = () => replaceParams("atlas", [], { period: st.period !== "all" ? st.period : null, view: st.view !== "adjusted" ? st.view : null,
    color: st.color !== "community" ? st.color : null, sel: st.sel, comm: st.comm });
  const hints = {
    adjusted: "Only pairs that share more commenters than size and activity predict.",
    surprise: "Every pair sharing a commenter: grey within chance, coloured when surprising.",
    raw: "Every pair sharing at least one commenter, weighted by raw overlap.",
  };

  function legend() {
    const box = main.querySelector("#a-legend");
    main.querySelector("#a-legend-title").textContent = st.color === "community" ? "Detected communities (click to isolate)" : "Frame categories";
    if (st.color === "community") {
      box.innerHTML = DATA.meta.communities.map((c) => `<button data-c="${c.id}" class="${st.comm === c.id ? "on" : ""}" aria-pressed="${st.comm === c.id}">
        <span class="dot" style="background:${communityColor(c.id)}"></span>${esc(c.label)}<small>${c.size}</small></button>`).join("");
      box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        st.comm = st.comm === +b.dataset.c ? null : +b.dataset.c;
        map.setCommunityFilter(st.comm); legend(); sync(); overview();
      }));
    } else {
      const counts = Object.fromEntries(CATEGORY_ORDER.map((c) => [c, DATA.nodes.filter((n) => n.category === c).length]));
      box.innerHTML = CATEGORY_ORDER.map((c) => `<div class="legend-static"><span class="dot" style="background:${categoryColor(c)}"></span>${esc(categoryLabel(c))}<small>${counts[c]}</small></div>`).join("");
    }
  }
  function segs() {
    main.querySelectorAll("#a-view button").forEach((b) => setOn(b, b.dataset.v === st.view));
    main.querySelectorAll("#a-color button").forEach((b) => setOn(b, b.dataset.v === st.color));
    main.querySelector("#a-view-hint").textContent = hints[st.view];
  }
  function overview() { overviewBtn.hidden = st.sel == null && st.comm == null; }
  let ready = Promise.resolve();
  async function draw() {
    segs();
    const p = await map.show({ period: st.period, view: st.view });
    if (!p) return;
    const sm = DATA.meta.summary;
    const total = DATA.nodes.length * (DATA.nodes.length - 1) / 2;
    note.textContent = st.view === "raw"
      ? `${periodLabel(st.period)} · raw overlap: ${fmtInt(map.graph.size)} links (${fmtPct(map.graph.size / total, 2)} of all pairs) — size dominates`
      : st.view === "surprise"
        ? `${periodLabel(st.period)} · ${fmtInt(p.validated.length)} surprising links in colour among ${fmtInt(map.graph.size)} raw links`
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
    const av = neighbours(p, i, "avoided").slice(0, 4);
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
        <div class="stat"><b style="font-size:22px">${n.participation.toFixed(2)}</b><span title="Participation coefficient: 0 = every surprising link stays inside its own cluster, towards 1 = links spread evenly across clusters">links spread across clusters</span></div>
      </div>
      <div class="chart-title">Strongest surprising overlaps</div>
      <div class="chart-sub">Shared commenters ÷ expected. Click one to move there.</div>
      <div id="d-bars">${neighbourBars(nb, { max: 8 })}</div>
      ${av.length ? `<div class="chart-title" style="margin-top:18px">Shares <em>fewer</em> commenters than chance with</div><div class="pill-list" style="margin-top:6px">${av.map((x) => `<a href="${hashFor("compare", [], { a: n.name, b: DATA.nodes[x.j].name })}"><span>r/${esc(DATA.nodes[x.j].name)}</span><span>${fmtX(x.affinity, 2)}</span></a>`).join("")}</div>` : ""}
      <div class="chart-title" style="margin-top:18px">By raw overlap it would look closest to</div>
      <div class="pill-list" style="margin-top:6px">${cos.map((x) => `<button class="pill-btn" data-j="${x.j}"><span>r/${esc(DATA.nodes[x.j].name)}${DATA.nodes[x.j].category === "gateway" ? '<span class="hub">hub</span>' : ""}</span><span>${x.validated ? fmtX(x.affinity) : `${fmtX(x.affinity, 2)} · within chance`}</span></button>`).join("")}</div>
      <div style="display:flex;gap:8px;margin-top:18px;flex-wrap:wrap">
        <a class="btn primary" href="#/explore/${encodeURIComponent(n.name)}">Full profile</a>
        <a class="btn" href="${hashFor("compare", [], { a: n.name })}">Compare…</a>
      </div>`;
    drawer.querySelector(".close").addEventListener("click", () => select(null));
    wireBars(drawer, (j) => select(j));
    drawer.querySelectorAll(".pill-btn").forEach((b) => b.addEventListener("click", () => select(+b.dataset.j)));
    drawer.classList.remove("closed"); wrap.classList.add("with-drawer");
  }
  function select(i) {
    st.sel = i;
    map.select(i);
    search.set(i == null ? null : DATA.nodes[i]);
    renderDrawer(); sync(); overview();
    if (isMobile()) { rail.classList.remove("open"); railToggle.setAttribute("aria-expanded", "false"); }
  }
  overviewBtn.addEventListener("click", () => { st.sel = null; st.comm = null; map.clearState(); map.reset(); search.set(null); legend(); renderDrawer(); sync(); overview(); });
  main.querySelector("#a-period").addEventListener("change", (e) => { st.period = e.target.value; ready = draw(); sync(); });
  main.querySelectorAll("#a-view button").forEach((b) => b.addEventListener("click", () => { st.view = b.dataset.v; ready = draw(); sync(); }));
  main.querySelectorAll("#a-color button").forEach((b) => b.addEventListener("click", () => {
    st.color = b.dataset.v; if (st.color === "category") { st.comm = null; map.setCommunityFilter(null); }
    map.setColorBy(st.color); segs(); legend(); sync(); overview();
  }));
  main.querySelectorAll(".zoom button").forEach((b) => b.addEventListener("click", () => (+b.dataset.z ? map.zoom(+b.dataset.z) : map.reset())));
  map.setColorBy(st.color);
  map.setCommunityFilter(st.comm);
  legend(); overview();
  ready = draw().then(() => { if (st.sel != null) { map.select(st.sel); search.set(DATA.nodes[st.sel]); } });
  registerPage({
    name: "atlas", map, get ready() { return ready; },
    setView: (v) => { st.view = v; sync(); return (ready = draw()); },
    setPeriod: (p) => { st.period = p; main.querySelector("#a-period").value = p; sync(); return (ready = draw()); },
    select: (i) => select(i), focus: (ids, edges) => map.setFocus(ids, edges), reset: () => { select(null); map.reset(); },
  });
  return () => map.destroy();
}

// ======================================================================
// Explore (subreddit profile)
// ======================================================================
/** Event markers for a subreddit's activity chart: only the crowd events that concern it. */
function nodeEvents(name) {
  const cr = ((DATA.stories && DATA.stories.stories) || []).find((s) => s.id === "crowds");
  const m = cr ? cr.metrics : {};
  const groups = [];
  if (m.crypto_monthly_authors && name in m.crypto_monthly_authors) groups.push("crypto");
  if (m.marvel_monthly_authors && name in m.marvel_monthly_authors) groups.push("marvel");
  if (m.starwars && m.starwars.name === name) groups.push("starwars");
  const evs = (DATA.meta.events || []).filter((e) => groups.includes(e.group)).map((e) => ({ x: e.date, label: e.label, short: "" }));
  if (groups.includes("starwars") && m.starwars.release) evs.push({ x: m.starwars.release, label: "The Last Jedi US release", short: "" });
  return evs;
}

export function renderExplore(main, { args, params }) {
  const n = args[0] ? DATA.byName.get(args[0].toLowerCase()) : null;
  if (!n) return renderExploreIndex(main, args[0]);
  const period = params.period && DATA.meta.periods.some((x) => x.id === params.period) ? params.period : "all";
  const i = n.id;
  main.innerHTML = `<div class="page">
    <div class="toolbar"><div class="field" style="flex:1;max-width:360px"><label>Another subreddit</label><div id="e-search"></div></div>
      <div class="field" style="max-width:220px"><label for="e-period">Relationships in</label><select id="e-period">${periodOptions(period)}</select></div>
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
    <div class="section grid2" id="e-row2">
      <div class="panel"><div class="chart-title">Shares fewer commenters than chance with</div>
        <div class="chart-sub">Pairs whose overlap falls significantly short of expectation (at most half, expected ≥ 20).</div><div id="e-avoid"></div></div>
      <div class="panel"><div class="chart-title">Connector role by quarter</div>
        <div class="chart-sub">Participation coefficient: 0 = all surprising links stay inside its own community; towards 1 = spread evenly across communities.</div><div id="e-role"></div></div>
    </div>
    <div class="section panel"><div class="chart-title">Weekly commenters</div><div class="chart-sub">Distinct accounts commenting each week (first and last weeks are partial).</div><div id="e-weekly"></div></div>
    <div class="section panel"><div class="chart-title">How its strongest relationships moved month by month</div>
      <div class="chart-sub">Affinity with its three strongest overall neighbours. Filled points: significant that month; hollow: not significant.</div><div id="e-monthly"><div class="empty">Loading monthly networks…</div></div></div>
  </div>`;
  searchBox(main.querySelector("#e-search"), { onPick: (m) => { location.hash = hashFor("explore", [m.name], { period: period !== "all" ? period : null }); } });
  main.querySelector("#e-period").addEventListener("change", (e) => { location.hash = hashFor("explore", [n.name], { period: e.target.value !== "all" ? e.target.value : null }); });

  const ready = (async () => {
    const p = await loadPairs(period);
    const nb = neighbours(p, i, "affinity");
    const cos = neighbours(p, i, "cosine");
    const av = neighbours(p, i, "avoided");
    const reached = new Set(nb.map((x) => DATA.nodes[x.j].community));
    main.querySelector("#e-kpis").innerHTML = `
      <div class="stat"><b>${fmtInt(p.users[i])}</b><span>commenters (${esc(periodLabel(period))})</span></div>
      <div class="stat"><b>${nb.length}</b><span>surprising links</span></div>
      <div class="stat"><b>${reached.size}</b><span>communities reached</span></div>
      <div class="stat"><b>${nb.length ? fmtX(nb[0].affinity) : "–"}</b><span>strongest affinity${nb.length ? ` (r/${esc(DATA.nodes[nb[0].j].name)})` : ""}</span></div>`;
    const bars = main.querySelector("#e-bars");
    bars.innerHTML = neighbourBars(nb, { max: 12, empty: `r/${n.name} has no surprising links in this period: its audience overlaps with others about as much as chance predicts.` });
    wireBars(bars, (j) => { location.hash = hashFor("explore", [DATA.nodes[j].name], { period: period !== "all" ? period : null }); });
    const col = (title, list, by) => `<div class="list-col"><h4>${title}</h4><div class="pill-list">${list.slice(0, 8).map((x) => {
      const m = DATA.nodes[x.j];
      return `<a href="#/explore/${encodeURIComponent(m.name)}"><span>r/${esc(m.name)}${m.category === "gateway" ? '<span class="hub">hub</span>' : ""}</span><span>${by === "cos" ? x.cosine.toFixed(3) : fmtX(x.affinity)}</span></a>`;
    }).join("")}</div></div>`;
    main.querySelector("#e-hid").innerHTML = col("Raw overlap (cosine)", cos, "cos") + col("Adjusted affinity", nb, "aff");
    const avBox = main.querySelector("#e-avoid");
    avBox.innerHTML = neighbourBars(av, { max: 6, metric: "avoided", empty: "None in this period." });
    wireBars(avBox, (j) => { location.hash = hashFor("compare", [], { a: n.name, b: DATA.nodes[j].name }); });

    const A = DATA.activity;
    lineChart(main.querySelector("#e-weekly"), {
      labels: A.weeks, series: [{ name: `r/${n.name}`, color: communityColor(n.community), values: A.weekly_authors[i] }],
      format: (v) => fmtCompact(v), tickFormat: (w, long) => monthTick(w, long), xTickEvery: 6,
      events: nodeEvents(n.name), ariaLabel: `Weekly commenters in r/${n.name}`,
    });
    const qs = DATA.meta.summary.quarters;
    main.querySelector("#e-role").innerHTML = `<table class="data"><thead><tr><th>Quarter</th><th class="r">Participation</th><th class="r">Rank of ${DATA.nodes.length}</th></tr></thead><tbody>${qs.map((q) => {
      const vals = DATA.nodes.map((m) => m.participation_by_quarter[q]);
      const rank = 1 + vals.filter((v) => v > n.participation_by_quarter[q]).length;
      return `<tr><td>${esc(periodLabel(q))}</td><td class="r">${n.participation_by_quarter[q].toFixed(2)}</td><td class="r">${rank}</td></tr>`;
    }).join("")}</tbody></table>`;

    const all = await loadPairs("all");
    const top3 = neighbours(all, i, "affinity").slice(0, 3);
    const months = DATA.meta.periods.filter((x) => x.kind === "month").map((x) => x.id);
    const mp = await Promise.all(months.map((m) => loadPairs(m)));
    const box = main.querySelector("#e-monthly");
    if (!top3.length) box.innerHTML = `<div class="empty">r/${esc(n.name)} has no surprising links over the whole window.</div>`;
    else lineChart(box, {
      labels: months, tickFormat: (m, long) => monthTick(m, long), format: (v) => fmtX(v), yMin: 0,
      series: top3.map((x, k) => {
        const s = mp.map((pp) => pairStats(pp, i, x.j));
        return { name: `r/${DATA.nodes[x.j].name}`, color: ["#3987e5", "#d95926", "#199e70"][k], values: s.map((t) => (t.expected > 0 ? t.affinity : null)), points: s.map((t) => t.validated) };
      }),
      ariaLabel: `Monthly affinity of r/${n.name} with its strongest neighbours`,
    });
  })();
  registerPage({ name: "explore", ready });
  return null;
}

function renderExploreIndex(main, missing) {
  const conn = story("connectors");
  const picks = ["personalfinance", "Bitcoin", "marvelstudios", "CanadaPolitics", "depression", "Python", "smoking", "AskReddit"].filter((x) => DATA.byName.has(x.toLowerCase()));
  main.innerHTML = `<div class="page">
    <div class="eyebrow">Subreddit explorer</div><h1 style="font-size:36px;margin-bottom:10px">Pick a community</h1>
    ${missing ? `<p class="muted">“${esc(missing)}” is not in the ${DATA.nodes.length}-subreddit frame.</p>` : ""}
    <p class="lede">Search any of the ${DATA.nodes.length} subreddits to see what it shares an unusually large audience with, how that compares with raw overlap, and how its activity and relationships moved month by month.</p>
    <div style="max-width:460px;margin:22px 0" id="x-search"></div>
    <div class="section"><h2>Good places to start</h2><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">${picks.map((p) => {
      const n = DATA.byName.get(p.toLowerCase());
      return `<a class="chip" style="font-size:14px;padding:6px 12px" href="#/explore/${encodeURIComponent(n.name)}"><span class="dot" style="background:${communityColor(n.community)}"></span>r/${esc(n.name)}</a>`;
    }).join("")}</div></div>
    ${conn ? `<div class="section"><h2>Top connectors</h2><div class="pill-list" style="max-width:520px;margin-top:10px">${conn.metrics.connectors.map((c) => `<a href="#/explore/${encodeURIComponent(c.name)}"><span>r/${esc(c.name)}</span><span>${c.participation_min.toFixed(2)}</span></a>`).join("")}</div></div>` : ""}
  </div>`;
  searchBox(main.querySelector("#x-search"), { onPick: (n) => { location.hash = `#/explore/${encodeURIComponent(n.name)}`; } });
  registerPage({ name: "explore", ready: Promise.resolve() });
  return null;
}
