"""
community.py
============
Leiden community detection (Traag, Waltman & van Eck, 2019) with a resolution and
seed sweep to identify stable community structures (Step 4 of methodology).

WHY THIS MODULE USED TO PRODUCE 150 SINGLETON "COMMUNITIES"
-----------------------------------------------------------
The original version ran leidenalg's CPMVertexPartition with
`resolution_parameter` in [0.5 ... 1.5] directly on the cosine-similarity
weighted subreddit graph. Cosine weights live in (0, 1) and average ~0.07 on a
real frame, but CPM's resolution parameter is calibrated for weights of order 1.
The gamma penalty therefore overwhelmed the internal edge weight and every node
was split off into its own community.

Two further mistakes compounded it: CPM was asked to optimise one objective
while `part.modularity` -- a different objective -- was reported and used to
pick the best resolution, and no check ever asked whether the chosen partition
was degenerate.

Measured on a synthetic frame with 6 planted communities over 150 subreddits:
    CPM, raw cosine weights, res 0.5-1.5  -> 150 communities, modularity -0.007
    RBConfiguration (modularity, gamma=1) ->   6 communities, modularity  0.730
CPM with weights renormalised to mean 1 also recovers 6 communities, at
res 0.05-0.1.

So: modularity is the default objective here, because it is scale-free, it is
what the project reports, and selecting on it is then coherent.
"""

from __future__ import annotations
import logging

import igraph as ig
import leidenalg
import networkx as nx
import numpy as np

log = logging.getLogger("community")
if not log.handlers:
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)


def networkx_to_igraph(G: nx.Graph) -> tuple[ig.Graph, list[str]]:
    """Converts a NetworkX graph to an igraph Graph."""
    nodes = list(G.nodes())
    node_to_idx = {n: i for i, n in enumerate(nodes)}

    edges = [(node_to_idx[u], node_to_idx[v]) for u, v in G.edges()]
    weights = [G[u][v].get('weight', 1.0) for u, v in G.edges()]

    ig_g = ig.Graph(n=len(nodes), edges=edges, directed=False)
    ig_g.es['weight'] = weights
    ig_g.vs['name'] = nodes

    return ig_g, nodes


def weighted_modularity(ig_g: ig.Graph, membership: list[int], weight_attr: str = "weight") -> float:
    """Modularity of `membership` using the edge weights the partition was optimised on.

    leidenalg's `part.modularity` delegates to igraph's Graph.modularity()
    WITHOUT weights. On the V1 cosine graph (99.85% dense) that unweighted
    value is ~0 for any partition, which is why V1 reported Q = -0.004 for a
    partition whose weighted modularity is +0.125 (see
    data_curation/data/logs/v1_modularity_audit.json). Report this instead.
    """
    return float(ig_g.modularity(list(membership), weights=weight_attr))


def _normalised_weights(ig_g: ig.Graph) -> list[float]:
    """Rescale edge weights to mean 1.

    Only needed for CPM, whose resolution parameter assumes weights of order 1.
    A zero-variance or all-zero weight set is mapped to all-ones so CPM falls
    back to unweighted behaviour instead of dividing by zero.
    """
    w = np.asarray(ig_g.es["weight"], dtype=float)
    if w.size == 0:
        return []
    mean = float(w.mean())
    if mean <= 0 or np.isclose(mean, 0.0):
        return np.ones_like(w).tolist()
    return (w / mean).tolist()


def detect_communities_leiden(
    G: nx.Graph,
    resolutions: list[float] = [0.5, 0.8, 1.0, 1.2, 1.5],
    seeds_per_res: int = 5,
    partition_model: str = "modularity",
) -> tuple[dict[str, int], float, float]:
    """
    Runs Leiden with a resolution x seed sweep and returns the best partition.

    Args:
        G: weighted NetworkX graph (edge attribute 'weight').
        resolutions: resolution parameters to sweep. For modularity, 1.0 is
            standard modularity and values below 1 merge more aggressively.
        seeds_per_res: random seeds per resolution, to expose seed sensitivity.
        partition_model: "modularity" (default, scale-free and matches the
            reported statistic) or "cpm" (Constant Potts Model, better for small
            communities; weights are renormalised to mean 1 so the resolution
            parameter is on a comparable scale to the unnormalised case).

    Returns:
        partition_dict: {node_name: community_id}
        best_modularity: modularity of the selected partition
        best_resolution: the resolution parameter that produced it
    """
    if len(G.nodes()) == 0:
        return {}, 0.0, 1.0

    ig_g, node_names = networkx_to_igraph(G)

    if partition_model == "cpm":
        weight_attr = "weight_norm"
        ig_g.es[weight_attr] = _normalised_weights(ig_g)
    elif partition_model == "modularity":
        weight_attr = "weight"
    else:
        raise ValueError(
            f"partition_model must be 'modularity' or 'cpm', got {partition_model!r}"
        )

    best_partition = None
    best_modularity = -np.inf
    best_res = 1.0

    for res in resolutions:
        for seed in range(seeds_per_res):
            part = leidenalg.find_partition(
                ig_g,
                _partition_class(partition_model),
                resolution_parameter=res,
                weights=weight_attr,
                seed=seed,
            )
            mod = weighted_modularity(ig_g, part.membership)
            if mod > best_modularity:
                best_modularity = mod
                best_partition = part
                best_res = res

    if best_partition is None:
        partition_dict = {n: 0 for n in node_names}
        return partition_dict, 0.0, 1.0

    membership = list(best_partition.membership)
    partition_dict = {node_names[i]: int(comm_id) for i, comm_id in enumerate(membership)}

    n_comms = len(set(partition_dict.values()))
    n_nodes = len(node_names)
    n_edges = ig_g.ecount()
    if best_modularity <= 0 or n_comms == n_nodes:
        log.warning(
            "DEGENERATE PARTITION: %d communities over %d nodes from %d edges, "
            "modularity %.4f. Every downstream measure is invalid on this "
            "partition -- the participation coefficient collapses to 1 - 1/k_i "
            "when communities are singletons, and the bridge position set "
            "saturates at C(n,2). Do not report results from this run.",
            n_comms, n_nodes, n_edges, best_modularity,
        )
    if n_edges == 0:
        log.warning(
            "Graph has no edges; every node is its own community by "
            "construction. Check the projection and the disparity filter alpha."
        )

    log.info(
        "Leiden (%s): %d communities over %d nodes, modularity %.4f at resolution %.2f",
        partition_model, n_comms, n_nodes, best_modularity, best_res,
    )
    return partition_dict, float(best_modularity), float(best_res)


def _partition_class(partition_model: str):
    """Map a model name to its leidenalg partition class.

    "modularity" maps to RBConfigurationVertexPartition, NOT
    ModularityVertexPartition: the latter is modularity fixed at gamma=1 and
    accepts no `resolution_parameter` in leidenalg 0.12, so the resolution sweep
    could not be applied to it. RBConfiguration is the same objective generalised
    by gamma -- at gamma=1.0 it is exactly modularity -- and it does accept the
    sweep. `part.modularity` is available on it, so the reported statistic stays
    modularity and selecting on modularity stays coherent.
    """
    if partition_model == "cpm":
        return leidenalg.CPMVertexPartition
    if partition_model == "modularity":
        return leidenalg.RBConfigurationVertexPartition
    raise ValueError(
        f"partition_model must be 'modularity' or 'cpm', got {partition_model!r}"
    )


def partitions_at_fixed_resolution(
    G: nx.Graph, resolution: float = 1.0,
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
    partition_model: str = "modularity",
) -> list[dict[str, int]]:
    """One partition per fixed seed at a single frozen resolution.

    The primary analysis NEVER sweeps gamma to find a nicer result: gamma=1 is
    the frozen primary setting and the sweep is robustness analysis only. This
    helper produces the five seeded partitions the seed-agreement diagnostic
    consumes.
    """
    ig_g, node_names = networkx_to_igraph(G)
    weight_attr = "weight"
    if partition_model == "cpm":
        weight_attr = "weight_norm"
        ig_g.es[weight_attr] = _normalised_weights(ig_g)
    out = []
    for seed in seeds:
        part = leidenalg.find_partition(
            ig_g,
            _partition_class(partition_model),
            resolution_parameter=resolution,
            weights=weight_attr,
            seed=seed,
        )
        out.append({node_names[i]: int(c)
                    for i, c in enumerate(part.membership)})
    return out


def seed_agreement(partitions: list[dict[str, int]]) -> dict:
    """Mean pairwise ARI/NMI across seeded partitions at one resolution.

    Answers exactly one question: is the partition seed-stable? Node labels are
    aligned on the shared node set (the fixed subreddit frame), so ARI/NMI are
    valid here. Failure rule: mean ARI < 0.60 -> no partition-dependent
    longitudinal inference.
    """
    from sklearn.metrics import adjusted_rand_score, \
        normalized_mutual_info_score
    if len(partitions) < 2:
        return {"n_seeds": len(partitions), "mean_ari": None, "mean_nmi": None,
                "note": "need >= 2 seeded partitions"}
    nodes = sorted(partitions[0])
    labels = [[p[n] for n in nodes] for p in partitions]
    aris, nmis = [], []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            aris.append(float(adjusted_rand_score(labels[i], labels[j])))
            nmis.append(float(normalized_mutual_info_score(labels[i], labels[j])))
    return {
        "n_seeds": len(partitions),
        "mean_ari": round(float(np.mean(aris)), 4),
        "mean_nmi": round(float(np.mean(nmis)), 4),
        "min_ari": round(float(np.min(aris)), 4),
    }


def resolution_profile(
    G: nx.Graph, resolutions: list[float] | None = None,
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
    partition_model: str = "modularity",
) -> list[dict]:
    """Compact robustness table around the frozen primary gamma.

    This is REPORTED, never selected on: the primary partition always comes
    from gamma=1. Each row gives community count, modularity, and seed
    agreement at that resolution.
    """
    if resolutions is None:
        resolutions = [0.5, 0.8, 1.0, 1.2, 1.5]
    rows = []
    for res in resolutions:
        parts = partitions_at_fixed_resolution(
            G, resolution=res, seeds=seeds, partition_model=partition_model)
        agree = seed_agreement(parts)
        ig_g, node_names = networkx_to_igraph(G)
        weight_attr = "weight"
        if partition_model == "cpm":
            weight_attr = "weight_norm"
            ig_g.es[weight_attr] = _normalised_weights(ig_g)
        mod = weighted_modularity(ig_g, leidenalg.find_partition(
            ig_g, _partition_class(partition_model),
            resolution_parameter=res,
            weights=weight_attr,
            seed=seeds[0]).membership)
        rows.append({
            "resolution": res,
            "n_communities": len(set(parts[0].values())),
            "modularity": round(mod, 4),
            "mean_seed_ari": agree["mean_ari"],
            "mean_seed_nmi": agree["mean_nmi"],
        })
    return rows

