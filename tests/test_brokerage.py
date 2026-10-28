"""Tests for the participation coefficient (Burt 1992).

P_i = 1 - sum_c (k_ic / k_i)^2

k_ic is the user's *strength of tie* to community c, i.e. their summed comment
count there. This was implemented as `groupby(...).size()` over a dataframe that
load_bipartite_dataframe() had already aggregated to one row per
(author, subreddit), so k_ic was always 1 and P_i collapsed to 1 - 1/k_i -- a
pure function of breadth. Engagement balance contributed nothing, and
`is_broker` silently reduced to "posts in many subreddits".
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from network_analysis.brokerage import compute_participation_coefficients

PART = {"SubOne": 0, "SubTwo": 1}


def _rows(pairs):
    return pd.DataFrame(
        pairs, columns=["author_h", "subreddit", "n_comments", "is_mod"])


def _p(pairs, user="A", pct=0.5):
    df = _rows(pairs)
    out = compute_participation_coefficients(df, PART, pct)
    return float(out.loc[out.author_h == user, "P"].iloc[0])


class TestParticipationCoefficient:
    def test_balanced_two_way_split(self):
        assert _p([("A", "SubOne", 1000, 0), ("A", "SubTwo", 1000, 0)]) == \
            pytest.approx(0.5)

    def test_matched_analytic_values(self):
        # 1 - (7/10)^2 - (3/10)^2 = 0.42
        assert _p([("u", "SubOne", 7, 0), ("u", "SubTwo", 3, 0)], "u") == \
            pytest.approx(0.42)

    def test_imbalance_is_detected(self):
        """The regression: these two users have identical breadth, so the old
        `.size()` implementation scored both 0.5."""
        balanced = _p([("A", "SubOne", 1000, 0), ("A", "SubTwo", 1000, 0)])
        monopolist = _p([("B", "SubOne", 1999, 0), ("B", "SubTwo", 1, 0)], "B")
        assert balanced == pytest.approx(0.5)
        assert monopolist == pytest.approx(1 - (1999 / 2000) ** 2 - (1 / 2000) ** 2)
        assert balanced - monopolist > 0.49

    def test_scale_invariant(self):
        """Participation measures *balance*, not activity level: doubling every
        count must not change P."""
        assert _p([("v", "SubOne", 1, 0), ("v", "SubTwo", 1, 0)], "v") == \
            _p([("v", "SubOne", 2, 0), ("v", "SubTwo", 2, 0)], "v")

    def test_single_community_user_is_zero(self):
        assert _p([("s", "SubOne", 500, 0)], "s") == pytest.approx(0.0)

    def test_n_comments_actually_feeds_k_ic(self):
        """Directly assert the internal quantity, not just the outcome."""
        df = _rows([("A", "SubOne", 7, 0), ("A", "SubTwo", 3, 0)])
        df["community"] = df["subreddit"].map(PART)
        grouped = df.groupby(["author_h", "community"])["n_comments"].sum()
        assert grouped.loc[("A", 0)] == 7
        assert grouped.loc[("A", 1)] == 3


class TestBrokerFlagging:
    def test_broker_needs_at_least_two_communities(self):
        df = _rows([("solo", "SubOne", 9000, 0), ("solo", "SubOne", 0, 0)])
        out = compute_participation_coefficients(df, PART, 0.5)
        assert not bool(out.loc[out.author_h == "solo", "is_broker"].iloc[0])

    def test_percentile_cutoff_selects_top_engagement_balance(self):
        rows = [("balanced", "SubOne", 100, 0), ("balanced", "SubTwo", 100, 0),
                ("lopsided", "SubOne", 199, 0), ("lopsided", "SubTwo", 1, 0)]
        out = compute_participation_coefficients(_rows(rows), PART, 0.5)
        flag = dict(zip(out.author_h, out.is_broker))
        assert flag["balanced"] and not flag["lopsided"]

    def test_subreddits_outside_partition_are_dropped(self):
        df = _rows([("A", "NotInPartition", 500, 0)])
        out = compute_participation_coefficients(df, PART, 0.5)
        assert out.empty or "A" not in set(out.author_h)
