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
from network_analysis.affinity import AffinityNetwork, affinity_network, fit_bicm, presence_matrix  # noqa: E402

CLEAN = ROOT / "data_curation/data/clean"
LOGS = ROOT / "data_curation/data/logs"
WEB_DATA = ROOT / "atlas/web/data"
EXPORTS = ROOT / "atlas/web/exports"
VALIDATION = ROOT / "atlas/validation"

ALPHA = 0.01            # Benjamini-Hochberg false discovery rate for validated edges
SENSITIVITY_MIN = 2     # robustness: a user must have >= 2 comments in a subreddit to count
AVOID_MAX_AFFINITY = 0.5  # "avoided" pair: lower-tail FDR alpha AND at most half the expected shared commenters ...
AVOID_MIN_EXPECTED = 20   # ... AND enough expected overlap for the shortfall to be meaningful
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


def write_json(path: Path, obj) -> None:
    """Write JSON atomically (temp file + replace) so a concurrent reader never sees a partial file."""
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    os.replace(tmp, path)


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
    ap.add_argument("--out", default=None, help="write web data and exports under this directory instead of atlas/web (for safe test builds)")
    ap.add_argument("--stories-only", action="store_true", help="regenerate stories.json from the already-published artifacts (seconds, no Parquet needed)")
    args = ap.parse_args()
    global WEB_DATA, EXPORTS
    if args.out:
        WEB_DATA, EXPORTS = Path(args.out) / "data", Path(args.out) / "exports"
    if args.stories_only:
        return rebuild_stories_from_artifacts()
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

    periods = [{"id": "all", "kind": "pooled", "label": f"All {len(months)} months ({mlabel(months[0])} – {mlabel(months[-1])})", "months": list(range(len(months)))}]
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
    sig2 = lambda x: float(f"{x:.1e}")   # two significant digits keeps the files small
    for p in periods:
        net = nets[p["id"]]
        avoid = net.avoided[iu] & (net.affinity[iu] <= AVOID_MAX_AFFINITY) & (net.expected[iu] >= AVOID_MIN_EXPECTED)
        out = {
            "period": p["id"],
            "shared": net.observed[iu].astype(int).tolist(),
            "expected": [round(x, 2) for x in net.expected[iu]],
            "cosine": [round(x, 5) for x in net.cosine[iu]],
            "p_high": [sig2(x) for x in net.pvalues[iu]],
            "p_low": [sig2(x) for x in net.pvalues_low[iu]],
            "validated": np.where(net.validated[iu])[0].tolist(),
            "avoided": np.where(avoid)[0].tolist(),
            "robust": np.where(net.validated[iu] & nets2[p["id"]].validated[iu])[0].tolist() if p["id"] in nets2 else None,
            "robust_affinity": [round(float(nets2[p["id"]].affinity[iu][k]), 3) for k in np.where(net.validated[iu] & nets2[p["id"]].validated[iu])[0]] if p["id"] in nets2 else None,
            "n_users": int(net.n_users),
            "community": per_period[p["id"]]["memb"].tolist(),
            "users": net.sub_users.astype(int).tolist(),
        }
        write_json(WEB_DATA / f"pairs_{p['id']}.json", out)

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
    write_json(WEB_DATA / "nodes.json", nodes)

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
    write_json(WEB_DATA / "activity.json", activity)

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
                   "sensitivity_ari": r(adjusted_rand_score(memb, memb2)),
                   "communities_major": int(sum(1 for c in set(memb) if (memb == c).sum() >= 5)),
                   "small_groups": int(sum(1 for c in set(memb) if 1 < (memb == c).sum() < 5)),
                   "isolates": int(sum(1 for c in set(memb) if (memb == c).sum() == 1))},
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
                       "sensitivity_min_comments": SENSITIVITY_MIN,
                       "avoided_rule": f"lower-tail Poisson test at FDR {ALPHA}, affinity <= {AVOID_MAX_AFFINITY}, expected >= {AVOID_MIN_EXPECTED}"},
    }
    write_json(WEB_DATA / "meta.json", meta)
    write_json(WEB_DATA / "stories.json", stories)
    write_exports(subs, cats, memb, labels, nets, qids, pos, P_all)
    pipeline = build_pipeline_facts(df, subs, cats, NU, anchor, nets, nets2, memb, labels, stories, cleaning, coverage, summary, commit)
    write_json(WEB_DATA / "pipeline.json", pipeline)
    log(f"done in {time.time() - t0:.0f}s")


# ---------------------------------------------------------------------------
# Stories (every number computed from the networks above)
# ---------------------------------------------------------------------------
IDEOLOGY = ["Conservative", "Libertarian", "socialism", "Anarchism", "democrats", "neoliberal", "CapitalismVSocialism"]
BEAUTY_CRAFT = ["MakeupAddiction", "SkincareAddiction", "femalefashionadvice", "crochet", "knitting"]
STARWARS = ["StarWars", "lego", "comics", "harrypotter", "Marvel", "marvelstudios"]


def avoid_mask(net):
    """The published 'avoided' rule: lower-tail FDR, at most half the expected overlap, enough expected overlap to matter."""
    return net.avoided & (net.affinity <= AVOID_MAX_AFFINITY) & (net.expected >= AVOID_MIN_EXPECTED)


def spearman_rows(X):
    """Spearman correlation of each row of X (n x T) with the time index."""
    from scipy.stats import rankdata
    R = rankdata(X, axis=1)
    t = rankdata(np.arange(X.shape[1]))
    R = R - R.mean(1, keepdims=True); t = t - t.mean()
    den = np.sqrt((R ** 2).sum(1) * (t ** 2).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (R @ t) / den
    out[~np.isfinite(out)] = 0.0
    return out


def build_stories(subs, cats, memb, labels, nets, nets2, periods, qids, months, activity, anchor, P_all, deg_all, per_period, gw, summary):
    S = len(subs); idx = {s: i for i, s in enumerate(subs)}
    iu = np.triu_indices(S, 1)
    m_ids = [p["id"] for p in periods if p["kind"] == "month"]
    all_ids = ["all"] + qids + m_ids
    stories = []
    cos, aff, val = anchor.cosine, anchor.affinity, anchor.validated
    users = anchor.sub_users
    has = lambda *names: all(n in idx for n in names)
    aff_q = lambda a, b: {q: r(nets[q].affinity[idx[a], idx[b]], 2) for q in qids}
    n_valid_periods = lambda a, b: int(sum(nets[p].validated[idx[a], idx[b]] for p in all_ids))

    # =========================================================================================
    # 1. What popularity hides
    # =========================================================================================
    strength = cos.sum(1)
    top_cos = [subs[i] for i in np.argsort(-strength)[:10]]
    hubs_in_top = int(sum(gw[idx[s]] for s in top_cos))
    big_comm = memb[int(np.argmax(users))]
    top_in_big_comm = int(sum(memb[idx[s]] == big_comm for s in top_cos))
    cands = []
    for i in range(S):
        if gw[i] or val[i].sum() < 8:
            continue
        nb_cos, nb_aff = top_neighbours(cos, i, 6), top_neighbours(aff, i, 6, val)
        if aff[i, nb_aff[0]] >= 2:
            cands.append((np.mean(gw[nb_cos]) - np.mean(gw[nb_aff]), users[i], i))
    ex = max(cands)[2]
    ex_cos = [{"name": subs[j], "cosine": r(cos[ex, j]), "affinity": r(aff[ex, j], 2), "gateway": bool(gw[j])} for j in top_neighbours(cos, ex, 6)]
    ex_aff = [{"name": subs[j], "cosine": r(cos[ex, j]), "affinity": r(aff[ex, j], 2), "gateway": bool(gw[j])} for j in top_neighbours(aff, ex, 6, val)]
    biggest = int(np.argmax(users))
    big_aff = aff[biggest][np.arange(S) != biggest]
    big_avoid = int(avoid_mask(anchor)[biggest].sum())
    big_below = int(((aff[biggest] < 1) & (np.arange(S) != biggest)).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        ceiling = np.minimum(users[biggest], users) / anchor.expected[biggest]
    ceiling_median = float(np.median(ceiling[np.arange(S) != biggest]))
    # the largest pair that is NOT a surprising link in any period
    never = np.ones(len(iu[0]), bool)
    for p in all_ids:
        never &= ~nets[p].validated[iu]
    k_big = int(np.argmax(np.where(never, anchor.observed[iu], -1)))
    ga, gb = iu[0][k_big], iu[1][k_big]
    giant = {"a": subs[ga], "b": subs[gb], "shared": int(anchor.observed[ga, gb]), "expected": r(anchor.expected[ga, gb], 0),
             "affinity": r(aff[ga, gb], 2), "cosine": r(cos[ga, gb]), "periods_tested": len(all_ids), "periods_validated": 0,
             "affinity_by_quarter": aff_q(subs[ga], subs[gb])}
    # zero overlap between raw top-5 and adjusted top-5
    zero = [subs[i] for i in range(S) if top_neighbours(aff, i, 5, val) and not set(top_neighbours(cos, i, 5)) & set(top_neighbours(aff, i, 5, val))]
    cos_txt = ", ".join(f"r/{n['name']}" for n in ex_cos[:4])
    aff_txt = ", ".join(f"r/{n['name']} ({n['affinity']}×)" for n in ex_aff[:3])
    stories.append({
        "id": "popularity", "title": "What popularity hides",
        "question": f"Why does everything look connected to r/{subs[biggest]}?",
        "headline": f"By raw shared audience, {hubs_in_top} of the {len(top_cos)} best-connected communities are front-page hubs and all {top_in_big_comm} of {len(top_cos)} sit in the front-page cluster. "
                    f"Once size and user activity are accounted for, hubs make up {summary['hub_share_top10']['affinity'] * 100:.0f}% of a topical subreddit's ten closest "
                    f"neighbours instead of {summary['hub_share_top10']['cosine'] * 100:.0f}%, and for {len(zero)} of {S} subreddits the two top-five lists share no name at all.",
        "metrics": {"cosine_density_all": summary["cosine_density"]["all"], "validated_density_all": summary["validated_density"]["all"],
                    "hub_share_cosine": summary["hub_share_top10"]["cosine"], "hub_share_affinity": summary["hub_share_top10"]["affinity"],
                    "same_category_cosine": summary["same_category_share_top10"]["cosine"], "same_category_affinity": summary["same_category_share_top10"]["affinity"],
                    "top_by_cosine_strength": top_cos, "hubs_in_top10": hubs_in_top, "top10_in_front_page_cluster": top_in_big_comm,
                    "example": subs[ex], "example_cosine_neighbours": ex_cos, "example_affinity_neighbours": ex_aff,
                    "biggest": subs[biggest], "biggest_users": int(users[biggest]), "biggest_median_affinity": r(np.median(big_aff), 2),
                    "biggest_validated_degree": int(val[biggest].sum()), "biggest_below_chance_partners": big_avoid, "biggest_below_expectation_partners": big_below,
                    "biggest_affinity_ceiling_median": r(ceiling_median, 2), "biggest_share_of_commenters": r(users[biggest] / anchor.n_users),
                    "giant_pair": giant, "zero_overlap_count": len(zero), "zero_overlap_examples": zero[:8]},
        "steps": [
            {"view": "raw", "focus": [], "callouts": [idx[s] for s in top_cos[:5]], "period": "all",
             "text": f"Raw view: a line for every pair that shares at least one commenter — {summary['cosine_density']['all'] * 100:.2f}% of all pairs, drawn on the same positions as the adjusted map so you can see which lines survive. "
                     f"The best-connected nodes are the giants: {', '.join('r/' + s for s in top_cos[:5])}."},
            {"view": "adjusted", "focus": [], "period": "all",
             "text": f"Adjusted view: keep only pairs that share far more commenters than user activity and community size predict "
                     f"({summary['validated_density']['all'] * 100:.1f}% of pairs). Topic communities appear."},
            {"view": "adjusted", "focus": [int(ga), int(gb)], "edge": [int(ga), int(gb)], "period": "all",
             "text": f"r/{subs[ga]} and r/{subs[gb]} share {int(anchor.observed[ga, gb]):,} commenters, the largest shared audience of any pair here that is never a surprising link — and "
                     f"within {abs(1 - aff[ga, gb]) * 100:.1f}% of what chance predicts ({aff[ga, gb]:.2f}×). In none of the {len(all_ids)} periods tested is it a surprising link."},
            {"view": "adjusted", "focus": [ex] + [idx[n["name"]] for n in ex_aff], "period": "all", "select": ex,
             "text": f"r/{subs[ex]}: by raw overlap its closest neighbours are {cos_txt}. Adjusted, they are {aff_txt}."},
            {"view": "adjusted", "focus": [idx[s] for s in zero[:12]], "period": "all",
             "text": f"For {len(zero)} of {S} subreddits (for example {', '.join('r/' + s for s in zero[:4])}) the five closest by raw overlap and the five closest by adjusted affinity share no name at all. "
                     f"r/{subs[biggest]} itself holds {users[biggest] / anchor.n_users * 100:.0f}% of all commenters here, so chance already predicts most of its overlap with anyone: its affinity cannot exceed about "
                     f"{ceiling_median:.1f}× by construction, and its overlap falls short of expectation with {big_below} of the other {S - 1} communities."},
        ],
        "caveats": ["Affinity measures co-commenting, not friendship, conversation or influence.",
                    "Raw and adjusted views use the same users and the same communities; only the edge definition changes.",
                    f"For the very largest communities the expected overlap is close to the maximum possible, so their affinity is bounded near 1 by construction (r/{subs[biggest]}: at most ~{ceiling_median:.1f}× with a typical partner)."],
        "takeaway": f"A raw shared-audience map mostly measures size: hubs make up {summary['hub_share_top10']['cosine'] * 100:.0f}% of a topical subreddit's closest neighbours by raw overlap and "
                    f"{summary['hub_share_top10']['affinity'] * 100:.0f}% once size and activity are accounted for. Compare what a pair shares with what chance predicts before calling two communities close.",
    })

    # =========================================================================================
    # 2. Neighbours and strangers
    # =========================================================================================
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
    order = np.argsort(-aff[iu])
    rank_of = {int(k): int(n + 1) for n, k in enumerate(order[:200])}
    k_of = lambda a, b: int(pairIndex_py(idx[a], idx[b], S))

    def pair_facts(a, b):
        i, j = idx[a], idx[b]
        return {"a": a, "b": b, "shared": int(anchor.observed[i, j]), "expected": r(anchor.expected[i, j], 1), "affinity": r(aff[i, j], 2),
                "validated": bool(val[i, j]), "avoided": bool(avoid_mask(anchor)[i, j]), "validated_periods": n_valid_periods(a, b),
                "affinity_by_quarter": aff_q(a, b), "rank": rank_of.get(k_of(a, b))}

    country = {}
    if has("CanadaPolitics", "PersonalFinanceCanada", "ukpolitics", "UKPersonalFinance", "politics", "personalfinance"):
        country = {
            "same_country": [pair_facts("CanadaPolitics", "PersonalFinanceCanada"), pair_facts("ukpolitics", "UKPersonalFinance")],
            "same_topic_across_border": [pair_facts("PersonalFinanceCanada", "UKPersonalFinance"), pair_facts("CanadaPolitics", "ukpolitics")],
            "to_us_default": [pair_facts("CanadaPolitics", "politics"), pair_facts("PersonalFinanceCanada", "personalfinance"),
                              pair_facts("ukpolitics", "politics"), pair_facts("UKPersonalFinance", "personalfinance")],
            "mutual_top_neighbour_periods": {f"{a}|{b}": int(sum(
                top_neighbours(nets[p].affinity, idx[a], 1, nets[p].validated)[:1] == [idx[b]] and top_neighbours(nets[p].affinity, idx[b], 1, nets[p].validated)[:1] == [idx[a]]
                for p in all_ids)) for a, b in [("CanadaPolitics", "PersonalFinanceCanada"), ("ukpolitics", "UKPersonalFinance")]},
            "periods": len(all_ids),
        }
    # audiences that keep apart: lowest affinities among well-measured pairs
    am = avoid_mask(anchor)
    big_exp = anchor.expected[iu] >= 100
    lowest = sorted([k for k in np.where(am[iu] & big_exp)[0]], key=lambda k: aff[iu[0][k], iu[1][k]])[:12]
    lowest_pairs = [{"a": subs[iu[0][k]], "b": subs[iu[1][k]], "shared": int(anchor.observed[iu[0][k], iu[1][k]]), "expected": r(anchor.expected[iu[0][k], iu[1][k]], 0),
                     "affinity": r(aff[iu[0][k], iu[1][k]], 3), "quarters_below_half": int(sum(avoid_mask(nets[q])[iu[0][k], iu[1][k]] for q in qids))} for k in lowest]
    isolation = sorted(range(S), key=lambda i: -am[i].sum())[:8]
    isolation_rows = [{"name": subs[i], "below_chance_partners": int(am[i].sum()), "validated_partners": int(val[i].sum())} for i in isolation]
    median_isolation = float(np.median(am.sum(1)))
    beauty = [s for s in BEAUTY_CRAFT if s in idx]
    blocks = []
    for lab_key in ("Tech, science & ideas", "Money & work"):
        comm_ids = [c for c, lab in labels.items() if lab == lab_key]
        if not comm_ids or not beauty:
            continue
        members = [i for i in range(S) if memb[i] == comm_ids[0] and subs[i] not in beauty]
        bi = [idx[s] for s in beauty]
        sh = sum(anchor.observed[i, j] for i in bi for j in members); ex_ = sum(anchor.expected[i, j] for i in bi for j in members)
        below = sum(am[i, j] for i in bi for j in members)
        by_q = {}
        for q in qids:   # the pooled ratio is not a quarterly one: publish both
            shq = sum(nets[q].observed[i, j] for i in bi for j in members); exq = sum(nets[q].expected[i, j] for i in bi for j in members)
            by_q[q] = r(shq / exq, 2) if exq else None
        blocks.append({"with": lab_key, "n_pairs": len(bi) * len(members), "shared": int(sh), "expected": r(ex_, 0), "affinity": r(sh / ex_, 2), "pairs_below_half": int(below),
                       "affinity_by_quarter": by_q})
    qrange = lambda b: f"{min(v for v in b['affinity_by_quarter'].values() if v is not None)}–{max(v for v in b['affinity_by_quarter'].values() if v is not None)}×"
    ideo = [s for s in IDEOLOGY if s in idx]
    ideology = {}
    if len(ideo) >= 4:
        pr = [(a, b) for k, a in enumerate(ideo) for b in ideo[k + 1:]]
        affs = [aff[idx[a], idx[b]] for a, b in pr]
        ideology = {"subreddits": ideo, "pairs": len(pr), "validated": int(sum(val[idx[a], idx[b]] for a, b in pr)),
                    "below_chance": int(sum(am[idx[a], idx[b]] for a, b in pr)), "min_affinity": r(min(affs), 2), "median_affinity": r(float(np.median(affs)), 2),
                    "weakest_pair": [p for p, x in zip(pr, affs) if x == min(affs)][0]}
    sc = country.get("same_country", [])
    def pair_txt(x):
        return (f"r/{x['a']} ({CATEGORY_LABELS[x['cat_a']].lower()}) and r/{x['b']} ({CATEGORY_LABELS[x['cat_b']].lower()}) share "
                f"{x['shared_all']:,} commenters where {x['expected_all']:,.0f} were expected — at least {x['min_affinity']}× in every quarter.")
    steps = [{"view": "adjusted", "period": "all", "focus": [x["ia"], x["ib"]], "edge": [x["ia"], x["ib"]], "text": pair_txt(x)} for x in lead[:2]]
    if country:
        pair_status = lambda u: "surprising but small" if u["validated"] else ("fewer than chance" if u["avoided"] else ("below expectation" if u["affinity"] < 0.9 else "within chance"))
        c1, c2 = country["same_country"]; xb = country["same_topic_across_border"][0]; us = country["to_us_default"]
        mut = country["mutual_top_neighbour_periods"][f"{c1['a']}|{c1['b']}"]
        steps[0]["text"] += (f" The two are each other's closest neighbour in {'all ' if mut == country['periods'] else ''}{mut}{'' if mut == country['periods'] else ' of ' + str(country['periods'])} periods, "
                             f"and this is the strongest link between two different categories in the whole map (rank {c1['rank']} of {len(iu[0]):,} pairs).")
        steps.append({"view": "adjusted", "period": "all", "focus": [idx[xb["a"]], idx[xb["b"]], idx["personalfinance"], idx["politics"]], "edge": [idx[xb["a"]], idx[xb["b"]]],
                      "text": f"The control: same topic across the border. r/{xb['a']} and r/{xb['b']} share {xb['shared']} commenters where {xb['expected']:.0f} were expected ({xb['affinity']}×), "
                              f"fewer than chance in every quarter. The national subreddits' ties to the US-default r/politics and r/personalfinance are modest by comparison: "
                              f"{'; '.join(f'{u["a"]}–{u["b"]} {u["affinity"]}× ({pair_status(u)})' for u in us)}."})
    if lowest_pairs:
        lp = lowest_pairs[0]
        steps.append({"view": "adjusted", "period": "all", "focus": sorted({idx[x["a"]] for x in lowest_pairs[:6]} | {idx[x["b"]] for x in lowest_pairs[:6]}),
                      "text": f"The same test in the other direction finds audiences that keep apart. r/{lp['a']} and r/{lp['b']} share {lp['shared']} commenters where {lp['expected']:.0f} were expected ({lp['affinity']}×). "
                              + (f"Taken together, the five beauty, fashion and fibre-craft communities share {blocks[0]['affinity']}× of the expected overlap with the {blocks[0]['with'].lower()} cluster ({qrange(blocks[0])} by quarter)"
                                 + (f" and {blocks[1]['affinity']}× with the {blocks[1]['with'].lower()} cluster ({qrange(blocks[1])} by quarter)" if len(blocks) > 1 else "") + "." if blocks else "")
                              + f" Some communities keep apart from almost everyone: r/{isolation_rows[0]['name']} shares fewer commenters than chance with {isolation_rows[0]['below_chance_partners']} of {S - 1} (the median community: {median_isolation:.1f})."})
    if ideology:
        wa, wb = ideology["weakest_pair"]
        steps.append({"view": "adjusted", "period": "all", "focus": [idx[s] for s in ideo],
                      "text": f"Political opponents are not strangers: none of the {ideology['pairs']} pairs among {', '.join('r/' + s for s in ideo)} shares fewer commenters than chance, and "
                              f"{ideology['validated']} of {ideology['pairs']} share more (weakest r/{wa}–r/{wb} at {ideology['min_affinity']}×, median {ideology['median_affinity']}×)."})
    stories.append({
        "id": "neighbours", "title": "Neighbours and strangers",
        "question": f"What do r/{lead[0]['a']} and r/{lead[0]['b']} have in common — and which audiences never meet?",
        "headline": f"{len(rows)} links join communities from different topic categories and hold in every quarter under both activity thresholds; the strongest two are a country's politics forum and the same country's personal-finance forum "
                    f"(at least {lead[0]['min_affinity']}× and {lead[1]['min_affinity']}× chance in every quarter), while the same personal-finance topic across the border sits far below chance"
                    + (f" ({country['same_topic_across_border'][0]['affinity']}×)" if country else "") + ". The widest gulfs in the sample are not political: "
                    + (f"r/{lowest_pairs[0]['a']} and r/{lowest_pairs[0]['b']} share {lowest_pairs[0]['affinity']}× of the expected overlap." if lowest_pairs else ""),
        "metrics": {"robust_cross_category_links": len(rows), "robust_cross_community_links": len(cross), "top_links": rows[:15], "top_cross_community_links": cross[:10],
                    "country": country, "lowest_pairs": lowest_pairs, "isolation": isolation_rows, "median_below_chance_partners": median_isolation,
                    "blocks": blocks, "beauty_craft": beauty, "ideology": ideology,
                    "avoided_rule": f"lower-tail FDR {ALPHA}, affinity <= {AVOID_MAX_AFFINITY}, expected >= {AVOID_MIN_EXPECTED}"},
        "steps": steps,
        "caveats": ["Shared audiences can reflect shared geography, profession or demographics; without comment text we cannot say which, and the data cannot say why two audiences keep apart.",
                    "Only two same-country pairs exist in the frame, so 'country beats topic' is consistent with these cases, not a general law.",
                    "Category labels come from a keyword rule and can be wrong (see Scope & limits)."],
        "takeaway": f"The same test that finds surprising neighbours also finds strangers. r/{lead[0]['a']} and r/{lead[0]['b']} share {lead[0]['shared_all']:,} commenters where {lead[0]['expected_all']:,.0f} were expected; "
                    + (f"the same personal-finance topic across the border shares {country['same_topic_across_border'][0]['affinity']}× of expectation; " if country else "")
                    + (f"and r/{lowest_pairs[0]['a']} and r/{lowest_pairs[0]['b']} share {lowest_pairs[0]['affinity']}×. " if lowest_pairs else "")
                    + "Which audiences meet is a fact in the data; why is not.",
    })

    # =========================================================================================
    # 3. Connectors and sealed rooms
    # =========================================================================================
    Pq = np.stack([per_period[q]["P"] for q in qids], 1)
    P_min = Pq.min(1)
    eligible = [i for i in range(S) if deg_all[i] >= 8]
    conn = sorted(eligible, key=lambda i: -P_min[i])[:10]
    conn_rows = [{"name": subs[i], "category": cats[i], "community": labels[int(memb[i])], "participation_min": r(P_min[i]),
                  "participation_all": r(P_all[i]), "degree": int(deg_all[i]), "users": int(users[i]), "gateway": bool(gw[i]),
                  "communities_reached": int(len({int(memb[j]) for j in np.where(val[i])[0]}))} for i in conn]
    # per-quarter rank of the top connectors among the eligible communities, and the baseline for the participation score
    def _rank_in(q, i):
        Pq = per_period[q]["P"]
        return 1 + sum(1 for j in eligible if Pq[j] > Pq[i])
    conn_max_rank = {subs[i]: max(_rank_in(q, i) for q in qids) for i in conn[:3]}
    conn_baseline = float(np.median([P_min[i] for i in eligible]))
    stab = summary["participation_rank_stability"]
    # outward share per community, against a configuration-model expectation (degrees fixed, partners random)
    A = val.copy(); np.fill_diagonal(A, False)
    deg = A.sum(1); two_m = deg.sum()
    outward = []
    for c in sorted(labels):
        mem = np.where(memb == c)[0]
        if len(mem) < 5:
            continue
        inside = int(A[np.ix_(mem, mem)].sum() / 2); total_ends = int(deg[mem].sum())
        out_links = total_ends - 2 * inside
        exp_out = 1 - deg[mem].sum() / two_m
        obs_out = out_links / (inside + out_links) if (inside + out_links) else 0.0
        outward.append({"community": labels[c], "id": int(c), "members": int(len(mem)), "links_inside": inside, "links_outward": int(out_links),
                        "outward_share": r(obs_out), "expected_outward_share": r(exp_out), "outward_vs_expected": r(obs_out / exp_out if exp_out else 0, 2)})
    outward.sort(key=lambda x: -x["outward_vs_expected"])
    bloc = np.where(memb == big_comm)[0]
    ask_in = int(sum(val[biggest, j] for j in bloc if j != biggest)); ask_out = int(sum(val[biggest, j] for j in range(S) if memb[j] != big_comm))
    ask_below_out = int(sum(aff[biggest, j] < 1 for j in range(S) if memb[j] != big_comm and j != biggest))
    ask_above_in = int(sum(aff[biggest, j] > 1 for j in bloc if j != biggest))
    giants = {"name": subs[biggest], "bloc": labels[int(big_comm)], "bloc_size": int(len(bloc)), "links_inside_bloc": ask_in, "links_outside_bloc": ask_out,
              "above_expectation_inside_bloc": ask_above_in, "below_expectation_outside_bloc": ask_below_out, "outside_bloc_count": int((memb != big_comm).sum())}
    top5 = conn_rows[:5]
    stories.append({
        "id": "connectors", "title": "Connectors and sealed rooms",
        "question": "Which communities quietly connect different parts of this map, and which keep to themselves?",
        "headline": f"r/{top5[0]['name']}'s surprising links reach {top5[0]['communities_reached']} different clusters and r/{top5[1]['name']}'s {top5[1]['communities_reached']}; "
                    f"{outward[0]['community']} sends {outward[0]['outward_share'] * 100:.0f}% of its links to other clusters while {outward[-1]['community']} sends {outward[-1]['outward_share'] * 100:.0f}%, "
                    f"and r/{subs[biggest]}, the largest community of all, has every one of its {ask_in + ask_out} surprising links inside its own cluster.",
        "metrics": {"connectors": conn_rows, "rank_stability": stab, "min_degree": 8, "outward": outward, "giants": giants,
                    "hub_mean_participation": r(P_all[gw].mean()), "topical_mean_participation": r(P_all[~gw].mean()),
                    "note": "The difference between hub and topical mean participation is not statistically significant (permutation p ≈ 0.3) and is not claimed."},
        "steps": [
            {"view": "adjusted", "period": "all", "focus": [], "callouts": [idx[c["name"]] for c in top5], "colorBy": "community",
             "text": f"r/{top5[0]['name']}'s surprising links reach {top5[0]['communities_reached']} clusters (its own included), r/{top5[1]['name']}'s {top5[1]['communities_reached']} and r/{top5[2]['name']}'s {top5[2]['communities_reached']}: "
                     f"over the whole window these are the three communities whose surprising links spread most evenly across clusters, and each ranks among the {max(conn_max_rank.values())} most even in every quarter."},
        ] + [{"view": "adjusted", "period": "all", "focus": [idx[c["name"]]], "select": idx[c["name"]],
              "text": f"r/{c['name']} ({CATEGORY_LABELS[c['category']].lower()}): {c['degree']} surprising links into {c['communities_reached']} clusters. Its participation score — 0 if every link stayed in its own cluster, "
                      f"towards 1 if links spread evenly — is at least {c['participation_min']} in every quarter (median among the {len(eligible)} communities with at least 8 links: {conn_baseline:.2f})."} for c in top5[:3]]
        + [{"view": "adjusted", "period": "all", "focus": [], "colorBy": "community",
            "text": f"Clusters differ in how sealed they are. {outward[0]['community']} sends {outward[0]['outward_share'] * 100:.0f}% of its surprising links to other clusters "
                    f"({outward[0]['outward_vs_expected']}× what its size alone would give); {outward[-1]['community']} sends {outward[-1]['outward_share'] * 100:.0f}% ({outward[-1]['outward_vs_expected']}×)."},
           {"view": "adjusted", "period": "all", "focus": [biggest], "select": biggest,
            "text": f"r/{subs[biggest]} is the opposite of a connector: all {ask_in + ask_out} of its surprising links are inside the {giants['bloc'].lower()} cluster, it is above expectation with {ask_above_in} of the other {len(bloc) - 1} members of that cluster, "
                    f"and below expectation with {ask_below_out} of the {giants['outside_bloc_count']} communities outside it. Part of this is arithmetic: holding {users[biggest] / anchor.n_users * 100:.0f}% of all commenters, it cannot share much more than chance with anyone."}],
        "caveats": ["Participation depends on the community partition; rank stability across quarters: " + ", ".join(f"{k} ρ={v}" for k, v in stab.items()) + ".",
                    "A connector shares unusually many commenters with several clusters; that is not evidence that information flows through it.",
                    "Front-page hubs average a lower participation score than topical communities, but the difference is not statistically significant and is not claimed."],
        "takeaway": f"The communities that bridge this map are mid-sized and topical (r/{top5[0]['name']}, r/{top5[1]['name']}, r/{top5[2]['name']}); clusters differ in how sealed they are "
                    f"({outward[0]['community']} most open, {outward[-1]['community']} most closed); and r/{subs[biggest]}, the largest community of all, keeps every one of its surprising links inside its own cluster.",
    })

    # =========================================================================================
    # 4. When crowds arrive and leave
    # =========================================================================================
    MA = np.array(activity["monthly_authors"]); frame_auth = np.array(activity["frame_monthly_authors"])
    crypto = [s for s in CRYPTO if s in idx]; marvel = [s for s in MARVEL if s in idx]; sw = [s for s in STARWARS if s in idx]
    series = lambda names: {n: MA[idx[n]].tolist() for n in names if n in idx}
    pair_aff = lambda a, b, use=nets: [r(use[m].affinity[idx[a], idx[b]], 2) if m in use else None for m in m_ids]
    cross_rate = lambda a, b: [r(nets[m].observed[idx[a], idx[b]] / max(1, nets[m].sub_users[idx[a]])) for m in m_ids]
    cosine_m = lambda a, b: [r(nets[m].cosine[idx[a], idx[b]]) for m in m_ids]
    peak = {s: months[int(np.argmax(MA[idx[s]]))] for s in crypto + marvel + sw[:1]}
    jan = months.index(peak[crypto[0]]); mjan = months.index("2018-01") if "2018-01" in months else 0
    change = {s: r(MA[idx[s]][-1] / MA[idx[s]][jan] - 1) for s in crypto + CRYPTO_COMPARISON if s in idx}
    frame_change = r(frame_auth[-1] / frame_auth[jan] - 1)
    cp = (crypto[0], crypto[1])
    ca, ca2 = pair_aff(*cp), pair_aff(*cp, nets2)
    rate_ab, rate_ba, cosm = cross_rate(*cp), cross_rate(cp[1], cp[0]), cosine_m(*cp)
    # Star Wars crowd (December 2017)
    starwars = {}
    if sw and "2017-12" in months and "2017-11" in months:
        i_sw = idx[sw[0]]; d, n_ = months.index("2017-12"), months.index("2017-11")
        partners = [s for s in sw[1:] if s in idx]
        starwars = {"name": sw[0], "monthly_authors": MA[i_sw].tolist(), "dec_over_nov": r(MA[i_sw][d] / MA[i_sw][n_], 2),
                    "new_share_dec": activity["monthly_new_share"][i_sw][d],
                    "partner_affinity": {p: pair_aff(sw[0], p) for p in partners}, "partner_cross_rate": {p: cross_rate(sw[0], p) for p in partners},
                    "release": "2017-12-15"}
    marvel_block = {}
    if len(marvel) == 2:
        marvel_block = {"pair": marvel, "affinity": pair_aff(*marvel), "affinity_min2": pair_aff(*marvel, nets2), "cross_rate_ab": cross_rate(*marvel), "cross_rate_ba": cross_rate(marvel[1], marvel[0]),
                        "monthly_authors": series(marvel)}
    # growth vs affinity drift across stable, well-measured ties
    E = np.stack([nets[m].expected[iu] for m in m_ids]); V = np.stack([nets[m].validated[iu] for m in m_ids]); AFm = np.stack([nets[m].affinity[iu] for m in m_ids]); CO = np.stack([nets[m].cosine[iu] for m in m_ids])
    stable = (E.min(0) >= 20) & (V.sum(0) >= 7)
    tr_aff = spearman_rows(AFm[:, stable].T); tr_cos = spearman_rows(CO[:, stable].T)
    ia, ib = iu[0][stable], iu[1][stable]
    growth = np.log(nets[qids[-1]].sub_users / np.maximum(1, nets[qids[0]].sub_users))
    node_tr, node_trc, node_g = [], [], []
    for i in range(S):
        sel = (ia == i) | (ib == i)
        if sel.sum() >= 5:
            node_tr.append(tr_aff[sel].mean()); node_trc.append(tr_cos[sel].mean()); node_g.append(growth[i])
    from scipy.stats import spearmanr
    tendency = {"n_subreddits": len(node_g), "n_stable_ties": int(stable.sum()),
                "spearman_growth_vs_affinity_trend": r(spearmanr(node_g, node_tr)[0], 2), "spearman_growth_vs_cosine_trend": r(spearmanr(node_g, node_trc)[0], 2),
                "definition": "ties with monthly expected overlap >= 20 in all months and validated in >= 7 of 12; trend = Spearman of the tie's monthly value against time; node value = mean over its ties; growth = log commenters last quarter / first quarter"}
    crypto_line = ", ".join(f"r/{s} {change[s] * 100:+.0f}%" for s in crypto[:3])
    crowd = {"months": months, "crypto_monthly_authors": series(crypto), "comparison_monthly_authors": series(CRYPTO_COMPARISON + MARVEL_COMPARISON),
             "marvel_monthly_authors": series(marvel), "frame_monthly_authors": frame_auth.tolist(), "peak_month": peak, "baseline_month": months[jan],
             "change_since_baseline": change, "frame_change_since_baseline": frame_change,
             "crypto_pair_affinity": {f"{cp[0]}|{cp[1]}": ca}, "crypto_pair_affinity_min2": {f"{cp[0]}|{cp[1]}": ca2},
             "crypto_cross_rate_ab": rate_ab, "crypto_cross_rate_ba": rate_ba, "crypto_pair_cosine": cosm,
             "marvel_pair_affinity": {f"{marvel[0]}|{marvel[1]}": marvel_block["affinity"]} if marvel_block else {},
             "marvel_pair_affinity_min2": {f"{marvel[0]}|{marvel[1]}": marvel_block["affinity_min2"]} if marvel_block else {},
             "marvel": marvel_block, "starwars": starwars,
             "new_share": {s: [None] + activity["monthly_new_share"][idx[s]][1:] for s in crypto[:2] + marvel + sw[:1] if s in idx},
             "events": EVENTS, "tendency": tendency}
    apr = months.index("2018-04") if "2018-04" in months else None
    ma = marvel_block.get("affinity")
    W = np.array(activity["weekly_authors"]); weeks = activity["weeks"]
    ms_ = idx.get("marvelstudios"); rel_wk = weeks.index("2018-04-23") if "2018-04-23" in weeks else None
    mar_wks = [weeks.index(w) for w in weeks if w.startswith("2018-03")]
    marvel_base = int(np.median(W[ms_, mar_wks])) if ms_ is not None and mar_wks else None
    marvel_peak_wk = int(W[ms_, rel_wk]) if ms_ is not None and rel_wk is not None else None
    crowd["marvel_release_week"] = {"week": "2018-04-23", "authors": marvel_peak_wk, "march_median_weekly": marvel_base}
    steps = [
        {"view": "timeline", "group": "crypto", "focus": [idx[s] for s in crypto], "period": months[0],
         "text": f"Monthly commenters, {mlabel(months[0])} to {mlabel(months[-1])}. r/{crypto[0]} peaks in {mlabel(peak[crypto[0]])} (Bitcoin's price peaked on 17 Dec 2017) and then falls steeply ({crypto_line} by {mlabel(months[-1])}) "
                 f"while r/investing and the frame as a whole ({frame_change * 100:+.0f}%) do not."},
        {"view": "adjusted", "focus": [idx[s] for s in crypto], "period": months[jan], "select": idx[crypto[0]],
         "text": f"The obvious reading. At the peak, r/{cp[0]}–r/{cp[1]} affinity is {ca[jan]}×; by {mlabel(months[-1])} it is {ca[-1]}× ({ca2[-1]}× under the stricter threshold). It looks as if the people who stayed were much more tightly bound."},
        {"view": "adjusted", "focus": [idx[s] for s in crypto], "period": months[-1], "select": idx[crypto[0]],
         "text": f"The careful reading. The share of r/{cp[0]} commenters who also posted in r/{cp[1]} moved only from {rate_ab[jan] * 100:.0f}% to {rate_ab[-1] * 100:.0f}%, the reverse share fell from {rate_ba[jan] * 100:.0f}% to {rate_ba[-1] * 100:.0f}%, "
                 f"and raw overlap (cosine) fell from {cosm[jan]:.2f} to {cosm[-1]:.2f}. The ratio rose because the expected overlap shrinks with the communities: affinity compares against a size-dependent expectation."},
    ]
    if starwars:
        d = months.index("2017-12"); n_ = months.index("2017-11"); p0 = list(starwars["partner_affinity"])[:3]
        steps.append({"view": "timeline", "group": "starwars", "focus": [idx[sw[0]]] + [idx[p] for p in p0], "period": "2017-12",
                      "text": f"A crowd arriving. In December 2017 (The Last Jedi, 15 Dec) r/{sw[0]} had {MA[idx[sw[0]]][d]:,} commenters, {starwars['dec_over_nov']}× November; {starwars['new_share_dec'] * 100:.0f}% of them had not commented there earlier in the window (later months, with more history to look back on: about {np.nanmedian([v for k_, v in enumerate(activity["monthly_new_share"][idx[sw[0]]]) if v is not None and k_ not in (0, d)]) * 100:.0f}%). "
                              f"Its affinity with each of its five fandom neighbours here ({', '.join('r/' + p for p in starwars['partner_affinity'])}) dipped that month ("
                              f"{', '.join(f'r/{p} {starwars["partner_affinity"][p][n_]}× → {starwars["partner_affinity"][p][d]}×' for p in p0)}) and recovered in January: the same arithmetic in reverse."})
    if ma and apr is not None and marvel_base:
        steps.append({"view": "timeline", "group": "marvel", "focus": [idx[s] for s in marvel], "period": "2018-04",
                      "text": f"Avengers: Infinity War opened in the US on 27 April 2018. r/marvelstudios went from ~{marvel_base:,} weekly commenters in March to {marvel_peak_wk:,} in the release week; "
                              f"r/{marvel[0]}–r/{marvel[1]} affinity fell from {ma[mjan]}× in {mlabel(months[mjan])} to {ma[apr]}× in April and recovered to {ma[-1]}× by {mlabel(months[-1])}."})
    steps.append({"view": "adjusted", "focus": [], "period": "all",
                  "text": f"Across the {tendency['n_subreddits']} communities with at least five stable, well-measured ties, faster growth over the year went with a downward drift in affinity (Spearman ρ = {tendency['spearman_growth_vs_affinity_trend']}) "
                          f"while raw overlap drifted up (ρ = {tendency['spearman_growth_vs_cosine_trend']}). Most of the 'change' in affinity is the expectation moving with size, not people changing where they comment."})
    stories.append({
        "id": "crowds", "title": "When crowds arrive and leave",
        "question": "What happens to a community's ties when a crowd suddenly arrives — or leaves?",
        "headline": f"After the Bitcoin peak, crypto communities lost most of their commenters ({crypto_line}, {mlabel(months[jan])} → {mlabel(months[-1])}) while the whole frame changed {frame_change * 100:+.0f}%. "
                    f"Their affinity to each other rose ({ca[jan]}× → {ca[-1]}×) — but the share of r/{cp[0]} commenters also in r/{cp[1]} barely moved ({rate_ab[jan] * 100:.0f}% → {rate_ab[-1] * 100:.0f}%): the ratio climbed because the expected overlap shrank with the communities. "
                    f"Crowds arriving (The Last Jedi, Infinity War) show the same arithmetic in reverse.",
        "metrics": crowd,
        "steps": steps,
        "caveats": ["Event dates are external context. Activity changing around an event is an association, not proof the event caused it.",
                    "Affinity compares observed overlap with an expectation that scales with community size, so sharp changes in size move it even when cross-posting behaviour does not.",
                    "Comments only: lurkers, votes and private communities are invisible; Pushshift-derived archives have gaps, so counts are lower bounds."],
        "takeaway": f"Crowds leave a clear trace in the counts ({crypto_line}; r/{sw[0] if sw else 'StarWars'} ×{starwars.get('dec_over_nov', '?')} in one month), but a changed affinity is not by itself a changed behaviour: "
                    f"check the share of commenters who actually cross over before calling a community's ties tighter or looser.",
    })

    # validity notes: a label the network corrected, plus a count of frame labels the network disagrees with
    vig = []
    cat_list = sorted(set(cats))
    mismatch = []
    for i in range(S):
        means = {c: float(np.mean([aff[i, j] for j in range(S) if j != i and cats[j] == c])) for c in cat_list}
        best = max(means, key=means.get)
        if best != cats[i] and best != "gateway":
            mismatch.append({"name": subs[i], "frame": cats[i], "network": best})
    for s in ("smoking",):
        if s in idx:
            i = idx[s]
            nb = top_neighbours(aff, i, 5, val)
            vig.append({"name": s, "label": cats[i], "community": labels[int(memb[i])],
                        "neighbours": [{"name": subs[j], "affinity": r(aff[i, j], 2), "category": cats[j]} for j in nb],
                        "peak_month": months[int(np.argmax(MA[i]))]})
    return {"stories": stories, "validity_notes": vig, "label_mismatch": {"definition": "frame category vs the category with the highest mean affinity (whole window, hubs excluded as a target)",
                                                                           "count": len(mismatch), "examples": mismatch[:16]}}


def pairIndex_py(i, j, S):
    if i > j:
        i, j = j, i
    return i * S - i * (i + 1) // 2 + (j - i - 1)


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



# ---------------------------------------------------------------------------
# Facts for the technical walkthrough (atlas/web/data/pipeline.json)
# ---------------------------------------------------------------------------
def _tests_inventory():
    """Every test function in tests/, with the first line of its docstring."""
    import ast
    tests, modules = [], {}
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        mod_doc = (ast.get_docstring(tree) or "").strip().splitlines()
        modules[f.name] = (mod_doc[0] if mod_doc else "").replace("author_h", "author id")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                doc = (ast.get_docstring(node) or "").strip().splitlines()
                tests.append({"file": f.name, "name": node.name, "doc": (doc[0] if doc else "").replace("author_h", "author id")})
    return tests, modules


def _artifact_inventory():
    """Size and sha256 prefix of every published data file and export (pipeline.json itself excluded)."""
    import hashlib
    files = []
    for f in sorted(WEB_DATA.glob("*.json")) + sorted(EXPORTS.glob("*")):
        if f.name == "pipeline.json":
            continue
        files.append({"file": f.relative_to(WEB_DATA.parent).as_posix(), "bytes": f.stat().st_size,
                      "sha256": hashlib.sha256(f.read_bytes()).hexdigest()[:12]})
    return files


def _pair_facts(net, net2, M, ku, subs, a, b):
    i, j = subs.index(a), subs.index(b)
    both = np.asarray(M[:, i].multiply(M[:, j]).sum(1)).ravel() > 0
    deg = ku[both]
    buckets = [("2", 2, 2), ("3–5", 3, 5), ("6–10", 6, 10), ("11–20", 11, 20), ("21+", 21, 10**9)]
    return {
        "a": a, "b": b, "users_a": int(net.sub_users[i]), "users_b": int(net.sub_users[j]),
        "shared": int(net.observed[i, j]), "expected": round(float(net.expected[i, j]), 1),
        "affinity": round(float(net.affinity[i, j]), 2), "cosine": round(float(net.cosine[i, j]), 4),
        "p_high": float(f"{net.pvalues[i, j]:.1e}"), "p_low": float(f"{net.pvalues_low[i, j]:.1e}"),
        "validated": bool(net.validated[i, j]), "robust": bool(net2.validated[i, j]) if net2 is not None else None,
        "shared_users_by_breadth": [{"breadth": lab, "n": int(((deg >= lo) & (deg <= hi)).sum())} for lab, lo, hi in buckets],
        "shared_users_median_breadth": int(np.median(deg)) if len(deg) else None,
    }


def build_pipeline_facts(df, subs, cats, NU, anchor, nets, nets2, memb, labels, stories, cleaning, coverage, summary, commit):
    import hashlib
    import scipy.sparse as sp
    S = len(subs); iu = np.triu_indices(S, 1)
    d = df[["u", "s"]].drop_duplicates()
    M = presence_matrix(d.u.values, d.s.values, NU, S).tocsc()
    ku = np.asarray(M.sum(1)).ravel().astype(int)
    active = ku > 0
    edges_per_user = ku * (ku - 1) // 2
    hist = [("1", 1, 1), ("2", 2, 2), ("3–5", 3, 5), ("6–10", 6, 10), ("11–20", 11, 20), ("21–50", 21, 50), ("51+", 51, 10**9)]
    breadth = [{"breadth": lab, "users": int(((ku >= lo) & (ku <= hi)).sum()),
                "pairs_linked": int(edges_per_user[(ku >= lo) & (ku <= hi)].sum())} for lab, lo, hi in hist]
    top_user_k = int(ku.max())
    # how many pairs would still share a commenter if only "narrow" users (<= 5 subreddits) counted
    narrow = M[ku <= 5]
    V_narrow = np.asarray((narrow.T @ narrow).todense())
    pairs_any = int((anchor.observed[iu] > 0).sum()); pairs_narrow = int((V_narrow[iu] > 0).sum())

    A = stories["stories"][0]["metrics"]; B = stories["stories"][1]["metrics"]
    lead = B["top_links"][0]
    ex = [_pair_facts(anchor, nets2.get("all"), M, ku, subs, lead["a"], lead["b"]),
          _pair_facts(anchor, nets2.get("all"), M, ku, subs, A["biggest"], A["example"])]

    # toy example: 8 users x 4 subreddits, run through the real model
    toy_names = ["A", "B", "C", "D"]
    toy_rows = np.array([[1, 1, 0, 0], [1, 1, 0, 0], [1, 0, 0, 0], [0, 1, 1, 0], [0, 0, 1, 1], [0, 0, 1, 1], [1, 1, 1, 1], [1, 0, 0, 1]])
    toy_net = affinity_network(sp.csr_matrix(toy_rows.astype(float)), toy_names, 0.01)
    toy_fit = fit_bicm(sp.csr_matrix(toy_rows.astype(float)))
    toy_ku = toy_rows.sum(1)
    toy_p = toy_fit.p[np.searchsorted(toy_fit.degree_values, toy_ku)]
    tiu = np.triu_indices(4, 1)
    toy = {
        "users": [f"u{k + 1}" for k in range(8)], "subreddits": toy_names, "matrix": toy_rows.tolist(),
        "user_breadth": toy_ku.tolist(), "subreddit_size": toy_rows.sum(0).tolist(),
        "fitted_probabilities": np.round(toy_p, 2).tolist(),
        "pairs": [{"a": toy_names[i], "b": toy_names[j], "shared": int(toy_net.observed[i, j]), "expected": round(float(toy_net.expected[i, j]), 2),
                   "affinity": round(float(toy_net.affinity[i, j]), 2)} for i, j in zip(*tiu)],
    }

    tests, test_modules = _tests_inventory()
    files = _artifact_inventory()
    raw = sum(int(r["rows_raw"]) for r in cleaning); kept = sum(int(r["rows_clean"]) for r in cleaning)
    deg_all = anchor.validated.sum(1).astype(int)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "git_commit": commit,
        "stages": {
            "archive": {"source": "open-index/arctic (Arctic Shift re-packaging of Pushshift dumps), read remotely with DuckDB",
                        "months": summary["months"], "quarters": [r["quarter"] for r in coverage],
                        "frame_subreddits": S, "coverage": [{"quarter": r["quarter"], "status": r["status"], "rows": int(r["rows"])} for r in coverage]},
            "clean": {"raw_comments": raw, "kept_comments": kept, "kept_share": round(kept / raw, 4),
                      "users_raw": sum(int(r["users_raw"]) for r in cleaning), "users_kept": sum(int(r["users_clean"]) for r in cleaning),
                      "bots_removed": sum(int(r["hard_bots_removed"]) for r in cleaning),
                      "rules": ["keep accounts with >= 5 comments in the quarter",
                                "remove accounts with >= 2,000 comments that are active in >= 50% of the frame (bots)",
                                "drop [deleted] and AutoModerator",
                                "hash usernames with a private salt (SHA-256) inside the query; keep no text"]},
            "bipartite": {"users": int(active.sum()), "subreddits": S, "presence_links": int(M.nnz),
                          "breadth_histogram": breadth, "max_breadth": top_user_k,
                          "pairs_linked_by_max_breadth_user": int(top_user_k * (top_user_k - 1) // 2),
                          "median_breadth": int(np.median(ku[active]))},
            "raw_overlap": {"pairs_total": int(len(iu[0])), "pairs_sharing_any": pairs_any,
                            "pairs_sharing_any_if_only_narrow_users": pairs_narrow, "narrow_user_definition": "active in <= 5 frame subreddits",
                            "cosine_density": round(pairs_any / len(iu[0]), 4)},
            "expected": {"model": "Bipartite Configuration Model (Saracco et al. 2015)", "unknowns": int(len(np.unique(ku[active])) + S),
                         "fit_max_error": float(f"{anchor.fit_error:.1e}"), "formula": "expected(a,b) = sum over users u of p(u,a) x p(u,b)"},
            "validated": {"test": "one-sided Poisson tail, Benjamini-Hochberg FDR", "alpha": ALPHA, "validated_pairs": int(anchor.validated[iu].sum()),
                          "density": round(float(anchor.validated[iu].mean()), 4),
                          "robust_pairs": int((anchor.validated[iu] & nets2["all"].validated[iu]).sum()) if "all" in nets2 else None,
                          "avoided_pairs": int((anchor.avoided[iu] & (anchor.affinity[iu] <= AVOID_MAX_AFFINITY) & (anchor.expected[iu] >= AVOID_MIN_EXPECTED)).sum()),
                          "isolated_subreddits": int((deg_all == 0).sum()), "median_degree": int(np.median(deg_all))},
            "communities": {"method": "Leiden, modularity (gamma = 1), log-affinity weights, best of 20 seeds", "count": int(len(set(memb))),
                            "weighted_modularity": summary["anchor"]["weighted_modularity"], "seed_ari": summary["anchor"]["seed_ari"],
                            "sensitivity_ari": summary["anchor"]["sensitivity_ari"], "labels": {int(k): v for k, v in labels.items()}},
            "temporal": {"periods": len(summary["validated_density"]), "quarter_edge_jaccard": summary["quarter_edge_jaccard"],
                         "month_edge_jaccard": summary["month_edge_jaccard"]},
        },
        "examples": ex, "toy": toy,
        "tests": tests, "test_modules": test_modules,
        "artifacts": files,
        "validation": {"reference_crosscheck_file": "atlas/validation/bicm_crosscheck.json"},
    }


def _net_from_pairs(path: Path, subs: list[str]) -> AffinityNetwork:
    """Rebuild an AffinityNetwork from a published pairs_<period>.json (everything except the user matrix)."""
    p = json.loads(path.read_text(encoding="utf-8"))
    S = len(subs); iu = np.triu_indices(S, 1)
    def sym(vals, dtype=float, diag=0.0):
        M = np.full((S, S), diag, dtype=dtype); M[iu] = vals; M.T[iu] = vals; return M
    V = sym(p["shared"], float); E = sym(p["expected"], float)
    P = sym(p["p_high"], float, 1.0); PL = sym(p["p_low"], float, 1.0)
    val = np.zeros(len(iu[0]), bool); val[p["validated"]] = True
    av = np.zeros(len(iu[0]), bool); av[p["avoided"]] = True
    users = np.array(p["users"], float)
    return AffinityNetwork(subs, V, E, P, sym(val, bool, False), users, int(p.get("n_users") or users.max()), ALPHA, 0.0, sym(p["cosine"], float), PL, sym(av, bool, False))


def rebuild_stories_from_artifacts():
    meta = json.loads((WEB_DATA / "meta.json").read_text(encoding="utf-8"))
    nodes = json.loads((WEB_DATA / "nodes.json").read_text(encoding="utf-8"))
    activity = json.loads((WEB_DATA / "activity.json").read_text(encoding="utf-8"))
    subs = [n["name"] for n in nodes]; cats = [n["category"] for n in nodes]
    memb = np.array([n["community"] for n in nodes]); labels = {c["id"]: c["label"] for c in meta["communities"]}
    periods = [{"id": p["id"], "kind": p["kind"], "label": p["label"]} for p in meta["periods"]]
    qids = [p["id"] for p in periods if p["kind"] == "quarter"]; months = meta["summary"]["months"]
    nets = {p["id"]: _net_from_pairs(WEB_DATA / f"pairs_{p['id']}.json", subs) for p in periods}
    # the stricter-threshold network is published only as the 'robust' subset of validated links
    nets2 = {}
    for p in periods:
        raw = json.loads((WEB_DATA / f"pairs_{p['id']}.json").read_text(encoding="utf-8"))
        if raw.get("robust") is None:
            continue
        n2 = _net_from_pairs(WEB_DATA / f"pairs_{p['id']}.json", subs)
        S = len(subs); iu = np.triu_indices(S, 1)
        keep = np.zeros(len(iu[0]), bool); keep[raw["robust"]] = True
        n2.validated = np.zeros((S, S), bool); n2.validated[iu] = keep; n2.validated = n2.validated | n2.validated.T
        if raw.get("robust_affinity"):   # published only for robust pairs: scale observed so affinity matches the stricter network
            for k, a in zip(raw["robust"], raw["robust_affinity"]):
                i, j = iu[0][k], iu[1][k]
                n2.observed[i, j] = n2.observed[j, i] = a * n2.expected[i, j]
        nets2[p["id"]] = n2
    anchor = nets["all"]
    P_all = np.array([n["participation"] for n in nodes]); deg_all = np.array([n["degree"] for n in nodes])
    per_period = {}
    for p in periods:
        pq = {q: np.array([n["participation_by_quarter"].get(q, n["participation"]) for n in nodes]) for q in qids}
        per_period[p["id"]] = {"memb": np.array(json.loads((WEB_DATA / f"pairs_{p['id']}.json").read_text(encoding="utf-8"))["community"]),
                               "P": pq.get(p["id"], P_all)}
    gw = np.array([c == "gateway" for c in cats])
    stories = build_stories(subs, cats, memb, labels, nets, nets2, periods, qids, months, activity, anchor, P_all, deg_all, per_period, gw, meta["summary"])
    write_json(WEB_DATA / "stories.json", stories)
    log(f"stories.json rebuilt from artifacts: {[s['id'] for s in stories['stories']]}")
    facts_path = WEB_DATA / "pipeline.json"
    if facts_path.exists():   # keep the walkthrough's test inventory and artifact fingerprints in step with what was just written
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        facts["tests"], facts["test_modules"] = _tests_inventory()
        facts["artifacts"] = _artifact_inventory()
        write_json(facts_path, facts)
        log("pipeline.json: tests and artifact fingerprints refreshed")

if __name__ == "__main__":
    main()
