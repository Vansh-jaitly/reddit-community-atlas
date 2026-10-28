"""Tests for the manual-review verdict stage.

Manual review is a REQUIRED stage per the synopsis. It only counts as real if
(a) a recorded verdict changes the data, and (b) a blank verdict is not
mistaken for a recorded one. Both directions were broken.
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data_curation"))

import clean as CL
import config as C


@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    cache = tmp_path / "cache"
    clean_dir = tmp_path / "clean"
    for d in (logs, cache, clean_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(C, "DATA_LOGS", logs)
    monkeypatch.setattr(C, "DATA_CACHE", cache)
    monkeypatch.setattr(C, "DATA_CLEAN", clean_dir)
    return tmp_path, logs, clean_dir


def _write_review(path: Path, rows):
    pd.DataFrame(rows, columns=["author_h", "n_comments", "n_subs",
                                "ever_mod", "flagged_high_volume",
                                "flagged_high_breadth", "verdict",
                                "notes"]).to_csv(path, index=False)


class TestVerdictLoading:
    def test_blank_verdicts_are_not_verdicts(self, dirs):
        _, logs, _ = dirs
        _write_review(logs / "manual_review_2018Q1.csv", [
            ("a", 100, 10, 0, False, False, "", ""),
            ("b", 100, 10, 0, False, False, None, None),
        ])
        assert CL.load_existing_verdicts("2018Q1") == {}

    def test_nan_verdicts_are_not_verdicts(self, dirs):
        """Regression: bool(float('nan')) is True, so `verdict or ""` let every
        unreviewed row through as the pseudo-verdict "nan"."""
        _, logs, _ = dirs
        _write_review(logs / "manual_review_2018Q1.csv", [
            ("a", 100, 10, 0, False, False, None, None),
            ("b", 100, 10, 0, False, False, float("nan"), None),
        ])
        assert CL.load_existing_verdicts("2018Q1") == {}

    def test_real_verdicts_survive_load(self, dirs):
        _, logs, _ = dirs
        _write_review(logs / "manual_review_2018Q1.csv", [
            ("a", 100, 10, 0, False, False, "bot", "obvious spam"),
            ("b", 100, 10, 0, False, False, "keep", "real person"),
        ])
        got = CL.load_existing_verdicts("2018Q1")
        assert set(got) == {"a", "b"}
        assert got["a"]["verdict"] == "bot"
        assert got["a"]["notes"] == "obvious spam"

    def test_missing_file_returns_empty(self, dirs):
        _, logs, _ = dirs
        assert CL.load_existing_verdicts("2099Q1") == {}


class TestVerdictApplication:
    def _clean_fixture(self, tmp_path, monkeypatch, dirs):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(C, "DATA_RAW", raw_dir)
        rows = ([("spammer", "s1", 0, 0)] * 30 +
                [("realperson", "s1", 0, 0)] * 30)
        pd.DataFrame(rows, columns=["author_h", "subreddit", "created_utc",
                                    "is_mod"]).to_parquet(raw_dir / "2018Q1.parquet")
        return duckdb.connect()

    def test_bot_verdict_actually_removes_rows(self, dirs, tmp_path,
                                                monkeypatch):
        _, logs, clean_dir = dirs
        con = self._clean_fixture(tmp_path, monkeypatch, dirs)
        CL.clean_quarter(con, "2018Q1", C.RunConfig(min_comments=1,
                                                    min_subs=1))
        before = con.execute(
            f"SELECT count(*) FROM '{(clean_dir / '2018Q1.parquet').as_posix()}'"
        ).fetchone()[0]
        assert before == 60

        # A human marks the account as a bot, exactly as the stage requires.
        _write_review(logs / "manual_review_2018Q1.csv", [
            ("spammer", 30, 1, 0, False, False, "bot", ""),
        ])
        prior = CL.load_existing_verdicts("2018Q1")
        assert prior, "verdict was not loaded; the stage would be a no-op"
        removed = CL.apply_manual_verdicts(
            con, clean_dir / "2018Q1.parquet", "2018Q1", prior)
        assert removed == 30
        after = con.execute(
            f"SELECT count(DISTINCT author_h) FROM "
            f"'{(clean_dir / '2018Q1.parquet').as_posix()}'"
        ).fetchone()[0]
        assert after == 1

    def test_keep_verdict_removes_nothing(self, dirs, tmp_path, monkeypatch):
        _, logs, clean_dir = dirs
        con = self._clean_fixture(tmp_path, monkeypatch, dirs)
        CL.clean_quarter(con, "2018Q1", C.RunConfig(min_comments=1,
                                                    min_subs=1))
        _write_review(logs / "manual_review_2018Q1.csv", [
            ("spammer", 30, 1, 0, False, False, "keep", ""),
        ])
        prior = CL.load_existing_verdicts("2018Q1")
        assert CL.apply_manual_verdicts(
            con, clean_dir / "2018Q1.parquet", "2018Q1", prior) == 0


class TestVerdictCarryOver:
    def test_blank_review_stays_blank_on_rewrite(self, dirs):
        """The corruption round-trip: blank -> "nan" -> NaN -> "nan" forever.
        A rewrite must leave unreviewed rows empty."""
        _, logs, _ = dirs
        _write_review(logs / "manual_review_2018Q1.csv", [
            ("a", 100, 10, 0, False, False, float("nan"), None),
        ])
        prior = CL.load_existing_verdicts("2018Q1")
        assert prior == {}
        cands = pd.DataFrame({"author_h": ["a"], "n_comments": [100],
                              "n_subs": [10], "ever_mod": [0]})
        CL.write_manual_review_csv("2018Q1", cands, prior)
        back = pd.read_csv(logs / "manual_review_2018Q1.csv")
        assert back["verdict"].isna().all()

    def test_real_verdict_is_carried_over(self, dirs):
        _, logs, _ = dirs
        _write_review(logs / "manual_review_2018Q1.csv", [
            ("a", 100, 10, 0, False, False, "bot", "spam"),
        ])
        prior = CL.load_existing_verdicts("2018Q1")
        cands = pd.DataFrame({"author_h": ["a", "b"], "n_comments": [100, 5],
                              "n_subs": [10, 2], "ever_mod": [0, 0]})
        CL.write_manual_review_csv("2018Q1", cands, prior)
        back = pd.read_csv(logs / "manual_review_2018Q1.csv")
        assert back.loc[back.author_h == "a", "verdict"].item() == "bot"
        assert pd.isna(back.loc[back.author_h == "b", "verdict"].item())
