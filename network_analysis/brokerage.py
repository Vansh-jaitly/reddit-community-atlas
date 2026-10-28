"""
brokerage.py
============
Computes Participation Coefficient P_i (Guimerà & Amaral, 2005) to identify
cross-community brokers (Step 6 of methodology). P is used as a CONTINUOUS
role measure; the top percentile is a descriptive operational set only, not a
literature-derived constant. Burt's Constraint is NOT computed here.

METHODOLOGICAL DEPENDENCY: P and broker identification are CONDITIONAL on
the detected community partition -- communities define the modules P is
computed over. Bridge positions therefore inherit dependence on
community-detection choices. Do not treat P as an independent measurement:
seed stability and resolution diagnostics are mandatory upstream gates before
any broker-based longitudinal claim.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def compute_participation_coefficients(
    bipartite_df: pd.DataFrame,
    community_partition: dict[str, int],
    broker_percentile: float = 0.99,
) -> pd.DataFrame:
    """
    Computes Participation Coefficient P_i for each active user.
    
    P_i = 1 - sum_{c=1}^M (k_ic / k_i)^2
    where k_ic is user i's degree to community c, and k_i is user i's total degree.
    
    Args:
        bipartite_df: DataFrame with ['author_h', 'subreddit', 'n_comments', 'is_mod']
        community_partition: dict mapping subreddit -> community_id
        broker_percentile: cutoff threshold for broker classification (default 0.99 for top 1%)
        
    Returns:
        DataFrame with user metrics:
            ['author_h', 'P', 'total_degree', 'n_subs', 'n_communities', 'is_mod', 'is_broker']
    """
    # Filter to subreddits present in the community partition
    df = bipartite_df[bipartite_df["subreddit"].isin(community_partition)].copy()
    if df.empty:
        return pd.DataFrame()

    df["community"] = df["subreddit"].map(community_partition)

    # Group by author and community to get k_ic.
    # k_ic is the user's strength of tie to community c, so it must be the
    # summed comment count. `groupby(...).size()` counted ROWS in an input that
    # load_bipartite_dataframe() had already aggregated to one row per
    # (author, subreddit), making k_ic == 1 for every user and collapsing
    # P_i to 1 - 1/k_i -- a pure function of breadth. A user with a perfectly
    # balanced 1000/1000 split and a 1999/1 monopolist both scored 0.5, so the
    # participation coefficient measured nothing about engagement balance and
    # is_broker silently reduced to "posts in many subreddits".
    user_comm = (
        df.groupby(["author_h", "community"])["n_comments"].sum()
          .reset_index(name="k_ic")
    )
    user_totals = df.groupby("author_h").agg(
        total_degree=("n_comments", "sum"),
        n_subs=("subreddit", "nunique"),
        is_mod=("is_mod", "max"),
    ).reset_index()

    merged = user_comm.merge(user_totals, on="author_h")
    merged["prop_sq"] = (merged["k_ic"] / merged["total_degree"]) ** 2

    # Aggregate P_i per user
    user_p = merged.groupby("author_h").agg(
        P=("prop_sq", lambda s: float(1.0 - s.sum())),
        n_communities=("community", "nunique"),
    ).reset_index()

    user_metrics = user_totals.merge(user_p, on="author_h")

    # Determine broker threshold (top 1% among users spanning >= 2 subreddits)
    multicomm_users = user_metrics[user_metrics["n_communities"] >= 2]
    if not multicomm_users.empty:
        p_cutoff = multicomm_users["P"].quantile(broker_percentile)
    else:
        p_cutoff = 0.5

    user_metrics["is_broker"] = (user_metrics["n_communities"] >= 2) & (user_metrics["P"] >= p_cutoff)
    user_metrics = user_metrics.sort_values(by=["P", "total_degree"], ascending=False)

    return user_metrics

