"""Comment text: VADER sentiment (cached per month), tokenisation and keyword contrasts.

Why VADER: a lexicon-and-rules model built for social-media text (negation, intensifiers, capitalisation,
emoticons, slang), with no training step and no GPU, so every score is reproducible from the comment and the
lexicon version. Its known limits (sarcasm, domain words such as "sick", short comments) are stated in
docs/FINDINGS_METHODOLOGY.md and checked on a labelled sample (validation.py).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as F

_URL = re.compile(r"https?://\S+|www\.\S+")
_QUOTE = re.compile(r"^\s*>.*$", re.M)
_MD = re.compile(r"[*_~`#>|\\]+")
_TOKEN = re.compile(r"[a-z]{3,}")
_MENTION = re.compile(r"(?<![A-Za-z0-9])/?u/[A-Za-z0-9_-]+", re.I)   # u/name mentions never become published terms: stripped before the markdown pass, which would split an underscored name

_ANALYZERS = {}


def _analyzer(domain: str | None = None):
    """Standard VADER, or a copy with the domain's topic words removed from the lexicon (valence 0)."""
    key = domain or "standard"
    if key not in _ANALYZERS:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        a = SentimentIntensityAnalyzer()
        if domain:
            for w in F.DOMAIN_NEUTRAL.get(domain, []):
                a.lexicon.pop(w, None)
        _ANALYZERS[key] = a
    return _ANALYZERS[key]


def neutralised_words(domain: str) -> list[str]:
    """The domain words that are actually in VADER's lexicon (so the note can list exactly what was dropped)."""
    std = _analyzer().lexicon
    return [w for w in F.DOMAIN_NEUTRAL.get(domain, []) if w in std]


def clean_body(text: str) -> str:
    """Strip what VADER should not score: links, quoted parent text, markdown marks."""
    if not text:
        return ""
    t = _URL.sub(" ", text)
    t = _QUOTE.sub(" ", t)
    t = _MD.sub(" ", t)
    t = t.replace("&gt;", " ").replace("&lt;", " ").replace("&amp;", " and ")
    return re.sub(r"\s+", " ", t).strip()


def score_texts(texts: list[str], domains: list | None = None) -> np.ndarray:
    """VADER scores for a list of bodies: columns compound, pos, neu, neg, compound_dn (domain-neutralised; equal to compound where no domain)."""
    std = _analyzer()
    out = np.zeros((len(texts), 5), dtype=np.float32)
    for i, t in enumerate(texts):
        c = clean_body(t)
        if not c:
            out[i, 2] = 1.0
            continue
        s = std.polarity_scores(c)
        out[i, :4] = (s["compound"], s["pos"], s["neu"], s["neg"])
        d = domains[i] if domains is not None else None
        out[i, 4] = _analyzer(d).polarity_scores(c)["compound"] if d else s["compound"]
    return out


def label(compound: np.ndarray | pd.Series, thresh: float | None = None) -> np.ndarray:
    """pos / neu / neg at VADER's ±0.05 (default) or at a stricter symmetric threshold."""
    c = np.asarray(compound, dtype=float)
    hi, lo = (F.POS_THRESH, F.NEG_THRESH) if thresh is None else (thresh, -thresh)
    return np.where(c >= hi, "pos", np.where(c <= lo, "neg", "neu"))


def _score_chunk(args):
    ids, texts, domains = args
    sc = score_texts(texts, domains)
    return ids, sc


def score_month(month: str, raw_text: Path | None = None, cache: Path | None = None, workers: int | None = None) -> Path:
    """Score every comment with text in one monthly file; cache (id, compound, pos, neu, neg, deleted) as Parquet."""
    import duckdb
    import os
    raw = (raw_text or F.RAW_TEXT) / f"{month}.parquet"
    cache_dir = cache or F.CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"sentiment_{month}.parquet"
    if out.exists():
        return out
    con = duckdb.connect()
    df = con.execute(f"SELECT id, lower(subreddit) AS subreddit, body FROM read_parquet('{raw.as_posix()}') WHERE body IS NOT NULL").df()
    deleted = df["body"].isin(["[deleted]", "[removed]"]).to_numpy()
    ids = df["id"].to_numpy()
    texts = df["body"].where(~deleted, "").tolist()
    domains = [F.DOMAIN_OF.get(s) for s in df["subreddit"]]
    n = len(texts)
    chunk = 10000
    scores = np.zeros((n, 5), dtype=np.float32)
    if n:
        # bounded parallelism: at most `w` chunks in flight, so a month never needs more than a few chunks of text in
        # worker memory at once (the fetch and DuckDB may be running beside this)
        w = workers or min(4, max(1, (os.cpu_count() or 2) - 2))
        if w == 1:   # inline (tests, notebooks): no process pool, no spawn requirements
            scores[:] = score_texts(texts, domains)
        else:
            starts = list(range(0, n, chunk))
            with ProcessPoolExecutor(max_workers=w) as ex:
                for wave in range(0, len(starts), w):
                    futs = [(st, ex.submit(_score_chunk, (ids[st:st + chunk], texts[st:st + chunk], domains[st:st + chunk]))) for st in starts[wave:wave + w]]
                    for st, fut in futs:
                        _, sc = fut.result()
                        scores[st:st + len(sc)] = sc
    res = pd.DataFrame({"id": ids, "compound": scores[:, 0], "pos": scores[:, 1], "neu": scores[:, 2], "neg": scores[:, 3],
                        "compound_dn": scores[:, 4], "deleted": deleted})
    res.to_parquet(out, index=False, compression="zstd")
    return out


def load_sentiment(months: list[str], cache: Path | None = None) -> pd.DataFrame:
    cache_dir = cache or F.CACHE
    frames = [pd.read_parquet(cache_dir / f"sentiment_{m}.parquet") for m in months if (cache_dir / f"sentiment_{m}.parquet").exists()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["id", "compound", "pos", "neu", "neg", "compound_dn", "deleted"])


# ---- keywords ---------------------------------------------------------------------------------
def _stopwords() -> set[str]:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    extra = {"http", "https", "www", "com", "amp", "gt", "lt", "deleted", "removed", "edit", "like", "just", "people", "think",
             "know", "really", "going", "don", "didn", "doesn", "isn", "ve", "ll", "yeah", "thing", "things", "way", "want",
             "got", "say", "said", "lol", "actually", "pretty", "make", "sure", "time", "good", "bad", "did", "does", "doing",
             "isnt", "dont", "didnt", "doesnt", "wasnt", "arent", "wont", "wouldnt", "couldnt", "shouldnt", "cant", "thats", "theres", "theyre",
             "youre", "hes", "shes", "whats", "ive", "youve", "weve", "theyve", "ill", "youll", "well", "hed", "itll", "lets", "yes", "yeah", "nah"}
    return set(ENGLISH_STOP_WORDS) | extra


STOP = None


def tokens(text: str) -> list[str]:
    global STOP
    if STOP is None:
        STOP = _stopwords()
    return [t for t in _TOKEN.findall(re.sub(r"[’'`]", "", clean_body(_MENTION.sub(" ", text or "")).lower())) if t not in STOP]


def term_counts(texts, min_len: int = 3) -> Counter:
    c = Counter()
    for t in texts:
        c.update(set(tok for tok in tokens(t) if len(tok) >= min_len))   # document frequency, not raw frequency
    return c


def log_odds(counts_a: Counter, counts_b: Counter, prior: Counter | None = None, alpha0: float = 500.0, min_count: int = 20,
             top: int = 20) -> list[dict]:
    """Monroe, Colaresi & Quinn (2008) log-odds ratio with an informative Dirichlet prior: words that mark A against B.

    Returns the `top` terms with the largest z-scores for A (positive) — call with swapped arguments for B.
    """
    prior = prior or (counts_a + counts_b)
    n_a, n_b, n_p = sum(counts_a.values()), sum(counts_b.values()), sum(prior.values())
    out = []
    for w in set(counts_a) | set(counts_b):
        ya, yb = counts_a.get(w, 0), counts_b.get(w, 0)
        if ya + yb < min_count:
            continue
        aw = alpha0 * prior.get(w, 0) / n_p if n_p else 0.0
        if aw <= 0:
            continue
        la = math.log((ya + aw) / (n_a + alpha0 - ya - aw))
        lb = math.log((yb + aw) / (n_b + alpha0 - yb - aw))
        var = 1.0 / (ya + aw) + 1.0 / (yb + aw)
        out.append({"term": w, "z": (la - lb) / math.sqrt(var), "count_a": ya, "count_b": yb})
    out.sort(key=lambda d: -d["z"])
    return [{**d, "z": round(d["z"], 2)} for d in out[:top]]
