# PROJECT CONTEXT HANDOFF — Reddit Bridge Brokers (CSMA)

**Purpose of this document:** a complete, self-contained briefing for a new agent (Claude) to continue this project without re-deriving anything. Everything below was verified by direct code inspection and test execution, not recollection.

**Project root:** `C:\Users\vansh\Desktop\CSMA\sm`
**Status:** infrastructure sound and tested; **no real data analysed yet**; several methodology decisions still open.
**Test suite:** 69 passing.

---

## 1. WHAT THE PROJECT IS

A CSMA course project studying **structural bridges in Reddit communities over time**.

**Central research question:** do bridge *positions* and *capacity* persist quarter-over-quarter, or do the same bridge positions get re-staffed by entirely different users?

**Data source:** `hf://datasets/open-index/arctic` (Arctic Reddit comment dump, hosted on HuggingFace)
**Window:** `2018-01` through `2022-08` = **19 quarters**
**Unit of analysis:** (user, subreddit, quarter) comment co-participation

**Reframed hypotheses** (the original binary framing was rejected as unfalsifiable):

| ID | Hypothesis |
|---|---|
| F1/H1 | Bridge **capacity/width** persists across quarters |
| F2 | Bridge **occupants** turn over |
| F3 | Occupant persistence **increases with bridge width** (dose-response) |
| F4 | Persistent bridges span **greater structural distance** |
| F5 | **Gateway** communities behave differently from ordinary boundaries |

The key methodological insight: raw occupant overlap is meaningless without a baseline, because the same accounts are present every quarter and will reappear as bridge occupants regardless of whether bridges are genuinely staffed by the same specialists. Hence a **width-preserving null**.

**Original (invalid) claims that must be scrubbed:** `Q = 0.412`, `J_position ≈ 0.68`, `J_person ≈ 0.12`, "H1 confirmed". These came from a degenerate one-quarter run.

---

## 2. ORIGINAL ARCHITECTURE

| File | Role | Original state |
|---|---|---|
| `data_curation/config.py` | Config + hand-typed 150-subreddit frame | `{subreddit: category}` dict, 6 categories |
| `data_curation/fetch.py` | SQL extraction from Arctic → Parquet | `WHERE subreddit IN (...)` **case-sensitive** |
| `data_curation/clean.py` | Bot filter + manual review | volume-only bot deletion |
| `network_analysis/bipartite.py` | user×subreddit matrix | binary `M[u,s]=1` |
| `network_analysis/projection.py` | subreddit→subreddit network | cosine similarity, O(n²) loop |
| `network_analysis/community.py` | Leiden communities | `CPMVertexPartition`, res 0.5–1.5, raw weights |
| `network_analysis/backbone.py` | Statistical backbone | disparity filter **alpha=0.05** |
| `network_analysis/brokerage.py` | Broker identification | participation coefficient |
| `network_analysis/stability_analysis.py` | Temporal comparisons | position/person Jaccard |
| `network_analysis/run_network_pipeline.py` | Orchestration | single quarter |

---

## 3. THE AUDIT THAT INVALIDATED THE ORIGINAL RESULTS

The historical run (2018Q1) produced:
- 18,282,918 raw rows → 16,074,924 clean rows, 476,996 users
- Network: **35 nodes, 595 raw edges, 30 backbone edges, 34 communities, 4,436 brokers, 561 positions, `transitions: []`**

Three fatal problems:

1. **Position Jaccard saturated.** `561 = C(34,2)` — *every* community pair was occupied by a broker, so `J_position` measured nothing.
2. **No temporal data.** One quarter means `transitions` is empty. Nothing about H1 was ever measured.
3. **Community detection was degenerate.** `CPMVertexPartition` on raw cosine weights (which live in (0,1], averaging ~0.07) split every node into its own community: **150 communities over 150 nodes, modularity −0.007**. Compounding it, the code optimised CPM while *reporting and selecting on* `part.modularity` — a different objective.

---

## 4. LITERATURE RESEARCH AND THE ARCHITECTURE IT PRODUCED

Three papers were read. **One produced a large architectural change, one produced a frame change, and three findings were never implemented.**

### 4.1 Rollo et al. (2022), *Attention Flow Graphs and Community Detection*, SocInfo
**Finding:** maximising modularity is prone to overfitting; recommends stochastic block modelling (SBM) over raw modularity.

**Architecture produced:** `community.py` rewritten — default switched to `RBConfigVertexPartition`, resolution × seed sweep (5 seeds per resolution), explicit degeneracy check, and `_normalised_weights()` so CPM may be used *only* with mean-1 weights. Measured justification, recorded in the module docstring:

| configuration | result |
|---|---|
| CPM + raw cosine, res 0.5–1.5 | 150 communities, modularity **−0.007** |
| RBConfiguration (modularity, γ=1) | **6 communities, modularity 0.730** |
| CPM + weights normalised to mean 1 | 6 communities (at res 0.05–0.1) |

Design principle adopted: the objective optimised is now the objective reported and selected on.

**NOT implemented:** the SBM itself. RBConfig is an *intermediate* fix; Rollo's actual recommendation is still outstanding. This is a live methodological decision, and `FRAME_JUSTIFICATION.md:176-177` currently cites Rollo for a fix that only partially follows from the paper.

**NOT implemented:** attention-flow / Personalized PageRank, Rollo's own method. Zero references in any `.py` file.

### 4.2 Sawicki & Ganzha (2024), *Exploring Reddit Community Structure: Bridges, Gateways and Highways*, Electronics 13(10), 1935
**Findings:** bridges and gateways largely overlap (nearly all bridges are also gateways); highways are *node sets* rather than edges; average shortest path 2.7 with 83% of node pairs at distance 2.

**Architecture produced:** a **7th `gateway` stratum** of 20 communities, alongside the six topical strata of 25. Implemented as `GATEWAY_SEED`, `GATEWAY_STRATUM`, and a `gateway` category across `config.py` / `frame_rules.py` (25 references). Rationale recorded at `FRAME_JUSTIFICATION.md:115`. Because the stratum carries ~49.2% of frame volume, it also created a **mandatory sensitivity comparison** against the 150-member topical-only frame.

**NOT implemented:** the paper's **highways** concept — 0 references anywhere in code. More importantly, the bridge/gateway taxonomy is used only for *sampling*, never for *measurement*: nothing in `network_analysis/` classifies a node's measured structural role. The `gateway` label is an assumption, and the gateway-vs-topical comparison will partly test whether the label was right.

### 4.3 arXiv 2407.11794, *What's in a Niche? Migration Patterns in Online Communities*
**Finding:** migration orientations are acyclic gradients across 13 categories; users move toward smaller, less toxic, more distinctive communities with fewer self-mentions.

**NOT implemented at all.** The only "migration" reference in the entire codebase is a keyword inside `frame_rules.py:126` (a subreddit classification rule), not an analysis. No gradient computation, no toxicity metric, no distinctiveness measure. This supports a *narrative* only.

---

## 5. FRAME REBUILD (the largest change)

### 5.1 The bug
The original frame silently lost members. Arctic subreddit **casing is inconsistent** — `cooking`/`Cooking`, `physics`/`Physics`, `dividends`/`DIVIDENDS`, `FIRE`/`Fire`, `PTSD`/`ptsd` — and `fetch.py` used an exact-match `WHERE subreddit IN (...)`.

- **19 members failed only on casing** (e.g. `politicalcompassmemes` → `PoliticalCompassMemes`)
- **4 members were entirely absent** (`bicycles`, `ListeningTo`, `filmmaking`, `boardgamegeek`)
- **23 of 150 dropped ≈ 2,743,012 comments ≈ 6.3% of frame volume**, with no warning

Additionally the frame contained **near-dead communities** (case-folded audit over three calibration months):
- `politicalcompassmenses` — `n_min = 20` against a 1.14M peak
- `FIRE`, `dividends`, `quant` — similarly near-dead
- 29/150 had `n_min < 2000`; 6 were unobservable

### 5.2 The fix
Full-month Arctic scans at three calibration points (start, middle, end of window):

| month | distinct subreddits | comments |
|---|---|---|
| 2018-01 | 102,304 | 91,558,594 |
| 2020-07 | 228,280 | 194,244,994 |
| 2022-08 | 274,210 | 162,000,000 |
| **merged pool** | **477,275** | **447,803,588** |

**Selection rule:** a subreddit must have `n_min ≥ 2000`, where `n_min` = *minimum* monthly count across all three points. This yields 2,701 candidates; a shipped `n_min ≥ 500` artifact (5,546 rows) backs auditability. Selection is **rule-based, not hand-picked**: keyword classifier + primary-rule precedence + `politics_news` regional-news fallback + an `EXCLUDE` blocklist of reviewed misclassifications (`HistoryPorn`, `FrankOcean`, `softwaregore`, `buildapcsales`, …).

**Result — 170 members, 0 case-insensitive duplicates, all `n_min ≥ 3787`:**

| category | n | `n_min` range |
|---|---|---|
| expertise | 25 | 6,557 – 115,573 |
| finance | 25 | 5,282 – 112,888 |
| gateway | 20 | 63,170 – 3,880,860 |
| hobby | 25 | 11,429 – 85,819 |
| media | 25 | 13,979 – 321,233 |
| politics_news | 25 | 3,990 – 904,358 |
| support | 25 | 3,787 – 79,380 |

Gateway seed: `AskReddit`, `worldnews`, `funny`, `mildlyinteresting`, `pics`, `todayilearned`, `aww`, `Showerthoughts`, `interestingasfuck`, `RoastMe`, `nottheonion`, `NoStupidQuestions`, `starterpacks`, `LifeProTips`, `dataisbeautiful`, `videos`, `PublicFreakout`, `mildlyinfuriating`, `tifu`, `oddlysatisfying`.

### 5.3 Verification
Case-insensitive SQL filter; `assert_frame_coverage()` runs **before** export and raises if any frame member is missing. Live proof on 6 real Arctic shards (2018-01): **1,834,018 rows, 170/170 frame members observed, 0 non-frame rows leaked.**

### 5.4 Known limitation
The three-point screen is a **heuristic, not proof** of quarter-wide presence. A subreddit can vanish between calibration points. The fetch-time coverage assertion is the actual guard.

---

## 6. EVERY BUG FOUND AND FIXED

### 6.1 `data_curation/clean.py` — three bugs found during end-to-end verification

**(a) Prolific users silently deleted.** The keep-filter was
`AND n_comments < {BOT_VOLUME_HARD_CUTOFF}` — volume alone — directly contradicting the comment two lines above it and the `high_volume & high_breadth` computation. For *this study specifically* it removed exactly the population being measured: high-volume users with narrow breadth are dedicated power users, and the most active cross-community users are the brokers under study. Now:
```sql
AND NOT (n_comments >= {BOT_VOLUME_HARD_CUTOFF} AND n_subs >= {breadth_cutoff})
```

**(b) `TypeError` on every clean run.** Line 188 read `agg["n_subs"] >= breadth_hard_cutoff` — the *function object*, missing `(n_frame)`. The frame-relative-breadth refactor had left clean broken; the first smoke test missed it only because test mode skips the clean stage.

**(c) Blank verdicts counted as real verdicts.** `str(row.get("verdict", "") or "")` fails because pandas fills blanks with `float('nan')` and **`bool(nan) is True`**. All 200 unreviewed rows became pseudo-verdicts of the string `"nan"`, producing the log message "reusing 200 existing manual verdict(s)" and `manual_verdicts_applied: 200` when **no human review had ever happened**. Writing `"nan"` back to CSV re-parses as NaN, making the corruption self-perpetuating. Guarded with `pd.isna` at all three sites.

### 6.2 `network_analysis/brokerage.py` — the broker definition was degenerate

```python
user_comm = df.groupby(["author_h", "community"]).size().reset_index(name="k_ic")
```

`load_bipartite_dataframe()` (called at `run_network_pipeline.py:91`) returns data **already aggregated** to one row per `(author_h, subreddit)`. So `.size()` counts *rows* → **`k_ic = 1` for every user**, and the Burt formula collapsed to `P_i = 1 - 1/k_i` — a pure function of breadth.

Demonstrated before fixing:

| user | split across 2 subs | P before | P after |
|---|---|---|---|
| A | 1000 / 1000 (balanced) | 0.5 | 0.5 |
| B | 1999 / 1 (monopolist) | 0.5 | 0.001 |

Identical breadth → identical P, so `is_broker` meant only "posts in many subreddits" and **engagement balance contributed nothing**. Fixed to `groupby(...)["n_comments"].sum()`; verified against analytic values (7/3 → 0.42, 1/1 → 0.5, scale-invariant as the participation coefficient requires).

### 6.3 `network_analysis/backbone.py`
`alpha = 0.05` over-pruned to 30 edges. Default now `0.3`, with over-pruning warnings.

### 6.4 `network_analysis/stability_analysis.py`
Original p-value was a **z-test of within-network mean degree** — a self-referential statistic, not a hypothesis test. `J_person` was raw overlap with no baseline. Replaced with:
- empirical permutation p-values `(1 + n_ge) / (1 + n_iterations)` (lines 318, 575)
- a **width-preserving occupant-turnover null**: preserves each position's width `w1, w2` and the account pool, destroys only identity assignment
- a dose-response test whose null is a **flat line** across width buckets — a concrete, falsifiable prediction

---

## 7. VERIFIED CURRENT STATE

**Tests: 69 passing**

| file | tests |
|---|---|
| `tests/test_frame_case_sensitivity.py` | 24 |
| `tests/test_measure_validity.py` | 12 |
| `tests/test_brokerage.py` | 9 |
| `tests/test_community_detection.py` | 9 |
| `tests/test_manual_review_stage.py` | 8 |
| `tests/test_clean_bot_logic.py` | 7 |

**Config:** `MIN_COMMENTS_PER_QUARTER=5`, `MIN_SUBS_PER_QUARTER=1`, `FRAME`=150, `GATEWAY_STRATUM`=20, `FRAME_ALL`=170, `FRAME_UNOBSERVABLE=set()`, `BOT_VOLUME_HARD_CUTOFF=2000`, `BOT_BREADTH_FRACTION=0.5`, `MANUAL_REVIEW_TOP_N=200`, `VERDICT_REMOVE={'remove','bot','spammer'}`, `breadth_hard_cutoff(170)=85`

**Calibration artifact:** `frame_calibration.csv`, 5,546 rows, columns `subreddit, n_2018_01, n_2020_07, n_2022_08, n_min, n_total`

**Data:** `raw parquet: 0`, `clean parquet: 0` — **nothing real has been analysed**

**Integration verified:** imports OK (frame 170), `build_frame_filter_sql` emits 170 lowercase literals, test-mode fetch+clean pass end-to-end on 1.83M rows.

---

## 8. REMAINING GAPS

### Blocking
1. **No data.** 0 Parquet files. No H1–F5 result is computable.
2. **`HASH_SALT = "bb-cse3729-2026-CHANGE-ME"` is a placeholder.** `config.py` explicitly says *"Change this to your own secret before a real run."* Because `author_h` is salted per-pipeline, running the 19-quarter fetch with this placeholder and later changing it would invalidate every row.
3. **O1 synopsis still documents the old 150-subreddit frame.** Dropping gateway no longer recovers the historical literal list — only the 25-per-stratum *structure* is preserved, because the topical membership was rebuilt. Reconciling this *after* a full fetch would force a re-download of all 19 quarters.

### Correctness / false claims
4. **`brokerage.py` docstring claims "Burt's Constraint C_i (Burt, 1992)".** The module has exactly one function, `compute_participation_coefficients`. No constraint code exists anywhere.
5. **Stale fabricated numbers** in `A2_MIDTERM_PROGRESS_REPORT.md`, `A3_FINAL_PROJECT_REPORT.md`, `README`, `data_curation/data/logs/network_results.json` (`Q=0.412`, `J_position≈0.68`, `J_person≈0.12`, "H1 confirmed").
6. **`FRAME_JUSTIFICATION.md` overstates** that three calibration points "guarantee" presence in every quarter.

### Methodology not yet settled
7. **Partition stability does not feed the null models.** The turnover null assumes position labels `(A,B)` are exchangeable, which assumes the Leiden partition is stable across quarters. Stability is computed but does not condition the p-value.
8. **RBConfiguration vs SBM** — Rollo's actual recommendation is unbuilt; current default only partially addresses modularity overfitting.
9. **Binary vs count-weighted interaction** — `bipartite.py:54` sets `M[u,s]=1`; `projection.py` uses cosine on presence. This is a design choice currently assumed rather than tested as a sensitivity.
10. **No reply/dyad layer.** `parent_id`, `link_id`, and `score` are available in the Arctic source but referenced in **zero** `.py` files. "Interaction" means co-commenting, not directed reply. (Optional; requires re-fetch.)
11. **`projection.py`** is an O(n²) Python loop; `n_users` lands only in a node attribute, so volume is discarded from the weighting.
12. **`broker_percentile=0.99` is unjustified** and has no sensitivity sweep.
13. **`anchored_matching.py`, `stability_analysis.py`, `projection.py`** — the three files carrying the most new logic — have **no direct tests**.

### Optional
14. Measured bridge/gateway/highway role classification (Sawicki & Ganzha's actual contribution).
15. Migration-gradient analysis (arXiv 2407.11794).

---

## 9. RECOMMENDED NEXT STEPS (in order)

1. **Set a real `HASH_SALT`** (untracked local override, not committed).
2. **Decide RBConfig vs SBM** and **reconcile the O1 synopsis frame description** — both must be settled *before* fetching, or all 19 quarters must be redone.
3. **Correct the false claims** (items 4–6): remove the Burt Constraint claim, scrub A2/A3/README/`network_results.json`, soften the quarter-coverage wording.
4. **Add tests** for `anchored_matching.py`, `stability_analysis.py`, `projection.py`.
5. **Run the 19-quarter fetch** (`data_curation/run_pipeline.py --start 2018 1 --end 2022 8`), confirming 170/170 coverage per quarter.
6. **Run clean**, then the network pipeline, producing at least two consecutive clean quarters.
7. **Compute the real analyses**: width persistence, occupant turnover vs the width-preserving null, width dose-response, structural-distance effects, and the gateway-vs-topical sensitivity (`dict(FRAME)`).
8. Only then draft results — from actual numbers.

---

## 10. WARNINGS FOR THE NEXT AGENT

- **Do not fabricate or interpolate results.** The user's standing requirement is scientific defensibility with explicit limitations.
- **Every re-fetch is expensive** (19 quarters, ~448M comments scanned). Settle frame and salt first.
- **Test-mode isolation is intentional.** `run_pipeline.py --max-shards N` writes to `data/raw_TEST/` with a separate progress file and staging DB, and does **not** update `coverage_report.csv`. Delete `raw_TEST/` when done. It cannot contaminate real data.
- **When testing `clean.py`, redirect `C.DATA_LOGS` too.** Doing otherwise reads and rewrites the real `manual_review_*.csv` (this happened once and was cleaned up).
- **`bool(float('nan'))` is `True`.** Any pandas-sourced optional string needs an explicit `pd.isna` guard, not `x or ""`.
- **Current git state:** all work is uncommitted. 15 files modified, 5 untracked (`conftest.py`, `frame_calibration.csv`, `frame_rules.py`, `tests/`, `tools/`).
