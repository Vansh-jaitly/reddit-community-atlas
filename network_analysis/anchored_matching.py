"""
anchored_matching.py
====================
Matches quarterly Leiden communities against a single pooled anchor reference
partition, so that "the same" community keeps the same id across quarters
(Step 5 of methodology). Without this, a quarter's raw Leiden labels are
arbitrary integers and comparing community pairs between quarters compares
meaningless numbers.

METHOD
------
Communities are compared by Jaccard membership overlap of their subreddit sets,
and the assignment is solved as a ONE-TO-ONE maximum-weight matching with
`scipy.optimize.linear_sum_assignment`. One-to-one matters: the previous version
matched each quarter community to its own best anchor independently, so several
quarter communities could all collapse onto the same anchor community, merging
distinct communities into one. Only pairs at or above `jaccard_threshold` are
accepted; the rest are left UNMATCHED.

CONTRACT FOR CALLERS
---------------------
`matched_map` contains ONLY genuine matches. Unmatched quarter communities are
deliberately absent rather than being mapped to a fallback id, because any id
this function invents would live in the anchor id space and could alias an
unrelated anchor community. Callers are expected to move unmatched communities
out of that space themselves (see `stability_analysis._remap_community_ids`).
Putting a fallback entry here is what previously caused two unrelated
communities to be reported as one bridge position.

DIAGNOSTIC ROLES (do not conflate):
    ARI/NMI (quarter vs anchor, quarter vs quarter)
    -> GLOBAL partition similarity. Answers whether two partitions resemble
       each other overall. Alone, this does NOT establish reliable
       longitudinal identity of any specific community.
    Hungarian/Jaccard matching
    -> COMMUNITY-LEVEL temporal alignment for position tracking. Answers
       which specific quarter community corresponds to which anchor label,
       which is what bridge-position tracking requires.
Both are required; neither alone suffices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


def _communities(partition: dict[str, int]) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for sub, cid in partition.items():
        out.setdefault(cid, set()).add(sub)
    return out


def jaccard_matrix(
    q_comms: dict[int, set[str]], anchor_comms: dict[int, set[str]]
) -> tuple[np.ndarray, list[int], list[int]]:
    """Jaccard overlap between every quarter community and every anchor community."""
    q_ids = sorted(q_comms)
    a_ids = sorted(anchor_comms)
    M = np.zeros((len(q_ids), len(a_ids)), dtype=float)
    for i, q in enumerate(q_ids):
        qs = q_comms[q]
        for j, a in enumerate(a_ids):
            a_s = anchor_comms[a]
            union = len(qs | a_s)
            M[i, j] = len(qs & a_s) / union if union else 0.0
    return M, q_ids, a_ids


def match_quarter_to_anchor(
    quarter_partition: dict[str, int],
    anchor_partition: dict[str, int],
    jaccard_threshold: float = 0.3,
) -> tuple[dict[int, int], list[dict]]:
    """
    One-to-one maximum-Jaccard matching of quarter communities to anchor communities.

    Args:
        quarter_partition: {subreddit: q_comm_id}
        anchor_partition: {subreddit: anchor_comm_id}
        jaccard_threshold: minimum Jaccard similarity to accept a match. Matches
            below this are reported as unmatched and omitted from matched_map.

    Returns:
        matched_map: {q_comm_id: anchor_comm_id} -- genuine matches ONLY
        match_records: one audit dict per quarter community, including the
            Jaccard score, whether it matched, and -- for a split/merged
            community -- how its subreddits were distributed across anchors.
    """
    q_comms = _communities(quarter_partition)
    anchor_comms = _communities(anchor_partition)
    if not q_comms or not anchor_comms:
        return {}, []

    M, q_ids, a_ids = jaccard_matrix(q_comms, anchor_comms)

    # Optimal one-to-one assignment over the full score matrix. Rejecting
    # sub-threshold pairs afterwards (rather than zeroing first) still yields the
    # optimal *accepted* matching, because the assignment only ever moves weight
    # to strictly better pairs.
    rows, cols = linear_sum_assignment(-M)

    matched_map: dict[int, int] = {}
    best_for: dict[int, tuple[float, int | None]] = {}
    for i, j in zip(rows, cols):
        q_cid, a_cid = q_ids[i], a_ids[j]
        score = float(M[i, j])
        best_for[q_cid] = (score, a_cid)
        if score >= jaccard_threshold:
            matched_map[q_cid] = a_cid

    match_records = []
    for q_cid in q_ids:
        score, best_anchor = best_for.get(q_cid, (0.0, None))
        matched = q_cid in matched_map
        rec = {
            "quarter_comm_id": q_cid,
            "anchor_comm_id": matched_map.get(q_cid),
            "jaccard_similarity": round(score, 3),
            "status": "matched" if matched else "unmatched",
            "subreddits_count": len(q_comms[q_cid]),
        }
        if not matched and best_anchor is not None:
            # The quarter community is real but did not correspond to any single
            # anchor community: it most likely split or merged across quarters.
            # Record that explicitly instead of forcing it onto a wrong label.
            rec["nearest_anchor_comm_id"] = best_anchor
            rec["reason"] = "split_or_merge"
        match_records.append(rec)

    return matched_map, match_records


def summarise_matches(match_records: list[dict]) -> pd.DataFrame:
    """Audit table: how much of each quarter's structure was actually matched."""
    if not match_records:
        return pd.DataFrame(
            columns=["quarter_comm_id", "anchor_comm_id", "jaccard_similarity",
                     "status", "subreddits_count", "nearest_anchor_comm_id", "reason"]
        )
    return pd.DataFrame(match_records)
