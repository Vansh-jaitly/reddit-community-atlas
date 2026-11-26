"""
Generate the final report and the demo script from the Atlas artifacts, so every
number in them traces to a generated file (atlas/web/data/*.json,
atlas/validation/bicm_crosscheck.json, data_curation/data/logs/*).

Usage:  python tools/build_docs.py [--pdf]
Writes: docs/FINAL_REPORT.md, docs/FINAL_REPORT.html (+ .pdf with --pdf), docs/DEMO_SCRIPT.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "atlas/web/data"
DOCS = ROOT / "docs"

meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
_stories_file = json.loads((DATA / "stories.json").read_text(encoding="utf-8"))
stories = {s["id"]: s for s in _stories_file["stories"]}
validity = _stories_file["validity_notes"]
label_mismatch = _stories_file.get("label_mismatch")
S = meta["summary"]
CC = meta["validation"]["bicm_crosscheck"]
V1 = meta["validation"]["v1_modularity_audit"]
CL = meta["cleaning_report"]
Q = S["quarters"]
CAT = meta["categories"]


def n(x):
    return f"{int(round(x)):,}"


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def mlabel(m):
    return dt.date(int(m[:4]), int(m[5:7]), 1).strftime("%b %Y")


def qlabel(q):
    return f"{q[:4]} Q{q[-1]}"


tot_raw = sum(int(r["rows_raw"]) for r in CL)
tot_clean = sum(int(r["rows_clean"]) for r in CL)
A, B, C, D = stories["popularity"], stories["neighbours"], stories["connectors"], stories["crowds"]
Am, Bm, Cm, Dm = A["metrics"], B["metrics"], C["metrics"], D["metrics"]
months = S["months"]
qj = S["quarter_edge_jaccard"]
mj = S["month_edge_jaccard"]
cp_key = next(iter(Dm["crypto_pair_affinity"]))
fmtx = lambda v: f"{v:.1f}×"
pl_json = json.loads((DATA / "pipeline.json").read_text(encoding="utf-8")) if (DATA / "pipeline.json").exists() else None
pl_tests = len(pl_json["tests"]) if pl_json else 112
lead_big = next((e for e in (pl_json["examples"] if pl_json else []) if e["a"] == Am["biggest"]), {"shared": 0})
cp = Dm["crypto_pair_affinity"][cp_key]
cp2 = Dm["crypto_pair_affinity_min2"][cp_key]
mk = next(iter(Dm["marvel_pair_affinity"]))
mv = Dm["marvel_pair_affinity"][mk]
mi = {m: i for i, m in enumerate(months)}
base = Dm["baseline_month"]
gt = Dm["tendency"]
crypto_names = list(Dm["crypto_monthly_authors"])
sw = Dm.get("starwars")
mvl = Dm["marvel"]
rate_ab, rate_ba, cos_m = Dm["crypto_cross_rate_ab"], Dm["crypto_cross_rate_ba"], Dm["crypto_pair_cosine"]
anc = S["anchor"]
comm_phrase = (f"{anc['communities_major']} major communities (plus {anc['small_groups']} small groups and {anc['isolates']} isolate{'s' if anc['isolates'] != 1 else ''})"
               if "communities_major" in anc else f"{anc['communities']} communities")
giant = Am["giant_pair"]
country = Bm["country"]
ideo = Bm["ideology"]
iso = Bm["isolation"][0]
hub_conn = [c["name"] for c in Cm["connectors"][:8] if c["gateway"]]
gi = Cm["giants"]
ctrl = country["same_topic_across_border"][0]
pair_status = lambda u: "surprising but small" if u["validated"] else ("fewer than chance" if u["avoided"] else ("below expectation" if u["affinity"] < 0.9 else "within chance"))
avoided_pairs = pl_json["stages"]["validated"]["avoided_pairs"] if pl_json else None
vig = validity[0] if validity else None


def community_table():
    rows = ["| Community (auto-labelled) | Subreddits | Largest members | Category mix |", "|---|---:|---|---|"]
    for c in meta["communities"]:
        mix = ", ".join(f"{CAT[k].split(' ')[0].rstrip(',').lower()} {v}" for k, v in c["category_mix"].items())
        rows.append(f"| {c['label']} | {c['size']} | {', '.join('r/' + x for x in c['members'][:5])} | {mix} |")
    return "\n".join(rows)


def links_table(rows, k=8):
    out = ["| Pair | Categories | Shared (all months) | Expected | Minimum affinity in any quarter |", "|---|---|---:|---:|---:|"]
    for x in rows[:k]:
        out.append(f"| r/{x['a']} – r/{x['b']} | {CAT[x['cat_a']]} × {CAT[x['cat_b']]} | {n(x['shared_all'])} | {n(x['expected_all'])} | {x['min_affinity']:.2f}× |")
    return "\n".join(out)


def connectors_table():
    out = ["| Subreddit | Frame category | Clusters reached | Participation (min over quarters) |", "|---|---|---:|---:|"]
    for c in Cm["connectors"][:8]:
        out.append(f"| r/{c['name']} | {CAT[c['category']]} | {c['communities_reached']} | {c['participation_min']:.2f} |")
    return "\n".join(out)


def country_table():
    out = ["| Pair | Relation | Shared | Expected | Affinity | Status |", "|---|---|---:|---:|---:|---|"]
    rows = [(x, "same country, different topic") for x in country["same_country"]] + \
           [(x, "same topic, across the border (control)") for x in country["same_topic_across_border"]] + \
           [(x, "national forum vs the US-default forum") for x in country["to_us_default"]]
    for x, rel in rows:
        status = "surprising" if x["validated"] else ("fewer than chance" if x["avoided"] else "within chance")
        out.append(f"| r/{x['a']} – r/{x['b']} | {rel} | {n(x['shared'])} | {n(x['expected'])} | {x['affinity']:.2f}× | {status} ({x['validated_periods']} of {country['periods']} periods significant) |")
    return "\n".join(out)


def outward_table():
    out = ["| Cluster | Subreddits | Links inside / outward | Share leaving | vs degree-preserving rewiring |", "|---|---:|---|---:|---:|"]
    for o in Cm["outward"]:
        out.append(f"| {o['community']} | {o['members']} | {n(o['links_inside'])} / {n(o['links_outward'])} | {pct(o['outward_share'], 0)} | {o['outward_vs_expected']:.2f}× |")
    return "\n".join(out)


def apart_table():
    out = ["| Pair | Shared | Expected | Affinity | Quarters below half of expectation |", "|---|---:|---:|---:|---:|"]
    for x in Bm["lowest_pairs"][:6]:
        out.append(f"| r/{x['a']} – r/{x['b']} | {n(x['shared'])} | {n(x['expected'])} | {x['affinity']:.3f}× | {x['quarters_below_half']} of {len(Q)} |")
    return "\n".join(out)


def cleaning_table():
    out = ["| Quarter | Raw comments | Retained | % kept | Commenters (raw → kept) | Bot accounts removed |", "|---|---:|---:|---:|---|---:|"]
    for r in CL:
        out.append(f"| {qlabel(r['quarter'])} | {n(int(r['rows_raw']))} | {n(int(r['rows_clean']))} | {pct(int(r['rows_clean']) / int(r['rows_raw']))} | "
                   f"{n(int(r['users_raw']))} → {n(int(r['users_clean']))} | {r['hard_bots_removed']} |")
    out.append(f"| **Total** | **{n(tot_raw)}** | **{n(tot_clean)}** | **{pct(tot_clean / tot_raw, 2)}** | {n(S['users_total'])} distinct kept | "
               f"{sum(int(r['hard_bots_removed']) for r in CL)} |")
    return "\n".join(out)


def ex_lists():
    raw = ", ".join(f"r/{x['name']}{' (hub)' if x['gateway'] else ''}" for x in Am["example_cosine_neighbours"][:5])
    adj = ", ".join(f"r/{x['name']} ({x['affinity']:.2f}×)" for x in Am["example_affinity_neighbours"][:5])
    return raw, adj


raw_list, adj_list = ex_lists()
cross = Bm["top_cross_community_links"]
lead = Bm["top_links"][0]

REPORT = f"""---
title: "Beyond the Hairball: The Reddit Community Atlas"
---

# Beyond the Hairball: The Reddit Community Atlas

**What really connects Reddit's communities? An interactive, statistically validated map of shared audiences across {S['subreddits']} subreddits ({mlabel(months[0])} – {mlabel(months[-1])})**

CSE3729 Computational Social Media Analysis · BML Munjal University · Academic year 2026–27

Team: Akashita (230779), Vansh Jaitly (230687) · see `docs/CONTRIBUTION_MATRIX.md`

*Every number in this report is generated from the project's build artifacts by `tools/build_docs.py`; Appendix A maps each headline figure to the file it comes from.*

---

## Abstract

Online communities are often mapped through the audiences they share, but raw shared-audience networks mostly measure size: one person who comments in many places links all of them, and the biggest communities look close to everything. We collected {n(tot_raw)} public Reddit comments from a fixed, rule-based frame of {S['subreddits']} subreddits over {len(months)} months ({mlabel(months[0])} – {mlabel(months[-1])}), cleaned them to {n(tot_clean)} comments by {n(S['users_total'])} pseudonymised commenters, and built a user × subreddit network. The conventional cosine projection links {pct(S['cosine_density']['all'], 2)} of all subreddit pairs. Comparing each pair's shared commenters with the number expected from community size and user activity alone (the Bipartite Configuration Model, BiCM) and keeping only pairs that exceed it at a 1% false discovery rate leaves {pct(S['validated_density']['all'])} of pairs. That network has a clear, reproducible structure: {comm_phrase} (weighted modularity {S['anchor']['weighted_modularity']}, seed agreement ARI {S['anchor']['seed_ari']}), stable connector roles, and a Jaccard overlap of {min(qj.values()):.2f}–{max(qj.values()):.2f} between consecutive quarters' link sets (about {100 * 2 * min(qj.values()) / (1 + min(qj.values())):.0f}% of a quarter's links recur). We built the results into an interactive web application, the Community Atlas, with four guided discoveries: what popularity hides, neighbours and strangers (the same test also marks pairs that share *fewer* commenters than chance), connectors and sealed clusters, and what changes — and what only appears to — when crowds arrive and leave. The project started as a test of whether cross-community "bridge positions" outlast their occupants. It evolved after the first, cosine-based pipeline proved too dense to measure bridges at all. The findings are descriptive and specific to this sample.

---

## 1. Introduction and research questions

Reddit is organised into hundreds of thousands of topical communities. Which of them share an audience, and why, is a basic question about how online attention is organised. It matters for information spread, community moderation and for any study that treats subreddits as separate populations. The usual way to answer it is a bipartite network of users and communities, *projected* onto the communities: two subreddits are linked when people comment in both.

The project began with a narrower, longitudinal question (the **submitted proposal**): *do cross-community bridge positions persist across quarters even when the people occupying them change?* Our first full pipeline (V1, §7) built that analysis on a cosine-similarity projection. On real data, the projection connected {pct(V1['2018Q1']['density'], 2)} of subreddit pairs. It produced only four communities and so only six possible bridge positions, all saturated. The bridge question could not be answered with that measurement lens. The final project therefore asks three questions that the data can support, and keeps the bridge idea as a measured connector role:

- **RQ1 (representation).** How much of the audience overlap between subreddits is explained by community size and user activity alone?
- **RQ2 (structure).** Which communities share *surprisingly* large audiences, and what communities and connectors do those relationships form?
- **RQ3 (change).** How stable are these relationships over time, and how do they respond when a crowd suddenly arrives or leaves?

The deliverable is an end-to-end, reproducible pipeline and an interactive application (the **Community Atlas**) through which an evaluator can explore the evidence.

---

## 2. Literature review

**Projections are dense by construction.** A one-mode projection of a bipartite network is a union of cliques: every user active in *k* communities adds a link between all *k* of them, and high-degree nodes share neighbours by chance (Saracco et al., 2017; Larremore et al., 2014). The same mechanism explains our 99.9%-dense V1 network. Olson and Neal (2015) met it on Reddit itself and extracted a subreddit "backbone" with the disparity filter of Serrano et al. (2009). That filter compares each edge with a per-node uniform null and ignores the bipartite origin of the weights. Coscia and Rossi (2019, preprint) show that the choice of projection and backbone changes substantive conclusions.

**Validating projections against a null model.** The Bipartite Configuration Model (Saracco et al., 2015) is a maximum-entropy random network that preserves, on average, every node's degree on both sides: here, each user's number of subreddits and each subreddit's number of commenters. Under it, the number of users shared by two communities follows a Poisson-binomial distribution, so each pair can be tested and the tests corrected for multiplicity with the Benjamini–Hochberg false discovery rate (Saracco et al., 2017). Neal, Domagalski and Sagan (2021) compare alternatives to the exact fixed-degree model and recommend this "stochastic degree sequence" approach with BiCM probabilities when exact sampling is impractical, as it is for {n(S['users_total'])} users. Cimini et al. (2022) show that different null models disagree at a fixed p-value but agree at matched density. This is why we report densities and run a sensitivity check rather than trusting one threshold. Applications to social media include validated projections of Twitter user networks (Becatti et al., 2019; Caldarelli et al., 2020). Waller and Anderson (2021) make the same conceptual move for Reddit at scale: communities are related when their user bases are "surprisingly similar" beyond chance.

**Communities, roles and time.** We detect communities with Leiden (Traag, Waltman & van Eck, 2019), which guarantees connected communities. Good, de Montjoye and Clauset (2010) show that modularity has many near-optimal partitions, so we report seed agreement and sensitivity rather than a single partition. A subreddit's connector role is measured with the participation coefficient of Guimerà and Amaral (2005). Communities and links are compared across time by Jaccard matching (Greene, Doyle & Cunningham, 2010). Text-free event studies of Reddit measure active users and newcomers around documented dates and mask archive outages (Horta Ribeiro et al., 2021). Crypto-community activity co-moves with prices during bubbles, without implying causation (Phillips & Gorse, 2018).

**Visualisation and storytelling.** The Atlas follows Shneiderman's (1996) "overview first, zoom and filter, details on demand". Its stories use the "martini glass" structure of Segel and Heer (2010): a short author-driven sequence that opens into free exploration. Node-link diagrams of dense graphs are hard to read (Ghoniem, Fekete & Castagliola, 2005), which is one more reason to show the validated network. Following Archambault, Purchase and Pinaud (2011), time comparisons are shown side by side by default. The force-directed layout is treated as an approximation in which distance is not literal (Jacomy et al., 2014).

**Data quality and ethics.** Pushshift-derived archives, which the Arctic Shift data repackages (Baumgartner et al., 2020), have bursty missing data; network analyses of such data are among the most exposed to it (Gaffney & Matias, 2018). Social-media samples are not populations, and platform design shapes what can be measured (Ruths & Pfeffer, 2014). Reddit research ethics stresses aggregation and care with sensitive communities (Proferes et al., 2021).

**Evidence matrix (selected sources).**

| Source | Contribution | Decision it informs |
|---|---|---|
| Saracco et al. (2015, 2017) | BiCM; Poisson-binomial test of shared neighbours with FDR | The edge definition |
| Neal et al. (2021); Cimini et al. (2022) | Comparison of null models; agreement at matched density | BiCM over exact sampling; report density and sensitivity |
| Larremore et al. (2014) | Projections lose information; bipartite SBM | Rejected direct SBM on {n(S['users_total'])} users as disproportionate |
| Serrano et al. (2009); Olson & Neal (2015) | Disparity-filter backbones, including on Reddit | V1 display baseline; Reddit precedent |
| Waller & Anderson (2021) | Reddit communities related by beyond-chance overlap | Supports observed ÷ expected |
| Traag et al. (2019); Good et al. (2010) | Leiden; degeneracy of modularity | Leiden, seed and sensitivity reporting |
| Guimerà & Amaral (2005) | Participation coefficient | Connector score |
| Greene et al. (2010) | Jaccard matching across snapshots | Link and community persistence |
| Shneiderman (1996); Segel & Heer (2010) | Overview → details; martini-glass stories | App structure and story mode |
| Archambault et al. (2011); Jacomy et al. (2014); Ghoniem et al. (2005) | Small multiples; layout caveats; dense-graph readability | Side-by-side periods; layout caption; no hairball as primary map |
| Gaffney & Matias (2018); Baumgartner et al. (2020) | Missing data in Pushshift-derived corpora; provenance | Counts as lower bounds; provenance statement |
| Horta Ribeiro et al. (2021); Phillips & Gorse (2018) | Text-free event metrics; crypto activity co-moves with price | Story D metrics and wording |
| Ruths & Pfeffer (2014); Proferes et al. (2021) | Population bias; Reddit research ethics | Scope wording; aggregate-only publication |

---

## 3. Data

**Source.** Public Reddit comments from the Arctic Shift archive, a re-packaging of Pushshift dumps hosted on Hugging Face (`open-index/arctic`), read remotely with DuckDB. Comments in this archive end in August 2022.

**Sampling frame.** {S['subreddits']} subreddits chosen by a fixed rule before any analysis: 25 in each of six topical categories (politics & news, hobby, support, finance, expertise, media) plus 20 front-page "gateway" hubs, each with at least 2,000 comments in every one of three calibration months (`frame.csv`, `FRAME_JUSTIFICATION.md`).

**Scope versus proposal.** The proposal planned roughly 150 subreddits over 2019–2025; verification showed comments are only available up to 2022-08, and the window was revised to 2018–2022. This bounded first study processed **{len(months)} months, {mlabel(months[0])} – {mlabel(months[-1])} ({', '.join(qlabel(q) for q in Q)})**. 2017 Q4 was added to the original three 2018 quarters so the window contains the December 2017 Bitcoin peak. The later years were not collected. All findings describe this sample and window, not Reddit as a whole.

**Collection and cleaning.** Usernames are replaced in the query by a salted SHA-256 hash; no text is kept, only author hash, subreddit, timestamp and a moderator flag. Every fetch asserts that all {S['subreddits']} subreddits are present (coverage: {', '.join(f"{qlabel(r['quarter'])} {r['status']}" for r in meta['coverage_report'])}). Cleaning keeps accounts with at least five comments in a quarter and removes accounts that are both very high-volume (≥ 2,000 comments) and active in at least half the frame (bots).

{cleaning_table()}

---

## 4. Methods

1. **Bipartite matrix.** For any period (the whole window, a quarter or a month), a binary matrix records which users commented in which subreddits. Duplicate records are collapsed; this matters, because unsummed duplicates inflate user degrees and break the model.
2. **Raw overlap (baseline).** Cosine similarity of commenter sets, as in V1.
3. **Expected overlap.** The BiCM probability *p(u, s)* that user *u* comments in subreddit *s*, fitted so every user keeps their number of subreddits and every subreddit its number of commenters (on average). Users with the same degree share parameters, so the fit has at most a few hundred unknowns. Expected shared commenters: *E(a, b) = Σ_u p(u, a) · p(u, b)*. **Affinity** = observed shared commenters ÷ *E(a, b)*.
4. **Validated ("surprising") links.** One-sided Poisson test of the observed count against *E(a, b)*, the reference implementation's default approximation, with Benjamini–Hochberg FDR at {pct(S['alpha'], 0)} over all {n(S['subreddits'] * (S['subreddits'] - 1) / 2)} pairs. The lower tail is tested the same way: a pair is marked as sharing *fewer* commenters than chance when its lower-tail test passes the same FDR and, as an effect-size floor, it shares at most half of its expected overlap with at least 20 expected (the "avoided" rule).
5. **Communities and roles.** Leiden (RBConfiguration, γ = 1) on log-affinity weights, best of 20 seeds, on the network pooled over all months. The resulting anchor partition gives stable colours across periods. Participation coefficient and within-community degree (Guimerà & Amaral, 2005) measure connector roles per quarter.
6. **Change over time.** Jaccard overlap of validated link sets between consecutive months and quarters, used as the "normal churn" baseline. Monthly affinity series for chosen pairs, weekly commenter counts and the share of newcomers.
7. **Validation.** (a) Unit tests: degree constraints, duplicates, empty communities, structureless data producing no false links, pure popularity producing no hub links, planted communities recovered. (b) Equivalence with the reference `bicm` package on real data. (c) Exact Poisson-binomial check near the cut-off. (d) A stricter threshold counting only users with ≥ {S['sensitivity_min_comments']} comments in a subreddit. (e) Artifact tests that recompute every story number from the published files.

**Validation results.** On a {n(CC['sample_users'])}-user sample of {qlabel(CC['quarter'])}, our implementation and `bicm` v{CC['bicm_version']} validate the identical set of {n(CC['validated_ours'])} links (overlap {CC['validated_jaccard']:.3f}); fitted probabilities differ by at most {CC['fit_max_abs_prob_difference']:.1e}. Exact Poisson-binomial p-values for the {CC['exact_poisson_binomial_pairs_checked']} pairs nearest the threshold would add {CC['exact_flips_gained']} links and remove {CC['exact_flips_lost']} ({pct(CC['exact_flips_share_of_validated'])} of validated links), so the approximation is slightly conservative. Under the stricter threshold, {pct(S['robust_share']['all'], 0)} of the whole-window links remain (quarters: {', '.join(pct(S['robust_share'][q], 0) for q in Q)}), and community assignments agree at ARI {S['anchor']['sensitivity_ari']}. Of the {pl_tests} automated tests, {pl_tests - 1} run in the standard environment and pass; the remaining one compares directly against the optional `bicm` package and passes when it is installed.

---

## 5. Results

Each result is reported as **observed → how measured → what it means → what we cannot conclude**.

### 5.1 What popularity hides (RQ1)

- **Observed.** Raw overlap links {pct(S['cosine_density']['all'], 2)} of pairs over the whole window ({', '.join(pct(S['cosine_density'][q], 2) for q in Q)} per quarter). {Am['hubs_in_top10']} of the ten communities with the largest total raw overlap are front-page hubs, and all ten sit in the front-page cluster ({', '.join('r/' + x for x in Am['top_by_cosine_strength'][:5])}, …). Among the ten closest neighbours of each topical subreddit, hubs make up **{pct(Am['hub_share_cosine'], 0)}** by raw overlap but **{pct(Am['hub_share_affinity'], 0)}** by affinity. Neighbours from the subreddit's own topical category rise from {pct(Am['same_category_cosine'], 0)} to {pct(Am['same_category_affinity'], 0)}. The validated network keeps {pct(S['validated_density']['all'])} of pairs over the whole window, {', '.join(pct(S['validated_density'][q]) for q in Q)} per quarter and {pct(min(S['validated_density'][m] for m in months))}–{pct(max(S['validated_density'][m] for m in months))} per month.
- **Example.** r/{Am['example']}'s closest raw neighbours are {raw_list}. Its strongest surprising overlaps are {adj_list}. r/{giant['a']} and r/{giant['b']} share {n(giant['shared'])} commenters, the largest shared audience of any pair that is never a surprising link, where {n(giant['expected'])} were expected ({giant['affinity']:.2f}×): in none of the {giant['periods_tested']} periods tested is it a surprising link. r/{Am['biggest']} ({n(Am['biggest_users'])} commenters, {pct(Am['biggest_share_of_commenters'], 0)} of everyone in the frame) has a median affinity of {Am['biggest_median_affinity']:.2f}× and falls short of expectation with {Am['biggest_below_expectation_partners']} of the other {S['subreddits'] - 1} communities; for a community that large the expected overlap is close to the maximum possible, so its affinity is bounded near {Am['biggest_affinity_ceiling_median']:.1f}× by construction. For {Am['zero_overlap_count']} of {S['subreddits']} subreddits (for example {', '.join('r/' + x for x in Am['zero_overlap_examples'][:3])}) the five closest neighbours by raw overlap and by affinity share no name at all.
- **Meaning.** Most of what a raw shared-audience map shows is community size. Controlling for size and user activity recovers topical relationships.
- **Cannot conclude.** Affinity measures co-commenting, not friendship, conversation or influence.

![Every pair sharing a commenter: grey within chance, coloured when surprising](screenshots/05_atlas_surprise.png)
![The adjusted Atlas](screenshots/03_atlas_adjusted.png)

### 5.2 Communities and connectors (RQ2)

The validated network pooled over all months has **{comm_phrase}**: weighted modularity {S['anchor']['weighted_modularity']}, mean agreement between 20 Leiden seeds ARI {S['anchor']['seed_ari']}. The communities found in each quarter agree with this anchor partition at ARI {', '.join(str(S['period_communities'][q]['ari_vs_anchor']) for q in Q)}. They partly follow the frame categories (ARI {S['category_ari_vs_anchor']}), with informative exceptions: r/Economics sits with politics, and media subreddits split between the front-page cluster and hobbies.

{community_table()}

**Connectors.** The participation coefficient is 0 when all of a subreddit's surprising links stay inside its own community and approaches 1 when they spread evenly across communities. Among subreddits with at least {Cm['min_degree']} links, the highest scores in every quarter belong to mid-sized topical communities{f", with one front-page hub among them (r/{hub_conn[0]})" if hub_conn else ""}:

{connectors_table()}

Front-page hubs average {Cm['hub_mean_participation']:.2f}, topical communities {Cm['topical_mean_participation']:.2f}; {Cm['note'][0].lower() + Cm['note'][1:] if Cm.get('note') else 'the difference is not tested'} Connector rankings are stable between quarters (Spearman ρ {', '.join(f"{v:.2f}" for v in Cm['rank_stability'].values())}).

**Sealed and porous clusters.** The share of a cluster's surprising links that leave it, compared with what a random rewiring that keeps every subreddit's number of links would give:

{outward_table()}

r/{gi['name']} is the opposite of a connector: all {gi['links_inside_bloc']} of its surprising links lie inside the {gi['bloc']} cluster; it is above expectation with {gi['above_expectation_inside_bloc']} of the other {gi['bloc_size'] - 1} members of that cluster and below expectation with {gi['below_expectation_outside_bloc']} of the {gi['outside_bloc_count']} communities outside it. Part of this is arithmetic: holding {pct(Am['biggest_share_of_commenters'], 0)} of all commenters, it cannot share much more than chance with anyone.

*Cannot conclude:* a connector shares unusually many commenters with several clusters; that is not evidence that information flows through it. The participation coefficient depends on the partition.

### 5.3 Neighbours and strangers (RQ2)

**{Bm['robust_cross_category_links']} links** join subreddits from different frame categories, excluding hubs, and are significant in every quarter under both thresholds. The strongest:

{links_table(Bm['top_links'])}

The two strongest pair a country's politics forum with the same country's personal-finance forum, which is consistent with shared nationality rather than topic organising these audiences. The control makes the point: the same personal-finance topic across the border (r/{ctrl['a']} – r/{ctrl['b']}) shares {n(ctrl['shared'])} commenters where {n(ctrl['expected'])} were expected ({ctrl['affinity']:.2f}×), fewer than chance in every quarter, and the national forums' ties to the US-default r/politics and r/personalfinance are modest by comparison ({'; '.join(f"r/{u['a']} – r/{u['b']} {u['affinity']:.2f}× ({pair_status(u)})" for u in country['to_us_default'])}). Only two same-country pairs exist in the frame, so this is consistent with these cases, not a general law.

{country_table()}

Links that also cross the detected communities include {', '.join(f"r/{x['a']} – r/{x['b']} (≥ {x['min_affinity']:.2f}×)" for x in cross[:6])}. **Audiences that keep apart.** The same test in the other direction finds strangers: {n(avoided_pairs) if avoided_pairs is not None else 'many'} pairs share fewer commenters than chance under the avoided rule (lower-tail FDR {pct(S['alpha'], 0)}, affinity ≤ 0.5, expected ≥ 20). The widest gulfs are not political. The five beauty, fashion and fibre-craft communities ({', '.join('r/' + x for x in Bm['beauty_craft'])}) share {Bm['blocks'][0]['affinity']:.2f}× of the expected overlap with the {Bm['blocks'][0]['with'].lower()} cluster and {Bm['blocks'][1]['affinity']:.2f}× with the {Bm['blocks'][1]['with'].lower()} cluster, in every quarter. Some communities keep apart from almost everyone: r/{iso['name']} shares fewer commenters than chance with {iso['below_chance_partners']} of {S['subreddits'] - 1} (the median community: {Bm['median_below_chance_partners']:.1f}).

{apart_table()}

**Political opponents are not strangers.** None of the {ideo['pairs']} pairs among {', '.join('r/' + x for x in ideo['subreddits'])} shares fewer commenters than chance; {ideo['validated']} of {ideo['pairs']} share more (weakest r/{ideo['weakest_pair'][0]} – r/{ideo['weakest_pair'][1]} at {ideo['min_affinity']:.2f}×, median {ideo['median_affinity']:.2f}×).

*Cannot conclude:* why audiences overlap or keep apart. Shared geography, profession or demographics are all possible, and without text we cannot tell them apart.

### 5.4 Stability, and what crowds change (RQ3)

**Stability.** Consecutive quarters share {', '.join(f"{v:.2f}" for v in qj.values())} of their validated links (Jaccard); consecutive months share {min(mj.values()):.2f}–{max(mj.values()):.2f}. Change smaller than that is normal churn.

**The crypto exodus: the trace in the counts.** r/Bitcoin's monthly commenters peak in {mlabel(Dm['peak_month']['Bitcoin'])}, the month Bitcoin's price peaked (17 Dec 2017); r/CryptoCurrency peaks a month later ({mlabel(Dm['peak_month']['CryptoCurrency'])}). From {mlabel(base)} to {mlabel(months[-1])}, {', '.join(f"r/{k} {v * 100:+.0f}%" for k, v in Dm['change_since_baseline'].items() if k in crypto_names)}, while r/investing changed {Dm['change_since_baseline']['investing'] * 100:+.0f}% and the whole frame {Dm['frame_change_since_baseline'] * 100:+.0f}%.

**The obvious reading, and the careful one.** r/{cp_key.replace('|', '–r/')} affinity was {cp[mi[base]]}× at the peak and **{cp[-1]}×** by {mlabel(months[-1])} ({cp2[-1]}× under the stricter threshold), which reads as if the people who stayed were far more tightly bound. The behavioural check says otherwise: the share of r/{cp_key.split('|')[0]} commenters who also posted in r/{cp_key.split('|')[1]} moved only from {pct(rate_ab[mi[base]], 0)} to {pct(rate_ab[-1], 0)}, the reverse share fell from {pct(rate_ba[mi[base]], 0)} to {pct(rate_ba[-1], 0)}, and raw overlap (cosine) fell from {cos_m[mi[base]]:.2f} to {cos_m[-1]:.2f}. The ratio rose because the expected overlap shrinks with the communities: affinity compares observed overlap with a size-dependent expectation, so when two communities lose most of their commenters the same cross-posting behaviour produces a much larger ratio.

**A crowd arriving: The Last Jedi.** {f"In {mlabel('2017-12')} (US release {sw['release']}) r/{sw['name']} had {n(sw['monthly_authors'][mi['2017-12']])} commenters, {sw['dec_over_nov']:.2f}× November, and {pct(sw['new_share_dec'], 0)} of them had not commented there earlier in the window. Its affinity with every fandom neighbour dipped that month ({', '.join(f'r/{p} {sw['partner_affinity'][p][mi['2017-11']]:.2f}× → {sw['partner_affinity'][p][mi['2017-12']]:.2f}×' for p in list(sw['partner_affinity'])[:3])}) and recovered in January: the same arithmetic in reverse." if sw else "Not computed in this build."}

**The Infinity War crowd.** *Avengers: Infinity War* opened in the US on 27 April 2018. r/marvelstudios went from a March median of {n(Dm['marvel_release_week']['march_median_weekly'])} weekly commenters to {n(Dm['marvel_release_week']['authors'])} in the release week. r/{mk.replace('|', '–r/')} affinity fell from {mv[mi['2018-01']]}× in January 2018 to {mv[mi['2018-04']]}× in April and recovered to {mv[-1]}× by {mlabel(months[-1])}, while the share of r/{mvl['pair'][0]} commenters also active in r/{mvl['pair'][1]} rose from {pct(mvl['cross_rate_ab'][mi['2018-01']], 0)} to {pct(mvl['cross_rate_ab'][mi['2018-04']], 0)}: both communities grew, the expected overlap grew faster, and the ratio fell although cross-posting did not.

**General tendency.** Across the {gt['n_subreddits']} communities with at least five stable, well-measured ties ({n(gt['n_stable_ties'])} ties), faster growth over the year went with a downward drift in affinity (Spearman ρ = {gt['spearman_growth_vs_affinity_trend']}) while raw overlap drifted up with growth (ρ = {gt['spearman_growth_vs_cosine_trend']}). Most of the "change" in affinity around a crowd is the expectation moving with size, not people changing where they comment.

- **Meaning.** Crowds leave a clear trace in the counts, and the share of commenters who cross between related communities is the right behavioural check. A changed affinity is not by itself a changed behaviour; the Atlas therefore shows the cross-posting share next to affinity in the crowd discovery.
- **Cannot conclude.** That the price crash or the films *caused* these changes. Event dates are external context and the patterns are temporal associations.

![Monthly commenters around the Bitcoin peak](screenshots/09_story_crowds_timeline.png)
![Affinity next to the cross-posting share for r/Bitcoin – r/CryptoCurrency](screenshots/11_story_crowds_after.png)

---

## 6. The application: the Community Atlas

The Atlas is a static web application (HTML/JavaScript with sigma.js, all libraries bundled) that reads only the aggregate JSON produced by `atlas/build_atlas.py`; nothing runs on a server, and the application says so. Every view is addressable by URL, so a view can be shared or cited. It is organised so that a visitor moves through four stages — discover, explore, understand, verify — without needing this report:

- **Start:** a scroll-driven opening that poses the question with two real pairs (one large but ordinary, one small but surprising) and then transforms one map in three steps: every pair sharing a commenter, the same map with pairs within chance greyed out, and the surprising links alone. The legend states what circle size, lines, colour and distance mean.
- **Guided tour:** a ten-step overlay that drives the real pages (map views, a profile, two discoveries, the technical walkthrough, the limits). It can be paused by navigating elsewhere and resumed from where it was left.
- **Discoveries:** four guided stories. Each step moves the map and highlights the relevant subreddits; the evidence and the caveats sit beside it; a closing step states the takeaway and offers actions to investigate the finding independently (compare the pair, open the profile, change the period).
- **Atlas:** search; period selector (whole window, quarters, months); three line views (surprising only, chance vs surprise, raw overlap); colour by detected community or frame category; community isolation; hover details; a panel for the selected subreddit with its strongest overlaps (observed vs expected), the pairs it shares *fewer* commenters with than chance, and what raw overlap would have shown; "back to overview".
- **Explore:** a profile for any subreddit: ranked surprising overlaps, raw-vs-adjusted neighbours, pairs below chance, connector role by quarter, weekly commenters and monthly affinity with its strongest neighbours.
- **Compare:** two subreddits (a three-way verdict — surprising, within chance, fewer than chance — with p-values, monthly affinity, per-quarter table, shared neighbours), or two periods (side-by-side maps with links that appeared and disappeared, against the churn baseline).
- **How it's made:** a nine-stage technical walkthrough fed by `pipeline.json`: input, transformation, output, purpose, a real example, the tests that guard the stage and what would go wrong without it. It includes the breadth histogram behind the hairball, a worked example of two real pairs with the breadth of their shared commenters, a toy BiCM example run through the real model, the test inventory, and artifact sizes and hashes. Badges separate what is precomputed, computed in the browser, and historical (V1).
- **Scope & limits:** sample and window, cleaning, validation, how the project evolved, the label the network corrected, privacy, and what can and cannot be concluded.

The existing Streamlit dashboard remains as the **Data & Pipeline Console** (coverage, cleaning audit, bot review). Design decisions are recorded in `docs/V2_DESIGN_DECISIONS.md`.

![The opening: raw overlap, then chance vs surprise, then the map](screenshots/02_start_raw.png)
![The guided tour driving the atlas](screenshots/06_tour_surprise.png)
![Subreddit drawer](screenshots/04_atlas_selected.png)
![Comparing two periods](screenshots/15_compare_periods.png)

---

## 7. How the project evolved

1. **Proposal.** Test whether bridge positions between communities persist while their occupants change, using a cosine projection, Leiden communities, participation-coefficient brokers and a turnover null model.
2. **V1 on real data** (tag `v1-baseline`). The cosine network linked {pct(V1['2018Q1']['density'], 2)} of pairs in 2018 Q1. Leiden found 4 communities, so only 6 bridge positions existed, all saturated by thousands of brokers. Pre-registered quality and sample-size gates failed, and all temporal results were labelled descriptive.
3. **Audit.** V1's reported community quality (Q = {V1['2018Q1']['stored_unweighted_q']}) was *unweighted* modularity: leidenalg's `.modularity` ignores edge weights. The same partitions have weighted modularity {V1['2018Q1']['weighted_q']}–{max(V1[q]['weighted_q'] for q in V1 if q.startswith('20'))} per quarter ({V1['anchor_pooled']['weighted_q'] if isinstance(V1.get('anchor_pooled'), dict) else V1.get('anchor_pooled')} pooled over the window) against a shuffled-label maximum near 0 (`v1_modularity_audit.json`). V1's communities were real but weak; the bridge design was limited by the representation.
4. **Re-representation.** Literature on bipartite projections pointed to null-model validation (§2). On real data, BiCM-validated links were {pct(min(S['validated_density'][q] for q in Q), 0)}–{pct(max(S['validated_density'][q] for q in Q), 0)} dense per quarter, stable over time, and reproduced exactly by the reference implementation.
5. **Final deliverable.** The Atlas keeps the bridge idea as the connector role and the original temporal interest in the crowd stories. **The submitted hypothesis is not answered here.** Testing whether bridge positions outlast their occupants would need link-level bridge positions on the validated network and a matched occupant-turnover null model, which remains future work.

---

## 8. Limitations and ethics

- **Sample and window.** {S['subreddits']} subreddits and {len(months)} months; overlaps with communities outside the frame are not observed. The frame's "gateway" stratum is large: front-page hubs hold most comments.
- **Commenters only.** Lurkers and voters are invisible. Comments deleted before archiving are missing, and Pushshift ingestion had outages (Gaffney & Matias, 2018), so counts are lower bounds.
- **No text.** Co-commenting is not conversation or influence; motives and topics cannot be inferred.
- **Statistical choices.** The test approximates the Poisson-binomial (slightly conservative); the FDR level and the activity threshold change details. The number of communities depends on thresholds (ARI {S['anchor']['sensitivity_ari']} under the stricter one).
- **Events.** Associations, not causal effects.
- **A size-dependent measure.** Affinity compares observed overlap with an expectation that scales with community size. For the largest communities the expectation is close to the maximum possible, so their affinity is bounded near 1 (r/{Am['biggest']}: about {Am['biggest_affinity_ceiling_median']:.1f}× at most); and when a community's size changes sharply, affinity moves even if cross-posting behaviour does not (§5.4).
- **Window length.** The default view pools all {len(months)} months. Pooled affinities run lower than quarterly ones (the expected overlap grows with pooled breadth) and pooled density higher ({pct(S['validated_density']['all'])} against {', '.join(pct(S['validated_density'][q]) for q in Q)} by quarter), so like must be compared with like; the discoveries quote quarters or months when they describe change.
- **Fewer-than-chance links.** The lower-tail test needs enough expected overlap to be informative; the avoided rule's floor (expected ≥ 20, affinity ≤ 0.5) means small pairs can never be marked, and the count depends on that floor.
- **Labels.** Frame categories come from a keyword rule and can be wrong{f": for {label_mismatch['count']} of {S['subreddits']} subreddits the category the network places them nearest to differs from the label (for example {', '.join(f'r/{x['name']}: {CAT[x['frame']]} → {CAT[x['network']]}' for x in label_mismatch['examples'][:3])})" if label_mismatch else ""}.{f" The network suggests r/{vig['name']} (labelled “{CAT[vig['label']]}”) is a smoked-food community: its strongest overlaps are {', '.join('r/' + x['name'] for x in vig['neighbours'][:3])}, and it peaks in {mlabel(vig['peak_month'])}." if vig else ""}
- **Ethics and privacy.** Data are public. Usernames are salted and hashed at collection, and the salt is never committed. Only subreddit-level aggregates are published, which an automated test checks. Mental-health communities appear only as aggregates. Earlier commits of this repository contain a bot-review file of 200 hashed account IDs from a prototype run; it is now untracked and ignored, and purging it from the remote history is recommended.

---

## 9. Conclusion

Raw shared-audience networks mostly measure size. Once size and user activity are accounted for, about one in seven subreddit pairs in our sample shares a surprisingly large audience. Those links form stable topical communities, reveal cross-topic neighbours (a nation's politics and personal-finance forums) and connector communities (r/Frugal, r/Economics, r/askscience), and the same test marks the audiences that keep apart. Crowds arriving and leaving are plainly visible in the counts, but most of the apparent change in affinity around them is the expectation moving with size: the cross-posting share, shown beside affinity in the Atlas, barely moves. The Community Atlas lets an evaluator verify each of these claims interactively. **Future work:** extend the window to 2019–2022 with the same pipeline; revisit bridge-occupant turnover with link-level bridge positions; add a reply-network layer (`parent_id` is available in the source) to separate co-presence from conversation.

---

## References

- Archambault, D., Purchase, H. C., & Pinaud, B. (2011). Animation, small multiples, and the effect of mental map preservation in dynamic graphs. *IEEE Transactions on Visualization and Computer Graphics, 17*(4), 539–552. https://doi.org/10.1109/TVCG.2010.78
- Baumgartner, J., Zannettou, S., Keegan, B., Squire, M., & Blackburn, J. (2020). The Pushshift Reddit dataset. *Proceedings of ICWSM, 14*, 830–839. https://doi.org/10.1609/icwsm.v14i1.7347
- Becatti, C., Caldarelli, G., Lambiotte, R., & Saracco, F. (2019). Extracting significant signal of news consumption from social networks: the case of Twitter in Italian political elections. *Palgrave Communications, 5*, 91. https://doi.org/10.1057/s41599-019-0300-3
- Caldarelli, G., De Nicola, R., Del Vigna, F., Petrocchi, M., & Saracco, F. (2020). The role of bot squads in the political propaganda on Twitter. *Communications Physics, 3*, 81. https://doi.org/10.1038/s42005-020-0340-4
- Cimini, G., Carra, A., Didomenicantonio, L., & Zaccaria, A. (2022). Meta-validation of bipartite network projections. *Communications Physics, 5*, 76. https://doi.org/10.1038/s42005-022-00856-9
- Coscia, M., & Rossi, L. (2019). The impact of projection and backboning on network topologies. *arXiv:1906.09081* (preprint).
- Gaffney, D., & Matias, J. N. (2018). Caveat emptor, computational social science: Large-scale missing data in a widely-published Reddit corpus. *PLoS ONE, 13*(7), e0200162. https://doi.org/10.1371/journal.pone.0200162
- Ghoniem, M., Fekete, J.-D., & Castagliola, P. (2005). On the readability of graphs using node-link and matrix-based representations. *Information Visualization, 4*(2), 114–135. https://doi.org/10.1057/palgrave.ivs.9500092
- Good, B. H., de Montjoye, Y.-A., & Clauset, A. (2010). Performance of modularity maximization in practical contexts. *Physical Review E, 81*, 046106. https://doi.org/10.1103/PhysRevE.81.046106
- Greene, D., Doyle, D., & Cunningham, P. (2010). Tracking the evolution of communities in dynamic social networks. *Proceedings of ASONAM 2010*, 176–183. https://doi.org/10.1109/ASONAM.2010.17
- Guimerà, R., & Amaral, L. A. N. (2005). Functional cartography of complex metabolic networks. *Nature, 433*, 895–900. https://doi.org/10.1038/nature03288
- Horta Ribeiro, M., Jhaver, S., Zannettou, S., Blackburn, J., Stringhini, G., De Cristofaro, E., & West, R. (2021). Do platform migrations compromise content moderation? Evidence from r/The_Donald and r/Incels. *Proceedings of the ACM on Human-Computer Interaction, 5*(CSCW2). https://doi.org/10.1145/3476057
- Jacomy, M., Venturini, T., Heymann, S., & Bastian, M. (2014). ForceAtlas2, a continuous graph layout algorithm for handy network visualization designed for the Gephi software. *PLoS ONE, 9*(6), e98679. https://doi.org/10.1371/journal.pone.0098679
- Larremore, D. B., Clauset, A., & Jacobs, A. Z. (2014). Efficiently inferring community structure in bipartite networks. *Physical Review E, 90*, 012805. https://doi.org/10.1103/PhysRevE.90.012805
- Neal, Z. P., Domagalski, R., & Sagan, B. (2021). Comparing alternatives to the fixed degree sequence model for extracting the backbone of bipartite projections. *Scientific Reports, 11*, 23929. https://doi.org/10.1038/s41598-021-03238-3
- Olson, R. S., & Neal, Z. P. (2015). Navigating the massive world of reddit: Using backbone networks to map user interests in social media. *PeerJ Computer Science, 1*, e4. https://doi.org/10.7717/peerj-cs.4
- Phillips, R. C., & Gorse, D. (2018). Cryptocurrency price drivers: Wavelet coherence analysis revisited. *PLoS ONE, 13*(4), e0195200. https://doi.org/10.1371/journal.pone.0195200
- Proferes, N., Jones, N., Gilbert, S., Fiesler, C., & Zimmer, M. (2021). Studying Reddit: A systematic overview of disciplines, approaches, methods, and ethics. *Social Media + Society, 7*(2). https://doi.org/10.1177/20563051211019004
- Ruths, D., & Pfeffer, J. (2014). Social media for large studies of behavior. *Science, 346*(6213), 1063–1064. https://doi.org/10.1126/science.346.6213.1063
- Saracco, F., Di Clemente, R., Gabrielli, A., & Squartini, T. (2015). Randomizing bipartite networks: the case of the World Trade Web. *Scientific Reports, 5*, 10595. https://doi.org/10.1038/srep10595
- Saracco, F., Straka, M. J., Di Clemente, R., Gabrielli, A., Caldarelli, G., & Squartini, T. (2017). Inferring monopartite projections of bipartite networks: an entropy-based approach. *New Journal of Physics, 19*, 053022. https://doi.org/10.1088/1367-2630/aa6b38
- Segel, E., & Heer, J. (2010). Narrative visualization: Telling stories with data. *IEEE Transactions on Visualization and Computer Graphics, 16*(6), 1139–1148. https://doi.org/10.1109/TVCG.2010.179
- Serrano, M. Á., Boguñá, M., & Vespignani, A. (2009). Extracting the multiscale backbone of complex weighted networks. *PNAS, 106*(16), 6483–6488. https://doi.org/10.1073/pnas.0808904106
- Shneiderman, B. (1996). The eyes have it: A task by data type taxonomy for information visualizations. *Proceedings of the IEEE Symposium on Visual Languages*, 336–343. https://doi.org/10.1109/VL.1996.545307
- Traag, V. A., Waltman, L., & van Eck, N. J. (2019). From Louvain to Leiden: guaranteeing well-connected communities. *Scientific Reports, 9*, 5233. https://doi.org/10.1038/s41598-019-41695-z
- Vallarano, N., Bruno, M., Marchese, E., Trapani, G., Saracco, F., Cimini, G., Zanon, M., & Squartini, T. (2021). Fast and scalable likelihood maximization for exponential random graph models with local constraints. *Scientific Reports, 11*. https://doi.org/10.1038/s41598-021-93830-4
- Waller, I., & Anderson, A. (2021). Quantifying social organization and political polarization in online platforms. *Nature, 600*, 264–268. https://doi.org/10.1038/s41586-021-04167-x

---

## Appendix A: where each headline number comes from

| Claim | Value | Artifact |
|---|---|---|
| Raw comments / retained | {n(tot_raw)} / {n(tot_clean)} | `data_curation/data/logs/cleaning_report.csv` |
| Distinct commenters | {n(S['users_total'])} | `atlas/web/data/meta.json` → `summary.users_total` |
| Raw-overlap density (all months) | {pct(S['cosine_density']['all'], 2)} | `meta.json` → `summary.cosine_density.all` |
| Validated density (all months / quarters) | {pct(S['validated_density']['all'])} / {', '.join(pct(S['validated_density'][q]) for q in Q)} | `meta.json` → `summary.validated_density` |
| Communities (all / major), weighted Q, seed ARI | {S['anchor']['communities']} / {S['anchor'].get('communities_major', '–')}, {S['anchor']['weighted_modularity']}, {S['anchor']['seed_ari']} | `meta.json` → `summary.anchor` |
| Largest shared audience, never surprising | r/{giant['a']} – r/{giant['b']}: {n(giant['shared'])} shared, {n(giant['expected'])} expected | `stories.json` → `popularity.metrics.giant_pair` |
| Pairs sharing fewer commenters than chance (avoided rule) | {n(avoided_pairs) if avoided_pairs is not None else '–'} | `pipeline.json` → `stages.validated.avoided_pairs`; per pair in `pairs_*.json` |
| Hub share of top-10 neighbours (raw / adjusted) | {pct(Am['hub_share_cosine'], 0)} / {pct(Am['hub_share_affinity'], 0)} | `stories.json` → `popularity.metrics` |
| Robust cross-category links | {Bm['robust_cross_category_links']} | `stories.json` → `neighbours.metrics` |
| Top connector participation | r/{Cm['connectors'][0]['name']} {Cm['connectors'][0]['participation_min']:.2f} | `stories.json` → `connectors.metrics`; `nodes.json` |
| r/{cp_key.replace('|', '–r/')} affinity ({mlabel(months[0])} / {mlabel(base)} / {mlabel(months[-1])}) | {cp[0]} / {cp[mi[base]]} / {cp[-1]} | `stories.json` → `crowds.metrics.crypto_pair_affinity`; recomputed by `tests/test_atlas_artifacts.py` |
| Cross-posting share r/{cp_key.split('|')[0]} → r/{cp_key.split('|')[1]} ({mlabel(base)} / {mlabel(months[-1])}) | {pct(rate_ab[mi[base]], 0)} / {pct(rate_ab[-1], 0)} | `stories.json` → `crowds.metrics.crypto_cross_rate_ab` |
| Growth vs affinity drift / vs raw-overlap drift (Spearman) | {gt['spearman_growth_vs_affinity_trend']} / {gt['spearman_growth_vs_cosine_trend']} | `stories.json` → `crowds.metrics.tendency` |
| Quarter-to-quarter link Jaccard | {', '.join(f"{v:.3f}" for v in qj.values())} | `meta.json` → `summary.quarter_edge_jaccard` |
| Reference cross-check | {CC['validated_ours']} = {CC['validated_reference']} links | `atlas/validation/bicm_crosscheck.json` |
| V1 stored vs weighted Q (2018 Q1) | {V1['2018Q1']['stored_unweighted_q']} vs {V1['2018Q1']['weighted_q']} | `data_curation/data/logs/v1_modularity_audit.json` |

## Appendix B: reproducing everything

```bash
pip install -r requirements.txt
python data_curation/run_pipeline.py --start 2017 10 --end 2018 9   # fetch + clean (needs a local salt; see README)
python atlas/build_atlas.py                                          # all Atlas data, stories and exports (~6–8 min)
python -m pytest tests/                                              # {pl_tests} tests (1 needs the optional bicm package)
python atlas/serve.py                                                # open the Atlas
python tools/build_docs.py --pdf                                     # this report
```

*Report generated {dt.date.today().isoformat()} from build {meta['generated_at']} (commit {meta['git_commit']}).*
"""

DEMO = f"""# Five-minute demo script

Start `python atlas/serve.py` (opens http://127.0.0.1:8000) before presenting. Each step lists the view, what to say, and the figure on screen; all figures come from the current build. The guided tour (top-right button) follows the same order if you prefer to let the application lead.

| Time | Do | Say |
|---|---|---|
| 0:00 | **Start** page; point at the two pair cards. | "Two communities share thousands of commenters. Is that a relationship? r/{Am['biggest']} and r/{Am['example']} share {n(lead_big['shared'])} people, {lead_big.get('affinity', 0):.2f}× what chance predicts: nothing surprising. r/{lead['a']} and r/{lead['b']} share {n(lead['shared_all'])} where {n(lead['expected_all'])} were expected: {fmtx(lead['shared_all'] / lead['expected_all'])} chance over the year, at least {fmtx(lead['min_affinity'])} in every quarter." |
| 0:40 | Scroll: the map turns from the hairball into grey-vs-coloured, then into the surprising links. | "Link every pair that shares a commenter and {pct(S['cosine_density']['all'], 2)} of pairs connect. Ask what chance would produce, and most lines go grey. Keep the surprising ones: {pct(S['validated_density']['all'])} of pairs, {comm_phrase}." |
| 1:30 | **Discoveries → Neighbours and strangers**, step 1, then step 4 (audiences that keep apart). | "A nation's politics and personal-finance forums share several times more people than chance, while the same money topic across the border shares a quarter of what chance predicts. The same test finds strangers: r/linux and r/MakeupAddiction share {Bm['lowest_pairs'][0]['affinity']:.3f}× of the expected overlap." |
| 2:15 | **Discoveries → When crowds arrive and leave**: timeline, then the peak and the September map. | "r/Bitcoin's commenters fell {abs(Dm['change_since_baseline']['Bitcoin']) * 100:.0f}% after the December 2017 peak while the frame grew {Dm['frame_change_since_baseline'] * 100:.0f}%. Its affinity with r/CryptoCurrency looks like it tripled, {cp[mi[base]]}× to {cp[-1]}×, but the share of r/Bitcoin commenters who also post there moved only from {pct(rate_ab[mi[base]], 0)} to {pct(rate_ab[-1], 0)}: the ratio rose because the expectation shrank with the communities. The crowds arriving for The Last Jedi and Infinity War show the same arithmetic in reverse. Associations with dated events, not causes." |
| 3:00 | **Atlas**: search r/{Am['example']}; show the drawer; switch to "Chance vs surprise". | "By raw overlap its neighbours are hubs. Adjusted, they are {adj_list.split(', r/')[0]} and r/{Am['example_affinity_neighbours'][1]['name']}. Every number is observed ÷ expected shared commenters." |
| 3:45 | **How it's made** → stage 5 (Expected) and stage 6 (Surprising links). | "A shuffled Reddit where everyone keeps their breadth and every community its size gives an expected overlap per pair; a Poisson test with a 1% false-discovery rate keeps the surprising ones. Our code matches the published `bicm` package link for link, and {pl_tests} automated tests recompute the story numbers." |
| 4:30 | **Scope & limits** → "What we can and cannot conclude". | "One sample of {S['subreddits']} subreddits, {len(months)} months, comments only, no text. We can show which audiences overlap more or less than chance and how that changed; we cannot show why, or that any event caused it." |

**If something fails live:** every view is a URL, and `docs/screenshots/` holds a capture of each step.
"""


def render_html(md_text: str) -> str:
    import markdown
    body = markdown.markdown(md_text.split("---\n", 2)[2] if md_text.startswith("---") else md_text,
                             extensions=["tables", "fenced_code", "toc"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Beyond the Hairball: The Reddit Community Atlas</title>
<style>
body{{font:11pt/1.55 "Segoe UI",system-ui,sans-serif;color:#1b1b1a;max-width:860px;margin:32px auto;padding:0 24px}}
h1{{font-size:24pt;letter-spacing:-.01em;margin:0 0 6px}} h2{{font-size:15pt;margin:28px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px}}
h3{{font-size:12.5pt;margin:20px 0 6px}} table{{border-collapse:collapse;width:100%;font-size:9.5pt;margin:10px 0}}
th,td{{border-bottom:1px solid #e3e2dc;padding:5px 6px;text-align:left;vertical-align:top}} th{{background:#f4f3ef}}
img{{max-width:100%;border:1px solid #ddd;border-radius:6px;margin:8px 0}} code{{background:#f4f3ef;padding:1px 4px;border-radius:3px;font-size:9.5pt}}
pre{{background:#f4f3ef;padding:10px;border-radius:6px;overflow:auto}} hr{{border:0;border-top:1px solid #e3e2dc;margin:20px 0}}
@media print{{h2{{page-break-after:avoid}} img,table{{page-break-inside:avoid}}}}
</style></head><body>{body}</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args()
    DOCS.mkdir(exist_ok=True)
    (DOCS / "FINAL_REPORT.md").write_text(REPORT, encoding="utf-8")
    (DOCS / "DEMO_SCRIPT.md").write_text(DEMO, encoding="utf-8")
    html = DOCS / "FINAL_REPORT.html"
    html.write_text(render_html(REPORT), encoding="utf-8")
    print("wrote docs/FINAL_REPORT.md, docs/FINAL_REPORT.html, docs/DEMO_SCRIPT.md")
    if args.pdf:
        import shutil
        from capture_screens import find_browser
        prof = tempfile.mkdtemp(prefix="atlas-pdf-")
        subprocess.run([find_browser(), "--headless=new", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                        f"--print-to-pdf={DOCS / 'FINAL_REPORT.pdf'}", html.resolve().as_uri()], capture_output=True, timeout=180)
        shutil.rmtree(prof, ignore_errors=True)
        print("wrote docs/FINAL_REPORT.pdf" if (DOCS / "FINAL_REPORT.pdf").exists() else "PDF rendering failed")


if __name__ == "__main__":
    main()
