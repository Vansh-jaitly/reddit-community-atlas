"""
Recompute the V1 community-quality numbers with edge weights, without
touching the historical V1 output (data_curation/data/logs/network_results.json).

V1 stored leidenalg's `part.modularity`, which igraph computes WITHOUT edge
weights. This tool rebuilds each V1 cosine graph from the cleaned data and
scores the stored V1 partitions both ways.

Usage:  python tools/audit_v1_modularity.py
Writes: data_curation/data/logs/v1_modularity_audit.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import igraph as ig
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from network_analysis.affinity import cooccurrence, load_presence  # noqa: E402

LOGS = ROOT / "data_curation/data/logs"
CLEAN = ROOT / "data_curation/data/clean"


def cosine_graph(paths, subs):
    M, subs = load_presence(paths, subreddits=subs)
    V = cooccurrence(M).astype(float)
    k = np.diag(V).copy()
    iu = np.triu_indices(len(subs), 1)
    w = V[iu] / np.sqrt(k[iu[0]] * k[iu[1]])
    keep = V[iu] > 0
    g = ig.Graph(n=len(subs), edges=list(zip(iu[0][keep], iu[1][keep])))
    g.es["weight"] = w[keep]
    return g


def score(g, subs, partition):
    mem = [partition[s] for s in subs]
    rng = np.random.default_rng(0)
    null = [g.modularity(list(rng.permutation(mem)), weights="weight") for _ in range(200)]
    return {
        "communities": len(set(mem)),
        "stored_unweighted_q": round(g.modularity(mem), 4),
        "weighted_q": round(g.modularity(mem, weights="weight"), 4),
        "shuffled_label_weighted_q_mean": round(float(np.mean(null)), 4),
        "shuffled_label_weighted_q_max": round(float(np.max(null)), 4),
        "density": round(g.density(), 4),
    }


def main():
    v1 = json.loads((LOGS / "network_results.json").read_text())
    subs = sorted(v1["anchor_partition"])
    quarters = sorted(v1["quarter_results"])
    out = {"note": "V1 stored unweighted modularity; weighted_q is the quality of the same partitions on the "
                   "weighted cosine graph they were optimised on. network_results.json is left unchanged.",
           "anchor_pooled": score(cosine_graph([CLEAN / f"{q}.parquet" for q in quarters], subs), subs, v1["anchor_partition"])}
    for q in quarters:
        out[q] = score(cosine_graph([CLEAN / f"{q}.parquet"], subs), subs, v1["quarter_results"][q]["community_partition"])
    (LOGS / "v1_modularity_audit.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
