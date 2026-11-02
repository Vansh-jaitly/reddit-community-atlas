"""Candidate selection for the focused community: every candidate's reply network over the same window, same metrics.

The window is one quarter so that fourteen candidates are compared on equal footing at bounded cost; the chosen
community is then rebuilt over the whole year. Betweenness on graphs above BIG_N nodes uses a path cutoff.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as F
from . import io as IO
from . import networks as N

BIG_N = 15000


def candidate_row(sub: str, start: str, end: str, raw_text=None) -> dict:
    df = IO.comments([sub], start, end, raw_text=raw_text)
    if df.empty:
        return {"subreddit": sub, "comments": 0, "note": "no data in window"}
    deleted_share = float(df["author_h"].isna().mean())
    e = N.reply_edges(df)
    g = N.build_graph(e)
    if g.vcount() == 0:
        return {"subreddit": sub, "comments": int(len(df)), "note": "no reply edges"}
    comm = N.communities(g)
    memb = comm["membership"]
    s = N.summary(g, comm)
    null = N.null_modularity(g, n=5)
    # centralities: path cutoff keeps big graphs tractable; the ranking is what matters here
    n = g.vcount()
    cutoff = 6 if n > BIG_N else None
    btw = np.array(g.betweenness(directed=False, cutoff=cutoff))
    btw_share_top5 = float(np.sort(btw)[::-1][:5].sum() / btw.sum()) if btw.sum() > 0 else 0.0
    P = N.participation(g, memb)
    reached = np.array([len({memb[u] for u in g.neighbors(v)}) for v in range(n)])
    top5pct = btw >= np.quantile(btw, 0.95) if n >= 20 else btw > 0
    bridges = int(((P >= 0.6) & (reached >= 3) & top5pct).sum())
    groups = N.user_groups(df, sub)
    gvec = [groups.get(v["name"]) for v in g.vs]
    flair_cov = float(np.mean([x is not None for x in gvec]))
    ei = N.ei_index(g, gvec) if flair_cov > 0.2 else None
    core, cover = N.readable_core(g)
    sizes = s["community_sizes"]
    return {
        "subreddit": sub, "comments": int(len(df)), "replies": int(e["w"].sum()), "deleted_author_share": round(deleted_share, 3),
        "nodes": s["nodes"], "edges": s["edges"], "density": s["density"], "mean_degree": s["mean_degree"],
        "components": s["components"], "largest_component_share": s["largest_component_share"], "reciprocity": s["reciprocity"],
        "modularity": s["modularity"], "null_modularity": round(null["mean"], 3) if null["mean"] is not None else None,
        "modularity_unweighted": s["modularity_unweighted"],
        "modularity_excess": round(s["modularity_unweighted"] - null["mean"], 3) if null["mean"] is not None else None,   # unweighted vs unweighted null
        "seed_ari": s["seed_ari"], "communities_ge5": int(s.get("communities_ge5", sum(1 for x in sizes if x >= 5))), "largest_community_share": round(sizes[0] / s["nodes"], 3) if sizes else None,
        "avg_clustering": s["avg_clustering"], "betweenness_top5_share": round(btw_share_top5, 3), "bridge_users": bridges,
        "flair_group_coverage": round(flair_cov, 3), "ei_index": None if ei is None else round(ei, 3),
        "core_k": cover["k"], "core_nodes": cover["nodes"], "core_edge_share": cover["edge_share"],
        "has_text": sub in F.TEXT_SUBS,
    }


def candidate_matrix(start: str = "2018-04-01", end: str = "2018-06-30", subs: list[str] | None = None, raw_text=None) -> pd.DataFrame:
    rows = [candidate_row(s, start, end, raw_text=raw_text) for s in (subs or F.CANDIDATES)]
    return pd.DataFrame(rows)


def score(df: pd.DataFrame) -> pd.DataFrame:
    """Transparent 0-1 scores per column of the selection matrix (documented in the research note)."""
    out = df.copy()
    r = lambda col, lo, hi: ((out[col].astype(float) - lo) / (hi - lo)).clip(0, 1)   # noqa: E731
    out["network_quality"] = (0.4 * r("largest_component_share", 0.3, 0.9) + 0.3 * r("avg_clustering", 0.02, 0.2) + 0.3 * r("reciprocity", 0.1, 0.5)).round(2)
    out["community_structure"] = (0.5 * r("modularity_excess", 0.0, 0.25) + 0.3 * r("communities_ge5", 2, 12) + 0.2 * (1 - r("largest_community_share", 0.2, 0.7))).round(2)
    out["interesting_patterns"] = (0.4 * r("bridge_users", 0, 15) + 0.3 * r("betweenness_top5_share", 0.1, 0.5) + 0.3 * r("flair_group_coverage", 0.0, 0.5)).round(2)
    out["data_completeness"] = (0.6 * (1 - r("deleted_author_share", 0.03, 0.2)) + 0.4 * r("core_edge_share", 0.05, 0.5)).round(2)
    out["storytelling"] = (0.4 * out["has_text"].astype(float) + 0.3 * r("flair_group_coverage", 0.0, 0.5) + 0.3 * r("ei_index", -1, 0).fillna(0)).round(2)
    out["total"] = (out[["network_quality", "community_structure", "interesting_patterns", "data_completeness", "storytelling"]].sum(axis=1)).round(2)
    return out.sort_values("total", ascending=False)
