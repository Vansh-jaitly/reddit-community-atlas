# Data Curation Pipeline

Fetches, cleans, and lets you browse the Reddit data for the Bridge Brokers project.
Every script here was tested against the live data source before being handed over.

## Files

| File | Purpose |
|---|---|
| `config.py` | **Edit this one.** Subreddit list, date window, thresholds, paths. |
| `fetch.py` | Pulls raw comment data from Hugging Face, hashes usernames, writes quarterly Parquet files. Resumable. |
| `clean.py` | Bot filtering + activity thresholds. Writes cleaned Parquet + manual-review CSVs. |
| `run_pipeline.py` | Runs fetch → clean in one command. |
| `dashboard.py` | Streamlit app to view coverage, cleaning stats, and browse the data live. |
| `requirements.txt` | `pip install -r requirements.txt` |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows cmd.exe
pip install -r requirements.txt
```

## Quick test (before committing to the full run)

**Fastest option — 1-2 shards, seconds not minutes:**

```bash
python fetch.py --start 2018 1 --end 2018 1 --max-shards 2
```

This fetches just 2 shards of January 2018 and finishes in well under a
minute. Output goes to a **completely separate** `data/raw_TEST/` folder with
its own progress file and staging database (`fetch_progress_TEST.json`,
`staging_TEST.duckdb`) — it can never collide with or be mistaken for real
fetched data, and `clean.py`/the dashboard never look in `raw_TEST/`, so
there's no risk of a tiny non-representative test slice quietly ending up in
your actual analysis. Delete `data/raw_TEST/` whenever you're done testing.

Use `--max-shards N` for any N — try 1 for the absolute minimum, or something
like 20 if you want a slightly more realistic (but still fast) sample.

**One-month test (real data, isolated the same way as above):**

```bash
python run_pipeline.py --start 2018 1 --end 2018 1
```

Note: `--start`/`--end` restrict to the requested months only (a quarter is
normally 3 months) — the coverage report will correctly show this quarter as
`"partial"` with the other two months listed under `months_skipped_by_request`,
not as a data problem. Rerun later with a wider window to fill them in.

## Full run

```bash
python run_pipeline.py
```

Default window is 2018-01 → 2022-08 (set in `config.py` — this is the full range
verified to exist on the primary data source; see the comment block at the top
of `config.py` for why).

**This will take a while and the exact time is genuinely unpredictable** — it
depends entirely on your network to Hugging Face. In testing this ran anywhere
from ~2.3 to ~4.5 seconds per data shard; a quarter has 400–600 shards, so
budget **anywhere from 20 minutes to a couple of hours per quarter**, and plan
to run it in the background over a day or overnight rather than expecting a
fixed runtime.

**This is why the script is checkpointed at the batch level (every ~15
shards), not just per-quarter.** If your laptop sleeps, wifi drops, or you
need to Ctrl+C it, just run the same command again — it picks up exactly
where it left off and does not re-download anything already saved.

```bash
python run_pipeline.py              # resumes automatically
python run_pipeline.py --force      # wipes progress, starts over
```

## Checking progress mid-run

While `fetch.py` is running (or after), open another terminal:

```bash
streamlit run dashboard.py
```

The **Coverage** tab shows exactly which quarters/months are done, in
progress, or missing — refresh your browser any time.

## After fetching: manual bot review

`clean.py` runs automatically as part of `run_pipeline.py`, but it flags — it
does not delete — the top 200 most cross-community accounts each quarter (see
the long comment at the top of `clean.py` for why: an aggressive bot filter
would also delete your real brokers, which is the thing the whole project is
trying to find). Open the **Manual Review** tab in the dashboard, or the CSVs
directly in `data/logs/manual_review_<quarter>.csv`, and have a team member
fill in the `verdict` column (`keep` / `bot` / `spammer`) for each quarter.
This is Stage 4 of the bot cascade described in the project synopsis and is
not optional — it's worth real marks under Module 2.

## Output layout

```
data/
  raw/     <quarter>.parquet     -- hashed, filtered to the frame, unclean
  clean/   <quarter>.parquet     -- bot-filtered, activity-thresholded
  logs/    pipeline.log                    -- full run log
           coverage_report.csv             -- per-quarter fetch status
           cleaning_report.csv             -- before/after cleaning stats
           manual_review_<quarter>.csv     -- top-200 accounts to eyeball
  cache/   fetch_progress.json             -- resumability checkpoint
           staging.duckdb                  -- in-progress extraction (safe to delete
                                               after a quarter shows "complete")
```

## If you extend the date window past 2022-08

The primary source (`open-index/arctic` on Hugging Face) only has Reddit
**comments** through 2022-08 — this is a hard limit of that dataset, not a bug
in this pipeline (verified by direct testing; see `DATA_SOURCES_VERIFIED.md`
in the parent folder). Extending past that date requires switching to the
torrent-based monthly dumps described in that file, which is a genuinely
different extraction method (zstd-compressed NDJSON, not queryable remotely).
`fetch.py` would need a second code path for that — it is not currently
implemented, since the project's committed window (per the synopsis) sits
entirely inside the HTTP-only range.

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `fetch.py` errors immediately on every month | `INSTALL httpfs` failed, likely no internet or a firewall | Check you can reach huggingface.co; corporate/university wifi sometimes blocks this |
| A quarter stuck at "in_progress" forever | Ctrl+C'd mid-run, or crashed | Just rerun `python fetch.py` — it resumes from the last completed batch |
| Dashboard shows "no coverage report" | `fetch.py` hasn't been run yet | Run `python run_pipeline.py` first |
| `clean.py` says "No raw quarters found" | `fetch.py` hasn't finished any quarter yet | Wait for at least one quarter to reach "complete" or "partial" in the coverage report |