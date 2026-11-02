# Findings: data inventory (before any new analysis)

*Written before building the Findings section, as the directive requires. Every figure below was read from the stored files on 1 Nov 2026.*

## 1. What is stored today

| Store | Content | Size |
|---|---|---|
| `data_curation/data/clean/{2017Q4,2018Q1,2018Q2,2018Q3}.parquet` | **210.3 M comments** by **2.45 M pseudonymous commenters** across the 170 frame subreddits, Oct 2017 – Sep 2018, every month complete (coverage report: 4/4 quarters complete) | 1.8 GB |
| `data_curation/data/raw/*.parquet` | the same before cleaning (223.2 M rows) | 1.9 GB |
| `atlas/web/data/*.json` | the Atlas artifacts: per-period pair statistics (shared, expected, affinity, p-values, validated/avoided), nodes with communities and participation, weekly/monthly activity, the four discoveries, pipeline facts | ~70 MB |

**Columns actually stored per comment: `author_h` (salted SHA-256 prefix), `subreddit`, `created_utc`, `is_mod`. Nothing else.** There is no comment text, no score, no `parent_id`/`link_id` (reply structure), no post/submission table, no flair. The existing codebase has no NLP, sentiment or topic code (`grep` for nltk/vader/sentiment/tfidf finds nothing), and no sentiment packages are installed (`vaderSentiment`, `nltk`, `torch` absent; `scikit-learn` present).

Consequences for the directive:

- **Sentiment / themes / opinion groups cannot be computed from the stored data.** They need text.
- **A user-level interaction network cannot be built from the stored data.** The only user–user relation available is co-presence in subreddits (what the Atlas already projects); drawing "interaction" edges from it would violate the instruction not to draw relationships that are not in the data. Reply edges need `parent_id`/`link_id`.
- The existing data *does* answer participation questions: who commented where and when, at weekly resolution, for all 170 communities.

## 2. Event coverage in the stored data (comments per UTC calendar month, thousands; Atlas store)

| Subreddit | Oct | Nov | Dec | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| r/marvelstudios | 75 | 143 | 140 | 114 | 171 | 293 | **354** | 322 | 172 | 174 | 231 | 211 | 2.40 M |
| r/Marvel | 17 | 22 | 25 | 19 | 25 | 27 | 48 | **53** | 26 | 27 | 26 | 24 | 0.34 M |
| r/movies | 358 | 409 | **535** | 449 | 412 | 430 | 418 | 417 | 357 | 455 | 357 | 341 | 4.94 M |
| r/Bitcoin | 175 | 335 | **505** | 219 | 165 | 117 | 102 | 91 | 86 | 72 | 76 | 58 | 2.00 M |
| r/CryptoCurrency | 89 | 143 | 316 | **677** | 424 | 288 | 239 | 200 | 154 | 114 | 123 | 100 | 2.87 M |
| r/ethereum | 14 | 20 | **25** | 25 | 16 | 13 | 16 | 12 | 9 | 12 | 9 | 7 | 0.18 M |
| r/dogecoin | 4 | 6 | 30 | **40** | 30 | 26 | 7 | 5 | 5 | 3 | 3 | 5 | 0.16 M |
| r/BitcoinBeginners | 7 | 10 | **15** | 8 | 6 | 3 | 2 | 2 | 1 | 2 | 2 | 1 | 0.06 M |

Both events are well covered in time: Infinity War (US release 27 Apr 2018) has almost seven months of the window before it and five after; the crypto decline is covered from the December 2017 peak (r/Bitcoin −81 % of commenters by September) through September 2018. The late-2017 run-up is only partly covered (the window starts in October 2017).

## 3. What the source can still provide

The Arctic Shift comment shards (`open-index/arctic`, read remotely with DuckDB exactly as `fetch.py` does) carry per comment: `id, author, subreddit, body, score, created_utc, link_id, parent_id, distinguished, author_flair_text`. A one-shard probe for r/marvelstudios + r/Bitcoin + r/CryptoCurrency shows ~137 characters of body on average, 59 % of comments replying to another comment (`t1_` parents), and 7.5 % of bodies deleted or removed. The historical fetch rate was ~7 minutes per month for all 170 subreddits without text.

## 4. Proposed additional collection (needs a go-ahead)

`data_curation/fetch_text.py` (written, not run) re-uses `fetch.py`'s resilient batch design and the **same salt**, and keeps:

- **text + structure** for 11 subreddits: the two Infinity War communities, the five crypto communities, and four debate communities that are candidates for the focused network (r/CapitalismVSocialism, r/PurplePillDebate, r/australianpolitics, r/thewallstreet) — about **9.2 M comments**;
- **structure only** (no body) for 11 more focused-network candidates and context (r/changemyview, r/CanadaPolitics, r/custommagic, r/kpop, r/askphilosophy, r/AskHistorians, r/medicalschool, r/rust, r/chess, r/newsokunomoral, r/comics) and for r/movies in Mar–Jun 2018 — about **8 M rows**.

Estimated cost: ~2 hours of remote reading, roughly 0.7 GB on disk (zstd Parquet, 12.9 GB free), local only (`data/raw_text/` will be gitignored). Published artifacts will contain aggregates (sentiment shares, volumes, themes as keywords) and anonymised networks (sequential node ids, group labels); never text, usernames or author hashes. `[deleted]` authors are kept as structure with a NULL author; AutoModerator is dropped as in the main pipeline.

Why these candidates (screen of all 170 communities on the stored data; full table in the research note): communities with 2–40 k commenters, 10–60 comments per commenter, month-to-month commenter stickiness ≥ 0.4, present in all 12 months, spread over categories, with debate communities included because their flairs record a self-declared position (needed to separate opinion disagreement from sentiment). Support/health communities are excluded from user-level network stories on ethical grounds.

## 5. Alternatives if the fetch is not wanted

- **Smaller fetch** (≈45 min): Infinity War text (r/marvelstudios, r/Marvel, Mar–Jun 2018) plus structure for the candidate list only; the crypto story would then rest on volumes and shared audiences without sentiment.
- **No fetch**: a Findings section limited to participation and shared-audience evidence (volumes, newcomer shares, affinity over time). Sentiment, themes, reply networks and brokers would be out of reach, and the directive's event stories could not be answered as posed.

## 6. Outcome (after collection, 1–2 November 2026)

The fetch ran as proposed and resumed from its checkpoint after one interruption: 12 months complete, 0 partial, 23 subreddits
(text + structure for 11, structure only for 11, r/movies for March–June 2018 only), 15,978,719 rows of which 10,546,665 carry text,
0.9 GB on disk as zstd Parquet plus 0.1 GB of cached VADER scores — both local and gitignored. Every published number in
the Findings section is computed from this store by `findings/build_findings.py`; the store itself, the scores and the labelled
validation sample never leave the machine.
