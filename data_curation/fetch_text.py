"""
fetch_text.py
=============
Targeted second pass over the same Arctic Shift source as fetch.py, for the
Findings section: comment TEXT and REPLY STRUCTURE for a small set of
subreddits, one Parquet file per month in data/raw_text/.

WHY A SECOND FETCH:
    fetch.py keeps only (author_h, subreddit, created_utc, is_mod) for all 170
    frame subreddits -- enough for shared-audience networks, useless for
    sentiment (no text) or interaction networks (no parent_id/link_id).
    Re-fetching everything with text would be ~210M rows; instead this script
    pulls text for ~11 subreddits and reply structure for ~12 more.

WHAT GETS KEPT (same privacy stance as fetch.py, with one extension):
    id, parent_id, link_id        reply structure (needed for interaction networks)
    author_h                      salted SHA-256 prefix, same salt as fetch.py so
                                  the two datasets can be joined; NULL for [deleted]
    subreddit, created_utc, score, is_mod, flair (author_flair_text)
    body                          ONLY for TEXT_SUBS; NULL for everything else
    Raw usernames never reach disk. Comment text is public but is kept LOCAL
    ONLY (data/raw_text/ is gitignored); the Findings builders publish
    aggregates and anonymised networks, never text or author hashes.

DESIGN:
    Same resilient batch design as fetch.py (small shard batches, staging
    DuckDB table, progress checkpoint after every batch, resumable). Shared
    helpers are imported from fetch.py rather than copied.

USAGE:
    python fetch_text.py                              # Oct 2017 - Sep 2018
    python fetch_text.py --start 2018 4 --end 2018 5  # a sub-window
    python fetch_text.py --max-shards 2               # TEST MODE (isolated output)
    python fetch_text.py --force                      # wipe progress + staging
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import duckdb

import config as C
from fetch import SHARD_BATCH_SIZE, month_range, probe_shard_count, with_retries

log = logging.getLogger("fetch_text")

# Subreddits whose comment text is kept (event stories + debate communities that
# are candidates for the focused network). Lower-case, matched case-insensitively.
TEXT_SUBS = [
    # Avengers: Infinity War (US release 27 Apr 2018)
    "marvelstudios", "marvel",
    # the 2018 crypto decline
    "bitcoin", "cryptocurrency", "ethereum", "dogecoin", "bitcoinbeginners",
    # debate communities (candidate focused networks; flair = self-declared position)
    "capitalismvsocialism", "purplepilldebate", "australianpolitics", "thewallstreet",
]
# Reply structure only (no body): remaining focused-network candidates and context.
STRUCT_SUBS = [
    "changemyview", "canadapolitics", "custommagic", "kpop", "askphilosophy", "askhistorians",
    "medicalschool", "rust", "chess", "newsokunomoral", "comics",
]
# Large context subreddits, structure only, restricted to a window (UTC month strings, inclusive).
WINDOWED_STRUCT_SUBS = {"movies": ("2018-03", "2018-06")}

OUT_DIR = C.ROOT / "data" / "raw_text"
PROGRESS_FILE = C.DATA_CACHE / "fetch_text_progress.json"
STAGING_DB = C.DATA_CACHE / "staging_text.duckdb"
TEST_OUT_DIR = C.ROOT / "data" / "raw_text_TEST"
TEST_PROGRESS_FILE = C.DATA_CACHE / "fetch_text_progress_TEST.json"
TEST_STAGING_DB = C.DATA_CACHE / "staging_text_TEST.duckdb"

DEFAULT_START, DEFAULT_END = (2017, 10), (2018, 9)


def _sql_list(names) -> str:
    return ",".join(f"'{n.strip().lower()}'" for n in names)


def _month_bounds_utc(ym: str) -> tuple[int, int]:
    import calendar
    import datetime as dt
    y, m = int(ym[:4]), int(ym[5:7])
    start = int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp())
    end = int(dt.datetime(y, m, calendar.monthrange(y, m)[1], 23, 59, 59, tzinfo=dt.timezone.utc).timestamp())
    return start, end


def batch_sql(paths: list[str], salt: str) -> str:
    """Filter + hash + column policy for one batch of shards."""
    file_list = "['" + "','".join(paths) + "']"
    windowed = " OR ".join(
        f"(lower(subreddit) = '{s}' AND created_utc BETWEEN {_month_bounds_utc(a)[0]} AND {_month_bounds_utc(b)[1]})"
        for s, (a, b) in WINDOWED_STRUCT_SUBS.items()
    ) or "FALSE"
    return f"""
        SELECT
            id, parent_id, link_id,
            CASE WHEN author IS NULL OR author IN ('[deleted]', 'None') THEN NULL
                 ELSE substr(sha256(concat('{salt}', lower(author))), 1, 16) END AS author_h,
            subreddit, created_utc, score,
            CASE WHEN distinguished = 'moderator' THEN 1 ELSE 0 END AS is_mod,
            author_flair_text AS flair,
            CASE WHEN lower(subreddit) IN ({_sql_list(TEXT_SUBS)}) THEN body ELSE NULL END AS body,
            body_length
        FROM read_parquet({file_list})
        WHERE (lower(subreddit) IN ({_sql_list(TEXT_SUBS + STRUCT_SUBS)}) OR {windowed})
          AND coalesce(author, '') <> 'AutoModerator'
    """


def ensure_table(con: duckdb.DuckDBPyConnection, ym: str) -> str:
    table = f"t_{ym.replace('-', '_')}"
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id VARCHAR, parent_id VARCHAR, link_id VARCHAR, author_h VARCHAR, subreddit VARCHAR,
            created_utc BIGINT, score BIGINT, is_mod TINYINT, flair VARCHAR, body VARCHAR, body_length BIGINT
        )
    """)
    return table


def fetch_month(con, year: int, month: int, salt: str, progress: dict, out_dir, progress_file, max_shards=None) -> dict:
    ym = f"{year}-{month:02d}"
    out_path = out_dir / f"{ym}.parquet"
    p = progress.setdefault(ym, {"done_batches": [], "status": "in_progress"})
    try:
        n_shards = with_retries(probe_shard_count, con, year, month, what=f"probe shard count {ym}")
    except Exception:
        p["status"] = "no_data"
        return p
    if n_shards == 0:
        log.info("  %s: no data on source", ym)
        p["status"] = "no_data"
        return p
    if max_shards is not None:
        n_shards = min(n_shards, max_shards)
    batch_size = min(SHARD_BATCH_SIZE, n_shards)
    table = ensure_table(con, ym)
    log.info("  %s: %d shards, batches of %d", ym, n_shards, batch_size)
    failed = []
    for batch_start in range(0, n_shards, batch_size):
        batch_id = f"{ym}:{batch_start}"
        if batch_id in p["done_batches"]:
            continue
        paths = [f"{C.HF_BASE}/{year}/{month:02d}/{i:03d}.parquet" for i in range(batch_start, min(batch_start + batch_size, n_shards))]
        sql = batch_sql(paths, salt)
        try:
            with_retries(lambda: con.execute(f"INSERT INTO {table} {sql}"), what=f"insert batch {batch_id}")
            p["done_batches"].append(batch_id)
            progress_file.write_text(json.dumps(progress, indent=2))
        except Exception as e:   # noqa: BLE001 - logged and visible in the coverage record
            log.error("  batch %s permanently failed, skipping: %s", batch_id, e)
            failed.append(batch_id)
        if (batch_start // batch_size) % 4 == 0:
            n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            log.info("    progress: %d/%d shards, %s rows staged", min(batch_start + batch_size, n_shards), n_shards, f"{n:,}")
    rows = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    with_text = con.execute(f"SELECT count(*) FROM {table} WHERE body IS NOT NULL").fetchone()[0]
    con.execute(f"COPY (SELECT * FROM {table}) TO '{out_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.execute(f"DROP TABLE {table}")
    p.update({"status": "partial" if failed else "complete", "rows": rows, "rows_with_text": with_text,
              "failed_batches": failed, "n_shards": n_shards})
    log.info("%s: %s rows (%s with text) -> %s (%s)", ym, f"{rows:,}", f"{with_text:,}", out_path.name, p["status"])
    return p


def run(start, end, resume=True, max_shards=None) -> dict:
    test_mode = max_shards is not None
    out_dir = TEST_OUT_DIR if test_mode else OUT_DIR
    progress_file = TEST_PROGRESS_FILE if test_mode else PROGRESS_FILE
    staging_db = TEST_STAGING_DB if test_mode else STAGING_DB
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = C.RunConfig(start=tuple(start), end=tuple(end), max_shards_per_month=max_shards)
    if not test_mode:
        C.require_real_salt(cfg)
    else:
        log.warning("TEST MODE: %d shards per month, output isolated in %s", max_shards, out_dir.name)
    if not resume:
        for f in (progress_file, staging_db):
            if f.exists():
                f.unlink()
    con = duckdb.connect(str(staging_db))
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET preserve_insertion_order=false;")
    progress = json.loads(progress_file.read_text()) if progress_file.exists() else {}
    log.info("Text/structure fetch: %d text subreddits, %d structure-only, %d windowed; months %s..%s",
             len(TEXT_SUBS), len(STRUCT_SUBS), len(WINDOWED_STRUCT_SUBS), start, end)
    for y, m in month_range(tuple(start), tuple(end)):
        ym = f"{y}-{m:02d}"
        if progress.get(ym, {}).get("status") == "complete" and (out_dir / f"{ym}.parquet").exists():
            log.info("%s: already complete -- skipping", ym)
            continue
        fetch_month(con, y, m, cfg.salt, progress, out_dir, progress_file, max_shards)
        progress_file.write_text(json.dumps(progress, indent=2))
    con.close()
    if not test_mode:
        manifest = {ym: {k: v for k, v in p.items() if k != "done_batches"} for ym, p in sorted(progress.items())}
        (out_dir / "manifest.json").write_text(json.dumps({"text_subreddits": TEXT_SUBS, "structure_subreddits": STRUCT_SUBS,
                                                           "windowed_structure": WINDOWED_STRUCT_SUBS, "months": manifest}, indent=2))
    return progress


def parse_args():
    ap = argparse.ArgumentParser(description="Fetch comment text + reply structure for the Findings subreddits.")
    ap.add_argument("--start", nargs=2, type=int, metavar=("YEAR", "MONTH"), default=list(DEFAULT_START))
    ap.add_argument("--end", nargs=2, type=int, metavar=("YEAR", "MONTH"), default=list(DEFAULT_END))
    ap.add_argument("--force", action="store_true", help="wipe progress + staging and start over")
    ap.add_argument("--max-shards", type=int, default=None, metavar="N", help="TEST MODE: cap shards per month")
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                        handlers=[logging.FileHandler(C.LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
    a = parse_args()
    prog = run(a.start, a.end, resume=not a.force, max_shards=a.max_shards)
    done = sum(1 for p in prog.values() if p.get("status") == "complete")
    log.info("DONE: %d months complete, %d partial/missing", done, len(prog) - done)
