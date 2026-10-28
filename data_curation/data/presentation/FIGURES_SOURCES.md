# Presentation artifacts — source table

Directory: `data_curation/data/presentation/`
Status of every number below: **descriptive only; inference blocked by failure gates** (saturation, Q ≤ 0, <10 shared positions). No new statistics were created for these slides.

| Figure | File | Exact data source | How to reproduce / update |
|---|---|---|---|
| 1. Data scale | `01_data_scale.png` + `.csv` | `data/logs/cleaning_report.csv` (rows_raw, rows_clean per quarter) | Rerun `pres1.py` §1 after re-cleaning; values are read from the CSV, hardcoded nowhere else |
| 2. Hairball diagnostic | `02_hairball_diagnostic.png` | `data/clean/2018Q1.parquet` via `load_bipartite_dataframe` → `build_bipartite_matrix` → `compute_cosine_projection` (170 nodes, 14,343 edges) | Rerun `pres2.py` §2; layout `spring_layout(seed=0)` |
| 3. Full vs backbone | `03_full_vs_backbone.png` | Same Q1 graph + `disparity_filter(G, alpha=0.3)` (5,981 edges) | Rerun `pres2.py` §3 |
| 4. Community diagnostic | `04_community_diagnostic.png` + `.csv`, `04_resolution_profile.csv` | `data/logs/network_results.json` → `quarter_results[*].community_partition / seed_agreement`, `anchor_resolution_profile` | Rerun `pres2.py` §4 after any pipeline rerun |
| 5. Bridge saturation | `05_bridge_saturation.png` | `network_results.json` transitions (`possible_community_pairs`, `max/mean_bridge_width`) | Rerun `pres1.py` §5; widths read from JSON |
| 6. Timeline | `06_timeline.png`, `05_06_temporal.csv` | `network_results.json` transitions (width_jaccard, width_correlation, match_rate, match_coverage) | Rerun `pres1.py` §6 |
| 7. Observed vs null | `07_observed_vs_null.png` + `.csv` | `network_results.json` transitions (`occupant_overlap.mean_occupant_jaccard`, `occupant_turnover_null.expected_overlap_by_chance`) | Rerun `pres1.py` §7 |
| 8. Methodology diagram | `08_methodology.png` | Frozen pipeline order (no data values) | Edit step list in `pres1.py` §8 |
| 9. Research story | `09_research_story.png` | Narrative + measured values (99.85% density, gate outcomes) | Edit step list in `pres1.py` §9 |

Generator scripts (kept outside the repo, in the agent temp dir): `pres1.py` (figs 1, 5–9), `pres2.py` (figs 2–4), `pres_csv.py` (CSVs). To regenerate inside the repo later, copy them to `tools/` and rerun after any pipeline change.

Key numbers pinned to outputs (do not hand-edit):
- Density 14,343/14,365 = 99.85% — recomputed live in `pres2.py`, matches Q1 pipeline log.
- Seed ARI 0.88–0.94, Q ≈ −0.004 — from `network_results.json`.
- Widths max 5,279/5,604, mean 3,928/4,141 — from `network_results.json`.
- Observed 0.0551/0.0274, chance-level 0.2196/0.2773 — from `network_results.json`.
