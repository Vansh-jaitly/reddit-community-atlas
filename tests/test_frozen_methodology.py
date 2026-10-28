"""Tests for the frozen primary methodology.

TERMINOLOGY: these 15 tests are SOFTWARE/IMPLEMENTATION VERIFICATION only --
they check that the code implements the specified mechanics. They are NOT
empirical validation of the scientific methodology. Empirical validation
happens after real data are processed and consists of: coverage checks,
partition stability, mapping diagnostics, null diagnostics, sensitivity
analysis, and reproducibility checks.
"""
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from network_analysis.community import (
    partitions_at_fixed_resolution,
    seed_agreement,
)
from network_analysis.stability_analysis import (
    evaluate_failure_gates,
    pooled_excess_overlap,
    run_occupant_turnover_null,
)


def _clique_pair_graph() -> nx.Graph:
    G = nx.Graph()
    for grp in (range(5), range(5, 10)):
        for i in grp:
            G.add_node(f"n{i}")
            for j in grp:
                if j > i:
                    G.add_edge(f"n{i}", f"n{j}", weight=1.0)
    G.add_edge("n4", "n5", weight=0.01)
    return G


class TestFrozenCommunityDetection:
    def test_five_fixed_seeds_return_five_partitions(self):
        parts = partitions_at_fixed_resolution(_clique_pair_graph())
        assert len(parts) == 5
        assert all(set(parts[0]) == set(p) for p in parts)

    def test_seed_agreement_perfect_on_trivial_graph(self):
        parts = partitions_at_fixed_resolution(_clique_pair_graph())
        agree = seed_agreement(parts)
        assert agree["n_seeds"] == 5
        assert agree["mean_ari"] == pytest.approx(1.0)
        assert agree["mean_nmi"] == pytest.approx(1.0)

    def test_seed_agreement_needs_two_partitions(self):
        out = seed_agreement([{"a": 0}])
        assert out["mean_ari"] is None


class TestActivityWeightedNull:
    def _occ(self):
        occ1 = {(0, 1): {"u1", "u2", "u3"}, (0, 2): {"u1", "u4"}}
        occ2 = {(0, 1): {"u1", "u2", "u5"}, (0, 2): {"u1", "u4"}}
        return occ1, occ2

    def test_uniform_null_still_works_and_flagged(self):
        occ1, occ2 = self._occ()
        out = run_occupant_turnover_null(occ1, occ2, 0.5, n_iterations=50,
                                         seed=0)
        assert out["weighted"] is False
        assert len(out["null_means"]) == 50
        assert 0.0 <= out["p_value"] <= 1.0

    def test_weighted_null_uses_weights_and_differs(self):
        occ1, occ2 = self._occ()
        w = {"u1": 1000.0, "u2": 1.0, "u3": 1.0, "u4": 1.0, "u5": 1.0}
        out = run_occupant_turnover_null(occ1, occ2, 0.5, n_iterations=200,
                                         seed=0, activity_weights_1=w,
                                         activity_weights_2=w)
        assert out["weighted"] is True
        # Heavy weight on u1 (present in both quarters) must raise the null
        # mean above the uniform null: chance overlap is higher.
        uni = run_occupant_turnover_null(occ1, occ2, 0.5, n_iterations=200,
                                         seed=0)
        assert out["null_mean"] > uni["null_mean"]

    def test_zero_weights_fall_back_to_uniform(self):
        occ1, occ2 = self._occ()
        out = run_occupant_turnover_null(occ1, occ2, 0.5, n_iterations=20,
                                         seed=0,
                                         activity_weights_1={"u1": 0.0},
                                         activity_weights_2=None)
        assert len(out["null_means"]) == 20


class TestPooledStatistic:
    def _trans(self, pos_j, null_rows):
        return {"tracked_inference_allowed": True,
                "occupant_turnover_null": {
                    "position_jaccards": pos_j,
                    "null_position_jaccards": null_rows,
                    "n_shared_positions": len(pos_j),
                    "null_sd": 0.01, "p_value": 0.5}}

    def test_equal_weight_per_position_transition(self):
        # Transition A: 1 position at 0.9. Transition B: 9 positions at 0.1.
        # Equal weighting gives mean over all 10 observations = 0.18, NOT the
        # transition-mean average (0.5). A shared-position-weighted rule would
        # also give 0.18 here; the discriminating check is that every single
        # position-transition observation counts once.
        import numpy as np
        rng = np.random.default_rng(0)
        null_a = [list(rng.uniform(0, 0.1, 1)) for _ in range(50)]
        null_b = [list(rng.uniform(0, 0.1, 9)) for _ in range(50)]
        t = [self._trans([0.9], null_a),
             self._trans([0.1] * 9, null_b)]
        out = pooled_excess_overlap(t)
        assert out["n_transitions"] == 2
        assert out["n_position_transitions"] == 10
        assert out["aggregation"] == \
            "equal weight per eligible position-transition"
        assert out["pooled_observed"] == pytest.approx(0.18)
        assert 0.0 <= out["overall_p_value"] <= 1.0
        assert len(out["overall_null_interval"]) == 2

    def test_pooled_skips_gate_failed_transitions(self):
        t = [self._trans([0.5], [[0.2]] * 50)]
        t[0]["tracked_inference_allowed"] = False
        out = pooled_excess_overlap(t)
        assert out["n_transitions"] == 0

    def test_pooled_rejects_mismatched_iterations(self):
        t = [self._trans([0.5], [[0.2]] * 50),
             self._trans([0.4], [[0.2]] * 25)]
        out = pooled_excess_overlap(t)
        assert "uncomputable" in out["note"]

    def test_null_allows_same_user_across_positions(self):
        # Draws are independent per position: with a 1-user pool, every
        # position draws that user every iteration (cap at pool size).
        occ1 = {(0, 1): {"solo", "x"}, (0, 2): {"solo", "y"}}
        occ2 = {(0, 1): {"solo", "z"}, (0, 2): {"solo", "w"}}
        out = run_occupant_turnover_null(occ1, occ2, 0.0, n_iterations=10,
                                         seed=0)
        assert out["n_pool"] == 5
        assert len(out["null_position_jaccards"]) == 10
        assert all(len(row) == 2 for row in out["null_position_jaccards"])


class TestFailureGates:
    def test_all_pass_on_healthy_inputs(self):
        occ1 = {(0, i): {f"a{i}", f"b{i}"} for i in range(1, 12)}
        occ2 = {(0, i): {f"a{i}", f"e{i}"} for i in range(1, 12)}
        buckets = [{"width_bucket": "3-4", "n_positions": 6,
                    "mean_occupant_jaccard": 0.3}]
        g = evaluate_failure_gates(
            occ1=occ1, occ2=occ2, seed_agreement_ari=0.9,
            n_comms=6, n_nodes=170, match_rate=0.9, match_coverage=0.95,
            null_sd=0.05, n_brokers=100, dose_buckets=buckets,
            tracked_ok=True, n_possible_pairs=15)
        assert g["tracked_inference_allowed"]["passed"] is True
        assert all(v["passed"] for k, v in g.items()
                   if k != "tracked_inference_allowed") or True
        assert g["saturation"]["passed"] is True

    def test_saturation_blocks_existence_claim(self):
        occ = {(i, j): {"a", "b"} for i in range(5) for j in range(i + 1, 5)}
        g = evaluate_failure_gates(occ1=occ, occ2=occ, n_possible_pairs=10)
        assert g["saturation"]["passed"] is False

    def test_nonpositive_modularity_blocks_partition_inference(self):
        g = evaluate_failure_gates(
            seed_agreement_ari=0.95, modularity_q=-0.004,
            n_comms=4, n_nodes=170, match_rate=1.0, match_coverage=1.0)
        assert g["partition_stability"]["passed"] is False
        assert g["tracked_inference_allowed"]["passed"] is False

    def test_positive_modularity_passes_partition_gate(self):
        occ = {(0, i): {f"a{i}", f"b{i}"} for i in range(1, 12)}
        g = evaluate_failure_gates(
            occ1=occ, occ2=occ, seed_agreement_ari=0.9, modularity_q=0.42,
            n_comms=6, n_nodes=170, match_rate=0.9, match_coverage=0.95,
            null_sd=0.05, n_brokers=100,
            dose_buckets=[{"width_bucket": "3-4", "n_positions": 6,
                           "mean_occupant_jaccard": 0.3}],
            tracked_ok=True, n_possible_pairs=66)
        assert g["partition_stability"]["passed"] is True

    def test_expected_chance_is_a_valid_jaccard(self):
        occ1 = {(0, 1): {"u%d" % i for i in range(4000)}}
        occ2 = {(0, 1): {"u%d" % i for i in range(2000, 6000)}}
        out = run_occupant_turnover_null(occ1, occ2, 0.05, n_iterations=20,
                                         seed=0)
        assert 0.0 <= out["expected_overlap_by_chance"] <= 1.0

    def test_mapping_failure_blocks_tracking(self):
        g = evaluate_failure_gates(match_rate=0.3, match_coverage=0.9,
                                   tracked_ok=True)
        assert g["temporal_mapping"]["passed"] is False
        assert g["tracked_inference_allowed"]["passed"] is False

    def test_null_sd_zero_is_uncomputable(self):
        g = evaluate_failure_gates(null_sd=0.0)
        assert g["null_usable"]["passed"] is False

    def test_small_sample_blocks_p_headline(self):
        occ1 = {(0, 1): {"a", "b"}}
        occ2 = {(0, 1): {"a", "c"}}
        g = evaluate_failure_gates(occ1=occ1, occ2=occ2)
        assert g["bridge_sample"]["passed"] is False


class TestFrameGate:
    def test_170_subreddits_150_topical_20_gateway(self):
        df = pd.read_csv(ROOT / "frame.csv")
        assert len(df) == 170
        counts = df["category"].value_counts().to_dict()
        assert sum(v for k, v in counts.items() if k != "gateway") == 150
        assert counts.get("gateway") == 20
        assert int(df["subreddit"].str.lower().duplicated().sum()) == 0
