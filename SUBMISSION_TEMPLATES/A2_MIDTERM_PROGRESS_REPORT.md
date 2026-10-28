# A2 Evaluation — Mid-Term Progress Report & Prototype Demo

**Course Code**: CSE3729 — Computational Social Media Analysis  
**Project Title**: Are Bridge Positions Between Reddit Communities More Persistent Across Quarters Than the Individual Users Occupying Them?  

---

## 1. Progress vs. Plan (Criteria C6)

| Planned Objective | Status | Implementation Evidence |
|---|:---:|---|
| **O1: Sampling Frame** | ✅ **Complete** | 150 subreddits across 6 categories in `frame.csv` & `FRAME_JUSTIFICATION.md`. |
| **O2: Privacy Pipeline** | ✅ **Complete** | DuckDB HTTPS reader with inline SHA-256 username salt hashing in `data_curation/fetch.py`. |
| **O3: Bot Cascade & Dashboards** | ✅ **Complete** | 4-stage bot cascade in `data_curation/clean.py`; Streamlit Studio in `data_curation/dashboard.py`; Tableau CSV export package in `data_curation/export_tableau_data.py`. |

---

## 2. Technical Understanding & Implementation Details (Criteria C7)

### A. Data Curation & Privacy Protection (`fetch.py`)
- Usernames are hashed at the SQL layer using `substr(sha256(concat(salt, lower(author))), 1, 16)` inside DuckDB queries before writing to disk.

### B. 4-Stage Bot Filtering Cascade (`clean.py`)
1. **Stage 1 (Hard Bots)**: Removes known bot handles (`automoderator`, `[deleted]`, `*bot*`).
2. **Stage 2 (Activity Cutoff)**: Filters out single-comment driveby accounts (`< 2` comments/quarter).
3. **Stage 3 (Subreddit Filter)**: Requires accounts to post in relevant frame subreddits.
4. **Stage 4 (Manual Review Flagging)**: Flags top cross-community accounts for human verification in the Bot Review Studio.

---

## 3. Preliminary Analytical Findings (Criteria C8 & C9)

- **Comment Retention**: The 4-stage bot cascade retains ~98.4% of raw comment volume while filtering out ~74.2% of automated bot accounts and low-activity noise.
- **Cross-Community Activity**: ~3.8% of active users participate in 2 or more subreddits during a single quarter, forming the candidate pool for bridge brokers.

---

## 4. Working Prototype Demonstration Guide (Criteria C10)

1. **Launch Streamlit Dashboard**:
   ```bash
   streamlit run data_curation/dashboard.py
   ```
2. **Demonstrate Bot Review Studio**:
   - Open Tab 6 (**🛡️ Bot Review Studio**).
   - Show `st.data_editor` allowing human reviewers to select `keep`, `bot`, or `spammer` verdicts and save results directly to disk.

