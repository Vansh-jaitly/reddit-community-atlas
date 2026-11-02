"""Reply networks for one subreddit and time window.

An edge is a real interaction present in the data: user A wrote a comment whose parent comment was written by
user B (parent_id = t1_<id of B's comment>). Replies to posts (t3_ parents) have no author in the comment
store and create no edge; self-replies are dropped. The graph used for communities and centralities is the
undirected weighted simplification (weight = replies in both directions); direction is kept for reciprocity.
"""
from __future__ import annotations

import math
import re

import igraph as ig
import leidenalg
import numpy as np
import pandas as pd

from . import config as F


# ---- construction --------------------------------------------------------------------------------
def reply_edges(df: pd.DataFrame) -> pd.DataFrame:
    """Directed reply edges replier -> parent author, counted, from a comments frame (id, parent_id, author_h)."""
    author_of = df.drop_duplicates("id").set_index("id")["author_h"]
    rep = df[df["parent_id"].str.startswith("t1_", na=False) & df["author_h"].notna()].copy()
    rep["dst"] = rep["parent_id"].str[3:].map(author_of)
    rep = rep.dropna(subset=["dst"])
    rep = rep[rep["author_h"] != rep["dst"]]
    e = rep.groupby(["author_h", "dst"]).size().reset_index(name="w")
    return e.rename(columns={"author_h": "src"})


def build_graph(edges: pd.DataFrame, min_replies: int = F.MIN_REPLIES_NODE) -> ig.Graph:
    """Undirected weighted graph; vertices with fewer than `min_replies` reply interactions are dropped."""
    if edges.empty:
        return ig.Graph()
    und = edges.assign(a=np.where(edges["src"] < edges["dst"], edges["src"], edges["dst"]),
                       b=np.where(edges["src"] < edges["dst"], edges["dst"], edges["src"]))
    und = und.groupby(["a", "b"], as_index=False)["w"].sum()
    g = ig.Graph.TupleList(und[["a", "b", "w"]].itertuples(index=False), directed=False, edge_attrs=["w"])
    g.vs["name"] = [str(n) for n in g.vs["name"]]
    strength = np.array(g.strength(weights="w"))
    keep = np.where(strength >= min_replies)[0]
    g = g.induced_subgraph(keep)
    # directed counts for reciprocity, re-attached after filtering
    names = set(g.vs["name"])
    d = edges[edges["src"].isin(names) & edges["dst"].isin(names)]
    pair = {(r.src, r.dst): int(r.w) for r in d.itertuples(index=False)}
    recip = 0
    for (s, t), w in pair.items():
        if (t, s) in pair:
            recip += 1
    g["reciprocity"] = recip / len(pair) if pair else 0.0
    g["directed_edges"] = len(pair)
    return g


# ---- structure -----------------------------------------------------------------------------------
def communities(g: ig.Graph, seeds: int = F.LEIDEN_SEEDS, resolution: float = F.LEIDEN_RESOLUTION) -> dict:
    """Leiden (modularity) on the weighted graph, best of `seeds`; agreement between seeds as mean ARI and AMI."""
    if g.vcount() == 0:
        return {"membership": [], "modularity": 0.0, "seed_ari": None, "seed_ami": None}
    from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score
    parts = []
    for s in range(seeds):
        p = leidenalg.find_partition(g, leidenalg.RBConfigurationVertexPartition, weights="w", resolution_parameter=resolution, seed=s, n_iterations=-1)
        parts.append((p.quality() / (2 * sum(g.es["w"])) if g.ecount() else 0.0, list(p.membership)))
    parts.sort(key=lambda x: -x[0])
    best = parts[0]
    q = g.modularity(best[1], weights="w") if g.ecount() else 0.0
    aris = [adjusted_rand_score(best[1], m) for _, m in parts[1:]]
    amis = [adjusted_mutual_info_score(best[1], m) for _, m in parts[1:]]
    # relabel communities by size (0 = largest)
    sizes = pd.Series(best[1]).value_counts()
    order = {c: k for k, c in enumerate(sizes.index)}
    memb = [order[c] for c in best[1]]
    return {"membership": memb, "modularity": float(q), "seed_ari": float(np.mean(aris)) if aris else None,
            "seed_ami": float(np.mean(amis)) if amis else None, "seeds": seeds}


def infomap_check(g: ig.Graph, memb: list[int], trials: int = 10) -> dict:
    """A flow-based partition (map equation) as a cross-check on the modularity partition."""
    if g.ecount() == 0:
        return {}
    from sklearn.metrics import adjusted_mutual_info_score
    im = g.community_infomap(edge_weights="w", trials=trials)
    return {"modules": len(im), "ami_vs_leiden": round(float(adjusted_mutual_info_score(memb, im.membership)), 3),
            "largest_module_share": round(max(len(c) for c in im) / g.vcount(), 3)}


def resolution_scan(g: ig.Graph, gammas=(0.5, 1.0, 1.5, 2.0), seed: int = 0) -> list[dict]:
    """Number of clusters and modularity at several resolutions: shows whether the chosen partition sits on a plateau."""
    out = []
    for gm in gammas:
        p = leidenalg.find_partition(g, leidenalg.RBConfigurationVertexPartition, weights="w", resolution_parameter=gm, seed=seed, n_iterations=-1)
        sizes = sorted((len(c) for c in p), reverse=True)
        out.append({"gamma": gm, "communities": len(sizes), "communities_ge5": sum(1 for x in sizes if x >= 5), "modularity": round(g.modularity(p.membership, weights="w"), 3)})
    return out


def null_modularity(g: ig.Graph, n: int = 10) -> dict:
    """Unweighted modularity found by the same procedure on degree-preserving rewirings: the chance baseline for structure.

    Compared with `modularity_unweighted` in summary(): the observed partition evaluated without weights, so a heavy-
    tailed weight distribution cannot inflate either side."""
    qs = []
    for s in range(n):
        h = _rewired(g, s)
        if h.ecount() == 0:
            continue
        p = leidenalg.find_partition(h, leidenalg.RBConfigurationVertexPartition, seed=s, n_iterations=-1)
        qs.append(h.modularity(p.membership))
    return {"mean": float(np.mean(qs)) if qs else None, "max": float(np.max(qs)) if qs else None, "n": len(qs), "unweighted": True}


def participation(g: ig.Graph, memb: list[int]) -> np.ndarray:
    """Guimerà & Amaral participation coefficient on weighted strength: 0 = all ties in own community."""
    memb = np.asarray(memb)
    P = np.zeros(g.vcount())
    for v in range(g.vcount()):
        tot = 0.0
        per = {}
        for e in g.incident(v):
            u = g.es[e].source if g.es[e].target == v else g.es[e].target
            w = g.es[e]["w"]
            per[memb[u]] = per.get(memb[u], 0.0) + w
            tot += w
        if tot > 0:
            P[v] = 1.0 - sum((x / tot) ** 2 for x in per.values())
    return P


def _distances(g: ig.Graph) -> list[float] | None:
    """Reply counts are strengths, so the path length between two users is 1 / replies (more replies = closer)."""
    return [1.0 / w for w in g.es["w"]] if g.ecount() else None


def node_metrics(g: ig.Graph, memb: list[int], light: bool = False) -> pd.DataFrame:
    """Per-node structure. light=True (large graphs): betweenness with a path cutoff, no closeness/eigenvector/constraint."""
    if g.vcount() == 0:
        return pd.DataFrame()
    n = g.vcount()
    comp = g.components()
    giant = max(range(len(comp)), key=lambda i: len(comp[i])) if len(comp) else 0
    in_giant = np.array([comp.membership[v] == giant for v in range(n)])
    if light:
        # large graphs: betweenness estimated from a fixed random sample of source nodes (pivot sampling), rescaled to the
        # full-graph scale; exact betweenness on 100k-user graphs would take hours per window
        import random
        random.seed(0)
        srcs = random.sample(range(n), min(n, F.BETWEENNESS_SOURCES))
        btw = np.array(g.betweenness(directed=False, weights=_distances(g), sources=srcs)) * (n / len(srcs))
    else:
        btw = np.array(g.betweenness(directed=False, weights=_distances(g)))
    btw_norm = btw / ((n - 1) * (n - 2) / 2) if n > 2 else btw
    deg = np.array(g.degree(), dtype=float)
    ev_brokerage = np.where(deg > 0, btw / np.maximum(deg, 1), 0.0)   # Everett & Valente: betweenness per tie
    clo = np.full(n, np.nan)
    eig = np.full(n, np.nan)
    if in_giant.sum() > 2 and not light:
        sub = g.induced_subgraph(np.where(in_giant)[0])
        clo_s = sub.closeness(normalized=True)
        eig_s = sub.eigenvector_centrality(weights="w", scale=True)
        clo[in_giant] = clo_s
        eig[in_giant] = eig_s
    P = participation(g, memb)
    memb = np.asarray(memb)
    reached = []
    for v in range(n):
        reached.append(len({memb[u] for u in g.neighbors(v)}))
    constraint = g.constraint(weights="w") if (g.ecount() and not light) else [np.nan] * n
    return pd.DataFrame({
        "name": g.vs["name"], "community": memb, "degree": g.degree(), "strength": g.strength(weights="w"),
        "betweenness": btw_norm, "betweenness_raw": btw, "ev_brokerage": ev_brokerage, "closeness": clo, "eigenvector": eig, "participation": P,
        "communities_reached": reached, "constraint": constraint, "in_giant": in_giant,
    })


def _rewired(g: ig.Graph, seed: int) -> ig.Graph:
    """Degree-preserving rewiring (Maslov-Sneppen) that keeps the weight multiset: rewire() drops edge attributes."""
    import random
    random.seed(seed)
    h = g.copy()
    h.rewire(n=max(10, 10 * h.ecount()), mode="simple")
    ws = list(g.es["w"])
    random.shuffle(ws)
    h.es["w"] = ws[:h.ecount()] + [1.0] * max(0, h.ecount() - len(ws))
    return h


def broker_significance(g: ig.Graph, names: list[str], n: int = F.REWIRINGS, light: bool = False, seed: int = 0, met=None) -> dict:
    """Each named node's betweenness against `n` degree-preserving rewirings of the same graph: z-score and empirical p.

    Rewiring needs a full betweenness pass per rewiring, so above REWIRE_MAX_N nodes the test is replaced by a
    degree-matched comparison on the observed graph: the node's percentile among nodes of similar degree (±25%)."""
    if not names or g.ecount() == 0:
        return {}
    idx = {g.vs[i]["name"]: i for i in range(g.vcount())}
    if g.vcount() > F.REWIRE_MAX_N and met is not None:
        out = {}
        deg = met["degree"].to_numpy(dtype=float); b = met["betweenness"].to_numpy(dtype=float); nm = met["name"].tolist()
        for name in names:
            if name not in idx:
                continue
            k = nm.index(name)
            mask = (deg >= 0.75 * deg[k]) & (deg <= 1.25 * deg[k]) & (np.arange(len(nm)) != k)
            if mask.sum() < 10:   # very high-degree nodes have few peers within 25%: take the 30 nearest in degree
                order = np.argsort(np.abs(deg - deg[k]))
                mask = np.zeros(len(nm), bool); mask[[i for i in order if i != k][:30]] = True
            pct = float(np.mean(b[mask] <= b[k]))
            out[name] = {"method": "degree-matched", "percentile": round(100 * pct, 1), "n_matched": int(mask.sum()), "degree": int(deg[k])}
        return out
    vids = [idx[x] for x in names if x in idx]
    cutoff = 3 if light else None
    obs = np.array(g.betweenness(vertices=vids, directed=False, weights=_distances(g), cutoff=cutoff))
    sims = []
    for s in range(n):
        h = _rewired(g, seed + s)
        sims.append(h.betweenness(vertices=vids, directed=False, weights=_distances(h), cutoff=cutoff))
    sims = np.array(sims)
    out = {}
    for k, name in enumerate([x for x in names if x in idx]):
        col = sims[:, k]
        sd = col.std() or 1e-9
        out[name] = {"method": "rewiring", "observed": float(obs[k]), "null_mean": float(col.mean()), "null_sd": float(col.std()),
                     "z": round(float((obs[k] - col.mean()) / sd), 2), "p": round(float((np.sum(col >= obs[k]) + 1) / (n + 1)), 4), "rewirings": n}
    return out


def ei_null(g: ig.Graph, group: list, n: int = F.REWIRINGS, seed: int = 0) -> dict:
    """The E-I index against degree-preserving rewirings: is the cross-group share more or less than chance would give?"""
    obs = ei_index(g, group)
    if obs is None or g.ecount() == 0:
        return {}
    n = min(n, 30) if g.ecount() > 200000 else n
    sims = []
    for s in range(n):
        h = _rewired(g, seed + s)
        v = ei_index(h, group)
        if v is not None:
            sims.append(v)
    sims = np.array(sims)
    sd = sims.std() or 1e-9
    return {"observed": round(float(obs), 3), "null_mean": round(float(sims.mean()), 3), "null_sd": round(float(sims.std()), 3),
            "z": round(float((obs - sims.mean()) / sd), 2), "p_two_sided": round(float((np.sum(np.abs(sims - sims.mean()) >= abs(obs - sims.mean())) + 1) / (len(sims) + 1)), 4), "rewirings": int(len(sims))}


def ei_index(g: ig.Graph, group: list) -> float | None:
    """Krackhardt & Stern E-I index on edge weights: -1 all ties inside groups, +1 all between."""
    group = np.asarray(group, dtype=object)
    e = i = 0.0
    for ed in g.es:
        ga, gb = group[ed.source], group[ed.target]
        if ga is None or gb is None:
            continue
        if ga == gb:
            i += ed["w"]
        else:
            e += ed["w"]
    return (e - i) / (e + i) if (e + i) > 0 else None


def summary(g: ig.Graph, comm: dict) -> dict:
    n, m = g.vcount(), g.ecount()
    comp = g.components()
    sizes = pd.Series(comm["membership"]).value_counts().tolist() if n else []
    return {
        "nodes": n, "edges": m, "directed_edges": g["directed_edges"] if "directed_edges" in g.attributes() else None,
        "tie_replies": int(round(sum(g.es["w"]))) if (m and "w" in g.es.attributes()) else None,
        "density": round(2 * m / (n * (n - 1)), 5) if n > 1 else 0.0,
        "components": len(comp), "largest_component_share": round(max(len(c) for c in comp) / n, 3) if n else 0.0,
        "reciprocity": round(g["reciprocity"], 3) if "reciprocity" in g.attributes() else None,
        "modularity": round(comm["modularity"], 3), "modularity_unweighted": round(g.modularity(comm["membership"]), 3) if (n and m) else 0.0,
        "seed_ari": round(comm["seed_ari"], 3) if comm.get("seed_ari") is not None else None,
        "communities": len(sizes), "community_sizes": sizes[:12], "communities_ge5": int(sum(1 for x in sizes if x >= 5)),
        "avg_clustering": round(g.transitivity_avglocal_undirected(mode="zero"), 3) if n else 0.0,
        "mean_degree": round(2 * m / n, 2) if n else 0.0,
    }


# ---- readable core ------------------------------------------------------------------------------
def readable_core(g: ig.Graph, max_nodes: int = F.FOCUS_MAX_NODES, min_nodes: int = F.FOCUS_MIN_NODES) -> tuple[ig.Graph, dict]:
    """Raise k in the k-core until at most `max_nodes` remain, then keep the largest component.

    Returns the subgraph and what it covers of the full graph (nodes, edges, reply weight)."""
    if g.vcount() <= max_nodes:
        sub, k = g.copy(), 0
    else:
        core = np.array(g.coreness())
        k = 1
        while (core >= k).sum() > max_nodes and k < core.max():
            k += 1
        if (core >= k).sum() < min_nodes and k > 1:
            k -= 1
        sub = g.induced_subgraph(np.where(core >= k)[0])
        if sub.vcount() > max_nodes:   # a flat core: keep the strongest nodes
            top = np.argsort(-np.array(sub.strength(weights="w")))[:max_nodes]
            sub = sub.induced_subgraph(sorted(top))
    comp = sub.components()
    sub = sub.induced_subgraph(max(comp, key=len)) if sub.vcount() else sub
    cover = {"k": int(k), "nodes": sub.vcount(), "node_share": round(sub.vcount() / g.vcount(), 4) if g.vcount() else 0,
             "edge_share": round(sub.ecount() / g.ecount(), 4) if g.ecount() else 0,
             "weight_share": round(sum(sub.es["w"]) / sum(g.es["w"]), 4) if g.ecount() else 0}
    return sub, cover


def layout(g: ig.Graph, seed: int = 7) -> np.ndarray:
    """Fruchterman–Reingold positions scaled to [0, 1]; weights pull replying users together."""
    if g.vcount() == 0:
        return np.zeros((0, 2))
    import random
    random.seed(seed)
    lay = g.layout_fruchterman_reingold(weights="w", niter=1500, seed=None)
    xy = np.array(lay.coords)
    lo, hi = xy.min(0), xy.max(0)
    span = np.where(hi - lo > 0, hi - lo, 1)
    return (xy - lo) / span


# ---- flair groups --------------------------------------------------------------------------------
FLAIR_RULES = {
    # ordered: the first pattern that matches wins, so left-wing compounds that contain right-wing words come first
    "capitalismvsocialism": [
        ("left", r"libertarian[- ]?(socialis|municipal|communis|marx|left)|left[- ]?libertarian|anarcho-?(communis|syndicalis|collectivis|primitivis|pacifis)|social anarchis|veganarch"),
        ("right", r"capitalis|\bancap\b|anarcho-?capitalis|libertarian|minarch|voluntaryis|classical liberal|conservativ|right[- ]?wing|objectivis|austrian|monarch|nationalis|fascis|falang|reactionar|traditionalis|propertarian|paleo|neocon|republican"),
        ("left", r"social(ist|ism)|communis|commie|marx|lenin|trotsky|maois|stalin|leftcom|left(ist)?\b|mutualis|syndicalis|communalis|anti-?fascis|antifa|progressiv|labou?r|anarchis|anarcha|democratic socialis|georgist socialis|luxemburg|council"),
        ("centre", r"social democra|socdem|centris|centre|center|moderate|neoliberal|\bliberal\b|georgis|distributis|mixed econ|third way|keynes|ordoliberal|pragmatis|undecided"),
    ],
    "purplepilldebate": [("red", r"\bred\b|\brp\b|tradcon|maroon|mgtow|redpill"), ("blue", r"\bblue\b|\bbp\b|bluepill|feminis"), ("purple", r"purple|\bpp\b"), ("black", r"black pill|blackpill")],
}


def flair_group(subreddit: str, flair: str | None) -> str | None:
    if not flair:
        return None
    f = flair.lower()
    for name, pat in FLAIR_RULES.get(subreddit.lower(), []):
        if re.search(pat, f):
            return name
    return None


def user_groups(df: pd.DataFrame, subreddit: str) -> dict[str, str]:
    """Each user's most frequent recognised flair group in the window (None if none recognised)."""
    if "flair" not in df:
        return {}
    d = df[["author_h", "flair"]].dropna()
    d = d.assign(group=[flair_group(subreddit, x) for x in d["flair"]]).dropna(subset=["group"])
    if d.empty:
        return {}
    top = (d.groupby(["author_h", "group"]).size().reset_index(name="n")
           .sort_values(["n", "group"], ascending=[False, True], kind="mergesort").drop_duplicates("author_h"))   # ties: alphabetical camp, deterministic
    return dict(zip(top["author_h"], top["group"]))


# ---- export ---------------------------------------------------------------------------------------
def anonymise(g: ig.Graph) -> dict[str, str]:
    """Stable pseudonyms ordered by strength: 'u1' is the most active node. Author hashes never leave the machine."""
    order = np.argsort(-np.array(g.strength(weights="w")), kind="stable")
    return {g.vs[int(v)]["name"]: f"u{k + 1}" for k, v in enumerate(order)}


def export(g: ig.Graph, memb: list[int], met: pd.DataFrame, xy: np.ndarray, extra: dict[str, dict] | None = None) -> dict:
    """JSON-ready network: anonymised nodes with positions, communities and metrics; weighted edges."""
    alias = anonymise(g)
    m = met.set_index("name")
    nodes = []
    for v in g.vs:
        r = m.loc[v["name"]]
        node = {"id": alias[v["name"]], "x": round(float(xy[v.index, 0]), 4), "y": round(float(xy[v.index, 1]), 4),
                "community": int(memb[v.index]), "degree": int(r["degree"]), "strength": int(r["strength"]),
                "betweenness": round(float(r["betweenness"]), 5), "ev_brokerage": round(float(r["ev_brokerage"]), 3), "participation": round(float(r["participation"]), 3),
                "reached": int(r["communities_reached"]), "eigenvector": None if pd.isna(r["eigenvector"]) else round(float(r["eigenvector"]), 4),
                "constraint": None if pd.isna(r["constraint"]) else round(float(r["constraint"]), 3)}
        for key, table in (extra or {}).items():
            val = table.get(v["name"])
            node[key] = None if val is None or (isinstance(val, float) and math.isnan(val)) else (round(val, 3) if isinstance(val, float) else val)
        nodes.append(node)
    edges = [{"s": alias[g.vs[e.source]["name"]], "t": alias[g.vs[e.target]["name"]], "w": int(e["w"])} for e in g.es]
    return {"nodes": nodes, "edges": edges}
