# CONTEXT PACK FOR GPT — Reddit Bridge Network Analysis

Purpose: everything another model needs to generate slides (PPTX) or a
written report from this project — the story, all verified numbers, the
literature base, the figure inventory with plot recipes, and the language
rules. No repository code is included; only research content.

Project: **"Beyond the Hairball: Measuring Cross-Community Bridges
in Reddit"** — longitudinal network analysis, 2018 Q1–Q3, 170 subreddits.
Status of ALL quantitative results below: **descriptive only; longitudinal
inference was blocked by prespecified failure gates.** Never present them
as confirmatory findings.

---

## 1. RESEARCH STORY (narrative arc for slides/report)

1. QUESTION: do cross-community bridge positions persist even when the
   people occupying them change? (Structure vs staffing, measured separately.)
2. Built a large real dataset: 170 subreddits × 3 quarters, 171.6M comments.
3. Modeled audience overlap: shared users → cosine similarity → subreddit
   network → Leiden communities → participation-coefficient brokers →
   bridge positions → temporal comparison with null baselines.
4. TWIST: the projection is 99.85% dense — a near-complete graph.
5. Communities: reproducible across seeds (ARI 0.88–0.94) but quality
   Q ≤ 0 at every tested resolution → validity gate failed.
6. Bridges: 6/6 pairs bridged with ~4,000 occupants each → saturated,
   not selective.
7. Refused to force the hypothesis: gates demoted everything to
   descriptive-only. No pooled headline reported.
8. Lesson: the pipeline worked; the measurement lens did not.
9. Next question: how to separate meaningful co-occurrence from generic,
   degree-driven overlap? (Validated bipartite projection; bipartite
   community detection.)

Central phrase: **"Stable structure? Or a hairball created by the
measurement lens?"**
Correct framing: **"The original representation was not discriminative
enough to support the intended bridge inference."**
NEVER: "hypothesis disproven", "Reddit has no bridges/structure",
"null proves turnover", "statistically significant" (for gated results).

---

## 2. VERIFIED NUMBERS (use exactly these)

### Data scale (source: cleaning_report.csv)
| quarter | subreddits | raw comments | clean comments | retention % |
|---|---|---|---|---|
| 2018Q1 | 170 | 55,248,128 | 52,118,250 | 94.3 |
| 2018Q2 | 170 | 57,301,138 | 54,002,756 | 94.2 |
| 2018Q3 | 170 | 59,053,604 | 55,570,837 | 94.1 |
| TOTAL | 170 | 171,602,870 | 161,691,843 | 94.22 |

Users raw→clean: Q1 2,919,421→1,215,022; Q2 3,069,238→1,279,269;
Q3 3,248,860→1,339,394. Hard bots removed: 5, 5, 0. Manual review:
200 flagged/quarter, 0 verdicts recorded. Frame coverage 170/170 all
quarters. Cleaning rules frozen: min 5 comments + 1 subreddit/quarter;
bot = ≥2000 comments AND ≥50% frame breadth.

### Network (source: network_results.json, Q1)
- Nodes 170, edges 14,343 / 14,365 possible = **99.85% dense**.
- Backbone (Serrano α=0.3, display only): 5,981 edges (Q1).

### Communities (source: network_results.json)
| quarter | communities | modularity Q | seed ARI | match rate / coverage |
|---|---|---|---|---|
| pooled anchor | 4 | −0.0043 | 0.94 | — |
| 2018Q1 | 4 | −0.0041 | 0.897 | 100% / 100% |
| 2018Q2 | 4 | −0.0043 | 0.882 | 100% / 100% |
| 2018Q3 | 4 | −0.0038 | 0.8799 | 75% / 95.9% |

Resolution profile (anchor): γ=0.5→1 comm (Q=0); 0.8→3; 1.0→4;
1.2→8; 1.5→24 — quality non-positive throughout.

### Bridges (source: network_results.json)
- Possible pairs 6; detected 6 (Q1 baseline); shared Q1→Q2 = 6, Q2→Q3 = 3.
- Widths: Q1→Q2 max 5,279 mean 3,928; Q2→Q3 max 5,604 mean 4,141.
- 0 positions at width 1. Brokers/quarter: 5,814 / 6,111 / 6,027.

### Temporal + staffing (source: network_results.json; DESCRIPTIVE ONLY)
| transition | width Jaccard | width corr | observed overlap | Monte Carlo null mean | expected (analytic) |
|---|---|---|---|---|---|
| Q1→Q2 | 0.4993 | 0.9996 | 0.0551 | 0.3238 | 0.2196 |
| Q2→Q3 | 0.4991 | 0.9567 | 0.0274 | 0.3784 | 0.2773 |

Null: 1,000 draws, activity-weighted, +1 p-value; pooled p = 1.0
(computed but WITHHELD as headline — gates failed). Null reference
intervals: Q1→Q2 [0.320, 0.328]; Q2→Q3 [0.373, 0.383].
Failed gates: saturation, partition quality (Q≤0), <10 shared positions
(+ width sparsity on Q2→Q3).

### Engineering (sources: pytest, logs)
- 88 automated tests passed. Deterministic null rerun verified.
- Salted SHA-256 author hashes (16-hex); no raw usernames/text stored.
- Frozen config: γ=1, seeds 0–4, min_width=2, top-1% brokers,
  1000 null iterations, J≥0.3, match≥60%, coverage≥80%, ARI≥0.60.

---

## 3. LITERATURE SURVEY (18 papers)

Status key: CONSULTED = read/used during this project's sessions;
CITED = long-standing project background citation, not re-read in-session.
Only CONSULTED papers should be described as informing a specific decision.

| # | Paper | Venue | What it establishes | Role in this project | Status |
|---|---|---|---|---|---|
| 1 | Granovetter (1973), The strength of weak ties | Am. J. Sociology | Weak ties bridge dense clusters; bridges carry novel information | Theoretical motivation for studying bridges | CITED |
| 2 | Burt (1992), Structural Holes (book) | Harvard UP | Gaps between clusters; brokers spanning them gain advantage | Defines "broker"/"structural hole" vocabulary | CITED |
| 3 | Wasserman & Faust (1994), SNA: Methods and Applications (book) | Cambridge UP | Canonical SNA methods reference | Course/methods backdrop | CITED |
| 4 | Newman & Girvan (2004), Finding and evaluating community structure | Phys. Rev. E | Edge-betweenness community detection; modularity concept | Background to community detection choice | CITED |
| 5 | Guimerà & Amaral (2005), Functional cartography of complex metabolic networks | Nature 433 | Participation coefficient P: how evenly a node's links spread across modules | Broker metric P used continuously; top-1% descriptive set only | CITED |
| 6 | Newman (2006), Modularity and community structure in networks | PNAS | Modularity Q formulation | Quality metric reported (Q ≤ 0 finding) | CITED |
| 7 | Reichardt & Bornholdt (2006), Statistical mechanics of community detection | Phys. Rev. Lett. | Potts/RB Potts-model generalization of modularity with resolution γ | Basis of RBConfigurationVertexPartition used at γ=1 | CITED |
| 8 | Blondel et al. (2008), Fast unfolding of communities in large networks | J. Stat. Mech. | Louvain method | Rejected in favor of Leiden (connectivity guarantees) | CITED |
| 9 | Serrano, Boguñá & Vespignani (2009), multiscale backbone | PNAS, doi:10.1073/pnas.0808904106 | Disparity filter vs local uniform null; α is a backbone-selection parameter | Backbone = visualization ONLY; α=0.3 display parameter, never inferential | CONSULTED |
| 10 | Fortunato (2010), Community detection in graphs | Physics Reports | Comprehensive survey incl. resolution limits of modularity | Supports resolution-profile reporting; resolution-limit awareness | CITED |
| 11 | Larremore, Clauset & Jacobs (2014), bipartite community inference | Phys. Rev. E | Principled community detection directly on bipartite data | Candidate next method (direct bipartite detection) | CITED |
| 12 | Saracco et al. (2015), Randomizing bipartite networks (World Trade Web) | Sci. Rep., doi:10.1038/srep10595 | Null choice follows which margins are preserved (fixed-fixed vs soft) | Frames the fixed-fixed optional null; motivates validated projection | CITED |
| 13 | Saracco et al. (2017), entropy-based bipartite projections | New J. Phys. 19:053022 | Statistically validated projections under degree constraints | Candidate next method (validated projection) | CITED |
| 14 | Traag, Waltman & van Eck (2019), From Louvain to Leiden | Sci. Rep., doi:10.1038/s41598-019-41695-z | Leiden guarantees well-connected communities; faster than Louvain | Leiden-over-Louvain decision; official docs also fetched | CONSULTED |
| 15 | Phipson & Smyth (2010), Permutation P-values should never be zero | Stat. Appl. Genet. Mol. Biol., doi:10.2202/1544-6115.1585 | +1 correction for Monte Carlo p-values; "exact" only if enumerated | Terminology: "Monte Carlo randomization p-value", null reference intervals | CITED |
| 16 | Rollo et al. (2022), Attention Flow Graphs and Community Detection | SocInfo | Modularity maximization overfits; SBM/attention-flow alternatives | Motivated RBConfig caution; SBM explicitly deferred as future work | CONSULTED |
| 17 | Sawicki & Ganzha (2024), Reddit community structure: bridges, gateways, highways | Electronics 13(10):1935 | Reddit bridges≈gateways; highways are node sets; avg path 2.7 | Motivated the 20-member gateway stratum + sensitivity framing | CONSULTED |
| 18 | Centola & Macy (2007), Complex contagions and the weakness of long ties | Am. J. Sociology 113(3) | Bridge width as load-bearing structural quantity | Width ≥ 2 rule; width-first (not existence-first) inference | CITED |

Supporting/data-context citations (use sparingly): Schmidt et al. (2017)
PNAS (online fragmentation); Kristensen et al. (2023) Soc. Media+Society
(partisan network shocks); Hart et al. (2022) (permutation
non-independence → aggregate statistics); PLOS Complex Systems (2024)
bipartite review (fixed-fixed vs soft nulls).

---

## 4. FIGURE INVENTORY + PLOT RECIPES (for regenerating slides)

All source PNGs: `data_curation/data/presentation/`. Raw plot data:
`gpt_context/graphs/*.csv` (this pack). Style: 16:9, navy #1F3864 /
teal #0E7C7B / muted gray, Calibri, one hero number per slide.

1. **Data scale** (`01_data_scale.png/.csv`): grouped bars raw vs clean
   per quarter (M), retention % labels (94.3/94.2/94.1). Rebuild as 4 KPI
   cards: 170 · 3 · 171.6M · 161.7M + timeline 55.2→57.3→59.1M.
2. **Hairball** (`02_hairball_diagnostic.png`; rebuild from
   `graphs/nodes_Q1_layout.csv` + `graphs/edges_full_Q1.csv` using the
   stored x,y — identical layout guaranteed): 170 nodes colored by
   `leiden_community_Q1`, edges alpha≈0.05; hero number 99.85%.
3. **Full vs backbone** (`03_full_vs_backbone.png`; rebuild from same
   layout + `graphs/edges_backbone_Q1.csv`): identical node positions
   both panels; caption backbone display-only.
4. **Communities** (`04_community_diagnostic.png`; data
   `graphs/partitions_all_quarters.csv`, `04_resolution_profile.csv`):
   KPIs 4 / ARI 0.88–0.94 / Q≤0; footnote γ profile 1/3/4/8/24.
5. **Saturation** (`05_bridge_saturation.png`, `05_06_temporal.csv`):
   six pair cards C1–C2…C3–C4 all highlighted; KPIs 6/6, ~4–5.6k.
6. **Timeline** (`06_timeline.png`, `05_06_temporal.csv`): Q1→Q2→Q3
   boxes; under each arrow width Jaccard 0.499/0.499, corr 1.00/0.96,
   mapping 100%/100%, 75%/96%; DESCRIPTIVE ONLY banner.
7. **Observed vs null** (`07_observed_vs_null.png`,
   `graphs/null_summary.csv`): paired bars per transition —
   observed 0.055/0.027 vs Monte Carlo null mean 0.324/0.378;
   DESCRIPTIVE ONLY banner. (Analytic 0.22/0.28 values are the
   closed-form approximation, NOT the test null — do not plot both
   without this explanation; prefer null_mean.)
8. **Methodology diagram**: 9 boxes — data → cleaning → bipartite →
   cosine → Leiden → participation → positions → temporal → gates.
9. **Research story**: 7-step vertical flow ending in the next question.
Appendix: resolution dual-axis plot (`Ax_resolution_profile.png`;
rebuild from `graphs/resolution_profile_anchor.csv`).

---

## 5. LANGUAGE RULES (mandatory for any generated slide/report)

FORBIDDEN: proved, disproved, no bridges, no structure, hypothesis false,
null proves turnover, statistically significant (gated results),
"modularity failed" (say "RB quality Q ≤ 0"), universal "Reddit …" claims.
REQUIRED: descriptive-only labels on all Q9–Q11 equivalents; "sample-
specific network"; "preliminary, short-horizon, sample-conditional,
associational"; "measurement lens"; "not inferable under the current
representation"; backbone = visualization only.

---

## 6. FILE MAP (repo locations)

- Results: `data_curation/data/logs/network_results.json`,
  `run_manifest_2018Q1-Q3.json`, `coverage_report.csv`,
  `cleaning_report.csv`
- Plot data: `gpt_context/graphs/` (8 CSVs: nodes+layout, full edges,
  backbone edges, partitions, widths, null summary, resolution,
  cleaning)
- Slide PNGs: `data_curation/data/presentation/` (9 + appendix plot)
- PPTX: `Reddit_Bridge_Network_Analysis_Presentation.pptx` (repo root)
- Notes/map: `speaker_notes.md`, `slide_asset_map.md` (repo root)
- Frozen methods: `network_analysis/` (88 tests green); frame:
  `frame.csv` (170 = 150 topical + 20 gateway)
