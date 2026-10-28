"""Tests for network_analysis/affinity.py (BiCM expected overlap, affinity, validated edges)."""

import numpy as np
import pytest
import scipy.sparse as sp

from network_analysis.affinity import (
    affinity_network, benjamini_hochberg, cooccurrence, expected_cooccurrence,
    fit_bicm, poisson_pvalues, presence_matrix,
)


def random_bipartite(n_users=3000, n_subs=12, seed=0):
    """Users with heterogeneous breadth choosing subreddits with heterogeneous popularity, no structure."""
    rng = np.random.default_rng(seed)
    pop = rng.pareto(1.5, n_subs) + 1
    pop /= pop.sum()
    rows, cols = [], []
    for u in range(n_users):
        k = min(n_subs - 1, 1 + rng.poisson(1.5))
        for s in rng.choice(n_subs, size=k, replace=False, p=pop):
            rows.append(u); cols.append(s)
    return presence_matrix(rows, cols, n_users, n_subs)


def planted_blocks(seed=1):
    """Two blocks of 5 subreddits: most users stay inside one block, a few roam everywhere."""
    rng = np.random.default_rng(seed)
    rows, cols, u = [], [], 0
    for block in (range(0, 5), range(5, 10)):
        for _ in range(1500):
            for s in rng.choice(list(block), size=rng.integers(1, 4), replace=False):
                rows.append(u); cols.append(s)
            u += 1
    for _ in range(300):
        for s in rng.choice(10, size=rng.integers(1, 4), replace=False):
            rows.append(u); cols.append(s)
        u += 1
    return presence_matrix(rows, cols, u, 10)


class TestPresenceMatrix:
    def test_duplicates_collapse_to_binary(self):
        M = presence_matrix([0, 0, 0, 1, 1], [2, 2, 1, 0, 0], 2, 3)
        assert M.nnz == 3
        assert set(M.data) == {1.0}
        np.testing.assert_array_equal(M.toarray(), [[0, 1, 1], [1, 0, 0]])

    def test_duplicates_do_not_change_the_fit(self):
        M = random_bipartite()
        coo = M.tocoo()
        dup = presence_matrix(np.r_[coo.row, coo.row], np.r_[coo.col, coo.col], *M.shape)
        a, b = affinity_network(M, list("abcdefghijkl")), affinity_network(dup, list("abcdefghijkl"))
        np.testing.assert_allclose(a.expected, b.expected)
        np.testing.assert_array_equal(a.validated, b.validated)

    def test_unsummed_duplicates_are_rejected(self):
        M = sp.csr_matrix((np.ones(4), ([0, 0, 0, 0], [0, 0, 1, 1])), shape=(1, 2))  # degree 4 > 2 subs
        with pytest.raises(ValueError):
            fit_bicm(M)


class TestBiCMFit:
    def test_degree_constraints_hold(self):
        M = random_bipartite()
        fit = fit_bicm(M)
        ku = np.asarray(M.sum(1)).ravel()
        assert fit.max_error < 1e-6
        np.testing.assert_allclose(fit.p.sum(1), fit.degree_values, atol=1e-6)
        np.testing.assert_allclose((fit.degree_counts[:, None] * fit.p).sum(0), np.asarray(M.sum(0)).ravel(), atol=1e-5)
        assert fit.n_users == int((ku > 0).sum())
        assert np.all((fit.p >= 0) & (fit.p <= 1))

    def test_user_in_every_subreddit_is_handled(self):
        M = random_bipartite(n_users=500, n_subs=6)
        full = presence_matrix(np.zeros(6, int), np.arange(6), 1, 6)
        M2 = sp.vstack([M, full]).tocsr()
        fit = fit_bicm(M2)
        assert np.all(np.isfinite(fit.p))
        np.testing.assert_allclose(fit.p[fit.degree_values == 6], 1.0)
        np.testing.assert_allclose((fit.degree_counts[:, None] * fit.p).sum(0), np.asarray(M2.sum(0)).ravel(), atol=1e-5)

    def test_inactive_users_and_empty_subreddit(self):
        M = random_bipartite(n_users=400, n_subs=5)
        M = sp.hstack([M, sp.csr_matrix((400, 1))]).tocsr()          # subreddit 5 has nobody
        M = sp.vstack([M, sp.csr_matrix((10, 6))]).tocsr()            # 10 users with no activity
        net = affinity_network(M, list("abcdef"))
        assert net.n_users == 400
        assert not net.validated[5].any()
        assert np.all(net.pvalues[5, :5] == 1.0)
        assert np.all(net.affinity[5] == 0.0)

    def test_expected_matches_bruteforce_sum_over_users(self):
        M = random_bipartite(n_users=300, n_subs=6)
        fit = fit_bicm(M)
        ku = np.asarray(M.sum(1)).ravel().astype(int)
        per_user = np.array([fit.p[np.searchsorted(fit.degree_values, k)] for k in ku if k > 0])
        np.testing.assert_allclose(expected_cooccurrence(fit), per_user.T @ per_user, rtol=1e-10)


class TestSignificance:
    def test_poisson_pvalues_edge_cases(self):
        p = poisson_pvalues(np.array([0, 5, 5, 20]), np.array([3.0, 0.0, 5.0, 5.0]))
        assert p[0] == 1.0 and p[1] == 1.0
        assert 0 < p[3] < p[2] < 1

    def test_benjamini_hochberg_matches_hand_calculation(self):
        p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])
        # thresholds alpha*i/m with alpha=0.05, m=10: 0.005, 0.01, 0.015, 0.02, 0.025, ...
        np.testing.assert_array_equal(benjamini_hochberg(p, 0.05), [True, True] + [False] * 8)
        assert not benjamini_hochberg(np.array([0.5, 0.9]), 0.05).any()
        assert benjamini_hochberg(np.array([]), 0.05).size == 0

    def test_structureless_data_gives_no_false_relationships(self):
        net = affinity_network(random_bipartite(n_users=4000, n_subs=12, seed=3), list("abcdefghijkl"))
        assert net.density <= 0.05

    def test_popularity_alone_does_not_create_edges_but_inflates_cosine(self):
        M = random_bipartite(n_users=5000, n_subs=12, seed=4)
        net = affinity_network(M, list("abcdefghijkl"))
        hub = int(np.argmax(net.sub_users))
        others = [j for j in range(12) if j != hub]
        assert net.cosine[hub, others].mean() > np.delete(net.cosine, hub, 0)[:, others].mean()
        assert net.validated[hub].sum() <= 1

    def test_planted_blocks_recovered(self):
        net = affinity_network(planted_blocks(), [f"s{i}" for i in range(10)])
        within = [(a, b) for blk in (range(5), range(5, 10)) for a in blk for b in blk if a < b]
        across = [(a, b) for a in range(5) for b in range(5, 10)]
        assert all(net.validated[a, b] for a, b in within)
        assert not any(net.validated[a, b] for a, b in across)
        assert all(net.affinity[a, b] > 1 for a, b in within)
        assert all(net.affinity[a, b] < 1 for a, b in across)

    def test_zero_overlap_is_never_validated(self):
        M = presence_matrix([0, 1, 2, 3, 4, 5], [0, 0, 0, 1, 1, 2], 6, 3)
        net = affinity_network(M, ["a", "b", "c"])
        assert cooccurrence(M)[0, 1] == 0
        assert not net.validated.any()

    def test_edge_table_is_consistent(self):
        net = affinity_network(planted_blocks(), [f"s{i}" for i in range(10)])
        e = net.edges()
        assert len(e) == int(np.triu(net.validated, 1).sum())
        assert (e["shared"] / e["expected"] - e["affinity"]).abs().max() < 1e-9
        assert e["pvalue"].max() <= net.alpha
        assert len(net.edges(validated_only=False)) == 45


def test_matches_reference_bicm_package_when_installed():
    bicm = pytest.importorskip("bicm")
    M = planted_blocks(seed=7)
    net = affinity_network(M, [f"s{i}" for i in range(10)])
    g = bicm.BipartiteGraph(biadjacency=M.toarray().astype(np.int8))
    g.solve_tool(method="fixed-point", tol=1e-10, max_steps=20000, print_error=False)
    g.compute_projection(rows=False, alpha=0.01, approx_method="poisson", validation_method="fdr", progress_bar=False)
    pv = np.asarray(g.get_projected_pvals_mat(layer="columns"))
    iu = np.triu_indices(10, 1)
    np.testing.assert_allclose(pv[iu], net.pvalues[iu], rtol=1e-6, atol=1e-12)
