"""Regenerate data_curation/frame_calibration.csv.

Counts monthly subreddit comment volume at three points spanning the study
window (start / middle / end), over ALL Arctic shards, then ships a table of
every subreddit observed at n_min >= SHIP_FLOOR.

This is what makes the sampling frame auditable: frame_rules.build_frame()
derives every member from this table by a published rule, so the frame is
reproducible instead of hand-picked, and a reviewer can check each member's
coverage at the start, middle and end of the window.

Usage:
    python tools/build_frame_calibration.py [--floor 500]

Note this reads ~600 shards and takes roughly 40 minutes on a cold cache; the
output is cached in the repository, so this only needs re-running if the
window, the floor, or the corpus changes.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import duckdb
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "data_curation"))

import frame_rules as FR  # noqa: E402

BASE = "hf://datasets/open-index/arctic/data/comments"
POINTS = [("n_2018_01", "2018", "01"), ("n_2020_07", "2020", "07"),
          ("n_2022_08", "2022", "08")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=int, default=FR.SHIP_FLOOR,
                    help="ship subs whose minimum monthly count >= this")
    ap.add_argument("--out", default=os.path.join(ROOT, "data_curation",
                                                  FR.CALIBRATION_CSV))
    args = ap.parse_args()

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET preserve_insertion_order=false;")
    con.execute("SET threads=4;")

    w = None
    for label, y, m in POINTS:
        glob = f"{BASE}/{y}/{m:02d}/*.parquet"
        t0 = time.time()
        df = None
        for attempt in range(1, 6):
            try:
                df = con.execute(
                    f"SELECT subreddit, count(*)::BIGINT n FROM "
                    f"read_parquet('{glob}', hive_partitioning=false) "
                    f"WHERE subreddit IS NOT NULL GROUP BY 1"
                ).df()
                break
            except Exception as exc:  # transient network/HTTP failures
                print(f"[{label}] attempt {attempt} failed: "
                      f"{str(exc)[:70]}", flush=True)
                time.sleep(10 * attempt)
        if df is None:
            print(f"[{label}] giving up", flush=True)
            return 1
        df = df.rename(columns={"n": label})
        print(f"[{label}] {len(df):,} subs in {time.time()-t0:.0f}s", flush=True)
        w = df if w is None else w.merge(df, on="subreddit", how="outer")

    for label, _, _ in POINTS:
        w[label] = w[label].fillna(0).astype("int64")
    w["n_min"] = w[[l for l, _, _ in POINTS]].min(axis=1)
    w["n_total"] = w[[l for l, _, _ in POINTS]].sum(axis=1)

    # Case-insensitive collapse; keep the highest-coverage spelling.
    w["key"] = w.subreddit.str.lower()
    w = (w.sort_values("n_min", ascending=False)
           .drop_duplicates("key")
           .drop(columns=["key"]))
    out = w[w.n_min >= args.floor].sort_values("n_min", ascending=False)
    out.to_csv(args.out, index=False)

    print(f"\nwrote {args.out}: {len(out):,} subs (floor {args.floor:,})")
    for t in (20000, 10000, 5000, 2000, 1000, 500):
        print(f"  n_min >= {t:>6,}: {int((out.n_min >= t).sum()):>6,}")
    frame = FR.build_frame(pool=out)
    print(f"\nframe: {len(frame)} subs")
    print(frame.groupby("stratum").agg(
        n=("subreddit", "count"), min_nmin=("n_min", "min"),
        total=("n_total", "sum")).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
