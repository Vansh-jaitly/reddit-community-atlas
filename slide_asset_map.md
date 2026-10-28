# Slide asset map — Reddit_Bridge_Network_Analysis_Presentation.pptx

All numbers verified against `data_curation/data/logs/network_results.json`,
`coverage_report.csv`, `cleaning_report.csv`, and `data/presentation/*.csv`.
Descriptive-only status applies to slides 9–11.

[FIGURE: TITLE_MOTIF]
Source: abstract motif (no data)
Slide: 1

[FIGURE: BRIDGE_CONCEPT]
Source: original diagram (no data)
Slide: 2

[FIGURE: DATA_SCALE]
Source: cleaning_report.csv → data/presentation/01_data_scale.csv
Slide: 3
Values: raw 55,248,128 / 57,301,138 / 59,053,604 (total 171,602,870);
clean 52,118,250 / 54,002,756 / 55,570,837 (total 161,691,843);
retention 94.3 / 94.2 / 94.1, overall 94.22%.

[FIGURE: PIPELINE]
Source: frozen methodology (no data values)
Slide: 4
Side panel: privacy (salted hashes), reproducibility (frozen config),
engineering verification (88 tests passed — `pytest tests/`).

[FIGURE: LENS]
Source: methodology definition (no data values)
Slide: 5

[FIGURE: HAIRBALL]
Source: Q1 full cosine network rebuilt from data/clean/2018Q1.parquet
Slide: 6
Values: 170 nodes, 14,343 / 14,365 edges = 99.85% density.

[FIGURE: FULL_VS_BACKBONE]
Source: Q1 cosine + Serrano α=0.3 (5,981 edges)
Slide: 7
Note: backbone is visualization only.

[FIGURE: COMMUNITY_DIAGNOSTIC]
Source: network_results.json
Slide: 8
Values: 4 communities; seed ARI 0.897/0.882/0.880 (range 0.88–0.94);
quality Q ≈ −0.004 at γ=1, ≤ 0 at γ = 0.5–1.5 (RBConfiguration).

[FIGURE: BRIDGE_SATURATION]
Source: network_results.json + data/presentation/05_06_temporal.csv
Slide: 9
Values: 6/6 possible pairs detected (Q1 baseline); shared Q1→Q2 = 6,
Q2→Q3 = 3; widths max 5,279/5,604, mean 3,928/4,141. NOTE: the earlier
`bridge_pairs = 0` in 05_06_temporal.csv was a CSV-generation bug (it read a
nonexistent `widths` key); corrected to detected baseline positions = 6, 6.

[FIGURE: TEMPORAL_TIMELINE]
Source: network_results.json
Slide: 10
Values: width Jaccard 0.4993/0.4991; correlation 0.9996/0.9567;
mapping 100%/100%, 75%/95.9%.

[FIGURE: OCCUPANT_OVERLAP]
Source: network_results.json
Slide: 11
Values: observed 0.0551/0.0274 vs Monte Carlo null means 0.3238/0.3784
(1,000 draws each). NOTE reconciled: `expected_overlap_by_chance`
(0.2196/0.2773) is a closed-form approximation E[I]/E[U]; `null_mean` is the
actual Monte Carlo mean the p-value is computed against — the slide uses
the latter, labeled "Monte Carlo null mean".

[FIGURE: STORY]
Derived only from verified measured results
Slide: 13

Slides 12, 14, 15, 16, Appendices B–C: text/checklists, no figures.
Appendix A figure: data/presentation/Ax_resolution_profile.png from
04_resolution_profile.csv.
