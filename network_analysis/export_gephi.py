"""
export_gephi.py
===============
Exports the Serrano Disparity Filter backbone network and Leiden community clusters
into standard GEXF (.gexf) and CSV format for visualization in Gephi.

VISUALIZATION ONLY: backbone communities exported here are display attributes, not inferential results. The primary analysis runs Leiden on the FULL cosine-weighted network; the backbone-filtered graph partitions differently by construction. Never cite these community labels as findings.

Generates:
  - data/gephi/network_backbone_<quarter>.gexf (Native Gephi XML network file)
  - data/gephi/nodes_<quarter>.csv (Node table with Leiden community IDs & categories)
  - data/gephi/edges_<quarter>.csv (Edge table with Cosine presence weights W_ij)
"""

from __future__ import annotations
from pathlib import Path
import sys

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import networkx as nx
import pandas as pd
import data_curation.config as C
from network_analysis.bipartite import load_bipartite_dataframe, build_bipartite_matrix
from network_analysis.projection import compute_cosine_projection
from network_analysis.backbone import disparity_filter
from network_analysis.community import detect_communities_leiden

GEPHI_DIR = C.DATA_LOGS.parent / "gephi"
GEPHI_DIR.mkdir(parents=True, exist_ok=True)


def export_to_gephi(quarter: str = "2018Q1", alpha: float = 0.3):
    parquet_path = C.DATA_CLEAN / f"{quarter}.parquet"
    if not parquet_path.exists():
        print(f"❌ Clean parquet file not found for {quarter}: {parquet_path}")
        return

    print(f"📦 Loading {quarter} data for Gephi export...")
    df = load_bipartite_dataframe(str(parquet_path))
    if df.empty:
        print(f"❌ DataFrame for {quarter} is empty.")
        return

    M, users, subs, _, _ = build_bipartite_matrix(df)
    G_proj = compute_cosine_projection(M, subs)
    G_backbone = disparity_filter(G_proj, alpha=alpha)
    partition, modularity, _ = detect_communities_leiden(G_backbone)

    print(f"🕸️ Backbone Graph: {G_backbone.number_of_nodes()} nodes, {G_backbone.number_of_edges()} edges")
    print(f"🎯 Leiden Modularity: {modularity:.4f}")

    # Attach attributes to NetworkX graph for GEXF export
    for node in G_backbone.nodes():
        G_backbone.nodes[node]["label"] = f"r/{node}"
        G_backbone.nodes[node]["category"] = C.FRAME.get(node, "other / hub")
        G_backbone.nodes[node]["leiden_community"] = int(partition.get(node, 0))

    # 1. Export GEXF File for Gephi
    gexf_path = GEPHI_DIR / f"network_backbone_{quarter}.gexf"
    nx.write_gexf(G_backbone, gexf_path)
    print(f"✅ Exported Gephi GEXF file: {gexf_path}")

    # 2. Export Node CSV for Gephi
    nodes_data = []
    for node in G_backbone.nodes():
        nodes_data.append({
            "Id": node,
            "Label": f"r/{node}",
            "Category": C.FRAME.get(node, "other / hub"),
            "Leiden_Community": partition.get(node, 0),
            "Degree": G_backbone.degree(node),
            "Users_Count": G_backbone.nodes[node].get("n_users", 0),
        })
    nodes_df = pd.DataFrame(nodes_data)
    nodes_path = GEPHI_DIR / f"nodes_{quarter}.csv"
    nodes_df.to_csv(nodes_path, index=False)
    print(f"✅ Exported Gephi Nodes CSV: {nodes_path}")

    # 3. Export Edge CSV for Gephi
    edges_data = []
    for u, v, d in G_backbone.edges(data=True):
        edges_data.append({
            "Source": u,
            "Target": v,
            "Weight": d.get("weight", 0.0),
            "Type": "Undirected",
        })
    edges_df = pd.DataFrame(edges_data)
    edges_path = GEPHI_DIR / f"edges_{quarter}.csv"
    edges_df.to_csv(edges_path, index=False)
    print(f"✅ Exported Gephi Edges CSV: {edges_path}")

    print("\n🎉 Gephi Export Complete! Open Gephi -> File -> Open -> Select network_backbone_2018Q1.gexf")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Gephi visualization export (display only).")
    ap.add_argument("--quarter", default="2018Q1")
    ap.add_argument("--alpha", type=float, default=0.3,
                    help="visualization backbone only")
    a = ap.parse_args()
    export_to_gephi(a.quarter, alpha=a.alpha)
