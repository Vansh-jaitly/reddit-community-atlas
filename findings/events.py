"""Event stories: daily series, windows, sentiment comparisons, change points and price alignment.

Statistical stance: windows are compared descriptively with effect sizes and resampling (bootstrap CIs, permutation
tests). Comments by the same user are not independent, so every comparison is also run on per-user means. Nothing
here claims that an event caused a change; the outputs are temporal associations with stated uncertainty.
"""
from __future__ import annotations

import csv
import datetime as dt
import math

import numpy as np
import pandas as pd

from . import config as F
from . import io as IO
from . import text as T


# ---- series --------------------------------------------------------------------------------------
def scored_comments(subs: list[str], start: str, end: str, raw_text=None, cache=None, with_text: bool = False) -> pd.DataFrame:
    """Comments with their cached VADER scores (text subreddits only); unscored rows keep NaN compound.

    with_text=True also carries the body (needed for keyword contrasts); it never leaves the machine."""
    df = IO.comments(subs, start, end, raw_text=raw_text)
    if with_text:
        bodies = IO.comments(subs, start, end, columns=["id", "body"], with_text=True, raw_text=raw_text)
        df = df.merge(bodies, on="id", how="left")
    sent = T.load_sentiment(IO.months_covering(start, end), cache=cache)
    df = df.merge(sent, on="id", how="left")
    df["day"] = pd.to_datetime(df["created_utc"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    df["label"] = np.where(df["compound"].isna(), None, T.label(df["compound"].fillna(0)))
    df["label_strict"] = np.where(df["compound"].isna(), None, T.label(df["compound"].fillna(0), F.STRICT_THRESH))
    df.loc[df["deleted"] == True, ["compound", "label", "label_strict"]] = [np.nan, None, None]   # noqa: E712 - deleted bodies carry no opinion
    return df


def daily_series(df: pd.DataFrame) -> pd.DataFrame:
    """Per subreddit and UTC day: comments, commenters, replies, scored comments and sentiment shares."""
    g = df.groupby(["subreddit", "day"])
    out = g.agg(comments=("id", "size"), commenters=("author_h", "nunique"),
                replies=("parent_id", lambda s: int(s.str.startswith("t1_", na=False).sum())),
                scored=("compound", "count"), mean_compound=("compound", "mean")).reset_index()
    lab = df.dropna(subset=["label"]).groupby(["subreddit", "day"])["label"].value_counts(normalize=True).unstack(fill_value=0.0)
    lab = lab.reindex(columns=["pos", "neu", "neg"], fill_value=0.0).reset_index().rename(columns={"pos": "pos_share", "neu": "neu_share", "neg": "neg_share"})
    out = out.merge(lab, on=["subreddit", "day"], how="left")
    out["mean_compound"] = out["mean_compound"].round(4)
    for c in ("pos_share", "neu_share", "neg_share"):
        out[c] = out[c].round(4)
    return out


def all_days(start: str, end: str) -> list[str]:
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    return [(s + dt.timedelta(days=k)).isoformat() for k in range((e - s).days + 1)]


def robust_z(values: np.ndarray, baseline: np.ndarray) -> np.ndarray:
    """(x - median) / (1.4826 * MAD) against a baseline sample: outlier-resistant surge detection."""
    med = np.median(baseline)
    mad = np.median(np.abs(baseline - med)) * 1.4826
    if mad == 0:
        mad = np.std(baseline) or 1.0
    return (np.asarray(values, dtype=float) - med) / mad


# ---- comparisons ---------------------------------------------------------------------------------
def compare(a: np.ndarray, b: np.ndarray, permutations: int = F.PERMUTATIONS, seed: int = 11) -> dict:
    """Difference of means b - a with Cohen's d, a bootstrap 95% CI and a two-sided permutation p-value."""
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) < 2 or len(b) < 2:
        return {"n_a": int(len(a)), "n_b": int(len(b)), "diff": None}
    rng = np.random.default_rng(seed)
    diff = float(b.mean() - a.mean())
    sp = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2)) or 1e-9
    boots = []
    for _ in range(500):
        boots.append(rng.choice(b, len(b)).mean() - rng.choice(a, len(a)).mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    pooled = np.concatenate([a, b])
    count = 0
    for _ in range(permutations):
        rng.shuffle(pooled)
        if abs(pooled[len(a):].mean() - pooled[:len(a)].mean()) >= abs(diff):
            count += 1
    return {"n_a": int(len(a)), "n_b": int(len(b)), "mean_a": round(float(a.mean()), 4), "mean_b": round(float(b.mean()), 4),
            "diff": round(diff, 4), "cohen_d": round(diff / sp, 3), "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "p_perm": round((count + 1) / (permutations + 1), 4)}


def compare_shares(labels_a, labels_b, cls: str = "neg", permutations: int = F.PERMUTATIONS, seed: int = 11) -> dict:
    """Difference in the share of class `cls` (b - a) with Cohen's h, a bootstrap 95% CI and a permutation p-value."""
    a = np.asarray([x == cls for x in labels_a if x is not None], dtype=float)
    b = np.asarray([x == cls for x in labels_b if x is not None], dtype=float)
    if len(a) < 2 or len(b) < 2:
        return {"n_a": int(len(a)), "n_b": int(len(b)), "diff": None}
    rng = np.random.default_rng(seed)
    pa, pb = float(a.mean()), float(b.mean())
    h = 2 * math.asin(math.sqrt(pb)) - 2 * math.asin(math.sqrt(pa))
    boots = [rng.choice(b, len(b)).mean() - rng.choice(a, len(a)).mean() for _ in range(500)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    pooled = np.concatenate([a, b]); cnt = 0
    for _ in range(permutations):
        rng.shuffle(pooled)
        if abs(pooled[len(a):].mean() - pooled[:len(a)].mean()) >= abs(pb - pa):
            cnt += 1
    return {"class": cls, "n_a": int(len(a)), "n_b": int(len(b)), "share_a": round(pa, 4), "share_b": round(pb, 4), "diff": round(pb - pa, 4),
            "cohen_h": round(h, 3), "ci95": [round(float(lo), 4), round(float(hi), 4)], "p_perm": round((cnt + 1) / (permutations + 1), 4)}


def its_level_change(counts: np.ndarray, days: list[str], break_day: str) -> dict:
    """Segmented regression of log(1 + daily comments) on time, a post-break level shift, a post-break slope change and
    day-of-week dummies (Bernal, Cummins & Gasparrini 2017). Returns the level-shift coefficient as a multiplicative change."""
    y = np.log1p(np.asarray(counts, dtype=float))
    n = len(y)
    if n < 21:
        return {}
    t = np.arange(n, dtype=float)
    post = np.array([1.0 if d >= break_day else 0.0 for d in days])
    if post.sum() < 3 or (1 - post).sum() < 7:
        return {}
    t_post = post * np.maximum(0, t - np.argmax(post))
    dow = np.array([dt.date.fromisoformat(d).weekday() for d in days])
    X = np.column_stack([np.ones(n), t, post, t_post] + [(dow == k).astype(float) for k in range(1, 7)])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res, ss_tot = float((resid ** 2).sum()), float(((y - y.mean()) ** 2).sum()) or 1.0
    dof = max(1, n - X.shape[1])
    cov = np.linalg.pinv(X.T @ X) * (ss_res / dof)
    se = float(np.sqrt(max(cov[2, 2], 0)))
    # Newey-West (Bartlett kernel) standard error: daily residuals are autocorrelated, which the OLS error ignores
    lags = int(np.floor(4 * (n / 100) ** (2 / 9)))
    xtx_inv = np.linalg.pinv(X.T @ X)
    u = resid[:, None] * X
    S = u.T @ u
    for lag in range(1, lags + 1):
        G = u[lag:].T @ u[:-lag]
        S += (1 - lag / (lags + 1)) * (G + G.T)
    cov_hac = xtx_inv @ S @ xtx_inv
    se_hac = float(np.sqrt(max(cov_hac[2, 2], 0)))
    r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if n > 3 else None
    return {"level_change_log": round(float(beta[2]), 4), "level_change_pct": round(float(np.expm1(beta[2])), 4), "se": round(se, 4),
            "t": round(float(beta[2] / se), 2) if se else None, "se_hac": round(se_hac, 4), "t_hac": round(float(beta[2] / se_hac), 2) if se_hac else None, "hac_lags": lags, "slope_change_log_per_day": round(float(beta[3]), 5), "r2": round(1 - ss_res / ss_tot, 3),
            "residual_lag1_autocorr": None if r1 is None else round(r1, 3), "n_days": n, "break_day": break_day}


def integrity_screen(daily_total: pd.Series, factor: float = 0.5) -> list[str]:
    """Days whose total comments across the whole frame fall below `factor` x the median: likely archive gaps, listed as caveats."""
    if daily_total.empty:
        return []
    med = float(daily_total.median())
    return sorted(str(d) for d, v in daily_total.items() if v < factor * med)


def window_slices(df: pd.DataFrame, windows: dict[str, tuple[str, str]]) -> dict[str, pd.DataFrame]:
    return {name: df[(df["day"] >= a) & (df["day"] <= b)] for name, (a, b) in windows.items()}


def window_summary(df: pd.DataFrame, windows: dict[str, tuple[str, str]], hist: pd.DataFrame | None = None, lookback_months: int | None = None) -> list[dict]:
    """Per window and subreddit: volume, commenters, newcomers, sentiment shares, mean compound with CI (comment- and user-level).
    Newcomers need `hist` (subreddit, author_h, day for the whole store) and a fixed lookback in months: a newcomer is a user
    not active in that subreddit during the `lookback_months` before the window, so every window is measured on the same footing."""
    rows = []
    for name, part in window_slices(df, windows).items():
        for sub, d in part.groupby("subreddit"):
            scored = d.dropna(subset=["compound"])
            users = scored.groupby("author_h")["compound"].mean()
            lab = scored["label"].value_counts(normalize=True)
            days = max(1, (dt.date.fromisoformat(windows[name][1]) - dt.date.fromisoformat(windows[name][0])).days + 1)
            new = None
            if hist is not None and lookback_months:
                lb = lookback_start(windows[name][0], lookback_months)
                before = active_users(hist, sub, lb, (pd.Timestamp(windows[name][0]) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")) if lb else None
                new = newcomer_share(d["author_h"].dropna().unique(), before)
            rows.append({"window": name, "subreddit": sub, "start": windows[name][0], "end": windows[name][1], "days": days,
                         "comments": int(len(d)), "comments_per_day": round(len(d) / days, 1), "commenters": int(d["author_h"].nunique()),
                         "newcomer_share": new,
                         "scored": int(len(scored)), "mean_compound": round(float(scored["compound"].mean()), 4) if len(scored) else None,
                         "mean_compound_std": round(float(scored["compound_std"].mean()), 4) if ("compound_std" in scored and len(scored)) else None,
                         "neg_share_ci95": _share_ci(scored["label"].to_numpy() == "neg") if len(scored) else None,
                         "neg_share_strict": round(float((scored["label_strict"] == "neg").mean()), 4) if ("label_strict" in scored and len(scored)) else None,
                         "pos_share_strict": round(float((scored["label_strict"] == "pos").mean()), 4) if ("label_strict" in scored and len(scored)) else None,
                         "user_mean_compound": round(float(users.mean()), 4) if len(users) else None,
                         "pos_share": round(float(lab.get("pos", 0)), 4), "neu_share": round(float(lab.get("neu", 0)), 4), "neg_share": round(float(lab.get("neg", 0)), 4)})
    return rows


def _share_ci(flags: np.ndarray, seed: int = 2) -> list[float]:
    rng = np.random.default_rng(seed)
    f = np.asarray(flags, dtype=float)
    boots = [rng.choice(f, len(f)).mean() for _ in range(300)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def lookback_start(start: str, months: int, store_start: str | None = None) -> str | None:
    """First day of the fixed lookback of `months` calendar months before `start`; None when it would reach before the store
    begins (a period compared against a shorter history counts too many users as new: left-censoring)."""
    store_start = store_start or (F.MONTHS[0] + "-01")
    lb = (pd.Timestamp(start) - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    return lb if lb >= store_start else None


def newcomer_share(active_now, active_before) -> float | None:
    """Share of the users active in a period who were not active in its fixed lookback. None when the lookback is undefined
    (`active_before` is None) or nobody was active; rounded to three places."""
    if active_before is None:
        return None
    now = set(active_now)
    if not now:
        return None
    return round(1.0 - len(now & set(active_before)) / len(now), 3)


def active_users(hist: pd.DataFrame, sub: str, start: str, end: str) -> set:
    """Users with at least one comment in `sub` between `start` and `end` (inclusive 'YYYY-MM-DD' days)."""
    h = hist[(hist["subreddit"] == sub) & (hist["day"] >= start) & (hist["day"] <= end)]
    return set(h["author_h"].dropna().unique())


# ---- change points -------------------------------------------------------------------------------
def change_points(y: np.ndarray, max_points: int = 3, min_size: int = 7, penalty: float | None = None) -> list[int]:
    """Binary segmentation on mean shifts with a BIC-style penalty; returns split indices (start of a new segment)."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 2 * min_size:
        return []
    pen = penalty if penalty is not None else 2.0 * np.log(n) * (y.var() or 1.0)

    def cost(seg):
        return ((seg - seg.mean()) ** 2).sum()

    splits = []
    segments = [(0, n)]
    while len(splits) < max_points:
        best = None
        for (s, e) in segments:
            if e - s < 2 * min_size:
                continue
            base = cost(y[s:e])
            for k in range(s + min_size, e - min_size + 1):
                gain = base - cost(y[s:k]) - cost(y[k:e])
                if best is None or gain > best[0]:
                    best = (gain, k, (s, e))
        if best is None or best[0] < pen:
            break
        gain, k, (s, e) = best
        splits.append(k)
        segments.remove((s, e))
        segments += [(s, k), (k, e)]
    return sorted(splits)


# ---- price -----------------------------------------------------------------------------------------
def price_series() -> pd.DataFrame:
    p = F.ROOT / "findings" / "data" / "btc_price_daily.csv"
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    return pd.DataFrame({"day": [r["date"] for r in rows], "price": [float(r["price_usd"]) for r in rows]})


def price_extrema(price: pd.DataFrame, min_swing: float = 0.25) -> list[dict]:
    """Zigzag filter: alternating peaks and troughs, each confirmed by a move of at least `min_swing` the other way."""
    days, p = price["day"].tolist(), price["price"].to_numpy(dtype=float)
    if len(p) < 2:
        return []
    ext = [{"day": days[0], "price": float(p[0]), "type": "start"}]
    cand_i, direction = 0, None          # direction: +1 looking for a peak (price rising), -1 looking for a trough
    for i in range(1, len(p)):
        if direction is None:
            if p[i] >= p[0] * (1 + min_swing):
                direction, cand_i = 1, i
            elif p[i] <= p[0] * (1 - min_swing):
                direction, cand_i = -1, i
            continue
        if direction > 0:
            if p[i] > p[cand_i]:
                cand_i = i
            elif p[i] <= p[cand_i] * (1 - min_swing):
                ext.append({"day": days[cand_i], "price": float(p[cand_i]), "type": "peak"}); direction, cand_i = -1, i
        else:
            if p[i] < p[cand_i]:
                cand_i = i
            elif p[i] >= p[cand_i] * (1 + min_swing):
                ext.append({"day": days[cand_i], "price": float(p[cand_i]), "type": "trough"}); direction, cand_i = 1, i
    if direction is not None and cand_i != len(p) - 1:
        ext.append({"day": days[cand_i], "price": float(p[cand_i]), "type": "peak" if direction > 0 else "trough", "unconfirmed": True})
    ext.append({"day": days[-1], "price": float(p[-1]), "type": "end"})
    return ext


def price_phases(ext: list[dict]) -> list[dict]:
    out = []
    for a, b in zip(ext, ext[1:]):
        chg = b["price"] / a["price"] - 1
        out.append({"start": a["day"], "end": b["day"], "from": a["type"], "to": b["type"], "change": round(chg, 3),
                    "label": ("run-up" if chg > 0 and a["type"] == "start" else "rebound" if chg > 0 else "decline")})
    seen = {}
    for ph in out:   # a second decline/rebound gets a number so phase names stay unique
        base = ph["label"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            ph["label"] = f"{base} {seen[base]}"
    return out


def lagged_rank_correlation(x: pd.Series, y: pd.Series, lags=range(-7, 8)) -> list[dict]:
    """Spearman correlation between two aligned daily series at several lags (positive lag: x leads y)."""
    from scipy.stats import spearmanr
    out = []
    for lag in lags:
        if lag >= 0:
            a, b = x.iloc[:len(x) - lag] if lag else x, y.iloc[lag:]
        else:
            a, b = x.iloc[-lag:], y.iloc[:len(y) + lag]
        a, b = a.to_numpy(), b.to_numpy()
        ok = ~(np.isnan(a) | np.isnan(b))
        if ok.sum() > 10:
            r, p = spearmanr(a[ok], b[ok])
            out.append({"lag": int(lag), "rho": round(float(r), 3), "p": float(f"{p:.2g}"), "n": int(ok.sum())})
    return out
