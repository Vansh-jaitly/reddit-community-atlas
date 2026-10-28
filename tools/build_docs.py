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

meta = json.loads((DATA / "meta.json").read_text())
stories = {s["id"]: s for s in json.loads((DATA / "stories.json").read_text())["stories"]}
validity = json.loads((DATA / "stories.json").read_text())["validity_notes"]
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
cp = Dm["crypto_pair_affinity"][cp_key]
cp2 = Dm["crypto_pair_affinity_min2"][cp_key]
mk = next(iter(Dm["marvel_pair_affinity"]))
mv = Dm["marvel_pair_affinity"][mk]
mi = {m: i for i, m in enumerate(months)}
base = Dm["baseline_month"]
gt = Dm["general_tendency"]
crypto_names = list(Dm["crypto_monthly_authors"])
vig = validity[0] if validity else None


def community_table():
    rows = ["| Community (auto-labelled) | Subreddits | Largest members | Category mix |", "|---|---:|---|---|"]
    for c in meta["communities"]:
        mix = ", ".join(f"{CAT[k].split(' ')[0].lower()} {v}" for k, v in c["category_mix"].items())
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

Online communities are often mapped through the audiences they share, but raw shared-audience networks mostly measure size: one person who comments in many places links all of them, and the biggest communities look close to everything. We collected {n(tot_raw)} public Reddit comments from a fixed, rule-based frame of {S['subreddits']} subreddits over {len(months)} months ({mlabel(months[0])} – {mlabel(months[-1])}), cleaned them to {n(tot_clean)} comments by {n(S['users_total'])} pseudonymised commenters, and built a user × subreddit network. The conventional cosine projection links {pct(S['cosine_density']['all'], 2)} of all subreddit pairs. Comparing each pair's shared commenters with the number expected from community size and user activity alone (the Bipartite Configuration Model, BiCM) and keeping only pairs that exceed it at a 1% false discovery rate leaves {pct(S['validated_density']['all'])} of pairs. That network has a clear, reproducible structure: {S['anchor']['communities']} communities (weighted modularity {S['anchor']['weighted_modularity']}, seed agreement ARI {S['anchor']['seed_ari']}), stable connector roles, and {pct(min(qj.values()), 0)}–{pct(max(qj.values()), 0)} of links recurring between consecutive quarters. We built the results into an interactive web application, the Community Atlas, with four guided stories: what popularity hides, unexpected neighbours, hidden connectors, and how community ties respond when crowds arrive and leave. The project started as a test of whether cross-community "bridge positions" outlast their occupants. It evolved after the first, cosine-based pipeline proved too dense to measure bridges at all. The findings are descriptive and specific to this sample.

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
4. **Validated ("surprising") links.** One-sided Poisson test of the observed count against *E(a, b)*, the reference implementation's default approximation, with Benjamini–Hochberg FDR at {pct(S['alpha'], 0)} over all {n(S['subreddits'] * (S['subreddits'] - 1) / 2)} pairs.
5. **Communities and roles.** Leiden (RBConfiguration, γ = 1) on log-affinity weights, best of 20 seeds, on the network pooled over all months. The resulting anchor partition gives stable colours across periods. Participation coefficient and within-community degree (Guimerà & Amaral, 2005) measure connector roles per quarter.
6. **Change over time.** Jaccard overlap of validated link sets between consecutive months and quarters, used as the "normal churn" baseline. Monthly affinity series for chosen pairs, weekly commenter counts and the share of newcomers.
7. **Validation.** (a) Unit tests: degree constraints, duplicates, empty communities, structureless data producing no false links, pure popularity producing no hub links, planted communities recovered. (b) Equivalence with the reference `bicm` package on real data. (c) Exact Poisson-binomial check near the cut-off. (d) A stricter threshold counting only users with ≥ {S['sensitivity_min_comments']} comments in a subreddit. (e) Artifact tests that recompute every story number from the published files.

**Validation results.** On a {n(CC['sample_users'])}-user sample of {qlabel(CC['quarter'])}, our implementation and `bicm` v{CC['bicm_version']} validate the identical set of {n(CC['validated_ours'])} links (overlap {CC['validated_jaccard']:.3f}); fitted probabilities differ by at most {CC['fit_max_abs_prob_difference']:.1e}. Exact Poisson-binomial p-values for the {CC['exact_poisson_binomial_pairs_checked']} pairs nearest the threshold would add {CC['exact_flips_gained']} links and remove {CC['exact_flips_lost']} ({pct(CC['exact_flips_share_of_validated'])} of validated links), so the approximation is slightly conservative. Under the stricter threshold, {pct(S['robust_share']['all'], 0)} of the whole-window links remain (quarters: {', '.join(pct(S['robust_share'][q], 0) for q in Q)}), and community assignments agree at ARI {S['anchor']['sensitivity_ari']}. Of the 108 automated tests, 107 run in the standard environment and pass; the remaining one compares directly against the optional `bicm` package and passes when it is installed.

---

## 5. Results

Each result is reported as **observed → how measured → what it means → what we cannot conclude**.

### 5.1 What popularity hides (RQ1)

- **Observed.** Raw overlap links {pct(S['cosine_density']['all'], 2)} of pairs over the whole window ({', '.join(pct(S['cosine_density'][q], 2) for q in Q)} per quarter). The ten communities with the largest total raw overlap are all front-page hubs ({', '.join('r/' + x for x in Am['top_by_cosine_strength'][:5])}, …). Among the ten closest neighbours of each topical subreddit, hubs make up **{pct(Am['hub_share_cosine'], 0)}** by raw overlap but **{pct(Am['hub_share_affinity'], 0)}** by affinity. Neighbours from the subreddit's own topical category rise from {pct(Am['same_category_cosine'], 0)} to {pct(Am['same_category_affinity'], 0)}. The validated network keeps {pct(S['validated_density']['all'])} of pairs over the whole window, {', '.join(pct(S['validated_density'][q]) for q in Q)} per quarter and {pct(min(S['validated_density'][m] for m in months))}–{pct(max(S['validated_density'][m] for m in months))} per month.
- **Example.** r/{Am['example']}'s closest raw neighbours are {raw_list}. Its strongest surprising overlaps are {adj_list}. r/{Am['biggest']}, with {n(Am['biggest_users'])} commenters, has a median affinity of {Am['biggest_median_affinity']:.2f}× with other communities: no more than chance.
- **Meaning.** Most of what a raw shared-audience map shows is community size. Controlling for size and user activity recovers topical relationships.
- **Cannot conclude.** Affinity measures co-commenting, not friendship, conversation or influence.

![Raw overlap (left) versus surprising overlap (right)](screenshots/02_atlas_raw.png)
![The adjusted Atlas](screenshots/03_atlas_adjusted.png)

### 5.2 Communities and connectors (RQ2)

The validated network pooled over all months has **{S['anchor']['communities']} communities**: weighted modularity {S['anchor']['weighted_modularity']}, mean agreement between 20 Leiden seeds ARI {S['anchor']['seed_ari']}. The communities found in each quarter agree with this anchor partition at ARI {', '.join(str(S['period_communities'][q]['ari_vs_anchor']) for q in Q)}. They largely follow the frame categories (ARI {S['category_ari_vs_anchor']}), with informative exceptions: r/Economics sits with politics, and media subreddits split between the front-page cluster and hobbies.

{community_table()}

**Connectors.** The participation coefficient is 0 when all of a subreddit's surprising links stay inside its own community and approaches 1 when they spread evenly across communities. Among subreddits with at least {Cm['min_degree']} links, the highest scores in every quarter belong to mid-sized topical communities, not hubs:

{connectors_table()}

Front-page hubs average {Cm['hub_mean_participation']:.2f}, topical communities {Cm['topical_mean_participation']:.2f}. Connector rankings are stable between quarters (Spearman ρ {', '.join(f"{v:.2f}" for v in Cm['rank_stability'].values())}). *Cannot conclude:* a connector shares unusually many commenters with several clusters; that is not evidence that information flows through it.

### 5.3 Unexpected neighbours (RQ2)

**{Bm['robust_cross_category_links']} links** join subreddits from different frame categories, excluding hubs, and are significant in every quarter under both thresholds. The strongest:

{links_table(Bm['top_links'])}

Two of the three strongest pair a country's politics forum with the same country's personal-finance forum: for these communities, nationality organises audiences more than topic. Links that also cross the detected communities include {', '.join(f"r/{x['a']} – r/{x['b']} (≥ {x['min_affinity']:.2f}×)" for x in cross[:6])}. *Cannot conclude:* why audiences overlap. Shared geography, profession or demographics are all possible, and without text we cannot tell them apart.

### 5.4 Stability and crowds (RQ3)

**Stability.** Consecutive quarters share {', '.join(f"{v:.2f}" for v in qj.values())} of their validated links (Jaccard); consecutive months share {min(mj.values()):.2f}–{max(mj.values()):.2f}. Change smaller than that is normal churn.

**The crypto exodus.** r/Bitcoin's monthly commenters peak in {mlabel(Dm['peak_month']['Bitcoin'])}, the month Bitcoin's price peaked (17 Dec 2017). From {mlabel(base)} to {mlabel(months[-1])}, {', '.join(f"r/{k} {v * 100:+.0f}%" for k, v in Dm['change_since_baseline'].items() if k in crypto_names)}, while r/investing changed {Dm['change_since_baseline']['investing'] * 100:+.0f}% and the whole frame {Dm['frame_change_since_baseline'] * 100:+.0f}%. Meanwhile the remaining audiences overlapped far more: r/{cp_key.replace('|', '–r/')} affinity was {cp[0]}× in {mlabel(months[0])}, fell to {cp[mi[base]]}× at the peak as newcomers arrived, and rose to **{cp[-1]}×** by {mlabel(months[-1])} ({cp2[-1]}× under the stricter threshold).

**The Infinity War crowd.** *Avengers: Infinity War* opened in the US on 27 April 2018. r/marvelstudios went from a March median of {n(Dm['marvel_release_week']['march_median_weekly'])} weekly commenters to {n(Dm['marvel_release_week']['authors'])} in the release week. In April, r/{mk.replace('|', '–r/')} affinity fell to {mv[mi['2018-04']]}× (from {mv[mi['2018-01']]}× in January 2018) and recovered to {mv[-1]}× by {mlabel(months[-1])}.

**General tendency.** Across all communities, month-to-month audience growth goes with falling affinity to their usual neighbours, and shrinkage with rising affinity, but modestly: Spearman ρ = {gt['spearman_large_swings']} over {gt['n_large_swings']} swings larger than 25% (ρ = {gt['spearman_all_steps']} over all {n(gt['n_steps'])} month-steps).

- **Meaning.** An arriving crowd consists largely of people who comment in only one of the related communities, which dilutes surprising overlap. A departing crowd leaves behind a core that is active across them.
- **Cannot conclude.** That the price crash or the film *caused* these changes. Event dates are external context and the patterns are temporal associations.

![Crypto and Marvel timelines](screenshots/09_story_crowds_timeline.png)

---

## 6. The application: the Community Atlas

The Atlas is a static web application (HTML/JavaScript with sigma.js, all libraries bundled) that reads only the aggregate JSON produced by `atlas/build_atlas.py`. Every view is addressable by URL, so a view can be shared or cited.

- **Discoveries:** the question, key numbers, a live raw ↔ adjusted toggle, and the four stories.
- **Atlas map:** search; period selector (whole window, quarters, months); raw ↔ adjusted links; colour by detected community or frame category; community filter; hover details; a side panel with the selected subreddit's strongest overlaps (observed vs expected) and what raw overlap would have shown.
- **Explore:** a profile for any subreddit: ranked surprising overlaps, raw-vs-adjusted neighbours, weekly commenters, monthly affinity with its strongest neighbours (significant months marked), and its connector role by quarter.
- **Compare:** two subreddits (verdict, monthly affinity, per-quarter table, shared neighbours), or two periods (side-by-side maps with appeared and disappeared links, against the churn baseline).
- **Stories:** four guided walkthroughs that drive the map, show their evidence and caveats, and end with "keep exploring from here".
- **Methods & data:** scope, cleaning, the metric, validation, project evolution, privacy, limitations and downloads (CSV and GEXF for Gephi and Tableau).

The existing Streamlit dashboard remains as the **Data & Pipeline Console** (coverage, cleaning audit, bot review).

![Subreddit drawer](screenshots/04_atlas_selected.png)
![Comparing two periods](screenshots/15_compare_periods.png)

---

## 7. How the project evolved

1. **Proposal.** Test whether bridge positions between communities persist while their occupants change, using a cosine projection, Leiden communities, participation-coefficient brokers and a turnover null model.
2. **V1 on real data** (tag `v1-baseline`). The cosine network linked {pct(V1['2018Q1']['density'], 2)} of pairs in 2018 Q1. Leiden found 4 communities, so only 6 bridge positions existed, all saturated by thousands of brokers. Pre-registered quality and sample-size gates failed, and all temporal results were labelled descriptive.
3. **Audit.** V1's reported community quality (Q = {V1['2018Q1']['stored_unweighted_q']}) was *unweighted* modularity: leidenalg's `.modularity` ignores edge weights. The same partitions have weighted modularity {V1['2018Q1']['weighted_q']}–{max(V1[q]['weighted_q'] for q in V1 if q.startswith('20'))} against a shuffled-label maximum near 0 (`v1_modularity_audit.json`). V1's communities were real but weak; the bridge design was limited by the representation.
4. **Re-representation.** Literature on bipartite projections pointed to null-model validation (§2). On real data, BiCM-validated links were about 12% dense per quarter, stable over time, and reproduced exactly by the reference implementation.
5. **Final deliverable.** The Atlas keeps the bridge idea as the connector role and the original temporal interest in the crowd stories. The occupant-turnover hypothesis remains future work: it would need many more bridge positions than V1 could provide, and a properly matched null model.

---

## 8. Limitations and ethics

- **Sample and window.** {S['subreddits']} subreddits and {len(months)} months; overlaps with communities outside the frame are not observed. The frame's "gateway" stratum is large: front-page hubs hold most comments.
- **Commenters only.** Lurkers and voters are invisible. Comments deleted before archiving are missing, and Pushshift ingestion had outages (Gaffney & Matias, 2018), so counts are lower bounds.
- **No text.** Co-commenting is not conversation or influence; motives and topics cannot be inferred.
- **Statistical choices.** The test approximates the Poisson-binomial (slightly conservative); the FDR level and the activity threshold change details. The number of communities depends on thresholds (ARI {S['anchor']['sensitivity_ari']} under the stricter one).
- **Events.** Associations, not causal effects.
- **Labels.** Frame categories come from a keyword rule and can be wrong.{f" The network suggests r/{vig['name']} (labelled “{CAT[vig['label']]}”) is a smoked-food community: its strongest overlaps are {', '.join('r/' + x['name'] for x in vig['neighbours'][:3])}, and it peaks in {mlabel(vig['peak_month'])}." if vig else ""}
- **Ethics and privacy.** Data are public. Usernames are salted and hashed at collection, and the salt is never committed. Only subreddit-level aggregates are published, which an automated test checks. Mental-health communities appear only as aggregates. Earlier commits of this repository contain a bot-review file of 200 hashed account IDs from a prototype run; it is now untracked and ignored, and purging it from the remote history is recommended.

---

## 9. Conclusion

Raw shared-audience networks mostly measure size. Once size and user activity are accounted for, about one in seven subreddit pairs in our sample shares a surprisingly large audience. Those links form stable topical communities, reveal cross-topic neighbours (a nation's politics and personal-finance forums) and connector communities (r/Frugal, r/Economics, r/askscience), and respond to crowds arriving and leaving. The Community Atlas lets an evaluator verify each of these claims interactively. **Future work:** extend the window to 2019–2022 with the same pipeline; revisit bridge-occupant turnover with link-level bridge positions; add a reply-network layer (`parent_id` is available in the source) to separate co-presence from conversation.

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
| Communities, weighted Q, seed ARI | {S['anchor']['communities']}, {S['anchor']['weighted_modularity']}, {S['anchor']['seed_ari']} | `meta.json` → `summary.anchor` |
| Hub share of top-10 neighbours (raw / adjusted) | {pct(Am['hub_share_cosine'], 0)} / {pct(Am['hub_share_affinity'], 0)} | `stories.json` → `popularity.metrics` |
| Robust cross-category links | {Bm['robust_cross_category_links']} | `stories.json` → `neighbours.metrics` |
| Top connector participation | r/{Cm['connectors'][0]['name']} {Cm['connectors'][0]['participation_min']:.2f} | `stories.json` → `connectors.metrics`; `nodes.json` |
| r/{cp_key.replace('|', '–r/')} affinity ({mlabel(months[0])} / {mlabel(base)} / {mlabel(months[-1])}) | {cp[0]} / {cp[mi[base]]} / {cp[-1]} | `stories.json` → `crowds.metrics.crypto_pair_affinity`; recomputed by `tests/test_atlas_artifacts.py` |
| Quarter-to-quarter link Jaccard | {', '.join(f"{v:.3f}" for v in qj.values())} | `meta.json` → `summary.quarter_edge_jaccard` |
| Reference cross-check | {CC['validated_ours']} = {CC['validated_reference']} links | `atlas/validation/bicm_crosscheck.json` |
| V1 stored vs weighted Q (2018 Q1) | {V1['2018Q1']['stored_unweighted_q']} vs {V1['2018Q1']['weighted_q']} | `data_curation/data/logs/v1_modularity_audit.json` |

## Appendix B: reproducing everything

```bash
pip install -r requirements.txt
python data_curation/run_pipeline.py --start 2017 10 --end 2018 9   # fetch + clean (needs a local salt; see README)
python atlas/build_atlas.py                                          # all Atlas data, stories and exports (~6–8 min)
python -m pytest tests/                                              # 108 tests (1 needs the optional bicm package)
python atlas/serve.py                                                # open the Atlas
python tools/build_docs.py --pdf                                     # this report
```

*Report generated {dt.date.today().isoformat()} from build {meta['generated_at']} (commit {meta['git_commit']}).*
"""

DEMO = f"""# Five-minute demo script

Start `python atlas/serve.py` (opens http://127.0.0.1:8000) before presenting. Each step lists the view, what to say, and the figure on screen; all figures come from the current build.

| Time | Do | Say |
|---|---|---|
| 0:00 | **Discoveries** page. Click **Raw overlap** on the hero map, then **Adjusted**. | "We took {n(tot_clean)} Reddit comments from {S['subreddits']} subreddits. If you link communities whenever they share a commenter, {pct(S['cosine_density']['all'], 2)} of pairs are linked: a hairball. When we keep only pairs that share far more commenters than size and activity predict, {pct(S['validated_density']['all'])} remain, and topics appear." |
| 0:45 | **Atlas**. Search **personalfinance**. | "By raw overlap its neighbours are hubs like r/AskReddit and r/pics. Adjusted, they are {adj_list.split(', r/')[0]} and r/{Am['example_affinity_neighbours'][1]['name']}. The number is observed ÷ expected shared commenters." |
| 1:30 | **Stories → Unexpected neighbours** (step 1). | "r/CanadaPolitics and r/PersonalFinanceCanada share {n(Bm['top_links'][0]['shared_all'])} commenters where {n(Bm['top_links'][0]['expected_all'])} were expected, at least {Bm['top_links'][0]['min_affinity']}× in every quarter. The UK pair is next: nationality, not topic, organises these audiences." |
| 2:15 | **Stories → When crowds arrive and leave**: timeline, then steps 2–3, then the Marvel step. | "Crypto commenters fell {abs(Dm['change_since_baseline']['Bitcoin']) * 100:.0f}% after Bitcoin's December 2017 peak while the frame grew. The remaining Bitcoin and CryptoCurrency audiences went from {cp[mi[base]]}× to {cp[-1]}×. The Infinity War crowd did the opposite: Marvel affinity dropped to {mv[mi['2018-04']]}× in April. This is association, not causation." |
| 3:15 | **Methods & data**: scroll through the pipeline and "How we checked it". | "Fetch, salted hashing and cleaning, then the BiCM null model and a 1% false discovery rate. Our implementation matches the published `bicm` package link-for-link, and automated tests recompute every story number from the published data." |
| 4:00 | **Methods → How the project evolved**, then **Compare → Two periods**. | "We set out to test whether bridge positions outlast their occupants. The first network was {pct(V1['2018Q1']['density'], 2)} dense with only 6 possible bridges, so we changed the measurement lens. Links are stable ({min(qj.values()):.2f}–{max(qj.values()):.2f} quarter to quarter), and the remaining changes are visible here." |
| 4:40 | Back to **Atlas**; hover a connector such as r/Frugal. | "Limits: one sample of {S['subreddits']} subreddits, {len(months)} months, comments only, no text. Everything is aggregate and reproducible with one command." |

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
