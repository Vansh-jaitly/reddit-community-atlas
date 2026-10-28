"""
fetch.py
========
Downloads/filters raw Reddit comment data for the sampling frame in config.py,
for every month in the configured window, and writes ONE PARQUET FILE PER
QUARTER to data/raw/.

DATA SOURCE (verified working 26 Aug 2026 -- see DATA_SOURCES_VERIFIED.md):
    Hugging Face dataset "open-index/arctic", queried remotely with DuckDB's
    httpfs extension. No download of the full dataset happens -- DuckDB reads
    only the columns/rows that match our WHERE clause, directly over HTTPS.

WHY DUCKDB INSTEAD OF pandas/requests:
    The source dataset is ~780 GB across the 2018-2022 window. DuckDB's Parquet
    reader supports "predicate + column pushdown" -- it skips row-groups that
    can't match the subreddit filter and never reads unused columns (body
    text, score, etc.) at all. This is what makes filtering feasible without
    ever downloading the raw files. See config.py's top comment for the
    coverage limits of this source (comments stop at 2022-08).

WHY BATCHED, NOT ONE GIANT QUERY PER QUARTER (IMPORTANT -- read this if you're
an agent editing this file):
    An early version of this script issued a single COPY over all ~550 shards
    in a quarter at once. Tested against a real network, that took many
    minutes with ZERO feedback and ZERO resumability -- if shard 400 of 550
    failed, the whole quarter's work was lost and had to restart from zero.
    This version instead:
      1. Splits each month's shards into small batches (SHARD_BATCH_SIZE).
      2. INSERTs each batch into a staging DuckDB table (data/cache/staging.duckdb).
      3. Records which batches succeeded in fetch_progress.json AFTER EACH BATCH.
      4. On restart, already-inserted batches are skipped entirely.
      5. Only once every batch in a quarter is in the staging table does the
         script export that quarter's table to data/raw/<quarter>.parquet.
    This trades a little extra complexity for resilience against exactly the
    kind of flaky/slow connection this was tested against. Do not revert to
    a single-query-per-quarter design without re-testing on a real connection.

WHAT GETS KEPT (privacy-by-design, not an afterthought):
    Only 4 fields survive extraction: author_h (HASHED), subreddit,
    created_utc, is_mod. The raw username and comment text are never written
    to disk -- hashing happens INSIDE the SQL query itself, at the moment of
    extraction, so raw usernames exist only in the remote source, never here.

ERROR HANDLING PHILOSOPHY:
    A single missing/corrupt shard or month should NOT crash the whole run.
    Every network call is retried with exponential backoff; if a batch still
    fails after MAX_RETRIES, it is logged and SKIPPED (not silently dropped --
    it shows up in the coverage report at the end, and in pipeline.log). This
    mirrors the "coverage rate table" requirement in the course's validity
    chapter (Module 6) -- missing data must be visible, never hidden.

USAGE:
    python fetch.py                              # full configured window
    python fetch.py --start 2018 1 --end 2018 3   # quick 1-quarter test
    python fetch.py                               # (default) resumes automatically
    python fetch.py --force                       # wipe staging + progress, start over
"""

from __future__ import annotations
import argparse
import json
import logging
import sys
import time

import duckdb

import config as C

# ------------------------------------------------------------------------
# Logging -- console + file, so an overnight run leaves a full record.
# ------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(C.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("fetch")

PROGRESS_FILE = C.DATA_CACHE / "fetch_progress.json"
STAGING_DB = C.DATA_CACHE / "staging.duckdb"
# TEST MODE gets entirely separate output/progress/staging so a --max-shards
# smoke test can NEVER collide with or be mistaken for real fetched data --
# see run() below, which switches to these when cfg.max_shards_per_month is set.
TEST_RAW_DIR = C.ROOT / "data" / "raw_TEST"
TEST_PROGRESS_FILE = C.DATA_CACHE / "fetch_progress_TEST.json"
TEST_STAGING_DB = C.DATA_CACHE / "staging_TEST.duckdb"

QUARTER_MONTHS = {
    "Q1": (1, 2, 3), "Q2": (4, 5, 6), "Q3": (7, 8, 9), "Q4": (10, 11, 12),
}

# How many shards to pull in a single SQL statement. Smaller = more resilient
# to network drops and more frequent progress feedback; larger = faster when
# the connection is healthy. 15 was chosen empirically after the original
# 500+-shard-per-query design proved too slow to give useful feedback.
SHARD_BATCH_SIZE = 15


# ------------------------------------------------------------------------
# Calendar helpers
# ------------------------------------------------------------------------
def month_range(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    ey, em = end
    while (y, m) <= (ey, em):
        yield (y, m)
        m += 1
        if m > 12:
            m = 1
            y += 1


def month_to_quarter(year: int, month: int) -> str:
    q = {1: "Q1", 2: "Q1", 3: "Q1", 4: "Q2", 5: "Q2", 6: "Q2",
         7: "Q3", 8: "Q3", 9: "Q3", 10: "Q4", 11: "Q4", 12: "Q4"}[month]
    return f"{year}{q}"


def quarters_in_window(start, end) -> list[str]:
    seen = []
    for y, m in month_range(start, end):
        q = month_to_quarter(y, m)
        if q not in seen:
            seen.append(q)
    return seen


# ------------------------------------------------------------------------
# Progress tracking (resumability at the BATCH level, not just quarter level)
# ------------------------------------------------------------------------
def load_progress(progress_file=None) -> dict:
    progress_file = progress_file or PROGRESS_FILE
    if progress_file.exists():
        try:
            return json.loads(progress_file.read_text())
        except json.JSONDecodeError:
            log.warning("progress file corrupt, starting fresh")
    return {}


def save_progress(progress: dict, progress_file=None) -> None:
    progress_file = progress_file or PROGRESS_FILE
    # Written after every batch, not just every quarter, so a crash mid-quarter
    # loses at most one batch (SHARD_BATCH_SIZE shards), not the whole quarter.
    progress_file.write_text(json.dumps(progress, indent=2))


# ------------------------------------------------------------------------
# Retry wrapper -- every network-touching call goes through this.
# ------------------------------------------------------------------------
def with_retries(fn, *args, what: str, **kwargs):
    last_err = None
    for attempt in range(1, C.MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 -- httpfs/duckdb raise generic
            # exceptions for everything from DNS failures to 404s, so we
            # can't safely narrow the except clause further here.
            last_err = e
            delay = C.RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
            log.warning(
                "%s failed (attempt %d/%d): %s -- retrying in %.0fs",
                what, attempt, C.MAX_RETRIES, str(e)[:200], delay,
            )
            time.sleep(delay)
    log.error("%s permanently failed after %d attempts: %s", what, C.MAX_RETRIES, last_err)
    raise last_err


# ------------------------------------------------------------------------
# Core extraction
# ------------------------------------------------------------------------
def probe_shard_count(con: duckdb.DuckDBPyConnection, year: int, month: int) -> int:
    """The HF dataset has no directory-listing API reachable from DuckDB's
    httpfs, so we binary-search the shard count: a read on a missing shard
    fails fast (HTTP 404) without downloading anything, so this is cheap.
    Returns 0 if shard 000 is missing (month absent from the source -- EXPECTED
    for months outside the verified 2018-01..2022-08 comment range)."""
    hi_ceiling = C.MAX_SHARDS_PER_MONTH

    def shard_exists(i: int) -> bool:
        path = f"{C.HF_BASE}/{year}/{month:02d}/{i:03d}.parquet"
        try:
            con.execute(f"SELECT 1 FROM read_parquet('{path}') LIMIT 1")
            return True
        except Exception:
            return False

    if not shard_exists(0):
        return 0
    step, found_hi = 1, 1
    while shard_exists(found_hi) and found_hi < hi_ceiling:
        step *= 2
        found_hi = min(found_hi + step, hi_ceiling)
    lo, hi = found_hi // 2, found_hi
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if shard_exists(mid):
            lo = mid
        else:
            hi = mid
    return lo + 1


def build_frame_filter_sql(frame: dict[str, str]) -> str:
    """Comma-separated lowercased subreddit literals for the frame.

    Reddit names are case-insensitive but the corpus is not case-consistent
    (it stores "Cooking"/"Physics"/"ptsd" where the frame writes
    "cooking"/"physics"/"PTSD"). An exact-match `IN` list therefore silently
    dropped 19 of 150 frame subs -- roughly 6% of frame comment volume -- with
    no error. Both sides are lowercased so casing can never delete data again.
    """
    seen: set[str] = set()
    names: list[str] = []
    for s in frame.keys():
        k = s.strip().replace("'", "").lower()
        if k and k not in seen:
            seen.add(k)
            names.append(k)
    return ",".join(f"'{n}'" for n in names)


def assert_frame_coverage(
    con: duckdb.DuckDBPyConnection, table: str, frame: dict[str, str],
    quarter: str, allowed_missing: set[str] | None = None,
) -> dict:
    """Fail loudly if any frame subreddit produced zero rows.

    Silent data loss is the failure mode this guards against: a subreddit can
    vanish because of a spelling mismatch, a rename, a dead community, or a
    shard that failed to download, and in every case the pipeline would
    otherwise report a "successful" quarter that is quietly missing nodes.
    Reports coverage so the frame can be re-validated over the real window.
    """
    allowed = {a.lower() for a in (allowed_missing or set())}
    observed = {r[0].lower() for r in con.execute(
        f"SELECT DISTINCT subreddit FROM {table}").fetchall()}
    missing = sorted(s for s in (x.lower() for x in frame) if s not in observed)
    unexpected = sorted(observed - {x.lower() for x in frame})

    log.info("[%s] frame coverage: %d/%d subreddits observed",
             quarter, len(observed & {x.lower() for x in frame}), len(frame))
    if unexpected:
        log.warning("[%s] %d non-frame subreddits present (e.g. %s)",
                    quarter, len(unexpected), ", ".join(unexpected[:5]))
    if missing:
        hard = [m for m in missing if m not in allowed]
        soft = [m for m in missing if m in allowed]
        if soft:
            log.warning("[%s] %d documented-unobservable frame subs absent: %s",
                        quarter, len(soft), ", ".join(soft))
        if hard:
            raise RuntimeError(
                f"[{quarter}] {len(hard)} frame subreddits produced no rows: "
                f"{', '.join(hard)}. This is data loss, not an empty quarter. "
                f"Check the name spelling against the corpus, whether the "
                f"community was renamed or shut down, and whether any shard "
                f"failed to download. Fix the frame or the fetch, then rerun."
            )
    return {"observed": len(observed & {x.lower() for x in frame}),
            "frame_size": len(frame),
            "missing": missing}



def batch_extract_sql(paths: list[str], frame_sql: str, salt: str) -> str:
    """The core filter+hash query, applied to one small batch of shards."""
    file_list = "['" + "','".join(paths) + "']"
    return f"""
        SELECT
            substr(sha256(concat('{salt}', lower(author))), 1, 16) AS author_h,
            subreddit,
            created_utc,
            CASE WHEN distinguished = 'moderator' THEN 1 ELSE 0 END AS is_mod
        FROM read_parquet({file_list})
        WHERE lower(subreddit) IN ({frame_sql})
          AND author IS NOT NULL
          AND author NOT IN ('[deleted]', 'AutoModerator', 'None')
    """


def ensure_staging_table(con: duckdb.DuckDBPyConnection, quarter: str) -> str:
    table = f"q_{quarter}"
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            author_h VARCHAR, subreddit VARCHAR, created_utc BIGINT, is_mod TINYINT
        )
    """)
    return table


def fetch_quarter(con: duckdb.DuckDBPyConnection, quarter: str, cfg: C.RunConfig,
                   progress: dict, raw_dir=None, progress_file=None) -> dict:
    """Extract one quarter in small batches, checkpointing after each batch,
    then export the finished staging table to data/raw/<quarter>.parquet.

    IMPORTANT -- months are restricted to the caller's cfg.start/cfg.end window.
    (This used to unconditionally process all 3 months of the quarter -- e.g.
    `--start 2018 1 --end 2018 1` would still silently pull Jan+Feb+Mar,
    because it only touched QUARTER_MONTHS[quarter], ignoring the requested
    end date. Fixed by intersecting with the requested range below. If you
    later widen the window and rerun, months outside the ORIGINAL run that
    are now in range will be picked up correctly, because done_batches is
    keyed per month, not per quarter -- nothing already fetched is repeated.)
    """
    year = int(quarter[:4])
    all_quarter_months = QUARTER_MONTHS[quarter[4:]]
    # Keep only months that both belong to this quarter AND fall inside the
    # caller's requested [cfg.start, cfg.end] window.
    months = [m for m in all_quarter_months if cfg.start <= (year, m) <= cfg.end]
    skipped_by_request = [m for m in all_quarter_months if m not in months]

    out_path = (raw_dir or C.DATA_RAW) / f"{quarter}.parquet"
    frame_sql = build_frame_filter_sql(cfg.frame)
    table = ensure_staging_table(con, quarter)

    q_progress = progress.setdefault(quarter, {
        "done_batches": [], "months_missing": [], "status": "in_progress",
    })
    months_missing = list(q_progress["months_missing"])

    if skipped_by_request:
        log.info(
            "  %s: only fetching %s this run (--start/--end restricts the "
            "other months of this quarter: %s). Rerun with a wider window "
            "later to fill them in -- already-fetched months won't repeat.",
            quarter, [f"{year}-{m:02d}" for m in months],
            [f"{year}-{m:02d}" for m in skipped_by_request],
        )

    for m in months:
        try:
            n_shards = with_retries(
                probe_shard_count, con, year, m,
                what=f"probe shard count {year}-{m:02d}",
            )
        except Exception:
            if f"{year}-{m:02d}" not in months_missing:
                months_missing.append(f"{year}-{m:02d}")
            continue

        if n_shards == 0:
            log.info("  %d-%02d: no data on source (expected outside 2018-01..2022-08)",
                      year, m)
            if f"{year}-{m:02d}" not in months_missing:
                months_missing.append(f"{year}-{m:02d}")
            continue

        # TESTING: cap shard count for a fast smoke test. See config.py's
        # max_shards_per_month docstring -- never set for a real analysis run.
        if cfg.max_shards_per_month is not None:
            n_shards_capped = min(n_shards, cfg.max_shards_per_month)
            if n_shards_capped < n_shards:
                log.info("  %d-%02d: capping to %d/%d shards (max_shards_per_month set -- TEST MODE)",
                          year, m, n_shards_capped, n_shards)
            n_shards = n_shards_capped

        # Batch size also shrinks for tiny caps, so a 2-shard test run
        # actually fetches 2 shards in one go instead of rounding up to a
        # full 15-shard batch.
        batch_size = min(SHARD_BATCH_SIZE, n_shards) if cfg.max_shards_per_month else SHARD_BATCH_SIZE

        log.info("  %d-%02d: %d shards found, in batches of %d",
                  year, m, n_shards, batch_size)

        for batch_start in range(0, n_shards, batch_size):
            batch_id = f"{year}-{m:02d}:{batch_start}"
            if batch_id in q_progress["done_batches"]:
                continue  # already inserted in a previous run -- skip

            batch_end = min(batch_start + batch_size, n_shards)
            paths = [
                f"{C.HF_BASE}/{year}/{m:02d}/{i:03d}.parquet"
                for i in range(batch_start, batch_end)
            ]
            sql = batch_extract_sql(paths, frame_sql, cfg.salt)

            def run_batch():
                con.execute(f"INSERT INTO {table} {sql}")

            try:
                with_retries(run_batch, what=f"insert batch {batch_id}")
                q_progress["done_batches"].append(batch_id)
                # Checkpoint to disk after EVERY batch -- this is the whole
                # point of the batched design: a crash now loses at most
                # SHARD_BATCH_SIZE shards of work, not a whole quarter.
                save_progress(progress, progress_file)
            except Exception as e:
                log.error("  batch %s permanently failed, skipping: %s", batch_id, e)
                # Not fatal to the run -- logged, and reflected in coverage report.

            if (batch_start // batch_size) % 5 == 0:
                n_so_far = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                log.info("    progress: %d/%d shards done this month, %s rows staged so far",
                          batch_end, n_shards, f"{n_so_far:,}")

    q_progress["months_missing"] = months_missing

    row_count = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    if row_count == 0:
        log.warning("%s: NO DATA extracted -- skipping export", quarter)
        q_progress["status"] = "no_data"
        q_progress["rows"] = 0
        return q_progress

    # Refuse to export a quarter that silently lost frame subreddits. This runs
    # BEFORE the COPY so a lossy quarter never reaches disk as "success".
    coverage = assert_frame_coverage(
        con, table, cfg.frame, quarter,
        allowed_missing=getattr(C, "FRAME_UNOBSERVABLE", set()))
    q_progress["frame_coverage"] = coverage

    # Export the finished staging table to the final quarterly Parquet file.
    con.execute(f"""
        COPY (SELECT * FROM {table})
        TO '{out_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    con.execute(f"DROP TABLE {table}")  # free space in the staging db

    # Status reflects BOTH true source gaps (months_missing) AND months
    # deliberately excluded by a narrower --start/--end than the full quarter
    # (skipped_by_request) -- both mean the exported file is not the full
    # quarter, and the coverage report should say so honestly either way.
    q_progress["skipped_by_request"] = [f"{year}-{m:02d}" for m in skipped_by_request]
    if months_missing or skipped_by_request:
        q_progress["status"] = "partial"
    else:
        q_progress["status"] = "complete"
    q_progress["rows"] = row_count
    q_progress["n_shards"] = len(q_progress["done_batches"])
    log.info("%s: %s rows written -> %s (%s)%s",
              quarter, f"{row_count:,}", out_path.name, q_progress["status"],
              " -- restricted by --start/--end, rerun with wider window to complete"
              if skipped_by_request else "")
    return q_progress


# ------------------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------------------
def run(cfg: C.RunConfig, resume: bool = True) -> list[dict]:
    test_mode = cfg.max_shards_per_month is not None
    raw_dir = TEST_RAW_DIR if test_mode else C.DATA_RAW
    progress_file = TEST_PROGRESS_FILE if test_mode else PROGRESS_FILE
    staging_db = TEST_STAGING_DB if test_mode else STAGING_DB
    raw_dir.mkdir(parents=True, exist_ok=True)

    if not test_mode:
        C.require_real_salt(cfg)
    else:
        log.warning(
            "TEST MODE: max_shards_per_month=%d. Output isolated to %s/ "
            "(NOT data/raw/) using a separate progress file and staging db, "
            "so this can never be mistaken for or contaminate real fetched "
            "data. Delete %s/ when done testing.",
            cfg.max_shards_per_month, raw_dir.name, raw_dir.name,
        )

    if not resume:
        for p in (progress_file, staging_db):
            if p.exists():
                p.unlink()
                log.info("Removed %s (--force)", p.name)

    con = duckdb.connect(str(staging_db))
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET preserve_insertion_order=false;")

    progress = load_progress(progress_file)
    quarters = quarters_in_window(cfg.start, cfg.end)
    log.info("Fetching %d quarters: %s .. %s", len(quarters), quarters[0], quarters[-1])
    log.info("Sampling frame: %d subreddits", len(cfg.frame))

    coverage_rows = []
    for quarter in quarters:
        out_path = raw_dir / f"{quarter}.parquet"
        already_done = progress.get(quarter, {}).get("status") in ("complete", "partial")
        if already_done and out_path.exists():
            log.info("%s: already complete -- skipping", quarter)
            coverage_rows.append(progress[quarter])
            continue

        log.info("=== %s ===", quarter)
        stats = fetch_quarter(con, quarter, cfg, progress, raw_dir=raw_dir,
                               progress_file=progress_file)
        save_progress(progress, progress_file)
        coverage_rows.append(stats)

    con.close()
    if not test_mode:
        write_coverage_report(quarters, progress)
    else:
        log.info("TEST MODE run finished -- coverage_report.csv NOT updated "
                  "(test output doesn't belong in the real coverage record).")
    return coverage_rows


def write_coverage_report(quarters: list[str], progress: dict) -> None:
    """Direct deliverable for the validity chapter (Module 6) and for
    Objective O2's 'per-quarter coverage table'."""
    import csv
    path = C.DATA_LOGS / "coverage_report.csv"
    # Record EVERY quarter known to the progress file, not just this run's
    # window: rewriting with only the current window silently drops earlier
    # quarters' coverage rows (observed when Q2-Q3 overwrote Q1's row).
    quarters = sorted(set(quarters) | set(progress))
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["quarter", "status", "rows", "n_shard_batches_done",
                    "months_missing_from_source", "months_skipped_by_request"])
        for quarter in quarters:
            r = progress.get(quarter, {})
            w.writerow([
                quarter, r.get("status", "not_started"), r.get("rows", 0),
                len(r.get("done_batches", [])),
                ";".join(r.get("months_missing", [])),
                ";".join(r.get("skipped_by_request", [])),
            ])
    log.info("Coverage report written to %s", path)


# ------------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Fetch Reddit comment data for the sampling frame.")
    p.add_argument("--start", nargs=2, type=int, metavar=("YEAR", "MONTH"),
                    default=list(C.DEFAULT_START))
    p.add_argument("--end", nargs=2, type=int, metavar=("YEAR", "MONTH"),
                    default=list(C.DEFAULT_END))
    p.add_argument("--force", action="store_true",
                    help="Wipe cached progress + staging db and start over.")
    p.add_argument("--max-shards", type=int, default=None, metavar="N",
                    help="TEST MODE: cap shards fetched per month to N (e.g. 2 for "
                         "a near-instant smoke test). Never use for a real run -- "
                         "the resulting data is real but a tiny non-representative "
                         "slice, and using --force afterward is required before a "
                         "full run reuses the same quarter (see README).")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = C.RunConfig(start=tuple(args.start), end=tuple(args.end),
                       max_shards_per_month=args.max_shards)
    results = run(cfg, resume=not args.force)
    n_ok = sum(1 for r in results if r.get("status") == "complete")
    n_partial = sum(1 for r in results if r.get("status") == "partial")
    n_fail = sum(1 for r in results if r.get("status") == "no_data")
    log.info("DONE. %d complete, %d partial, %d with no data.", n_ok, n_partial, n_fail)
    if n_fail or n_partial:
        log.warning("Some quarters incomplete -- check coverage_report.csv and pipeline.log")