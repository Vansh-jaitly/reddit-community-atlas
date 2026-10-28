"""Reproducible, data-driven construction of the sampling frame.

RULE (auditable, replaces hand-picking):
  1. Candidate universe U = every subreddit appearing in the Arctic
     2018-2022 calibration sample (2018-01, 2020-07, 2022-08) with
     n_min >= MIN_N, where n_min is the MINIMUM monthly comment count across
     those three points. Taking the minimum (not the mean) guarantees a
     community that is observable at BOTH ends of the study window, so all 19
     quarters are covered.
  2. A subreddit joins the frame only if its name matches its stratum's
     keyword rule, and it is assigned to exactly ONE stratum.
  3. Within a stratum, members are ranked by n_min and the top N are taken.
  4. The 20 highest-volume cross-cutting "default" communities form the
     gateway stratum (see FRAME_JUSTIFICATION.md, Sawicki & Ganzha 2024).
  5. MIN_N = 2000. The previous hand-picked frame had 29 of 150 members below
     this floor; rank-150 of the eligible universe still exceeds 55,000, so
     this floor is generous, not restrictive.

Every subreddit below was verified present in U. Case is matched
case-insensitively (Arctic is not case-consistent).
"""
from __future__ import annotations

import os
import re

import pandas as pd

# Minimum monthly comments at EVERY calibration point.
MIN_N = 2000

# Stratum size for the six topical strata (course synopsis Objective O1).
PER_TOPICAL = 25
# Size of the added gateway stratum.
N_GATEWAY = 20

# Calibration artifact, shipped alongside this module. Contains, for every
# subreddit observed at n_min >= SHIP_FLOOR, its monthly comment count at three
# points spanning the study window (start / middle / end) plus the derived
# n_min and n_total. Regenerate with:
#     python tools/build_frame_calibration.py
# It is trimmed at SHIP_FLOOR (below MIN_N) rather than at MIN_N so the
# threshold remains a real, checkable cut and the file stays small.
CALIBRATION_CSV = "frame_calibration.csv"
SHIP_FLOOR = 500
CALIBRATION_POINTS = ["n_2018_01", "n_2020_07", "n_2022_08"]

# --------------------------------------------------------------------------
# Keyword rules. Ordered patterns within a stratum are all OR-ed; the first
# stratum that matches a subreddit owns it, so order defines precedence.
# --------------------------------------------------------------------------
TOPICAL_RULES: dict[str, list[str]] = {
    "expertise": [
        r"science", r"physics", r"chemistry", r"biology", r"genetic", r"evolution",
        r"ecolog", r"astronom", r"space$", r"^space", r"nasa", r"geolog",
        r"geograph", r"ocean", r"meteorolog", r"climate", r"medicine", r"medical",
        r"askdocs", r"publichealth", r"epidemiolog", r"pharmac", r"nutrition",
        r"psycholog", r"neuroscien", r"philosoph", r"^logic", r"linguist",
        r"anthropolog", r"archaeolog", r"histor", r"^math", r"mathemat",
        r"statistic", r"datascien", r"machinelearn", r"artificialintelligen",
        r"^ai$", r"computerscien", r"computational", r"programming", r"^coding",
        r"^python", r"^javascript", r"^java$", r"^rust$", r"^golang", r"^go$",
        r"^swift$", r"^c\+\+", r"^csharp", r"webdev", r"software", r"engineer",
        r"^devops$", r"^sysadmin$", r"^linux$", r"^windows$", r"buildapc",
        r"^hardware$", r"^electronics$", r"cybersecurity", r"netsec", r"askmath",
        r"^calculus", r"algebra", r"geometry$", r"medieval", r"skeptic",
    ],
    "finance": [
        r"stocks", r"investing", r"^options$", r"wallstreet", r"^bogleheads",
        r"passiveinvest", r"indexinvest", r"^etf", r"mutualfund", r"^dividend",
        r"^ipo$", r"cryptocurrency", r"^bitcoin", r"ethereum", r"^defi$",
        r"^altcoin", r"^dogecoin", r"personalfinance", r"financialplan",
        r"financialindependence", r"^frugal", r"^budget", r"^savings", r"^debt",
        r"^credit$", r"creditcard", r"creditscore", r"^mortgage", r"realestate",
        r"firsttimebuyer", r"^insurance$", r"^taxes?$", r"accounting",
        r"^cpa$", r"^economics?$", r"econometric", r"^trading$", r"^forex$",
        r"commodit", r"^inflation$", r"^recession$", r"^unemployment$",
        r"^market$", r"^pension", r"retirement", r"socialsecurity", r"beermoney",
        r"sidehustle", r"swagbucks", r"^entrepreneur", r"^startups?$",
        r"smallbusiness", r"^business$", r"^ecommerce", r"dropshipping",
        r"amazonfba", r"^saas$", r"^freelance$", r"^marketing$", r"^sales$",
        r"^jobs$", r"^careers$", r"algotrading", r"^quant$", r"money",
        r"wealth", r"poverty", r"^scams?$", r"identitytheft", r"antifraud",
        r"daytrading", r"options trading", r"stocks?t",
    ],
    "hobby": [
        r"cooking", r"recipes?", r"baking", r"castiron", r"^bread$", r"^tea$",
        r"^coffee$", r"^wine$", r"beer", r"gardening", r"^plants?$",
        r"houseplant", r"succulent", r"^bonsai$", r"aquarium", r"^birds?$",
        r"beekeep", r"^chickens?$", r"woodwork", r"^diy$", r"^crafts?$",
        r"knitting", r"^sewing$", r"embroider", r"3dprint", r"3dprinting",
        r"modelmak", r"scalemodel", r"photograph", r"^landscape$", r"^travel$",
        r"^camping$", r"^hiking$", r"backpacking", r"^fishing$", r"^hunting$",
        r"cycling", r"^running$", r"^marathon$", r"triathlon", r"^fitness$",
        r"^gym$", r"workout", r"^yoga$", r"climbing", r"skateboard", r"^surfing",
        r"^skiing$", r"snowboard", r"^dogs?$", r"^cats?$", r"^puppy", r"^kitten",
        r"^pets?$", r"^horse", r"homestead", r"permaculture", r"compost",
        r"^solar$", r"^chess$", r"boardgame", r"^puzzles?$", r"solitaire",
        r"^sudoku$", r"^catan$", r"^tcg$", r"magic", r"^guitar$", r"^piano$",
        r"^bass$", r"^drums?$", r"^singing$", r"songwriting", r"^painting$",
        r"watercolo", r"^sketch", r"tattoo", r"bookbinding", r"^furniture$",
        r"^lego$", r"^pokemontcg", r"^puzzles", r"crochet", r"quilt",
        r"^origami$", r"whittling", r"model_?rail", r"amateur", r"^jets",
    ],
    "media": [
        r"^movies?$", r"^film$", r"cinema", r"moviedetails", r"^television$",
        r"^tvshows?$", r"^series$", r"^netflix$", r"^hbo$", r"^anime$",
        r"^manga$", r"^books?$", r"^literature$", r"^novels?$", r"bookclub",
        r"booksuggestion", r"suggestmeabook", r"^writing$", r"^writers?$",
        r"writingprompt", r"screenwrit", r"screenplay", r"^filmmaking$",
        r"^documentar", r"^animat", r"^cosplay$", r"^comics?$", r"marvel",
        r"^dc comics", r"starwars", r"potter", r"lordoftherings", r"gameofthrones",
        r"^music$", r"hiphop", r"^rap$", r"^metal$", r"^punk$", r"^rock$",
        r"^indie$", r"^kpop$", r"^pop$", r"classicalmusic", r"^jazz$",
        r"electronicmusic", r"indierock", r"vinyl", r"^listentothis$",
        r"wearethemusicmakers", r"makingmusic", r"^audiobooks?$", r"^audible$",
        r"^podcasts?$", r"^youtube$", r"^vlog", r"^oldschoolcool$",
        r"^retro$", r"^vintage$", r"streetwear", r"^sneakers?$", r"^boots$",
        r"malefashion", r"femalefashion", r"frugalfemalefashion", r"^thrift",
        r"^art$", r"artporn", r"^digitalart$", r"^makeup", r"skincare",
        r"^malefashionadvice", r"itookapicture", r"^ocpd$",
    ],
    "politics_news": [
        r"politic", r"news", r"conspirac", r"^changemyview$",
        r"^purplepilldebate$", r"^gunpolitics$", r"^geopolit",
        r"^immigration", r"^propaganda", r"^journalis", r"^press$",
        r"^censorship", r"^election", r"^vot", r"^ballot", r"^senate$",
        r"^congress$", r"^whitehouse$", r"^capitol", r"^nato$", r"^sanction",
        r"^refugee", r"^asylum", r"^diplomat", r"^askamerican",
        r"^moderatepolit", r"^objectivebias", r"^debunk", r"^askpolitician",
        r"^conservative", r"^democrat", r"^republican", r"^liberal$",
        r"^progressive", r"^socialis", r"^communism", r"^anarchis",
        r"^libertarian", r"^capitalis", r"neoliberal", r"^trump", r"^biden$",
        r"^obama", r"^worldnews$", r"^media$",
    ],
    "support": [
        r"^anxiety$", r"^depression$", r"^mentalhealth$", r"^addiction$",
        r"^recovery$", r"^alcoholism$", r"^sober", r"^stopdrinking",
        r"^quits?moking", r"^quits?vaping", r"^smoking$", r"^selfhelp",
        r"selfimprove", r"^motivation$", r"^insomnia$", r"^sleep$",
        r"^ocd$", r"^adhd$", r"^autism$", r"^bipolar", r"schizophreni",
        r"^ptsd$", r"^cpTSD$".lower(), r"^trauma$", r"chronicpain",
        r"chronicillness", r"fibromyalgia", r"^ibs$", r"crohns", r"^epilep",
        r"^migraine$", r"^disabilit", r"accessibility", r"^divorce$",
        r"^relationship_advice$", r"^relationships$", r"^parenting$",
        r"^momofmany", r"^childfree$", r"^adoption$", r"fostercare",
        r"^grief$", r"^lonely$", r"socialanxiety", r"panicattack",
        r"suicide", r"depressionadvice", r"caregiver", r"^hospice$",
        r"eldercare", r"alzheim", r"borderlineperson", r"toxicrelations",
        r"codepend", r"^homeschool", r"^specialed$", r"neurodivergent",
        r"^offmychest$", r"^lostit$", r"^nohelp$", r"^sanitycheck$",
    ],
}

# Regional / country news communities, used ONLY to top up the politics_news
# stratum once its primary political/news rule has supplied PRIMARY_TAKE
# members. Ranking on volume alone would otherwise fill the stratum with
# country subs (canada 158k, europe 159k, Philippines 139k all outrank most
# political communities), which would mislabel a regional-news sample as a
# political one. The two-tier rule keeps the stratum coherent and reproducible.
TOPICAL_FALLBACK: dict[str, list[str]] = {
    "politics_news": [
        r"^canada$", r"^australia$", r"^ireland$", r"^india$", r"^mexico$",
        r"^philippines$", r"^argentina$", r"^singapore$", r"^southafrica$",
        r"^turkey$", r"^japan$", r"^korea$", r"^brazil$", r"^brasil$",
        r"^newzealand$", r"^sweden$", r"^italy$", r"^france$", r"^germany$",
        r"^spain$", r"^europe$", r"^norway$", r"^denmark$", r"^finland$",
        r"^netherlands$", r"^poland$", r"^switzerland$", r"^portugal$",
        r"^greece$", r"^russia$", r"^china$", r"^israel$", r"^iran$",
        r"^ukraine$", r"^pakistan$", r"^nigeria$", r"^egypt$",
    ],
}

# How many members each stratum draws from its primary rule before the
# fallback patterns are allowed to top it up.
PRIMARY_TAKE = 20

# --------------------------------------------------------------------------
# Hand-review exclusions. Keyword rules necessarily over-match: they cannot
# tell r/HistoryPorn (an art sub) from r/AskHistorians, or r/FrankOcean from
# astronomy. Every name below was selected by a rule and then REJECTED on
# review. This list is the "hand-review to remove misfits" step of the
# construction, made explicit and auditable rather than hidden in someone's
# memory of Reddit. Each entry states why it was dropped, so a reviewer can
# disagree with a specific call instead of re-deriving the whole frame.
# --------------------------------------------------------------------------
EXCLUDE: dict[str, str] = {
    "historyporn": "art/erotic-history sub; matched the 'histor' rule",
    "fakehistoryporn": "art sub; matched the 'histor' rule",
    "softwaregore": "shock-content sub; matched the 'software' rule",
    "asksciencefiction": "sci-fi literature; belongs in media, not science",
    "frankocean": "musician; matched the 'ocean' rule",
    "malelivingspace": "dating sub; matched the 'space' rule",
    "buildapcsales": "hardware sales marketplace, not a knowledge community",
    "budgetaudiophile": "hi-fi gear; matched the 'budget' rule",
    "frugalmalefashion": "fashion; matched the 'frugal' rule",
    "blackmagicfuckery": "personal/tattoo sub; matched the 'magic' rule",
    "gamernews": "gaming news; belongs in media",
    "dc_cinematic": "film studio fan sub; matches media but not a community of practice",
    "consoles": "console fan sub; gaming belongs in media",
    "relationships": "kept out of support: overlaps too heavily with media/dating",
    "exmormon": "religion/exit community; not one of the six analytical strata",
    "atheism": "religion debate; not one of the six analytical strata",
    "christianity": "religion; not one of the six analytical strata",
    "guns": "firearms enthusiast sub; not a knowledge or support community",
    "legaladvice": "legal advice; overlaps support but is a distinct service",
    "historymemes": "meme sub; matched the 'histor' rule",
}

# Cross-cutting "default" communities. These are not about a topic; they are
# where cross-cutting traffic goes. Sawicki & Ganzha (2024) find that on Reddit
# nearly all bridges are also gateways, so excluding this class deletes the
# object of study by construction.
GATEWAY_SEED = [
    "AskReddit", "worldnews", "funny", "mildlyinteresting", "pics",
    "todayilearned", "aww", "Showerthoughts", "interestingasfuck", "RoastMe",
    "nottheonion", "NoStupidQuestions", "starterpacks", "LifeProTips",
    "dataisbeautiful", "videos", "PublicFreakout", "mildlyinfuriating",
    "tifu", "oddlysatisfying",
]

# Rule precedence for ownership: the most specific/analytically distinct
# strata claim a subreddit first, so "space" lands in expertise rather than
# hobby, and a politics sub cannot be claimed by a looser pattern.
PRECEDENCE = ["expertise", "finance", "support", "media", "hobby",
              "politics_news"]


def _with_key(pool: pd.DataFrame) -> pd.DataFrame:
    """Ensure the case-folded `key` column exists and is the unique index."""
    p = pool.copy()
    if "key" not in p.columns:
        p["key"] = p.subreddit.str.lower()
    p = p.sort_values("n_min", ascending=False).drop_duplicates("key")
    return p


def load_pool(path: str | None = None) -> pd.DataFrame:
    """Load the shipped calibration table and recompute n_min defensively."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                CALIBRATION_CSV)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"missing {path}. Regenerate with "
            f"`python tools/build_frame_calibration.py`, which counts monthly "
            f"subreddit volume over all Arctic shards at the three calibration "
            f"points.")
    w = pd.read_csv(path)
    # Case-insensitive collapse: Arctic stores several spellings inconsistently
    # ("Cooking" vs "cooking"), so collapse on the lowercased name.
    return _with_key(w)


def classify(name: str, rules: dict[str, list[str]]) -> str | None:
    """First stratum (in PRECEDENCE order) whose rules match, else None."""
    n = name.lower()
    for stratum in PRECEDENCE:
        for pat in rules[stratum]:
            if re.search(pat, n):
                return stratum
    return None


def classify_fallback(name: str) -> str | None:
    """First stratum whose FALLBACK rule matches, else None."""
    n = name.lower()
    for stratum in PRECEDENCE:
        for pat in TOPICAL_FALLBACK.get(stratum, []):
            if re.search(pat, n):
                return stratum
    return None


def build_frame(pool: pd.DataFrame | None = None, min_n: int = MIN_N,
                per_topical: int = PER_TOPICAL,
                n_gateway: int = N_GATEWAY,
                primary_take: int = PRIMARY_TAKE) -> pd.DataFrame:
    """Return the full frame as a DataFrame(subreddit, stratum, n_min, n_total)."""
    pool = _with_key(load_pool() if pool is None else pool)
    universe = pool[pool.n_min >= min_n]

    # Gateway stratum first, so hubs cannot be claimed by a topical rule.
    gseed = {g.lower() for g in GATEWAY_SEED}
    gateway = universe[universe.key.isin(gseed)].nlargest(n_gateway, "n_min")
    claimed = set(gateway.key)

    rest = universe[~universe.key.isin(claimed)].copy()
    dropped = rest.key.isin({k.strip() for k in EXCLUDE})
    if dropped.any():
        rest = rest[~dropped]
    rest["stratum"] = [classify(s, TOPICAL_RULES) for s in rest.subreddit]
    rest["via"] = "primary"
    rest.loc[rest.stratum.isna(), "via"] = None

    # Strata with fallback patterns also draw from subs that matched no primary
    # rule at all (e.g. country subs for politics_news). Label those too,
    # respecting the same precedence order, so they can be ranked as fallbacks.
    unlabelled = rest[rest.stratum.isna()].copy()
    unlabelled["stratum"] = [classify_fallback(s) for s in unlabelled.subreddit]
    unlabelled["via"] = "fallback"
    remaining = pd.concat([rest[rest.stratum.notna()],
                           unlabelled[unlabelled.stratum.notna()]])

    frames = [gateway.assign(stratum="gateway")]
    for stratum in PRECEDENCE:
        pool_for = remaining[remaining.stratum == stratum].copy()
        # Prefer members matched by the stratum's PRIMARY rule, ranked by
        # volume; only spill into the fallback patterns once the primary rule
        # is exhausted. Ranking on volume alone would otherwise fill
        # politics_news with country subs (canada 158k, europe 159k all outrank
        # most political communities), mislabelling a regional-news sample as a
        # political one. An earlier version capped primaries at PRIMARY_TAKE and
        # then topped up from fallback patterns in pattern order, which silently
        # discarded higher-volume primary matches (e.g. UpliftingNews, 38k).
        if TOPICAL_FALLBACK.get(stratum):
            pool_for["via_rank"] = (pool_for.via != "primary").astype(int)
        else:
            pool_for["via_rank"] = 0
        sel = (pool_for.sort_values(["via_rank", "n_min"], ascending=[True, False])
               .head(per_topical))
        if len(sel) < per_topical:
            raise ValueError(
                f"stratum {stratum!r} matched only {len(sel)} of the required "
                f"{per_topical} at n_min>={min_n}. Broaden its keyword rule or "
                f"lower min_n; do not hand-pick silently.")
        frames.append(sel)

    out = pd.concat(frames).sort_values(["stratum", "n_min"], ascending=[True, False])
    return out.reset_index(drop=True)[["subreddit", "stratum", "n_min", "n_total"]]
