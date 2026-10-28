# Objective O3 Deliverable: 5-Sheet Tableau Dashboard Guide

**Project**: Bridge Brokers of Reddit — Data Curation & Network Analysis  
**Deliverable**: Objective O3 — Five-Sheet Tableau Dashboard  
**Generated CSV Location**: `data/tableau/` (produced by `python data_curation/export_tableau_data.py`)

---

## 1. Overview of the 5 Tableau Sheets

To fulfill Objective O3, the project requires a 5-sheet interactive Tableau Story / Dashboard:

| Sheet # | Sheet Title | Primary Dataset | Primary Visual Type | Key Metric / Insight |
|---|---|---|---|---|
| **Sheet 1** | **Extraction Coverage & Speed** | `tableau_1_coverage_overview.csv` | Grouped Bar / Gantt Chart | Harvested comment volume & fetch elapsed time per quarter. |
| **Sheet 2** | **Bot Cascade Funnel & Retention** | `tableau_2_bot_cascade_funnel.csv` | Funnel / Dual-Axis Bar Chart | Step-by-step data retention through 4-stage bot cascade. |
| **Sheet 3** | **Category & Subreddit Volume** | `tableau_3_subreddit_categories.csv` | Treemap / Stacked Bar | Subreddit comment volume stratified by 6 sampling frame categories. |
| **Sheet 4** | **Leiden Community Partition** | `tableau_4_anchor_communities.csv` | Packed Bubble / Highlight Table | Global anchor community clusters and category composition. |
| **Sheet 5** | **Position vs Person Stability** | `tableau_5_stability_comparison.csv` | Dual Line / Band Chart | Position Jaccard vs. Person Jaccard stability gap across consecutive quarters (Hypothesis H1). |

---

## 2. Step-by-Step Instructions to Build in Tableau Desktop / Tableau Public

### Step 1: Connect to Datasets
1. Launch Tableau Desktop / Tableau Public.
2. Select **Text File** connector and select `data/tableau/tableau_1_coverage_overview.csv`.
3. Add the remaining 4 CSV files from `data/tableau/` as independent data sources.

### Step 2: Build Sheet 1 — Extraction Coverage Overview
1. Open a new worksheet, rename to `Sheet 1 - Coverage Overview`.
2. Drag `quarter` to **Columns**, `rows` to **Rows**.
3. Drag `status` to **Color** (Set colors: `complete` = Green `#2E7D32`, `partial` = Yellow `#F9A825`, `no_data` = Red `#C62828`).
4. Add `elapsed_sec` as a secondary mark for timing diagnostics.

### Step 3: Build Sheet 2 — Bot Cascade Funnel & Retention
1. Create a new worksheet `Sheet 2 - Bot Cascade Funnel`.
2. Drag `quarter` to **Columns**, `rows_raw` and `rows_clean` to **Rows** as a Measure Values dual-axis bar chart.
3. Drag `pct_rows_retained` to **Tooltip** and `hard_bots_removed` to a secondary detail sheet.

### Step 4: Build Sheet 3 — Subreddit & Category Treemap
1. Create a new worksheet `Sheet 3 - Category Treemap`.
2. Drag `category` and `subreddit` to **Marks -> Text/Detail**.
3. Drag `comment_count` to **Size** and `unique_users` to **Color**.
4. Set marks type to **Treemap**.

### Step 5: Build Sheet 4 — Anchor Community Partition
1. Create a new worksheet `Sheet 4 - Anchor Partition`.
2. Drag `anchor_community_id` to **Columns**, `category` to **Color**.
3. Set marks type to **Packed Bubble** or **Bar Chart** showing community distribution.

### Step 6: Build Sheet 5 — Position vs Person Stability Gap (Hypothesis H1)
1. Create a new worksheet `Sheet 5 - Stability Gap`.
2. Drag `transition` to **Columns**, `position_stability` and `person_stability` to **Rows**.
3. Set Measure Values as a dual line chart (Blue line = Position Stability, Red line = Person Stability).
4. Add `stability_gap` as label highlighting the difference ($\Delta$).

### Step 7: Combine into an Interactive Dashboard Story
1. Create a new Dashboard (`1920x1080` resolution).
2. Drag all 5 sheets into a structured 2x3 or tabbed layout.
3. Add interactive **Filter Actions** linking category and quarter selection across all sheets.
4. Export as Tableau Workbook (`.twbx`) or publish to Tableau Public.

