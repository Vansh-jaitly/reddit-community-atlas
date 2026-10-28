"""
build_atlas.py
==============
Regenerates every data artifact behind the Reddit Community Atlas from the
cleaned quarterly Parquet files:

    atlas/web/data/meta.json             periods, communities, summary statistics, data quality
    atlas/web/data/nodes.json            subreddits: category, community, layout, sizes, roles
    atlas/web/data/pairs_<period>.json   every subreddit pair: shared / expected / cosine, validated edges
    atlas/web/data/activity.json         weekly commenters per subreddit, monthly newcomer share
    atlas/web/data/stories.json          the guided stories, every number computed here
    atlas/web/exports/                   CSV edge/node tables and GEXF files (Gephi, Tableau)

Published files contain only subreddit-level aggregates (no author hashes).

Usage:
    python atlas/build_atlas.py              # full build (~10-20 min)
    python atlas/build_atlas.py --skip-monthly-sensitivity
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import igraph as ig
import leidenalg
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import adjusted_rand_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from network_analysis.affinity import AffinityNetwork, affinity_network, presence_matrix  # noqa: E402

CLEAN = ROOT / "data_curation/data/clean"
LOGS = ROOT / "data_curation/data/logs"
WEB_DATA = ROOT / "atlas/web/data"
EXPORTS = ROOT / "atlas/web/exports"
VALIDATION = ROOT / "atlas/validation"

ALPHA = 0.01            # Benjamini-Hochberg false discovery rate for validated edges
SENSITIVITY_MIN = 2     # robustness: a user must have >= 2 comments in a subreddit to count
LEIDEN_SEEDS = 20
LAYOUT_SEED = 42

CATEGORY_LABELS = {
    "gateway": "Front page & entertainment", "media": "Media & fandom", "hobby": "Hobbies & lifestyle",
    "support": "Support & health", "politics_news": "Politics & news", "finance": "Money & work",
    "expertise": "Tech, science & ideas",
}
CRYPTO = ["Bitcoin", "CryptoCurrency", "ethereum", "dogecoin", "BitcoinBeginners"]
CRYPTO_COMPARISON = ["investing", "personalfinance", "wallstreetbets"]
MARVEL = ["marvelstudios", "Marvel"]
MARVEL_COMPARISON = ["movies", "StarWars", "comics"]
# Verified external dates (sources listed in docs/FINAL_REPORT.md)
EVENTS = [
    {"date": "2017-12-17", "label": "Bitcoin all-time high (~$19.8k)", "story": "crowds", "group": "crypto"},
    {"date": "2018-02-06", "label": "Bitcoin falls below $6,000", "story": "crowds", "group": "crypto"},
    {"date": "2018-06-22", "label": "New 2018 Bitcoin low", "story": "crowds", "group": "crypto"},
    {"date": "2018-04-27", "label": "Avengers: Infinity War US release", "story": "crowds", "group": "marvel"},
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def mlabel(m: str) -> str:
    return dt.date(int(m[:4]), int(m[5:7]), 1).strftime("%b %Y")


def r(x, nd=3):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_monthly(quarters: list[str]):
    """One row per (user, subreddit, month) with comment counts, users as integers."""
    import tempfile
    con = duckdb.connect()
    spill = (Path(tempfile.gettempdir()) / "atlas_duckdb").as_posix()
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='4GB'; SET preserve_insertion_order=false; SET temp_directory='{spill}'")
    files = ", ".join(f"'{(CLEAN / f'{q}.parquet').as_posix()}'" for q in quarters)
    con.execute(f"""CREATE TEMP TABLE sm AS
        SELECT author_h, subreddit, strftime(to_timestamp(created_utc), '%Y-%m') AS month, COUNT(*)::INTEGER AS n
        FROM read_parquet([{files}]) GROUP BY 1, 2, 3""")
    con.execute("CREATE TEMP TABLE uid AS SELECT author_h, (ROW_NUMBER() OVER ())::INTEGER - 1 AS u FROM (SELECT DISTINCT author_h FROM sm)")
    subs = [x[0] for x in con.execute("SELECT DISTINCT subreddit FROM sm ORDER BY lower(subreddit)").fetchall()]
    sid = {s: i for i, s in enumerate(subs)}
    months = [x[0] for x in con.execute("SELECT DISTINCT month FROM sm ORDER BY 1").fetchall()]
    mid = {m: i for i, m in enumerate(months)}
    df = con.execute("SELECT x.month, u.u, x.subreddit, x.n FROM sm x JOIN uid u USING (author_h)").df()
    df["s"] = df.subreddit.map(sid).astype(np.int16)
    df["m"] = df.month.map(mid).astype(np.int8)
    df = df[["m", "u", "s", "n"]]
    weekly = con.execute("""
        SELECT subreddit, date_trunc('week', to_timestamp(created_utc))::DATE AS week,
               COUNT(DISTINCT author_h) AS authors, COUNT(*) AS comments
        FROM read_parquet([""" + files + """]) GROUP BY 1, 2""").df()
    first = con.execute("""
        WITH f AS (SELECT subreddit, author_h, MIN(month) AS first_month FROM sm GROUP BY 1, 2)
        SELECT x.subreddit, x.month, AVG(CASE WHEN f.first_month = x.month THEN 1.0 ELSE 0.0 END) AS new_share,
               COUNT(*) AS authors
        FROM sm x JOIN f USING (subreddit, author_h) GROUP BY 1, 2""").df()
    totals = con.execute("SELECT month, COUNT(DISTINCT author_h) AS authors, SUM(n) AS comments FROM sm GROUP BY 1 ORDER BY 1").df()
    con.close()
    return df, subs, months, weekly, first, totals


def network_for(df, months_idx, n_users, subs, min_n=1) -> AffinityNetwork:
    d = df[df.m.isin(months_idx)]
    if min_n > 1:
        d = d.groupby(["u", "s"], as_index=False)["n"].sum()
        d = d[d.n >= min_n]
    M = presence_matrix(d.u.values, d.s.values, n_users, len(subs))
    return affinity_network(M, subs, ALPHA)


# ---------------------------------------------------------------------------
# Network measures
# ---------------------------------------------------------------------------
def weighted_graph(net: AffinityNetwork) -> ig.Graph:
    iu = np.triu_indices(len(net.subreddits), 1)
    keep = net.validated[iu]
    g = ig.Graph(n=len(net.subreddits), edges=list(zip(iu[0][keep], iu[1][keep])))
    g.es["weight"] = np.log(net.affinity[iu][keep])     # validated edges have affinity > 1
    return g


def leiden(g: ig.Graph):
    parts = [leidenalg.find_partition(g, leidenalg.RBConfigurationVertexPartition, weights="weight",
                                      resolution_parameter=1.0, seed=s) for s in range(LEIDEN_SEEDS)]
    best = max(parts, key=lambda p: p.quality())
    ari = float(np.mean([adjusted_rand_score(best.membership, p.membership) for p in parts]))
    return np.array(best.membership), float(g.modularity(best.membership, weights="weight")), ari


def roles(net: AffinityNetwork, membership: np.ndarray):
    """Participation coefficient and within-community degree z-score (Guimera & Amaral 2005), log-affinity weights."""
    S = len(net.subreddits)
    A = np.where(net.validated, np.log(np.where(net.affinity > 0, net.affinity, 1.0)), 0.0)
    np.fill_diagonal(A, 0.0)
    k = A.sum(1)
    comms = np.unique(membership)
    kc = np.stack([A[:, membership == c].sum(1) for c in comms], 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        P = np.where(k > 0, 1 - ((kc / k[:, None]) ** 2).sum(1), 0.0)
    own = kc[np.arange(S), np.searchsorted(comms, membership)]
    z = np.zeros(S)
    for c in comms:
        idx = membership == c
        sd = own[idx].std()
        z[idx] = (own[idx] - own[idx].mean()) / sd if sd > 0 else 0.0
    return P, z, (A > 0).sum(1)


def layout(g: ig.Graph, membership: np.ndarray) -> np.ndarray:
    """Community-aware force-directed positions (Fruchterman-Reingold), fixed seed, scaled to [-1, 1]."""
    import random
    random.seed(LAYOUT_SEED)
    ig.set_random_number_generator(random)
    rng = np.random.default_rng(LAYOUT_SEED)
    # seed positions by community so clusters start apart and the result is reproducible
    angles = {c: 2 * np.pi * i / len(np.unique(membership)) for i, c in enumerate(np.unique(membership))}
    seed = np.array([[np.cos(angles[c]) * 10 + rng.normal(), np.sin(angles[c]) * 10 + rng.normal()] for c in membership])
    # Display-only weights: strong ties pull harder (squared log-affinity) and ties inside a community
    # pull 10x more than ties across, so clusters separate while cross-cluster links stay visible.
    ends = np.array(g.get_edgelist())
    same = membership[ends[:, 0]] == membership[ends[:, 1]] if len(ends) else np.array([], bool)
    g.es["layout_w"] = (np.array(g.es["weight"]) ** 2 * np.where(same, 3.0, 0.3)).tolist()
    pos = np.array(g.layout_fruchterman_reingold(weights="layout_w", niter=3000, seed=seed.tolist(), grid=False).coords)
    deg = np.array(g.degree())
    if (deg == 0).any():   # isolates: park them on an outer ring rather than at random
        centre, rad = pos[deg > 0].mean(0), np.abs(pos[deg > 0] - pos[deg > 0].mean(0)).max() * 1.15
        iso = np.where(deg == 0)[0]
        for j, i in enumerate(iso):
            a = 2 * np.pi * j / len(iso) + 0.3
            pos[i] = centre + rad * np.array([np.cos(a), np.sin(a)])
    pos -= pos.mean(0)
    return pos / np.abs(pos).max()


def community_labels(membership, subs, cats, sizes):
    labels = {}
    used = set()
    for c in np.unique(membership):
        idx = np.where(membership == c)[0]
        members = sorted(idx, key=lambda i: -sizes[i])
        if len(idx) <= 4:
            lab = " · ".join(subs[i] for i in members[:3])
        else:
            top = pd.Series([cats[i] for i in idx]).value_counts().index[0]
            lab = CATEGORY_LABELS[top]
            if lab in used:
                lab = f"{lab} ({subs[members[0]]})"
        used.add(lab)
        labels[int(c)] = lab
    return labels


def top_neighbours(score: np.ndarray, i: int, k: int, mask=None):
    s = score[i].astype(float).copy()
    s[i] = -np.inf
    if mask is not None:
        s[~mask[i]] = -np.inf
    order = [j for j in np.argsort(-s) if np.isfinite(s[j])]
    return order[:k]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-monthly-sensitivity", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    WEB_DATA.mkdir(parents=True, exist_ok=True); EXPORTS.mkdir(parents=True, exist_ok=True)

    quarters = sorted(p.stem for p in CLEAN.glob("*.parquet"))
    log(f"quarters found: {quarters}")
    df, subs, months, weekly, first, totals = load_monthly(quarters)
    S, NU = len(subs), int(df.u.max()) + 1
    frame = pd.read_csv(ROOT / "frame.csv")
    catmap = {s.lower(): c for s, c in zip(frame.subreddit, frame.category)}
    cats = [catmap[s.lower()] for s in subs]
    iu = np.triu_indices(S, 1)
    log(f"{len(df):,} user-subreddit-month rows, {NU:,} users, {S} subreddits, months {months[0]}..{months[-1]}")

    def q_months(q):
        y, k = int(q[:4]), int(q[-1])
        return [months.index(f"{y}-{m:02d}") for m in range(3 * k - 2, 3 * k + 1) if f"{y}-{m:02d}" in months]

    periods = [{"id": "all", "kind": "pooled", "label": f"All ({months[0]} – {months[-1]})", "months": list(range(len(months)))}]
    periods += [{"id": q, "kind": "quarter", "label": f"{q[:4]} Q{q[-1]}", "months": q_months(q)} for q in quarters]
    periods += [{"id": m, "kind": "month", "label": dt.date(int(m[:4]), int(m[5:]), 1).strftime("%b %Y"), "months": [i]} for i, m in enumerate(months)]

    # --- networks per period -------------------------------------------------
    nets, nets2 = {}, {}
    for p in periods:
        nets[p["id"]] = network_for(df, p["months"], NU, subs)
        if p["kind"] in ("quarter", "pooled") or (p["kind"] == "month" and not args.skip_monthly_sensitivity):
            nets2[p["id"]] = network_for(df, p["months"], NU, subs, SENSITIVITY_MIN)
        log(f"  {p['id']}: users {nets[p['id']].n_users:,}, validated density {nets[p['id']].density:.3f}, fit error {nets[p['id']].fit_error:.1e}")

    # --- anchor communities, roles, layout -------------------------------------
    anchor = nets["all"]
    g_anchor = weighted_graph(anchor)
    memb, anchor_q, anchor_ari = leiden(g_anchor)
    memb2, _, _ = leiden(weighted_graph(nets2["all"]))
    sizes = anchor.sub_users
    labels = community_labels(memb, subs, cats, sizes)
    pos = layout(g_anchor, memb)
    P_all, z_all, deg_all = roles(anchor, memb)
    log(f"anchor: {len(set(memb))} communities, weighted Q {anchor_q:.3f}, seed ARI {anchor_ari:.2f}")

    per_period = {}
    for p in periods:
        net = nets[p["id"]]
        mp, qp, arip = leiden(weighted_graph(net))
        Pp, zp, degp = roles(net, memb)
        per_period[p["id"]] = dict(memb=mp, q=qp, ari=arip, P=Pp, z=zp, deg=degp)

    # --- pairs files -----------------------------------------------------------------------
    for p in periods:
        net = nets[p["id"]]
        out = {
            "period": p["id"],
            "shared": net.observed[iu].astype(int).tolist(),
            "expected": [round(x, 2) for x in net.expected[iu]],
            "cosine": [round(x, 5) for x in net.cosine[iu]],
            "validated": np.where(net.validated[iu])[0].tolist(),
            "robust": np.where(net.validated[iu] & nets2[p["id"]].validated[iu])[0].tolist() if p["id"] in nets2 else None,
            "community": per_period[p["id"]]["memb"].tolist(),
            "users": net.sub_users.astype(int).tolist(),
        }
        (WEB_DATA / f"pairs_{p['id']}.json").write_text(json.dumps(out, separators=(",", ":"), allow_nan=False))

    # --- nodes -------------------------------------------------------------------------
    qids = [p["id"] for p in periods if p["kind"] == "quarter"]
    nodes = []
    for i, s in enumerate(subs):
        nodes.append({
            "id": i, "name": s, "category": cats[i], "community": int(memb[i]),
            "x": r(pos[i, 0], 4), "y": r(pos[i, 1], 4),
            "users": int(sizes[i]),
            "participation": r(P_all[i]), "within_z": r(z_all[i], 2), "degree": int(deg_all[i]),
            "participation_by_quarter": {q: r(per_period[q]["P"][i]) for q in qids},
            "community_sensitivity": int(memb2[i]),
        })
    (WEB_DATA / "nodes.json").write_text(json.dumps(nodes, separators=(",", ":"), allow_nan=False))

    # --- activity ------------------------------------------------------------------------
    weekly["week"] = pd.to_datetime(weekly.week).dt.strftime("%Y-%m-%d")
    weeks = sorted(weekly.week.unique())
    W = weekly.pivot(index="subreddit", columns="week", values="authors").reindex(index=subs, columns=weeks).fillna(0).astype(int)
    first_piv = first.pivot(index="subreddit", columns="month", values="new_share").reindex(index=subs, columns=months)
    mon_auth = first.pivot(index="subreddit", columns="month", values="authors").reindex(index=subs, columns=months).fillna(0).astype(int)
    activity = {
        "weeks": weeks,
        "partial_weeks": [weeks[0], weeks[-1]],
        "weekly_authors": W.values.tolist(),
        "months": months,
        "monthly_authors": mon_auth.values.tolist(),
        "monthly_new_share": [[None] + [r(x) for x in row[1:]] for row in first_piv.values],   # first month: everyone is "new"
        "frame_monthly_authors": totals.authors.astype(int).tolist(),
        "frame_monthly_comments": totals.comments.astype(int).tolist(),
    }
    (WEB_DATA / "activity.json").write_text(json.dumps(activity, separators=(",", ":"), allow_nan=False))

    # --- summary statistics ---------------------------------------------------------------
    quarters_net = {q: nets[q] for q in qids}
    def jacc(a, b):
        return float((a & b).sum() / max(1, (a | b).sum()))
    gw = np.array([c == "gateway" for c in cats])
    hub_share, same_cat = {}, {}
    for name, score, mask in (("cosine", anchor.cosine, None), ("affinity", anchor.affinity, anchor.validated)):
        hubs, same = [], []
        for i in range(S):
            nb = top_neighbours(score, i, 10, mask)
            if gw[i] or not nb:
                continue
            hubs.append(np.mean(gw[nb]))
            same.append(np.mean([cats[j] == cats[i] for j in nb]))
        hub_share[name], same_cat[name] = r(np.mean(hubs)), r(np.mean(same))
    month_ids = [p["id"] for p in periods if p["kind"] == "month"]
    summary = {
        "subreddits": S, "users_total": NU, "months": months, "quarters": qids,
        "alpha": ALPHA, "sensitivity_min_comments": SENSITIVITY_MIN,
        "cosine_density": {p["id"]: r(float((nets[p["id"]].observed[iu] > 0).mean()), 4) for p in periods if p["kind"] != "month"},
        "validated_density": {p["id"]: r(nets[p["id"]].density, 4) for p in periods},
        "validated_edges": {p["id"]: int(np.triu(nets[p["id"]].validated, 1).sum()) for p in periods},
        "robust_share": {p["id"]: r(float((nets[p["id"]].validated[iu] & nets2[p["id"]].validated[iu]).sum() / max(1, nets[p["id"]].validated[iu].sum()))) for p in periods if p["id"] in nets2},
        "sensitivity_edge_jaccard": {p["id"]: r(jacc(nets[p["id"]].validated[iu], nets2[p["id"]].validated[iu])) for p in periods if p["id"] in nets2},
        "anchor": {"communities": int(len(set(memb))), "weighted_modularity": r(anchor_q), "seed_ari": r(anchor_ari),
                   "sensitivity_ari": r(adjusted_rand_score(memb, memb2))},
        "period_communities": {pid: {"communities": int(len(set(v["memb"]))), "weighted_modularity": r(v["q"]), "seed_ari": r(v["ari"]),
                                     "ari_vs_anchor": r(adjusted_rand_score(memb, v["memb"]))} for pid, v in per_period.items()},
        "quarter_edge_jaccard": {f"{a}->{b}": r(jacc(quarters_net[a].validated[iu], quarters_net[b].validated[iu])) for a, b in zip(qids, qids[1:])},
        "month_edge_jaccard": {f"{a}->{b}": r(jacc(nets[a].validated[iu], nets[b].validated[iu])) for a, b in zip(month_ids, month_ids[1:])},
        "hub_share_top10": hub_share, "same_category_share_top10": same_cat,
        "participation_rank_stability": {f"{a}->{b}": r(spearmanr(per_period[a]["P"], per_period[b]["P"])[0]) for a, b in zip(qids, qids[1:])},
        "category_ari_vs_anchor": r(adjusted_rand_score(cats, memb)),
    }

    # --- stories -------------------------------------------------------------------------------
    stories = build_stories(subs, cats, memb, labels, nets, nets2, periods, qids, months, activity, anchor, P_all, deg_all, per_period, gw, summary)

    # --- meta ----------------------------------------------------------------------------------
    cleaning = pd.read_csv(LOGS / "cleaning_report.csv").fillna("").to_dict("records")
    coverage = pd.read_csv(LOGS / "coverage_report.csv").fillna("").to_dict("records")
    crosscheck = json.loads((VALIDATION / "bicm_crosscheck.json").read_text()) if (VALIDATION / "bicm_crosscheck.json").exists() else None
    v1_audit = json.loads((LOGS / "v1_modularity_audit.json").read_text()) if (LOGS / "v1_modularity_audit.json").exists() else None
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = None
    comm_info = []
    for c in sorted(labels):
        idx = np.where(memb == c)[0]
        comm_info.append({
            "id": int(c), "label": labels[c], "size": int(len(idx)),
            "members": [subs[i] for i in sorted(idx, key=lambda i: -sizes[i])],
            "category_mix": pd.Series([cats[i] for i in idx]).value_counts().to_dict(),
        })
    meta = {
        "title": "Beyond the Hairball: The Reddit Community Atlas",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit,
        "periods": [{k: v for k, v in p.items() if k != "months"} | {"months": [months[i] for i in p["months"]], "users": nets[p["id"]].n_users} for p in periods],
        "categories": CATEGORY_LABELS,
        "communities": comm_info,
        "summary": summary,
        "events": EVENTS,
        "cleaning_report": cleaning, "coverage_report": coverage,
        "validation": {"bicm_crosscheck": crosscheck, "v1_modularity_audit": v1_audit},
        "parameters": {"alpha": ALPHA, "test": "one-sided Poisson approximation of the Poisson-binomial, Benjamini-Hochberg FDR",
                       "community_method": "Leiden RBConfiguration (modularity, gamma=1), log-affinity weights, best of 20 seeds",
                       "layout": f"Fruchterman-Reingold, squared log-affinity weights, within-community ties x10 (display only), seed {LAYOUT_SEED}",
                       "sensitivity_min_comments": SENSITIVITY_MIN},
    }
    (WEB_DATA / "meta.json").write_text(json.dumps(meta, separators=(",", ":"), allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    (WEB_DATA / "stories.json").write_text(json.dumps(stories, separators=(",", ":"), allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    write_exports(subs, cats, memb, labels, nets, qids, pos, P_all)
    log(f"done in {time.time() - t0:.0f}s")


# ---------------------------------------------------------------------------
# Stories (every number computed from the networks above)
# ---------------------------------------------------------------------------
def build_stories(subs, cats, memb, labels, nets, nets2, periods, qids, months, activity, anchor, P_all, deg_all, per_period, gw, summary):
    S = len(subs); idx = {s: i for i, s in enumerate(subs)}
    stories = []

    # A. What popularity hides --------------------------------------------------------------
    cos, aff, val = anchor.cosine, anchor.affinity, anchor.validated
    strength = cos.sum(1)
    top_cos = [subs[i] for i in np.argsort(-strength)[:10]]
    cands = []
    for i in range(S):
        if gw[i] or val[i].sum() < 8:
            continue
        nb_cos, nb_aff = top_neighbours(cos, i, 6), top_neighbours(aff, i, 6, val)
        # the clearest illustration: raw neighbours all hubs, adjusted neighbours none, and a strong top link
        if aff[i, nb_aff[0]] >= 2:
            cands.append((np.mean(gw[nb_cos]) - np.mean(gw[nb_aff]), anchor.sub_users[i], i))
    ex = max(cands)[2]
    ex_cos = [{"name": subs[j], "cosine": r(cos[ex, j]), "affinity": r(aff[ex, j], 2), "gateway": bool(gw[j])} for j in top_neighbours(cos, ex, 6)]
    ex_aff = [{"name": subs[j], "cosine": r(cos[ex, j]), "affinity": r(aff[ex, j], 2), "gateway": bool(gw[j])} for j in top_neighbours(aff, ex, 6, val)]
    biggest = int(np.argmax(anchor.sub_users))
    big_aff = aff[biggest][np.arange(S) != biggest]
    cos_txt = ", ".join(f"r/{n['name']}" for n in ex_cos[:4])
    aff_txt = ", ".join(f"r/{n['name']} ({n['affinity']}×)" for n in ex_aff[:3])
    stories.append({
        "id": "popularity", "title": "What popularity hides",
        "question": f"Why does everything look connected to r/{subs[biggest]}?",
        "headline": f"In raw shared-audience terms the {len(top_cos)} best-connected communities are all front-page hubs. "
                    f"Once size and user activity are accounted for, hubs make up {summary['hub_share_top10']['affinity'] * 100:.0f}% of a topical "
                    f"subreddit's top-10 neighbours instead of {summary['hub_share_top10']['cosine'] * 100:.0f}%.",
        "metrics": {"cosine_density_all": summary["cosine_density"]["all"], "validated_density_all": summary["validated_density"]["all"],
                    "hub_share_cosine": summary["hub_share_top10"]["cosine"], "hub_share_affinity": summary["hub_share_top10"]["affinity"],
                    "same_category_cosine": summary["same_category_share_top10"]["cosine"], "same_category_affinity": summary["same_category_share_top10"]["affinity"],
                    "top_by_cosine_strength": top_cos, "example": subs[ex], "example_cosine_neighbours": ex_cos, "example_affinity_neighbours": ex_aff,
                    "biggest": subs[biggest], "biggest_users": int(anchor.sub_users[biggest]),
                    "biggest_median_affinity": r(np.median(big_aff), 2), "biggest_validated_degree": int(val[biggest].sum())},
        "steps": [
            {"view": "raw", "focus": [idx[s] for s in top_cos], "period": "all",
             "text": f"Raw view: an edge for every pair that shares at least one commenter — {summary['cosine_density']['all'] * 100:.2f}% of all pairs. "
                     f"The strongest nodes are the giants: {', '.join('r/' + s for s in top_cos[:5])}."},
            {"view": "adjusted", "focus": [], "period": "all",
             "text": f"Adjusted view: keep only pairs that share far more commenters than user activity and community size predict "
                     f"({summary['validated_density']['all'] * 100:.1f}% of pairs). Topic communities appear."},
            {"view": "adjusted", "focus": [ex] + [idx[n["name"]] for n in ex_aff], "period": "all", "select": ex,
             "text": f"r/{subs[ex]}: by raw overlap its closest neighbours are {cos_txt}. Adjusted, they are {aff_txt}."},
            {"view": "adjusted", "focus": [biggest], "period": "all", "select": biggest,
             "text": f"r/{subs[biggest]} has {int(anchor.sub_users[biggest]):,} commenters in the frame, but its median affinity with other "
                     f"communities is {np.median(big_aff):.2f}× — {'no more than' if np.median(big_aff) <= 1.1 else 'only modestly above'} what chance predicts. It is big, not especially close to anyone."},
        ],
        "caveats": ["Affinity measures co-commenting, not friendship, conversation or influence.",
                    "Raw and adjusted views use the same users and the same communities; only the edge definition changes."],
    })

    # B. Unexpected neighbours ---------------------------------------------------------------
    iu = np.triu_indices(S, 1)
    robust_all = np.logical_and.reduce([nets[q].validated[iu] & nets2[q].validated[iu] for q in qids])
    min_aff = np.min([nets[q].affinity[iu] for q in qids], axis=0)
    rows = []
    for e in np.where(robust_all)[0]:
        a, b = iu[0][e], iu[1][e]
        if cats[a] == cats[b] or gw[a] or gw[b]:
            continue
        rows.append({"a": subs[a], "b": subs[b], "ia": int(a), "ib": int(b), "cat_a": cats[a], "cat_b": cats[b],
                     "cross_community": bool(memb[a] != memb[b]), "min_affinity": r(min_aff[e], 2),
                     "affinity_by_quarter": {q: r(nets[q].affinity[a, b], 2) for q in qids},
                     "shared_all": int(anchor.observed[a, b]), "expected_all": r(anchor.expected[a, b], 1)})
    rows.sort(key=lambda x: -x["min_affinity"])
    cross = [x for x in rows if x["cross_community"]]
    lead = rows[:3]
    def pair_txt(x):
        return (f"r/{x['a']} ({CATEGORY_LABELS[x['cat_a']].lower()}) and r/{x['b']} ({CATEGORY_LABELS[x['cat_b']].lower()}) share "
                f"{x['shared_all']:,} commenters where {x['expected_all']:,.0f} were expected — at least {x['min_affinity']}× in every quarter.")
    stories.append({
        "id": "neighbours", "title": "Unexpected neighbours",
        "question": f"What do r/{lead[0]['a']} and r/{lead[0]['b']} have in common?",
        "headline": f"{len(rows)} links join communities from different topic categories and survive every quarter and the stricter "
                    f"two-comment threshold. The strongest: {pair_txt(lead[0])}",
        "metrics": {"robust_cross_category_links": len(rows), "robust_cross_community_links": len(cross),
                    "top_links": rows[:15], "top_cross_community_links": cross[:10]},
        "steps": [{"view": "adjusted", "period": "all", "focus": [x["ia"], x["ib"]], "edge": [x["ia"], x["ib"]], "select": x["ia"], "text": pair_txt(x)} for x in lead]
                 + [{"view": "adjusted", "period": "all", "focus": sorted({i for x in cross[:6] for i in (x["ia"], x["ib"])}),
                     "edges": [[x["ia"], x["ib"]] for x in cross[:6]],
                     "text": "Links that even cross the detected communities: " + "; ".join(f"r/{x['a']} – r/{x['b']} ({x['min_affinity']}×+)" for x in cross[:6]) + "."}],
        "caveats": ["Shared audiences can reflect shared geography, profession or demographics; without comment text we cannot say which.",
                    "Category labels come from a keyword rule and can be wrong (see Methods: r/smoking)."],
    })

    # C. Hidden connectors ---------------------------------------------------------------------
    Pq = np.stack([per_period[q]["P"] for q in qids], 1)
    P_min = Pq.min(1)
    eligible = [i for i in range(S) if deg_all[i] >= 8]
    conn = sorted(eligible, key=lambda i: -P_min[i])[:10]
    conn_rows = [{"name": subs[i], "category": cats[i], "community": labels[int(memb[i])], "participation_min": r(P_min[i]),
                  "participation_all": r(P_all[i]), "degree": int(deg_all[i]), "users": int(anchor.sub_users[i]),
                  "communities_reached": int(len({int(memb[j]) for j in np.where(anchor.validated[i])[0]}))} for i in conn]
    stab = summary["participation_rank_stability"]
    stories.append({
        "id": "connectors", "title": "The hidden connectors",
        "question": "Which communities quietly connect different parts of Reddit?",
        "headline": f"The communities whose surprising links spread most evenly across the map are r/{conn_rows[0]['name']}, r/{conn_rows[1]['name']} and "
                    f"r/{conn_rows[2]['name']} — not the giant front-page hubs (mean participation {P_all[gw].mean():.2f} for hubs vs {P_all[~gw].mean():.2f} for topical communities).",
        "metrics": {"connectors": conn_rows, "hub_mean_participation": r(P_all[gw].mean()), "topical_mean_participation": r(P_all[~gw].mean()),
                    "rank_stability": stab, "min_degree": 8},
        "steps": [{"view": "adjusted", "period": "all", "focus": [idx[c["name"]] for c in conn_rows[:5]], "colorBy": "community",
                   "text": "Participation coefficient: 0 when all of a community's surprising links stay inside its own cluster, approaching 1 when they "
                           "spread evenly over many clusters. Highlighted: the five highest (minimum over quarters, at least 8 links)."},
                  ] + [{"view": "adjusted", "period": "all", "focus": [idx[c["name"]]], "select": idx[c["name"]],
                        "text": f"r/{c['name']} ({CATEGORY_LABELS[c['category']].lower()}) links into {c['communities_reached']} different clusters; "
                                f"participation ≥ {c['participation_min']} in every quarter."} for c in conn_rows[:3]]
                + [{"view": "adjusted", "period": "all", "focus": [i for i in range(S) if gw[i]],
                    "text": f"The front-page hubs average {P_all[gw].mean():.2f}: once their size is accounted for, their surprising links are mostly with each other."}],
        "caveats": ["Participation depends on the community partition; rank stability across quarters: " + ", ".join(f"{k} ρ={v}" for k, v in stab.items()) + ".",
                    "A connector shares unusually many commenters with several clusters; that is not evidence that information flows through it."],
    })

    # D. Crowds arrive and leave -----------------------------------------------------------------
    m_ids = [p["id"] for p in periods if p["kind"] == "month"]
    crowd = {"months": months}
    MA = np.array(activity["monthly_authors"])
    frame_auth = np.array(activity["frame_monthly_authors"])
    def series(names):
        return {n: MA[idx[n]].tolist() for n in names if n in idx}
    def pair_aff(a, b, use=nets):
        return [r(use[m].affinity[idx[a], idx[b]], 2) if m in use else None for m in m_ids]
    crypto = [s for s in CRYPTO if s in idx]
    marvel = [s for s in MARVEL if s in idx]
    peak = {s: months[int(np.argmax(MA[idx[s]]))] for s in crypto + marvel}
    jan = months.index(peak[crypto[0]])          # crypto baseline: the month r/Bitcoin peaked
    mjan = months.index("2018-01") if "2018-01" in months else 0   # Marvel baseline: before the 2018 releases
    change = {s: r(MA[idx[s]][-1] / MA[idx[s]][jan] - 1) for s in crypto + CRYPTO_COMPARISON if s in idx}
    frame_change = r(frame_auth[-1] / frame_auth[jan] - 1)
    crypto_pairs = [(a, b) for k, a in enumerate(crypto[:3]) for b in crypto[k + 1:3]]
    crowd.update({
        "crypto_monthly_authors": series(crypto), "comparison_monthly_authors": series(CRYPTO_COMPARISON + MARVEL_COMPARISON),
        "marvel_monthly_authors": series(marvel), "frame_monthly_authors": frame_auth.tolist(),
        "peak_month": peak, "baseline_month": months[jan], "change_since_baseline": change, "frame_change_since_baseline": frame_change,
        "crypto_pair_affinity": {f"{a}|{b}": pair_aff(a, b) for a, b in crypto_pairs},
        "crypto_pair_affinity_min2": {f"{a}|{b}": pair_aff(a, b, nets2) for a, b in crypto_pairs},
        "marvel_pair_affinity": {f"{marvel[0]}|{marvel[1]}": pair_aff(*marvel)} if len(marvel) == 2 else {},
        "marvel_pair_affinity_min2": {f"{marvel[0]}|{marvel[1]}": pair_aff(*marvel, use=nets2)} if len(marvel) == 2 else {},
        "new_share": {s: [None] + activity["monthly_new_share"][idx[s]][1:] for s in crypto[:2] + marvel + ["movies"] if s in idx},
        "events": EVENTS,
    })
    # general tendency: month-to-month change in commenters vs change in mean log-affinity to anchor neighbours
    A = anchor.validated
    steps_rows = []
    for k in range(len(m_ids) - 1):
        a, b = nets[m_ids[k]], nets[m_ids[k + 1]]
        for i in range(S):
            nb = np.where(A[i])[0]
            if len(nb) < 3 or a.sub_users[i] == 0 or b.sub_users[i] == 0:
                continue
            la = np.mean(np.log(np.clip(a.affinity[i, nb], 1e-3, None))); lb = np.mean(np.log(np.clip(b.affinity[i, nb], 1e-3, None)))
            steps_rows.append((np.log(b.sub_users[i] / a.sub_users[i]), lb - la))
    G = np.array(steps_rows)
    big = np.abs(G[:, 0]) > np.log(1.25)
    crowd["general_tendency"] = {"spearman_all_steps": r(spearmanr(G[:, 0], G[:, 1])[0]), "n_steps": int(len(G)),
                                 "spearman_large_swings": r(spearmanr(G[big, 0], G[big, 1])[0]), "n_large_swings": int(big.sum())}
    cp = crypto_pairs[0]; ca = crowd["crypto_pair_affinity"][f"{cp[0]}|{cp[1]}"]
    mk = f"{marvel[0]}|{marvel[1]}" if len(marvel) == 2 else None
    ma = crowd["marvel_pair_affinity"].get(mk) if mk else None
    apr = months.index("2018-04") if "2018-04" in months else None
    W = np.array(activity["weekly_authors"]); weeks = activity["weeks"]
    ms = idx.get("marvelstudios")
    rel_wk = weeks.index("2018-04-23") if "2018-04-23" in weeks else None
    mar_wks = [weeks.index(w) for w in weeks if w.startswith("2018-03")]
    marvel_base = int(np.median(W[ms, mar_wks])) if ms is not None and mar_wks else None
    marvel_peak_wk = int(W[ms, rel_wk]) if ms is not None and rel_wk is not None else None
    crowd["marvel_release_week"] = {"week": "2018-04-23", "authors": marvel_peak_wk, "march_median_weekly": marvel_base}
    crypto_line = ", ".join(f"r/{s} {change[s] * 100:+.0f}%" for s in crypto[:3])
    stories.append({
        "id": "crowds", "title": "When crowds arrive and leave",
        "question": "What happens to a community's ties when a crowd suddenly arrives — or leaves?",
        "headline": f"After the Bitcoin peak, crypto communities lost most of their commenters ({crypto_line}, {mlabel(months[jan])} → {mlabel(months[-1])}) "
                    f"while the whole frame changed {frame_change * 100:+.0f}%. The remaining audiences overlapped far more: r/{cp[0]}–r/{cp[1]} affinity went from "
                    f"{ca[jan]}× to {ca[-1]}×." + (f" The Infinity War crowd did the opposite: r/{marvel[0]}–r/{marvel[1]} affinity fell from "
                    f"{ma[mjan]}× in {mlabel(months[mjan])} to {ma[apr]}× in April 2018." if ma and apr is not None else ""),
        "metrics": crowd,
        "steps": [
            {"view": "timeline", "group": "crypto", "focus": [idx[s] for s in crypto], "period": months[0],
             "text": f"Monthly commenters, {mlabel(months[0])} to {mlabel(months[-1])}. r/{crypto[0]} peaks in {mlabel(peak[crypto[0]])} (Bitcoin's price "
                     f"peaked on 17 Dec 2017) and then falls steeply; r/investing and the frame as a whole do not."},
            {"view": "adjusted", "focus": [idx[s] for s in crypto], "period": months[jan], "select": idx[crypto[0]],
             "text": f"{mlabel(months[jan])}, at the peak: the crypto communities form a cluster of surprising links. r/{cp[0]}–r/{cp[1]} affinity {ca[jan]}×"
                     + (f", down from {ca[0]}× in {mlabel(months[0])} while newcomers poured in." if jan > 0 and ca[0] > ca[jan] else ".")},
            {"view": "adjusted", "focus": [idx[s] for s in crypto], "period": months[-1], "select": idx[crypto[0]],
             "text": f"{mlabel(months[-1])}: with most commenters gone, the remaining audiences overlap {ca[-1]}× more than expected. "
                     f"Same result with the two-comment threshold ({crowd['crypto_pair_affinity_min2'][f'{cp[0]}|{cp[1]}'][-1]}×)."},
        ] + ([
            {"view": "timeline", "group": "marvel", "focus": [idx[s] for s in marvel], "period": "2018-04",
             "text": f"Avengers: Infinity War opened in the US on 27 April 2018. r/marvelstudios went from ~{marvel_base:,} weekly commenters in March "
                     f"to {marvel_peak_wk:,} in the release week."},
            {"view": "adjusted", "focus": [idx[s] for s in marvel], "period": "2018-04", "select": idx[marvel[0]],
             "text": f"In April the two Marvel communities' affinity dropped to {ma[apr]}× (from {ma[mjan]}× in {mlabel(months[mjan])}): the newcomers mostly "
                     f"commented in one of them, not both. It recovered to {ma[-1]}× by {mlabel(months[-1])}."},
        ] if ma and apr is not None and marvel_base else []) + [
            {"view": "adjusted", "focus": [], "period": "all",
             "text": f"Across all communities, months with big audience swings tend to move affinity the other way, but only modestly "
                     f"(Spearman ρ = {crowd['general_tendency']['spearman_large_swings']} over {crowd['general_tendency']['n_large_swings']} swings above 25%)."},
        ],
        "caveats": ["Event dates are external context. Activity changing around an event is an association, not proof the event caused it.",
                    "Comments only: lurkers, votes and private communities are invisible.",
                    "Pushshift-derived archives have gaps; counts are lower bounds."],
    })

    # Validity vignette: what the network says about a category label
    vig = []
    for s in ("smoking",):
        if s in idx:
            i = idx[s]
            nb = top_neighbours(anchor.affinity, i, 5, anchor.validated)
            peak_m = months[int(np.argmax(MA[i]))]
            vig.append({"name": s, "label": cats[i], "community": labels[int(memb[i])],
                        "neighbours": [{"name": subs[j], "affinity": r(anchor.affinity[i, j], 2), "category": cats[j]} for j in nb],
                        "peak_month": peak_m})
    return {"stories": stories, "validity_notes": vig}


# ---------------------------------------------------------------------------
# Exports for Gephi / Tableau / the report
# ---------------------------------------------------------------------------
def write_exports(subs, cats, memb, labels, nets, qids, pos, P_all):
    nodes = pd.DataFrame({"Id": subs, "Label": subs, "category": cats, "community": memb,
                          "community_label": [labels[int(c)] for c in memb], "participation": np.round(P_all, 3),
                          "x": np.round(pos[:, 0] * 1000, 1), "y": np.round(pos[:, 1] * 1000, 1)})
    nodes.to_csv(EXPORTS / "atlas_nodes.csv", index=False)
    import networkx as nx
    for pid in ["all"] + qids:
        e = nets[pid].edges()
        e.insert(0, "period", pid)
        e.to_csv(EXPORTS / f"atlas_edges_{pid}.csv", index=False)
        G = nx.Graph()
        for _, n in nodes.iterrows():
            G.add_node(n.Id, label=n.Label, category=n.category, community=int(n.community), participation=float(n.participation),
                       users=int(nets[pid].sub_users[subs.index(n.Id)]), x=float(n.x), y=float(n.y))
        for _, x in e.iterrows():
            G.add_edge(x.source, x.target, weight=float(np.log(x.affinity)), affinity=float(x.affinity), shared=int(x.shared))
        nx.write_gexf(G, EXPORTS / f"atlas_network_{pid}.gexf")


if __name__ == "__main__":
    main()
