"""
affinity.py
===========
Activity-adjusted audience affinity between subreddits, and the statistically
validated subreddit network used by the Community Atlas.

WHY THIS MODULE REPLACES COSINE AS THE PRIMARY RELATIONSHIP MEASURE
-------------------------------------------------------------------
Projecting the user x subreddit matrix with cosine similarity produced a
99.85%-dense graph on the real 2018 data (V1 baseline). Every user active in k
subreddits adds a k-clique to a projection, so a few very active accounts link
almost every pair, and large "gateway" subreddits look close to everything.

Here a relationship is instead judged against what user activity and
subreddit size alone would produce:

    expected shared commenters E_ab = sum over users u of p_ua * p_ub

where p_us is the probability that user u comments in subreddit s under the
Bipartite Configuration Model (BiCM; Saracco et al. 2015, Sci. Rep. 5:10595).
BiCM keeps every user's number of subreddits and every subreddit's number of
users on average and randomises everything else:

    p_us = x_u * y_s / (1 + x_u * y_s),  sum_s p_us = k_u,  sum_u p_us = k_s

Two derived quantities:
  * affinity_ab = observed shared commenters / E_ab  (1.0 = what chance gives)
  * an edge a-b is VALIDATED when the observed count is improbably high under
    the model: one-sided Poisson p-value (the reference `bicm` package's
    default approximation of the Poisson-binomial), corrected for testing all
    S(S-1)/2 pairs with Benjamini-Hochberg FDR (Saracco et al. 2017, NJP 19).

Users with the same degree share the same multiplier, so the fit has at most
(#distinct user degrees + #subreddits) unknowns regardless of user count.

Validated against the reference implementation (`bicm` 3.4.0) on a real
150,000-user sample: identical validated edge sets and p-values agreeing to
~1e-12; see tools/crosscheck_bicm_reference.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.stats import poisson


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def presence_matrix(user_idx, sub_idx, n_users: int, n_subs: int) -> sp.csr_matrix:
    """Binary user x subreddit presence matrix.

    Duplicate (user, subreddit) records -- e.g. one row per comment or per
    month -- collapse to a single 1. scipy keeps duplicates as separate stored
    entries until they are summed, and an unsummed matrix silently inflates
    degrees past the number of subreddits, which makes the model infeasible.
    """
    M = sp.csr_matrix(
        (np.ones(len(user_idx), dtype=np.float64), (np.asarray(user_idx), np.asarray(sub_idx))),
        shape=(n_users, n_subs),
    )
    M.sum_duplicates()
    M.data[:] = 1.0
    M.eliminate_zeros()
    return M


def load_presence(
    parquet_paths: list[str | Path],
    subreddits: list[str] | None = None,
    min_comments: int = 1,
    where: str | None = None,
    con=None,
) -> tuple[sp.csr_matrix, list[str]]:
    """Load a presence matrix from cleaned Parquet files with DuckDB.

    Args:
        parquet_paths: cleaned quarterly files (columns author_h, subreddit, created_utc).
        subreddits: fixed column order; defaults to the sorted subreddits present.
        min_comments: a user counts as present in a subreddit only with at least
            this many comments there in the window (1 = any comment).
        where: optional SQL predicate on the raw rows, e.g. a created_utc range.
    """
    import duckdb

    own = con is None
    con = con or duckdb.connect()
    files = ", ".join("'" + str(p).replace("\\", "/") + "'" for p in parquet_paths)
    filt = f"WHERE {where}" if where else ""
    df = con.execute(f"""
        WITH pairs AS (
            SELECT author_h, subreddit FROM read_parquet([{files}]) {filt}
            GROUP BY 1, 2 HAVING COUNT(*) >= {int(min_comments)}
        )
        SELECT (DENSE_RANK() OVER (ORDER BY author_h))::INTEGER - 1 AS u, subreddit FROM pairs
    """).df()
    if own:
        con.close()
    if subreddits is None:
        subreddits = sorted(df["subreddit"].unique())
    col = {s: j for j, s in enumerate(subreddits)}
    df = df[df["subreddit"].isin(col)]
    n_users = int(df["u"].max()) + 1 if len(df) else 0
    return presence_matrix(df["u"].values, df["subreddit"].map(col).values, n_users, len(subreddits)), list(subreddits)


# ---------------------------------------------------------------------------
# BiCM fit
# ---------------------------------------------------------------------------
@dataclass
class BiCMFit:
    """Fitted BiCM, with users grouped by degree.

    p[c, s] is the probability that a user in degree class c (degree
    degree_values[c], degree_counts[c] users) comments in subreddit s.
    """
    p: np.ndarray
    degree_values: np.ndarray
    degree_counts: np.ndarray
    sub_degrees: np.ndarray
    n_users: int
    max_error: float
    iterations: int


def fit_bicm(M: sp.spmatrix, tol: float = 1e-8, max_iter: int = 50_000) -> BiCMFit:
    """Fit BiCM multipliers by damped fixed-point iteration.

    Users with no activity are ignored. Users active in every active subreddit
    have p = 1 there by construction (their multiplier is infinite), so they are
    set analytically and removed from the subreddit totals before fitting.
    """
    M = sp.csr_matrix(M)
    ku = np.asarray(M.sum(1)).ravel().astype(np.int64)
    ks = np.asarray(M.sum(0)).ravel().astype(np.float64)
    active_sub = ks > 0
    n_active = int(active_sub.sum())
    if np.any(ku > n_active):
        raise ValueError("user degree exceeds the number of subreddits: duplicate entries were not collapsed")
    deg_values, deg_counts = np.unique(ku[ku > 0], return_counts=True)
    S = M.shape[1]

    full = deg_values == n_active
    ks_rest = ks - np.where(active_sub, deg_counts[full].sum(), 0.0)
    if np.any(ks_rest[active_sub] >= (deg_counts[~full].sum())) and deg_counts[~full].sum() > 0:
        # A subreddit containing every non-full user also has an infinite multiplier.
        raise ValueError("a subreddit contains every user; BiCM probabilities are degenerate")

    dv, n = deg_values[~full].astype(np.float64), deg_counts[~full].astype(np.float64)
    P = np.zeros((len(deg_values), S))
    P[np.ix_(full, active_sub)] = 1.0
    err, it = 0.0, 0
    if len(dv):
        cols = np.where(active_sub)[0]
        k_s = ks_rest[cols]
        L = float((dv * n).sum())
        x = dv / np.sqrt(L)
        y = np.maximum(k_s, 1e-12) / np.sqrt(L)
        for it in range(1, max_iter + 1):
            xy = np.outer(x, y)
            x_new = dv / (y / (1.0 + xy)).sum(1)
            y_new = k_s / (n[:, None] * x[:, None] / (1.0 + xy)).sum(0)
            x, y = 0.5 * x + 0.5 * x_new, 0.5 * y + 0.5 * y_new
            if it % 50 == 0:
                q = np.outer(x, y); q /= 1.0 + q
                err = max(np.abs(q.sum(1) - dv).max(), np.abs((n[:, None] * q).sum(0) - k_s).max())
                if err < tol:
                    break
        q = np.outer(x, y); q /= 1.0 + q
        err = max(np.abs(q.sum(1) - dv).max(), np.abs((n[:, None] * q).sum(0) - k_s).max())
        P[np.ix_(~full, cols)] = q
    return BiCMFit(P, deg_values, deg_counts, ks, int((ku > 0).sum()), float(err), it)


def expected_cooccurrence(fit: BiCMFit) -> np.ndarray:
    """E[a, b] = expected number of users commenting in both a and b."""
    return fit.p.T @ (fit.degree_counts[:, None] * fit.p)


def cooccurrence(M: sp.spmatrix) -> np.ndarray:
    """V[a, b] = observed number of users commenting in both a and b."""
    M = sp.csr_matrix(M)
    return np.asarray((M.T @ M).todense())


# ---------------------------------------------------------------------------
# Significance
# ---------------------------------------------------------------------------
def poisson_pvalues(observed: np.ndarray, expected: np.ndarray) -> np.ndarray:
    """One-sided P(X >= observed) for X ~ Poisson(expected); 1 where nothing is expected or observed."""
    observed = np.asarray(observed, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    p = np.ones_like(observed)
    ok = (expected > 0) & (observed > 0)
    p[ok] = poisson.sf(observed[ok] - 1, expected[ok])
    return p


def benjamini_hochberg(pvalues: np.ndarray, alpha: float) -> np.ndarray:
    """Boolean mask of discoveries at false discovery rate alpha."""
    p = np.asarray(pvalues, dtype=np.float64)
    m = len(p)
    if m == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p, kind="mergesort")
    passed = p[order] <= alpha * np.arange(1, m + 1) / m
    keep = np.zeros(m, dtype=bool)
    if passed.any():
        keep[order[: np.max(np.where(passed)[0]) + 1]] = True
    return keep


# ---------------------------------------------------------------------------
# One call for the Atlas
# ---------------------------------------------------------------------------
@dataclass
class AffinityNetwork:
    subreddits: list[str]
    observed: np.ndarray        # S x S shared commenters
    expected: np.ndarray        # S x S BiCM expectation
    pvalues: np.ndarray         # S x S (diagonal = 1)
    validated: np.ndarray       # S x S bool, symmetric
    sub_users: np.ndarray       # commenters per subreddit
    n_users: int
    alpha: float
    fit_error: float
    cosine: np.ndarray = field(repr=False, default=None)

    @property
    def affinity(self) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            a = self.observed / self.expected
        a[~np.isfinite(a)] = 0.0
        np.fill_diagonal(a, 0.0)
        return a

    @property
    def density(self) -> float:
        S = len(self.subreddits)
        return float(np.triu(self.validated, 1).sum() / (S * (S - 1) / 2))

    def edges(self, validated_only: bool = True) -> pd.DataFrame:
        """One row per subreddit pair (a < b)."""
        iu = np.triu_indices(len(self.subreddits), 1)
        df = pd.DataFrame({
            "source": np.array(self.subreddits)[iu[0]],
            "target": np.array(self.subreddits)[iu[1]],
            "shared": self.observed[iu].astype(np.int64),
            "expected": self.expected[iu],
            "affinity": self.affinity[iu],
            "pvalue": self.pvalues[iu],
            "validated": self.validated[iu],
            "cosine": self.cosine[iu] if self.cosine is not None else np.nan,
        })
        return df[df["validated"]].reset_index(drop=True) if validated_only else df


def affinity_network(M: sp.spmatrix, subreddits: list[str], alpha: float = 0.01) -> AffinityNetwork:
    """Fit BiCM on a presence matrix and validate every subreddit pair."""
    M = sp.csr_matrix(M)
    fit = fit_bicm(M)
    V = cooccurrence(M)
    E = expected_cooccurrence(fit)
    S = len(subreddits)
    iu = np.triu_indices(S, 1)
    p_up = poisson_pvalues(V[iu], E[iu])
    keep = benjamini_hochberg(p_up, alpha)
    P = np.ones((S, S)); P[iu] = p_up; P.T[iu] = p_up
    Vd = np.zeros((S, S), dtype=bool); Vd[iu] = keep; Vd = Vd | Vd.T
    k = np.diag(V).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos = V / np.sqrt(np.outer(k, k))
    cos[~np.isfinite(cos)] = 0.0
    np.fill_diagonal(cos, 0.0)
    return AffinityNetwork(list(subreddits), V, E, P, Vd, k, fit.n_users, alpha, fit.max_error, cos)
