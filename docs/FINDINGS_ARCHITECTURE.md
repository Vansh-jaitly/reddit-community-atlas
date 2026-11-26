# Findings: architecture and data flow

The Findings section is a self-contained addition. It shares the application shell (router, charts, styles) and the
cleaned comment store with the Atlas, and adds one local data store, one Python package and three front-end modules.
Nothing in the existing pipeline, data or pages was changed to build it.

```
Arctic Shift comment shards (remote, read with DuckDB)
        │  fetch.py (existing)                       │  fetch_text.py (new, same salt, same batch design)
        ▼                                            ▼
data_curation/data/clean/*.parquet            data_curation/data/raw_text/<YYYY-MM>.parquet   (gitignored)
170 subreddits · no text · 210 M rows         23 subreddits · text for 11 · reply structure · flair · score
        │                                            │
        │   findings/io.py (DuckDB readers)          │   findings/text.py  → findings_cache/sentiment_<month>.parquet (VADER, gitignored)
        ▼                                            ▼
                 findings/stories.py  (build_community · build_infinity_war · build_bitcoin)
                 ├─ networks.py   reply edges → igraph graph → Leiden · centralities · brokerage · k-core → anonymised export
                 ├─ events.py     daily series · windows · bootstrap/permutation comparisons · change points · price phases
                 ├─ candidates.py the fourteen-candidate selection matrix (same quarter, same metrics)
                 └─ insights.py   rule-based detectors with thresholds (config.py) → insight records with links
                                  │
                 findings/build_findings.py → atlas/web/data/findings/{index,community,infinity_war,bitcoin}.json
                                              docs/findings_candidate_matrix.csv
                                  │
atlas/web/assets/findings.js (#/findings routes) · findings_net.js (sigma reply-network component) · style.css (.findings)
```

## What is published, what stays local

| Stays on the machine (gitignored) | Published (committed JSON) |
|---|---|
| comment text, scores, flair text, author hashes, reply ids | daily/monthly counts and sentiment shares per subreddit |
| per-comment VADER scores | window and phase summaries with effect sizes, CIs, permutation p-values |
| full reply graphs | readable cores (≤ 150 nodes) with anonymous ids `u1…`, positions, cluster, metrics, mean tone |
| the validation sample with excerpts | agreement statistics only |

`tests/test_findings.py` enforces the rule on every JSON under `atlas/web/data/findings/` (no 16-hex tokens, no
`author_h`/`body` columns, anonymous ids, insight links that resolve to Findings routes).

## Runtime behaviour

The Findings pages load `data/findings/index.json` on first visit and each story's JSON lazily; everything shown is
read from those files — no computation beyond smoothing, sorting and layout happens in the browser. The network
component renders the precomputed core (positions from a Fruchterman–Reingold layout computed in Python) with
sigma.js, so colouring by cluster, tone or camp, isolating a cluster and highlighting brokers are instant.

## Reproducing

```bash
python data_curation/fetch_text.py                    # ~2 h, needs the local salt (data_curation/salt.local)
python -m findings.build_findings                     # scores sentiment (~1 h, cached), then ~4 h for the three stories (null models, permutations)
python -m findings.validation export                  # labelled-sample export for the sentiment check
python -m pytest tests/test_findings.py               # unit + artifact tests
python atlas/serve.py                                 # → http://127.0.0.1:8000/#/findings
```

New dependency: `vaderSentiment==3.3.2` (added to `requirements.txt`). Tornado (already present through Streamlit)
is used by `tools/capture_screens.py` for narrow-viewport screenshots.

## Validation sample and its labels

`python -m findings.validation export` writes a stratified sample (3 subreddit groups × 3 months × 3 VADER labels × 12,
up to 324 excerpts) to the local cache with an empty `label` column; `python -m findings.validation score` reports
accuracy, macro-F1, Cohen's κ and the confusion matrix. The labels shipped with this build were produced by three
independent language-model annotators with a majority vote (disclosed in the methodology note and in the app); they are a
stand-in for the team's own double coding, which should replace them before submission.

## Methods at a glance

Reply edges from `parent_id`; Leiden (30 seeds, fewer on large graphs, ARI/AMI agreement, rewired-graph baseline, Infomap
cross-check and resolution scan for the focused community); betweenness with 1/replies distances (sampled from 2,000
sources above 6,000 users), Everett–Valente brokerage, participation coefficient, broker significance against
degree-preserving rewirings (small graphs) or a degree-matched percentile (large graphs); E–I index with a rewiring null; VADER with a
pre-declared domain-neutralised lexicon for the event stories (standard score beside it); class shares with Cohen's h,
bootstrap CIs and permutation tests; segmented regression for the release-level change compared with all 170 communities;
Benjamini–Hochberg across the insight tests of each story. Details and references: `docs/FINDINGS_METHODOLOGY.md`.
