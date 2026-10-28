"""
export_tableau_data.py
======================
Formats and exports 5 structured CSV datasets into `data/tableau/` specifically
designed for building the 5-sheet Tableau Dashboard required for Objective O3.
"""

from __future__ import annotations
import json
from pathlib import Path
import duckdb
import pandas as pd
import sys

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import data_curation.config as C


def export_tableau_datasets():
    tableau_dir = C.ROOT / "data" / "tableau"
    tableau_dir.mkdir(parents=True, exist_ok=True)

    print("🚀 Exporting formatted Tableau Datasets to data/tableau/...")

    # --- Dataset 1: Coverage & Extraction Summary ---
    cov_path = C.DATA_LOGS / "coverage_report.csv"
    if cov_path.exists():
        cov_df = pd.read_csv(cov_path)
        cov_out = tableau_dir / "tableau_1_coverage_overview.csv"
        cov_df.to_csv(cov_out, index=False)
        print(f"  • Sheet 1 data saved: {cov_out.name}")

    # --- Dataset 2: Bot Cascade & Data Retention Funnel ---
    clean_path = C.DATA_LOGS / "cleaning_report.csv"
    if clean_path.exists():
        clean_df = pd.read_csv(clean_path)
        clean_df["pct_rows_retained"] = (100.0 * clean_df["rows_clean"] / clean_df["rows_raw"]).round(2)
        clean_df["pct_users_retained"] = (100.0 * clean_df["users_clean"] / clean_df["users_raw"]).round(2)
        clean_out = tableau_dir / "tableau_2_bot_cascade_funnel.csv"
        clean_df.to_csv(clean_out, index=False)
        print(f"  • Sheet 2 data saved: {clean_out.name}")

    # --- Dataset 3: Subreddit & Category Volume Distribution ---
    clean_parquets = sorted(C.DATA_CLEAN.glob("*.parquet"))
    if clean_parquets:
        con = duckdb.connect()
        union_query = " UNION ALL ".join(
            [f"SELECT '{p.stem}' AS quarter, subreddit, author_h, is_mod FROM '{str(p).replace('\\\\', '/')}'" for p in clean_parquets]
        )
        cat_df = con.execute(
            f"""
            WITH raw_data AS ({union_query})
            SELECT 
                quarter, 
                subreddit, 
                COUNT(*) AS comment_count, 
                COUNT(DISTINCT author_h) AS unique_users,
                SUM(CAST(is_mod AS INTEGER)) AS mod_comments
            FROM raw_data
            GROUP BY quarter, subreddit
            ORDER BY quarter, comment_count DESC
            """
        ).df()
        con.close()
        cat_df["category"] = cat_df["subreddit"].map(C.category_of)
        cat_out = tableau_dir / "tableau_3_subreddit_categories.csv"
        cat_df.to_csv(cat_out, index=False)
        print(f"  • Sheet 3 data saved: {cat_out.name}")

    # --- Dataset 4: Cross-Community Brokers & Participation Coefficient ---
    net_path = C.DATA_LOGS / "network_results.json"
    if net_path.exists():
        with open(net_path, "r", encoding="utf-8") as f:
            net_res = json.load(f)

        anchor_part = net_res.get("anchor_partition", {})
        anchor_df = pd.DataFrame(
            list(anchor_part.items()), columns=["subreddit", "anchor_community_id"]
        )
        anchor_df["category"] = anchor_df["subreddit"].map(C.category_of)
        anchor_out = tableau_dir / "tableau_4_anchor_communities.csv"
        anchor_df.to_csv(anchor_out, index=False)
        print(f"  • Sheet 4 data saved: {anchor_out.name}")

        transitions = net_res.get("transitions", [])
        if transitions:
            trans_df = pd.DataFrame(transitions)
            trans_out = tableau_dir / "tableau_5_stability_comparison.csv"
            trans_df.to_csv(trans_out, index=False)
            print(f"  • Sheet 5 data saved: {trans_out.name}")

    print("\n✅ Tableau datasets successfully generated in `data/tableau/`!")


if __name__ == "__main__":
    export_tableau_datasets()
