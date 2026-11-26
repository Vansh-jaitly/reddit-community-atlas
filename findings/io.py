"""Readers over the local stores (DuckDB), returning pandas frames. Nothing here writes to the repository."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import pandas as pd

from . import config as F


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC';")
    con.execute("SET memory_limit='3GB';")   # the fetch and the scorer may be running beside a build
    return con


def available_months(raw_text: Path | None = None) -> list[str]:
    d = raw_text or F.RAW_TEXT
    return sorted(p.stem for p in d.glob("20??-??.parquet"))


def _files(months: list[str] | None, raw_text: Path | None = None) -> str | None:
    """DuckDB list literal of the monthly files that exist, or None when none of the requested months is stored."""
    d = raw_text or F.RAW_TEXT
    ms = months or available_months(d)
    have = [f"'{(d / (m + '.parquet')).as_posix()}'" for m in ms if (d / (m + ".parquet")).exists()]
    return "[" + ",".join(have) + "]" if have else None


def utc_day(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def day_bounds(start: str, end: str) -> tuple[int, int]:
    s = int(dt.datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
    e = int(dt.datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()) + 86399
    return s, e


def months_covering(start: str, end: str) -> list[str]:
    return [m for m in F.MONTHS if start[:7] <= m <= end[:7]]


def comments(subs: list[str], start: str, end: str, columns: list[str] | None = None, with_text: bool = False,
             raw_text: Path | None = None) -> pd.DataFrame:
    """Comments of `subs` between two UTC dates (inclusive), from the text/structure store."""
    cols = columns or ["id", "parent_id", "link_id", "author_h", "subreddit", "created_utc", "score", "is_mod", "flair"] + (["body"] if with_text else [])
    files = _files(months_covering(start, end), raw_text)
    if files is None:
        return pd.DataFrame(columns=cols)
    s, e = day_bounds(start, end)
    sub_sql = ",".join(f"'{x.lower()}'" for x in subs)
    q = f"""SELECT {', '.join(cols)} FROM read_parquet({files})
            WHERE lower(subreddit) IN ({sub_sql}) AND created_utc BETWEEN {s} AND {e}{' AND body IS NOT NULL' if with_text else ''}"""
    df = _con().execute(q).df()
    if "subreddit" in df.columns:
        df["subreddit"] = df["subreddit"].str.lower()
    return df


def daily_counts(subs: list[str], start: str, end: str, raw_text: Path | None = None) -> pd.DataFrame:
    """Comments and distinct commenters per UTC day and subreddit (text/structure store)."""
    files = _files(months_covering(start, end), raw_text)
    if files is None:
        return pd.DataFrame(columns=["subreddit", "day", "comments", "commenters", "replies"])
    s, e = day_bounds(start, end)
    sub_sql = ",".join(f"'{x.lower()}'" for x in subs)
    q = f"""SELECT lower(subreddit) AS subreddit, strftime(to_timestamp(created_utc), '%Y-%m-%d') AS day,
                   count(*) AS comments, count(DISTINCT author_h) AS commenters, sum(CASE WHEN parent_id LIKE 't1_%' THEN 1 ELSE 0 END) AS replies
            FROM read_parquet({files})
            WHERE lower(subreddit) IN ({sub_sql}) AND created_utc BETWEEN {s} AND {e}
            GROUP BY 1, 2 ORDER BY 1, 2"""
    return _con().execute(q).df()


def frame_daily_counts(subs: list[str], start: str, end: str, clean: Path | None = None) -> pd.DataFrame:
    """Comments and commenters per UTC day for any frame subreddit (the 170-subreddit store, no text)."""
    d = clean or F.CLEAN
    s, e = day_bounds(start, end)
    sub_sql = ",".join(f"'{x.lower()}'" for x in subs)
    q = f"""SELECT lower(subreddit) AS subreddit, strftime(to_timestamp(created_utc), '%Y-%m-%d') AS day,
                   count(*) AS comments, count(DISTINCT author_h) AS commenters
            FROM read_parquet('{(d / '*.parquet').as_posix()}')
            WHERE lower(subreddit) IN ({sub_sql}) AND created_utc BETWEEN {s} AND {e}
            GROUP BY 1, 2 ORDER BY 1, 2"""
    return _con().execute(q).df()


def frame_daily_all(start: str, end: str, clean: Path | None = None) -> pd.DataFrame:
    """Comments per UTC day for every frame subreddit (170 x days): the comparison set for level changes and the integrity screen."""
    d = clean or F.CLEAN
    s, e = day_bounds(start, end)
    q = f"""SELECT lower(subreddit) AS subreddit, strftime(to_timestamp(created_utc), '%Y-%m-%d') AS day, count(*) AS comments
            FROM read_parquet('{(d / '*.parquet').as_posix()}') WHERE created_utc BETWEEN {s} AND {e} GROUP BY 1, 2"""
    return _con().execute(q).df()


def frame_window_totals(start: str, end: str, clean: Path | None = None) -> pd.DataFrame:
    """Comments and commenters per frame subreddit in a window: who took part in an event, across all 170."""
    d = clean or F.CLEAN
    s, e = day_bounds(start, end)
    q = f"""SELECT lower(subreddit) AS subreddit, count(*) AS comments, count(DISTINCT author_h) AS commenters
            FROM read_parquet('{(d / '*.parquet').as_posix()}') WHERE created_utc BETWEEN {s} AND {e} GROUP BY 1"""
    return _con().execute(q).df()


def month_manifest(raw_text: Path | None = None) -> dict:
    import json
    p = (raw_text or F.RAW_TEXT) / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
