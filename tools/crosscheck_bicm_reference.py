"""
Cross-check network_analysis/affinity.py against the reference `bicm` package
(Vallarano et al. 2021) on a real-data sample, and check the Poisson
approximation against exact Poisson-binomial p-values near the FDR cut-off.

Needs the optional package:  pip install bicm==3.4.0
The reference package builds a dense users x subreddits matrix, so a
deterministic user sample is used (default 150,000 users of one quarter).

Usage:
    python tools/crosscheck_bicm_reference.py --quarter 2018Q1 --users 150000
Writes atlas/validation/bicm_crosscheck.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from network_analysis.affinity import (  # noqa: E402
    affinity_network, benjamini_hochberg, fit_bicm, presence_matrix,
)


def exact_tail(fit, a: int, b: int, observed: int) -> float:
    """P(V >= observed) where V = sum over degree classes of Binomial(n_c, p_ca * p_cb)."""
    pmf = np.array([1.0])
    for n_c, q in zip(fit.degree_counts, fit.p[:, a] * fit.p[:, b]):
        hi = int(binom.ppf(1 - 1e-15, n_c, q)) + 1
        pmf = np.convolve(pmf, binom.pmf(np.arange(hi + 1), n_c, q))
    return float(pmf[observed:].sum()) if observed < len(pmf) else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", default="2018Q1")
    ap.add_argument("--users", type=int, default=150_000)
    ap.add_argument("--alpha", type=float, default=0.01)
    args = ap.parse_args()
    import bicm

    path = (ROOT / "data_curation/data/clean" / f"{args.quarter}.parquet").as_posix()
    df = duckdb.connect().execute(f"""
        WITH p AS (SELECT DISTINCT author_h, subreddit FROM '{path}'),
             u AS (SELECT author_h, (ROW_NUMBER() OVER (ORDER BY hash(author_h || 'crosscheck')))::INTEGER - 1 AS u
                   FROM (SELECT DISTINCT author_h FROM p))
        SELECT u.u, p.subreddit FROM p JOIN u USING (author_h) WHERE u.u < {args.users}""").df()
    subs = sorted(df.subreddit.unique()); col = {s: j for j, s in enumerate(subs)}
    M = presence_matrix(df.u.values, df.subreddit.map(col).values, args.users, len(subs))
    M = M[np.asarray(M.sum(1)).ravel() > 0]
    S = len(subs); iu = np.triu_indices(S, 1)

    t = time.time(); net = affinity_network(M, subs, args.alpha); fit = fit_bicm(M); t_ours = time.time() - t
    ours = net.validated[iu]

    t = time.time()
    g = bicm.BipartiteGraph(biadjacency=M.astype(np.int8))
    g.solve_tool(method="fixed-point", tol=1e-10, max_steps=20000, print_error=False)
    P_ref = np.asarray(g.get_bicm_matrix())
    g.compute_projection(rows=False, alpha=args.alpha, approx_method="poisson", validation_method="fdr", progress_bar=False)
    p_ref = np.asarray(g.get_projected_pvals_mat(layer="columns"))[iu]
    ref = np.zeros(len(iu[0]), bool)
    pos = {(a, b): k for k, (a, b) in enumerate(zip(*iu))}
    for a, nbrs in g.projected_cols_adj_list.items():
        for b in nbrs:
            ref[pos[(min(a, b), max(a, b))]] = True
    t_ref = time.time() - t

    ku = np.asarray(M.sum(1)).ravel().astype(int)
    P_ours = fit.p[np.searchsorted(fit.degree_values, ku)]
    p_ours = net.pvalues[iu]
    lp = lambda x: np.log10(np.clip(x, 1e-300, 1))

    # exact Poisson-binomial for the 300 pairs nearest the cut-off
    order = np.argsort(p_ours); k = int(ours.sum()); m = len(p_ours)
    border = order[max(0, k - 150): k + 150]
    exact = np.array([exact_tail(fit, iu[0][e], iu[1][e], int(net.observed[iu[0][e], iu[1][e]])) for e in border])
    p_exact_all = p_ours.copy(); p_exact_all[border] = exact
    exact_keep = benjamini_hochberg(p_exact_all, args.alpha)
    flips = border[(exact_keep[border] != ours[border])]

    out = {
        "quarter": args.quarter, "sample_users": int(M.shape[0]), "subreddits": S, "links": int(M.nnz), "alpha": args.alpha,
        "fit_max_abs_prob_difference": float(np.abs(P_ref - P_ours).max()),
        "pvalue_median_abs_log10_difference": float(np.median(np.abs(lp(p_ref) - lp(p_ours)))),
        "validated_ours": int(ours.sum()), "validated_reference": int(ref.sum()),
        "validated_jaccard": float((ours & ref).sum() / max(1, (ours | ref).sum())),
        "only_ours": int((ours & ~ref).sum()), "only_reference": int((ref & ~ours).sum()),
        "exact_poisson_binomial_pairs_checked": int(len(border)),
        "exact_decision_flips": int(len(flips)),
        "exact_flips_gained": int((exact_keep[flips]).sum()), "exact_flips_lost": int((~exact_keep[flips]).sum()),
        "exact_flips_share_of_validated": float(len(flips) / max(1, k)),
        "seconds_ours": round(t_ours, 1), "seconds_reference": round(t_ref, 1),
        "bicm_version": getattr(bicm, "__version__", "3.4.0"),
    }
    dest = ROOT / "atlas/validation/bicm_crosscheck.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
