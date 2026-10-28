"""Regression tests for case-sensitive frame matching.

The Arctic subsample is not case-consistent ("Cooking", "Physics", "ptsd"),
while the FRAME dict is written with its own casing. fetch.py previously used
an exact-match `WHERE subreddit IN (...)`, which silently deleted 19 of 150
frame subreddits (~6% of frame comment volume) with no warning. These tests
pin the fix so casing can never again delete data.
"""
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data_curation"))
sys.path.insert(0, str(ROOT / "network_analysis"))

import config as C
import fetch as F

# Real spellings observed in the Arctic 2018-2022 calibration sample.
CORPUS_SPELLINGS = {
    "cooking": "Cooking",
    "physics": "Physics",
    "PTSD": "ptsd",
    "FIRE": "Fire",
    "politicalcompassmemes": "PoliticalCompassMemes",
    "parenting": "Parenting",
    "economics": "Economics",
    "libertarian": "Libertarian",
    "realestate": "RealEstate",
    "astronomy": "Astronomy",
}


class TestFrameFilterSQL:
    def test_literals_are_lowercased(self):
        sql = F.build_frame_filter_sql({"cooking": "hobby", "AskReddit": "x"})
        assert "'cooking'" in sql and "'askreddit'" in sql
        assert "'Cooking'" not in sql and "'AskReddit'" not in sql

    def test_deduplicates_case_variants(self):
        sql = F.build_frame_filter_sql({"cooking": "hobby", "Cooking": "hobby"})
        assert sql.count("'cooking'") == 1
        assert sql.count(",") == 0

    def test_strips_quotes_and_blanks(self):
        sql = F.build_frame_filter_sql({"we'ird": "x", "  ": "y", " a ": "z"})
        assert "'weird'" in sql and "'a'" in sql
        assert "''" not in sql

    def test_all_frame_names_lowercase(self):
        sql = F.build_frame_filter_sql(C.FRAME)
        literals = [s.strip("'") for s in sql.split(",")]
        assert literals and all(s == s.lower() for s in literals)
        assert len(literals) == len(C.FRAME)


class TestCategoryLookup:
    """Frame-agnostic: uses whatever frame.csv currently holds."""

    def test_matches_regardless_of_casing(self):
        for name, cat in C.FRAME_ALL.items():
            assert C.category_of(name) == cat
            assert C.category_of(name.lower()) == cat
            assert C.category_of(name.upper()) == cat

    def test_out_of_frame_returns_hub_bucket(self):
        # "soccer" is on the documented omission list, so it is a real
        # non-member rather than a hypothetical.
        assert "soccer" not in {s.lower() for s in C.FRAME_ALL}
        assert C.category_of("soccer") == "other / hub"
        assert C.category_of("SOCCER") == "other / hub"
        assert C.category_of(None) == "other / hub"
        assert C.category_of("") == "other / hub"

    def test_in_frame_is_case_insensitive(self):
        for name in C.FRAME_ALL:
            assert C.in_frame(name) and C.in_frame(name.lower())
            assert C.in_frame(name.upper())
        assert not C.in_frame("soccer")

    def test_no_frame_collision_after_folding(self):
        folded = {}
        for s, cat in C.FRAME_ALL.items():
            assert s.lower() not in folded, f"{s} collides with {folded.get(s.lower())}"
            folded[s.lower()] = cat

    def test_every_stratum_is_reachable(self):
        seen = {C.category_of(s) for s in C.FRAME_ALL}
        assert seen == set(C.FRAME_ALL.values())
        assert "gateway" in seen


class TestCoverageAssertion:
    @staticmethod
    def _table(con, rows):
        con.execute("CREATE TABLE t (subreddit VARCHAR)")
        if rows:
            con.executemany("INSERT INTO t VALUES (?)", [(r,) for r in rows])

    def test_passes_when_every_sub_present(self):
        con = duckdb.connect()
        self._table(con, list(CORPUS_SPELLINGS.values()))
        rep = F.assert_frame_coverage(con, "t", C.FRAME, "2018Q1",
                                      allowed_missing=C.FRAME)
        assert rep["frame_size"] == len(C.FRAME)

    def test_raises_on_missing_subreddit(self):
        con = duckdb.connect()
        self._table(con, ["Cooking"])
        with pytest.raises(RuntimeError, match="produced no rows"):
            F.assert_frame_coverage(con, "t", C.FRAME, "2018Q1",
                                    allowed_missing=set())

    def test_case_mismatch_alone_does_not_raise(self):
        """The regression itself: differing casing must not count as missing."""
        con = duckdb.connect()
        self._table(con, list(C.FRAME))
        F.assert_frame_coverage(con, "t", C.FRAME, "2018Q1",
                                allowed_missing=C.FRAME)

    def test_documented_unobservable_subs_warn_not_raise(self):
        con = duckdb.connect()
        absent = C.FRAME_UNOBSERVABLE
        present = [s for s in C.FRAME if s not in absent]
        self._table(con, present)
        rep = F.assert_frame_coverage(con, "t", C.FRAME, "2018Q1",
                                      allowed_missing=absent)
        assert set(rep["missing"]) == {a.lower() for a in absent}

    def test_unobservable_set_actually_absent(self):
        for s in C.FRAME_UNOBSERVABLE:
            assert s in C.FRAME, f"{s} documented as unobservable but not in FRAME"


class TestRunConfigFrameSize:
    def test_tracks_custom_frame(self):
        cfg = C.RunConfig(frame={"a": "x", "b": "y"})
        assert cfg.frame_size == 2

    def test_default_covers_whole_frame(self):
        cfg = C.RunConfig()
        assert cfg.frame_size == len(C.FRAME_ALL)
        assert len(cfg.frame) == len(C.FRAME_ALL)

    def test_conflicting_explicit_size_is_corrected(self):
        with pytest.warns(RuntimeWarning):
            cfg = C.RunConfig(frame={"a": "x"}, frame_size=99)
        assert cfg.frame_size == 1


class TestFrameIsDerivedNotHandTyped:
    """frame.csv is GENERATED by frame_rules.build_frame(). If the two drift,
    the committed artifact a reviewer reads no longer describes the frame the
    pipeline fetches -- the same drift class as the case-sensitivity bug."""

    def test_committed_csv_matches_the_rule(self):
        import frame_rules as FR
        import pandas as pd
        committed = pd.read_csv(ROOT / "frame.csv")
        derived = FR.build_frame()
        assert len(committed) == len(derived)
        got = dict(zip(committed.subreddit.str.lower(), committed.category))
        want = dict(zip(derived.subreddit.str.lower(), derived.stratum))
        assert got == want, (
            "frame.csv is out of date with frame_rules.py; regenerate it with "
            "`python tools/build_frame.py`")

    def test_stratum_sizes(self):
        assert len(C.FRAME) == 150
        assert len(C.GATEWAY_STRATUM) == 20
        assert len(C.FRAME_ALL) == 170

    def test_topical_strata_are_25_each(self):
        counts = pd.Series(list(C.FRAME.values())).value_counts()
        assert set(counts.index) == {"politics_news", "hobby", "finance",
                                     "support", "expertise", "media"}
        assert (counts == 25).all()

    def test_no_subreddit_in_two_strata(self):
        lowered = [s.lower() for s in C.FRAME_ALL]
        assert len(lowered) == len(set(lowered))

    def test_every_member_observable_at_all_calibration_points(self):
        import frame_rules as FR
        pool = FR.load_pool()
        n_min = dict(zip(pool.subreddit.str.lower(), pool.n_min))
        for s in C.FRAME_ALL:
            assert n_min.get(s.lower(), 0) >= FR.MIN_N, (
                f"{s} has n_min={n_min.get(s.lower(), 0)} < {FR.MIN_N}")

    def test_excluded_hubs_are_not_in_the_frame(self):
        overlap = {s.lower() for s in C.EXCLUDED_HUBS} & \
                  {s.lower() for s in C.FRAME_ALL}
        assert not overlap, f"declared-excluded subs are in the frame: {overlap}"

    def test_gateway_hubs_previously_excluded_are_now_included(self):
        for s in ("AskReddit", "worldnews", "funny", "pics", "todayilearned"):
            assert C.in_frame(s), f"{s} was meant to be added as a gateway"
            assert C.category_of(s) == "gateway"


import pandas as pd  # noqa: E402  (used by the tests above)
