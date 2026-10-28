"""
tests/test_measure_validity.py
=============================
Synthetic-fixture tests for the network measures.

WHY THIS FILE EXISTS:
    The 2018Q1 run shipped a participation coefficient that was mathematically
    identical to `1 - 1/k_i`, a bridge position set that covered 100% of the
    C(34,2) possible community pairs, and a null model that drew
    np.random.uniform(0.01, 0.05) and reported a hardcoded p = 0.001. None of
    that was caught, because there were no tests. These tests encode the
    failure modes as executable assertions so they cannot silently return.

Tests that assert a CURRENT DEFECT are marked `characterization` and say so in
the docstring: they pin the observed behaviour of the real production
functions. If one starts failing, that is the defect being fixed -- flip the
assertion at that point, do not delete the test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from network_analysis.brokerage import compute_participation_coefficients
from network_analysis.stability_analysis import (
    UNMATCHED_ID_OFFSET,
    _double_edge_swap_bipartite,
    _rewire_dataframe,
    compare_position_vs_person_stability,
    compute_bridge_widths,
    extract_bridge_positions,
    occupant_stability_by_width,
    run_degree_preserving_null_model,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def pair_table(pairs, n_comments=1):
    """Build the (author_h, subreddit, n_comments, is_mod) shape the pipeline uses."""
    return pd.DataFrame(
        {
            "author_h": [p[0] for p in pairs],
            "subreddit": [p[1] for p in pairs],
            "n_comments": [n_comments] * len(pairs),
            "is_mod": [0] * len(pairs),
        }
    )


def singleton_partition(subs):
    return {s: i for i, s in enumerate(sorted(subs))}


def brokers_table(users, flag=True):
    return pd.DataFrame({"author_h": users, "is_broker": [flag] * len(users)})


# ---------------------------------------------------------------------------
# Participation coefficient
# ---------------------------------------------------------------------------
def test_p_collapses_to_one_minus_one_over_k_on_singleton_communities():
    """The observed 2018Q1 defect: 33 of 34 communities were singletons.

    When every subreddit is its own community, P_i is forced to 1 - 1/k_i and
    therefore carries no information beyond 'how many subreddits did this
    account touch'. It cannot separate a dedicated contributor from a drive-by.
    """
    subs = [f"s{i}" for i in range(5)]
    pairs = [("u1", s) for s in subs]           # one comment in each of 5 subs
    df = pair_table(pairs)

    out = compute_participation_coefficients(df, singleton_partition(subs))
    p = float(out.loc[out["author_h"] == "u1", "P"].iloc[0])

    assert p == pytest.approx(1 - 1 / 5, abs=1e-12)
    assert p == pytest.approx(1 - 1 / out.loc[out["author_h"] == "u1",
                                              "n_subs"].iloc[0], abs=1e-12)


def test_participation_ignores_comment_volume():
    """Characterization of a real defect: n_comments is loaded but never used.

    `bipartite.load_bipartite_dataframe` returns one row per (user, subreddit)
    and counts comments into a `n_comments` column, but
    `compute_participation_coefficients` calls `groupby(...).size()`, which
    counts ROWS. So a user with 400 comments in 5 subreddits and a user with 1
    comment in each of 5 subreddits receive an identical P. The volume signal
    the docstring advertises is discarded.
    """
    subs = [f"s{i}" for i in range(5)]
    pairs = [("heavy", s) for s in subs] + [("light", s) for s in subs]
    base = pair_table(pairs)

    scaled = base.copy()
    scaled.loc[scaled["author_h"] == "heavy", "n_comments"] = 80
    scaled.loc[scaled["author_h"] == "light", "n_comments"] = 1

    part = singleton_partition(subs)
    out = compute_participation_coefficients(base, part)
    out2 = compute_participation_coefficients(scaled, part)

    p_heavy = float(out.loc[out["author_h"] == "heavy", "P"].iloc[0])
    p_heavy_scaled = float(out2.loc[out2["author_h"] == "heavy", "P"].iloc[0])
    assert p_heavy == pytest.approx(p_heavy_scaled, abs=1e-12), (
        "n_comments is no longer used by compute_participation_coefficients. "
        "The volume-based weighting has been implemented -- update this test to "
        "assert that a heavier user scores HIGHER."
    )


def test_p_distinguishes_clustered_participation_from_specialisation():
    """Positive control: on a genuine partition P must discriminate.

    One account is confined to a single community; another spreads evenly over
    two. A working participation coefficient must rank the spreader higher.
    """
    subs = ["a1", "a2", "b1", "b2"]
    part = {"a1": 0, "a2": 0, "b1": 1, "b2": 1}
    pairs = [("specialist", "a1"), ("specialist", "a2"), ("spreader", "a1"),
             ("spreader", "b1")]
    df = pair_table(pairs)

    out = compute_participation_coefficients(df, part)
    p_spec = float(out.loc[out["author_h"] == "specialist", "P"].iloc[0])
    p_spread = float(out.loc[out["author_h"] == "spreader", "P"].iloc[0])

    assert p_spec == pytest.approx(0.0, abs=1e-12)
    assert p_spread == pytest.approx(0.5, abs=1e-12)
    assert p_spread > p_spec


# ---------------------------------------------------------------------------
# Bridge positions: saturation, width, and the ID-collision fix
# ---------------------------------------------------------------------------
def test_fully_occupied_position_set_pins_jaccard_to_one():
    """The 2018Q1 defect: 561 positions == C(34,2) == every possible pair.

    A saturated position set cannot shrink, so J_position is 1.0 no matter what
    happens to the accounts, and H1 (position more stable than person) is
    unfalsifiable. This is the arithmetic behind the claim that the old H1 was
    true by construction.
    """
    comms = list(range(34))
    all_pairs = {(a, b) for i, a in enumerate(comms) for b in comms[i + 1:]}
    assert len(all_pairs) == 561  # C(34, 2)

    occ1 = {p: {f"u{i}"} for i, p in enumerate(all_pairs)}
    occ2 = {p: {f"v{i}"} for i, p in enumerate(all_pairs)}  # complete turnover

    stab = compare_position_vs_person_stability(set(occ1), occ1, set(occ2), occ2)
    assert stab["position_stability"] == pytest.approx(1.0)
    assert stab["person_stability"] == pytest.approx(0.0)
    assert stab["stability_gap"] == pytest.approx(1.0)


def test_min_width_breaks_saturation():
    """min_width > 1 keeps only load-bearing bridges (Centola & Macy width)."""
    subs = ["a1", "a2", "b1", "b2"]
    part = {"a1": 0, "a2": 0, "b1": 1, "b2": 1}
    # u1 and u2 both bridge A<->B; u3 alone bridges nothing load-bearing.
    pairs = [("u1", s) for s in subs] + [("u2", s) for s in subs] + [("u3", "a1")]
    df = pair_table(pairs)
    brokers = brokers_table(["u1", "u2", "u3"])

    pos_all, occ_all = extract_bridge_positions(df, brokers, part)
    pos_wide, occ_wide = extract_bridge_positions(df, brokers, part, min_width=2)

    assert compute_bridge_widths(occ_all)[(0, 1)] == 2   # u1 and u2
    assert (0, 1) in pos_all
    assert pos_wide == {(0, 1)}, "only the width-2 bridge should survive min_width=2"
    assert set(occ_wide[(0, 1)]) == {"u1", "u2"}


def test_unmatched_communities_cannot_collide_with_anchor_ids():
    """Real bug: `matched_map.get(c, c)` let unmatched raw ids alias anchor ids.

    Anchored matching cannot map a community that is absent from the anchor
    partition, so it fell through to the raw id. A raw community 3 that failed
    to match was then written as id 3 -- indistinguishable from anchor
    community 3, merging two unrelated communities into one position.
    """
    subs = ["a", "b", "c"]
    part = {"a": 0, "b": 1, "c": 2}
    df = pair_table([("u1", s) for s in subs])
    brokers = brokers_table(["u1"])

    # Only community 0 matches the anchor; 1 and 2 are unmatched.
    matched = {0: 0}
    _, occ = extract_bridge_positions(df, brokers, part, matched_map=matched)

    ids = sorted({cid for pos in occ for cid in pos})
    assert set(ids) == {0, UNMATCHED_ID_OFFSET - 1, UNMATCHED_ID_OFFSET - 2}
    # The collision is gone: no unmatched community shares an id with anchor 0.
    assert len(set(ids)) == 3


def test_occupant_stability_by_width_pairs_narrower_width():
    """Width is credited as min(w1, w2) so a collapsed quarter is not flattered."""
    occ1 = {(0, 1): {"a", "b", "c", "d"}}
    occ2 = {(0, 1): {"a"}}
    rows = occupant_stability_by_width(occ1, occ2)
    assert rows == [(1, pytest.approx(1 / 4))]


# ---------------------------------------------------------------------------
# Degree-preserving null model
# ---------------------------------------------------------------------------
def test_double_edge_swap_preserves_both_degree_sequences_exactly():
    """Maslov & Sneppen (2002): the null must control for degree, exactly."""
    rng = np.random.default_rng(7)
    users = np.repeat(np.arange(30), 4)
    subs = rng.integers(0, 12, size=len(users))
    edges = np.column_stack([users, subs])

    swapped = _double_edge_swap_bipartite(edges, rng, n_swaps=4000)

    for col, n in ((0, 30), (1, 12)):
        before = np.bincount(edges[:, col], minlength=n)
        after = np.bincount(swapped[:, col], minlength=n)
        assert np.array_equal(before, after), f"degree sequence changed on side {col}"

    assert len(swapped) == len(edges)


def test_rewire_dataframe_preserves_degrees_and_row_count():
    rng = np.random.default_rng(3)
    subs = [f"s{i}" for i in range(6)]
    pairs = [("u1", s) for s in subs] + [("u2", subs[0]), ("u2", subs[3])]
    df = pair_table(pairs)

    out = _rewire_dataframe(df, rng, n_swaps_per_edge=20)

    for user in df["author_h"].unique():
        before = set(df.loc[df["author_h"] == user, "subreddit"])
        after = set(out.loc[out["author_h"] == user, "subreddit"])
        assert before == after, f"{user} lost degree in the randomisation"
    for s in df["subreddit"].unique():
        assert int((df["subreddit"] == s).sum()) == int((out["subreddit"] == s).sum())


def test_null_model_reports_a_valid_empirical_p_value():
    """The old model returned a hardcoded p=0.001 from a uniform(0.01, 0.05) draw.

    A permutation p-value must be derived from the permutations, be a multiple
    of 1/(1+n), and never be zero.
    """
    subs = [f"s{i}" for i in range(6)]
    pairs = [("u1", s) for s in subs] + [("u2", s) for s in subs] \
        + [("u3", "s0"), ("u3", "s1"), ("u3", "s2")]
    df = pair_table(pairs)

    n = 4
    res = run_degree_preserving_null_model(
        df, df, observed_gap=0.5, n_iterations=n, seed=1, min_width=1
    )

    assert res["n_iterations"] == n
    assert len(res["null_gaps"]) == n
    assert res["p_value"] is not None
    assert 1.0 / (1 + n) <= res["p_value"] <= 1.0
    assert res["p_value"] == pytest.approx(
        (1 + res["n_null_ge_observed"]) / (1 + n)
    )
    lo, hi = res["null_gap_ci95"]
    assert lo <= res["null_gap_mean"] <= hi


def test_null_model_is_seed_deterministic():
    """Same seed, same null distribution -- so a reported p-value is reproducible."""
    subs = [f"s{i}" for i in range(5)]
    pairs = [("u1", s) for s in subs] + [("u2", s) for s in subs]
    df = pair_table(pairs)

    a = run_degree_preserving_null_model(df, df, observed_gap=0.2,
                                         n_iterations=3, seed=42)
    b = run_degree_preserving_null_model(df, df, observed_gap=0.2,
                                         n_iterations=3, seed=42)
    assert a["null_gaps"] == b["null_gaps"]
    assert a["p_value"] == b["p_value"]


def test_null_model_gaps_are_not_the_old_hardcoded_range():
    """Guards against a regression to fabricating the null distribution.

    The previous implementation appended np.random.uniform(0.01, 0.05) and
    discarded the permutation entirely, so every gap landed in that band by
    construction. Gaps produced by real randomisations must not be confined to
    it.
    """
    subs = [f"s{i}" for i in range(6)]
    pairs = [("u1", s) for s in subs] + [("u2", s) for s in subs] \
        + [("u3", "s0"), ("u3", "s2")]
    df = pair_table(pairs)

    res = run_degree_preserving_null_model(df, df, observed_gap=0.0,
                                           n_iterations=12, seed=5)
    gaps = res["null_gaps"]
    assert any(g < 0.01 or g > 0.05 for g in gaps), (
        "every null gap landed inside the old hardcoded uniform(0.01, 0.05) band"
    )
