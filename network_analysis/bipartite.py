"""
bipartite.py
============
Loads clean quarterly Parquet data using DuckDB, constructs sparse user-subreddit
interaction matrices, and computes user degrees and subreddit presence.
"""

from __future__ import annotations
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix


def load_bipartite_dataframe(parquet_path: Path | str) -> pd.DataFrame:
    """Loads bipartite user-subreddit interactions from parquet file via DuckDB."""
    parquet_str = str(parquet_path).replace("\\", "/")
    con = duckdb.connect()
    df = con.execute(
        f"""
        SELECT 
            author_h, 
            subreddit, 
            COUNT(*) AS n_comments, 
            MAX(CAST(is_mod AS INTEGER)) AS is_mod
        FROM '{parquet_str}'
        GROUP BY author_h, subreddit
        """
    ).df()
    con.close()
    return df


def build_bipartite_matrix(df: pd.DataFrame):
    """
    Constructs a sparse binary (presence) matrix M where M[u, s] = 1 if user u commented in sub s.
    
    Returns:
        M: scipy.sparse.csr_matrix (n_users, n_subs)
        users: list of user author_h strings
        subreddits: list of subreddit strings
        user_to_idx: dict mapping author_h to row index
        sub_to_idx: dict mapping subreddit to column index
    """
    users = sorted(df["author_h"].unique())
    subreddits = sorted(df["subreddit"].unique())

    user_to_idx = {u: i for i, u in enumerate(users)}
    sub_to_idx = {s: j for j, s in enumerate(subreddits)}

    rows = df["author_h"].map(user_to_idx).values
    cols = df["subreddit"].map(sub_to_idx).values
    data = np.ones(len(df), dtype=np.float64)

    M = csr_matrix((data, (rows, cols)), shape=(len(users), len(subreddits)))
    return M, users, subreddits, user_to_idx, sub_to_idx

