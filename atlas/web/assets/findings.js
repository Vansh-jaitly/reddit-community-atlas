// Findings: research stories built from comment text and reply structure (data/findings/*.json).
// Landing page, "Inside a community", "Infinity War", "Bitcoin". Everything shown is read from the built JSON.
import { PALETTE, fmtInt, fmtPct, esc, hashFor, replaceParams, registerPage, isMobile, setOn, SHOT } from "./core.js";
import { lineChart, barChart, monthTick } from "./charts.js";
import { FocusNet, GROUP_COLORS, clusterColor, toneColor } from "./findings_net.js";

const FD = { index: null, stories: {} };
const SLUG = { community: "community", "infinity-war": "infinity_war", bitcoin: "bitcoin" };
const BACK = { community: "community", infinity_war: "infinity-war", bitcoin: "bitcoin" };

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
const loadIndex = async () => (FD.index ||= await getJSON("data/findings/index.json"));
const loadStory = async (id) => (FD.stories[id] ||= await getJSON(`data/findings/${id}.json`));

const sign = (v, d = 3) => (v == null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);
const fmtShare = (v) => (v != null && v >= 0.995 && v < 1 ? `${(100 * v).toFixed(1)}%` : fmtPct(v));   // 0.999 is not 100%
const fmtCompact = (v) => (v == null ? "–" : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}k` : v.toFixed(2));
const dayTick = (d, long) => { const [y, m, dd] = d.split("-"); const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m - 1]; return long ? `${+dd} ${mon} ${y}` : `${+dd} ${mon}`; };
const roll = (vals, k = 7) => vals.map((_, i) => { const w = vals.slice(Math.max(0, i - k + 1), i + 1).filter((v) => v != null && isFinite(v)); return w.length ? w.reduce((a, b) => a + b, 0) / w.length : null; });
const confChip = (c) => `<span class="fn-chip ${c}">${{ high: "high confidence", medium: "medium confidence", descriptive: "descriptive" }[c] || c}</span>`;
const sub = (s) => `r/${esc(s)}`;

// ---- shared blocks -------------------------------------------------------------------------------
function narrativeHTML(n, id) {
  const sec = (k, title, body) => `<section class="fn-sec" id="${id}-${k}"><h3><span class="fn-num">${k}</span>${title}</h3>${body}</section>`;
  return `<div class="fn-narrative">
    ${sec(1, "The question", `<p>${esc(n.question)}</p>`)}
    ${sec(2, "The context", `<p>${esc(n.context)}</p>`)}
    ${sec(3, "The observation", `<p>${esc(n.observation)}</p>`)}
    ${sec(4, "The visualization", `<p>${{ c: "The drawing on the left is the readable core of the year-long reply network (one partition for colours, tables and insights); below it the cluster table, the Brokers table, the camp panels and the quarter table carry the structure and tone evidence.",
      iw: "The indexed volume chart shows the surge and the bar chart which communities added the most comments in absolute terms (Atlas store); the rolling tone chart and the window comparisons carry the sentiment tests; the per-window networks with their cluster and broker tables show the structure.",
      bc: "The price chart defines the phases; the daily comment chart, the newcomer chart and the lag table carry presence and tone; the monthly structure chart and the key-month networks show how the reply graphs changed." }[id] || "The charts and the network beside this text are the evidence."} Every number is read from the built data files, and each insight card links to the view that shows it.</p>`)}
    ${sec(5, "The explanation", `<p>${esc(n.explanation)}</p>`)}
    ${sec(6, "The conclusion", `<p><b>${esc(n.conclusion)}</b></p>`)}
    ${sec(7, "The limitations", `<ul>${n.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`)}
  </div>`;
}

function insightCards(list, { compact = false } = {}) {
  if (!list.length) return `<div class="empty">No pattern passed the thresholds here.</div>`;
  return `<div class="fn-insights">${list.map((i) => `<a class="fn-insight" href="${esc(i.link)}">
      <div class="fn-insight-head">${confChip(i.confidence)}<span class="fn-kind">${esc(i.kind.replace(/_/g, " "))}${i.period ? ` · ${esc(i.period)}` : ""}${i.q_value != null ? ` · q = ${i.q_value} (${i.n_candidates_tested} test${i.n_candidates_tested === 1 ? "" : "s"})` : ""}</span></div>
      <h4>${esc(i.title)}</h4>
      <p class="fn-observed">${esc(i.observed)}</p>
      ${compact ? "" : `<dl><dt>Period</dt><dd>${esc(i.period)}</dd><dt>Scope</dt><dd>${esc(i.scope)}</dd><dt>Why it matters</dt><dd>${esc(i.why_interesting)}</dd><dt>Interpretation</dt><dd>${esc(i.interpretation)}</dd><dt>Limits</dt><dd>${esc(i.limitations)}</dd></dl>`}
    </a>`).join("")}</div>`;
}

function table(headers, rows, cls = "data") {
  return `<table class="${cls}"><thead><tr>${headers.map((h) => `<th${h.r ? ' class="r"' : ""}>${esc(h.t ?? h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, k) => `<td${headers[k] && headers[k].r ? ' class="r"' : ""}>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function comparisonsTable(comparisons, subs, fmtKey) {
  const rows = subs.flatMap((s) => Object.entries(comparisons[s] || {}).map(([k, c]) => {
    const a = c.comment_level || {}, u = c.user_level || {}, n = c.neg_share || {}, sv = c.standard_vader || {};
    return [sub(s), esc(fmtKey(k)),
      n.diff == null ? "–" : `${fmtPct(n.share_a, 1)} → ${fmtPct(n.share_b, 1)}`, n.diff == null ? "–" : `${(100 * n.diff).toFixed(1).replace(/^(\d)/, "+$1")} pts (${(100 * n.ci95[0]).toFixed(1)} to ${(100 * n.ci95[1]).toFixed(1)})`, n.cohen_h ?? "–", n.p_perm ?? "–",
      a.diff == null ? "–" : `${sign(a.mean_a)} → ${sign(a.mean_b)}`, a.cohen_d ?? "–", a.p_perm ?? "–", u.diff == null ? "–" : `${u.cohen_d} / ${u.p_perm}`, sv.diff == null ? "–" : `${sv.cohen_d} / ${sv.p_perm}`,
      (c.neg_share_strict && c.neg_share_strict.diff != null) ? `${fmtPct(c.neg_share_strict.share_a, 1)} → ${fmtPct(c.neg_share_strict.share_b, 1)} (h ${c.neg_share_strict.cohen_h}, p ${c.neg_share_strict.p_perm})` : "–"];
  }));
  return table(["Community", "Windows", { t: "Negative share a → b", r: true }, { t: "Diff (95% CI)", r: true }, { t: "Cohen's h", r: true }, { t: "p (perm.)", r: true }, { t: "Mean tone a → b", r: true }, { t: "d", r: true }, { t: "p", r: true }, { t: "Per-user d / p", r: true }, { t: "Standard VADER d / p", r: true }, { t: "Strict ±0.3 negative share", r: true }], rows);
}

function netStage(id) {
  return `<div class="fn-stage" id="${id}">
    <div class="fn-overlay">
      <div class="fn-controls">
        <div class="seg" data-ctl="mode"><button data-v="community" class="on" aria-pressed="true">Clusters</button><button data-v="sentiment" aria-pressed="false">Tone</button><button data-v="group" aria-pressed="false">Camps</button></div>
        <button class="btn small" data-ctl="brokers" aria-pressed="false">Highlight brokers</button>
        <button class="btn small" data-ctl="reset">Reset view</button>
      </div>
      <div class="fn-clusters" data-ctl="clusters"></div>
    </div>
    <div class="fn-net"></div>
    <aside class="fn-drawer" hidden></aside>
    <div class="fn-foot"><div class="fn-legend"></div><div class="fn-netnote"></div></div>
  </div>`;
}

/** Wire a FocusNet into a stage; returns {show(net, meta), destroy}. */
function mountNet(stageEl, { hasGroups = false, hasTone = false } = {}) {
  const host = stageEl.querySelector(".fn-net"), drawer = stageEl.querySelector(".fn-drawer"), legend = stageEl.querySelector(".fn-legend");
  const clusters = stageEl.querySelector("[data-ctl=clusters]"), note = stageEl.querySelector(".fn-netnote");
  let current = null;
  const net = new FocusNet(host, { onSelect: (d) => drawerFor(d) });
  const modeBtns = stageEl.querySelectorAll("[data-ctl=mode] button");
  modeBtns.forEach((b) => b.addEventListener("click", () => { modeBtns.forEach((x) => setOn(x, x === b)); net.setMode(b.dataset.v); drawLegend(b.dataset.v); }));
  const brokersBtn = stageEl.querySelector("[data-ctl=brokers]");
  brokersBtn.addEventListener("click", () => { const on = brokersBtn.getAttribute("aria-pressed") !== "true"; brokersBtn.setAttribute("aria-pressed", String(on)); brokersBtn.classList.toggle("on", on); net.setBrokers(on); });
  stageEl.querySelector("[data-ctl=reset]").addEventListener("click", () => { net.setFocus(null); net.select(null); net.reset(); clusters.querySelectorAll("button").forEach((x) => setOn(x, false)); });
  if (!hasGroups) stageEl.querySelector("[data-ctl=mode] [data-v=group]").hidden = true;
  if (!hasTone) stageEl.querySelector("[data-ctl=mode] [data-v=sentiment]").hidden = true;

  function drawLegend(mode) {
    if (!current) return;
    if (mode === "sentiment") legend.innerHTML = `<span class="fn-lg"><i style="background:${toneColor(-0.6)}"></i>negative tone</span><span class="fn-lg"><i style="background:${toneColor(0)}"></i>neutral</span><span class="fn-lg"><i style="background:${toneColor(0.6)}"></i>positive tone</span><span class="fn-lgnote">mean VADER compound of the user's comments in this window</span>`;
    else if (mode === "group") legend.innerHTML = Object.entries(GROUP_COLORS).filter(([g]) => current.nodes.some((n) => n.group === g)).map(([g, c]) => `<span class="fn-lg"><i style="background:${c}"></i>${esc(g)}</span>`).join("") + `<span class="fn-lg"><i style="background:#56554f"></i>no recognised flair</span>`;
    else legend.innerHTML = `<span class="fn-lgnote">circle = a user (anonymous id) · size = number of users they exchanged replies with · line = replies between two users (thicker = more) · colour = one of the eight largest Leiden clusters on the full network (grey = smaller clusters) · position = layout, not a measurement</span>`;
  }
  function drawerFor(d) {
    if (!d) { drawer.hidden = true; return; }
    const ties = current.edges.filter((e) => e.s === d.id || e.t === d.id).map((e) => ({ other: e.s === d.id ? e.t : e.s, w: e.w })).sort((a, b) => b.w - a.w);
    const byId = Object.fromEntries(current.nodes.map((n) => [n.id, n]));
    drawer.hidden = false;
    drawer.innerHTML = `<button class="close" aria-label="Close">×</button><div class="eyebrow">User (anonymous)</div><h3>${esc(d.id)}</h3>
      <div class="kpis"><div class="stat"><b>${d.degree}</b><span>users exchanged replies with</span></div><div class="stat"><b>${d.strength}</b><span>replies in those ties</span></div>
        <div class="stat"><b>${d.betweenness.toFixed(3)}</b><span>betweenness (core)</span></div><div class="stat"><b>${d.participation.toFixed(2)}</b><span>participation · ${d.reached} clusters reached</span></div></div>
      <p class="muted">Cluster ${d.community + 1}${d.group ? ` · camp: ${esc(d.group)}` : ""}${d.sentiment != null ? ` · mean tone ${sign(d.sentiment, 2)}` : ""}${d.constraint != null ? ` · Burt constraint ${d.constraint.toFixed(2)}` : ""}</p>
      <div class="chart-title">Strongest reply ties</div><div class="pill-list">${ties.slice(0, 8).map((t) => `<button class="pill-btn" data-id="${esc(t.other)}"><span>${esc(t.other)} <small>cluster ${(byId[t.other]?.community ?? 0) + 1}</small></span><span>${t.w}</span></button>`).join("")}</div>`;
    drawer.querySelector(".close").addEventListener("click", () => net.select(null));
    drawer.querySelectorAll(".pill-btn").forEach((b) => b.addEventListener("click", () => net.select(b.dataset.id)));
  }
  function show(n, meta = {}) {
    current = n;
    const inCore = (meta.brokers || []).filter((id) => n.nodes.some((x) => x.id === id));
    net.show(n, inCore.length ? meta.brokers : null);   // the Brokers table's rows when any of them is drawn; otherwise the core's own top brokers
    const brokerNote = meta.brokers && meta.brokers.length && !inCore.length ? " None of the full network's five strongest brokers is in the drawn core, so the broker highlight shows the core's own top brokers." : "";
    const sizes = {};
    n.nodes.forEach((x) => { sizes[x.community] = (sizes[x.community] || 0) + 1; });
    clusters.innerHTML = Object.entries(sizes).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([c, k]) => `<button data-c="${c}" aria-pressed="false"><i style="background:${clusterColor(+c)}"></i>cluster ${+c + 1} <small>${k}</small></button>`).join("");
    clusters.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { const on = !b.classList.contains("on"); clusters.querySelectorAll("button").forEach((x) => setOn(x, false)); setOn(b, on); net.setFocus(on ? +b.dataset.c : null); }));
    drawLegend(stageEl.querySelector("[data-ctl=mode] .on").dataset.v);
    drawer.hidden = true;
    note.textContent = (meta.note || "") + brokerNote;
  }
  return { show, destroy: () => net.destroy(), net };
}

function coverText(net) {
  const c = net.core, s = net.summary;
  const extra = [s.seed_ami != null ? `seed agreement AMI ${s.seed_ami}` : null, s.infomap ? `Infomap finds ${s.infomap.modules} modules, AMI vs Leiden ${s.infomap.ami_vs_leiden}` : null,
    s.resolution_scan ? `resolution scan γ 0.5/1/1.5/2 → ${s.resolution_scan.map((r) => r.communities_ge5).join("/")} clusters ≥ 5` : null].filter(Boolean).join("; ");
  return `Readable core: ${c.nodes.length} of ${fmtInt(s.nodes)} repliers (${c.k > 0 ? `${c.k}-core, ` : ""}${fmtPct(c.edge_share)} of reply ties, ${fmtPct(c.weight_share)} of replies). Full network: ${fmtInt(s.edges)} ties, density ${s.density}, ${s.communities} clusters, modularity ${s.modularity} weighted / ${s.modularity_unweighted ?? "–"} unweighted (rewired baseline ${s.null_modularity?.mean?.toFixed(2) ?? "–"}${extra ? "; " + extra : ""}).`;
}

function communitiesTable(net, { tone = true } = {}) {
  const rows = (net.communities || []).slice(0, 10).map((c) => [
    `<span class="dot" style="display:inline-block;background:${clusterColor(c.id)}"></span> cluster ${c.id + 1}`, fmtInt(c.size), `${fmtInt(c.edges_inside)} / ${fmtInt(c.edges_outward)}`,
    c.ei_index == null ? "–" : sign(c.ei_index, 2), tone ? (c.mean_sentiment == null ? "–" : sign(c.mean_sentiment, 2)) : (c.group_mix ? Object.entries(c.group_mix).map(([g, v]) => `${esc(g)} ${fmtPct(v)}`).join(", ") : "–"),
    c.top_terms ? c.top_terms.map((t) => `<span class="fn-term">${esc(t)}</span>`).join(" ") : (c.group_mix && tone ? Object.entries(c.group_mix).map(([g, v]) => `${esc(g)} ${fmtPct(v)}`).join(", ") : "–"),
  ]);
  return table(["Cluster", { t: "Users", r: true }, { t: "Ties inside / out", r: true }, { t: "E–I", r: true }, { t: tone ? "Mean tone" : "Camps", r: true }, "Marks it out"], rows);
}

function bridgesTable(net) {
  if (!net.bridges || !net.bridges.length) return `<p class="muted">No user meets the broker rule here (participation ≥ 0.6, replies to or from ≥ 3 clusters).</p>`;
  return table(["User", { t: "Betweenness", r: true }, { t: "Per tie (EV)", r: true }, { t: "vs rewired", r: true }, { t: "Participation", r: true }, { t: "Clusters", r: true }, { t: "Ties", r: true }, "Tone", "Camp"],
    net.bridges.map((b) => [esc(b.id), b.betweenness.toFixed(4), fmtCompact(b.ev_brokerage), b.null ? (b.null.method === "rewiring" ? `z = ${b.null.z}, p = ${b.null.p}` : `${b.null.percentile}th pct. of ${b.null.n_matched} similar-degree nodes`) : "not tested", b.participation.toFixed(2), b.reached, b.degree, b.sentiment == null ? "–" : sign(b.sentiment, 2), b.group ? esc(b.group) : "–"])) +
    `<p class="muted">Betweenness uses reply counts as proximities (distance = 1 / replies); "per tie" is Everett–Valente brokerage (betweenness ÷ degree); "vs rewired" is the z-score and empirical p against degree-preserving rewirings of the full graph (graphs up to 3,000 users) or the node's percentile among users of similar degree (larger graphs), where tested. The table lists the five highest-betweenness users that meet the broker rule (participation ≥ 0.6, replies to or from ≥ 3 clusters); an insight card's "next highest" is taken over all users, so it can name a user the rule excludes.</p>`;
}

// ---- router entry ---------------------------------------------------------------------------------
export function renderFindings(main, { args, params }) {
  const page = args[0] || "home";
  let cleanup = null, gone = false;   // a render abandoned by the router must not touch the DOM or the URL
  const ready = (async () => {
    main.innerHTML = `<div class="loading">Loading the findings…</div>`;
    try { await loadIndex(); } catch (e) {
      if (!gone) main.innerHTML = `<div class="page"><div class="eyebrow">Findings</div><h1>Not built yet</h1><p class="lede">The Findings data files are missing. Run <code>python -m findings.build_findings</code> (after <code>data_curation/fetch_text.py</code>) and reload.</p></div>`;
      return;
    }
    if (gone) return;
    if (page === "home") { cleanup = renderHome(main); return; }
    const id = SLUG[page];
    if (!id) { main.innerHTML = `<div class="page"><div class="empty">No such finding. <a href="#/findings">Back to Findings</a></div></div>`; return; }
    let story;
    try { story = await loadStory(id); } catch (e) { if (!gone) main.innerHTML = `<div class="page"><div class="empty">This story has not been built yet (${esc(id)}.json missing).</div></div>`; return; }
    if (gone) return;
    cleanup = ({ community: renderCommunity, infinity_war: renderInfinityWar, bitcoin: renderBitcoin })[id](main, story, params);
  })();
  registerPage({ name: "findings", ready });
  return () => { gone = true; if (cleanup) cleanup(); };
}

// ---- landing ---------------------------------------------------------------------------------------
function renderHome(main) {
  let preview = null, gone = false;
  const ix = FD.index;
  const top = ix.insights.slice(0, 1)[0];
  const cards = [
    { id: "community", n: 1, t: "Inside a Reddit community", q: "Who replies to whom inside one community, which camps form, and who connects them?" },
    { id: "infinity_war", n: 2, t: "Infinity War: the Reddit reaction", q: "Did volume, tone and the shape of conversation change around the film's release?" },
    { id: "bitcoin", n: 3, t: "Bitcoin: when market optimism changed", q: "How did crypto communities change through the 2018 decline, in presence, tone and structure?" },
  ];
  const built = new Set(ix.stories.map((s) => s.id));
  main.innerHTML = `<div class="page findings">
    <div class="fn-hero">
      <div class="eyebrow">Findings · research stories from the data</div>
      <h1>What the comments say, and who says it to whom</h1>
      <p class="lede">The Atlas maps which communities share an audience. These three stories go one level down: real reply threads, the words people used, and how both moved around two dated events. Every number is computed by the <code>findings</code> pipeline from the comment store; nothing here is typed in.</p>
      <div class="fn-hero-actions"><a class="btn primary" href="#/findings/community">Start with the community</a><a class="btn" href="#/findings/infinity-war">Infinity War</a><a class="btn" href="#/findings/bitcoin">Bitcoin</a></div>
    </div>
    ${top ? `<section class="section"><div class="eyebrow">The most important finding</div><a class="fn-top" href="${esc(top.link)}"><div>${confChip(top.confidence)}<h2>${esc(top.title)}</h2><p>${esc(top.observed)}</p><p class="muted">${esc(top.interpretation)}</p></div><span class="go">Open the evidence →</span></a></section>` : ""}
    <section class="section"><h2>Three stories</h2><div class="cards">${cards.map((c) => `<a class="card ${built.has(c.id) ? "" : "disabled"}" href="#/findings/${BACK[c.id]}"><span class="n">Story ${c.n}</span><h3>${esc(c.t)}</h3><p>${esc(c.q)}</p><span class="go">${built.has(c.id) ? "Read it →" : "Not built yet"}</span></a>`).join("")}</div></section>
    <section class="section fn-previews"><div><div class="chart-title">Preview: the focused reply network</div><div class="fn-preview-net" id="fn-prev-net"></div></div><div><div class="chart-title">Preview: tone around the Infinity War release</div><div id="fn-prev-chart"></div></div></section>
    <section class="section"><h2>All insights that passed the thresholds</h2><p class="muted">Ranked by confidence. Each card opens the view with the data behind it.</p>${insightCards(ix.insights, { compact: true })}</section>
    ${ix.validation ? `<section class="section"><h2>How well does the sentiment tool agree with labelled comments?</h2><div class="panel"><p>On a stratified sample of <b>${fmtInt(ix.validation.n)}</b> comments (three subreddit groups — Marvel, crypto, debate — × three months × VADER's three labels), VADER's ±0.05 label matched the annotators' label for <b>${fmtPct(ix.validation.accuracy)}</b> (macro-F1 ${ix.validation.macro_f1}, Cohen's κ ${ix.validation.kappa}${ix.validation.binary_pos_neg_accuracy != null ? `; positive vs negative alone ${fmtPct(ix.validation.binary_pos_neg_accuracy)} on ${fmtInt(ix.validation.binary_n)}` : ""}${ix.validation.accuracy_strict != null ? `; at the stricter ±${ix.validation.strict_threshold} threshold ${fmtPct(ix.validation.accuracy_strict)}, κ ${ix.validation.kappa_strict}` : ""}). The annotators called ${fmtPct((ix.validation.annotator_label_shares || {}).neu || 0)} of this VADER-balanced sample neutral: VADER's main error is calling neutral comments polar, which inflates absolute shares but moves little between windows, so the stories lean on <em>changes</em> in shares, require the mean tone to agree in direction, and show the strict threshold beside the default.${ix.validation.accuracy_marvel != null ? ` By community group: Marvel ${fmtPct(ix.validation.accuracy_marvel)}, crypto ${fmtPct(ix.validation.accuracy_crypto)}, debate ${fmtPct(ix.validation.accuracy_debate)}.` : ""}</p><p class="muted">${esc(ix.validation.annotators || "")}</p></div></section>` : ""}
    <section class="section"><h2>How to read these pages</h2><div class="grid2"><div class="panel"><h4>Networks</h4><p>A circle is a user (anonymous id); a line means one replied to the other's comment. Size = users they exchanged replies with; colour = one of the eight largest clusters found by Leiden (grey = smaller ones); position comes from a layout and is not a measurement. Brokers are users whose replies span several clusters.</p></div><div class="panel"><h4>Sentiment</h4><p>VADER scores the polarity of a comment's language (−1 to +1). Positive language is not agreement and negative language is not disagreement; we report shares and means with effect sizes, and we keep tone separate from who talks to whom.</p></div></div></section>
  </div>`;
  // previews (best effort)
  (async () => {
    try {
      if (built.has("community")) {
        const st = await loadStory("community");
        if (st.year?.core && !gone) { const m = mountNet(main.querySelector("#fn-prev-net").parentElement.appendChild(Object.assign(document.createElement("div"), { innerHTML: netStage("fn-prev-stage") })).firstElementChild, { hasTone: !!st.year.core.nodes.some((n) => n.sentiment != null) }); preview = m; m.show(st.year.core, { brokers: (st.year.bridges || []).map((b) => b.id),  note: `r/${st.subreddit}, Oct 2017 – Sep 2018` }); main.querySelector("#fn-prev-net").remove(); }
      }
      if (built.has("infinity_war")) {
        const st = await loadStory("infinity_war");
        const lead = st.subreddits[0];
        const d = st.daily.filter((x) => x.subreddit === lead);
        lineChart(main.querySelector("#fn-prev-chart"), { labels: d.map((x) => x.day), tickFormat: dayTick, height: 220, yMin: -0.2, format: (v) => sign(v, 2), directLabels: false,
          series: [{ name: "mean tone, 7-day mean", color: "#3987e5", values: roll(d.map((x) => x.mean_compound)) }, { name: "negative share, 7-day mean", color: "#d95926", dashed: true, values: roll(d.map((x) => x.neg_share)) }],
          events: [{ x: st.anchor.date, label: st.anchor.label, short: "release" }], ariaLabel: "Mean tone around the release" });
      }
    } catch (e) { console.warn("preview", e); }
  })();
  return () => { gone = true; if (preview) preview.destroy(); };
}

// ---- story 1: community ---------------------------------------------------------------------------
function renderCommunity(main, st, params) {
  const y = st.year, sm = y.summary || {};
  const hasGroups = !!(y.groups && y.groups.groups && y.groups.groups.length), hasTone = !!(y.core && y.core.nodes.some((n) => n.sentiment != null));
  const matrix = st.matrix;
  const cols = ["network_quality", "community_structure", "interesting_patterns", "data_completeness", "storytelling", "total"];
  main.innerHTML = `<div class="findings fn-story">
    <header class="fn-head page"><div class="eyebrow">Findings · Story 1 of 3</div><h1>Inside r/${esc(st.subreddit)}</h1><p class="lede">${esc(st.narrative.question)}</p>
      <div class="kpis"><div class="stat"><b>${fmtInt(sm.nodes)}</b><span>users who exchanged replies</span></div><div class="stat"><b>${fmtInt(sm.edges)}</b><span>reply ties (carrying ${fmtInt(sm.tie_replies ?? y.reply_edges)} replies)</span></div><div class="stat"><b>${sm.modularity_unweighted}</b><span>unweighted modularity · rewired ${sm.null_modularity?.mean?.toFixed(2)}</span></div><div class="stat"><b>${fmtShare(sm.largest_component_share)}</b><span>in the largest component</span></div>${hasGroups ? `<div class="stat"><b>${fmtPct(y.groups.between_share)}</b><span>of camp-flaired replies cross camp lines</span></div>` : ""}</div></header>
    <div class="fn-split"><div class="fn-left">${netStage("fn-c-stage")}
        <div class="page fn-evidence"><h2>The evidence</h2>
          <h3>Clusters on the full network</h3>${communitiesTable(y, { tone: hasTone })}
          <h3>Brokers</h3>${bridgesTable(y)}
          ${hasGroups ? `<h3 id="groups">Self-declared camps</h3>${campsHTML(y.groups)}` : ""}
          <h3 id="quarters">Quarter by quarter</h3>${table(["Quarter", { t: "Users", r: true }, { t: "Ties", r: true }, { t: "Largest comp.", r: true }, { t: "Modularity", r: true }, { t: "Reciprocity", r: true }, { t: "E–I (camps)", r: true }],
            st.quarters.filter((q) => q.summary).map((q) => [esc(q.label), fmtInt(q.summary.nodes), fmtInt(q.summary.edges), fmtShare(q.summary.largest_component_share), q.summary.modularity, fmtPct(q.summary.reciprocity), q.groups?.ei_index == null ? "–" : sign(q.groups.ei_index, 2)]))}
          ${st.persistence.length ? `<p class="muted">Cluster membership of users present in consecutive quarters (adjusted Rand index): ${st.persistence.map((p) => `${p.from}→${p.to} ${p.ari} (n=${p.users_in_both})`).join(" · ")}.</p>` : ""}
          <details class="fn-matrix"><summary>How r/${esc(st.subreddit)} was chosen: the selection matrix (${matrix.length} candidates, ${st.selection_window.start} – ${st.selection_window.end})</summary>
            <p class="muted">Each column is a 0–1 score from the metrics in this table and the research note; the rule set is in <code>findings/candidates.py</code> and the research note. Runner-up: r/${esc(st.alternative)}.</p>
            ${table(["Candidate", { t: "Users", r: true }, { t: "Ties", r: true }, { t: "Unw. mod. excess", r: true }, { t: "Brokers", r: true }, { t: "Flair cov.", r: true }, ...cols.map((c) => ({ t: c.replace(/_/g, " "), r: true }))],
              matrix.map((r) => [`${r.subreddit === st.subreddit ? "<b>" : ""}r/${esc(r.subreddit)}${r.has_text ? ' <span class="hub">text</span>' : ""}${r.subreddit === st.subreddit ? "</b>" : ""}`, fmtInt(r.nodes), fmtInt(r.edges), r.modularity_excess ?? "–", r.bridge_users ?? "–", r.flair_group_coverage == null ? "–" : fmtPct(r.flair_group_coverage), ...cols.map((c) => r[c] == null ? "–" : r[c])]))}
          </details>
        </div></div>
      <aside class="fn-right page">${narrativeHTML(st.narrative, "c")}<h2>Insights</h2>${insightCards(st.insights)}</aside></div></div>`;
  const stage = main.querySelector("#fn-c-stage");
  const m = mountNet(stage, { hasGroups, hasTone });
  if (y.core) m.show(y.core, { brokers: (y.bridges || []).map((b) => b.id), note: coverText(y) }); else stage.querySelector(".fn-net").innerHTML = `<div class="empty">Too few reply ties to draw.</div>`;
  if (!SHOT && (params.view === "groups" || params.view === "quarters")) { const el = main.querySelector(`#${params.view}`); if (el) setTimeout(() => el.scrollIntoView({ block: "start" }), 50); }
  return () => m.destroy();
}

function campsHTML(g) {
  const groups = g.groups;
  const mat = g.matrix || {}, tone = g.tone_matrix || {};
  const rows = groups.map((a) => [esc(a), ...groups.map((b) => `${fmtInt(mat[a]?.[b] ?? 0)}${tone[a]?.[b] != null ? `<br><small class="muted">tone ${sign(tone[a][b], 2)}</small>` : ""}`)]);
  return `<p>${fmtPct(g.coverage)} of repliers carry a recognised camp flair; E–I index ${sign(g.ei_index, 2)} (−1 = all replies inside a camp, +1 = all across)${g.ei_null ? `; degree-preserving rewirings give ${sign(g.ei_null.null_mean, 2)} ± ${g.ei_null.null_sd} (z = ${g.ei_null.z}, p = ${g.ei_null.p_two_sided})` : ""}. ${g.between ? `Replies across camp lines average <b>${sign(g.between.mean_compound, 3)}</b> on the compound scale (n = ${fmtInt(g.between.n)}) against <b>${sign(g.within.mean_compound, 3)}</b> within a camp (n = ${fmtInt(g.within.n)}); permutation p = ${g.p_perm}.` : ""}</p>
    ${table(["replier ↓ · replied to →", ...groups.map((x) => ({ t: x, r: true }))], rows)}
    <p class="muted">Counts are replies from the row camp to the column camp; tone is the mean compound of those replying comments. Camps come from flair keywords (see the story's limitations).</p>`;
}

// ---- story 2: Infinity War ------------------------------------------------------------------------
function renderInfinityWar(main, st, params) {
  const subs = st.subreddits, lead = subs[0];
  const W = st.windows, wnames = Object.keys(W);
  let win = wnames.includes(params.window) ? params.window : "release";
  let cur = subs.includes(params.sub) ? params.sub : lead;
  const days = [...new Set(st.daily.map((d) => d.day))].sort();
  const bySub = Object.fromEntries(subs.map((s) => [s, Object.fromEntries(st.daily.filter((d) => d.subreddit === s).map((d) => [d.day, d]))]));
  const ctxBy = {};
  (st.context_daily || []).forEach((d) => { (ctxBy[d.subreddit] ||= {})[d.day] = d; });
  const median = (arr) => { const s = arr.filter((v) => v != null).sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 1; };
  const indexed = (map) => { const vals = days.map((d) => map[d]?.comments ?? null); const base = median(days.filter((d) => d >= W.before.start && d <= W.before.end).map((d) => map[d]?.comments ?? null)); return vals.map((v) => (v == null ? null : (100 * v) / base)); };
  const events = [{ x: st.anchor.date, label: st.anchor.label, short: "US release" }, { x: W.release.start, label: "release window starts", short: "release window" }, { x: W.after.start, label: "after window starts", short: "after window" }];
  const wsum = st.window_summary;
  const ws = (w, s) => wsum.find((r) => r.window === w && r.subreddit === s) || {};
  const leadFrame = (st.frame_participation || []).find((r) => r.subreddit === lead), relRow = ws("release", lead);
  const frameCover = leadFrame && relRow && relRow.comments_per_day ? `; its r/${esc(lead)} count in the release window is ${Math.round(100 * leadFrame.release_per_day / relRow.comments_per_day)}% of the text-store count in the KPIs` : "";
  main.innerHTML = `<div class="findings fn-story">
    <header class="fn-head page"><div class="eyebrow">Findings · Story 2 of 3 · event story</div><h1>${esc(st.title)}</h1><p class="lede">${esc(st.narrative.question)}</p>
      <div class="kpis">${wnames.map((w) => { const r = ws(w, lead); return `<div class="stat"><b>${fmtInt(r.comments_per_day)}</b><span>r/${esc(lead)} comments/day · ${w} (${dayTick(W[w].start)} – ${dayTick(W[w].end)})</span></div>`; }).join("")}
        <div class="stat"><b>${fmtPct(ws("release", lead).newcomer_share)}</b><span>of release-window commenters were new to r/${esc(lead)} (not active there in the previous five months)</span></div></div></header>
    <div class="page fn-timeline">
      <h2>1 · Volume: the crowd arrives</h2><div class="chart-sub">Daily comments indexed to each community's median in the "before" window (= 100). Context communities (structure only, no text) dashed.</div><div id="iw-vol"></div>
      <div class="fn-stack" style="margin-top:18px"><div><div class="chart-title">Largest absolute increases across the 170 communities (Atlas store)</div><div class="chart-sub">Extra comments per day in the release window compared with the seven weeks before, counted in the Atlas store (accounts with at least five comments in the quarter${frameCover}). Large communities lead by size; the segmented-regression percentile below is the size-free comparison.</div><div id="iw-frame"></div></div>
        <div><div class="chart-title">Window summary</div>${table(["Window", "Community", { t: "Comments/day", r: true }, { t: "Commenters", r: true }, { t: "New (5-mo. lookback)", r: true }, { t: "Pos / neu / neg", r: true }, { t: "Neg 95% CI", r: true }, { t: "Mean tone", r: true }, { t: "Standard VADER", r: true }],
          wsum.map((r) => [esc(r.window), sub(r.subreddit), fmtInt(r.comments_per_day), fmtInt(r.commenters), fmtPct(r.newcomer_share), `${fmtPct(r.pos_share)} / ${fmtPct(r.neu_share)} / ${fmtPct(r.neg_share)}`, r.neg_share_ci95 ? `${fmtPct(r.neg_share_ci95[0], 1)}–${fmtPct(r.neg_share_ci95[1], 1)}` : "–", sign(r.mean_compound), sign(r.mean_compound_std)]))}
          <p class="muted">"New" = not active in that community during the five months before the window, a fixed lookback so the windows compare like with like. Tone = VADER with topic words neutralised (${esc((st.sentiment_measure?.neutralised_words || []).slice(0, 8).join(", "))}…); "standard VADER" is the unmodified lexicon, shown as a sensitivity check.</p>
          ${st.its ? `<div class="chart-title" style="margin-top:12px">Level change at the release (segmented regression)</div>${table(["Community", { t: "Level change", r: true }, { t: "t (Newey–West)", r: true }, { t: "t (OLS)", r: true }, { t: "Resid. autocorr. (lag 1)", r: true }, { t: "Slope change/day", r: true }, { t: "Percentile among 170", r: true }, { t: "Frame median", r: true }],
            Object.entries(st.its).filter(([, v]) => v && v.level_change_pct != null).map(([s, v]) => [sub(s), `${(100 * v.level_change_pct).toFixed(0)}%`, v.t_hac ?? "–", v.t, v.residual_lag1_autocorr ?? "–", v.slope_change_log_per_day, v.percentile_among_frame, `${(100 * v.frame_median_pct).toFixed(0)}%`]))}
          <p class="muted">log(1 + daily comments) on time, a level shift at ${dayTick(st.anchor.date, true)}, a slope change and day-of-week terms (Bernal et al. 2017); the t statistic uses Newey–West standard errors because the daily residuals are autocorrelated (the OLS t and the residual lag-1 autocorrelation are shown for comparison); the same model on all 170 communities gives the percentile, which does not depend on the standard error.${st.gap_days && st.gap_days.length ? ` Archive-gap screen: ${st.gap_days.length} day(s) with frame-wide totals below half the median (${st.gap_days.slice(0, 4).map((d) => dayTick(d)).join(", ")}).` : " Archive-gap screen: no day in the window falls below half the frame-wide median."}</p>` : ""}</div></div>
      <h2>2 · Tone: what changed, and how much</h2><div class="chart-sub">Seven-day rolling mean of VADER compound (solid) and of the negative share (dashed), per community.</div><div id="iw-tone"></div>
      <div class="chart-title" style="margin-top:14px">Window comparisons</div>${comparisonsTable(st.comparisons, subs, (k) => k.replace(/_/g, " "))}
      ${st.change_points ? `<p class="muted">Change points (binary segmentation, BIC penalty) in r/${esc(lead)}: daily volume ${st.change_points.comments.map((d) => dayTick(d)).join(", ") || "none"}; daily mean tone ${st.change_points.mean_compound.map((d) => dayTick(d)).join(", ") || "none"}.</p>` : ""}
      <h2>3 · Structure: who talked to whom</h2>
      <div class="fn-selectors"><div class="seg" id="iw-win">${wnames.map((w) => `<button data-v="${w}">${w}</button>`).join("")}</div><div class="seg" id="iw-sub">${subs.map((s) => `<button data-v="${s}">r/${esc(s)}</button>`).join("")}</div></div>
    </div>
    <div class="fn-split"><div class="fn-left">${netStage("fn-iw-stage")}
        <div class="page fn-evidence" id="iw-netdoc"></div></div>
      <aside class="fn-right page">${narrativeHTML(st.narrative, "iw")}<h2>Insights</h2>${insightCards(st.insights)}</aside></div></div>`;
  // charts
  const volSeries = subs.map((s, k) => ({ name: `r/${s}`, color: PALETTE[k], values: indexed(bySub[s]) }));
  Object.entries(ctxBy).forEach(([s, map], k) => volSeries.push({ name: `r/${s}`, color: PALETTE[(k + 3) % PALETTE.length], dashed: true, values: indexed(map) }));
  lineChart(main.querySelector("#iw-vol"), { labels: days, tickFormat: dayTick, format: (v) => v.toFixed(0), height: 300, yMin: 0, series: volSeries, events, ariaLabel: "Daily comments indexed to the before-window median" });
  barChart(main.querySelector("#iw-frame"), { rows: st.frame_participation.slice(0, 12).map((r) => ({ label: `r/${r.subreddit}`, value: r.release_extra_per_day, note: r.release_ratio ? `${r.release_ratio}×` : "", color: subs.includes(r.subreddit) ? PALETTE[0] : "#8e8d86" })), format: (v) => `+${fmtInt(v)}/day`, ariaLabel: "Extra comments per day in the release window" });
  lineChart(main.querySelector("#iw-tone"), { labels: days, tickFormat: dayTick, format: (v) => sign(v, 2), height: 280, yMin: "auto", directLabels: false, series: subs.flatMap((s, k) => [{ name: `r/${s} mean tone`, color: PALETTE[k], values: roll(days.map((d) => bySub[s][d]?.mean_compound ?? null)) }, { name: `r/${s} negative share`, color: PALETTE[k], dashed: true, values: roll(days.map((d) => bySub[s][d]?.neg_share ?? null)) }]), events, ariaLabel: "Rolling mean tone and negative share" });
  // network per window
  const stage = main.querySelector("#fn-iw-stage");
  const m = mountNet(stage, { hasTone: true });
  const doc = main.querySelector("#iw-netdoc");
  function showNet() {
    const net = st.networks[cur][win];
    replaceParams("findings", ["infinity-war"], { window: win, sub: cur });
    main.querySelectorAll("#iw-win button").forEach((b) => setOn(b, b.dataset.v === win));
    main.querySelectorAll("#iw-sub button").forEach((b) => setOn(b, b.dataset.v === cur));
    if (net.core) m.show(net.core, { brokers: (net.bridges || []).map((b) => b.id), note: `${sub(cur)} · ${win} window (${dayTick(W[win].start)} – ${dayTick(W[win].end)}) · ${coverText(net)}` });
    else stage.querySelector(".fn-net").innerHTML = `<div class="empty">${esc(net.note || "No network for this window.")}</div>`;
    const themes = st.themes[cur] || {};
    doc.innerHTML = `<h2>The ${win} window in ${sub(cur)}</h2>
      ${net.summary ? `<div class="kpis"><div class="stat"><b>${fmtInt(net.summary.nodes)}</b><span>users exchanging replies</span></div><div class="stat"><b>${fmtInt(net.summary.edges)}</b><span>reply ties</span></div><div class="stat"><b>${net.summary.modularity_unweighted}</b><span>unweighted modularity (rewired ${net.summary.null_modularity?.mean?.toFixed(2)})</span></div><div class="stat"><b>${fmtShare(net.summary.largest_component_share)}</b><span>largest component</span></div><div class="stat"><b>${fmtPct(net.summary.reciprocity)}</b><span>reciprocated pairs</span></div></div>` : ""}
      <h3>Clusters and their tone</h3>${communitiesTable(net, { tone: true })}
      <h3>Brokers</h3>${bridgesTable(net)}
      <h3>Words that mark each window</h3><div class="grid3">${wnames.map((w) => `<div class="panel"><h4>${esc(w)}</h4><p>${(themes[w] || []).map((t) => `<span class="fn-term" title="z = ${t.z}">${esc(t.term)}</span>`).join(" ") || "–"}</p></div>`).join("")}</div>
      <p class="muted">Log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi & Quinn 2008) on document frequency, each window against the other two.</p>
      ${st.context_subreddits.map((c) => { const n = st.networks[c]?.[win]; return n && n.summary ? `<p class="muted">${sub(c)} (structure only) in this window: ${fmtInt(n.summary.nodes)} repliers, ${fmtInt(n.summary.edges)} ties, modularity ${n.summary.modularity}, largest component ${fmtShare(n.summary.largest_component_share)}.</p>` : ""; }).join("")}`;
  }
  main.querySelectorAll("#iw-win button").forEach((b) => b.addEventListener("click", () => { win = b.dataset.v; showNet(); }));
  main.querySelectorAll("#iw-sub button").forEach((b) => b.addEventListener("click", () => { cur = b.dataset.v; showNet(); }));
  showNet();
  if (!SHOT && (params.window || params.sub)) setTimeout(() => stage.scrollIntoView({ block: "start" }), 60);
  return () => m.destroy();
}

// ---- story 3: Bitcoin ------------------------------------------------------------------------------
function renderBitcoin(main, st, params) {
  const subs = st.subreddits, lead = subs[0];
  const netSubs = Object.keys(st.networks);
  const days = st.price.map((p) => p.day);
  const bySub = {};
  st.daily.forEach((d) => { (bySub[d.subreddit] ||= {})[d.day] = d; });
  const months = [...new Set(st.monthly.map((m) => m.month))].sort();
  const keyMonths = netSubs.length ? Object.entries(st.networks[netSubs[0]]).filter(([, v]) => v.core).map(([m]) => m) : [];
  let cur = netSubs.includes(params.sub) ? params.sub : netSubs[0];
  let month = keyMonths.includes(params.month) ? params.month : (keyMonths.includes(st.anchor.date.slice(0, 7)) ? st.anchor.date.slice(0, 7) : keyMonths[0]);
  const ext = st.price_extrema.filter((e) => e.type === "peak" || e.type === "trough").map((e) => ({ x: e.day, label: `${e.type} $${fmtInt(e.price)} on ${dayTick(e.day, true)}${e.unconfirmed ? " (provisional)" : ""}`, short: `${e.type === "peak" ? "▲" : "▼"} $${fmtInt(e.price)}${e.unconfirmed ? " (prov.)" : ""}` }));
  const phaseRows = st.phase_summary;
  const ps = (k, s) => phaseRows.find((r) => r.phase === k && r.subreddit === s) || {};
  const mr = (m, s) => st.monthly.find((r) => r.month === m && r.subreddit === s) || {};
  main.innerHTML = `<div class="findings fn-story">
    <header class="fn-head page"><div class="eyebrow">Findings · Story 3 of 3 · event story</div><h1>${esc(st.title)}</h1><p class="lede">${esc(st.narrative.question)}</p>
      <div class="kpis"><div class="stat"><b>$${fmtInt(st.price_extrema.find((e) => e.type === "peak")?.price)}</b><span>peak price, ${dayTick(st.anchor.date, true)}</span></div>
        ${subs.slice(0, 2).map((s) => { const a = mr(st.anchor.date.slice(0, 7), s), z = mr(months.at(-1), s); return `<div class="stat"><b>${fmtInt(a.commenters)} → ${fmtInt(z.commenters)}</b><span>r/${esc(s)} commenters, peak month → ${monthTick(months.at(-1), true)}</span></div>`; }).join("")}
        <div class="stat"><b>${fmtPct(mr(st.anchor.date.slice(0, 7), lead).newcomer_share)} → ${fmtPct(mr(months.at(-1), lead).newcomer_share)}</b><span>newcomer share in r/${esc(lead)}, peak month → ${monthTick(months.at(-1), true)} (not active there in the previous two months)</span></div></div></header>
    <div class="page fn-timeline">
      <h2>1 · Price and presence</h2><div class="chart-sub">Bitcoin price (USD, Blockchain.com daily market price) with the peaks and troughs that define the phases; below it, daily comments per community.</div><div id="bc-price"></div><div id="bc-vol" style="margin-top:10px"></div>
      <div class="chart-title" style="margin-top:16px">Phases from the price series (zigzag, ≥40% swings)</div>${table(["Phase", "Dates", { t: "Price change", r: true }, ...subs.map((s) => ({ t: `r/${s} mean tone · neg share`, r: true }))],
        st.phases.map((p) => { const k = `P${st.phases.indexOf(p) + 1} ${p.label}`; return [esc(p.label), `${dayTick(p.start)} – ${dayTick(p.end, true)}`, `${(100 * p.change).toFixed(0)}%`, ...subs.map((s) => { const r = ps(k, s); return r.mean_compound == null ? "–" : `${sign(r.mean_compound)} · ${fmtPct(r.neg_share)} <small class="muted">(n=${fmtInt(r.scored)})</small>`; })]; }))}
      ${st.price_extrema.some((e) => e.unconfirmed) ? `<div class="chart-sub">The last turning point (${dayTick(st.price_extrema.find((e) => e.unconfirmed).day, true)}) is provisional: the window ends before the following move reaches the 40% threshold, so the final phase is open-ended.</div>` : ""}
      <h2>2 · Tone through the decline</h2><div class="chart-sub">Seven-day rolling mean of VADER compound per community; phase boundaries marked.</div><div id="bc-tone"></div>
      <div class="grid2" style="margin-top:14px"><div><div class="chart-title">Newcomers (not active there in the previous two months) and negativity by month, r/${esc(lead)} and r/${esc(subs[1])}</div><div id="bc-month"></div></div>
        <div><div class="chart-title">Daily price return vs daily tone (Spearman, by lag)</div><div class="chart-sub">Positive lag: price leads tone. Both series are daily and aligned by UTC day, so a lag of ±1 day is within the alignment uncertainty. Associations only.</div><div id="bc-corr"></div></div></div>
      <div class="chart-title" style="margin-top:14px" id="bc-cmp-title">Consecutive phases compared</div><div class="seg" id="bc-cmp-sub">${subs.map((s) => `<button data-v="${s}">r/${esc(s)}</button>`).join("")}</div><div id="bc-cmp"></div>
      <p class="muted">Tone = VADER with topic words neutralised (${esc((st.sentiment_measure?.neutralised_words || []).slice(0, 8).join(", "))}…); the "standard VADER" column repeats the mean-tone test with the unmodified lexicon.</p>
      <h2>3 · Structure month by month</h2><div class="chart-sub">Reply networks of r/${esc(netSubs[0])} and r/${esc(netSubs[1] || netSubs[0])}: modularity (solid) and largest-component share (dashed) per month; pick a key month to open its readable core.</div><div id="bc-struct"></div>
      <div class="fn-selectors"><div class="seg" id="bc-month-sel">${keyMonths.map((m) => `<button data-v="${m}">${monthTick(m, true)}</button>`).join("")}</div><div class="seg" id="bc-sub">${netSubs.map((s) => `<button data-v="${s}">r/${esc(s)}</button>`).join("")}</div></div>
    </div>
    <div class="fn-split"><div class="fn-left">${netStage("fn-bc-stage")}<div class="page fn-evidence" id="bc-netdoc"></div></div>
      <aside class="fn-right page">${narrativeHTML(st.narrative, "bc")}<h2>Insights</h2>${insightCards(st.insights)}</aside></div></div>`;
  lineChart(main.querySelector("#bc-price"), { labels: days, tickFormat: dayTick, format: (v) => `$${fmtInt(v)}`, height: 240, yMin: 0, series: [{ name: "BTC price (USD)", color: "#c98500", values: st.price.map((p) => p.price) }], events: ext, ariaLabel: "Bitcoin price" });
  lineChart(main.querySelector("#bc-vol"), { labels: days, tickFormat: dayTick, format: (v) => fmtInt(v), height: 220, yMin: 0, series: subs.slice(0, 3).map((s, k) => ({ name: `r/${s}`, color: PALETTE[k], values: days.map((d) => bySub[s]?.[d]?.comments ?? null) })), events: ext, ariaLabel: "Daily comments" });
  const phaseEvents = st.phases.map((p) => ({ x: p.start, label: `${p.label} (${dayTick(p.start)} – ${dayTick(p.end)})`, short: p.label }));
  lineChart(main.querySelector("#bc-tone"), { labels: days, tickFormat: dayTick, format: (v) => sign(v, 2), height: 260, yMin: "auto", series: subs.slice(0, 3).map((s, k) => ({ name: `r/${s}`, color: PALETTE[k], values: roll(days.map((d) => bySub[s]?.[d]?.mean_compound ?? null)) })), events: phaseEvents, ariaLabel: "Rolling mean tone" });
  lineChart(main.querySelector("#bc-month"), { labels: months, tickFormat: (m, l) => monthTick(m, l), format: (v) => fmtPct(v), height: 220, yMin: 0, directLabels: false, series: subs.slice(0, 2).flatMap((s, k) => [{ name: `r/${s} newcomers`, color: PALETTE[k], values: months.map((m) => mr(m, s).newcomer_share ?? null) }, { name: `r/${s} negative share`, color: PALETTE[k], dashed: true, values: months.map((m) => mr(m, s).neg_share ?? null) }]), ariaLabel: "Newcomer share and negative share by month" });
  const corr = st.correlations[lead]?.return_vs_mean_compound || [];
  if (corr.length) lineChart(main.querySelector("#bc-corr"), { labels: corr.map((c) => String(c.lag)), format: (v) => v.toFixed(2), height: 200, directLabels: false, series: [{ name: `r/${lead}: ρ(return, tone)`, color: PALETTE[0], values: corr.map((c) => c.rho), points: corr.map((c) => c.p < 0.01) }, ...(st.correlations[subs[1]] ? [{ name: `r/${subs[1]}`, color: PALETTE[1], values: st.correlations[subs[1]].return_vs_mean_compound.map((c) => c.rho), points: st.correlations[subs[1]].return_vs_mean_compound.map((c) => c.p < 0.01) }] : [])], ariaLabel: "Lagged rank correlation" });
  const sm = (s, m) => st.networks[s]?.[m]?.summary;
  lineChart(main.querySelector("#bc-struct"), { labels: months, tickFormat: (m, l) => monthTick(m, l), format: (v) => v.toFixed(2), height: 220, yMin: 0, directLabels: false, series: netSubs.flatMap((s, k) => [{ name: `r/${s} modularity`, color: PALETTE[k], values: months.map((m) => sm(s, m)?.modularity ?? null) }, { name: `r/${s} largest component`, color: PALETTE[k], dashed: true, values: months.map((m) => sm(s, m)?.largest_component_share ?? null) }]), ariaLabel: "Network structure by month" });
  const stage = main.querySelector("#fn-bc-stage");
  const m = mountNet(stage, { hasTone: true });
  const doc = main.querySelector("#bc-netdoc");
  let cmpSub = subs.includes(params.sub) ? params.sub : lead;
  const cmpEl = main.querySelector("#bc-cmp");
  function showCmp() { cmpEl.innerHTML = comparisonsTable(st.comparisons, [cmpSub], (k) => k); main.querySelectorAll("#bc-cmp-sub button").forEach((b) => setOn(b, b.dataset.v === cmpSub)); }
  main.querySelectorAll("#bc-cmp-sub button").forEach((b) => b.addEventListener("click", () => { cmpSub = b.dataset.v; showCmp(); }));
  showCmp();
  if (!SHOT && params.phase) setTimeout(() => main.querySelector("#bc-cmp-title").scrollIntoView({ block: "start" }), 60);
  function showNet() {
    const net = st.networks[cur]?.[month];
    replaceParams("findings", ["bitcoin"], { month, sub: cur });
    main.querySelectorAll("#bc-month-sel button").forEach((b) => setOn(b, b.dataset.v === month));
    main.querySelectorAll("#bc-sub button").forEach((b) => setOn(b, b.dataset.v === cur));
    if (net && net.core) m.show(net.core, { brokers: (net.bridges || []).map((b) => b.id), note: `${sub(cur)} · ${monthTick(month, true)} · ${coverText(net)}` });
    else stage.querySelector(".fn-net").innerHTML = `<div class="empty">No readable core for this month.</div>`;
    const themes = st.themes[cur] || {};
    const y0 = +month.slice(0, 4), m0 = +month.slice(5, 7), mS = Date.UTC(y0, m0 - 1, 1), mE = Date.UTC(y0, m0, 0);
    const overlapDays = (w) => Math.max(0, (Math.min(Date.parse(w.end), mE) - Math.max(Date.parse(w.start), mS)) / 864e5 + 1);
    const phaseOfMonth = Object.entries(st.windows).map((e) => [e, overlapDays(e[1])]).filter(([, o]) => o > 0).sort((a, b) => b[1] - a[1])[0]?.[0];   // the phase covering most of the month
    doc.innerHTML = `<h2>${sub(cur)} in ${monthTick(month, true)}</h2>
      ${net && net.summary ? `<div class="kpis"><div class="stat"><b>${fmtInt(net.summary.nodes)}</b><span>users exchanging replies</span></div><div class="stat"><b>${fmtInt(net.summary.edges)}</b><span>reply ties</span></div><div class="stat"><b>${net.summary.modularity_unweighted}</b><span>unweighted modularity (rewired ${net.summary.null_modularity?.mean?.toFixed(2)})</span></div><div class="stat"><b>${fmtShare(net.summary.largest_component_share)}</b><span>largest component</span></div><div class="stat"><b>${fmtPct(net.summary.reciprocity)}</b><span>reciprocated pairs</span></div></div>` : ""}
      ${net ? `<h3>Clusters and their tone</h3>${communitiesTable(net, { tone: true })}<h3>Brokers</h3>${bridgesTable(net)}` : ""}
      <h3>Words that mark each phase in ${sub(cur)}</h3><div class="grid3">${Object.entries(themes).map(([k, terms]) => `<div class="panel ${phaseOfMonth && phaseOfMonth[0] === k ? "is-active" : ""}"><h4>${esc(k)}</h4><p>${terms.map((t) => `<span class="fn-term" title="z = ${t.z}">${esc(t.term)}</span>`).join(" ")}</p></div>`).join("")}</div>
      <p class="muted">Log-odds ratio with an informative Dirichlet prior on document frequency, each phase against the others.</p>`;
  }
  main.querySelectorAll("#bc-month-sel button").forEach((b) => b.addEventListener("click", () => { month = b.dataset.v; showNet(); }));
  main.querySelectorAll("#bc-sub button").forEach((b) => b.addEventListener("click", () => { cur = b.dataset.v; showNet(); }));
  showNet();
  if (!SHOT && !params.phase && (params.month || params.sub)) setTimeout(() => stage.scrollIntoView({ block: "start" }), 60);
  return () => m.destroy();
}
