"""
projection.py
=============
One-mode projection from bipartite user-subreddit matrix to subreddit-subreddit network,
weighted by Cosine Similarity on binary user presence (Step 2 of methodology).
"""

from __future__ import annotations
import numpy as np
import scipy.sparse as sp
import networkx as nx


def compute_cosine_projection(M: sp.csr_matrix, subreddits: list[str]) -> nx.Graph:
    """
    Computes one-mode subreddit-subreddit network projection using Cosine Similarity on Presence.
    
    Cosine similarity: W_ij = |U_i ∩ U_j| / sqrt(|U_i| * |U_j|)
    where U_i is the set of unique users who commented in subreddit i.
    
    Returns:
        nx.Graph with edges containing:
            - 'weight': float (cosine similarity 0.0 to 1.0)
            - 'shared_users': int (count of shared unique users)
    """
    # S[i,j] = number of shared unique users between sub_i and sub_j
    S = (M.T @ M).toarray()
    
    # User counts per subreddit (diagonal elements)
    user_counts = np.diag(S)
    
    n_subs = len(subreddits)
    G = nx.Graph()

    # Add all subreddits as nodes
    for s in subreddits:
        G.add_node(s, n_users=int(user_counts[subreddits.index(s)]))

    # Compute Cosine Weights for all pairs with > 0 shared users
    for i in range(n_subs):
        for j in range(i + 1, n_subs):
            shared = S[i, j]
            if shared > 0:
                denom = np.sqrt(user_counts[i] * user_counts[j])
                if denom > 0:
                    cosine_w = float(shared / denom)
                    G.add_edge(
                        subreddits[i],
                        subreddits[j],
                        weight=cosine_w,
                        shared_users=int(shared),
                    )

    return G

