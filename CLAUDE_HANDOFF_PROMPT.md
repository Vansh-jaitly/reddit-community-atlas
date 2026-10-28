# HANDOFF PROMPT FOR CLAUDE — paste everything below this line into Claude
# (Claude will also have full access to the repository folder.)

You are taking over the project in this repository (`<repo>`).
Read this entire brief first. It is authoritative. Do not redo completed work.

## 1. WHAT THIS IS

CSE3729 course project: "Beyond the Hairball — Measuring Cross-Community
Bridges in Reddit." Research question: do cross-community bridge positions
persist across quarters while the people occupying them turn over?
Data: Arctic Reddit comments (HuggingFace `open-index/arctic`), 2018Q1–Q3,
170 subreddits (150 topical + 20 gateway), 171.6M raw → 161.7M clean comments
(94.22% retention). All results are DESCRIPTIVE ONLY — longitudinal inference
was blocked by prespecified failure gates. Never claim confirmation of any
hypothesis.

## 2. CURRENT STATE (verified, do not re-derive blindly)

- 88 pytest tests pass. Full pipeline ran end-to-end on real data.
- Raw + clean Parquet for 2018Q1/Q2/Q3 exist locally (gitignored).
- Key outputs: `data_curation/data/logs/network_results.json`,
  `run_manifest_2018Q1-Q3.json`, `coverage_report.csv`, `cleaning_report.csv`.
- Presentation deck `Reddit_Bridge_Network_Analysis_Presentation.pptx` (19 slides)
  + `speaker_notes.md` + `slide_asset_map.md` exist in repo root.
- GPT context pack in `gpt_context/` (numbers, 18-paper literature table,
  plot-ready graph CSVs with frozen layouts).
- Git: work is uncommitted; private salt in `data_curation/salt.local`
  (gitignored — NEVER commit, print, or put it in any artifact).

## 3. THE HONEST RESULT (do not overturn without new evidence)

- Full cosine network is 99.85% dense (14,343/14,365 edges).
- Leiden γ=1 finds 4 communities, modularity ≈ −0.004, Q ≤ 0 at every
  tested resolution; seed ARI 0.88–0.94 (reproducible but invalid).
- Bridges saturated 6/6 pairs, widths ~4,000; <10 shared positions.
- Gates failed (saturation, partition quality, sample size) → both
  transitions descriptive-only; no pooled headline was reported.
- Correct framing: "the representation was not discriminative enough,"
  NOT "hypothesis disproven."

## 4. FROZEN METHODOLOGY (do not redesign without asking)

Full cosine → Leiden RBConfiguration γ=1 (5 fixed seeds) → pooled-anchor
Hungarian matching (J≥0.3, match≥60%, coverage≥80%) → continuous
participation coefficient, top-1% descriptive brokers → width≥2 positions →
activity-weighted turnover null (1000 iters, +1 Monte Carlo p) →
pooled equal-weight excess → prespecified failure gates. Serrano α=0.3 is
VISUALIZATION ONLY and never feeds inference. Full spec: ask the user for
the methodology freeze doc if needed; key code is `network_analysis/`
with `run_network_pipeline.py` as orchestrator.

## 5. HOW TO WORK HERE

- Read files with the read tool; run commands with `workdir` set to the repo
  root (Windows PowerShell 5.1 — no `&&`, no `tail`; quote paths with spaces).
- Test mode (`--max-shards N`) writes to `data/raw_TEST/` with separate
  progress DB and never touches real data; delete test artifacts when done.
- When testing `clean.py`, redirect `C.DATA_LOGS` to a temp dir or you will
  rewrite the real `manual_review_*.csv` files.
- `bool(float('nan')) is True` — every pandas optional string needs an
  explicit `pd.isna` guard.
- Never fabricate numbers; every claim needs a file:line or JSON path.
- `git status` first; do not commit unless explicitly asked.

## 6. KNOWN REMAINING WORK (highest value first)

1. Stale A2/A3/README numbers still unscrubbed (Q=0.412, J≈0.68/0.12,
   "H1 confirmed" — all invalid).
2. O1 synopsis still describes the old 150-member frame; needs amendment
   (dropping gateway does NOT recover the historical list).
3. Next experiment (NOT started): degree/activity-aware representation —
   statistically validated bipartite projection (Saracco et al. 2015/2017)
   or direct bipartite community detection (Larremore et al. 2014).
   Select on construct validity, not prettiest graph.
4. Deferred robustness: uniform null, width=3, percentile sweep,
   count-weighted projection, 150-frame comparison.

## 7. START BY

1. Running `git status` and `python -m pytest tests/ -q`.
2. Reading `gpt_context/CONTEXT_FOR_GPT.md` and `slide_asset_map.md`.
3. Reporting back anything in this brief that does not match the repo
   before making changes.
