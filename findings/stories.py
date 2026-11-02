"""The three Findings stories, computed end to end from the local stores.

Each builder returns a JSON-ready dict with the evidence tables, the networks, the insights that fired and a
templated narrative (question, context, observation, explanation, conclusion, limitations) filled with computed
values only.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
from urllib.parse import quote
import pandas as pd

from . import candidates as CAND
from . import config as F
from . import events as EV
from . import insights as INS
from . import io as IO
from . import networks as N
from . import text as T

QUARTERS = {"2017Q4": ("2017-10-01", "2017-12-31"), "2018Q1": ("2018-01-01", "2018-03-31"), "2018Q2": ("2018-04-01", "2018-06-30"), "2018Q3": ("2018-07-01", "2018-09-30")}


# ---- shared: one reply network with everything the stories need ----------------------------------
def network_for(df: pd.DataFrame, sub: str, label: str, link: str, with_core: bool = True, groups: dict | None = None,
                text_terms: bool = False, significance: bool = False, deep: bool = False, seeds: int | None = None,
                summary_only: bool = False, period: str | None = None, tested: list | None = None) -> dict:
    """Full-graph structure + readable core export + per-community stats + flair-group tone, for one window.

    significance=True tests the top brokers (and the E-I index) against degree-preserving rewirings; deep=True adds the
    Infomap cross-check and the resolution scan (used for the focused community). With a core, the broker insight is judged
    here on the full network (period labels it) and handed back as out["bridge_insight"]; tested collects the permutation
    p-values for the story's one Benjamini-Hochberg correction."""
    e = N.reply_edges(df)
    g = N.build_graph(e)
    out = {"label": label, "subreddit": sub, "comments": int(len(df)), "reply_edges": int(e["w"].sum()) if len(e) else 0}
    if g.vcount() < 5:
        out.update({"summary": N.summary(g, {"membership": [0] * g.vcount(), "modularity": 0.0, "seed_ari": None}) if g.vcount() else None, "note": "too few reply ties"})
        return out
    light = g.vcount() > F.BIG_N
    comm = N.communities(g, seeds=seeds or (3 if g.vcount() > 50000 else 10 if light else F.LEIDEN_SEEDS))
    memb = comm["membership"]
    summ = N.summary(g, comm)
    summ["seed_ami"] = round(comm["seed_ami"], 3) if comm.get("seed_ami") is not None else None
    summ["null_modularity"] = N.null_modularity(g, n=(20 if deep else 2 if (light or summary_only) else 5))
    if summary_only:   # context communities: size and cohesion only
        out.update({"summary": summ, "link": link})
        return out
    met = N.node_metrics(g, memb, light=light)
    if deep:
        summ["infomap"] = N.infomap_check(g, memb)
        summ["resolution_scan"] = N.resolution_scan(g)
    alias = N.anonymise(g)
    # node sentiment = mean compound of the user's scored comments in this window
    sent = df.dropna(subset=["compound"]).groupby("author_h")["compound"].mean().to_dict() if "compound" in df else {}
    # communities on the full graph
    memb_arr = np.asarray(memb)
    inside = {}; outward = {}
    for ed in g.es:
        a, b = memb_arr[ed.source], memb_arr[ed.target]
        if a == b:
            inside[a] = inside.get(a, 0) + ed["w"]
        else:
            outward[a] = outward.get(a, 0) + ed["w"]; outward[b] = outward.get(b, 0) + ed["w"]
    sizes = pd.Series(memb).value_counts()
    comms = []
    users_by_c = {}
    for c, size in sizes.items():
        members = [g.vs[i]["name"] for i in np.where(memb_arr == c)[0]]
        users_by_c[c] = set(members)
        s_vals = [sent[u] for u in members if u in sent]
        gi, go = inside.get(c, 0), outward.get(c, 0)
        row = {"id": int(c), "size": int(size), "edges_inside": int(gi), "edges_outward": int(go),
               "ei_index": round((go - gi) / (go + gi), 3) if (go + gi) else None, "outward_share": round(go / (go + gi), 3) if (go + gi) else None,
               "mean_sentiment": round(float(np.mean(s_vals)), 3) if s_vals else None, "scored_members": len(s_vals)}
        if groups:
            gs = pd.Series([groups.get(u) for u in members]).dropna()
            row["group_mix"] = gs.value_counts(normalize=True).round(2).to_dict() if len(gs) else {}
        comms.append(row)
    if text_terms and "body" in df and len(comms):
        texts_by_user = df.dropna(subset=["body"]).groupby("author_h")["body"].apply(list)
        all_counts = T.term_counts([b for lst in texts_by_user for b in lst])
        for row in comms[:8]:
            if row["size"] < 8:
                continue
            mine = T.term_counts([b for u in users_by_c[row["id"]] if u in texts_by_user for b in texts_by_user[u]])
            rest = all_counts - mine
            row["top_terms"] = [d["term"] for d in T.log_odds(mine, rest, min_count=15, top=8)]
    out["summary"] = summ
    out["communities"] = comms[:20]
    # bridges on the full graph
    cand = met[(met["participation"] >= 0.6) & (met["communities_reached"] >= 3)].sort_values("betweenness", ascending=False).head(5)
    null = N.broker_significance(g, cand["name"].tolist(), n=F.REWIRINGS if deep else 50, light=light, met=met) if significance and len(cand) else {}
    out["bridges"] = [{"id": alias[r["name"]], "betweenness": round(float(r["betweenness"]), 4), "ev_brokerage": round(float(r["ev_brokerage"]), 3),
                       "participation": round(float(r["participation"]), 3),
                       "reached": int(r["communities_reached"]), "degree": int(r["degree"]), "community": int(r["community"]),
                       "sentiment": round(sent[r["name"]], 3) if r["name"] in sent else None, "group": groups.get(r["name"]) if groups else None,
                       "null": null.get(r["name"])}
                      for _, r in cand.iterrows()]
    # flair groups: structure and tone across the divide
    if groups:
        gvec = [groups.get(v["name"]) for v in g.vs]
        cov = float(np.mean([x is not None for x in gvec]))
        cross = {"coverage": round(cov, 3), "ei_index": N.ei_index(g, gvec), "groups": sorted({x for x in gvec if x})}
        if cross["ei_index"] is not None:
            cross["ei_index"] = round(cross["ei_index"], 3)
            if significance:
                cross["ei_null"] = N.ei_null(g, gvec, n=F.REWIRINGS if deep else 50)
        cross.update(_cross_group_tone(df, groups))
        out["groups"] = cross
    if with_core:
        core, cover = N.readable_core(g)
        # one partition everywhere: the core's metrics (participation, clusters reached) are measured against the FULL-graph
        # clusters that the drawing, the tables and the insights all use; no second Leiden run on the core
        full_c = {g.vs[i]["name"]: int(memb[i]) for i in range(g.vcount())}
        core_memb = [full_c[n] for n in core.vs["name"]]
        core_met = N.node_metrics(core, core_memb)
        xy = N.layout(core)
        extra = {"sentiment": {n: sent.get(n) for n in core.vs["name"]}, "group": {n: (groups or {}).get(n) for n in core.vs["name"]}}
        ex = N.export(core, core_memb, core_met, xy, extra)
        # re-alias with the full-graph aliases so bridges and nodes share ids
        core_alias = N.anonymise(core)
        rev = {v: k for k, v in core_alias.items()}
        for node in ex["nodes"]:
            node["id"] = alias[rev[node["id"]]]
        for edge in ex["edges"]:
            edge["s"] = alias[rev[edge["s"]]]; edge["t"] = alias[rev[edge["t"]]]
        out["core"] = {**cover, "modularity": round(core.modularity(core_memb, weights="w"), 3) if core.ecount() else 0.0, "nodes": ex["nodes"], "edges": ex["edges"]}
        # the broker insight is judged on the full network: the same rows as the Brokers table, never the drawn core
        rows = [{"id": alias[r["name"]], "betweenness": float(r["betweenness"]), "participation": float(r["participation"]),
                 "reached": int(r["communities_reached"]), "degree": int(r["degree"]), "null": null.get(r["name"])} for r in met.to_dict("records")]
        out["bridge_insight"] = INS.bridge(rows, summ, sub, period or label, link, tested=tested)
    out["link"] = link
    return out


def _pct(x: float) -> str:
    """Whole-number percent, except that a share just under 1 is not rounded up to 100%."""
    return f"{100 * x:.1f}%" if 0.995 <= x < 1 else f"{100 * x:.0f}%"


def _validation_note() -> str | None:
    """The measured VADER agreement from the labelled sample, quoted in every story's limitations when available."""
    import json
    p = F.CACHE / "sentiment_validation_result.json"
    if not p.exists():
        return None
    v = json.loads(p.read_text(encoding="utf-8"))
    return (f"On a labelled sample of {v['n']} comments VADER's label agreed with the annotators' for {100 * v['accuracy']:.0f}% (Cohen's κ {v['kappa']}"
            + (f"; {100 * v['accuracy_strict']:.0f}% at the stricter ±{v['strict_threshold']} threshold" if v.get("accuracy_strict") is not None else "")
            + "), mostly by calling neutral comments polar; absolute shares are VADER shares, and the claims rest on changes between windows.")


def _use_domain_neutralised(df: pd.DataFrame) -> pd.DataFrame:
    """Event stories score tone with topic words neutralised; the standard score travels along as compound_std."""
    if "compound_dn" in df.columns:
        df = df.copy()
        df["compound_std"] = df["compound"]
        df["compound"] = df["compound_dn"]
        df["label"] = np.where(df["compound"].isna(), None, T.label(df["compound"].fillna(0)))
        df["label_strict"] = np.where(df["compound"].isna(), None, T.label(df["compound"].fillna(0), F.STRICT_THRESH))
        df.loc[df["deleted"] == True, ["compound", "label", "label_strict", "compound_std"]] = [np.nan, None, None, np.nan]   # noqa: E712
    return df


def _metrics_with_cutoff(g, memb, cutoff):
    """node_metrics for large graphs: betweenness with a path cutoff, no closeness/eigenvector."""
    n = g.vcount()
    btw = np.array(g.betweenness(directed=False, cutoff=cutoff))
    btw = btw / ((n - 1) * (n - 2) / 2) if n > 2 else btw
    P = N.participation(g, memb)
    memb_a = np.asarray(memb)
    reached = [len({memb_a[u] for u in g.neighbors(v)}) for v in range(n)]
    return pd.DataFrame({"name": g.vs["name"], "community": memb, "degree": g.degree(), "strength": g.strength(weights="w"),
                         "betweenness": btw, "closeness": np.nan, "eigenvector": np.nan, "participation": P,
                         "communities_reached": reached, "constraint": np.nan, "in_giant": True})


def _cross_group_tone(df: pd.DataFrame, groups: dict, perms: int = F.PERMUTATIONS, seed: int = 5) -> dict:
    """Replies between and within flair groups: counts matrix and mean tone of the replying comment."""
    if "compound" not in df:
        return {}
    author_of = df.drop_duplicates("id").set_index("id")["author_h"]
    rep = df[df["parent_id"].str.startswith("t1_", na=False)].copy()
    rep["dst"] = rep["parent_id"].str[3:].map(author_of)
    rep = rep.dropna(subset=["dst", "author_h"])
    rep["g_src"] = rep["author_h"].map(groups); rep["g_dst"] = rep["dst"].map(groups)
    rep = rep.dropna(subset=["g_src", "g_dst"])
    if rep.empty:
        return {}
    mat = rep.groupby(["g_src", "g_dst"]).size().unstack(fill_value=0)
    scored = rep.dropna(subset=["compound"])
    between = (scored["g_src"] != scored["g_dst"]).to_numpy()
    comp = scored["compound"].to_numpy(dtype=float)
    out = {"matrix": {a: {b: int(mat.loc[a, b]) for b in mat.columns} for a in mat.index},
           "between_share": round(float((rep["g_src"] != rep["g_dst"]).mean()), 3)}
    if between.sum() >= 30 and (~between).sum() >= 30:
        diff = comp[between].mean() - comp[~between].mean()
        rng = np.random.default_rng(seed); cnt = 0; lab = between.copy()
        for _ in range(perms):
            rng.shuffle(lab)
            if abs(comp[lab].mean() - comp[~lab].mean()) >= abs(diff):
                cnt += 1
        out.update({"within": {"n": int((~between).sum()), "mean_compound": round(float(comp[~between].mean()), 4)},
                    "between": {"n": int(between.sum()), "mean_compound": round(float(comp[between].mean()), 4)},
                    "diff": round(float(diff), 4), "p_perm": round((cnt + 1) / (perms + 1), 4)})
        # pairwise tone matrix (mean compound of replies from row group to column group)
        tone = scored.groupby(["g_src", "g_dst"])["compound"].mean().unstack()
        out["tone_matrix"] = {a: {b: (None if pd.isna(tone.loc[a, b]) else round(float(tone.loc[a, b]), 3)) for b in tone.columns} for a in tone.index}
    return out


def _user_level(df_a: pd.DataFrame, df_b: pd.DataFrame) -> dict:
    ua = df_a.dropna(subset=["compound"]).groupby("author_h")["compound"].mean().to_numpy()
    ub = df_b.dropna(subset=["compound"]).groupby("author_h")["compound"].mean().to_numpy()
    return EV.compare(ua, ub, permutations=500)


def _themes(df: pd.DataFrame, windows: dict[str, tuple[str, str]], sub: str, top: int = 15) -> dict:
    """Words that mark each window against the others (document-frequency log-odds)."""
    parts = EV.window_slices(df[(df["subreddit"] == sub) & df["body"].notna()], windows)
    counts = {k: T.term_counts(v["body"]) for k, v in parts.items()}
    out = {}
    for k, c in counts.items():
        rest = sum((v for j, v in counts.items() if j != k), start=type(c)())
        out[k] = T.log_odds(c, rest, min_count=30, top=top)
    return out


# ---- story 2: Infinity War ------------------------------------------------------------------------
def build_infinity_war(raw_text=None, cache=None, clean=None) -> dict:
    ev = F.EVENTS["infinity_war"]
    W = ev["windows"]; start, end = W["before"][0], W["after"][1]
    subs = ev["subs"]
    tested = []   # every permutation p-value a detector considers, for one Benjamini-Hochberg correction per story
    df = EV.scored_comments(subs, start, end, raw_text=raw_text, cache=cache, with_text=True)
    df = _use_domain_neutralised(df)
    hist = IO.comments(subs, "2017-10-01", end, columns=["author_h", "subreddit", "created_utc"], raw_text=raw_text)
    hist["day"] = pd.to_datetime(hist["created_utc"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    daily = EV.daily_series(df)
    days = EV.all_days(start, end)
    daily_full = (daily.set_index(["subreddit", "day"]).reindex(pd.MultiIndex.from_product([subs, days], names=["subreddit", "day"]))
                  .reset_index().fillna({"comments": 0, "commenters": 0, "replies": 0, "scored": 0}))
    wsum = EV.window_summary(df, W, hist=hist, lookback_months=F.NEWCOMER_LOOKBACK["infinity_war"])   # newcomers against a fixed lookback
    comparisons = {}
    for sub in subs:
        d = df[df["subreddit"] == sub]
        sl = EV.window_slices(d, W)
        comparisons[sub] = {}
        for a, b in (("before", "release"), ("release", "after"), ("before", "after")):
            comparisons[sub][f"{a}_vs_{b}"] = {"comment_level": EV.compare(sl[a]["compound"].to_numpy(dtype=float), sl[b]["compound"].to_numpy(dtype=float)),
                                               "user_level": _user_level(sl[a], sl[b]),
                                               "neg_share": EV.compare_shares(sl[a]["label"].tolist(), sl[b]["label"].tolist(), "neg"),
                                               "pos_share": EV.compare_shares(sl[a]["label"].tolist(), sl[b]["label"].tolist(), "pos"),
                                               "neg_share_strict": EV.compare_shares(sl[a]["label_strict"].tolist(), sl[b]["label_strict"].tolist(), "neg", permutations=300),
                                               "standard_vader": EV.compare(sl[a]["compound_std"].to_numpy(dtype=float), sl[b]["compound_std"].to_numpy(dtype=float), permutations=300)}
    # participation across the whole frame: comments per day in each window, 170 subreddits
    part = {}
    for name, (a, b) in W.items():
        t = IO.frame_window_totals(a, b, clean=clean)
        ndays = (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days + 1
        part[name] = dict(zip(t["subreddit"], (t["comments"] / ndays).round(1)))
    frame_rows = []
    for s in part["before"]:
        b0, r0, a0 = part["before"].get(s, 0), part["release"].get(s, 0), part["after"].get(s, 0)
        frame_rows.append({"subreddit": s, "before_per_day": b0, "release_per_day": r0, "after_per_day": a0,
                           "release_ratio": round(r0 / b0, 2) if b0 else None, "release_extra_per_day": round(r0 - b0, 1)})
    frame_rows.sort(key=lambda r: -r["release_extra_per_day"])
    # level change at the release (segmented regression) for the lead community, against the same model on all 170 communities
    fd = IO.frame_daily_all(start, end, clean=clean)
    piv = fd.pivot(index="day", columns="subreddit", values="comments").reindex(days).fillna(0)
    its_all = {s: EV.its_level_change(piv[s].to_numpy(), days, ev["anchor_date"]) for s in piv.columns}
    coefs = sorted(v["level_change_log"] for v in its_all.values() if v)
    lead = subs[0]
    its = {sub: its_all.get(sub, {}) for sub in subs}
    for sub in subs:
        if its[sub]:
            its[sub]["percentile_among_frame"] = round(100 * sum(1 for c in coefs if c <= its[sub]["level_change_log"]) / len(coefs), 1)
            its[sub]["frame_median_pct"] = round(float(np.expm1(np.median(coefs))), 4)
    gap_days = EV.integrity_screen(piv.drop(columns=[s for s in subs if s in piv.columns]).sum(axis=1))
    # context structure-only subreddits (r/movies, r/comics) daily volume from the text store
    ctx = IO.daily_counts(ev["context_subs"], start, end, raw_text=raw_text)
    themes = {sub: _themes(df, W, sub) for sub in subs}
    nets = {}
    for sub in subs + ev["context_subs"]:
        nets[sub] = {}
        src = df if sub in subs else IO.comments([sub], start, end, raw_text=raw_text).assign(day=lambda x: pd.to_datetime(x["created_utc"], unit="s", utc=True).dt.strftime("%Y-%m-%d"))
        for name, (a, b) in W.items():
            d = src[(src["subreddit"] == sub) & (src["day"] >= a) & (src["day"] <= b)]
            nets[sub][name] = network_for(d, sub, name, f"#/findings/infinity-war?window={name}&sub={sub}", with_core=(sub in subs), text_terms=(sub in subs), significance=(sub == subs[0]), summary_only=(sub not in subs), period=f"{name} window", tested=tested)
    # change points on r/marvelstudios daily comments and daily mean compound
    dl = daily_full[daily_full["subreddit"] == lead].sort_values("day")
    cps = {"comments": [dl["day"].iloc[k] for k in EV.change_points(dl["comments"].to_numpy(dtype=float))],
           "mean_compound": [dl["day"].iloc[k] for k in EV.change_points(dl["mean_compound"].fillna(dl["mean_compound"].mean()).to_numpy(dtype=float))]}
    # insights
    ins = []
    for sub in subs:
        rows = daily_full[daily_full["subreddit"] == sub].to_dict("records")
        x = INS.surge(rows, W["before"], W["release"], sub, f"#/findings/infinity-war?sub={sub}", ev["anchor_label"])
        if x: ins.append(x)
        for key, (a, b) in {"before_vs_release": ("before", "release"), "release_vs_after": ("release", "after"), "before_vs_after": ("before", "after")}.items():
            c = comparisons[sub][key]
            x = INS.shift(c["comment_level"], c["user_level"], sub, a, b, f"{W[a][0]} – {W[b][1]}", f"#/findings/infinity-war?sub={sub}&window={b}", shares=c["neg_share"], tested=tested)
            if x: ins.append(x)
        for name in W:
            net = nets[sub][name]
            if net.get("core"):
                x = net.pop("bridge_insight", None)   # judged on the full network inside network_for
                if x: ins.append(x)
                x = INS.community_gap(net["core"]["nodes"], sub, f"{name} window", net["link"], tested=tested)
                if x: ins.append(x)
        series = [{"label": name, **nets[sub][name]["summary"]} for name in W if nets[sub][name].get("summary")]
        x = INS.fragmentation(series, sub, f"#/findings/infinity-war?sub={sub}")
        if x: ins.append(x)
    story = {"id": "infinity_war", "title": ev["title"], "anchor": {"date": ev["anchor_date"], "label": ev["anchor_label"]},
             "windows": {k: {"start": a, "end": b} for k, (a, b) in W.items()}, "subreddits": subs, "context_subreddits": ev["context_subs"],
             "daily": daily_full.to_dict("records"), "context_daily": ctx.to_dict("records"), "window_summary": wsum, "comparisons": comparisons,
             "frame_participation": frame_rows[:25], "its": its, "gap_days": gap_days, "themes": themes, "networks": nets, "change_points": cps,
             "sentiment_measure": {"primary": "VADER with topic words neutralised (compound_dn)", "neutralised_words": T.neutralised_words("marvel"), "secondary": "standard VADER (compound_std)"},
             "insights": INS.finalize(ins, tested)}
    story["narrative"] = _narrative_infinity_war(story)
    return story


def _narrative_infinity_war(s: dict) -> dict:
    lead = s["subreddits"][0]
    ws = {(r["window"], r["subreddit"]): r for r in s["window_summary"]}
    b, r, a = ws.get(("before", lead)), ws.get(("release", lead)), ws.get(("after", lead))
    cmp_br = s["comparisons"][lead]["before_vs_release"]["comment_level"]; cmp_ra = s["comparisons"][lead]["release_vs_after"]["comment_level"]
    top_frame = [x for x in s["frame_participation"] if x["subreddit"] not in s["subreddits"]][:5]
    nets = s["networks"][lead]
    nb, nr, na = (nets[k].get("summary") or {} for k in ("before", "release", "after"))
    surge = next((i for i in s["insights"] if i["kind"] == "volume_surge" and i["scope"] == f"r/{lead}"), None)
    shifts = [i for i in s["insights"] if i["kind"] == "sentiment_shift"]
    struct = [i for i in s["insights"] if i["kind"] == "structure_change"]
    obs = []
    if b and r:
        obs.append(f"r/{lead} went from {b['comments_per_day']:,.0f} comments a day in the seven weeks before the release to {r['comments_per_day']:,.0f} in the three-week release window"
                   f" ({r['comments_per_day'] / b['comments_per_day']:.1f}×), with {r['commenters']:,} distinct commenters of whom {100 * (r['newcomer_share'] or 0):.0f}% had not commented there in the previous {F.NEWCOMER_LOOKBACK['infinity_war']} months.")
    own = [x for x in s["frame_participation"] if x["subreddit"] in s["subreddits"]]
    lead_frame = next((x for x in own if x["subreddit"] == lead), None)
    if top_frame:
        cover = (f" (its count for r/{lead} in the release window is {100 * lead_frame['release_per_day'] / r['comments_per_day']:.0f}% of the text store's used above)"
                 if (lead_frame and r and r.get("comments_per_day")) else "")
        obs.append(f"In the Atlas store of 170 communities, which keeps accounts with at least five comments in a quarter{cover}, the largest absolute increases in comments per day "
                   "in the release window outside the Marvel communities came from " + ", ".join(f"r/{x['subreddit']} (+{x['release_extra_per_day']:,.0f}/day, {x['release_ratio']}×)" for x in top_frame[:4])
                   + ("; relative to their own baselines the Marvel communities lead (" + ", ".join(f"r/{x['subreddit']} {x['release_ratio']}×" for x in own) + ")." if own else "."))
    if b and r and a:
        obs.append(f"Shares of positive / neutral / negative comments in r/{lead}: {100 * b['pos_share']:.0f}/{100 * b['neu_share']:.0f}/{100 * b['neg_share']:.0f}% before, "
                   f"{100 * r['pos_share']:.0f}/{100 * r['neu_share']:.0f}/{100 * r['neg_share']:.0f}% in the release window, {100 * a['pos_share']:.0f}/{100 * a['neu_share']:.0f}/{100 * a['neg_share']:.0f}% after; "
                   f"mean compound {b['mean_compound']:+.3f} → {r['mean_compound']:+.3f} → {a['mean_compound']:+.3f} (before→release d = {cmp_br.get('cohen_d')}, release→after d = {cmp_ra.get('cohen_d')}).")
    if nb and nr and na:
        obs.append(f"The reply network of r/{lead} had {nb['nodes']:,} active repliers before, {nr['nodes']:,} in the release window and {na['nodes']:,} after; "
                   f"modularity {nb['modularity']:.2f} → {nr['modularity']:.2f} → {na['modularity']:.2f}, largest component {_pct(nb['largest_component_share'])} → {_pct(nr['largest_component_share'])} → {_pct(na['largest_component_share'])}.")
    expl = ("A release crowd is mostly new or occasional commenters arriving in many parallel threads, which raises volume far faster than it changes the tone of the community; "
            "the measurable sentiment changes are small in standardised terms even where they are statistically clear, and they describe language, not approval of the film.")
    concl = (f"Reddit's reaction to Infinity War is visible as a {surge['evidence']['robust_z']:.0f}-sigma surge in r/{lead} on {surge['evidence']['peak_day']}" if surge else f"Reddit's reaction to Infinity War is visible as a surge in r/{lead}") + \
            (f", with {len(shifts)} measurable tone shift(s) between windows" if shifts else ", without a tone shift that passes our thresholds") + \
            (("; the shape of conversation (who replied to whom) changed as well: " + struct[0]["title"] + ".") if struct else
             "; nor does a change in the shape of conversation (who replied to whom) pass the thresholds: the release crowd raised volume without moving tone or structure beyond them.")
    return {"question": "Did Reddit's conversation about Avengers: Infinity War change in volume, tone and structure around the film's release, and where did the reaction come from?",
            "context": "The film's US release (27 April 2018) sits in the middle of our window, so the same communities can be observed for seven weeks before and after a three-week release window.",
            "observation": " ".join(obs), "explanation": expl, "conclusion": concl,
            "limitations": [x for x in [_validation_note()] if x] + ["Comment counts and sentiment cover r/marvelstudios and r/Marvel; other communities contribute volume only (no text was fetched for them).",
                            "VADER measures the polarity of language, not opinions about the film; sarcasm and fandom slang are scored imperfectly (see the validation sample).",
                            "Windows are calendar-defined; a surge around a dated event is a temporal association, not proof of cause.",
                            "Reply networks link users through parent comments only; replies to posts and to deleted comments create no edge."]}


# ---- story 3: Bitcoin ---------------------------------------------------------------------------------
def build_bitcoin(raw_text=None, cache=None) -> dict:
    ev = F.EVENTS["bitcoin"]
    subs = ev["subs"]
    start, end = "2017-10-01", "2018-09-30"
    tested = []   # every permutation p-value a detector considers, for one Benjamini-Hochberg correction per story
    price = EV.price_series()
    ext = EV.price_extrema(price, min_swing=0.4)   # 40% swings: the Christmas dip and smaller wiggles stay inside larger phases
    phases = EV.price_phases(ext)
    for k in range(1, len(phases)):   # a turning-point day closes the phase it ends; the next phase starts the day after (no day counted twice)
        phases[k]["start"] = (pd.Timestamp(phases[k - 1]["end"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    windows = {f"P{k + 1} {p['label']}": (p["start"], p["end"]) for k, p in enumerate(phases)}
    # month by month to bound memory; daily series + window summaries + networks per month
    daily_parts, month_rows, nets = [], [], {s: {} for s in subs[:2]}
    active_by_month = {}   # (subreddit, month) -> users active that month, for the fixed-lookback newcomer share
    per_sub_phase = {s: {k: [] for k in windows} for s in subs}        # comment-level compounds per phase
    per_sub_phase_lab = {s: {k: [] for k in windows} for s in subs}    # comment-level labels per phase
    per_sub_phase_strict = {s: {k: [] for k in windows} for s in subs}
    per_sub_phase_std = {s: {k: [] for k in windows} for s in subs}    # standard-VADER compounds per phase
    per_sub_phase_user = {s: {k: {} for k in windows} for s in subs}   # user -> list of compounds per phase
    themes_counts = {s: {k: None for k in windows} for s in subs[:2]}
    for m in F.MONTHS:
        ms, me = f"{m}-01", (pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
        df = _use_domain_neutralised(EV.scored_comments(subs, ms, me, raw_text=raw_text, cache=cache, with_text=True))
        if df.empty:
            continue
        for s, d in df.dropna(subset=["author_h"]).groupby("subreddit"):
            active_by_month[(s, m)] = set(d["author_h"].unique())   # months run in order, so the lookback months are already here
        daily_parts.append(EV.daily_series(df))
        for sub, d in df.groupby("subreddit"):
            sc = d.dropna(subset=["compound"])
            lab = sc["label"].value_counts(normalize=True)
            authors = d["author_h"].dropna().unique()
            lb = EV.lookback_start(ms, F.NEWCOMER_LOOKBACK["bitcoin"])   # fixed lookback; undefined where it would reach before the store
            before = set().union(*(active_by_month.get((sub, pm), set()) for pm in F.MONTHS if lb <= f"{pm}-01" < ms)) if lb else None
            new = EV.newcomer_share(authors, before)
            month_rows.append({"month": m, "subreddit": sub, "comments": int(len(d)), "commenters": int(len(authors)), "newcomer_share": new,
                               "scored": int(len(sc)), "mean_compound": round(float(sc["compound"].mean()), 4) if len(sc) else None,
                               "pos_share": round(float(lab.get("pos", 0)), 4), "neu_share": round(float(lab.get("neu", 0)), 4), "neg_share": round(float(lab.get("neg", 0)), 4)})
            for k, (a, b) in windows.items():
                part = sc[(sc["day"] >= a) & (sc["day"] <= b)]
                if len(part):
                    per_sub_phase[sub][k].append(part["compound"].to_numpy(dtype=float))
                    per_sub_phase_lab[sub][k].append(part["label"].to_numpy())
                    per_sub_phase_strict[sub][k].append(part["label_strict"].to_numpy())
                    per_sub_phase_std[sub][k].append(part["compound_std"].to_numpy(dtype=float))
                    for u, v in part.groupby("author_h")["compound"].mean().items():
                        per_sub_phase_user[sub][k].setdefault(u, []).append(v)
                    if sub in themes_counts:
                        c = T.term_counts(part["body"].dropna()) if "body" in part else None
                        if c is not None:
                            themes_counts[sub][k] = c if themes_counts[sub][k] is None else themes_counts[sub][k] + c
        for sub in subs[:2]:
            d = df[df["subreddit"] == sub]
            key_months = {"2017-10", "2017-12", "2018-02", "2018-05", "2018-09"}
            nets[sub][m] = network_for(d, sub, m, f"#/findings/bitcoin?month={m}&sub={sub}", with_core=(m in key_months), text_terms=(m in key_months), seeds=(None if m in key_months else 5), significance=(m in key_months), period=m, tested=tested)
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    # phase comparisons per subreddit: consecutive phases, comment- and user-level
    comparisons = {}
    keys = list(windows)
    for sub in subs:
        comparisons[sub] = {}
        for a, b in zip(keys, keys[1:]):
            va = np.concatenate(per_sub_phase[sub][a]) if per_sub_phase[sub][a] else np.array([])
            vb = np.concatenate(per_sub_phase[sub][b]) if per_sub_phase[sub][b] else np.array([])
            ua = np.array([np.mean(v) for v in per_sub_phase_user[sub][a].values()]); ub = np.array([np.mean(v) for v in per_sub_phase_user[sub][b].values()])
            la = np.concatenate(per_sub_phase_lab[sub][a]) if per_sub_phase_lab[sub][a] else np.array([]); lb = np.concatenate(per_sub_phase_lab[sub][b]) if per_sub_phase_lab[sub][b] else np.array([])
            sa = np.concatenate(per_sub_phase_std[sub][a]) if per_sub_phase_std[sub][a] else np.array([]); sb = np.concatenate(per_sub_phase_std[sub][b]) if per_sub_phase_std[sub][b] else np.array([])
            sta = np.concatenate(per_sub_phase_strict[sub][a]) if per_sub_phase_strict[sub][a] else np.array([]); stb = np.concatenate(per_sub_phase_strict[sub][b]) if per_sub_phase_strict[sub][b] else np.array([])
            comparisons[sub][f"{a} → {b}"] = {"comment_level": EV.compare(va, vb), "user_level": EV.compare(ua, ub, permutations=500),
                                              "neg_share": EV.compare_shares(la.tolist(), lb.tolist(), "neg"), "pos_share": EV.compare_shares(la.tolist(), lb.tolist(), "pos"),
                                              "neg_share_strict": EV.compare_shares(sta.tolist(), stb.tolist(), "neg", permutations=300),
                                              "standard_vader": EV.compare(sa, sb, permutations=300)}
    phase_rows = []
    for sub in subs:
        for k in keys:
            v = np.concatenate(per_sub_phase[sub][k]) if per_sub_phase[sub][k] else np.array([])
            if len(v):
                lab = pd.Series(T.label(v)).value_counts(normalize=True)
                phase_rows.append({"phase": k, "subreddit": sub, "start": windows[k][0], "end": windows[k][1], "scored": int(len(v)), "mean_compound": round(float(v.mean()), 4),
                                   "pos_share": round(float(lab.get("pos", 0)), 4), "neu_share": round(float(lab.get("neu", 0)), 4), "neg_share": round(float(lab.get("neg", 0)), 4),
                                   "users": len(per_sub_phase_user[sub][k])})
    themes = {}
    for sub, cs in themes_counts.items():
        themes[sub] = {}
        for k, c in cs.items():
            if c is None:
                continue
            rest = sum((v for j, v in cs.items() if j != k and v is not None), start=type(c)())
            themes[sub][k] = T.log_odds(c, rest, min_count=40, top=15)
    # price alignment: lagged rank correlations of daily log return with daily mean compound and daily volume (r/bitcoin, r/cryptocurrency)
    corr = {}
    if len(daily):
        pr = price.copy(); pr["ret"] = np.log(pr["price"]).diff()
        for sub in subs[:2]:
            d = daily[daily["subreddit"] == sub].merge(pr, on="day", how="inner").sort_values("day")
            corr[sub] = {"return_vs_mean_compound": EV.lagged_rank_correlation(d["ret"], d["mean_compound"]),
                         "return_vs_comments": EV.lagged_rank_correlation(d["ret"], np.log1p(d["comments"]).diff()),
                         "price_vs_comments_level": EV.lagged_rank_correlation(d["price"], d["comments"], lags=[0])}
    # insights
    ins = []
    for sub in subs:   # text detectors (volume surge, phase-to-phase tone shifts) on every community with text
        rows = daily[daily["subreddit"] == sub].to_dict("records") if len(daily) else []
        peak_month = ext[1]["day"][:7] if len(ext) > 1 else "2017-12"
        x = INS.surge(rows, ("2017-10-01", "2017-11-15"), (f"{peak_month}-01", (pd.Timestamp(peak_month + "-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")), sub, f"#/findings/bitcoin?sub={sub}&month={peak_month}", ev["anchor_label"])
        if x: ins.append(x)
        for key, c in comparisons[sub].items():
            a, b = key.split(" → ")
            x = INS.shift(c["comment_level"], c["user_level"], sub, a, b, f"{windows[a][0]} – {windows[b][1]}", f"#/findings/bitcoin?sub={sub}&phase={quote(b)}", shares=c["neg_share"], tested=tested)
            if x: ins.append(x)
    for sub in subs[:2]:   # structure detectors where the monthly networks are built
        series = [{"label": m, **nets[sub][m]["summary"]} for m in F.MONTHS if nets[sub].get(m, {}).get("summary")]
        x = INS.fragmentation(series, sub, f"#/findings/bitcoin?sub={sub}")
        if x: ins.append(x)
        for m, net in nets[sub].items():
            if net.get("core"):
                x = net.pop("bridge_insight", None);  ins.append(x) if x else None
                x = INS.community_gap(net["core"]["nodes"], sub, m, net["link"], tested=tested);  ins.append(x) if x else None
    story = {"id": "bitcoin", "title": ev["title"], "anchor": {"date": ext[1]["day"] if len(ext) > 1 else ev["anchor_date"], "label": ev["anchor_label"]},
             "price": price.round(2).to_dict("records"), "price_extrema": ext, "phases": phases, "windows": {k: {"start": a, "end": b} for k, (a, b) in windows.items()},
             "subreddits": subs, "context_subreddits": ev["context_subs"], "daily": daily.to_dict("records") if len(daily) else [], "monthly": month_rows,
             "phase_summary": phase_rows, "comparisons": comparisons, "themes": themes, "correlations": corr,
             "networks": {s: {m: v for m, v in d.items()} for s, d in nets.items()},
             "sentiment_measure": {"primary": "VADER with topic words neutralised (compound_dn)", "neutralised_words": T.neutralised_words("crypto"), "secondary": "standard VADER (compound_std)"},
             "insights": INS.finalize(ins, tested)}
    story["narrative"] = _narrative_bitcoin(story)
    return story


def _narrative_bitcoin(s: dict) -> dict:
    subs = s["subreddits"]; lead = subs[0]
    mr = {(r["month"], r["subreddit"]): r for r in s["monthly"]}
    peak_m = s["anchor"]["date"][:7]
    first, last = F.MONTHS[0], F.MONTHS[-1]
    obs = []
    for sub in subs[:2]:
        a, p, z = mr.get((first, sub)), mr.get((peak_m, sub)), mr.get((last, sub))
        if a and p and z:
            obs.append(f"r/{sub}: {a['comments']:,} comments in {first}, {p['comments']:,} in the peak month ({peak_m}), {z['comments']:,} in {last}; "
                       f"mean compound {a['mean_compound']:+.3f} → {p['mean_compound']:+.3f} → {z['mean_compound']:+.3f}; negative share {100 * a['neg_share']:.0f}% → {100 * p['neg_share']:.0f}% → {100 * z['neg_share']:.0f}%; "
                       f"newcomers (not active there in the previous {F.NEWCOMER_LOOKBACK['bitcoin']} months) {100 * (p['newcomer_share'] or 0):.0f}% of commenters at the peak vs {100 * (z['newcomer_share'] or 0):.0f}% at the end.")
    ph = s["phases"]
    if ph:
        obs.append("Price phases from the series: " + "; ".join(f"{x['label']} {x['start']}→{x['end']} ({100 * x['change']:+.0f}%)" for x in ph) + ".")
    shifts = [i for i in s["insights"] if i["kind"] == "sentiment_shift"]
    corr = s["correlations"].get(lead, {}).get("return_vs_mean_compound", [])
    best = max(corr, key=lambda c: abs(c["rho"])) if corr else None
    lp, lz = mr.get((peak_m, lead)), mr.get((last, lead))
    lost = (1 - lz["commenters"] / lp["commenters"]) if (lp and lz and lp.get("commenters")) else None
    nz, npk = (lz or {}).get("newcomer_share"), (lp or {}).get("newcomer_share")
    presence = (f"r/{lead} had {100 * lost:.0f}% fewer commenters in {last} than in the peak month" if lost is not None else f"r/{lead} lost commenters after the peak") + \
               (f", and the share of newcomers (against a fixed {F.NEWCOMER_LOOKBACK['bitcoin']}-month lookback) was {'lower' if nz < npk else 'no lower'} at the end than at the peak ({100 * npk:.0f}% → {100 * nz:.0f}%)" if (nz is not None and npk is not None) else "")
    n_pairs = sum(len(v) for v in s.get("comparisons", {}).values())
    expl = (f"The decline shows first in volume and in who is present: {presence}. "
            "Tone moves less than volume; where it moves, it is measured as small standardised shifts in the polarity of language, and daily price returns correlate only weakly with daily tone"
            + (f" (strongest Spearman ρ = {best['rho']} at lag {best['lag']} days)" if best else "") + ".")
    where = ", ".join(sorted({i["scope"] for i in shifts}))
    concl = (f"Between the {peak_m} peak and {last}, r/{lead} " + ("lost most of its commenters" if (lost is not None and lost >= 0.5) else f"lost {100 * (lost or 0):.0f}% of its commenters") +
             (f"; {len(shifts)} of {n_pairs} phase-to-phase tone comparisons across the {len(subs)} communities pass the thresholds ({where})" if shifts else f"; none of the {n_pairs} phase-to-phase tone comparisons across the {len(subs)} communities passes the thresholds") +
             ". Discourse followed the market in presence more than in polarity.")
    return {"question": "How did Reddit's cryptocurrency communities change, in volume, tone, themes and structure, through the 2018 decline from the December 2017 peak?",
            "context": "Our window starts two months before the peak and ends nine months after it, so the same communities can be followed through the first crash, the rebounds and the summer lows; the price series is reference context, not a target.",
            "observation": " ".join(obs), "explanation": expl, "conclusion": concl,
            "limitations": [x for x in [_validation_note()] if x] + ["Price and sentiment are aligned by UTC day; correlations at any lag are associations, not causal effects in either direction.",
                            "VADER was not built for financial slang ('moon', 'hodl', 'rekt', 'dip'); scores describe language polarity, not expectations or positions.",
                            "The window begins in October 2017, so the run-up is only partly observed.",
                            f"Newcomer shares use a fixed {F.NEWCOMER_LOOKBACK['bitcoin']}-month lookback, so the first {F.NEWCOMER_LOOKBACK['bitcoin']} months have none and a user absent for that long counts as new on return.",
                            "Reply networks are built from parent comments only; monthly networks differ in size, which affects density and modularity."]}


# ---- story 1: inside a community ------------------------------------------------------------------
def build_community(raw_text=None, cache=None, window=("2018-04-01", "2018-06-30"), chosen: str | None = None) -> dict:
    matrix = CAND.score(CAND.candidate_matrix(window[0], window[1], raw_text=raw_text))
    chosen = chosen or str(matrix.iloc[0]["subreddit"])
    alternative = str(matrix[matrix["subreddit"] != chosen].iloc[0]["subreddit"])
    start, end = "2017-10-01", "2018-09-30"
    has_text = chosen in F.TEXT_SUBS
    tested = []   # every permutation p-value a detector considers, for one Benjamini-Hochberg correction per story
    df = EV.scored_comments([chosen], start, end, raw_text=raw_text, cache=cache, with_text=True) if has_text else IO.comments([chosen], start, end, raw_text=raw_text).assign(day=lambda x: pd.to_datetime(x["created_utc"], unit="s", utc=True).dt.strftime("%Y-%m-%d"))
    groups = N.user_groups(df, chosen)
    year = network_for(df, chosen, "Oct 2017 – Sep 2018", "#/findings/community", with_core=True, groups=groups or None, text_terms=has_text, significance=True, deep=True, period="Oct 2017 – Sep 2018", tested=tested)
    quarters = []
    prev = None
    for q, (a, b) in QUARTERS.items():
        d = df[(df["day"] >= a) & (df["day"] <= b)]
        net = network_for(d, chosen, q, f"#/findings/community?quarter={q}", with_core=False, groups=groups or None)
        quarters.append(net)
    # membership persistence between consecutive quarters (ARI on users present in both)
    persistence = []
    qnets = {}
    for q, (a, b) in QUARTERS.items():
        d = df[(df["day"] >= a) & (df["day"] <= b)]
        g = N.build_graph(N.reply_edges(d))
        if g.vcount():
            qnets[q] = dict(zip(g.vs["name"], N.communities(g)["membership"]))
    from sklearn.metrics import adjusted_rand_score
    qs = list(qnets)
    for a, b in zip(qs, qs[1:]):
        common = sorted(set(qnets[a]) & set(qnets[b]))
        if len(common) >= 20:
            persistence.append({"from": a, "to": b, "users_in_both": len(common), "ari": round(adjusted_rand_score([qnets[a][u] for u in common], [qnets[b][u] for u in common]), 3)})
    ins = []
    if year.get("core"):
        x = year.pop("bridge_insight", None); ins.append(x) if x else None
        x = INS.community_gap(year["core"]["nodes"], chosen, "Oct 2017 – Sep 2018", "#/findings/community", tested=tested); ins.append(x) if x else None
    if year.get("groups"):
        x = INS.camp_mixing(year["groups"], chosen, "Oct 2017 – Sep 2018", "#/findings/community?view=groups", tested=tested); ins.append(x) if x else None
        x = INS.group_hostility(year["groups"], chosen, "Oct 2017 – Sep 2018", "#/findings/community?view=groups", tested=tested); ins.append(x) if x else None
    x = INS.isolation(year.get("communities", []), chosen, "Oct 2017 – Sep 2018", "#/findings/community"); ins.append(x) if x else None
    x = INS.fragmentation([{"label": n["label"], **n["summary"]} for n in quarters if n.get("summary")], chosen, "#/findings/community?view=quarters"); ins.append(x) if x else None
    story = {"id": "community", "title": f"Inside r/{chosen}", "subreddit": chosen, "alternative": alternative, "selection_window": {"start": window[0], "end": window[1]},
             "matrix": matrix.replace({np.nan: None}).to_dict("records"), "year": year, "quarters": quarters, "persistence": persistence,
             "insights": sorted(INS.finalize(ins, tested), key=lambda i: {"high": 0, "medium": 1, "descriptive": 2}.get(i["confidence"], 3)),
             "flair_rules": {k: [{"group": g, "pattern": p} for g, p in v] for k, v in N.FLAIR_RULES.items() if k == chosen}}
    story["narrative"] = _narrative_community(story)
    return story


def _narrative_community(s: dict) -> dict:
    sub = s["subreddit"]; y = s["year"]; sm = y.get("summary") or {}
    row = next((r for r in s["matrix"] if r["subreddit"] == sub), {})
    obs = []
    if sm:
        nl = sm.get("null_modularity") or {}
        weak = (nl.get("max") is not None and sm.get("modularity_unweighted", 0) <= nl["max"]) or (sm.get("infomap", {}).get("largest_module_share", 0) >= 0.8)
        per = s.get("persistence") or []
        obs.append(f"Over the year, {sm['nodes']:,} users replied to each other in r/{sub} through {sm['edges']:,} reply ties (carrying {sm.get('tie_replies') or y.get('reply_edges', 0):,} replies); "
                   f"{_pct(sm['largest_component_share'])} of them sit in one connected component and {100 * sm['reciprocity']:.0f}% of reply pairs are reciprocated. "
                   f"Leiden splits it into {sm['communities']} clusters (weighted modularity {sm['modularity']:.2f}; unweighted {sm.get('modularity_unweighted', 0):.2f} against {nl.get('mean', 0):.2f} for degree-preserving rewirings"
                   + (f"; Infomap puts {100 * sm['infomap']['largest_module_share']:.0f}% of users in one module" if sm.get("infomap") else "") + ")"
                   + (f", and returning users do not keep their cluster from quarter to quarter (ARI {', '.join(str(p['ari']) for p in per)})" if per else "") + ". "
                   + ("The cluster structure is weak: r/" + sub + " behaves as one conversation, not as a set of separate rooms." if weak else "The clusters are stronger than chance and persist."))
    g = y.get("groups")
    if g and g.get("between"):
        nl = g.get("ei_null") or {}
        obs.append(f"Self-declared camps ({', '.join(g['groups'])}) cover {100 * g['coverage']:.0f}% of repliers; {100 * g['between_share']:.0f}% of their replies cross camp lines (E–I index {g['ei_index']:+.2f}"
                   + (f" against {nl['null_mean']:+.2f} for rewired graphs, z = {nl['z']}" if nl else "") + "), "
                   f"and replies across the divide average {g['between']['mean_compound']:+.3f} on the compound scale against {g['within']['mean_compound']:+.3f} within a camp (permutation p = {g['p_perm']}): "
                   + ("cross-camp replies are no harsher than replies within a camp." if g['between']['mean_compound'] >= g['within']['mean_compound'] else "cross-camp replies are harsher than replies within a camp."))
    br = y.get("bridges") or []
    if br:
        obs.append(f"On the full network the strongest broker ({br[0]['id']}) reaches {br[0]['reached']} clusters with participation {br[0]['participation']:.2f} and betweenness {br[0]['betweenness']:.3f}.")
    per = s.get("persistence") or []
    if per:
        obs.append("Cluster membership of returning users between consecutive quarters: " + ", ".join(f"{p['from']}→{p['to']} ARI {p['ari']} (n={p['users_in_both']})" for p in per) + ".")
    return {"question": f"What does the conversation inside r/{sub} look like as a network: who replies to whom, which groups form, who connects them, and how stable is it?",
            "context": f"r/{sub} was chosen from fourteen candidates on a selection matrix computed over the same quarter ({s['selection_window']['start']} – {s['selection_window']['end']}): "
                       f"network quality {row.get('network_quality')}, community structure {row.get('community_structure')}, interesting patterns {row.get('interesting_patterns')}, "
                       f"data completeness {row.get('data_completeness')}, storytelling potential {row.get('storytelling')} (total {row.get('total')}); the runner-up is r/{s['alternative']}.",
            "observation": " ".join(obs),
            "explanation": "Reply ties are real interactions (a comment under another user's comment). Clusters are groups of users who answer each other more than chance would give, and are reported with their stability and a rewired baseline because modularity finds clusters even in random graphs; brokers are the few users whose replies span several of them; the E–I index against its rewired baseline and the cross-camp tone separate who talks to whom from how they talk.",
            "conclusion": (s["insights"][0]["title"] if s["insights"] else f"r/{sub} has a measurable, stable reply structure") + ". See the insight cards for the evidence behind each statement.",
            "limitations": ["Edges exist only where a parent comment and its author are in the data; replies to posts and to deleted comments are invisible."] + [x for x in [_validation_note()] if x] + [
                            "Clusters come from one modularity partition (Leiden, best of several seeds); small clusters are unstable.",
                            "Flair groups are self-declared, keyword-matched and cover only flaired users; they are stances by self-description, not measured opinions.",
                            "Pseudonymous ids; no attempt is made to identify accounts, and none should be."]}
