"""Paths, subreddit sets, windows and thresholds for the Findings section.

Everything the Findings builders publish is derived from two local stores:
  data_curation/data/clean/*.parquet      all 170 frame subreddits, no text (the Atlas data)
  data_curation/data/raw_text/*.parquet   text + reply structure for the Findings subreddits (fetch_text.py)
and one small public series (Bitcoin price, see events.py).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_TEXT = ROOT / "data_curation" / "data" / "raw_text"
CLEAN = ROOT / "data_curation" / "data" / "clean"
CACHE = ROOT / "data_curation" / "data" / "findings_cache"
OUT = ROOT / "atlas" / "web" / "data" / "findings"
DOCS = ROOT / "docs"

MONTHS = ["2017-10", "2017-11", "2017-12", "2018-01", "2018-02", "2018-03",
          "2018-04", "2018-05", "2018-06", "2018-07", "2018-08", "2018-09"]

# VADER's documented thresholds for the compound score
POS_THRESH, NEG_THRESH = 0.05, -0.05
STRICT_THRESH = 0.3           # sensitivity labelling: only clearly polar comments count as positive/negative

# ---- event stories -----------------------------------------------------------------------------
# Windows are UTC calendar dates, inclusive. Infinity War: 7 weeks before, a 3-week release window
# (world premiere 23 Apr, US release 27 Apr, first two weekends), 7 weeks after, so "before" and
# "after" are the same length and the release window isolates the surge.
EVENTS = {
    "infinity_war": {
        "title": "Infinity War: the Reddit reaction",
        "subs": ["marvelstudios", "marvel"],
        "context_subs": ["movies", "comics"],
        "anchor_date": "2018-04-27",
        "anchor_label": "Avengers: Infinity War US release",
        "windows": {"before": ("2018-03-02", "2018-04-19"), "release": ("2018-04-20", "2018-05-10"), "after": ("2018-05-11", "2018-06-28")},
    },
    "bitcoin": {
        "title": "Bitcoin: when market optimism changed",
        "subs": ["bitcoin", "cryptocurrency", "ethereum", "dogecoin", "bitcoinbeginners"],
        "context_subs": ["investing", "wallstreetbets"],
        "anchor_date": "2017-12-17",
        "anchor_label": "Bitcoin price peak",
        # phases are derived from the price series in events.py (peak, first trough, rebound, ...); months are the unit of network comparison
        "windows": None,
    },
}

# ---- focused-community candidates (reply structure fetched for all; text for the first four) ---
CANDIDATES = ["capitalismvsocialism", "purplepilldebate", "australianpolitics", "thewallstreet",
              "changemyview", "canadapolitics", "custommagic", "kpop", "askphilosophy", "askhistorians",
              "medicalschool", "rust", "chess", "newsokunomoral"]
TEXT_SUBS = ["marvelstudios", "marvel", "bitcoin", "cryptocurrency", "ethereum", "dogecoin", "bitcoinbeginners",
             "capitalismvsocialism", "purplepilldebate", "australianpolitics", "thewallstreet"]

# ---- network construction ------------------------------------------------------------------------
MIN_REPLIES_NODE = 2          # a user enters a reply network with at least this many reply edges (in or out)
FOCUS_MAX_NODES = 150         # readable focused network: raise the k-core until at most this many nodes remain
FOCUS_MIN_NODES = 30
LEIDEN_SEEDS = 30
LEIDEN_RESOLUTION = 1.0

# Words with VADER valence that are topic vocabulary in these communities (plot talk, price moves) rather than opinion;
# the domain-neutralised score drops them from the lexicon. Both scores are published; the event stories use the
# neutralised one and show the standard one beside it.
DOMAIN_NEUTRAL = {
    "marvel": ["kill", "killed", "killing", "kills", "die", "died", "dies", "dying", "death", "deaths", "dead", "war", "wars", "villain", "villains",
               "destroy", "destroyed", "destruction", "cry", "cried", "crying", "fight", "fights", "fighting", "fought", "battle", "battles", "lose",
               "lost", "loss", "losses", "pain", "evil", "hell", "dark", "blood", "weapon", "weapons", "attack", "attacks", "murder", "threat",
               "threats", "sacrifice", "sacrifices", "snap", "sick", "insane", "crazy", "fear", "scared", "monster", "doom", "stone", "stones"],
    "crypto": ["crash", "crashed", "crashes", "crashing", "dump", "dumped", "dumping", "dumps", "bubble", "bubbles", "bear", "bull", "dip", "dips",
               "sick", "insane", "crazy", "loss", "losses", "lose", "lost", "losing", "fall", "falls", "falling", "fell", "drop", "drops", "dropped",
               "dropping", "low", "lows", "high", "highs", "gain", "gains", "gained", "profit", "profits", "fees", "fee", "cheap", "free"],
}
DOMAIN_OF = {"marvelstudios": "marvel", "marvel": "marvel", "bitcoin": "crypto", "cryptocurrency": "crypto", "ethereum": "crypto", "dogecoin": "crypto", "bitcoinbeginners": "crypto"}

# ---- insight thresholds (documented in docs/FINDINGS_METHODOLOGY.md) ----------------------------
SURGE_Z = 3.0                 # daily volume more than 3 robust z-scores above the pre-window median
MIN_EFFECT_D = 0.10           # smallest standardised sentiment difference we call a shift
ALPHA = 0.001                 # permutation / bootstrap significance level for insights
NEWCOMER_LOOKBACK = {"infinity_war": 5, "bitcoin": 2}   # months before a period in which a "newcomer" was not active there: the longest lookback the store allows for the earliest compared period
PERMUTATIONS = 1000
REWIRINGS = 100              # degree-preserving rewirings behind broker and E-I significance
CAMP_MIXING_Z = 3.0          # camp-mixing insight fires when the E-I index is at least this many null SDs from its rewiring mean
CAMP_MIXING_HIGH_Z = 5.0     # "high" confidence needs |z| >= this and a two-sided p <= CAMP_MIXING_HIGH_P (100 rewirings floor p at 1/101)
CAMP_MIXING_HIGH_P = 0.01
BIG_N = 6000                 # above this many users betweenness is sampled and closeness/eigenvector are skipped (the focused community stays exact)
REWIRE_MAX_N = 3000          # rewiring-based broker tests above this size are replaced by a degree-matched percentile
BETWEENNESS_SOURCES = 2000   # source sample for estimated betweenness on large graphs
