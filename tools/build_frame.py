"""Regenerate frame.csv from the published rule in data_curation/frame_rules.py.

frame.csv is a committed artefact so a reviewer can read the frame without
running anything, but it is GENERATED: this script is the only sanctioned way
to change it, and a test asserts the committed file still matches the rule.
"""
import os, sys
import pandas as pd

ROOT = r"C:\Users\vansh\Desktop\CSMA\sm"
sys.path.insert(0, os.path.join(ROOT, "data_curation"))
import frame_rules as FR

frame = FR.build_frame()
out = frame.rename(columns={"stratum": "category"})[
    ["subreddit", "category", "n_min", "n_total"]].copy()
dest = os.path.join(ROOT, "frame.csv")
out.to_csv(dest, index=False)

print(f"wrote {dest}: {len(out)} rows")
print(out.groupby("category").agg(
    n=("subreddit", "count"), min_n_min=("n_min", "min"),
    median=("n_min", "median"), max_n_min=("n_min", "max")).to_string())
print(f"\nduplicates (case-insensitive): "
      f"{out.subreddit.str.lower().duplicated().sum()}")
print(f"any n_min below {FR.MIN_N:,}: {(out.n_min < FR.MIN_N).sum()}")
print(f"\nvolume share by stratum:")
tot = out.groupby("category").n_total.sum()
print((100 * tot / tot.sum()).round(1).to_string())
