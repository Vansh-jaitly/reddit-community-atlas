"""
run_network_pipeline.py
======================
CLI orchestrator for executing the complete network analysis pipeline across all clean quarters:
  1. Bipartite User-Subreddit Graph Construction
  2. Cosine Similarity Projection (FULL weighted network -> inference)
  3. Leiden Community Detection at frozen gamma=1 (5 fixed seeds)
  4. Anchored Community Matching to Global Anchor Partition (label alignment ONLY)
  5. Participation Coefficient (P_i) & Brokerage Calculations
  6. Bridge Survival + Occupant Turnover vs Activity-Weighted Null

Serrano disparity filtering is VISUALIZATION ONLY (Gephi/dashboard backbone).
It never feeds community detection or any inferential statistic.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import sys

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import data_curation.config as C
import leidenalg
from network_analysis.bipartite import load_bipartite_dataframe, build_bipartite_matrix
from network_analysis.projection import compute_cosine_projection
from network_analysis.backbone import disparity_filter
from network_analysis.community import (
    detect_communities_leiden,
    partitions_at_fixed_resolution,
    seed_agreement,
    resolution_profile,
    networkx_to_igraph,
    _partition_class,
)
from network_analysis.brokerage import compute_participation_coefficients
from network_analysis.anchored_matching import match_quarter_to_anchor
from network_analysis.stability_analysis import (
    extract_bridge_positions,
    compare_position_vs_person_stability,
    compute_bridge_widths,
    observed_occupant_overlap,
    run_degree_preserving_null_model,
    run_occupant_turnover_null,
    pooled_excess_overlap,
    evaluate_failure_gates,
    width_statistics,
    width_stability_dose_response,
)


# ----------------------------------------------------------------------------
# FROZEN PRIMARY CONFIGURATION (methodology specification, final gate).
# Do NOT tune these after seeing results. Robustness variations are reported
# separately and never promoted to headline findings.
# ----------------------------------------------------------------------------
PRIMARY_GAMMA = 1.0
PRIMARY_SEEDS = (0, 1, 2, 3, 4)
PRIMARY_MIN_WIDTH = 2
PRIMARY_BROKER_PERCENTILE = 0.99
PRIMARY_TURNOVER_ITERATIONS = 1000
PRIMARY_JACCARD_THRESHOLD = 0.3
PRIMARY_MATCH_RATE_GATE = 0.60
PRIMARY_COVERAGE_GATE = 0.80
PRIMARY_SEED_ARI_GATE = 0.60
# Serrano alpha is a VISUALIZATION parameter only (backbone for Gephi/dashboard).
VIZ_ALPHA = 0.3


def run(quarters: list[str] | None = None, alpha: float = 0.3,
        min_width: int = 2, null_iterations: int = 0, turnover_iterations: int = 1000,
        broker_percentile: float = 0.99, null_seed: int = 0):
    clean_dir = C.DATA_CLEAN
    available_files = sorted(clean_dir.glob("*.parquet"))

    if not available_files:
        print(f"❌ No clean parquet files found in {clean_dir}. Run `python run_pipeline.py` first.")
        return

    if quarters:
        available_files = [f for f in available_files if f.stem in quarters]

    print(f"🚀 Starting Network Analysis Engine across {len(available_files)} quarter(s)...")

    # Step 1: Build Global Anchor Reference Partition across pooled quarters.
    # The anchor is LABEL ALIGNMENT ONLY (a coordinate system). It never
    # influences community detection, gamma selection, broker selection, or any
    # primary outcome. Detection runs on the FULL cosine-weighted network;
    # Serrano filtering is visualization-only and is computed separately below.
    print("\n--- Step 1: Building Pooled Anchor Reference Partition ---")
    all_dfs = []
    for p in available_files:
        print(f"Reading {p.name}...")
        df_q = load_bipartite_dataframe(p)
        all_dfs.append(df_q)

    pooled_df = pd.concat(all_dfs, ignore_index=True)
    M_pool, users_p, subs_p, _, _ = build_bipartite_matrix(pooled_df)
    G_pool = compute_cosine_projection(M_pool, subs_p)
    anchor_seed_parts = partitions_at_fixed_resolution(
        G_pool, resolution=PRIMARY_GAMMA, seeds=PRIMARY_SEEDS)
    anchor_seed_audit = seed_agreement(anchor_seed_parts)
    anchor_partition = anchor_seed_parts[0]
    _ig_pool, _ = networkx_to_igraph(G_pool)
    anchor_mod = float(leidenalg.find_partition(
        _ig_pool, _partition_class("modularity"),
        resolution_parameter=PRIMARY_GAMMA,
        weights="weight", seed=PRIMARY_SEEDS[0]).modularity)
    anchor_res = PRIMARY_GAMMA
    anchor_res_profile = resolution_profile(G_pool)
    # Visualization-only backbone (never feeds inference).
    G_pool_viz = disparity_filter(G_pool, alpha=VIZ_ALPHA)

    print(f"✅ Anchor partition generated with {len(set(anchor_partition.values()))} communities (Modularity: {anchor_mod:.3f})")

    # Step 2: Per-Quarter Network Analysis & Brokerage Computation
    print("\n--- Step 2: Per-Quarter Analysis & Broker Identification ---")
    quarter_results = {}
    quarter_positions = {}
    quarter_occupants = {}
    quarter_brokers = {}
    quarter_frames = {}
    quarter_community_counts = {}

    for p in available_files:
        q_name = p.stem
        print(f"\nProcessing {q_name}...")

        df_q = load_bipartite_dataframe(p)
        M_q, users_q, subs_q, _, _ = build_bipartite_matrix(df_q)
        G_q = compute_cosine_projection(M_q, subs_q)
        # PRIMARY: community detection on the FULL cosine-weighted network.
        # Serrano is visualization-only and never feeds inference.
        q_seed_parts = partitions_at_fixed_resolution(
            G_q, resolution=PRIMARY_GAMMA, seeds=PRIMARY_SEEDS)
        q_seed_audit = seed_agreement(q_seed_parts)
        q_partition = q_seed_parts[0]
        _ig_q, _ = networkx_to_igraph(G_q)
        q_mod = float(leidenalg.find_partition(
            _ig_q, _partition_class("modularity"),
            resolution_parameter=PRIMARY_GAMMA,
            weights="weight", seed=PRIMARY_SEEDS[0]).modularity)
        q_res = PRIMARY_GAMMA
        q_res_profile = resolution_profile(G_q)
        G_q_viz = disparity_filter(G_q, alpha=VIZ_ALPHA)

        matched_map, match_audit = match_quarter_to_anchor(
            q_partition, anchor_partition,
            jaccard_threshold=PRIMARY_JACCARD_THRESHOLD)
        n_matchable = len({c for c in q_partition.values()})
        n_matched = len(matched_map)
        match_rate = (n_matched / n_matchable) if n_matchable else 0.0
        matched_subs = sum(
            1 for s, c in q_partition.items() if c in matched_map)
        match_coverage = (matched_subs / len(q_partition)) if q_partition else 0.0
        mapping_ok = (match_rate >= PRIMARY_MATCH_RATE_GATE
                      and match_coverage >= PRIMARY_COVERAGE_GATE)
        if not mapping_ok:
            print(f"  ⚠ MAPPING GATE FAILED: match rate {match_rate:.2f} "
                  f"(need >={PRIMARY_MATCH_RATE_GATE}), coverage "
                  f"{match_coverage:.2f} (need >={PRIMARY_COVERAGE_GATE}). "
                  f"This quarter is descriptive-only; no tracked-position "
                  f"longitudinal inference may use it.")
        brokers_df = compute_participation_coefficients(
            df_q, q_partition, broker_percentile=broker_percentile
        )

        pos, occ = extract_bridge_positions(
            df_q, brokers_df, q_partition, matched_map, min_width=min_width
        )

        quarter_positions[q_name] = pos
        quarter_occupants[q_name] = occ
        quarter_brokers[q_name] = brokers_df
        quarter_frames[q_name] = df_q
        quarter_community_counts[q_name] = len(set(q_partition.values()))

        n_brokers = int(brokers_df["is_broker"].sum()) if not brokers_df.empty else 0
        n_comms = len(set(q_partition.values()))

        print(f"  • Nodes: {G_q.number_of_nodes()}, Edges: {G_q.number_of_edges()} -> Viz backbone edges: {G_q_viz.number_of_edges()}")
        print(f"  • Communities: {n_comms}, Modularity: {q_mod:.3f}")
        print(f"  • Active Brokers Identified: {n_brokers}, Occupied Bridge Positions: {len(pos)}")

        quarter_results[q_name] = {
            "nodes": G_q.number_of_nodes(),            "raw_edges": G_q.number_of_edges(),
            "viz_backbone_edges": G_q_viz.number_of_edges(),
            "communities_count": n_comms,
            "modularity": round(q_mod, 4),
            "seed_agreement": q_seed_audit,
            "resolution_profile": q_res_profile,
            "match_rate": round(match_rate, 4),
            "match_coverage": round(match_coverage, 4),
            "mapping_ok": mapping_ok,
            "brokers_count": n_brokers,
            "bridge_positions_count": len(pos),
            "community_partition": q_partition,
        }

    # Step 3: Position vs Person Stability Comparison across Consecutive Quarters
    print("\n--- Step 3: Position vs. Person Stability Evaluation (Hypothesis H1) ---")
    q_names = sorted(quarter_positions.keys())
    transitions = []

    for i in range(len(q_names) - 1):
        q1, q2 = q_names[i], q_names[i + 1]
        stab = compare_position_vs_person_stability(
            quarter_positions[q1], quarter_occupants[q1],
            quarter_positions[q2], quarter_occupants[q2]
        )
        trans_name = f"{q1} -> {q2}"
        stab["transition"] = trans_name

        occ1, occ2 = quarter_occupants[q1], quarter_occupants[q2]
        widths = compute_bridge_widths(occ1)
        n_comms = quarter_community_counts[q1]
        n_possible = n_comms * (n_comms - 1) // 2

        # Mapping gate: if EITHER quarter failed mapping, this transition is
        # descriptive-only. There is NO fallback to a fixed pooled partition:
        # that would artificially impose persistence.
        q1_ok = quarter_results[q1].get("mapping_ok", False)
        q2_ok = quarter_results[q2].get("mapping_ok", False)
        mapping_ok_both = bool(q1_ok and q2_ok)
        stab["tracked_inference_allowed"] = mapping_ok_both
        if not mapping_ok_both:
            print(f"  ⚠ {trans_name}: mapping gate failed in "
                  f"{q1 if not q1_ok else ''}{q2 if not q2_ok else ''}. "
                  f"Quarter-specific descriptive results only; NO "
                  f"tracked-position longitudinal inference.")

        # Activity weights: quarter-specific user activity for the
        # activity-weighted null. q1 draws use q1 activity ONLY; q2 draws use
        # q2 activity ONLY. Never use future-quarter activity for a past
        # quarter's null.
        def _activity(df):
            return {u: float(n) for u, n in
                    df.groupby("author_h")["n_comments"].sum().items()}
        w1 = _activity(quarter_frames[q1])
        w2 = _activity(quarter_frames[q2])

        # The original H1 test, retained only as a documented diagnostic. It is
        # uninformative in both directions that occur in practice, because
        # J_position saturates whenever every community pair has a broker. See
        # the note in stability_analysis.width_statistics.
        stab["legacy_position_jaccard"] = stab.pop("position_stability")
        stab["legacy_person_jaccard"] = stab.pop("person_stability")
        stab["legacy_stability_gap"] = stab.pop("stability_gap")

        # Primary H1 evidence: does bridging CAPACITY persist, and do the same
        # accounts return more often than chance?
        stab["width_stability"] = width_statistics(occ1, occ2)
        stab["occupant_overlap"] = observed_occupant_overlap(occ1, occ2)
        stab["width_dose_response"] = width_stability_dose_response(occ1, occ2)
        stab["occupant_turnover_null"] = run_occupant_turnover_null(
            occ1, occ2,
            observed_mean_jaccard=stab["occupant_overlap"]["mean_occupant_jaccard"],
            n_iterations=turnover_iterations, seed=null_seed,
            activity_weights_1=w1, activity_weights_2=w2,
        )
        stab["failure_gates"] = evaluate_failure_gates(
            occ1=occ1, occ2=occ2,
            seed_agreement_ari=quarter_results[q1].get("seed_agreement", {}).get("mean_ari"),
            modularity_q=quarter_results[q1].get("modularity"),
            n_comms=n_comms, n_nodes=quarter_results[q1].get("nodes"),
            match_rate=min(quarter_results[q1].get("match_rate", 0.0),
                           quarter_results[q2].get("match_rate", 0.0)),
            match_coverage=min(quarter_results[q1].get("match_coverage", 0.0),
                               quarter_results[q2].get("match_coverage", 0.0)),
            null_sd=stab["occupant_turnover_null"].get("null_sd"),
            n_brokers=n_brokers,
            dose_buckets=stab["width_dose_response"].get("buckets", []),
            tracked_ok=mapping_ok_both,
        )
        # The tracked flag is mapping AND the full gate battery: a transition
        # is inferential only if every gate passes. Anything else is
        # descriptive-only, and the pooled headline excludes it.
        stab["tracked_inference_allowed"] = bool(
            mapping_ok_both and stab["failure_gates"][
                "tracked_inference_allowed"]["passed"])
        if not stab["tracked_inference_allowed"]:
            failed = [k for k, v in stab["failure_gates"].items()
                      if k != "tracked_inference_allowed" and not v["passed"]]
            print(f"  ⚠ {trans_name}: failure gates {failed} did not pass. "
                  f"Descriptive-only; excluded from the pooled headline.")

        stab["communities_in_quarter"] = n_comms
        stab["possible_community_pairs"] = n_possible
        stab["max_bridge_width"] = max(widths.values()) if widths else 0
        stab["mean_bridge_width"] = (
            round(float(np.mean(list(widths.values()))), 4) if widths else 0.0
        )
        stab["positions_at_width_1"] = sum(1 for w in widths.values() if w == 1)
        stab["position_set_saturated"] = bool(widths and len(widths) >= n_possible)

        if null_iterations > 0:
            print(f"  • Running degree-preserving null ({null_iterations} iterations)...")
            null_res = run_degree_preserving_null_model(
                quarter_frames[q1], quarter_frames[q2],
                observed_gap=stab["legacy_stability_gap"],
                n_iterations=null_iterations, seed=null_seed,
                alpha=alpha, min_width=min_width,
            )
            stab["partition_null_model"] = null_res

        transitions.append(stab)

        ws = stab["width_stability"]
        oo = stab["occupant_overlap"]
        tn = stab["occupant_turnover_null"]
        tag = "" if stab["tracked_inference_allowed"] else " [DESCRIPTIVE-ONLY]"
        print(f"\nTransition {trans_name}:{tag}")
        print(f"  • Communities in {q1}: {n_comms}  (possible pairs {n_possible}, "
              f"positions found {len(widths)})")
        print(f"  • Bridge width: max {stab['max_bridge_width']}, "
              f"mean {stab['mean_bridge_width']}, "
              f"{stab['positions_at_width_1']}/{len(widths)} at width 1")
        if stab["position_set_saturated"]:
            print(f"  ⚠ SATURATED: all {n_possible} possible community pairs are "
                  f"bridged. J_position would be pinned at 1.0, so it is reported "
                  f"only as a diagnostic and H1 is tested on width + turnover.")
        print(f"  • H1 width: {ws.get('n_shared_positions', 0)} positions bridged in "
              f"both quarters; width Jaccard {ws.get('width_jaccard')}, "
              f"width correlation {ws.get('width_correlation')}, "
              f"capacity persistence {ws.get('width_persistence_rate')}")
        print(f"  • H1 occupants: mean Jaccard {oo.get('mean_occupant_jaccard')} vs "
              f"{tn.get('expected_overlap_by_chance')} expected by chance "
              f"(p = {tn.get('p_value')})")
        for b in stab["width_dose_response"].get("buckets", []):
            print(f"      width {b['width_bucket']:>3}: n={b['n_positions']:<4} "
                  f"mean occupant Jaccard {b['mean_occupant_jaccard']}")
        if null_iterations > 0:
            print(f"    partition null gap mean: "
                  f"{stab['partition_null_model']['null_gap_mean']:.4f} "
                  f"(95% CI {stab['partition_null_model']['null_gap_ci95']}), "
                  f"p = {stab['partition_null_model']['p_value']}")

    # Save summary results to JSON
    output_json = C.DATA_LOGS / "network_results.json"
    pooled = pooled_excess_overlap(transitions)
    print("\n--- Pooled staffing result (ONE prespecified overall statistic) ---")
    if pooled.get("n_transitions", 0):
        print(f"  • Pooled excess occupant Jaccard: {pooled.get('pooled_excess')}")
        print(f"  • Monte Carlo randomization p-value (+1 correction): "
              f"{pooled.get('overall_p_value')}")
        print(f"  • 95% null reference interval: {pooled.get('overall_null_interval')}")
    else:
        print(f"  • No eligible transitions ({pooled.get('note')}). "
              f"Descriptive-only run: no pooled headline is reported.")
    summary_data = {
        "primary_config": {
            "gamma": PRIMARY_GAMMA, "seeds": list(PRIMARY_SEEDS),
            "min_width": PRIMARY_MIN_WIDTH,
            "broker_percentile": PRIMARY_BROKER_PERCENTILE,
            "turnover_iterations": PRIMARY_TURNOVER_ITERATIONS,
            "jaccard_threshold": PRIMARY_JACCARD_THRESHOLD,
            "match_rate_gate": PRIMARY_MATCH_RATE_GATE,
            "coverage_gate": PRIMARY_COVERAGE_GATE,
            "seed_ari_gate": PRIMARY_SEED_ARI_GATE,
            "viz_alpha": VIZ_ALPHA,
            "actual_run_args": {
                "alpha": alpha, "min_width": min_width,
                "null_iterations": null_iterations,
                "turnover_iterations": turnover_iterations,
                "broker_percentile": broker_percentile, "null_seed": null_seed,
            },
        },
        "anchor_communities_count": len(set(anchor_partition.values())),
        "anchor_modularity": round(anchor_mod, 4),
        "anchor_seed_agreement": anchor_seed_audit,
        "anchor_resolution_profile": anchor_res_profile,
        "anchor_partition": anchor_partition,
        "quarter_results": quarter_results,
        "transitions": transitions,
        "pooled_staffing": pooled,
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f"\n✅ Network analysis results saved to {output_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Reddit Bridge Brokers Network Analysis Engine")
    parser.add_argument("--quarters", nargs="*", help="Specific quarters to process (e.g. 2018Q1)")
    parser.add_argument("--alpha", type=float, default=0.3,
                        help="Serrano disparity alpha for the VISUALIZATION-ONLY "
                             "backbone (Gephi/dashboard). Never feeds inference.")
    parser.add_argument("--min-width", type=int, default=2,
                        help="Minimum bridge width (distinct brokers) for a community "
                             "pair to count as a position. Primary is 2; 1 = "
                             "original behaviour, which saturates on most frames.")
    parser.add_argument("--null-iterations", type=int, default=0,
                        help="Degree-preserving null iterations per transition. 0 (default) "
                             "skips it: each iteration re-runs projection + "
                             "Leiden + brokerage, so this is expensive.")
    parser.add_argument("--turnover-iterations", type=int, default=1000,
                        help="Permutation iterations for the H1 occupant-turnover null. "
                             "Cheap (no network rebuild), unlike --null-iterations.")
    parser.add_argument("--broker-percentile", type=float, default=0.99,
                        help="Broker cut-off quantile of P among multi-community users. "
                             "0.99 = top 1%%; on the 2018Q1 frame that was 4436 "
                             "accounts, which is not a defensible definition of a "
                             "'broker' without a sensitivity sweep.")
    parser.add_argument("--null-seed", type=int, default=0, help="RNG seed for the null model")
    args = parser.parse_args()

    run(quarters=args.quarters, alpha=args.alpha, min_width=args.min_width,
        null_iterations=args.null_iterations,
        turnover_iterations=args.turnover_iterations,
        broker_percentile=args.broker_percentile, null_seed=args.null_seed)
