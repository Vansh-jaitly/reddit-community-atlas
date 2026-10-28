"""
backbone.py
===========
Implements the Serrano, Boguñá & Vespignani (2009) Disparity Filter for extracting
the multi-scale network backbone of weighted networks (Step 3 of methodology).

ON THE alpha DEFAULT:
    The historical default of alpha=0.05 is far too aggressive for a
    cosine-similarity weighted subreddit graph. Measured on a synthetic frame
    with 6 planted communities over 150 subreddits (1369 edges):
        alpha=0.05 ->    4 edges kept (0.3%), 146 communities,  6% recovery
        alpha=0.10 ->   45 edges kept (3.3%), 105 communities, 16% recovery
        alpha=0.30 ->  447 edges kept (32.7%),   6 communities, 100% recovery
        alpha=0.50 ->  890 edges kept (65.0%),   6 communities, 100% recovery
    Keeping a fraction of this many edges destroys the community structure that
    every downstream measure depends on. RETENTION_WARN_FRACTION guards against
    silently producing such a graph again.
"""

from __future__ import annotations
import logging

import networkx as nx

log = logging.getLogger("backbone")
if not log.handlers:
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)

# Below this fraction of retained edges the backbone has almost certainly
# destroyed the network's community structure rather than denoised it.
RETENTION_WARN_FRACTION = 0.10

DEFAULT_ALPHA = 0.3


def disparity_filter(G: nx.Graph, alpha: float = DEFAULT_ALPHA) -> nx.Graph:
    """
    Extracts multi-scale backbone using Serrano's disparity filter.
    
    Args:
        G: NetworkX Graph with weighted edges ('weight').
        alpha: Significance threshold (default: 0.05).
        
    Returns:
        Backbone nx.Graph containing preserved edges.
    """
    G_backbone = nx.Graph()
    G_backbone.add_nodes_from(G.nodes(data=True))

    # Precompute total strength for each node
    node_strength = {n: sum(data['weight'] for _, _, data in G.edges(n, data=True)) for n in G.nodes()}
    node_degree = {n: G.degree(n) for n in G.nodes()}

    preserved_edges = set()

    for u, v, data in G.edges(data=True):
        w = data['weight']

        # Node u direction
        k_u = node_degree[u]
        if k_u > 1 and node_strength[u] > 0:
            p_uv = w / node_strength[u]
            alpha_uv = (1.0 - p_uv) ** (k_u - 1)
        else:
            alpha_uv = 0.0  # Keep edge if degree is 1

        # Node v direction
        k_v = node_degree[v]
        if k_v > 1 and node_strength[v] > 0:
            p_vu = w / node_strength[v]
            alpha_vu = (1.0 - p_vu) ** (k_v - 1)
        else:
            alpha_vu = 0.0

        # Preserve edge if statistically significant for either node
        if alpha_uv < alpha or alpha_vu < alpha:
            preserved_edges.add((u, v))

    for u, v in preserved_edges:
        G_backbone.add_edge(u, v, **G[u][v])

    n_in, n_out = G.number_of_edges(), G_backbone.number_of_edges()
    if n_in and n_out / n_in < RETENTION_WARN_FRACTION:
        log.warning(
            "Disparity filter kept only %d/%d edges (%.1f%%) at alpha=%.3f. "
            "This much pruning will break community detection downstream "
            "(communities collapse toward singletons, the participation "
            "coefficient degenerates to 1 - 1/k_i, and bridge positions "
            "saturate). Raise alpha or sweep it before trusting any result.",
            n_out, n_in, 100 * n_out / n_in, alpha,
        )

    return G_backbone

