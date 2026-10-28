"""
clean.py
========
Takes the raw quarterly Parquet files in data/raw/ and produces cleaned
versions in data/clean/, applying:
  1. Username-pattern bot filtering (fast, no data needed beyond the hash...
     BUT this stage runs on author_h, which is already hashed -- see note below).
  2. Low-activity filtering (drive-by accounts within the quarter).
  3. A manual-review candidate list for the top-N most cross-community users,
     since a human still has to eyeball these (Objective O3 / the bot cascade's
     mandatory "Stage 4: manual review of top 200" step from the synopsis).

IMPORTANT LIMITATION -- READ THIS BEFORE EDITING:
    Because fetch.py hashes usernames AT EXTRACTION TIME (by design, for
    privacy), username-PATTERN bot detection (e.g. matching "*bot", "*_bot")
    CANNOT run in this script -- the raw username no longer exists anywhere
    in this pipeline once fetch.py has run. Two username-based filters
    (AutoModerator, "[deleted]", "None") are therefore applied INSIDE
    fetch.py's SQL query, before hashing, not here.
    This script's job is everything that CAN be computed after hashing:
    behavioural bot signals (posting volume/frequency, no diurnal variation,
    cross-subreddit spam pattern) and activity thresholds. If you need
    additional username-pattern rules, they must be added to fetch.py's
    KNOWN_BOT_NAMES / KNOWN_BOT_SUFFIXES in config.py and re-run from raw.

BEHAVIOURAL BOT SIGNALS IMPLEMENTED HERE:
    - Posting volume: accounts posting above a very high per-quarter comment
      count are flagged (bots often post thousands of times; humans rarely do).
    - Subreddit breadth: accounts posting in an implausibly large number of
      distinct subreddits are flagged (many bots, e.g. link-fixers or
      cross-posters, appear everywhere). This deliberately overlaps with what
      would otherwise look like a "broker" -- which is exactly why catching it
      here matters. An unfiltered bot would appear as your #1 broker.
    - These flags do NOT auto-delete anyone. They populate a manual review
      candidate CSV (data/logs/manual_review_candidates.csv) matching the
      synopsis's "Stage 4: manual review of top 200" requirement, since only
      a human can distinguish a real cross-community power-user from a bot at
      this stage. Auto-removal only happens for the volume outliers set by
      BOT_VOLUME_HARD_CUTOFF, which is set deliberately extreme (only catches
      near-certain bots) to avoid discarding real brokers.

ERROR HANDLING:
    Each quarter is processed independently; if one quarter's raw file is
    missing or corrupt, it is logged and skipped, not fatal to the batch.

USAGE:
    python clean.py                 # clean every quarter found in data/raw/
    python clean.py --quarter 2018Q1   # clean just one (useful for testing)
"""

from __future__ import annotations
import argparse
import csv
import logging
import sys

import duckdb
import pandas as pd

import config as C

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(C.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("clean")

# ------------------------------------------------------------------------
# Bot thresholds
# ------------------------------------------------------------------------
# Deliberately extreme thresholds -- these only catch near-certain bots
# automatically. Anything less extreme goes to manual review instead, because
# a real cross-community broker (the thing this whole project is looking for)
# can legitimately have unusual volume/breadth, and auto-deleting them would
# quietly destroy the signal the project exists to measure.
#
# BREADTH IS FRAME-RELATIVE, NOT ABSOLUTE:
#   This used to be BOT_BREADTH_HARD_CUTOFF = 40 with the comment "the frame
#   only has ~36 subreddits". The frame is now 150 subreddits, so a fixed 40
#   is only 27% of the frame and is trivially reached by an ordinary active
#   user -- and by exactly the power users this project is trying to find. A
#   hard cutoff calibrated to an older frame size is a silent data-loss bug.
#   It is now a FRACTION of the configured frame instead, so it keeps its
#   meaning if the frame changes again.
BOT_VOLUME_HARD_CUTOFF = 2000     # comments in a single quarter, single account
BOT_BREADTH_FRACTION = 0.5        # distinct subreddits as a share of the frame

# A hard deletion requires BOTH signals. The previous rule was an OR, which
# meant a merely-broad account could be auto-deleted with no volume evidence --
# contrary to the intent stated in this file's own docstring.
# Accounts that trip EITHER signal alone go to manual review, not deletion.

MANUAL_REVIEW_TOP_N = 200         # matches the synopsis's Stage-4 requirement

VERDICT_REMOVE = {"bot", "spammer", "remove"}


def breadth_hard_cutoff(frame_size: int) -> int:
    """Absolute breadth cutoff derived from the frame size.

    Raises if the frame is too small for the fraction to mean anything: a
    cutoff at or above the frame size would make every account look maximally
    broad, which silently turns the bot rule into a volume-only rule -- exactly
    the failure this cutoff exists to prevent.
    """
    if frame_size < 4:
        raise ValueError(
            f"frame_size={frame_size} is too small for a "
            f"{BOT_BREADTH_FRACTION:.0%} breadth cutoff")
    cutoff = max(2, int(round(frame_size * BOT_BREADTH_FRACTION)))
    if cutoff >= frame_size:
        raise ValueError(
            f"breadth cutoff ({cutoff}) is not below the frame size "
            f"({frame_size}); lower BOT_BREADTH_FRACTION")
    return cutoff


def load_existing_verdicts(quarter: str) -> dict[str, dict]:
    """Read any human verdicts already recorded for this quarter.

    Manual review is a required stage whose output must be CONSUMED, not just
    displayed. The previous version overwrote the verdict column on every run,
    so a re-run silently destroyed completed human review work.
    """
    path = C.DATA_LOGS / f"manual_review_{quarter}.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
    except Exception as e:
        log.warning("  %s: unreadable, treating as no prior review (%s)", path.name, e)
        return {}
    if "author_h" not in df.columns:
        return {}
    out = {}
    for _, row in df.iterrows():
        raw_verdict = row.get("verdict", "")
        # `raw or ""` is NOT enough here: pandas fills a blank verdict column
        # with float('nan'), and bool(nan) is True, so every unreviewed row
        # became a pseudo-verdict of "nan". That inflated the reported verdict
        # count and re-wrote the literal string "nan" into the CSV, which
        # re-parses as NaN and made the corruption self-perpetuating.
        if raw_verdict is None or pd.isna(raw_verdict):
            continue
        verdict = str(raw_verdict).strip().lower()
        if not verdict or verdict == "nan":
            continue
        out[str(row["author_h"])] = {
            "verdict": verdict,
            "notes": "" if pd.isna(row.get("notes", "")) else str(row["notes"]),
        }
    if out:
        log.info("  %s: reusing %d existing manual verdict(s)", path.name, len(out))
    return out


def find_raw_quarters() -> list[str]:
    return sorted(p.stem for p in C.DATA_RAW.glob("*.parquet"))


def clean_quarter(con: duckdb.DuckDBPyConnection, quarter: str, cfg: C.RunConfig) -> dict:
    raw_path = C.DATA_RAW / f"{quarter}.parquet"
    clean_path = C.DATA_CLEAN / f"{quarter}.parquet"

    if not raw_path.exists():
        log.error("%s: raw file missing, skipping", quarter)
        return {"quarter": quarter, "status": "missing_raw"}

    try:
        n_raw = con.execute(f"SELECT count(*) FROM '{raw_path.as_posix()}'").fetchone()[0]
    except Exception as e:
        log.error("%s: raw file unreadable/corrupt, skipping (%s)", quarter, e)
        return {"quarter": quarter, "status": "corrupt_raw"}

    # ---- Step 1: per-user aggregates for this quarter ----
    # (used for both the activity-threshold filter and the manual-review list)
    agg_sql = f"""
        WITH per_user AS (
            SELECT
                author_h,
                count(*) AS n_comments,
                count(DISTINCT subreddit) AS n_subs,
                max(is_mod) AS ever_mod
            FROM '{raw_path.as_posix()}'
            GROUP BY author_h
        )
        SELECT * FROM per_user
    """
    agg = con.execute(agg_sql).fetchdf()

    if agg.empty:
        log.warning("%s: 0 users after aggregation, skipping export", quarter)
        return {"quarter": quarter, "status": "empty"}

    # ---- Step 2: behavioural bot flags ----
    # Hard deletion needs BOTH extreme volume AND extreme breadth. Either
    # signal on its own only routes an account to manual review.
    n_frame = cfg.frame_size or len(cfg.frame)
    breadth_cutoff = breadth_hard_cutoff(n_frame)

    high_volume = agg["n_comments"] >= BOT_VOLUME_HARD_CUTOFF
    high_breadth = agg["n_subs"] >= breadth_cutoff
    hard_bots = agg[high_volume & high_breadth]
    n_hard_bot = len(hard_bots)

    # ---- Step 3: manual review candidate list ----
    # Top N by subreddit breadth = exactly the users who WOULD be identified
    # as brokers downstream. These are the highest-value accounts to manually
    # verify are real people, per the synopsis's Stage-4 requirement.
    review_candidates = agg.sort_values("n_subs", ascending=False).head(MANUAL_REVIEW_TOP_N)
    review_candidates = review_candidates.assign(
        flagged_high_volume=high_volume[review_candidates.index].values,
        flagged_high_breadth=high_breadth[review_candidates.index].values,
    )
    prior_verdicts = load_existing_verdicts(quarter)
    write_manual_review_csv(quarter, review_candidates, prior_verdicts)

    # ---- Step 4: apply filters and export ----
    # Hard bot removal requires BOTH extreme volume AND extreme breadth, which
    # is what hard_bots above counts. This used to filter on volume alone
    # (`n_comments < BOT_VOLUME_HARD_CUTOFF`), which contradicted the stated
    # rule above and, worse for this study, silently deleted every prolific
    # account regardless of breadth. The most active cross-community users are
    # exactly the brokers the project measures, so volume-only deletion removed
    # the study's central population. Either signal alone must survive to
    # manual review.
    keep_ids_sql = f"""
        SELECT author_h FROM (
            SELECT author_h, count(*) AS n_comments, count(DISTINCT subreddit) AS n_subs
            FROM '{raw_path.as_posix()}' GROUP BY author_h
        )
        WHERE n_comments >= {cfg.min_comments}
          AND n_subs >= {cfg.min_subs}
          AND NOT (n_comments >= {BOT_VOLUME_HARD_CUTOFF}
                   AND n_subs >= {breadth_cutoff})
    """
    con.execute(f"""
        COPY (
            SELECT r.*
            FROM '{raw_path.as_posix()}' r
            INNER JOIN ({keep_ids_sql}) k USING (author_h)
        ) TO '{clean_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    n_before_verdicts = con.execute(
        f"SELECT count(*) FROM '{clean_path.as_posix()}'"
    ).fetchone()[0]
    n_removed_by_verdict = apply_manual_verdicts(
        con, clean_path, quarter, prior_verdicts
    )

    n_clean = con.execute(
        f"SELECT count(*) FROM '{clean_path.as_posix()}'"
    ).fetchone()[0]
    n_users_raw = len(agg)
    n_users_clean = con.execute(
        f"SELECT count(DISTINCT author_h) FROM '{clean_path.as_posix()}'"
    ).fetchone()[0]

    log.info(
        "%s: %s -> %s rows (%.1f%% kept) | %d -> %d users | %d hard-bot removed | "
        "%d flagged for manual review | %d rows removed by manual verdict%s",
        quarter, f"{n_raw:,}", f"{n_clean:,}", 100 * n_clean / n_raw if n_raw else 0,
        n_users_raw, n_users_clean, n_hard_bot, len(review_candidates),
        n_removed_by_verdict,
        " (no verdicts recorded yet)" if not prior_verdicts else "",
    )
    return {
        "quarter": quarter, "status": "ok",
        "rows_raw": n_raw, "rows_clean": n_clean,
        "users_raw": n_users_raw, "users_clean": n_users_clean,
        "hard_bots_removed": n_hard_bot,
        "manual_review_flagged": len(review_candidates),
        "manual_verdicts_applied": len(prior_verdicts),
        "rows_removed_by_verdict": n_removed_by_verdict,
        "breadth_hard_cutoff": breadth_cutoff,
        "frame_size": n_frame,
    }


def apply_manual_verdicts(
    con: duckdb.DuckDBPyConnection,
    clean_path,
    quarter: str,
    prior_verdicts: dict[str, dict],
) -> int:
    """Remove rows for accounts a human marked bot/spammer.

    Without this, the manual review stage produces a CSV that nothing reads:
    the required human check has no effect on the data, which makes the whole
    stage ceremonial. Returns the number of rows removed.
    """
    remove_ids = [
        a for a, v in prior_verdicts.items() if v["verdict"] in VERDICT_REMOVE
    ]
    if not remove_ids:
        return 0

    before = con.execute(
        f"SELECT count(*) FROM '{clean_path.as_posix()}'"
    ).fetchone()[0]

    con.execute("CREATE OR REPLACE TEMP TABLE _remove_ids (author_h VARCHAR)")
    con.executemany("INSERT INTO _remove_ids VALUES (?)", [(a,) for a in remove_ids])
    con.execute(f"""
        COPY (
            SELECT c.* FROM '{clean_path.as_posix()}' c
            ANTI JOIN _remove_ids r USING (author_h)
        ) TO '{(clean_path.parent / (clean_path.stem + '_tmp.parquet')).as_posix()}'
            (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    tmp = clean_path.parent / (clean_path.stem + "_tmp.parquet")
    tmp.replace(clean_path)

    after = con.execute(
        f"SELECT count(*) FROM '{clean_path.as_posix()}'"
    ).fetchone()[0]
    log.info("  %s: manual verdicts removed %d rows (%d accounts)",
             quarter, before - after, len(remove_ids))
    return before - after


def write_manual_review_csv(quarter: str, candidates, prior_verdicts: dict) -> None:
    """One CSV per quarter, listing the top-N most cross-community accounts
    for a human to eyeball. This is a REQUIRED manual step per the synopsis.

    Existing verdicts and notes are CARRIED OVER for accounts that appear again,
    so re-running clean.py never destroys completed review work. The verdicts
    are then applied to the cleaned data by apply_manual_verdicts().
    """
    path = C.DATA_LOGS / f"manual_review_{quarter}.csv"
    candidates = candidates.copy()
    candidates["verdict"] = ""
    candidates["notes"] = ""
    if prior_verdicts:
        carried = 0
        for i, aid in candidates["author_h"].items():
            prior = prior_verdicts.get(str(aid))
            if prior:
                candidates.at[i, "verdict"] = prior["verdict"]
                candidates.at[i, "notes"] = prior["notes"]
                carried += 1
        if carried:
            log.info("  manual review: carried over %d verdict(s)", carried)
    candidates.to_csv(path, index=False)
    written = (
        candidates["verdict"].fillna("").astype(str).str.strip().str.lower()
    )
    n_done = int((~written.isin(["", "nan"])).sum())
    log.info(
        "  manual review candidates written to %s (%d/%d verdicts recorded)",
        path.name, n_done, len(candidates),
    )


def run(cfg: C.RunConfig, only_quarter: str | None = None) -> list[dict]:
    con = duckdb.connect()  # clean.py needs no network access, pure local SQL
    quarters = [only_quarter] if only_quarter else find_raw_quarters()
    if not quarters:
        log.warning("No raw quarters found in %s -- run fetch.py first", C.DATA_RAW)
        return []

    results = []
    for q in quarters:
        try:
            results.append(clean_quarter(con, q, cfg))
        except Exception as e:
            log.error("%s: unexpected error, skipping quarter (%s)", q, e)
            results.append({"quarter": q, "status": "error", "error": str(e)})

    con.close()
    write_cleaning_report(results)
    return results


def write_cleaning_report(results: list[dict]) -> None:
    """Before/after comparison table -- direct deliverable for Objective O3."""
    path = C.DATA_LOGS / "cleaning_report.csv"
    fields = ["quarter", "status", "rows_raw", "rows_clean", "users_raw",
              "users_clean", "hard_bots_removed", "manual_review_flagged"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)
    log.info("Cleaning report written to %s", path)


def parse_args():
    p = argparse.ArgumentParser(description="Clean raw quarterly Reddit data.")
    p.add_argument("--quarter", default=None, help="Clean only this quarter, e.g. 2018Q1")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = C.RunConfig()
    results = run(cfg, only_quarter=args.quarter)
    n_ok = sum(1 for r in results if r.get("status") == "ok")
    log.info("DONE. %d/%d quarters cleaned successfully.", n_ok, len(results))