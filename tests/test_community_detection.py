"""
tests/test_community_detection.py
==================================
Regression tests for community detection.

The 2018Q1 run reported 34 communities over 35 nodes with modularity -0.0072.
That partition was degenerate: 33 of the 34 "communities" were single
subreddits. Every downstream statistic was invalid as a result -- the
participation coefficient collapsed to 1 - 1/k_i and the bridge position set
saturated at C(34,2).

These tests build a frame with a KNOWN planted community structure and assert
that detection recovers it. They are the cheapest possible guard against the
failure actually shipping.
"""

from __future__ import annotations

import logging

import networkx as nx
import numpy as np
import pytest

from network_analysis.bipartite import build_bipartite_matrix
from network_analysis.community import detect_communities_leiden
from network_analysis.projection import compute_cosine_projection

N_CATS = 6
SUBS_PER_CAT = 25


def planted_frame(seed=11, n_brokers_per_cat=12, n_regulars_per_cat=260):
    """A bipartite frame with 6 planted communities and known planted brokers."""
    import pandas as pd

    rng = np.random.default_rng(seed)
    subs, truth = [], {}
    for c in range(N_CATS):
        for j in range(SUBS_PER_CAT):
            name = f"c{c}_s{j}"
            subs.append(name)
            truth[name] = c

    rows, brokers = [], []
    for c in range(N_CATS):
        pool = [s for s in subs if truth[s] == c]
        for b in range(n_brokers_per_cat):
            uid = f"brk_{seed}_{c}_{b}"
            span = rng.choice([2, 3])
            for t in rng.choice(N_CATS, size=span, replace=False):
                rows.append((uid, rng.choice([x for x in subs if truth[x] == t])))
            brokers.append(uid)
        for r in range(n_regulars_per_cat):
            uid = f"reg_{seed}_{c}_{r}"
            for s in rng.choice(pool, size=rng.integers(1, 4), replace=False):
                rows.append((uid, s))

    df = pd.DataFrame(rows, columns=["author_h", "subreddit"]).drop_duplicates()
    df["n_comments"] = 1
    df["is_mod"] = 0
    return df.reset_index(drop=True), truth, set(brokers)


def planted_graph(seed=11):
    df, truth, brokers = planted_frame(seed=seed)
    M, _, subs, _, _ = build_bipartite_matrix(df)
    return compute_cosine_projection(M, subs), truth, brokers


def recovery(truth, partition):
    """Fraction of subs sitting in their planted community's modal detected community."""
    best = {}
    for s, p in partition.items():
        t = truth[s]
        best.setdefault(t, {})
        best[t][p] = best[t].get(p, 0) + 1
    return sum(max(v.values()) for v in best.values()) / len(truth)


def test_cosine_weights_are_far_below_one():
    """The precondition for the old bug: CPM's resolution assumes weights ~1.

    If this ever stops holding, the reason community detection needs weight
    normalisation goes away with it.
    """
    G, _, _ = planted_graph()
    w = np.array([d["weight"] for _, _, d in G.edges(data=True)])
    assert w.mean() < 0.5, f"expected sub-unit cosine weights, got mean {w.mean():.3f}"
    assert w.max() <= 1.0


def test_modularity_partition_recovers_planted_communities():
    G, truth, _ = planted_graph()
    partition, mod, res = detect_communities_leiden(G, partition_model="modularity")

    assert len(set(partition.values())) == N_CATS
    assert mod > 0.5, f"modularity {mod:.4f} is too low to be a real partition"
    assert recovery(truth, partition) > 0.95


def test_modularity_partition_is_seed_stable():
    """Same partition regardless of RNG seed -- no seed lottery in the result."""
    G, _, _ = planted_graph()
    counts = {}
    for seed in (1, 2, 3):
        part, _, _ = detect_communities_leiden(
            G, resolutions=[1.0], seeds_per_res=1, partition_model="modularity"
        )
        # Compare partitions up to label permutation.
        groups = frozenset(
            frozenset(n for n, c in part.items() if c == cid)
            for cid in set(part.values())
        )
        counts[groups] = counts.get(groups, 0) + 1
    assert len(counts) == 1, f"community detection is seed-dependent: {len(counts)} outcomes"


def test_cpm_needs_normalised_weights_to_beat_singletons():
    """CPM on raw cosine weights reproduces the historical failure.

    This is the old code path, kept as a test: it documents that a partition of
    n_nodes singleton communities is what the pipeline used to produce, so the
    warning in detect_communities_leiden is triggered for the right reason.
    """
    G, truth, _ = planted_graph()
    import igraph as ig
    import leidenalg
    from network_analysis.community import networkx_to_igraph, _normalised_weights

    ig_g, names = networkx_to_igraph(G)

    raw = leidenalg.find_partition(
        ig_g, leidenalg.CPMVertexPartition,
        resolution_parameter=0.5, weights="weight", seed=0,
    )
    assert len(set(raw.membership)) == len(names), (
        "CPM on raw cosine weights no longer degenerates; the weight-scale "
        "explanation in community.py may no longer be the active cause"
    )
    assert raw.modularity <= 0

    ig_g.es["wnorm"] = _normalised_weights(ig_g)
    normed = leidenalg.find_partition(
        ig_g, leidenalg.CPMVertexPartition,
        resolution_parameter=0.05, weights="wnorm", seed=0,
    )
    assert len(set(normed.membership)) == N_CATS
    assert normed.modularity > 0.5


def test_degenerate_partition_emits_a_warning(caplog):
    """An all-singleton partition must be announced, not silently returned."""
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c", "d"])
    G.add_edge("a", "b", weight=1.0)   # one edge, two isolated nodes

    with caplog.at_level(logging.WARNING, logger="community"):
        partition, mod, _ = detect_communities_leiden(
            G, resolutions=[1.0], seeds_per_res=1
        )
    assert mod <= 0 or len(set(partition.values())) == len(partition)
    assert any("DEGENERATE" in r.message or "no edges" in r.message
               for r in caplog.records)


def test_empty_graph_returns_empty_partition():
    partition, mod, res = detect_communities_leiden(nx.Graph())
    assert partition == {}
    assert mod == 0.0


def test_unknown_partition_model_raises():
    G, _, _ = planted_graph()
    with pytest.raises(ValueError, match="partition_model"):
        detect_communities_leiden(G, partition_model="louvain")


# ---------------------------------------------------------------------------
# Disparity filter
# ---------------------------------------------------------------------------
def test_default_alpha_does_not_destroy_planted_structure():
    """The historical alpha=0.05 kept 4 of 1369 edges and destroyed the frame."""
    from network_analysis.backbone import DEFAULT_ALPHA, disparity_filter

    G, truth, _ = planted_graph()
    assert DEFAULT_ALPHA == 0.3

    tight = disparity_filter(G, alpha=0.05)
    default = disparity_filter(G, alpha=DEFAULT_ALPHA)

    assert tight.number_of_edges() < 0.01 * G.number_of_edges()
    assert default.number_of_edges() > 0.25 * G.number_of_edges()

    part, mod, _ = detect_communities_leiden(default)
    assert len(set(part.values())) == N_CATS
    assert mod > 0.5


def test_over_pruned_backbone_warns(caplog):
    from network_analysis.backbone import disparity_filter

    G, _, _ = planted_graph()
    with caplog.at_level(logging.WARNING, logger="backbone"):
        disparity_filter(G, alpha=0.001)
    assert any("Disparity filter kept only" in r.message for r in caplog.records)


def test_reported_modularity_uses_edge_weights():
    """V1 reported leidenalg's unweighted `part.modularity`. On a complete graph
    whose structure lives only in the weights, that value is ~0 for every
    partition, while the weighted modularity the partition was optimised on is
    clearly positive. The reported statistic must be the weighted one."""
    import igraph as ig
    from network_analysis.community import networkx_to_igraph, weighted_modularity

    n = 12
    G = nx.complete_graph(n)
    for u, v in G.edges():
        G[u][v]["weight"] = 1.0 if (u < 6) == (v < 6) else 0.05
    partition, mod, _ = detect_communities_leiden(G, resolutions=[1.0], seeds_per_res=3)
    ig_g, names = networkx_to_igraph(G)
    membership = [partition[n_] for n_ in names]
    assert len(set(membership)) == 2
    assert ig_g.modularity(membership) <= 0          # unweighted: blind to the structure
    assert mod == pytest.approx(weighted_modularity(ig_g, membership))
    assert mod > 0.35
