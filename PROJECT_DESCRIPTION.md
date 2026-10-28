# Bridge Brokers of Reddit — Complete Project Reference

**Purpose of this document:** this is the single source of truth for the project. Hand
this to any AI coding agent (Claude Code, Cursor, Copilot, etc.) or any teammate before
asking them to touch the code. It contains the research question, every methodological
decision and why it was made, every verified data source, the full repo structure, what
is built and tested versus what remains, and the known bugs already fixed. An agent
reading only this file should be able to continue the project correctly without asking
the questions that are already answered here.

**Course:** CSE3729 Computational Social Media Analysis, BML Munjal University, Batch
2023 (7th Sem), Academic Year 2026-27. Faculty: Dr. Kiran Sharma, Dr. Jakob Bæk
Kristensen. Semester: 27 July – 28 November 2026.

**Document current as of:** 27 August 2026. Data-source verification dates are noted
separately below — re-verify anything older than a few weeks before relying on it.

---

## 1. The Research Question (read this first)

### 1.1 The problem

Reddit is organised into thousands of communities that largely do not overlap. Most
users concentrate their activity in a small number of related subreddits — this is the
kind of fragmentation Schmidt et al. (2017) documented for online news consumption on
Facebook. Yet information still moves between communities, and that movement depends on
a minority of users who are active in several otherwise-disconnected communities.
Following Burt (1992), we call these users **brokers**, and the gap they span a
**structural hole**.

The existing literature (Granovetter 1973 on weak ties, Burt 1992/2004 on structural
holes) treats brokerage as a property of *individuals*. Both frameworks were built for
organisations and friendship networks, where membership is comparatively stable. Reddit
is not such a setting — accounts are pseudonymous, cheap to create and abandon, and
turnover is high.

**The reframing this project is built on:** a bridge should be understood as a
*position* — a slot in the network structure — not as a person. Analogy: a hotel
receptionist is a position (different people occupy it over the years; the role
persists because the structure requires it). A star football player is a person
(nobody replaces them; if they stop, that thing stops).

### 1.2 Research question

> Over 2018–2022 (see §4 for why this window, not the originally-proposed 2019–2025),
> are bridge positions between Reddit communities more persistent across consecutive
> quarters than the individual users occupying them? If so, which bridges get repaired,
> who is recruited to repair them, and how long do occupants last?

### 1.3 Hypothesis (H1)

Position stability substantially exceeds person stability — brokerage on Reddit is a
structural role the platform refills, not a property of specific individuals.

### 1.4 Why every outcome is reportable (no result is a "failed" project)

- **Position stability ≫ person stability** → hypothesis confirmed. Brokerage is a
  structural slot Reddit refills. Headline finding.
- **Both high** → brokerage is a durable individual role; Burt's original framing
  transfers directly to the platform. Interesting, contradicts H1, still valid.
- **Both low** → Reddit has no durable cross-community structure at all. Surprising,
  still worth reporting.
- **Position stability < person stability** → very odd, would suggest measurement
  error. Requires diagnosis, not a valid substantive finding on its own.

**Do not let the write-up imply the project failed if H1 is not confirmed.** The
hypothesis-rejected framing was written into the plan before any result existed, per the
synopsis.

### 1.5 Scope of claims — read before writing the conclusion

The project samples ~150 of Reddit's millions of subreddits, stratified by category (see
§5). This is **not** a claim about "Reddit" as a monolith. The defensible conclusion
sentence is of the form: *"Within a stratified sample of socially, topically and
politically diverse Reddit communities, cross-community bridge positions are
substantially more persistent than the individuals occupying them, and this pattern
varies by community type."* Never write "Reddit refills its bridges" as an unqualified
universal claim — an examiner will (correctly) push back on it.

**Category-stratified secondary analysis:** position/person stability should also be
reported *separately per category* (politics/news, hobby, support, finance, expertise,
media — see §5). With only ~25 subreddits per category this breakdown is
**interpretive, not independently statistically confirmed** — say so explicitly in the
report. This is what turns a single headline number into an actual account of how
different parts of the platform behave differently (e.g. support-community bridges
might be far more person-dependent and fragile than hobby-community bridges, which would
be a genuinely interesting and citable finding).

---

## 2. Objectives (the committed, gradeable scope)

Each objective has one verifiable deliverable, checkable as complete/incomplete without
argument. O1–O5 are committed. O6 is conditional and gated on Week 13 (see §9 timeline).

| # | Objective | Verifiable deliverable | Status |
|---|---|---|---|
| O1 | Construct and justify a stratified sampling frame of ~150 subreddits across six categories, excluding universal hub subreddits. | `frame.csv` + one-page written justification of every inclusion rule. | Draft frame exists in `config.py` (36 subreddits currently — **needs expansion toward ~150**, see §5 and §10 open items). |
| O2 | Build a reproducible, privacy-preserving pipeline converting public Reddit archives into quarterly user–subreddit datasets. | Quarterly Parquet files with SHA-256 hashed user IDs; documented code; per-quarter coverage table. | **Built and tested** — `fetch.py`. See §7. |
| O3 | Characterise the data through exploratory analysis and quantify the effect of bot/low-activity filtering. | EDA chapter, five-sheet Tableau dashboard, before/after filtering comparison table. | Bot-filtering half **built and tested** (`clean.py`). Tableau dashboard **not yet built** — separate from the Streamlit pipeline-monitoring dashboard (see §7.4 for the distinction). |
| O4 | Detect community structure per quarter; assign community identities consistent over time. | Community assignments per quarter; resolution sweep table; GraphML exports. | **Prototyped, not finalised** — see §8 (network analysis scripts from earlier handoff, not yet re-integrated into this pipeline's file structure). |
| O5 | Measure and statistically compare position stability against person stability across consecutive quarters. | Headline figure, null-model band, empirical p-value. | **Prototyped, not finalised** — see §8. |
| O6 | CONDITIONAL — extensions: bridge criticality, occupant succession, moderator-vs-organic brokers (uses the `is_mod` field, already captured), the natural-experiment shock (see §4.3). | One extension chapter covering as many of the four as time permits. | Not started. Gated on O1–O5 completion by Week 13. |

**Deliberately excluded from scope (recorded, not silently dropped):** Cox
proportional-hazards modelling of broker tenure, Kaplan–Meier survival curves (replaced
by a simpler tenure distribution), a two-coder qualitative broker typology with Cohen's
κ, panel logistic regression predicting bridge dissolution. These are future work.

---

## 3. Methodology — full pipeline with rationale

Each quarter is processed independently through this pipeline. Steps 1–4 are standard
network-science procedure; steps 5–7 are the project's actual contribution.

| Step | What | Why |
|---|---|---|
| 1. Bipartite network | Users on one side, subreddits on the other; edge where a user commented. | Preserves the two-mode structure of the raw data; users never connect directly to users. |
| 2. One-mode projection | Squash to subreddit–subreddit network, weighted by shared users, **cosine-normalised on presence** (not raw comment volume). | Without normalisation, large subreddits look similar to everything just by being large. Cosine on presence (0/1, not comment count) fixes this. |
| 3. Disparity filter | Serrano, Boguñá & Vespignani (2009) backbone extraction. | Without it the projected network is a hairball — every subreddit connects to every other — and community detection returns one undifferentiated block. |
| 4. Community detection | Leiden algorithm (Traag, Waltman & van Eck, 2019), **not Louvain**. Resolution swept 0.5→1.5 across 10 random seeds. | Louvain can return internally *disconnected* communities (a "community" that is actually two separate pieces); Leiden guarantees connectivity and is faster. The resolution sweep is the answer to "why 1.0?" — a near-certain viva question. |
| 5. Community identity over time (**anchored matching**) | Leiden's numeric labels are arbitrary each quarter. Every quarter is matched **independently** against ONE reference partition built from pooled data across the whole window, via Jaccard membership overlap (threshold 0.3). | **This replaces chained Greene matching (Q1→Q2→Q3→...).** Chaining propagates error: one bad match early corrupts every quarter after it. Anchoring keeps errors local — it's one loop instead of a 20+ link chain. This was the project's stated highest technical risk; anchoring substantially reduces it. Communities that fail to match (Jaccard < 0.3 against every anchor community) are recorded as split/merge/birth/death events — these become material for O6 extensions, not discarded. |
| 6. Broker identification | Participation coefficient (Guimerà & Amaral, 2005): `P = 1 - Σ(k_ic/k_i)²`. Brokers = top 1% by P among users meeting a minimum activity threshold. Sensitivity tested at 0.5%/1%/5%. Burt's constraint and raw communities-spanned serve as convergent-validity checks. | P is defined *relative to communities*, not raw subreddit count — it specifically captures boundary-crossing, not just being active. Posting in 10 subreddits that are all the same community scores low; posting in 2 subreddits from 2 different communities scores high. |
| 7. The core comparison | A **position** = a pair of communities bridged by ≥1 broker. **Position stability** = Jaccard similarity of the *set of occupied positions* between consecutive quarters. **Person stability** = mean Jaccard similarity of the *occupant sets* of positions present in both quarters. | This gap between the two series is the entire finding. |

### 3.1 Validation strategy

- **Null model:** degree-preserving randomisation — each user keeps their exact number
  of subreddits and comment volume, but *which* subreddits is randomised, repeated
  ≥200 times. Rules out "your brokers are just the most active users" — expect this
  exact objection in the viva.
- **Convergent validity:** if participation coefficient, Burt's constraint, and raw
  communities-spanned agree on who the brokers are, the measure is trustworthy.
- **Construct validity:** manual inspection of a sample of top-ranked brokers to confirm
  they genuinely bridge topics rather than being bots/spammers.
- **Frame truncation:** the sampling frame only covers ~150 subreddits, so a user
  bridging communities *outside* the frame looks provincial in the data. Fix: for 500
  random users, pull their **complete** cross-Reddit subreddit distribution via the
  Arctic Shift API's `/api/users/interactions/subreddits` endpoint (§4.2), compute a
  "true" participation coefficient, and correlate with the in-frame estimate. r > 0.7 =
  the in-frame measure holds; r < 0.4 = the frame needs widening.
- **Bot filtering:** see §7.2 — implemented as a hard-cutoff auto-removal plus a
  manual-review queue for the rest, not a single aggressive filter.

---

## 4. Data sources — VERIFIED, with dates and caveats

All of the following were tested programmatically (not just read from documentation) on
26 August 2026. Do not trust any Reddit-data link found via general web search without
re-verifying it the same way — see §4.4 for sources that looked legitimate but were
confirmed dead.

### 4.1 Primary source: Hugging Face `open-index/arctic` (comments)

`https://huggingface.co/datasets/open-index/arctic`

- Queried remotely via DuckDB's `httpfs` extension — **no bulk download required**;
  DuckDB reads only matching rows/columns directly over HTTPS.
- Path pattern: `hf://datasets/open-index/arctic/data/comments/YYYY/MM/NNN.parquet`
- Schema (verified): `id, author, subreddit, body, score, created_utc, created_at,
  body_length, link_id, parent_id, distinguished, author_flair_text`
- **`distinguished` field:** set to `"moderator"` when the comment was posted by that
  subreddit's moderator acting in that capacity. This is what gives O6's
  moderator-vs-organic-broker comparison "for free" — no extra collection needed, the
  field is already in every row.

**⚠️ CRITICAL LIMITATION, verified by direct probing:** the dataset card advertises
2005–2026 coverage, but that applies to **submissions**, not comments. **Comments on
this source stop at 2022-08.** Verified directly:
```
comments 2022/08: PRESENT      comments 2022/09: 404 (absent)
comments 2023/01: 404          comments 2024/06: 404
```
This is why the project window is **2018-01 → 2022-08**, not the originally-proposed
2019–2025 (see §4.3 for why this is actually a good trade, not just a limitation).

**Measured throughput:** highly variable depending on network conditions — observed
anywhere from ~2.3 to ~4.5 seconds per shard in testing. A month has 130–520 shards
depending on how busy Reddit was that month. Budget accordingly; do not assume a fixed
runtime (this is why `fetch.py` is checkpointed at the shard-batch level — see §7.1).

### 4.2 Arctic Shift API (validation only, not bulk collection)

Base: `https://arctic-shift.photon-reddit.com`

- Free, no OAuth required, maintained by the same person who built the Parquet mirror.
- Verified coverage: returned records dated June of every year 2018 through 2026
  (tested directly).
- **The endpoint that matters most for validation:**
  ```
  /api/users/interactions/subreddits?author=USERNAME&min_count=5
  ```
  Returns a user's **complete** subreddit distribution across all of Reddit in one
  call — this is the frame-truncation validator from §3.1.
- **Throughput ceiling (measured):** `limit=1000` silently returns 0 results;
  `limit=auto` returns ~350–450 records per ~1 second call. **This API cannot be used
  for bulk quarterly collection** — a single busy subreddit-month would need thousands
  of calls. Use only for the 500-user validation sample and spot checks. Respect its
  rate limits (`x-ratelimit-reset` header present).

### 4.3 Why 2018–2022 instead of 2019–2025 (a scope decision, not just a constraint)

The original synopsis targeted 2019–2025, anchored on the 2023 Reddit API shutdown as
the study's natural shock. Verification revealed comments only exist through 2022-08 on
the free HTTP-queryable source; extending to 2025 would require the torrent-based
monthly `.zst` dumps (§4.4), which are a genuinely different extraction method
(zstd-compressed NDJSON, not remotely queryable — must be fully downloaded and
streamed) and would reintroduce exactly the multi-hundred-GB download problem the
Parquet-mirror approach was chosen to avoid.

**Recommended reframe:** shift the window to 2018–2022 and anchor the natural-experiment
shock on **COVID-19** instead of the 2023 API shutdown. This is arguably an upgrade:
Kristensen et al. (2023) — one of the two course instructors — wrote *"Did COVID-19 blur
partisan boundaries?"*, directly on this exact question. The shock becomes better
documented, better cited, and directly connected to the course reading list, while
removing the torrent dependency from the critical path entirely.

**If the team instead wants to keep the original 2019–2025 window:** the back half
(2022-09 onward) requires the torrent-based path below. This is not currently
implemented in `fetch.py` — it would need a second extraction code path (see §10 open
items).

### 4.4 Fallback / extension sources (for 2022-09 onward, if needed)

**Monthly `.zst` torrents** — master link table (check this first, it's updated the day
each new dump lands): `https://raw.githubusercontent.com/ArthurHeitmann/arctic_shift/master/download_links.md`

All entries below verified live (page 200, `.torrent` downloads, non-zero seeders via
direct tracker scrape) as of 26 Aug 2026:
- Individual months 2024-04 → 2026-07: seeders ranged 6–55 across all 28 months checked.
- Full archive 2005-06 → 2024-12 (3.12 TB, 464 files, file-selectable): 13 seeders.
  `https://academictorrents.com/details/ba051999301b109eab37d16f027b3f49ade2de13`
- **Gap 2022-09 → 2024-03:** individual monthly torrents for this range are struck
  through/superseded in the maintainer's table, and their replacement is also dead. The
  full 3.12 TB archive above (with file selection) is the *only* verified surviving
  route to comments in this specific range.

Parsing scripts written for these files: `https://github.com/Watchful1/PushshiftDumps`

### 4.5 Verified DEAD or unusable — do not use, do not re-search for these

| Source | Verified result |
|---|---|
| Per-subreddit torrents (all 3 generations, various hashes) | Detail page 404, `.torrent` file 404, not registered on tracker. Search engines still index these pages, which is *why* they look alive — they are not. |
| PullPush API | HTTP 429, explicit message: "does not provide free scraping resources for agents... paid scraping service" |
| Legacy Pushshift API (`api.pushshift.io`) | HTTP 307 redirect, no data |
| Reddit's own public `.json` endpoints (`old.reddit.com`, `www.reddit.com`) | HTTP 403 |
| `yikeee/reddit-subreddits25` (HF per-subreddit mirror) | Incomplete upload — manifest lists ~80,000 files, only ~12,600 (about a third) actually exist. Named subreddits frequently 404. |
| Combined 2005→2025-12 torrent | 404, not on tracker (superseded) |

**Official Reddit API** — apply anyway, but do not depend on it:
- Responsible Builder Policy: `https://support.reddithelp.com/hc/en-us/articles/42728983564564`
- Reddit for Researchers (needs institutional email + ethics letter, so needs faculty):
  `https://support.reddithelp.com/hc/en-us/articles/49381918834964`
- Free tier ~100 queries/min per OAuth client, approval-gated, small research projects
  are the most-rejected category.
- **Log the application regardless of outcome** — date, response or silence, and the
  validated substitution used instead. This is a direct Module 6 (validity/ethics)
  deliverable that most teams will not have.

---

## 5. Sampling frame

Stratified across six categories. **Current `config.py` frame has 36 subreddits — this
needs to grow toward the ~150 target stated in Objective O1** (see §10 open items).

Current categories and rationale (extend within these, don't add new categories without
updating both the frame and the synopsis's Objective O1 justification text):

| Category | Examples currently in frame | Rationale |
|---|---|---|
| `politics_news` | politics, news, worldnews, Conservative, democrats, PoliticalDiscussion | Core RQ2b/cross-partisan-bridge material; connects to Kristensen et al. |
| `hobby` | gaming, pcmasterrace, buildapc, cooking, movies, anime, etc. | Interest-based, expected to show different (more fungible) bridge dynamics than politics. |
| `finance` | personalfinance, investing, stocks, wallstreetbets | High cross-posting volume; useful contrast case. |
| `support` | depression, Anxiety, mentalhealth, loseit | Expected candidate for *fragile*, person-dependent bridges (trust-based). |
| `expertise` | AskHistorians, science, askscience | Heavily moderated; good candidate for moderator-vs-organic broker comparison (O6). |
| `media` | movies, television, books, Music | Low-stakes, broad-appeal control category. |

**Excluded hubs** (analysed separately if O6 is reached, never in the main network):
AskReddit, funny, pics, todayilearned — these connect to nearly everything and would
destroy community structure if included (standard "hub removal" in network science, not
an arbitrary omission — say this explicitly in the methodology write-up).

The full, editable list lives in `config.py`'s `FRAME` dict — **this is the only place
frame edits should be made**; nothing else in the pipeline should ever hardcode a
subreddit name.

---

## 6. Repository structure

```
bridge-brokers/
├── README.md                        -- project-level overview
├── LINKS.md                         -- earlier, less-complete link list (superseded
│                                        by §4 of THIS document — kept for history)
├── DATA_SOURCES_VERIFIED.md          -- full verification detail behind §4 above
├── frame.csv                         -- draft sampling frame export (see §5)
│
├── src/                              -- NETWORK ANALYSIS prototype scripts
│   ├── 01_parse_zst.py               --   .zst streaming parser (for the torrent
│   │                                       fallback path, §4.4) -- tested, working
│   ├── 02_extract_quarters.py        --   EARLIER extraction script -- SUPERSEDED
│   │                                       by pipeline/fetch.py below, kept for
│   │                                       reference only, do not run
│   ├── 03_build_networks.py          --   bipartite -> projection -> disparity
│   │                                       filter -> Leiden. Tested on real data.
│   └── 04_core_test.py               --   anchored matching + position/person
│                                            stability + null model. Tested on real
│                                            data (small sample -- see §8 caveats).
│
└── pipeline/                         -- DATA CURATION pipeline (current, active work)
    ├── config.py                     --   SINGLE SOURCE OF TRUTH. Edit this, not
    │                                       the other files, for frame/dates/thresholds.
    ├── fetch.py                      --   raw extraction from HF Parquet mirror.
    │                                       Batched, checkpointed, resumable. TESTED.
    ├── clean.py                      --   bot filtering + activity thresholds.
    │                                       TESTED against synthetic bot data.
    ├── run_pipeline.py               --   orchestrator: fetch -> clean in one command.
    ├── dashboard.py                  --   Streamlit pipeline-monitoring dashboard
    │                                       (NOT the final Tableau report dashboard
    │                                       from Objective O3 -- see §7.4).
    ├── requirements.txt
    ├── README.md                     --   pipeline-specific usage instructions
    └── data/                         --   all git-ignored, generated at runtime
        ├── raw/         <quarter>.parquet        -- hashed, frame-filtered, unclean
        ├── raw_TEST/                              -- ISOLATED test-mode output, see §7.3
        ├── clean/       <quarter>.parquet         -- bot-filtered
        ├── logs/        pipeline.log,
        │                coverage_report.csv,
        │                cleaning_report.csv,
        │                manual_review_<q>.csv
        └── cache/       fetch_progress.json,       -- resumability checkpoints
                          staging.duckdb
```

**IMPORTANT for any agent editing this repo:** `src/` and `pipeline/` currently
represent two separate rounds of work that have **not yet been merged**. `src/`'s
`02_extract_quarters.py` is superseded by `pipeline/fetch.py` (which is more robust —
batched, checkpointed, retry-wrapped). `src/03_build_networks.py` and
`04_core_test.py` are the network-analysis stage and have NOT been updated to read
from `pipeline/data/clean/` yet — this integration is the next major piece of work
(§10, item 1).

---

## 7. The data curation pipeline — what is built and tested

### 7.1 `fetch.py` — extraction

- Pulls from the HF Parquet mirror via DuckDB `httpfs`, filtered to the sampling frame,
  for every month in the configured window.
- **Hashes usernames inside the SQL query itself**, at the moment of extraction
  (`SHA-256(salt + lowercase(username))`, truncated to 16 hex chars). Raw usernames
  never touch disk anywhere in this pipeline.
- Only 4 fields survive: `author_h`, `subreddit`, `created_utc`, `is_mod`.
- **Batched + checkpointed design (important — do not revert):** an earlier version
  issued one giant query per quarter (500+ shards at once). Tested against a real
  network, this took many minutes with zero feedback and zero resumability — a failure
  partway through lost the entire quarter's work. The current version batches shards
  (`SHARD_BATCH_SIZE = 15`), inserts each batch into a staging DuckDB table, and writes
  a progress checkpoint to `fetch_progress.json` **after every batch**. A crash now
  loses at most one batch of shards, not a whole quarter. Rerunning the same command
  always resumes correctly — already-inserted batches are skipped, never repeated.
- **Bug fixed 27 Aug 2026:** an early version ignored `--end` once it had determined
  which quarter you were touching, and always fetched all 3 months of that quarter
  regardless of what you asked for. Now fixed — months are intersected against the
  requested `[start, end]` window, and a quarter fetched with a restricted window is
  correctly marked `"partial"` (not `"complete"`) with the excluded months recorded
  under `months_skipped_by_request` in the coverage report, distinct from genuine
  source gaps (`months_missing_from_source`).
- **`--max-shards N` test mode:** fetches only N shards per month for a near-instant
  smoke test (e.g. `--max-shards 2` completes in ~15 seconds). **Fully isolated** —
  writes to `data/raw_TEST/` with its own progress file and staging DB
  (`fetch_progress_TEST.json`, `staging_TEST.duckdb`), never touching the real
  `data/raw/` or the real progress tracking. This isolation was a deliberate fix: an
  earlier design would have let a tiny test slice masquerade as a real "complete"
  quarter if the same command were later run without `--max-shards`.
- CLI: `python fetch.py [--start Y M] [--end Y M] [--force] [--max-shards N]`

### 7.2 `clean.py` — bot filtering

- **Cannot do username-pattern bot detection** (matching `*bot`, `*_bot` etc.) because
  usernames are already hashed by the time this script runs — that filtering happens
  inside `fetch.py`'s SQL instead (`KNOWN_BOT_NAMES`/`KNOWN_BOT_SUFFIXES` in
  `config.py`), before hashing.
- What this script *can* do: behavioural signals computed after hashing —
  per-quarter comment volume and subreddit breadth.
- **Deliberately conservative auto-removal:** hard cutoffs
  (`BOT_VOLUME_HARD_CUTOFF = 2000` comments/quarter, `BOT_BREADTH_HARD_CUTOFF = 40`
  distinct subreddits/quarter) only catch near-certain bots. Anything less extreme is
  NOT auto-deleted — it goes into a **manual review queue** instead
  (`data/logs/manual_review_<quarter>.csv`, top 200 accounts by subreddit breadth).
  This was a deliberate design choice, verified by testing: a real cross-community
  broker (the exact thing this project is trying to find) can legitimately show
  high subreddit breadth, and an aggressive automatic filter would quietly delete the
  project's own signal.
- **Tested with synthetic data** containing a known volume-spam bot (3000 comments, 1
  subreddit), a known cross-posting bot (present in every subreddit, moderate volume),
  and a known legitimate broker (moderate volume, several subreddits). Result: the
  volume bot was auto-removed; the cross-poster was correctly *held back* for manual
  review rather than deleted; the legitimate broker survived untouched.
- Writes `cleaning_report.csv` (before/after row & user counts) — this is the direct
  Objective O3 deliverable.
- CLI: `python clean.py [--quarter 2018Q1]`

### 7.3 Manual review workflow (Stage 4 of the bot cascade — not optional)

For each quarter, `clean.py` produces `manual_review_<quarter>.csv` listing the top 200
most cross-community accounts (by hashed ID, not username — they cannot be
de-anonymised from this file). A team member opens this file (or the dashboard's
"Manual Review" tab), inspects each account's behaviour pattern, and records a verdict
(`keep` / `bot` / `spammer`) plus notes. This step is explicitly required by the
synopsis's methodology and is a graded component (Module 2), not busywork — do not skip
it or automate it away.

### 7.4 `dashboard.py` — Streamlit pipeline monitor (distinct from the report dashboard)

**This is a data-quality/progress dashboard for the team while the pipeline runs — it
is NOT the final Tableau analysis dashboard required by Objective O3 for the report.**
Do not confuse the two; both are needed, they serve different purposes.

Four tabs, all reading live from whatever's currently on disk:
1. **Coverage** — which quarters are complete/partial/missing, row counts, missing
   months (reads `coverage_report.csv`).
2. **Cleaning** — before/after row & user counts, bots removed (reads
   `cleaning_report.csv`).
3. **Browse Data** — live sample + summary stats for any quarter, computed directly
   from the Parquet file with DuckDB (always current, no separate export step).
4. **Manual Review** — opens the top-200 candidate list for a chosen quarter.

Run with `streamlit run dashboard.py`. Verified to boot cleanly (HTTP 200, no
exceptions) in headless mode during testing.

### 7.5 `run_pipeline.py` — orchestrator

Thin wrapper: calls `fetch.run()` then `clean.run()`, prints a summary. Contains
almost no logic of its own by design — real logic lives in `fetch.py`/`clean.py` where
it's easier to find independently.

```bash
python run_pipeline.py                              # full configured window
python run_pipeline.py --start 2018 1 --end 2018 1   # one-month test
python run_pipeline.py --max-shards 2                # near-instant smoke test
python run_pipeline.py --force                       # wipe cache, start fully over
python run_pipeline.py --skip-fetch                  # re-run cleaning only
```

**Note:** `--max-shards` routes fetch output to the isolated `raw_TEST/` folder (§7.1),
which `clean.py` never reads — so `run_pipeline.py --max-shards N` will correctly fetch
a tiny test sample but then report "no raw quarters found" at the clean stage. That is
expected, not a bug; inspect `data/raw_TEST/` directly for the fetch-stage test output.

---

## 8. Network analysis stage — prototyped, needs integration

Located in `src/`, built and tested against real Reddit data (small sample, ~1% of
2020) during an earlier phase of this project, **before** `pipeline/` existed. Proven
to run correctly end-to-end, but:
- Reads from an older, simpler data format than what `pipeline/clean.py` now produces
  (paths and schema may need small adjustments — check column names match:
  `author_h, subreddit, created_utc, is_mod` from the new pipeline).
- Was only tested on a 1% sample — the anchored-matching and stability-comparison
  results from that test run should be treated as a **plumbing verification only**, not
  as preliminary findings. At that sample size, person stability came out as exactly
  0.000, which is a sampling artefact (too few broker occupancies for any overlap to be
  possible), not a real result.

**`03_build_networks.py`** — implements pipeline steps 1–4 from §3 (bipartite →
projection → disparity filter → Leiden with resolution sweep). Outputs GraphML per
quarter for Gephi, plus JSON community assignments.

**`04_core_test.py`** — implements steps 5–7 (anchored matching, participation
coefficient, position/person stability comparison, degree-preserving null model). This
is the script that produces the headline result for Objective O5.

**Sample output from the earlier small-sample test run** (for reference — not a real
finding, see caveat above):
```
Anchor reference partition: 7 communities
  C1: Conservative, PoliticalDiscussion, democrats, news, politics, worldnews
  C3: Steam, buildapc, pcgaming, pcmasterrace
  C5: investing, stocks, wallstreetbets

transition       POSITION   PERSON     GAP
2020Q1->Q2          0.273    0.000    0.273
2020Q2->Q3           0.556    0.000    0.556
```
Communities came out clean and interpretable even at 1% sampling — a good sign for
feasibility. Person stability of exactly 0 is the sampling artefact noted above.

**⚠️ FEASIBILITY GATE — do this before investing further time in anything downstream:**
The entire project's validity rests on one assumption: that Leiden communities are
stable enough across quarters to be meaningfully matched. Run `03_build_networks.py`
+ `04_core_test.py` on 3 real (not 1%-sampled) consecutive quarters from the actual
pipeline output before committing further engineering time to O4/O5. If communities
come out incoherent or the anchor-match rate is very low (<60%), fall back to a single
fixed partition from pooled data and treat positions as fixed rather than tracked — a
smaller but still valid project. Decide this early, not in Week 13.

---

## 9. Timeline

Semester: 27 July – 28 November 2026. Full week-by-week table is in the A1 synopsis
document (`A1_Synopsis_BridgeBrokers.docx`, not reproduced here to avoid drift between
two copies — treat that document as authoritative for exact dates). Summary of major
milestones:

| Week(s) | Milestone |
|---|---|
| 6 | A1 — Project Phase Evaluation 1 (20%) — synopsis, timeline, responsibility matrix |
| 11 | A2 — Project Phase Evaluation 2 (20%) — data collection + preliminary analysis |
| 13 | Decision point: is Objective O6 (extensions) attempted, based on O1–O5 progress |
| 17 | Quiz (20%) — full syllabus |
| 18 | A3 — End Term Evaluation (40%) — final report, repo, deck, demo video |

---

## 10. Open items / what to do next

In rough priority order:

1. **Expand the sampling frame from 36 to ~150 subreddits** (Objective O1 target).
   Extend within the existing six categories in `config.py`'s `FRAME` dict; write the
   accompanying one-page justification.
2. **Run the feasibility gate** (§8) on 3 real consecutive quarters from actual
   pipeline output, not the old 1%-sample test data.
3. **Integrate `src/03_build_networks.py` and `04_core_test.py` with
   `pipeline/data/clean/`** — update file paths and confirm the schema
   (`author_h, subreddit, created_utc, is_mod`) lines up; it should mostly just work
   since the column names already match.
4. **Decide on the 2018–2022 vs. 2019–2025 window** (§4.3) as a team, ideally with
   faculty input, since it changes the natural-experiment framing (COVID vs. the 2023
   API shutdown) and whether the torrent-based extension path (§4.4) needs building.
5. **Run the full `fetch.py` + `clean.py`** over the committed window once the frame is
   finalised. Expect this to take a genuinely unpredictable amount of wall-clock time
   (§4.1) — plan to run it unattended over a day or overnight, relying on the
   checkpointing to survive interruptions.
6. **Build the actual Tableau dashboard** for Objective O3 (distinct from the Streamlit
   pipeline monitor, §7.4).
7. **Apply to Reddit for Researchers** regardless of the above (§4.5) — log the
   application and outcome for the Module 6 validity chapter.
8. **Begin the manual bot-review workflow** (§7.3) once real quarters start completing
   — do not leave this until the end, it's meant to happen incrementally per quarter.

---

## 11. Ethics and privacy — non-negotiable constraints for any code changes

- Usernames are hashed with SHA-256 + a project salt **inside the SQL extraction
  query itself**, in `fetch.py`, before any file is written to disk. No script anywhere
  in this pipeline should ever write a raw username to any file. If an agent is asked
  to add a feature that seems to require the raw username downstream of `fetch.py`,
  that is a signal the feature needs to be re-designed to happen inside `fetch.py`'s
  extraction query instead, or flagged as a problem rather than implemented.
- Only public Reddit content is used. No private messages, no deleted content, no
  attempt at deanonymisation.
- Comment text (`body` field) is discarded at extraction — never stored.
- The public GitHub repository should contain code and hashed derivatives only, never
  raw data or the real `HASH_SALT` value (keep the real salt in an untracked local
  override, not committed).

---

## 12. Key citations (for methodology justification in the report)

- Burt, R. S. (1992). *Structural Holes: The Social Structure of Competition.* Harvard
  University Press.
- Granovetter, M. S. (1973). The strength of weak ties. *American Journal of Sociology*,
  78(6), 1360–1380.
- Guimerà, R., & Amaral, L. A. N. (2005). Functional cartography of complex metabolic
  networks. *Nature*, 433, 895–900. [participation coefficient]
- Kristensen, J. B., Henriksen, F. M., & Mayerhöffer, E. (2023). Did COVID-19 blur
  partisan boundaries? *Social Media + Society*, 9(3). [co-instructor's own paper —
  cite explicitly, especially if the COVID-anchored window (§4.3) is adopted]
- Rogers, R. (2015). *Digital Methods for Web Research.* Wiley.
- Schmidt, A. L., et al. (2017). Anatomy of news consumption on Facebook. *PNAS*,
  114(12), 3035–3039.
- Serrano, M. Á., Boguñá, M., & Vespignani, A. (2009). Extracting the multiscale
  backbone of complex weighted networks. *PNAS*, 106(16), 6483–6488. [disparity filter]
- Traag, V. A., Waltman, L., & van Eck, N. J. (2019). From Louvain to Leiden:
  guaranteeing well-connected communities. *Scientific Reports*, 9, 5233.