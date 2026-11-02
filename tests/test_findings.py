"""Findings section: unit tests on synthetic data (no Reddit data needed) and artifact tests when the JSON exists.

The artifact tests enforce the publication rule: nothing in atlas/web/data/findings may contain comment text, author
hashes or usernames; networks carry anonymous ids only; every insight links to a route of the application.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from findings import config as F
from findings import events as EV
from findings import insights as INS
from findings import networks as N
from findings import text as T

FINDINGS = Path(__file__).resolve().parents[1] / "atlas" / "web" / "data" / "findings"


# ---- networks -------------------------------------------------------------------------------------
def _comments(edges, extra_singletons=0):
    """Build a comments frame in which `edges` = [(replier, parent_author), ...] become real parent links."""
    rows, k = [], 0
    for src, dst in edges:
        k += 1
        rows.append({"id": f"p{k}", "parent_id": "t3_post", "author_h": dst})       # the parent comment
        rows.append({"id": f"c{k}", "parent_id": f"t1_p{k}", "author_h": src})      # the reply
    for j in range(extra_singletons):
        rows.append({"id": f"s{j}", "parent_id": "t3_post", "author_h": f"lone{j}"})
    return pd.DataFrame(rows)


def test_reply_edges_follow_parent_links_only():
    df = _comments([("a", "b"), ("a", "b"), ("c", "a"), ("d", "d")], extra_singletons=3)
    e = N.reply_edges(df)
    pairs = {(r.src, r.dst): r.w for r in e.itertuples()}
    assert pairs == {("a", "b"): 2, ("c", "a"): 1}          # self-reply dropped, post replies make no edge


def test_build_graph_min_replies_and_reciprocity():
    df = _comments([("a", "b"), ("b", "a"), ("c", "a"), ("x", "y")])
    g = N.build_graph(N.reply_edges(df), min_replies=2)
    assert set(g.vs["name"]) == {"a", "b", "c"} or set(g.vs["name"]) == {"a", "b"}
    assert 0 <= g["reciprocity"] <= 1


def test_two_planted_groups_and_bridge():
    rng = np.random.default_rng(0)
    A = [f"a{i}" for i in range(12)]; B = [f"b{i}" for i in range(12)]
    edges = []
    for grp in (A, B):
        for _ in range(80):
            u, v = rng.choice(grp, 2, replace=False); edges.append((u, v))
    for _ in range(6):                       # one broker talks to both sides
        edges.append(("broker", rng.choice(A))); edges.append(("broker", rng.choice(B)))
    g = N.build_graph(N.reply_edges(_comments(edges)), min_replies=1)
    comm = N.communities(g)
    met = N.node_metrics(g, comm["membership"])
    assert comm["modularity"] > 0.3
    top = met.sort_values("betweenness", ascending=False).iloc[0]
    assert top["name"] == "broker" and top["communities_reached"] >= 2 and top["participation"] > 0.4
    core, cover = N.readable_core(g, max_nodes=10, min_nodes=3)
    assert 3 <= core.vcount() <= 10 and 0 < cover["edge_share"] <= 1
    alias = N.anonymise(g)
    assert all(re.fullmatch(r"u\d+", v) for v in alias.values()) and len(set(alias.values())) == g.vcount()
    ex = N.export(g, comm["membership"], met, N.layout(g))
    assert {n["id"] for n in ex["nodes"]} == set(alias.values()) and all(0 <= n["x"] <= 1 and 0 <= n["y"] <= 1 for n in ex["nodes"])


def test_ei_index_extremes():
    g = N.build_graph(N.reply_edges(_comments([("a", "b"), ("c", "d")])), min_replies=1)
    assert N.ei_index(g, ["x", "x", "y", "y"][: g.vcount()]) == -1.0 if g.vcount() == 4 else True
    assert N.ei_index(g, ["x", "y", "x", "y"][: g.vcount()]) == 1.0 if g.vcount() == 4 else True


def test_flair_groups():
    assert N.flair_group("capitalismvsocialism", "Libertarian Socialist") == "left"
    assert N.flair_group("capitalismvsocialism", "Anarcho-Capitalist") == "right"
    assert N.flair_group("capitalismvsocialism", "Voluntaryist") == "right"
    assert N.flair_group("capitalismvsocialism", "Mutualist") == "left"
    assert N.flair_group("capitalismvsocialism", "Social Democrat") == "centre"
    assert N.flair_group("capitalismvsocialism", "Chairman Meow") is None
    assert N.flair_group("purplepilldebate", "Red Pill Man") == "red"
    assert N.flair_group("purplepilldebate", "Mostly Red") == "red"
    assert N.flair_group("purplepilldebate", "banana") is None


# ---- text -----------------------------------------------------------------------------------------
def test_clean_body_and_labels():
    assert "http" not in T.clean_body("see https://x.y/z > quoted\n**bold** text")
    lab = T.label(np.array([0.5, 0.0, -0.5, 0.04, -0.04]))
    assert list(lab) == ["pos", "neu", "neg", "neu", "neu"]
    sc = T.score_texts(["This is wonderful, I love it", "This is terrible, I hate it", ""])
    assert sc[0, 0] > 0.3 and sc[1, 0] < -0.3 and sc[2, 2] == 1.0


def test_log_odds_direction():
    a = Counter({"moon": 50, "dip": 40, "film": 2, "common": 100})
    b = Counter({"film": 60, "thanos": 40, "moon": 1, "common": 100})
    top_a = [d["term"] for d in T.log_odds(a, b, min_count=5, top=2)]
    top_b = [d["term"] for d in T.log_odds(b, a, min_count=5, top=2)]
    assert "moon" in top_a and "film" in top_b and "common" not in top_a


# ---- events ----------------------------------------------------------------------------------------
def test_compare_and_change_points():
    rng = np.random.default_rng(1)
    same = EV.compare(rng.normal(0, 1, 500), rng.normal(0, 1, 500), permutations=200)
    assert abs(same["cohen_d"]) < 0.2 and same["p_perm"] > 0.01
    diff = EV.compare(rng.normal(0, 1, 500), rng.normal(0.5, 1, 500), permutations=200)
    assert diff["cohen_d"] > 0.3 and diff["p_perm"] < 0.01 and diff["ci95"][0] > 0
    y = np.r_[rng.normal(10, 1, 40), rng.normal(30, 2, 20), rng.normal(12, 1, 40)]
    cps = EV.change_points(y)
    assert any(abs(c - 40) <= 2 for c in cps) and any(abs(c - 60) <= 2 for c in cps)


def test_price_extrema_zigzag():
    days = [f"2018-01-{d:02d}" for d in range(1, 31)]
    p = [10] * 5 + [20] * 5 + [12] * 5 + [18] * 5 + [9] * 5 + [9.5] * 5
    ext = EV.price_extrema(pd.DataFrame({"day": days, "price": p}), min_swing=0.3)
    types = [e["type"] for e in ext]
    assert types[0] == "start" and "peak" in types and "trough" in types
    phases = EV.price_phases(ext)
    assert phases[0]["label"] == "run-up" and any(ph["label"].startswith("decline") for ph in phases)


def test_robust_z_flags_spike():
    base = np.array([100, 105, 98, 101, 99, 103, 97, 102, 100, 104], dtype=float)
    z = EV.robust_z(np.array([150, 102]), base)
    assert z[0] > 3 and abs(z[1]) < 1


# ---- insights -----------------------------------------------------------------------------------------
def test_surge_detector_fires_only_on_spikes():
    daily = [{"day": f"2018-04-{d:02d}", "comments": 100 + (d % 3)} for d in range(1, 20)] + [{"day": "2018-04-27", "comments": 900}, {"day": "2018-04-28", "comments": 105}]
    x = INS.surge(daily, ("2018-04-01", "2018-04-19"), ("2018-04-27", "2018-04-28"), "test", "#/x", "release")
    assert x and x["kind"] == "volume_surge" and x["evidence"]["peak_day"] == "2018-04-27"
    flat = [{"day": f"2018-04-{d:02d}", "comments": 100 + (d % 3)} for d in range(1, 29)]
    assert INS.surge(flat, ("2018-04-01", "2018-04-19"), ("2018-04-20", "2018-04-28"), "test", "#/x", "release") is None


def test_shift_detector_needs_effect_and_significance():
    cmp_down = {"n_a": 1000, "n_b": 1000, "mean_a": 0.1, "mean_b": 0.0, "diff": -0.1, "cohen_d": -0.25, "ci95": [-0.15, -0.05], "p_perm": 0.0005}
    weak = {"class": "neg", "n_a": 1000, "n_b": 1000, "share_a": 0.20, "share_b": 0.21, "diff": 0.01, "cohen_h": 0.02, "ci95": [0.0, 0.02], "p_perm": 0.0005}
    assert INS.shift(cmp_down, None, "s", "a", "b", "p", "#/x", shares=weak) is None
    strong = {"class": "neg", "n_a": 1000, "n_b": 1000, "share_a": 0.20, "share_b": 0.30, "diff": 0.10, "cohen_h": 0.23, "ci95": [0.06, 0.14], "p_perm": 0.0005}
    x = INS.shift(cmp_down, None, "s", "a", "b", "p", "#/x", shares=strong)
    assert x and x["confidence"] == "medium" and "more negative" in x["title"]
    cmp_up = {**cmp_down, "diff": 0.1, "cohen_d": 0.25, "ci95": [0.05, 0.15]}
    assert INS.shift(cmp_up, None, "s", "a", "b", "p", "#/x", shares=strong) is None   # share and mean disagree in direction


def test_finalize_applies_bh_and_drops_weak():
    mk = lambda p: {"kind": "k", "title": "t", "confidence": "high", "evidence": {"p_perm": p}}   # noqa: E731
    out = INS.finalize([mk(0.0005), mk(0.02), mk(0.2), {"kind": "d", "title": "x", "confidence": "descriptive", "evidence": {}}])
    assert len(out) == 3 and out[0]["q_value"] <= 0.01 and out[0]["confidence"] == "high"
    assert out[1]["confidence"] == "medium" and all(i["n_candidates_tested"] == 3 for i in out)


def test_compare_shares_and_its():
    rng = np.random.default_rng(4)
    a = rng.choice(["neg", "pos", "neu"], 2000, p=[0.2, 0.4, 0.4]); b = rng.choice(["neg", "pos", "neu"], 2000, p=[0.3, 0.35, 0.35])
    r = EV.compare_shares(a.tolist(), b.tolist(), "neg", permutations=200)
    assert r["diff"] > 0.05 and r["cohen_h"] > 0.15 and r["p_perm"] < 0.01 and r["ci95"][0] > 0
    days = [f"2018-04-{d:02d}" for d in range(1, 31)] + [f"2018-05-{d:02d}" for d in range(1, 31)]
    counts = np.r_[rng.poisson(100, 30), rng.poisson(300, 30)]
    its = EV.its_level_change(counts, days, "2018-05-01")
    assert its["level_change_pct"] > 1.5 and its["t"] > 3


def test_domain_neutralised_scores():
    sc = T.score_texts(["That scene where he killed him was absolutely brilliant"], domains=["marvel"])
    assert sc[0, 4] > sc[0, 0]   # neutralising 'dies' lifts the score
    sc2 = T.score_texts(["That scene was brilliant"], domains=["marvel"])
    assert abs(sc2[0, 4] - sc2[0, 0]) < 1e-6
    assert "kill" in T.neutralised_words("marvel") and "crash" in T.neutralised_words("crypto")


def test_ei_null_and_broker_significance():
    rng = np.random.default_rng(0)
    A = [f"a{i}" for i in range(15)]; B = [f"b{i}" for i in range(15)]
    edges = []
    for grp in (A, B):
        for _ in range(120):
            u, v = rng.choice(grp, 2, replace=False); edges.append((u, v))
    for _ in range(8):
        edges.append(("broker", rng.choice(A))); edges.append(("broker", rng.choice(B)))
    g = N.build_graph(N.reply_edges(_comments(edges)), min_replies=1)
    group = ["A" if n.startswith("a") else "B" if n.startswith("b") else None for n in g.vs["name"]]
    e = N.ei_null(g, group, n=30)
    assert e["observed"] < e["null_mean"] and e["z"] < -3          # segregated far beyond chance
    sig = N.broker_significance(g, ["broker"], n=30)
    assert sig["broker"]["z"] > 2 and sig["broker"]["p"] < 0.1


# ---- published artifacts (only when built) -----------------------------------------------------------
HEX16 = re.compile(r"(?<![\w.])[0-9a-f]{16}(?![\w.])")


@pytest.mark.skipif(not (FINDINGS / "index.json").exists(), reason="findings artifacts not built")
def test_findings_artifacts_are_anonymous_and_linked():
    files = list(FINDINGS.glob("*.json"))
    for f in files:
        txt = f.read_text(encoding="utf-8")
        assert not {h for h in HEX16.findall(txt) if re.search("[a-f]", h)}, f"{f.name}: hash-like token"
        assert "author_h" not in txt and '"body"' not in txt, f"{f.name}: text or author column leaked"
    idx = json.loads((FINDINGS / "index.json").read_text(encoding="utf-8"))
    for ins in idx["insights"]:
        assert ins["link"].startswith("#/findings"), ins["title"]
        assert ins["confidence"] in ("high", "medium", "descriptive")
        for key in ("title", "observed", "evidence", "period", "scope", "why_interesting", "interpretation", "limitations"):
            assert ins[key], f"{ins['title']} missing {key}"
    for sid in ("community", "infinity_war", "bitcoin"):
        p = FINDINGS / f"{sid}.json"
        if not p.exists():
            continue
        st = json.loads(p.read_text(encoding="utf-8"))
        assert all(k in st["narrative"] for k in ("question", "context", "observation", "explanation", "conclusion", "limitations"))
        nets = []
        if sid == "community":
            nets = [st["year"]]
        else:
            nets = [v for d in st["networks"].values() for v in d.values()]
        for net in nets:
            core = net.get("core")
            if not core:
                continue
            ids = {n["id"] for n in core["nodes"]}
            assert all(re.fullmatch(r"u\d+", i) for i in ids)
            assert all(e["s"] in ids and e["t"] in ids for e in core["edges"])
            assert len(core["nodes"]) <= F.FOCUS_MAX_NODES


def test_finalize_pools_every_test_run():
    """BH runs over every permutation test a story ran (fired or not): the pool size is m and fired p-values are adjusted against it."""
    mk = lambda p: {"kind": "x", "title": "t", "confidence": "high", "evidence": {"p_perm": p}}
    out = INS.finalize([mk(0.001)], tested=[0.001, 0.5, 0.2, 0.9, 0.04, 0.3, 0.7, 0.6, 0.8, 0.1])
    assert out[0]["n_candidates_tested"] == 10 and out[0]["q_value"] == 0.01      # 0.001 * 10 / 1
    out = INS.finalize([mk(0.02)], tested=[0.02, 0.001, 0.5])
    assert out[0]["q_value"] == 0.03 and out[0]["confidence"] == "medium"          # 0.02 * 3 / 2: kept, demoted
    assert INS.finalize([mk(0.001)])[0]["q_value"] == 0.001                        # no pool: the fired p-values only


def test_core_metrics_follow_the_published_partition_and_terms_carry_no_mentions():
    """Every published core: a node's 'reached' equals the number of distinct clusters among its neighbours under the
    published `community` field (one partition for the drawing, the tables and the insights); and no published term is
    an account mention."""
    files = [FINDINGS / f"{sid}.json" for sid in ("community", "infinity_war", "bitcoin")]
    files = [f for f in files if f.exists()]
    if not files:
        pytest.skip("no built stories")
    terms = []
    for f in files:
        st = json.loads(f.read_text(encoding="utf-8"))
        nets = [st["year"]] if "year" in st else [v for d in st["networks"].values() for v in d.values()]
        for net in nets:
            core = net.get("core")
            if not core:
                continue
            comm = {n["id"]: n["community"] for n in core["nodes"]}
            nbrs = {i: set() for i in comm}
            for e in core["edges"]:
                nbrs[e["s"]].add(comm[e["t"]]); nbrs[e["t"]].add(comm[e["s"]])
            for n in core["nodes"]:
                assert n["reached"] == len(nbrs[n["id"]]), (f.name, n["id"], n["reached"], len(nbrs[n["id"]]))
            for c in net.get("communities", []):
                terms += c.get("top_terms") or []
        for per_sub in (st.get("themes") or {}).values():
            for lst in (per_sub.values() if isinstance(per_sub, dict) else []):
                terms += [t["term"] for t in lst if isinstance(t, dict) and "term" in t]
    assert terms and not [t for t in terms if "/" in t or t.startswith("u_")], "a published term looks like an account mention"


def test_newcomer_share_uses_a_fixed_lookback():
    assert EV.lookback_start("2017-12-01", 2) == "2017-10-01"
    assert EV.lookback_start("2017-11-01", 2) is None                  # would reach before the store: undefined, not 100 %
    assert EV.lookback_start("2018-03-02", 5) == "2017-10-02"
    assert EV.newcomer_share({"a", "b", "c"}, {"a"}) == pytest.approx(0.667, abs=1e-3)
    assert EV.newcomer_share(set(), {"a"}) is None
    assert EV.newcomer_share({"a"}, None) is None
    hist = pd.DataFrame({"subreddit": ["s"] * 4, "author_h": ["a", "b", "c", "d"], "day": ["2018-01-05", "2018-02-20", "2017-12-30", "2018-03-02"]})
    assert EV.active_users(hist, "s", "2018-01-01", "2018-02-28") == {"a", "b"}


def test_tokens_strip_mentions_before_markdown_cleaning():
    assert "username" not in T.tokens("thanks u/plain_username for the write-up")
    assert "capitaluser" not in T.tokens("/U/CapitalUser said so")
    toks = T.tokens("ping u/GoodBot_BadBot please")
    assert "ping" in toks and "badbot" not in toks and "goodbot" not in toks


def test_level_change_reports_a_newey_west_error():
    rng = np.random.default_rng(0)
    days = [str(d.date()) for d in pd.date_range("2018-03-01", periods=80)]
    e = np.zeros(80)
    for k in range(1, 80):
        e[k] = 0.7 * e[k - 1] + rng.normal(0, 0.3)            # autocorrelated noise
    counts = np.exp(5 + 0.6 * (np.arange(80) >= 50) + e)
    r = EV.its_level_change(counts, days, days[50])
    assert r["hac_lags"] >= 1 and r["se_hac"] > 0 and r["t_hac"] is not None
    assert r["se_hac"] > r["se"]                              # the OLS error understates the uncertainty here
