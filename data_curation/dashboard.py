"""
dashboard.py
============
Advanced, interactive, and high-end data quality & analytics dashboard for the
Reddit Bridge Brokers Data Curation Pipeline.

Features:
  1. Executive Summary & Pipeline Overview (KPI Cards, Global Metrics)
  2. Extraction & Coverage Analytics (Interactive timelines, Shard efficiency, Timings)
  3. Cleaning Audit & Bot Cascade Dynamics (Funnel diagrams, Retention %, Bot removal breakdown)
  4. Interactive Data Explorer & Cross-Community Analytics (DuckDB powered treemaps, broker rankings, activity dists, time series)
  5. Network & Community Structure (Interactive 2D graph, Leiden community detection, disparity filter backbone, stability gap H1)
  6. Interactive Manual Bot Review Studio (st.data_editor with direct CSV write-back & account drill-down)
  7. Pipeline Health, Logs & Config Inspector (Log filtering, progress monitoring, sampling frame viewer)
"""

from __future__ import annotations
from pathlib import Path
import json
import duckdb
import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import sys

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as C
from network_analysis.bipartite import load_bipartite_dataframe, build_bipartite_matrix
from network_analysis.projection import compute_cosine_projection
from network_analysis.backbone import disparity_filter
from network_analysis.brokerage import compute_participation_coefficients

# Page Config
st.set_page_config(
    page_title="Community Atlas | Data & Pipeline Console",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Modern, Premium UI
st.markdown(
    """
    <style>
    /* Metric Card Styling */
    .metric-card {
        background-color: var(--background-secondary, #f8f9fa);
        border: 1px solid var(--border-color, #e9ecef);
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        margin-bottom: 12px;
    }
    .metric-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-color-secondary, #6c757d);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
    }
    .metric-val {
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--text-color, #212529);
        line-height: 1.2;
    }
    .metric-sub {
        font-size: 0.8rem;
        color: var(--text-muted, #8c98a4);
        margin-top: 4px;
    }
    
    /* Custom Header Banner */
    .main-header {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 24px 30px;
        border-radius: 12px;
        margin-bottom: 24px;
    }
    .main-header h1 {
        margin: 0;
        color: white;
        font-size: 2.2rem;
        font-weight: 700;
    }
    .main-header p {
        margin-top: 6px;
        margin-bottom: 0;
        opacity: 0.9;
        font-size: 1.05rem;
    }

    /* Cascade Stage Cards */
    .cascade-card {
        border-left: 4px solid #2a5298;
        background-color: var(--background-secondary, #f8f9fa);
        padding: 12px 16px;
        border-radius: 4px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------------
# DATA LOADERS (Cached with TTLs & Graceful Fallbacks)
# ------------------------------------------------------------------------
@st.cache_data(ttl=15)
def load_csv_if_exists(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        return df if not df.empty else None
    except Exception as e:
        st.warning(f"Could not read {path.name}: {e}")
        return None


@st.cache_data(ttl=15)
def list_quarters(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.parquet"))


@st.cache_data(ttl=10)
def load_fetch_progress() -> dict | None:
    path = C.DATA_CACHE / "fetch_progress.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@st.cache_data(ttl=15)
def load_network_results() -> dict | None:
    path = C.DATA_LOGS / "network_results.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@st.cache_data(ttl=60)
def build_network_plotly_fig(parquet_path_str: str, anchor_partition: dict[str, int], alpha: float = 0.05):
    try:
        df_q = load_bipartite_dataframe(parquet_path_str)
        if df_q.empty:
            return None
        M, users, subs, _, _ = build_bipartite_matrix(df_q)
        G = compute_cosine_projection(M, subs)
        G_backbone = disparity_filter(G, alpha=alpha)

        pos = nx.spring_layout(G_backbone, seed=42, k=0.35)

        edge_x, edge_y = [], []
        for u, v in G_backbone.edges():
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=0.8, color="#B0BEC5"),
            hoverinfo="none",
            mode="lines",
        )

        node_x, node_y, node_text, node_color, node_size = [], [], [], [], []

        for node in G_backbone.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)

            cid = anchor_partition.get(node, 0)
            cat = C.category_of(node)
            deg = G_backbone.degree(node)
            n_u = G_backbone.nodes[node].get("n_users", 0)

            node_text.append(f"<b>r/{node}</b><br>Category: {cat}<br>Anchor Community: {cid}<br>Backbone Degree: {deg}<br>Users: {n_u:,}")
            node_color.append(cid)
            node_size.append(min(45, max(14, deg * 2.2)))

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode="markers+text",
            hoverinfo="text",
            text=[f"r/{n}" for n in G_backbone.nodes()],
            textposition="top center",
            hovertext=node_text,
            marker=dict(
                showscale=True,
                colorscale="Viridis",
                color=node_color,
                size=node_size,
                colorbar=dict(
                    thickness=15,
                    title=dict(text="Community ID", side="right"),
                    xanchor="left",
                ),
                line_width=2,
            ),
        )

        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title=dict(
                    text="🕸️ Serrano Disparity Backbone & Leiden Community Clusters (Interactive)",
                    font=dict(size=16),
                ),
                showlegend=False,
                hovermode="closest",
                margin=dict(b=20, l=20, r=20, t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                height=650,
            ),
        )
        return fig
    except Exception as e:
        st.warning(f"Could not render 2D network graph: {e}")
        return None


# DuckDB Cached Analytics Queries
@st.cache_data(ttl=60)
def get_quarter_kpis(parquet_path_str: str):
    try:
        con = duckdb.connect()
        res = con.execute(
            f"""
            SELECT 
                COUNT(*) AS total_rows,
                COUNT(DISTINCT author_h) AS unique_users,
                COUNT(DISTINCT subreddit) AS unique_subs,
                SUM(CAST(is_mod AS INTEGER)) AS mod_comments
            FROM '{parquet_path_str}'
            """
        ).fetchone()
        con.close()
        return {
            "total_rows": res[0] or 0,
            "unique_users": res[1] or 0,
            "unique_subs": res[2] or 0,
            "mod_comments": res[3] or 0,
        }
    except Exception:
        return {"total_rows": 0, "unique_users": 0, "unique_subs": 0, "mod_comments": 0}


@st.cache_data(ttl=60)
def get_subreddit_category_breakdown(parquet_path_str: str):
    try:
        con = duckdb.connect()
        df = con.execute(
            f"""
            SELECT subreddit, COUNT(*) AS n_comments, COUNT(DISTINCT author_h) AS n_users
            FROM '{parquet_path_str}'
            GROUP BY subreddit
            ORDER BY n_comments DESC
            """
        ).df()
        con.close()
        df["category"] = df["subreddit"].map(C.category_of)
        return df
    except Exception:
        return pd.DataFrame(columns=["subreddit", "n_comments", "n_users", "category"])


@st.cache_data(ttl=60)
def get_user_activity_distribution(parquet_path_str: str):
    try:
        con = duckdb.connect()
        df = con.execute(
            f"""
            WITH user_counts AS (
                SELECT author_h, COUNT(*) AS comments
                FROM '{parquet_path_str}'
                GROUP BY author_h
            )
            SELECT comments, COUNT(*) AS user_count
            FROM user_counts
            GROUP BY comments
            ORDER BY comments ASC
            """
        ).df()
        con.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["comments", "user_count"])


@st.cache_data(ttl=60)
def get_cross_community_brokers_db(parquet_path_str: str, top_n: int = 50):
    try:
        con = duckdb.connect()
        df = con.execute(
            f"""
            SELECT 
                author_h, 
                COUNT(DISTINCT subreddit) AS sub_count, 
                COUNT(*) AS total_comments,
                SUM(CAST(is_mod AS INTEGER)) AS mod_count
            FROM '{parquet_path_str}'
            GROUP BY author_h
            HAVING COUNT(DISTINCT subreddit) >= 2
            ORDER BY sub_count DESC, total_comments DESC
            LIMIT {top_n}
            """
        ).df()
        con.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["author_h", "sub_count", "total_comments", "mod_count"])


@st.cache_data(ttl=60)
def get_time_series_data(parquet_path_str: str):
    try:
        con = duckdb.connect()
        df = con.execute(
            f"""
            SELECT 
                to_timestamp(created_utc)::DATE AS date,
                COUNT(*) AS comment_count,
                COUNT(DISTINCT author_h) AS user_count
            FROM '{parquet_path_str}'
            GROUP BY date
            ORDER BY date ASC
            """
        ).df()
        con.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["date", "comment_count", "user_count"])


@st.cache_data(ttl=30)
def get_user_subreddit_breakdown(parquet_path_str: str, author_h: str):
    try:
        con = duckdb.connect()
        df = con.execute(
            f"""
            SELECT subreddit, COUNT(*) as comment_count, SUM(CAST(is_mod AS INTEGER)) as mod_comments
            FROM '{parquet_path_str}'
            WHERE author_h = '{author_h}'
            GROUP BY subreddit
            ORDER BY comment_count DESC
            """
        ).df()
        con.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["subreddit", "comment_count", "mod_comments"])


# ------------------------------------------------------------------------
# HEADER & GLOBAL BANNER
# ------------------------------------------------------------------------
st.markdown(
    """
    <div class="main-header">
        <h1>🗂️ Community Atlas — Data &amp; Pipeline Console</h1>
        <p>Data quality pipeline monitor, bot cascade audit suite, and interactive cross-community analytics studio.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

cov_df = load_csv_if_exists(C.DATA_LOGS / "coverage_report.csv")
clean_df = load_csv_if_exists(C.DATA_LOGS / "cleaning_report.csv")

# Global Metrics
total_raw = int(cov_df["rows"].sum()) if cov_df is not None and "rows" in cov_df.columns else 0
total_clean = int(clean_df["rows_clean"].sum()) if clean_df is not None and "rows_clean" in clean_df.columns else 0
retention = (100.0 * total_clean / total_raw) if total_raw > 0 else 0.0
complete_q = int((cov_df["status"] == "complete").sum()) if cov_df is not None and "status" in cov_df.columns else 0
total_q = len(cov_df) if cov_df is not None else 0
flagged_cnt = int(clean_df["manual_review_flagged"].sum()) if clean_df is not None and "manual_review_flagged" in clean_df.columns else 0

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Raw Comments", f"{total_raw:,}" if total_raw > 0 else "0 (No data)")
m2.metric("Total Clean Comments", f"{total_clean:,}" if total_clean > 0 else "0 (No data)")
m3.metric("Retention Rate", f"{retention:.1f}%" if total_raw > 0 else "N/A")
m4.metric("Complete Quarters", f"{complete_q} / {total_q}" if total_q > 0 else "0 / 0")
m5.metric("Bot Review Flagged", f"{flagged_cnt:,}" if flagged_cnt > 0 else "0")

st.markdown("---")

# Sidebar Controls
with st.sidebar:
    st.header("⚙️ Pipeline Controls")
    
    if st.button("🔄 Refresh Data Cache", use_container_width=True):
        st.cache_data.clear()
        st.success("Cache cleared! Reloading data...")
        st.rerun()

    st.markdown("---")
    st.subheader("📋 Dataset Info")
    st.markdown(f"**Target Window**: `{C.DEFAULT_START[0]}Q{C.DEFAULT_START[1]}` to `{C.DEFAULT_END[0]}Q{C.DEFAULT_END[1]}`")
    st.markdown(f"**Subreddits Frame**: `{len(C.FRAME)}` subreddits")
    st.markdown(f"**Excluded Hubs**: `{len(C.EXCLUDED_HUBS)}` subreddits")
    st.markdown(f"**Min Comments / Qtr**: `{C.MIN_COMMENTS_PER_QUARTER}`")
    st.markdown(f"**Min Subs / Qtr**: `{C.MIN_SUBS_PER_QUARTER}`")
    
    st.markdown("---")
    progress = load_fetch_progress()
    if progress:
        st.subheader("⚡ Live Extraction State")
        st.info(f"**Current Quarter**: `{progress.get('current_quarter', 'N/A')}`\n\n**Shard**: `{progress.get('shard_index', 0)}`\n\n**Total Fetched**: `{progress.get('total_fetched_shards', 0)}`")
    else:
        st.caption("No active fetch progress checkpoint.")


# Main Tabs
tab_overview, tab_coverage, tab_cleaning, tab_explorer, tab_network, tab_review, tab_health = st.tabs(
    [
        "📊 Executive Summary",
        "📡 Extraction & Coverage",
        "🧹 Cleaning Audit",
        "🔍 Data Explorer & Analytics",
        "🕸️ Network & Communities",
        "🛡️ Bot Review Studio",
        "📜 System Health & Logs",
    ]
)

# ============================================================ TAB 1: EXECUTIVE SUMMARY
with tab_overview:
    st.subheader("📌 Executive Overview & Dataset Progress")
    
    if cov_df is None:
        st.info("👋 No coverage data has been fetched yet. Run `python run_pipeline.py` or `python fetch.py` to begin.")
    else:
        st.markdown(
            "This dashboard monitors the Reddit Bridge Brokers data curation pipeline. "
            "It tracks extraction from Hugging Face, audit metrics across the 4-stage bot filtering cascade, "
            "and provides live analytical drill-downs across cross-community activity."
        )

        c1, c2 = st.columns([1, 1])

        with c1:
            st.markdown("### 📈 Extraction Progress by Quarter")
            if "rows" in cov_df.columns:
                fig_cov = px.bar(
                    cov_df,
                    x="quarter",
                    y="rows",
                    color="status",
                    color_discrete_map={
                        "complete": "#2E7D32",
                        "partial": "#F9A825",
                        "no_data": "#C62828",
                        "not_started": "#9E9E9E",
                    },
                    labels={"quarter": "Quarter", "rows": "Comment Count", "status": "Status"},
                    title="Comment Records Harvested per Quarter",
                    text_auto=".2s",
                )
                fig_cov.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=350)
                st.plotly_chart(fig_cov, use_container_width=True)

        with c2:
            st.markdown("### 🧹 Data Retention (Raw vs. Clean)")
            if clean_df is not None and "rows_raw" in clean_df.columns and "rows_clean" in clean_df.columns:
                fig_ret = px.bar(
                    clean_df,
                    x="quarter",
                    y=["rows_raw", "rows_clean"],
                    barmode="group",
                    labels={"value": "Rows", "variable": "Data Stage", "quarter": "Quarter"},
                    color_discrete_map={"rows_raw": "#5C6BC0", "rows_clean": "#26A69A"},
                    title="Raw vs. Clean Comment Volumes",
                )
                fig_ret.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=350)
                st.plotly_chart(fig_ret, use_container_width=True)
            else:
                st.info("Clean report not generated yet. Run `python clean.py` to see retention breakdown.")

        st.markdown("### 🗂️ Quarters Executive Status Table")
        merged_summary = cov_df.copy()
        if clean_df is not None:
            merged_summary = merged_summary.merge(
                clean_df[["quarter", "rows_clean", "users_raw", "users_clean", "hard_bots_removed", "manual_review_flagged"]],
                on="quarter",
                how="left",
            )
            merged_summary["retention_%"] = (100.0 * merged_summary["rows_clean"] / merged_summary["rows"]).round(1)

        st.dataframe(
            merged_summary,
            column_config={
                "quarter": st.column_config.TextColumn("Quarter"),
                "status": st.column_config.TextColumn("Status"),
                "rows": st.column_config.NumberColumn("Raw Rows", format="%'d"),
                "rows_clean": st.column_config.NumberColumn("Clean Rows", format="%'d"),
                "users_raw": st.column_config.NumberColumn("Raw Users", format="%'d"),
                "users_clean": st.column_config.NumberColumn("Clean Users", format="%'d"),
                "retention_%": st.column_config.NumberColumn("Retention %", format="%.1f%%"),
                "hard_bots_removed": st.column_config.NumberColumn("Bots Auto-Removed", format="%'d"),
                "manual_review_flagged": st.column_config.NumberColumn("Flagged Review", format="%'d"),
            },
            use_container_width=True,
            hide_index=True,
        )


# ============================================================ TAB 2: COVERAGE
with tab_coverage:
    st.subheader("📡 Extraction & Coverage Analytics")

    if cov_df is None:
        st.info("No coverage report found. Run `python fetch.py` first.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Quarters Attempted", len(cov_df))
        col2.metric("Complete Quarters", int((cov_df["status"] == "complete").sum()))
        col3.metric("Partial Quarters", int((cov_df["status"] == "partial").sum()))
        col4.metric("No Data Quarters", int((cov_df["status"] == "no_data").sum()))

        st.markdown("---")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 📦 Shard Fetch Efficiency")
            if "fetched_shards" in cov_df.columns and "total_shards" in cov_df.columns:
                fig_shards = px.bar(
                    cov_df,
                    x="quarter",
                    y=["fetched_shards", "total_shards"],
                    barmode="overlay",
                    opacity=0.8,
                    title="Fetched Shards vs Total Available Shards",
                    color_discrete_sequence=["#1976D2", "#BBDEFB"],
                )
                fig_shards.update_layout(height=350)
                st.plotly_chart(fig_shards, use_container_width=True)
            else:
                st.caption("Shard detail columns absent in coverage report.")

        with c2:
            st.markdown("#### ⏱️ Fetch Duration per Quarter")
            if "elapsed_sec" in cov_df.columns:
                cov_df["elapsed_min"] = (cov_df["elapsed_sec"] / 60.0).round(1)
                fig_time = px.bar(
                    cov_df,
                    x="quarter",
                    y="elapsed_min",
                    title="Extraction Elapsed Time (Minutes)",
                    color_discrete_sequence=["#7E57C2"],
                    text_auto=".1f",
                )
                fig_time.update_layout(height=350)
                st.plotly_chart(fig_time, use_container_width=True)
            else:
                st.caption("Elapsed timing data absent in coverage report.")

        st.markdown("#### 📑 Detailed Coverage Audit Log")
        st.dataframe(cov_df, use_container_width=True, hide_index=True)

        if "months_missing" in cov_df.columns:
            missing = cov_df[cov_df["months_missing"].notna() & (cov_df["months_missing"] != "")]
            if not missing.empty:
                st.warning(
                    f"⚠️ **{len(missing)} Quarter(s) Have Missing Months**: "
                    "Months outside 2018-01 to 2022-08 are expected to be missing on Hugging Face HTTP source."
                )
                st.dataframe(missing[["quarter", "months_missing"]], use_container_width=True, hide_index=True)


# ============================================================ TAB 3: CLEANING AUDIT
with tab_cleaning:
    st.subheader("🧹 Bot Cascade Audit & Cleaning Dynamics")

    st.markdown(
        """
        The pipeline executes a **4-Stage Bot Cascade** to purge non-human accounts without removing authentic community brokers:
        1. **Stage 1 (Hard Bot Cutoff)**: Auto-removes known bot accounts (`automoderator`, `[deleted]`, `*bot*` suffixes).
        2. **Stage 2 (Activity Threshold)**: Purges single-driveby accounts (`< MIN_COMMENTS_PER_QUARTER`).
        3. **Stage 3 (Subreddit Filter)**: Filters out accounts not meeting minimum subreddit presence thresholds.
        4. **Stage 4 (Manual Review Flagging)**: Flags top cross-community accounts for human verification before network stage.
        """
    )

    if clean_df is None:
        st.info("No cleaning report yet. Run `python clean.py` after fetching data.")
    else:
        clean_df["pct_rows_kept"] = (100 * clean_df["rows_clean"] / clean_df["rows_raw"]).round(1) if "rows_clean" in clean_df.columns else 0
        clean_df["pct_users_kept"] = (100 * clean_df["users_clean"] / clean_df["users_raw"]).round(1) if "users_clean" in clean_df.columns else 0

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### 👥 Unique Users: Raw vs. Clean")
            if "users_raw" in clean_df.columns and "users_clean" in clean_df.columns:
                fig_users = px.bar(
                    clean_df,
                    x="quarter",
                    y=["users_raw", "users_clean"],
                    barmode="group",
                    title="Unique Users Retained Post-Cleaning",
                    color_discrete_map={"users_raw": "#AB47BC", "users_clean": "#26A69A"},
                )
                fig_users.update_layout(height=350)
                st.plotly_chart(fig_users, use_container_width=True)

        with c2:
            st.markdown("#### 🤖 Hard Bots Removed vs Flagged Review")
            if "hard_bots_removed" in clean_df.columns and "manual_review_flagged" in clean_df.columns:
                fig_bots = px.bar(
                    clean_df,
                    x="quarter",
                    y=["hard_bots_removed", "manual_review_flagged"],
                    barmode="group",
                    title="Bot Cascade Dispositions",
                    color_discrete_map={"hard_bots_removed": "#EF5350", "manual_review_flagged": "#FFA726"},
                )
                fig_bots.update_layout(height=350)
                st.plotly_chart(fig_bots, use_container_width=True)

        st.markdown("#### 📊 Overall Cleaning Retention Cascade Funnel")
        tot_raw_r = clean_df["rows_raw"].sum() if "rows_raw" in clean_df.columns else 0
        tot_bots_r = clean_df["hard_bots_removed"].sum() if "hard_bots_removed" in clean_df.columns else 0
        tot_clean_r = clean_df["rows_clean"].sum() if "rows_clean" in clean_df.columns else 0
        tot_filtered_r = max(0, tot_raw_r - tot_clean_r - tot_bots_r)

        fig_funnel = go.Figure(
            go.Funnel(
                y=["Raw Input Comments", "Hard Bots Auto-Removed", "Low Activity Filtered", "Cleaned Output Data"],
                x=[tot_raw_r, tot_bots_r, tot_filtered_r, tot_clean_r],
                textinfo="value+percent initial",
                marker={"color": ["#5C6BC0", "#EF5350", "#FFCA28", "#26A69A"]},
            )
        )
        fig_funnel.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_funnel, use_container_width=True)

        st.markdown("#### 📑 Detailed Quarter Cleaning Table")
        st.dataframe(
            clean_df,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================ TAB 4: DATA EXPLORER & ANALYTICS
with tab_explorer:
    st.subheader("🔍 Interactive Data Explorer & Cross-Community Analytics")

    exp_col1, exp_col2 = st.columns([1, 2])
    with exp_col1:
        stage_choice = st.radio("Select Data Stage", ["clean", "raw"], horizontal=True, key="exp_stage_choice")
    
    dir_path = C.DATA_CLEAN if stage_choice == "clean" else C.DATA_RAW
    available_q = list_quarters(dir_path)

    if not available_q:
        st.info(f"No {stage_choice} parquet files found in `data/{stage_choice}/` yet.")
    else:
        with exp_col2:
            selected_q = st.selectbox(
                "Select Quarter",
                available_q,
                index=len(available_q) - 1,
                key="exp_quarter_choice",
            )

        parquet_file = dir_path / f"{selected_q}.parquet"
        parquet_str = str(parquet_file).replace("\\", "/")

        with st.spinner("Executing DuckDB aggregations..."):
            kpis = get_quarter_kpis(parquet_str)
            sub_df = get_subreddit_category_breakdown(parquet_str)
            user_dist = get_user_activity_distribution(parquet_str)
            brokers_df = get_cross_community_brokers_db(parquet_str, top_n=50)

        # KPI Metrics Display
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Comments", f"{kpis['total_rows']:,}")
        k2.metric("Unique Authors", f"{kpis['unique_users']:,}")
        k3.metric("Subreddits Represented", f"{kpis['unique_subs']:,}")
        mod_pct = (100.0 * kpis['mod_comments'] / kpis['total_rows']) if kpis['total_rows'] > 0 else 0
        k4.metric("Moderator Comments", f"{kpis['mod_comments']:,} ({mod_pct:.2f}%)")

        st.markdown("---")

        t1, t2 = st.columns([1, 1])

        with t1:
            st.markdown("#### 🌳 Subreddit Category Distribution (Treemap)")
            if not sub_df.empty:
                fig_tree = px.treemap(
                    sub_df,
                    path=["category", "subreddit"],
                    values="n_comments",
                    color="n_users",
                    color_continuous_scale="Viridis",
                    title="Comment Volume by Category & Subreddit",
                )
                fig_tree.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380)
                st.plotly_chart(fig_tree, use_container_width=True)

        with t2:
            st.markdown("#### 📊 Subreddit Volume & Unique User Count")
            if not sub_df.empty:
                fig_sub = px.bar(
                    sub_df.head(15),
                    x="subreddit",
                    y="n_comments",
                    color="category",
                    hover_data=["n_users"],
                    title="Top 15 Subreddits by Comment Count",
                )
                fig_sub.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_sub, use_container_width=True)

        a1, a2 = st.columns([1, 1])

        with a1:
            st.markdown("#### 📈 User Activity Distribution (Log-Scale)")
            use_log = st.checkbox("Log scale Y-axis", value=True, key="log_scale_dist")
            if not user_dist.empty:
                fig_dist = px.bar(
                    user_dist.head(50),
                    x="comments",
                    y="user_count",
                    log_y=use_log,
                    labels={"comments": "Comments per User", "user_count": "Number of Users"},
                    title="Frequency of Comments per User",
                    color_discrete_sequence=["#00897B"],
                )
                fig_dist.update_layout(height=360)
                st.plotly_chart(fig_dist, use_container_width=True)

        with a2:
            st.markdown("#### 🌉 Top Cross-Community Brokers (>= 2 Subreddits)")
            st.dataframe(
                brokers_df,
                column_config={
                    "author_h": st.column_config.TextColumn("Hashed Author (SHA256)"),
                    "sub_count": st.column_config.NumberColumn("Subreddits Count"),
                    "total_comments": st.column_config.NumberColumn("Total Comments"),
                    "mod_count": st.column_config.NumberColumn("Mod Comments"),
                },
                use_container_width=True,
                height=310,
                hide_index=True,
            )

        st.markdown("#### 📅 Activity Timeline Across Quarter")
        ts_df = get_time_series_data(parquet_str)
        if not ts_df.empty:
            fig_ts = px.line(
                ts_df,
                x="date",
                y="comment_count",
                title="Daily Comment Volume",
                labels={"date": "Date", "comment_count": "Comments"},
                color_discrete_sequence=["#3949AB"],
            )
            fig_ts.update_layout(height=300)
            st.plotly_chart(fig_ts, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🎲 Live Parquet Random Sample Inspector")
        sample_size = st.slider("Sample Size", min_value=50, max_value=500, value=100, step=50, key="sample_size_slider")
        
        con = duckdb.connect()
        sample_df = con.execute(f"SELECT * FROM '{parquet_str}' USING SAMPLE {sample_size}").df()
        con.close()

        st.dataframe(sample_df, use_container_width=True)
        st.caption("🔒 `author_h` is a SHA-256 hash computed with project salt in `fetch.py`. Raw usernames are never stored.")


# ============================================================ TAB 5: NETWORK & COMMUNITIES
with tab_network:
    st.subheader("🕸️ Interactive 2D Network Graph & Community Structure Visualizer")
    st.warning(
        "This tab shows the **V1 baseline** (cosine projection + Serrano display backbone), kept for the project "
        "history. The final relationship map is the **Community Atlas** (`python atlas/serve.py`), which uses the "
        "activity-adjusted BiCM affinity network. V1's stored modularity is unweighted; see "
        "`data_curation/data/logs/v1_modularity_audit.json` for the weighted values."
    )

    net_res = load_network_results()

    if net_res is None:
        st.info(
            "💡 No network analysis results found. "
            "Run `python network_analysis/run_network_pipeline.py` to execute projection, Serrano disparity filtering, "
            "Leiden community detection, and position vs. person stability calculations."
        )
    else:
        st.markdown(
            "This tab presents the **interactive structural network visualizer** (Objectives O4 & O5): "
            "2D network layout, Serrano disparity backbone edges, Leiden community clusters, "
            "and the **Position Stability vs. Person Stability (Hypothesis H1)** comparison."
        )

        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Anchor Communities", net_res.get("anchor_communities_count", 0))
        n2.metric("Anchor Modularity", f"{net_res.get('anchor_modularity', 0.0):.3f}")
        n3.metric("Quarters Analyzed", len(net_res.get("quarter_results", {})))
        n4.metric("Evaluated Transitions", len(net_res.get("transitions", [])))

        st.markdown("---")

        # 2D Interactive Network Graph Visualization
        st.markdown("#### 🕸️ Interactive Subreddit Network Graph (Serrano Backbone & Leiden Clusters)")
        available_clean_q = list_quarters(C.DATA_CLEAN)
        if available_clean_q:
            net_q = st.selectbox("Select Quarter for 2D Graph Visualizer", available_clean_q, index=len(available_clean_q)-1, key="net_graph_q_select")
            net_parquet = C.DATA_CLEAN / f"{net_q}.parquet"
            
            with st.spinner("Rendering 2D Network Layout..."):
                fig_net = build_network_plotly_fig(str(net_parquet).replace("\\", "/"), net_res.get("anchor_partition", {}))
                if fig_net:
                    st.plotly_chart(fig_net, use_container_width=True)

        st.markdown("---")

        # Global Anchor Partition Breakdown Table
        st.markdown("#### 🎯 Global Anchor Community Partition")
        anchor_part = net_res.get("anchor_partition", {})
        if anchor_part:
            anchor_df = pd.DataFrame(
                list(anchor_part.items()), columns=["subreddit", "anchor_community_id"]
            )
            anchor_df["category"] = anchor_df["subreddit"].map(C.category_of)

            a_col1, a_col2 = st.columns([1, 1])
            with a_col1:
                st.dataframe(anchor_df, use_container_width=True, height=350, hide_index=True)
            with a_col2:
                comm_cat = anchor_df.groupby(["anchor_community_id", "category"]).size().reset_index(name="count")
                fig_comm = px.bar(
                    comm_cat,
                    x="anchor_community_id",
                    y="count",
                    color="category",
                    title="Category Composition per Anchor Community",
                    labels={"anchor_community_id": "Anchor Community ID", "count": "Subreddits Count"},
                )
                fig_comm.update_layout(height=350)
                st.plotly_chart(fig_comm, use_container_width=True)

        st.markdown("---")
        st.markdown("#### ⚖️ Position Stability vs. Person Stability Comparison (Hypothesis H1)")

        transitions = net_res.get("transitions", [])
        if not transitions:
            st.info(
                "ℹ️ **Single Quarter Mode Active**: Transition stability evaluation ($J_{position} \\text{ vs. } J_{person}$) requires "
                "at least 2 consecutive quarters (e.g. `2018Q1` and `2018Q2`). "
                "Currently, 1 quarter (`2018Q1`) has been processed. Interactive 2D backbone graph (30 backbone edges), 34 anchor communities, and 561 bridge positions are active above!"
            )
        else:
            trans_df = pd.DataFrame(transitions)
            
            t_col1, t_col2 = st.columns([1, 1])
            with t_col1:
                fig_stab = px.bar(
                    trans_df,
                    x="transition",
                    y=["position_stability", "person_stability"],
                    barmode="group",
                    title="Position Jaccard vs. Person Jaccard Stability",
                    labels={"value": "Jaccard Similarity", "variable": "Metric", "transition": "Transition"},
                    color_discrete_map={"position_stability": "#1E88E5", "person_stability": "#E53935"},
                )
                fig_stab.update_layout(height=350)
                st.plotly_chart(fig_stab, use_container_width=True)

            with t_col2:
                st.markdown("**Stability Gap Audit Table**")
                st.dataframe(
                    trans_df[
                        [
                            "transition",
                            "position_stability",
                            "person_stability",
                            "stability_gap",
                            "shared_positions_count",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )


# ============================================================ TAB 6: MANUAL REVIEW STUDIO
with tab_review:
    st.subheader("🛡️ Interactive Manual Bot Review Studio")
    st.caption(
        "Candidate accounts flagged during Stage 4 of the bot cascade. "
        "Select a quarter, edit verdicts directly in the table, and save results back to disk."
    )

    review_files = sorted(C.DATA_LOGS.glob("manual_review_*.csv"))

    if not review_files:
        st.info("No manual review CSV files found. Run `python clean.py` first.")
    else:
        q_labels = [f.stem.replace("manual_review_", "") for f in review_files]
        chosen_review_q = st.selectbox(
            "Select Review Quarter",
            q_labels,
            index=len(q_labels) - 1,
            key="review_quarter_select",
        )

        review_path = C.DATA_LOGS / f"manual_review_{chosen_review_q}.csv"
        review_df = pd.read_csv(review_path)

        if "verdict" not in review_df.columns:
            review_df["verdict"] = None
        if "notes" not in review_df.columns:
            review_df["notes"] = ""

        review_df["verdict"] = review_df["verdict"].fillna("")
        review_df["notes"] = review_df["notes"].fillna("")

        r_total = len(review_df)
        r_reviewed = int((review_df["verdict"] != "").sum())
        r_pending = r_total - r_reviewed
        r_keep = int((review_df["verdict"] == "keep").sum())
        r_bot = int((review_df["verdict"] == "bot").sum())
        r_spammer = int((review_df["verdict"] == "spammer").sum())

        rc1, rc2, rc3, rc4, rc5 = st.columns(5)
        rc1.metric("Total Candidates", r_total)
        rc2.metric("Pending Review", r_pending)
        rc3.metric("Verdict: Keep", r_keep)
        rc4.metric("Verdict: Bot", r_bot)
        rc5.metric("Verdict: Spammer", r_spammer)

        st.markdown("---")

        st.markdown("#### ✏️ Candidate Review Editor (Interactive)")
        st.info("💡 Double-click any cell in **Verdict** to choose `keep`, `bot`, or `spammer`, then click **Save Review Verdicts** below.")

        edited_df = st.data_editor(
            review_df,
            column_config={
                "author_h": st.column_config.TextColumn("Hashed Author (SHA256)", disabled=True),
                "n_comments": st.column_config.NumberColumn("Comments", disabled=True),
                "n_subs": st.column_config.NumberColumn("Subreddits", disabled=True),
                "ever_mod": st.column_config.NumberColumn("Mod Comments", disabled=True),
                "verdict": st.column_config.SelectboxColumn(
                    "Verdict",
                    options=["keep", "bot", "spammer"],
                    required=False,
                    help="Select human verdict",
                ),
                "notes": st.column_config.TextColumn("Notes / Justification"),
            },
            use_container_width=True,
            height=450,
            hide_index=True,
            key=f"data_editor_{chosen_review_q}",
        )

        col_save, col_dl = st.columns([1, 2])
        with col_save:
            if st.button("💾 Save Review Verdicts to Disk", use_container_width=True, type="primary"):
                edited_df.to_csv(review_path, index=False)
                st.success(f"Successfully saved verdicts to `{review_path.name}`!")
                st.rerun()

        with col_dl:
            st.download_button(
                "📥 Download Review List as CSV",
                edited_df.to_csv(index=False),
                file_name=f"manual_review_{chosen_review_q}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.markdown("---")
        st.markdown("#### 🔍 Candidate Account Deep-Dive Inspector")

        user_list = review_df["author_h"].tolist()
        selected_user = st.selectbox("Select Candidate Account to Inspect", user_list, key="candidate_inspector_select")

        clean_parquet_file = C.DATA_CLEAN / f"{chosen_review_q}.parquet"
        if clean_parquet_file.exists() and selected_user:
            user_subs = get_user_subreddit_breakdown(str(clean_parquet_file).replace("\\", "/"), selected_user)
            
            u1, u2 = st.columns([1, 1])
            with u1:
                st.markdown(f"**Subreddit Activity Breakdown for `{selected_user[:12]}...`**")
                st.dataframe(user_subs, use_container_width=True, hide_index=True)
            with u2:
                fig_u = px.pie(
                    user_subs,
                    names="subreddit",
                    values="comment_count",
                    title="Comment Concentration across Subreddits",
                )
                fig_u.update_layout(height=300)
                st.plotly_chart(fig_u, use_container_width=True)


# ============================================================ TAB 7: SYSTEM HEALTH & LOGS
with tab_health:
    st.subheader("📜 System Health, Logs & Configuration Inspector")

    h1, h2 = st.columns(2)

    with h1:
        st.markdown("#### ⚙️ Pipeline Configuration Parameters")
        config_data = {
            "Parameter": [
                "Default Start Date",
                "Default End Date",
                "Subreddit Frame Size",
                "Excluded Hub Subreddits",
                "Min Comments / Qtr",
                "Min Subreddits / Qtr",
                "Hugging Face Base Path",
            ],
            "Value": [
                f"{C.DEFAULT_START[0]}-{C.DEFAULT_START[1]:02d}",
                f"{C.DEFAULT_END[0]}-{C.DEFAULT_END[1]:02d}",
                f"{len(C.FRAME)} subreddits",
                ", ".join(C.EXCLUDED_HUBS),
                str(C.MIN_COMMENTS_PER_QUARTER),
                str(C.MIN_SUBS_PER_QUARTER),
                C.HF_BASE,
            ],
        }
        st.dataframe(pd.DataFrame(config_data), use_container_width=True, hide_index=True)

    with h2:
        st.markdown("#### 🎯 Sampling Frame Categories")
        frame_df = pd.DataFrame(list(C.FRAME.items()), columns=["Subreddit", "Category"]).sort_values(by="Category")
        st.dataframe(frame_df, use_container_width=True, height=280, hide_index=True)

    st.markdown("---")
    st.markdown("#### 📄 Pipeline Run Log Viewer (`pipeline.log`)")

    log_path = C.LOG_FILE
    if not log_path.exists():
        st.info("No log file found at `data/logs/pipeline.log` yet.")
    else:
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log_lines = f.readlines()
            
            l_col1, l_col2 = st.columns([1, 2])
            with l_col1:
                log_level = st.selectbox("Filter Log Level", ["ALL", "INFO", "WARNING", "ERROR"], key="log_level_filter")
            with l_col2:
                search_term = st.text_input("Search Log Text", "", key="log_search_text")

            filtered_logs = log_lines
            if log_level != "ALL":
                filtered_logs = [line for line in filtered_logs if log_level in line]
            if search_term:
                filtered_logs = [line for line in filtered_logs if search_term.lower() in line.lower()]

            st.text_area(
                f"Showing last {min(300, len(filtered_logs))} matching lines (Total: {len(log_lines)})",
                value="".join(filtered_logs[-300:]),
                height=400,
            )
        except Exception as e:
            st.error(f"Error reading log file: {e}")

st.divider()
st.caption(
    "🌉 **Bridge Brokers of Reddit Data Curation Dashboard** | Built with Streamlit, DuckDB, Plotly & iGraph"
)