"""
run_pipeline.py
================
One command to run the whole data-curation pipeline end to end:
    fetch (raw extraction)  ->  clean (bot filtering)  ->  summary printed

This file deliberately contains almost no logic of its own -- it just calls
fetch.run() and clean.run() in order and prints a final summary. All the real
work and all the interesting error handling lives in fetch.py and clean.py,
where it's easier to find and reason about independently. If something breaks,
check the log file (data/logs/pipeline.log) and the two CSV reports
(coverage_report.csv, cleaning_report.csv) before this file.

USAGE:
    python run_pipeline.py                       # full configured window
    python run_pipeline.py --start 2018 1 --end 2018 3   # quick test run
    python run_pipeline.py --skip-fetch           # only re-run cleaning
    python run_pipeline.py --force                # wipe fetch cache, start over

AFTER THIS RUNS, START THE DASHBOARD WITH:
    streamlit run dashboard.py
"""

from __future__ import annotations
import argparse
import logging
import sys
import time

import config as C
import fetch
import clean

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(C.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("pipeline")


def parse_args():
    p = argparse.ArgumentParser(description="Run the full fetch -> clean pipeline.")
    p.add_argument("--start", nargs=2, type=int, metavar=("YEAR", "MONTH"),
                    default=list(C.DEFAULT_START))
    p.add_argument("--end", nargs=2, type=int, metavar=("YEAR", "MONTH"),
                    default=list(C.DEFAULT_END))
    p.add_argument("--force", action="store_true",
                    help="Wipe fetch progress/staging and re-fetch everything.")
    p.add_argument("--max-shards", type=int, default=None, metavar="N",
                    help="TEST MODE: cap shards fetched per month to N. Output goes "
                         "to data/raw_TEST/, fully isolated from real data -- see "
                         "fetch.py's --max-shards help for details. NOTE: clean.py "
                         "only ever reads from data/raw/, so in test mode this script "
                         "will just report 'no raw quarters found' at the clean stage "
                         "-- that's expected. Look in data/raw_TEST/ directly instead.")
    p.add_argument("--skip-fetch", action="store_true",
                    help="Skip the fetch stage, only (re-)run cleaning on existing raw data.")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = C.RunConfig(start=tuple(args.start), end=tuple(args.end),
                       max_shards_per_month=args.max_shards)
    t0 = time.time()

    log.info("=" * 70)
    log.info("BRIDGE BROKERS PIPELINE -- starting run")
    log.info("Window: %s to %s | Frame size: %d subreddits",
              cfg.start, cfg.end, len(cfg.frame))
    log.info("=" * 70)

    if not args.skip_fetch:
        log.info(">>> STAGE 1: FETCH")
        fetch_results = fetch.run(cfg, resume=not args.force)
    else:
        log.info(">>> STAGE 1: FETCH (skipped by --skip-fetch)")
        fetch_results = []

    log.info(">>> STAGE 2: CLEAN")
    clean_results = clean.run(cfg)

    elapsed_min = (time.time() - t0) / 60
    n_fetch_ok = sum(1 for r in fetch_results if r.get("status") in ("complete", "partial"))
    n_clean_ok = sum(1 for r in clean_results if r.get("status") == "ok")

    log.info("=" * 70)
    log.info("PIPELINE COMPLETE in %.1f minutes", elapsed_min)
    log.info("  Fetched : %d/%d quarters", n_fetch_ok, len(fetch_results))
    log.info("  Cleaned : %d/%d quarters", n_clean_ok, len(clean_results))
    log.info("  Reports : %s, %s", C.DATA_LOGS / "coverage_report.csv",
              C.DATA_LOGS / "cleaning_report.csv")
    log.info("  Next    : streamlit run dashboard.py")
    log.info("=" * 70)


if __name__ == "__main__":
    main()