# A1 Evaluation — Project Synopsis & Timeline

**Course Code**: CSE3729 — Computational Social Media Analysis  
**Academic Year**: 2026–27 (7th Semester)  
**Project Title**: Are Bridge Positions Between Reddit Communities More Persistent Across Quarters Than the Individual Users Occupying Them?  

---

## 1. Problem Definition (Criteria C1)

Social media platforms like Reddit are composed of thousands of distinct interest-based subreddits. While most users participate within a single domain, a critical minority—termed **bridge brokers**—spans across structural community boundaries. This project investigates whether community bridge positions represent **persistent structural roles** built into the network topology of Reddit, or whether they are transient artifacts of individual user activity.

---

## 2. Project Objectives & Expected Outcomes (Criteria C2)

- **Objective O1**: Construct a stratified sampling frame of 150 subreddits across 6 diverse functional categories (`politics_news`, `hobby`, `finance`, `support`, `expertise`, `media`) while excluding universal hub subreddits (`AskReddit`, `funny`, `pics`, `todayilearned`, `worldnews`).
- **Objective O2**: Build a scalable, privacy-preserving data extraction and cleaning pipeline using DuckDB and SHA-256 username salt hashing to harvest historical Reddit comment archives.
- **Objective O3**: Develop a 4-stage bot filtering cascade and build interactive data characterization dashboards in Streamlit and Tableau.
- **Objective O4**: Implement a network analysis engine using Cosine Presence Similarity projections, Serrano Disparity Filter backbones, and Leiden community detection.
- **Objective O5**: Quantify and compare **Position Stability ($J_{position}$)** vs. **Person Stability ($J_{person}$)** across consecutive quarters against degree-preserving null models to test **Hypothesis H1**.

---

## 3. Methodology & Technical Approach (Criteria C3)

```
[ Hugging Face Archive ]
           │
           ▼ (fetch.py - Privacy SHA-256 Hashing)
   150 Subreddits Data Extraction
           │
           ▼ (clean.py - 4-Stage Bot Cascade)
   Cleaned Bipartite User-Subreddit Matrix
           │
           ▼ (network_analysis/ - Engine)
   Cosine Projection ➔ Serrano Backbone ➔ Leiden Communities ➔ Brokerage (P_i)
           │
           ▼ (stability_analysis.py)
   Position Stability (J_pos) vs. Person Stability (J_per) Gap & Null Models
```

---

## 4. Feasibility & Resource Planning (Criteria C4)

- **Data Source**: Hugging Face `arctic-shift/reddit-comments` public Parquet archive (2018–2022).
- **Tools Used**: Python (DuckDB, Pandas, NetworkX, python-igraph, Leidenalg), Streamlit, Tableau Desktop, Gephi.
- **Hardware Requirements**: Standard workstation memory & CPU; DuckDB in-memory engine handles multi-gigabyte queries efficiently.

---

## 5. Project Timeline & Team Responsibility Matrix (Criteria C5)

| Project Phase | Target Dates | Core Deliverables | Team Responsibilities |
|---|---|---|---|
| **Phase 1 (A1)** | Sept W1 – Sept W3 | Synopsis, Sampling Frame (150 subreddits), Data source setup | All members: Data source definition & synopsis design. |
| **Phase 2 (A2)** | Sept W4 – Oct W4 | Data fetching pipeline, 4-stage bot cascade, Streamlit & Tableau dashboards | Member 1 & 2: Preprocessing & DuckDB. Member 3 & 4: Dashboard & Bot Studio. |
| **Phase 3 (A3)** | Nov W1 – Nov W4 | Network engine, Leiden communities, Stability gap analysis, Gephi exports, Final report | All members: Network analysis, presentation, final report & viva demonstration. |

