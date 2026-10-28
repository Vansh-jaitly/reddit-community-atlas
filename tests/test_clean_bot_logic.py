"""Regression tests for the bot filter in clean.py.

The hard-bot rule is documented as requiring BOTH extreme volume AND extreme
breadth, with either signal alone only routing an account to manual review.
The SQL used to filter on volume alone, which contradicted that rule and --
for this study specifically -- deleted every prolific account regardless of
breadth. The most active cross-community users are exactly the brokers the
project measures, so volume-only deletion silently removed the study's central
population.
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


def _make_raw(path: Path, rows) -> Path:
    df = pd.DataFrame(rows, columns=["author_h", "subreddit", "created_utc",
                                     "is_mod"])
    df.to_parquet(path)
    return path


@pytest.fixture()
def cfg_and_con(tmp_path, monkeypatch):
    """A RunConfig whose data dirs point at a tmp dir, plus a DuckDB handle."""
    raw = tmp_path / "raw"
    clean_dir = tmp_path / "clean"
    logs = tmp_path / "logs"
    cache = tmp_path / "cache"
    for d in (raw, clean_dir, logs, cache):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(C, "DATA_RAW", raw)
    monkeypatch.setattr(C, "DATA_CLEAN", clean_dir)
    monkeypatch.setattr(C, "DATA_LOGS", logs)
    monkeypatch.setattr(C, "DATA_CACHE", cache)
    cfg = C.RunConfig(min_comments=1, min_subs=1)
    return cfg, duckdb.connect(), raw, clean_dir


class TestBreadthCutoff:
    def test_scales_with_frame_size(self):
        assert CL.breadth_hard_cutoff(100) == 50
        assert CL.breadth_hard_cutoff(170) == 85
        assert CL.breadth_hard_cutoff(10) == 5

    def test_is_strictly_below_frame_size(self):
        for n in (10, 36, 100, 150, 170, 500):
            assert 0 < CL.breadth_hard_cutoff(n) < n

    def test_rejects_degenerate_fraction(self):
        with pytest.raises(ValueError):
            CL.breadth_hard_cutoff(1)


class TestHardBotRemoval:
    """Volume alone must never delete an account."""

    def _run(self, tmp_path, monkeypatch, users):
        raw_dir = tmp_path / "raw"
        clean_dir = tmp_path / "clean"
        for d in (raw_dir, clean_dir, tmp_path / "logs", tmp_path / "cache"):
            d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(C, "DATA_RAW", raw_dir)
        monkeypatch.setattr(C, "DATA_CLEAN", clean_dir)
        monkeypatch.setattr(C, "DATA_LOGS", tmp_path / "logs")
        monkeypatch.setattr(C, "DATA_CACHE", tmp_path / "cache")
        raw = _make_raw(raw_dir / "2018Q1.parquet", users)
        con = duckdb.connect()
        cfg = C.RunConfig(min_comments=1, min_subs=1)
        rep = CL.clean_quarter(con, "2018Q1", cfg)
        out = con.execute(
            f"SELECT DISTINCT author_h FROM '{(clean_dir / '2018Q1.parquet').as_posix()}'"
        ).df().author_h.tolist()
        return set(out), rep

    def test_prolific_but_narrow_account_survives(self, tmp_path, monkeypatch):
        """The regression: 2,500 comments in ONE subreddit is not a bot, and is
        exactly the profile of a dedicated power user."""
        vol = CL.BOT_VOLUME_HARD_CUTOFF + 500
        users = [(f"prolific_narrow", "hobby_sub", 0, 0)] * vol
        kept, rep = self._run(tmp_path, monkeypatch, users)
        assert "prolific_narrow" in kept, (
            "high volume with low breadth was deleted; the broker population "
            "is being silently removed")
        assert rep["hard_bots_removed"] == 0

    def test_high_volume_high_breadth_account_removed(self, tmp_path,
                                                      monkeypatch):
        vol = CL.BOT_VOLUME_HARD_CUTOFF + 500
        subs = [f"sub{i}" for i in range(200)]
        users = []
        for i in range(vol):
            users.append(("spammer", subs[i % len(subs)], 0, 0))
        kept, rep = self._run(tmp_path, monkeypatch, users)
        assert "spammer" not in kept
        assert rep["hard_bots_removed"] == 1

    def test_broad_but_quiet_account_survives(self, tmp_path, monkeypatch):
        subs = [f"sub{i}" for i in range(200)]
        users = [("tourist", s, 0, 0) for s in subs]
        kept, rep = self._run(tmp_path, monkeypatch, users)
        assert "tourist" in kept, "low volume with high breadth was deleted"
        assert rep["hard_bots_removed"] == 0

    def test_min_activity_thresholds_still_apply(self, tmp_path, monkeypatch):
        users = [("driveby", "s1", 0, 0)] * 1
        raw_dir = tmp_path / "raw"
        clean_dir = tmp_path / "clean"
        for d in (raw_dir, clean_dir, tmp_path / "logs", tmp_path / "cache"):
            d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(C, "DATA_RAW", raw_dir)
        monkeypatch.setattr(C, "DATA_CLEAN", clean_dir)
        monkeypatch.setattr(C, "DATA_LOGS", tmp_path / "logs")
        monkeypatch.setattr(C, "DATA_CACHE", tmp_path / "cache")
        _make_raw(raw_dir / "2018Q1.parquet", users)
        con = duckdb.connect()
        CL.clean_quarter(con, "2018Q1", C.RunConfig(min_comments=5, min_subs=1))
        out = con.execute(
            f"SELECT count(*) FROM '{(clean_dir / '2018Q1.parquet').as_posix()}'"
        ).fetchone()[0]
        assert out == 0
