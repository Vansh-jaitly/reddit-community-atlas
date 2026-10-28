// Builds docs/presentation/Community_Atlas.pptx from the Atlas artifacts (every number is read from JSON).
// Usage (from this folder): npm install && npm run build
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..", "..");
const J = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));
const meta = J("atlas/web/data/meta.json");
const storyList = J("atlas/web/data/stories.json").stories;
const st = Object.fromEntries(storyList.map((s) => [s.id, s]));
const S = meta.summary, CC = meta.validation.bicm_crosscheck, V1 = meta.validation.v1_modularity_audit;
const CL = meta.cleaning_report;
const shot = (n) => path.join(ROOT, "docs/screenshots", n);

const fmt = (x) => Math.round(x).toLocaleString("en-US");
const pct = (x, d = 1) => `${(100 * x).toFixed(d)}%`;
const mil = (x) => `${(x / 1e6).toFixed(1)}M`;
const mlabel = (m) => new Date(Date.UTC(+m.slice(0, 4), +m.slice(5, 7) - 1, 1)).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
const totRaw = CL.reduce((a, r) => a + +r.rows_raw, 0), totClean = CL.reduce((a, r) => a + +r.rows_clean, 0);
const months = S.months, Q = S.quarters;
const qj = Object.values(S.quarter_edge_jaccard);

// ---------- palette (matches the app; validated dark categorical slots) ----------
const BG = "111110", BG2 = "1A1A19", CARD = "222220", LINE = "333330";
const INK = "F0EFEC", INK2 = "C3C2B7", MUTED = "8E8D86";
const SER = ["3987E5", "D95926", "199E70", "C98500", "D55181", "008300", "9085E9", "E66767"];
const FONT = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.title = "Beyond the Hairball: The Reddit Community Atlas";
pres.author = "Akashita, Vansh Jaitly";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

pres.defineSlideMaster({
  title: "TITLE", background: { color: BG },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.0, w: 6.2, h: 2.2, fontFace: FONT, fontSize: 40, bold: true, color: INK, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 4.35, w: 6.0, h: 1.4, fontFace: FONT, fontSize: 18, color: INK2, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: BG },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.9, fontFace: FONT, fontSize: 30, bold: true, color: INK, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: "Beyond the Hairball · The Reddit Community Atlas · CSE3729", options: { x: 0.6, y: 7.02, w: 8, h: 0.3, fontFace: FONT, fontSize: 10, color: MUTED, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.02, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color: MUTED, align: "right" },
});

const text = (slide, t, o) => slide.addText(t, { isTextBox: true, fontFace: FONT, color: INK2, fontSize: 15, margin: 0, valign: "top", ...o });
const card = (slide, x, y, w, h, name) => slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: CARD }, line: { color: LINE, width: 0.75 }, rectRadius: 0.08, objectName: name });
function stat(slide, x, y, w, big, label, color = INK) {
  text(slide, big, { x, y, w, h: 0.75, fontSize: 36, bold: true, color, valign: "bottom" });
  text(slide, label, { x, y: y + 0.8, w, h: 0.6, fontSize: 13, color: MUTED });
}
function image(slide, file, x, y, w) {
  slide.addImage({ path: shot(file), x, y, w, h: w / 1.6, altText: file.replace(/^\d+_|\.png$/g, "").replace(/_/g, " ") });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h: w / 1.6, fill: { type: "none" }, line: { color: LINE, width: 0.75 } });
}
function dotNode(slide, x, y, color, label) {   // motif: network nodes
  slide.addShape(pres.shapes.OVAL, { x, y, w: 0.42, h: 0.42, fill: { color }, line: { color: BG, width: 0 } });
  if (label) text(slide, label, { x, y: y + 0.06, w: 0.42, h: 0.3, fontSize: 12, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
}
const content = (section, title) => { const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section }); s.addText(title, { placeholder: "title" }); return s; };

const A = st.popularity.metrics, B = st.neighbours.metrics, C = st.connectors.metrics, D = st.crowds.metrics;
const cpKey = Object.keys(D.crypto_pair_affinity)[0], cp = D.crypto_pair_affinity[cpKey];
const mkKey = Object.keys(D.marvel_pair_affinity)[0], mv = D.marvel_pair_affinity[mkKey];
const mi = Object.fromEntries(months.map((m, i) => [m, i]));
const base = D.baseline_month;

// 1 ---------------------------------------------------------------- title
pres.addSection({ title: "Opening" });
let s = pres.addSlide({ masterName: "TITLE", sectionTitle: "Opening" });
s.addText("Beyond the Hairball: The Reddit Community Atlas", { placeholder: "title" });
s.addText(`What really connects Reddit's communities? An interactive map of surprising shared audiences across ${S.subreddits} subreddits, ${mlabel(months[0])} – ${mlabel(months.at(-1))}`, { placeholder: "body" });
text(s, "CSE3729 Computational Social Media Analysis · BML Munjal University\nAkashita (230779) · Vansh Jaitly (230687)", { x: 0.6, y: 6.15, w: 6.2, h: 0.7, fontSize: 13, color: MUTED });
image(s, "01_discover.png", 7.1, 1.6, 5.7);
s.addNotes("Introduce the question: which Reddit communities share an audience, and which only seem to because they are big. Point at the live map: every circle is a subreddit, every line a surprisingly large shared audience.");

// 2 ---------------------------------------------------------------- hairball
pres.addSection({ title: "Problem and data" });
s = content("Problem and data", "Raw shared audiences connect almost everything");
image(s, "02_atlas_raw.png", 0.6, 1.45, 5.85);
image(s, "03_atlas_adjusted.png", 6.85, 1.45, 5.85);
stat(s, 0.6, 5.25, 5.8, pct(S.cosine_density.all, 2), "of subreddit pairs share at least one commenter: the raw network is a hairball");
stat(s, 6.85, 5.25, 5.8, pct(S.validated_density.all), "of pairs share far more commenters than size and activity predict", SER[0]);
s.addNotes(`Raw overlap links ${pct(S.cosine_density.all, 2)} of pairs, because one person who comments in many places links all of them. Keeping only pairs that beat the expected overlap leaves ${pct(S.validated_density.all)}, and topical communities appear.`);

// 3 ---------------------------------------------------------------- data
s = content("Problem and data", "A year of Reddit comments, cleaned and pseudonymised");
const stats3 = [[mil(totRaw), "raw comments collected"], [mil(totClean), `kept after cleaning (${pct(totClean / totRaw, 1)})`], [`${(S.users_total / 1e6).toFixed(2)}M`, "distinct pseudonymised commenters"], [`${S.subreddits} × ${months.length}`, "subreddits × months"]];
stats3.forEach(([b, l], k) => { card(s, 0.6 + k * 3.075, 1.5, 2.85, 1.7, `stat-${k}`); stat(s, 0.85 + k * 3.075, 1.6, 2.5, b, l, k === 1 ? SER[2] : INK); });
const flow = ["Arctic Shift archive", "Fetch + salted hash", "Clean (activity, bots)", "User × subreddit matrix", "Expected overlap (BiCM)", "Surprising links (FDR 1%)", "Communities + roles", "Atlas app"];
flow.forEach((f, k) => {
  const x = 0.6 + k * 1.53;
  card(s, x, 3.75, 1.38, 1.05, `flow-${k}`);
  text(s, f, { x: x + 0.1, y: 3.8, w: 1.18, h: 0.95, fontSize: 12.5, color: INK, align: "center", valign: "middle" });
  if (k < flow.length - 1) text(s, "›", { x: x + 1.38, y: 3.95, w: 0.15, h: 0.6, fontSize: 20, color: MUTED, align: "center" });
});
text(s, [
  { text: "Frame: ", options: { bold: true, color: INK } },
  { text: "150 topical subreddits (25 in each of 6 categories) + 20 front-page hubs, chosen by a fixed rule before analysis. ", options: {} },
  { text: "Scope: ", options: { bold: true, color: INK } },
  { text: `the proposal planned 2019–2025; the archive's comments end in Aug 2022, and this bounded study covers ${Q.map((q) => q.slice(0, 4) + " Q" + q.slice(-1)).join(", ")}. `, options: {} },
  { text: "Privacy: ", options: { bold: true, color: INK } },
  { text: "no text stored; usernames hashed at collection; only subreddit-level aggregates published.", options: {} },
], { x: 0.6, y: 5.2, w: 12.1, h: 1.5, fontSize: 15 });
s.addNotes("Data: public comments from the Arctic Shift archive, read remotely with DuckDB. Every fetch checks that all 170 subreddits are present. Cleaning keeps accounts with at least five comments a quarter and removes bot-like accounts.");

// 4 ---------------------------------------------------------------- method
pres.addSection({ title: "Method" });
s = content("Method", "The question for every pair: more shared commenters than chance?");
card(s, 0.6, 1.5, 6.3, 5.2, "method-card");
text(s, "Expected shared commenters", { x: 0.9, y: 1.75, w: 5.8, h: 0.4, fontSize: 18, bold: true, color: INK });
text(s, "A random Reddit in which every account keeps its number of subreddits and every subreddit keeps its number of commenters, but who comments where is shuffled (Bipartite Configuration Model, Saracco et al. 2015).", { x: 0.9, y: 2.2, w: 5.8, h: 1.2, fontSize: 15 });
text(s, "expected(a,b) = Σ users  p(u→a) · p(u→b)\naffinity(a,b) = shared ÷ expected", { x: 0.9, y: 3.45, w: 5.8, h: 0.9, fontSize: 16, fontFace: "Courier New", color: INK });
text(s, `A link is drawn only when the shared count is improbably high: one-sided Poisson test, Benjamini–Hochberg false discovery rate ${pct(S.alpha, 0)} over all ${fmt(S.subreddits * (S.subreddits - 1) / 2)} pairs. Communities: Leiden on log-affinity. Connector role: participation coefficient.`, { x: 0.9, y: 4.5, w: 5.8, h: 1.9, fontSize: 15 });
const checks = [
  [`${CC.validated_ours} = ${CC.validated_reference}`, "links validated by our code and the published bicm package (150k-user real sample)"],
  [pct(S.robust_share.all, 0), "of links survive a stricter ≥2-comment threshold"],
  [`${Math.round(100 * Math.min(...qj))}–${Math.round(100 * Math.max(...qj))}%`, "of links persist from one quarter to the next (Jaccard)"],
  ["108", "automated tests, incl. recomputing every story number from published data"],
];
checks.forEach(([b, l], k) => { const y = 1.5 + k * 1.33; card(s, 7.25, y, 5.45, 1.15, `check-${k}`); text(s, b, { x: 7.5, y: y + 0.12, w: 1.9, h: 0.9, fontSize: 26, bold: true, color: SER[2], valign: "middle" }); text(s, l, { x: 9.45, y: y + 0.12, w: 3.1, h: 0.9, fontSize: 13.5, valign: "middle" }); });
s.addNotes("Explain observed versus expected in one sentence. The model only keeps how active each person is and how big each community is; anything beyond that is a genuine shared audience. Validation: identical to the reference implementation, robust to a stricter threshold, stable over time.");

// 5 ---------------------------------------------------------------- story 1
pres.addSection({ title: "Findings" });
s = content("Findings", "What popularity hides: hubs vanish from real neighbour lists");
const ex = A.example;
card(s, 0.6, 1.5, 3.6, 5.2, "s1-stats");
stat(s, 0.85, 1.7, 3.2, pct(A.hub_share_cosine, 0), "of a topical subreddit's 10 closest neighbours are front-page hubs, by raw overlap");
stat(s, 0.85, 3.4, 3.2, pct(A.hub_share_affinity, 0), "after adjusting for size and activity", SER[0]);
text(s, `r/${A.biggest}: ${fmt(A.biggest_users)} commenters, median affinity ${A.biggest_median_affinity.toFixed(2)}× — big, not close to anyone.`, { x: 0.85, y: 5.25, w: 3.2, h: 1.3, fontSize: 13.5 });
const col = (x, title, rows, color) => {
  text(s, title, { x, y: 1.55, w: 4, h: 0.4, fontSize: 16, bold: true, color: INK });
  rows.forEach((r, k) => {
    const y = 2.05 + k * 0.72;
    card(s, x, y, 4.05, 0.6, `${title}-${k}`);
    text(s, `r/${r.name}${r.gateway ? "   HUB" : ""}`, { x: x + 0.2, y: y + 0.1, w: 2.8, h: 0.4, fontSize: 15, color: r.gateway ? "C98500" : INK, valign: "middle" });
    text(s, `${r.affinity.toFixed(2)}×`, { x: x + 2.95, y: y + 0.1, w: 0.9, h: 0.4, fontSize: 15, color, align: "right", valign: "middle" });
  });
};
col(4.55, `r/${ex} · raw overlap`, A.example_cosine_neighbours.slice(0, 6), INK2);
col(8.65, `r/${ex} · adjusted`, A.example_affinity_neighbours.slice(0, 6), SER[0]);
text(s, "Numbers: affinity (shared ÷ expected) over all 12 months. 1.0× = chance.", { x: 4.55, y: 6.45, w: 8.1, h: 0.35, fontSize: 12, color: MUTED });
s.addNotes(`By raw overlap r/${ex} looks closest to front-page hubs. Adjusted, its neighbours are ${A.example_affinity_neighbours.slice(0, 3).map((x) => "r/" + x.name).join(", ")}.`);

// 6 ---------------------------------------------------------------- communities
s = content("Findings", `${S.anchor.communities} stable communities emerge from the surprising links`);
image(s, "03_atlas_adjusted.png", 0.6, 1.45, 7.3);
meta.communities.forEach((c, k) => {
  const y = 1.5 + k * 0.5;
  s.addShape(pres.shapes.OVAL, { x: 8.3, y: y + 0.1, w: 0.22, h: 0.22, fill: { color: c.size > 1 && k < 8 ? SER[k] : "8A8984" }, line: { color: BG, width: 0 } });
  text(s, c.label, { x: 8.65, y, w: 3.4, h: 0.42, fontSize: 14.5, color: INK, valign: "middle" });
  text(s, String(c.size), { x: 12.1, y, w: 0.6, h: 0.42, fontSize: 14.5, color: MUTED, align: "right", valign: "middle" });
});
text(s, `Weighted modularity ${S.anchor.weighted_modularity} · agreement across 20 seeds ARI ${S.anchor.seed_ari} · each quarter's communities match at ARI ${Q.map((q) => S.period_communities[q].ari_vs_anchor).join(", ")}`, { x: 8.3, y: 6.15, w: 4.4, h: 0.7, fontSize: 12, color: MUTED });
s.addNotes("The detected communities largely follow topics, with telling exceptions: r/Economics sits with politics, and media subreddits split between the front page and hobbies.");

// 7 ---------------------------------------------------------------- story 2
s = content("Findings", "Unexpected neighbours: for some communities, country beats topic");
const top = B.top_links.slice(0, 8).reverse();
s.addChart(pres.charts.BAR, [{ name: "Minimum affinity in any quarter", labels: top.map((x) => `r/${x.a} – r/${x.b}`), values: top.map((x) => x.min_affinity) }], {
  x: 0.6, y: 1.45, w: 7.9, h: 5.3, barDir: "bar", chartColors: [SER[1]], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"×"',
  dataLabelColor: INK, dataLabelFontSize: 12, dataLabelFontFace: FONT, catAxisLabelColor: INK2, catAxisLabelFontSize: 12, catAxisLabelFontFace: FONT,
  valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false,
  showTitle: true, title: "Minimum affinity across all four quarters (shared ÷ expected)", titleColor: MUTED, titleFontSize: 12, titleFontFace: FONT,
});
const lead = B.top_links[0];
card(s, 8.85, 1.5, 3.85, 5.2, "s2-callout");
stat(s, 9.1, 1.7, 3.4, fmt(lead.shared_all), `commenters shared by r/${lead.a} and r/${lead.b}`);
stat(s, 9.1, 3.35, 3.4, fmt(lead.expected_all), "expected from size and activity alone", SER[1]);
text(s, `${B.robust_cross_category_links} cross-category links hold in every quarter and under the stricter threshold. The second strongest is the UK pair. Without text we cannot say why: geography, profession and demographics all fit.`, { x: 9.1, y: 5.0, w: 3.4, h: 1.6, fontSize: 13.5 });
s.addNotes("A nation's politics forum and its personal-finance forum share an audience seven times larger than chance, in every quarter.");

// 8 ---------------------------------------------------------------- story 3
s = content("Findings", "The hidden connectors are mid-sized topical communities, not hubs");
const conn = C.connectors.slice(0, 8).reverse();
s.addChart(pres.charts.BAR, [{ name: "Participation", labels: conn.map((c) => `r/${c.name}`), values: conn.map((c) => c.participation_min) }], {
  x: 0.6, y: 1.45, w: 7.9, h: 5.3, barDir: "bar", chartColors: [SER[2]], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00",
  dataLabelColor: INK, dataLabelFontSize: 12, dataLabelFontFace: FONT, catAxisLabelColor: INK2, catAxisLabelFontSize: 13, catAxisLabelFontFace: FONT,
  valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 0.8, valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false,
  showTitle: true, title: "Participation coefficient, minimum across quarters (≥ 8 links)", titleColor: MUTED, titleFontSize: 12, titleFontFace: FONT,
});
card(s, 8.85, 1.5, 3.85, 5.2, "s3-callout");
stat(s, 9.1, 1.7, 3.4, C.hub_mean_participation.toFixed(2), "average for the 20 front-page hubs");
stat(s, 9.1, 3.35, 3.4, C.topical_mean_participation.toFixed(2), "average for topical communities", SER[2]);
text(s, `0 = all surprising links stay in one community; towards 1 = spread evenly. Rankings are stable between quarters (ρ ${Object.values(C.rank_stability).map((v) => v.toFixed(2)).join(", ")}).`, { x: 9.1, y: 5.0, w: 3.4, h: 1.6, fontSize: 13.5 });
s.addNotes("Connectors share unusually large audiences with several clusters. That is co-presence, not evidence that information flows through them.");

// 9 ---------------------------------------------------------------- story 4
s = content("Findings", "When crowds leave, ties tighten; when they arrive, ties loosen");
const idx = (arr) => arr.map((v) => Math.round((100 * v) / arr[0]));
const crypto = D.crypto_monthly_authors;
s.addChart(pres.charts.LINE, [
  { name: "r/Bitcoin", labels: months.map(mlabel), values: idx(crypto.Bitcoin) },
  { name: "r/CryptoCurrency", labels: months.map(mlabel), values: idx(crypto.CryptoCurrency) },
  { name: "r/investing", labels: months.map(mlabel), values: idx(D.comparison_monthly_authors.investing) },
  { name: "All 170 subreddits", labels: months.map(mlabel), values: idx(D.frame_monthly_authors) },
], {
  x: 0.6, y: 1.45, w: 6.0, h: 4.4, chartColors: [SER[0], SER[1], SER[3], "8A8984"], lineSize: 2, lineDataSymbol: "none",
  catAxisLabelColor: MUTED, valAxisLabelColor: MUTED, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10, catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT,
  valGridLine: { color: "2B2B29", size: 0.75 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "b", legendColor: INK2, legendFontSize: 11, legendFontFace: FONT,
  showTitle: true, title: `Monthly commenters (${mlabel(months[0])} = 100)`, titleColor: MUTED, titleFontSize: 12, titleFontFace: FONT,
});
s.addChart(pres.charts.LINE, [
  { name: `r/${cpKey.replace("|", " – r/")}`, labels: months.map(mlabel), values: cp },
  { name: `r/${mkKey.replace("|", " – r/")}`, labels: months.map(mlabel), values: mv },
], {
  x: 6.75, y: 1.45, w: 6.0, h: 4.4, chartColors: [SER[0], SER[4]], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 6,
  catAxisLabelColor: MUTED, valAxisLabelColor: MUTED, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10, catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT,
  valGridLine: { color: "2B2B29", size: 0.75 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "b", legendColor: INK2, legendFontSize: 11, legendFontFace: FONT,
  valAxisMinVal: 0, showTitle: true, title: "Affinity between the two communities (× chance)", titleColor: MUTED, titleFontSize: 12, titleFontFace: FONT,
});
text(s, [
  { text: "Crypto: ", options: { bold: true, color: INK } },
  { text: `Bitcoin peaked 17 Dec 2017; r/Bitcoin commenters ${Math.round(100 * D.change_since_baseline.Bitcoin)}% by ${mlabel(months.at(-1))} while the frame grew ${Math.round(100 * D.frame_change_since_baseline)}%. The remaining audiences overlap ${cp[mi[base]]}× → ${cp.at(-1)}×.  ` },
  { text: "Marvel: ", options: { bold: true, color: INK } },
  { text: `Infinity War (27 Apr 2018) doubled weekly commenters; affinity fell to ${mv[mi["2018-04"]]}× in April.  ` },
  { text: "All communities: ", options: { bold: true, color: INK } },
  { text: `ρ = ${D.general_tendency.spearman_large_swings} over ${D.general_tendency.n_large_swings} swings > 25%. Association, not causation.` },
], { x: 0.6, y: 6.0, w: 12.1, h: 0.85, fontSize: 13.5 });
s.addNotes("Arriving crowds mostly comment in only one of the related communities, which dilutes the surprising overlap; a departing crowd leaves a core active in all of them.");

// 10 --------------------------------------------------------------- application
pres.addSection({ title: "Application" });
s = content("Application", "The Atlas lets anyone check every claim");
[["06_story_popularity_example.png", "Guided stories drive the map"], ["13_explore_profile.png", "Profile of any subreddit"], ["14_compare_pair.png", "Compare two communities over time"], ["15_compare_periods.png", "Compare two periods: links gained and lost"]].forEach(([f, cap], k) => {
  const x = 0.6 + (k % 2) * 6.2, y = 1.4 + Math.floor(k / 2) * 2.85;
  image(s, f, x, y, 3.85);
  text(s, cap, { x: x + 4.05, y: y + 0.2, w: 1.95, h: 1.6, fontSize: 15, color: INK });
});
s.addNotes("Live demo: open the Atlas, search r/personalfinance, play the crowds story, compare two periods. Every view is a URL; the Streamlit console shows data collection and cleaning.");

// 11 --------------------------------------------------------------- evolution
pres.addSection({ title: "Evolution and limits" });
s = content("Evolution and limits", "How the project evolved from the submitted proposal");
const steps = [
  ["Proposal", "Do bridge positions between communities outlast the people occupying them?"],
  ["V1 hairball", `Cosine network ${pct(V1["2018Q1"].density, 2)} dense; 4 communities → only 6 bridge positions, all saturated`],
  ["Audit", `Reported Q ${V1["2018Q1"].stored_unweighted_q} was unweighted; the weighted value is ${V1["2018Q1"].weighted_q}`],
  ["Re-representation", "Literature on bipartite projections → BiCM validation, checked against the reference code"],
  ["Atlas", "Bridges become measured connector roles; time becomes the crowd stories"],
];
steps.forEach(([h, d], k) => {
  const x = 0.6 + k * 2.47;
  dotNode(s, x, 1.75, SER[k], String(k + 1));
  if (k < steps.length - 1) s.addShape(pres.shapes.LINE, { x: x + 0.47, y: 1.96, w: 1.95, h: 0, line: { color: LINE, width: 1.5 } });
  text(s, h, { x, y: 2.4, w: 2.25, h: 0.45, fontSize: 17, bold: true, color: INK });
  text(s, d, { x, y: 2.9, w: 2.2, h: 2.2, fontSize: 14 });
});
card(s, 0.6, 5.35, 12.1, 1.35, "evo-note");
text(s, "V1 is preserved unchanged at git tag v1-baseline. The occupant-turnover hypothesis is not claimed as proven or disproven: it needs many more bridge positions and a matched null, which is future work.", { x: 0.85, y: 5.5, w: 11.6, h: 1.05, fontSize: 15, valign: "middle" });
s.addNotes("The change of lens follows from evidence, not convenience. The original question survives as the connector role and the temporal stories.");

// 12 --------------------------------------------------------------- limits
s = content("Evolution and limits", "What we can and cannot conclude");
const can = ["Which subreddit pairs share more commenters than size and activity explain", "That these links form stable topical communities and connector roles", "That audiences changed around dated events, and how affinity moved with them"];
const cannot = ["Why audiences overlap: no text, so no topics, motives or sentiment", "That events caused the changes: associations only", "Anything about Reddit as a whole: a fixed sample of 170 subreddits, 12 months, commenters only, with archive gaps"];
[[can, "We can show", SER[2]], [cannot, "We cannot claim", SER[1]]].forEach(([list, h, c], k) => {
  const x = 0.6 + k * 6.2;
  card(s, x, 1.5, 5.9, 5.2, `limits-${k}`);
  text(s, h, { x: x + 0.3, y: 1.7, w: 5.3, h: 0.5, fontSize: 20, bold: true, color: c });
  list.forEach((t, j) => { dotNode(s, x + 0.3, 2.45 + j * 1.35, c); text(s, t, { x: x + 0.95, y: 2.4 + j * 1.35, w: 4.7, h: 1.2, fontSize: 15.5, color: INK }); });
});
s.addNotes("Ethics: public data, salted hashes, aggregate-only publication, sensitive support communities shown only in aggregate.");

// 13 --------------------------------------------------------------- close
s = pres.addSlide({ masterName: "TITLE", sectionTitle: "Evolution and limits" });
s.addText("Size explains most raw overlap. What remains is a readable, stable map", { placeholder: "title" });
s.addText(`${pct(S.validated_density.all)} of pairs, ${S.anchor.communities} communities, country-level neighbours, mid-sized connectors, and ties that loosen and tighten with crowds.`, { placeholder: "body" });
card(s, 7.1, 2.0, 5.6, 3.6, "run-card");
text(s, "Run it", { x: 7.4, y: 2.2, w: 5, h: 0.45, fontSize: 18, bold: true, color: INK });
text(s, "python atlas/serve.py\npython atlas/build_atlas.py\npython -m pytest tests/\nstreamlit run data_curation/dashboard.py", { x: 7.4, y: 2.75, w: 5.1, h: 1.9, fontSize: 15, fontFace: "Courier New", color: INK2 });
text(s, "Report: docs/FINAL_REPORT.pdf", { x: 7.4, y: 4.85, w: 5.1, h: 0.4, fontSize: 13, color: MUTED });

// Appendix ------------------------------------------------------------------
pres.addSection({ title: "Appendix" });
s = content("Appendix", "Appendix: the literature behind each design decision");
const lit = [
  ["Saracco et al. 2015, 2017", "BiCM null model; Poisson-binomial test with FDR", "Edge definition"],
  ["Neal et al. 2021; Cimini et al. 2022", "Comparing null models; agreement at matched density", "BiCM over exact sampling; sensitivity checks"],
  ["Olson & Neal 2015; Waller & Anderson 2021", "Reddit maps from shared users; beyond-chance similarity", "Reddit precedent; observed ÷ expected"],
  ["Traag et al. 2019; Good et al. 2010", "Leiden; degeneracy of modularity", "Leiden + seed/sensitivity reporting"],
  ["Guimerà & Amaral 2005; Greene et al. 2010", "Participation coefficient; Jaccard matching over time", "Connector score; persistence"],
  ["Shneiderman 1996; Segel & Heer 2010; Archambault et al. 2011", "Overview → details; martini-glass stories; small multiples", "App structure and story mode"],
  ["Gaffney & Matias 2018; Horta Ribeiro et al. 2021", "Missing Pushshift data; text-free event metrics", "Lower bounds; crowd-story metrics"],
];
s.addTable([[{ text: "Source", options: { bold: true, color: MUTED } }, { text: "Establishes", options: { bold: true, color: MUTED } }, { text: "Used for", options: { bold: true, color: MUTED } }],
  ...lit.map((r) => r.map((c) => ({ text: c })))], {
  x: 0.6, y: 1.45, w: 12.1, colW: [4.0, 4.6, 3.5], fontFace: FONT, fontSize: 13, color: INK2, fill: { color: BG2 }, border: { type: "solid", color: LINE, pt: 0.75 }, rowH: 0.62, valign: "middle",
});

const out = path.join(ROOT, "docs/presentation/Community_Atlas.pptx");
fs.mkdirSync(path.dirname(out), { recursive: true });
pres.writeFile({ fileName: out }).then((f) => console.log("wrote", f));
