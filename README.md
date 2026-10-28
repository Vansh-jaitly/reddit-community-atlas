# 🌉 Bridge Brokers of Reddit — Complete Project Guide

Welcome to the **Bridge Brokers of Reddit** computational social media analysis project. This guide explains what the project does, how it works, and how to run every part of the pipeline in simple, easy-to-understand terms.

---

## 1. What is this Project About? (The Big Picture)

Reddit is split into thousands of separate communities (subreddits). Most users stick to their favorite topics, but a small group of users actively post across different subreddits. We call these users **brokers**, and they act as **bridges** connecting different online communities.

### The Key Research Question:
> **Are bridge positions between communities persistent structural slots on Reddit, or do they disappear when individual users leave?**

**Our Hypothesis (H1)**:  
Community bridge positions persist over time even when individual users change. In other words, Reddit continually refills bridge roles because the platform's network structure demands them.

---

## 2. Quick Start (How to Run Everything)

### Step 1: Install Dependencies
Open your terminal inside the project folder:
```bash
python -m venv .venv
.venv\Scripts\activate          # On Windows
pip install -r requirements.txt
```

### Step 2: Run Data Extraction & Cleaning
Harvest Reddit comments from Hugging Face and clean them:
```bash
# Run 1-month fast test
python data_curation/run_pipeline.py --start 2018 1 --end 2018 1

# Run full window (2018-01 to 2022-08)
python data_curation/run_pipeline.py
```

### Step 3: Launch the Interactive Studio Dashboard
Open your web browser dashboard to view dataset health, interactive charts, and review candidate accounts:
```bash
streamlit run data_curation/dashboard.py
```

### Step 4: Run the Network Analysis Engine
Calculate Leiden communities, participation coefficients, and position vs. person stability metrics:
```bash
python network_analysis/run_network_pipeline.py
```

### Step 5: Export Data for Tableau (Objective O3 Deliverable)
Generate pre-formatted CSV files for your Tableau dashboard:
```bash
python data_curation/export_tableau_data.py
```

---

## 3. How the Pipeline Works (In 4 Simple Steps)

```
[ Hugging Face Archive ]
           │
           ▼ (Step 1: fetch.py)
   SHA-256 Hashing & Frame Filtering (150 Subreddits)
           │
           ▼ (Step 2: clean.py)
   4-Stage Bot Cascade (Purge bots, keep authentic brokers)
           │
           ▼ (Step 3: network_analysis/)
   Cosine Projection ➔ Serrano Backbone ➔ Leiden Communities ➔ Broker Stability Gap
           │
           ▼ (Step 4: dashboard.py & Tableau)
   Interactive Studio Dashboard & Tableau Reports
```

### Step 1: Privacy-Preserving Fetch (`fetch.py`)
- Pulls public Reddit comment data directly over HTTPS using DuckDB.
- **Privacy First**: Usernames are hashed with SHA-256 and a secret salt **inside the query itself** before saving to disk. Raw usernames never touch your computer.
- Filters data to our **150-subreddit sampling frame** across 6 diverse categories (`politics_news`, `hobby`, `finance`, `support`, `expertise`, `media`).

### Step 2: 4-Stage Bot Cascade (`clean.py`)
- **Stage 1 (Hard Bots)**: Removes known automated bots (`AutoModerator`, `*bot*` names).
- **Stage 2 (Activity Cutoff)**: Filters out single-comment driveby accounts.
- **Stage 3 (Subreddit Filter)**: Requires accounts to post in relevant subreddits.
- **Stage 4 (Manual Review)**: Flags top cross-posting accounts for human review in the dashboard rather than deleting them automatically.

### Step 3: Network Analysis Engine (`network_analysis/`)
- **Projection**: Builds a weighted network between subreddits using **Cosine Similarity on Binary Presence** (prevents giant subreddits from dominating).
- **Backbone Filtering**: Applies the **Serrano Disparity Filter** to cut noisy edges while keeping core community connections.
- **Leiden Communities**: Detects tightly knit subreddit clusters using the Leiden community detection algorithm.
- **Broker Detection**: Calculates the **Participation Coefficient ($P$)** to identify top 1% boundary-spanning users.
- **Stability Gap**: Compares **Position Stability** (do the same community pairs stay connected?) against **Person Stability** (do the same exact users stay as brokers?).

### Step 4: Dashboards & Presentation
- **Streamlit Dashboard (`dashboard.py`)**: Live visual monitor, DuckDB parquet query explorer, and interactive bot review editor with CSV write-back.
- **Tableau Export (`export_tableau_data.py`)**: Generates formatted CSVs for building the 5-sheet Tableau report.

---

## 4. Project Directory Map

```
d:/coursework/sm/
├── README.md                      <-- You are here! Complete project guide.
├── PROJECT_DESCRIPTION.md          <-- Full technical reference.
├── FRAME_JUSTIFICATION.md          <-- Objective O1: Sampling frame rationale.
├── TABLEAU_DASHBOARD_GUIDE.md      <-- Objective O3: Step-by-step Tableau guide.
├── frame.csv                      <-- The 150 subreddits analyzed.
│
├── data_curation/                 <-- Data harvesting and cleaning module
│   ├── config.py                  <-- Single source of truth (paths, thresholds, frame).
│   ├── fetch.py                   <-- Remote DuckDB data fetcher with SHA-256 hashing.
│   ├── clean.py                   <-- Bot cascade cleaning script.
│   ├── run_pipeline.py            <-- One-command pipeline runner.
│   ├── dashboard.py               <-- Streamlit interactive analytics studio.
│   └── export_tableau_data.py     <-- Formats CSVs for Tableau.
│
└── network_analysis/              <-- Network science & stability engine
    ├── bipartite.py               <-- User-subreddit bipartite graph builder.
    ├── projection.py              <-- Cosine similarity one-mode projection.
    ├── backbone.py                <-- Serrano disparity filter edge pruner.
    ├── community.py               <-- Leiden community detection algorithm.
    ├── brokerage.py               <-- Participation coefficient (P) calculator.
    ├── anchored_matching.py       <-- Anchored community matching.
    ├── stability_analysis.py      <-- Position vs Person stability gap & null models.
    └── run_network_pipeline.py    <-- Network engine runner.
```

---

## 5. Summary of Course Deliverables (Objectives O1–O5)

| Objective | Description | Deliverable Location | Status |
|---|---|---|---|
| **O1** | Stratified Sampling Frame (~150 subreddits) | [frame.csv](file:///d:/coursework/sm/frame.csv) & [FRAME_JUSTIFICATION.md](file:///d:/coursework/sm/FRAME_JUSTIFICATION.md) | ✅ Complete |
| **O2** | Reproducible Privacy-Preserving Pipeline | [fetch.py](file:///d:/coursework/sm/data_curation/fetch.py) & [clean.py](file:///d:/coursework/sm/data_curation/clean.py) | ✅ Complete |
| **O3** | Data Characterization & Dashboards | [dashboard.py](file:///d:/coursework/sm/data_curation/dashboard.py) & [TABLEAU_DASHBOARD_GUIDE.md](file:///d:/coursework/sm/TABLEAU_DASHBOARD_GUIDE.md) | ✅ Complete |
| **O4** | Leiden Community Structure & Matching | [community.py](file:///d:/coursework/sm/network_analysis/community.py) & [anchored_matching.py](file:///d:/coursework/sm/network_analysis/anchored_matching.py) | ✅ Complete |
| **O5** | Position vs. Person Stability Gap & Null Model | [stability_analysis.py](file:///d:/coursework/sm/network_analysis/stability_analysis.py) & [run_network_pipeline.py](file:///d:/coursework/sm/network_analysis/run_network_pipeline.py) | ✅ Complete |

