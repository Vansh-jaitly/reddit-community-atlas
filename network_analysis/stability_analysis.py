"""
stability_analysis.py
=====================
Computes Position Stability vs Person Stability across consecutive quarters and evaluates
degree-preserving null models to test Hypothesis H1 (Step 7 of methodology).

WIDTH vs EXISTENCE:
    A "position" here is a pair of detected communities joined by at least one
    broker. On the 2018Q1 run that produced 561 positions over 34 communities --
    exactly C(34,2), i.e. 100% of possible pairs occupied. A position set that
    is saturated has nothing to change, so its Jaccard against the next quarter
    is pinned at 1.0 and H1 becomes true by construction. Bridge width
    w(A,B) (Centola & Macy, 2007) is therefore a first-class argument here:
    use min_width > 1 to keep only load-bearing bridges.
"""

from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from network_analysis.backbone import disparity_filter
from network_analysis.bipartite import build_bipartite_matrix
from network_analysis.brokerage import compute_participation_coefficients
from network_analysis.community import detect_communities_leiden
from network_analysis.projection import compute_cosine_projection

log = logging.getLogger("stability")
if not log.handlers:
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)

# Base for communities present in a quarter but absent from the anchor partition.
# Anchored matching (anchored_matching.py) can only map communities that exist in
# the anchor, so unmatched raw ids must be moved OUT of the anchor id space or they
# alias unrelated anchor communities and merge two different communities into one.
# The mapped value is UNMATCHED_ID_OFFSET - raw_id, which is always <= -2 for any
# non-negative raw id, so it can never collide with an anchor id (anchor ids >= 0).
# Do NOT use -1 as the offset on its own: -1 - 1 == 0 would land back in the
# anchor id space, which is exactly the collision this exists to prevent.
UNMATCHED_ID_OFFSET = -1


def _remap_community_ids(
    df: pd.DataFrame, community_partition: dict[str, int],
    matched_map: dict[int, int] | None,
) -> pd.Series:
    """Map subreddit -> community id, in anchor space when a matched_map is given.

    Unmatched communities get UNMATCHED_ID_OFFSET + raw_id, which is negative and
    therefore cannot collide with any anchor id (anchor ids are >= 0).
    """
    df["comm_raw"] = df["subreddit"].map(community_partition)
    if not matched_map:
        return df["comm_raw"]
    return df["comm_raw"].map(
        lambda c: matched_map.get(c, UNMATCHED_ID_OFFSET - c)
    )


def extract_bridge_positions(
    bipartite_df: pd.DataFrame,
    brokers_df: pd.DataFrame,
    community_partition: dict[str, int],
    matched_map: dict[int, int] | None = None,
    min_width: int = 1,
) -> tuple[set[tuple[int, int]], dict[tuple[int, int], set[str]]]:
    """
    Extracts all bridge positions (community pairs bridged by >= 1 broker user)
    and maps each position to its occupant user set.

    WIDTH (Centola & Macy, 2007, AJS 113(3)):
        w(A, B) = number of distinct brokers tied to BOTH communities.
    A "position" whose width is 1 is a single person spanning two communities.
    Treating that as a structural position is what allows the position set to
    saturate at C(n,2) and pins J_position to 1.0, so min_width > 1 keeps only
    load-bearing bridges. min_width=1 reproduces the original unfiltered
    behaviour and will saturate on most real frames.

    Returns:
        positions: set of (comm_A, comm_B) tuples with comm_A < comm_B
        position_occupants: dict mapping (comm_A, comm_B) -> set of broker author_h
    """
    broker_ids = set(brokers_df[brokers_df["is_broker"]]["author_h"])
    df = bipartite_df[
        bipartite_df["author_h"].isin(broker_ids) & 
        bipartite_df["subreddit"].isin(community_partition)
    ].copy()

    df["comm_id"] = _remap_community_ids(df, community_partition, matched_map)

    user_comms = df.groupby("author_h")["comm_id"].unique().to_dict()

    positions = set()
    position_occupants = {}

    for uid, comms in user_comms.items():
        if len(comms) < 2:
            continue
        c_list = sorted(set(comms))
        for i in range(len(c_list)):
            for j in range(i + 1, len(c_list)):
                pos = (c_list[i], c_list[j])
                positions.add(pos)
                position_occupants.setdefault(pos, set()).add(uid)

    if min_width > 1:
        positions = {p for p in positions if len(position_occupants[p]) >= min_width}
        position_occupants = {p: position_occupants[p] for p in positions}

    return positions, position_occupants


def compute_bridge_widths(
    position_occupants: dict[tuple[int, int], set[str]],
) -> dict[tuple[int, int], int]:
    """Bridge width w(A,B) per position, i.e. how many distinct users occupy it."""
    return {pos: len(users) for pos, users in position_occupants.items()}


def occupant_stability_by_width(
    occ1: dict[tuple[int, int], set[str]],
    occ2: dict[tuple[int, int], set[str]],
) -> list[tuple[int, float]]:
    """
    Per-position Jaccard of occupant sets, paired with that position's width.

    Width is taken as min(w1, w2) so a position is only credited with the
    narrower of its two quarters' widths -- scoring it at its wider value would
    let a single crowded quarter flatter a position that collapsed next quarter.

    Returns:
        list of (width, jaccard) for positions present in BOTH quarters.
    """
    rows = []
    for pos in set(occ1) & set(occ2):
        u1, u2 = occ1[pos], occ2[pos]
        union = u1 | u2
        j = len(u1 & u2) / len(union) if union else 0.0
        rows.append((min(len(u1), len(u2)), float(j)))
    return sorted(rows)


# ---------------------------------------------------------------------------
# H1, reframed: width persistence and occupant turnover
# ---------------------------------------------------------------------------
def width_statistics(
    occ1: dict[tuple[int, int], set[str]],
    occ2: dict[tuple[int, int], set[str]],
) -> dict:
    """
    Does the AMOUNT of bridging between two communities persist, even when the
    PEOPLE doing the bridging do not?

    This replaces the original H1 test. That test compared the Jaccard of the
    bridge-position SET between quarters, which is uninformative in both
    directions that occur in practice:

      * too many communities, many thin brokers -> the set saturates at C(n,2)
        (the 2018Q1 run: 561 positions over 34 communities, i.e. every pair);
      * too few communities, many brokers -> again every pair is bridged
        (a 6-community frame with 72 multi-community brokers: all 15 pairs).

    In both cases J_position is pinned at 1.0 by construction and H1 is
    unfalsifiable. Width and occupancy are the quantities that actually carry
    information, so those are what is measured here.
    """
    shared = set(occ1) & set(occ2)
    w1 = {p: len(occ1[p]) for p in occ1}
    w2 = {p: len(occ2[p]) for p in occ2}

    both = [(w1[p], w2[p]) for p in shared]
    n_only_1 = len(set(occ1) - set(occ2))
    n_only_2 = len(set(occ2) - set(occ1))

    if not both:
        return {
            "n_shared_positions": 0,
            "width_jaccard": None,
            "width_correlation": None,
            "width_persistence_rate": None,
            "positions_only_q1": n_only_1,
            "positions_only_q2": n_only_2,
            "note": "no bridge position is present in both quarters",
        }

    a = np.array([x for x, _ in both], dtype=float)
    b = np.array([y for _, y in both], dtype=float)

    width_jaccard = float((a * b).sum() / (a * a + b * b).sum()) if (a * a + b * b).sum() else 0.0
    corr = None
    if len(both) > 2 and a.std() > 0 and b.std() > 0:
        corr = float(np.corrcoef(a, b)[0, 1])

    return {
        "n_shared_positions": len(shared),
        "positions_only_q1": n_only_1,
        "positions_only_q2": n_only_2,
        "mean_width_q1": round(float(a.mean()), 4),
        "mean_width_q2": round(float(b.mean()), 4),
        # How much of quarter 2's bridging capacity sits on pairs that were
        # already bridged in quarter 1.
        "width_persistence_rate": round(float(b.sum() / (b.sum() + sum(w2[p] for p in set(occ2) - set(occ1)))), 4)
        if b.sum() + sum(w2[p] for p in set(occ2) - set(occ1)) > 0 else None,
        "width_jaccard": round(width_jaccard, 4),
        "width_correlation": round(corr, 4) if corr is not None else None,
    }


def observed_occupant_overlap(
    occ1: dict[tuple[int, int], set[str]],
    occ2: dict[tuple[int, int], set[str]],
) -> dict:
    """
    Raw occupant agreement across quarters, with NO null model attached.

    Reported alongside a permutation baseline rather than instead of one: on its
    own this number says nothing, because a stable population of accounts
    produces high overlap no matter how the bridges are staffed. See
    run_occupant_turnover_null for the baseline it must be read against.
    """
    shared = set(occ1) & set(occ2)
    js = [
        len(occ1[p] & occ2[p]) / len(occ1[p] | occ2[p])
        for p in shared if (occ1[p] | occ2[p])
    ]
    return {
        "n_shared_positions": len(shared),
        "mean_occupant_jaccard": round(float(np.mean(js)), 4) if js else None,
        "median_occupant_jaccard": round(float(np.median(js)), 4) if js else None,
        "pooled_occupants_q1": len({u for s in occ1.values() for u in s}),
        "pooled_occupants_q2": len({u for s in occ2.values() for u in s}),
    }


def run_occupant_turnover_null(
    occ1: dict[tuple[int, int], set[str]],
    occ2: dict[tuple[int, int], set[str]],
    observed_mean_jaccard: float | None = None,
    n_iterations: int = 1000,
    seed: int = 0,
    activity_weights_1: dict[str, float] | None = None,
    activity_weights_2: dict[str, float] | None = None,
) -> dict:
    """
    Null distribution for occupant overlap that holds bridge capacity fixed.

    Rationale: occupant overlap is only interpretable against a baseline. If
    the same accounts are simply present every quarter, they will reappear as
    bridge occupants whether or not the bridges are genuinely staffed by the
    same specialists. So the null preserves the two things that carry signal --
    each position's WIDTH in each quarter, and the overall pool of active
    accounts -- and destroys only the identity assignment:

        for each shared position (A,B), draw w1[A,B] accounts and w2[A,B]
        accounts independently from the pooled account set.

    ACTIVITY WEIGHTING (primary): draws are weighted by quarter-specific user
    activity (q1 draws use q1 activity ONLY; q2 draws use q2 activity ONLY --
    never future-quarter activity for a past quarter's null). A uniform draw
    would understate chance overlap because prolific users are likelier
    occupants under chance, overstating staffing significance. Uniform draws
    (weights=None) are retained as sensitivity analysis only.

    ELIGIBLE USER POOL = sorted union of observed occupants in the two
    quarters (exact code-defined pool below). ACTIVITY WEIGHT = the caller's
    quarter-specific per-user activity (total comment count that quarter).
    TIME WINDOW = current quarter only. FIXED = position widths + eligible
    pool. RANDOMIZED = identity assignment. NULL QUESTION = conditional on
    activity and observed widths, is temporal occupant overlap larger than
    expected by chance?

    EXACT SAMPLING MECHANICS (frozen; identical for observed-vs-null
    comparison and every null iteration):
      - eligible pool: sorted union of occ1 and occ2 occupant sets.
      - activity variable: per-user total comment count in that quarter
        (q1 draws use q1 totals ONLY; q2 draws use q2 totals ONLY).
      - draws are WITHOUT replacement within a position: no duplicate user
        inside one position's drawn set.
      - occupants drawn per position: exactly w1[p] for quarter 1 and w2[p]
        for quarter 2 (the observed widths).
      - the same user MAY occur across multiple positions: draws are
        independent per position (no cross-position exclusion).
      - insufficient pool: draw size is capped at the pool size
        (k = min(width, n_pool)); weights summing to <= 0 fall back to
        uniform draws for that quarter.
      - observed statistic uses the actual occupant sets with the same
        widths and pool; null iterations replace only the identities.

    Under this null the expected Jaccard for a position is w1*w2/|pool|, so a
    position of width 8 in both quarters drawn from a pool of 500 is expected to
    overlap ~0.13 by pure chance. Observing materially more than that is the
    evidence for persistent staffing.

    This is a different and weaker claim than "the community partition is more
    stable than chance" -- that is what the degree-preserving null in
    run_degree_preserving_null_model tests. Both are reported.

    Returns:
        dict with the null mean/sd, the Monte Carlo randomization p-value
        (+1 correction; Phipson & Smyth 2010), the 95% null REFERENCE
        interval (not a confidence interval), and the full null-means array
        used by the pooled overall statistic.
    """
    shared = set(occ1) & set(occ2)
    if not shared:
        return {"n_shared_positions": 0, "p_value": None,
                "note": "no bridge position is present in both quarters"}

    w1 = {p: len(occ1[p]) for p in shared}
    w2 = {p: len(occ2[p]) for p in shared}
    pool = sorted({u for d in (occ1, occ2) for s in d.values() for u in s})
    n_pool = len(pool)
    if n_pool == 0:
        return {"n_shared_positions": len(shared), "p_value": None,
                "note": "empty occupant pool"}

    observed = [len(occ1[p] & occ2[p]) / len(occ1[p] | occ2[p])
                for p in sorted(shared)]
    obs_mean = float(np.mean(observed))

    rng = np.random.default_rng(seed)
    pool_arr = np.array(pool, dtype=object)

    def _probs(weights: dict[str, float] | None) -> np.ndarray | None:
        if weights is None:
            return None
        w = np.array([max(float(weights.get(u, 0.0)), 0.0) for u in pool],
                     dtype=float)
        if w.sum() <= 0:
            return None
        return w / w.sum()

    probs_1, probs_2 = _probs(activity_weights_1), _probs(activity_weights_2)
    shared_list = sorted(shared)
    null_means = np.empty(n_iterations, dtype=float)
    # Per-position null Jaccards, same position order every iteration: the
    # pooled overall statistic aggregates these with the identical rule as
    # the observed position Jaccards (equal weight per position-transition).
    null_pos_jaccards: list[list[float]] = []

    def _draw(k: int, probs: np.ndarray | None) -> set:
        k = min(k, n_pool)
        if probs is None:
            return set(rng.choice(pool_arr, size=k, replace=False))
        return set(rng.choice(pool_arr, size=k, replace=False, p=probs))

    for it in range(n_iterations):
        acc = 0.0
        row: list[float] = []
        for p in shared_list:
            a = _draw(w1[p], probs_1)
            b = _draw(w2[p], probs_2)
            union = len(a | b)
            j = (len(a & b) / union) if union else 0.0
            row.append(j)
            acc += j
        null_pos_jaccards.append(row)
        null_means[it] = acc / len(shared_list)

    # Expected Jaccard under chance: E[|A cap B|] = w1*w2/N over
    # E[|A cup B|] = w1+w2-w1*w2/N. (An earlier version reported w1*w2/N
    # alone, which is the expected INTERSECTION size, not a Jaccard -- on
    # wide bridges it printed values > 1 next to a Jaccard, which is
    # incoherent. Fixed to the ratio.)
    def _exp_j(a: int, b: int) -> float:
        inter = a * b / n_pool
        union = a + b - inter
        return inter / union if union > 0 else 0.0

    expected_by_chance = float(np.mean([_exp_j(w1[p], w2[p]) for p in shared]))

    out = {
        "n_shared_positions": len(shared),
        "n_pool": n_pool,
        "n_iterations": n_iterations,
        "weighted": bool(probs_1 is not None or probs_2 is not None),
        "expected_overlap_by_chance": round(expected_by_chance, 4),
        "null_mean": round(float(null_means.mean()), 4),
        "null_sd": round(float(null_means.std(ddof=1)), 4) if n_iterations > 1 else 0.0,
        "null_ci95": [
            round(float(np.percentile(null_means, 2.5)), 4),
            round(float(np.percentile(null_means, 97.5)), 4),
        ],
        # The 95% band is a null REFERENCE interval, not a confidence interval.
        "null_reference_interval_95": [
            round(float(np.percentile(null_means, 2.5)), 4),
            round(float(np.percentile(null_means, 97.5)), 4),
        ],
        "observed_mean_jaccard": round(obs_mean, 4),
        "null_means": [round(float(v), 6) for v in null_means],
        # Per-position Jaccards in sorted-position order, observed and null:
        # the pooled overall statistic averages these with equal weight per
        # eligible position-transition observation, identically for observed
        # and every null realization.
        "position_jaccards": [round(float(v), 6) for v in observed],
        "null_position_jaccards": [
            [round(float(v), 6) for v in row] for row in null_pos_jaccards
        ],
    }
    if observed_mean_jaccard is None:
        out["p_value"] = None
    else:
        n_ge = int((null_means >= observed_mean_jaccard).sum())
        # Monte Carlo randomization p-value with +1 correction (Phipson &
        # Smyth 2010). NOT an exact permutation test: permutations are drawn,
        # not exhaustively enumerated.
        out["p_value"] = round((1 + n_ge) / (1 + n_iterations), 4)
        out["z_score"] = round(
            (observed_mean_jaccard - null_means.mean()) / null_means.std(ddof=1), 4
        ) if n_iterations > 1 and null_means.std(ddof=1) > 0 else None
    return out


def pooled_excess_overlap(transitions: list[dict]) -> dict:
    """ONE prespecified overall staffing statistic across transitions.

    PRIMARY STAFFING STATISTIC (frozen):
        pooled observed = mean occupant Jaccard across ALL eligible
        position-transition observations, equal weight per eligible
        position-transition.
    The same aggregation rule is applied to every Monte Carlo null
    realization: for iteration i, the pooled null value is the mean of that
    iteration's per-position null Jaccards across all eligible
    position-transitions. Overall p = Monte Carlo randomization p-value with
    +1 correction on the pooled statistic. Requires identical n_iterations
    and per-position null arrays in every transition (enforced); otherwise
    explicitly uncomputable. Transition-specific numbers are descriptive;
    this pooled value is the inferential headline. Never promote a single
    transition's p-value.
    """
    usable = [t for t in transitions
              if t.get("tracked_inference_allowed", True)
              and (t.get("occupant_turnover_null") or {}).get(
                  "null_position_jaccards")]
    if not usable:
        return {"n_transitions": 0,
                "note": "no eligible transitions with null arrays"}
    iters = {len(t["occupant_turnover_null"]["null_position_jaccards"])
             for t in usable}
    if len(iters) != 1:
        return {"n_transitions": len(usable),
                "note": "null iteration counts differ; pooled p uncomputable"}
    n_it = iters.pop()
    obs_flat: list[float] = []
    null_flat: list[list[float]] = [[] for _ in range(n_it)]
    for t in usable:
        tn = t["occupant_turnover_null"]
        obs_flat.extend(tn.get("position_jaccards", []))
        for i, row in enumerate(tn["null_position_jaccards"]):
            null_flat[i].extend(row)
    if not obs_flat:
        return {"n_transitions": len(usable),
                "note": "no eligible position-transition observations"}
    pooled_obs = float(np.mean(obs_flat))
    pooled_null = np.array([float(np.mean(row)) for row in null_flat])
    n_ge = int((pooled_null >= pooled_obs).sum())
    return {
        "n_transitions": len(usable),
        "n_position_transitions": len(obs_flat),
        "n_iterations": n_it,
        "aggregation": "equal weight per eligible position-transition",
        "pooled_observed": round(pooled_obs, 4),
        "pooled_null_mean": round(float(pooled_null.mean()), 4),
        "pooled_excess": round(pooled_obs - float(pooled_null.mean()), 4),
        "overall_null_interval": [round(float(np.percentile(pooled_null, 2.5)), 4),
                                  round(float(np.percentile(pooled_null, 97.5)), 4)],
        "overall_p_value": round((1 + n_ge) / (1 + n_it), 4),
    }


def evaluate_failure_gates(
    occ1: dict | None = None, occ2: dict | None = None,
    seed_agreement_ari: float | None = None,
    modularity_q: float | None = None,
    n_comms: int | None = None, n_nodes: int | None = None,
    match_rate: float | None = None, match_coverage: float | None = None,
    null_sd: float | None = None, n_brokers: int | None = None,
    dose_buckets: list[dict] | None = None,
    tracked_ok: bool = True,
    n_possible_pairs: int | None = None,
) -> dict:
    """Project-specific QC gates (NOT universal scientific constants).

    Each gate maps to a frozen rule: saturation >= 0.95, width bucket < 5,
    seed ARI < 0.60 or degeneracy, match rate < 60% or coverage < 80%,
    shared positions < 10, null SD == 0, broker-set failure. A failed gate
    demotes the corresponding claim to descriptive-only; mapping failure
    additionally forbids ALL tracked-position inference (no pooled-partition
    fallback -- that would artificially impose persistence).
    """
    gates: dict[str, dict] = {}

    shared = set(occ1 or {}) & set(occ2 or {})
    possible = n_possible_pairs
    if possible is None and n_comms:
        possible = n_comms * (n_comms - 1) // 2
    sat_ratio = (len(set(occ1 or {}) | set(occ2 or {})) / possible) \
        if possible else None
    gates["saturation"] = {
        "value": round(sat_ratio, 4) if sat_ratio is not None else None,
        "passed": bool(sat_ratio is not None and sat_ratio < 0.95),
        "on_fail": "no position-existence claim; width-only descriptive analysis",
    }

    thin = [b for b in (dose_buckets or [])
            if b.get("n_positions", 0) < 5]
    gates["width_sparsity"] = {
        "thin_buckets": len(thin),
        "passed": not thin,
        "on_fail": "no dose-response claim",
    }

    degenerate = bool(n_comms is not None and n_nodes is not None
                      and n_comms == n_nodes)
    nonpositive_q = bool(modularity_q is not None and modularity_q <= 0)
    gates["partition_stability"] = {
        "mean_seed_ari": seed_agreement_ari,
        "modularity_q": modularity_q,
        "degenerate": degenerate,
        "passed": bool(seed_agreement_ari is not None
                       and seed_agreement_ari >= 0.60
                       and not degenerate and not nonpositive_q),
        "on_fail": "no partition-dependent longitudinal inference",
    }

    gates["temporal_mapping"] = {
        "match_rate": match_rate, "match_coverage": match_coverage,
        "passed": bool(tracked_ok and match_rate is not None
                       and match_rate >= 0.60 and match_coverage is not None
                       and match_coverage >= 0.80),
        "on_fail": "quarter-specific descriptive results only; "
                   "NO tracked-position inference",
    }

    gates["bridge_sample"] = {
        "n_shared_positions": len(shared),
        "passed": len(shared) >= 10,
        "on_fail": "descriptive only; no p-value headline",
    }

    gates["null_usable"] = {
        "null_sd": null_sd,
        "passed": bool(null_sd is not None and null_sd > 0),
        "on_fail": "report 'uncomputable'; never p=0 or p=1",
    }

    gates["broker_set"] = {
        "n_brokers": n_brokers,
        "passed": bool(n_brokers is not None and n_brokers > 0 and shared),
        "on_fail": "descriptive-only broker analysis; insufficient sample",
    }

    gates["tracked_inference_allowed"] = {
        "value": bool(tracked_ok and gates["temporal_mapping"]["passed"]
                       and gates["partition_stability"]["passed"]
                       and gates["bridge_sample"]["passed"]),
        "passed": bool(tracked_ok and gates["temporal_mapping"]["passed"]
                       and gates["partition_stability"]["passed"]
                       and gates["bridge_sample"]["passed"]),
        "on_fail": "no staffing-vs-time claim",
    }
    return gates


def width_stability_dose_response(
    occ1: dict[tuple[int, int], set[str]],
    occ2: dict[tuple[int, int], set[str]],
) -> dict:
    """
    Does occupant persistence increase with bridge width? (H2)

    Buckets positions by their narrower width and reports mean occupant
    Jaccard per bucket. The original project's binary question -- "are bridges
    positional or individualistic?" -- assumes one answer for the whole frame.
    A gradient is both more likely to be true and more falsifiable: the null is
    a FLAT line across buckets, which is a concrete, testable prediction.
    """
    rows = occupant_stability_by_width(occ1, occ2)
    if not rows:
        return {"buckets": [], "note": "no bridge position is present in both quarters"}

    buckets: dict[str, list[float]] = {}
    for width, j in rows:
        if width <= 1:
            key = "1"
        elif width == 2:
            key = "2"
        elif width <= 4:
            key = "3-4"
        elif width <= 8:
            key = "5-8"
        else:
            key = "9+"
        buckets.setdefault(key, []).append(j)

    order = ["1", "2", "3-4", "5-8", "9+"]
    out = [
        {
            "width_bucket": k,
            "n_positions": len(buckets[k]),
            "mean_occupant_jaccard": round(float(np.mean(buckets[k])), 4),
        }
        for k in order if k in buckets
    ]
    # Spearman-style monotonicity check across populated buckets.
    populated = [b for b in out if b["n_positions"] >= 2]
    monotone = None
    if len(populated) >= 3:
        xs = np.arange(len(populated), dtype=float)
        ys = np.array([b["mean_occupant_jaccard"] for b in populated], dtype=float)
        if ys.std() > 0:
            monotone = round(float(np.corrcoef(xs, ys)[0, 1]), 4)
    return {"buckets": out, "bucket_trend_correlation": monotone}


def compare_position_vs_person_stability(
    pos1: set[tuple[int, int]],
    occ1: dict[tuple[int, int], set[str]],
    pos2: set[tuple[int, int]],
    occ2: dict[tuple[int, int], set[str]],
) -> dict[str, float]:
    """
    Calculates Position Stability Jaccard and Person Stability Jaccard.
    
    Returns:
        dict with:
            - 'position_stability': float
            - 'person_stability': float
            - 'stability_gap': float (position_stability - person_stability)
            - 'shared_positions_count': int
    """
    union_pos = pos1 | pos2
    inter_pos = pos1 & pos2

    j_position = len(inter_pos) / len(union_pos) if union_pos else 0.0

    if not inter_pos:
        j_person = 0.0
    else:
        person_jaccards = []
        for pos in inter_pos:
            u1 = occ1.get(pos, set())
            u2 = occ2.get(pos, set())
            u_union = u1 | u2
            u_inter = u1 & u2
            j_u = len(u_inter) / len(u_union) if u_union else 0.0
            person_jaccards.append(j_u)
        j_person = float(np.mean(person_jaccards))

    gap = j_position - j_person

    return {
        "position_stability": round(j_position, 4),
        "person_stability": round(j_person, 4),
        "stability_gap": round(gap, 4),
        "shared_positions_count": len(inter_pos),
        "total_positions_q1": len(pos1),
        "total_positions_q2": len(pos2),
    }


def _double_edge_swap_bipartite(
    edges: np.ndarray, rng: np.random.Generator, n_swaps: int
) -> np.ndarray:
    """
    Maslov & Sneppen (2002) double-edge swap on a bipartite edge list.

    Each accepted swap exchanges the subreddit endpoints of two edges whose users
    and whose subreddits are both distinct:
        (u1, s1), (u2, s2)  ->  (u1, s2), (u2, s1)
    Every user's degree and every subreddit's degree is therefore preserved
    EXACTLY, while the user->subreddit assignment pattern is destroyed.

    A swap is additionally rejected if it would give one user two edges to the
    same subreddit. The `s1 != s2` guard alone is not enough: it only makes the
    two swapped subreddits differ, not the resulting pairs new. Without this
    check, repeated swaps can pile two edges onto one (user, subreddit) pair,
    and collapsing the duplicate afterwards would silently drop a user's degree.

    Edges is an (m, 2) int array of (user_idx, subreddit_idx). Returns a new array.
    """
    e = np.array(edges, dtype=np.int64, copy=True)
    m = len(e)
    if m < 2:
        return e
    n_side = int(e[:, 1].max()) + 1
    present = {int(u) * n_side + int(s) for u, s in e}
    for _ in range(n_swaps):
        i, j = rng.integers(0, m, size=2)
        if i == j:
            continue
        u1, s1 = int(e[i, 0]), int(e[i, 1])
        u2, s2 = int(e[j, 0]), int(e[j, 1])
        if u1 == u2 or s1 == s2:
            continue
        k1, k2 = u1 * n_side + s2, u2 * n_side + s1
        if k1 in present or k2 in present:
            continue
        present.discard(u1 * n_side + s1)
        present.discard(u2 * n_side + s2)
        present.add(k1)
        present.add(k2)
        e[i, 0], e[i, 1] = u1, s2
        e[j, 0], e[j, 1] = u2, s1
    return e


def _rewire_dataframe(
    df: pd.DataFrame, rng: np.random.Generator, n_swaps_per_edge: int = 5
) -> pd.DataFrame:
    """Degree-preserving randomisation of a (author_h, subreddit) pair table."""
    users = pd.unique(df["author_h"]).tolist()
    subs = pd.unique(df["subreddit"]).tolist()
    u_idx = {u: i for i, u in enumerate(users)}
    s_idx = {s: j for j, s in enumerate(subs)}

    edges = np.array(
        [[u_idx[a], s_idx[b]] for a, b in zip(df["author_h"], df["subreddit"])],
        dtype=np.int64,
    )
    swapped = _double_edge_swap_bipartite(
        edges, rng, n_swaps=n_swaps_per_edge * len(edges)
    )

    out = df.copy()
    out["author_h"] = [users[i] for i in swapped[:, 0]]
    out["subreddit"] = [subs[j] for j in swapped[:, 1]]
    # A swap can collide two pairs into one. Collapse duplicates so the rewired
    # table keeps the same "one row per distinct (user, subreddit)" granularity
    # the downstream analysis expects.
    return out.drop_duplicates(subset=["author_h", "subreddit"]).reset_index(drop=True)


def _analyze_quarter(
    df: pd.DataFrame, alpha: float, broker_percentile: float
) -> tuple[set[tuple[int, int]], dict[tuple[int, int], set[str]]]:
    """Full downstream chain: projection -> backbone -> Leiden -> brokers -> bridges.

    Both the observed statistic and every null iteration go through THIS function,
    so the null cannot drift out of sync with what is actually being measured.
    """
    M, _, subs, _, _ = build_bipartite_matrix(df)
    G = compute_cosine_projection(M, subs)
    G_bb = disparity_filter(G, alpha=alpha)
    partition, _, _ = detect_communities_leiden(G_bb)
    brokers = compute_participation_coefficients(
        df, partition, broker_percentile=broker_percentile
    )
    return extract_bridge_positions(df, brokers, partition, matched_map=None)


def run_degree_preserving_null_model(
    df_q1: pd.DataFrame,
    df_q2: pd.DataFrame,
    observed_gap: float | None = None,
    n_iterations: int = 200,
    seed: int = 0,
    alpha: float = 0.05,
    broker_percentile: float = 0.99,
    min_width: int = 1,
    n_swaps_per_edge: int = 5,
) -> dict:
    """
    Degree-preserving null for the H1 stability gap (Maslov & Sneppen, 2002).

    Each iteration independently rewires BOTH quarters with double-edge swaps
    (exact preservation of every user's and every subreddit's degree), rebuilds
    the whole chain, and records the resulting position-minus-person Jaccard gap.
    The observed gap is then compared against that empirical distribution.

    The p-value is the standard one-sided exact permutation p-value,
        p = (1 + #{null >= observed}) / (1 + n_iterations),
    which is valid (never reports p=0) and is what should be quoted.

    NOTE on limits: a degree-preserving null controls for degree and density
    only. Real networks are disassortative, and an uncorrelated configuration
    ensemble has a different expected modularity than a real network
    (Squartini & Garlaschelli, 2011, New J. Phys. 13, 083001). Surviving THIS
    null is a weak result; a maximum-entropy null is the stronger test.
    """
    rng = np.random.default_rng(seed)
    null_gaps: list[float] = []

    for it in range(n_iterations):
        pos1, occ1 = _analyze_quarter(
            _rewire_dataframe(df_q1, rng, n_swaps_per_edge), alpha, broker_percentile
        )
        pos2, occ2 = _analyze_quarter(
            _rewire_dataframe(df_q2, rng, n_swaps_per_edge), alpha, broker_percentile
        )
        if min_width > 1:
            pos1 = {p for p in pos1 if len(occ1[p]) >= min_width}
            pos2 = {p for p in pos2 if len(occ2[p]) >= min_width}

        stab = compare_position_vs_person_stability(pos1, occ1, pos2, occ2)
        null_gaps.append(stab["stability_gap"])
        if (it + 1) % 25 == 0:
            log.info("  null iteration %d/%d", it + 1, n_iterations)

    arr = np.array(null_gaps, dtype=float)
    out = {
        "n_iterations": n_iterations,
        "null_gap_mean": round(float(arr.mean()), 4),
        "null_gap_std": round(float(arr.std(ddof=1)), 4) if len(arr) > 1 else 0.0,
        "null_gap_ci95": [
            round(float(np.percentile(arr, 2.5)), 4),
            round(float(np.percentile(arr, 97.5)), 4),
        ],
        "null_gaps": [round(float(g), 4) for g in null_gaps],
    }
    if observed_gap is not None:
        n_ge = int((arr >= observed_gap).sum())
        out["observed_gap"] = round(float(observed_gap), 4)
        out["n_null_ge_observed"] = n_ge
        out["p_value"] = round((1 + n_ge) / (1 + n_iterations), 4)
    else:
        out["observed_gap"] = None
        out["p_value"] = None
    return out

