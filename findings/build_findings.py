"""Build the Findings artifacts: atlas/web/data/findings/*.json (+ selection-matrix table for the research note).

Usage:
    python -m findings.build_findings                 # everything (scores sentiment first if the cache is missing)
    python -m findings.build_findings --only bitcoin  # one story
    python -m findings.build_findings --score-only    # just the VADER cache
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from . import config as F
from . import io as IO
from . import stories as S
from . import text as T


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not serialisable: {type(o)}")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_json_default), encoding="utf-8")
    os.replace(tmp, path)


def score_all(months: list[str]) -> None:
    for m in months:
        t = time.time()
        p = T.score_month(m)
        log(f"sentiment {m}: {p.name} ({time.time() - t:.0f}s)")


def insights_index(stories: dict) -> list[dict]:
    out = []
    for sid, st in stories.items():
        for k, ins in enumerate(st.get("insights", [])):
            out.append({"story": sid, "story_title": st["title"], "index": k, **ins})
    # confidence first; within a confidence level, insights that carry a corrected test (smaller q first) come before
    # untested descriptive ones, in story order (the focused community first, then Infinity War, then Bitcoin), then by q
    # and build order, so the ranking does not depend on which story happens to sort first alphabetically
    rank = {"high": 0, "medium": 1, "descriptive": 2}
    story_order = {"community": 0, "infinity_war": 1, "bitcoin": 2}
    out.sort(key=lambda i: (rank.get(i["confidence"], 3), i.get("q_value") is None, story_order.get(i["story"], 9),
                            i.get("q_value") if i.get("q_value") is not None else 0.0, i["index"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["community", "infinity_war", "bitcoin"], default=None)
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--chosen", default=None, help="override the focused community (default: top of the selection matrix)")
    ap.add_argument("--index-only", action="store_true", help="rebuild index.json and the research notes from the stories already built")
    args = ap.parse_args()
    months = IO.available_months()
    log(f"months in the text store: {months}")
    if not args.index_only:
        score_all(months)
    if args.score_only:
        return
    F.OUT.mkdir(parents=True, exist_ok=True)
    stories = {}
    existing = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in F.OUT.glob("*.json") if p.stem in ("community", "infinity_war", "bitcoin")}
    todo = [] if args.index_only else [args.only] if args.only else ["infinity_war", "community", "bitcoin"]
    for sid in todo:
        t = time.time()
        if sid == "infinity_war":
            st = S.build_infinity_war()
        elif sid == "bitcoin":
            st = S.build_bitcoin()
        else:
            st = S.build_community(chosen=args.chosen)
        write_json(F.OUT / f"{sid}.json", st)
        stories[sid] = st
        log(f"{sid}: {len(st.get('insights', []))} insights, {(F.OUT / (sid + '.json')).stat().st_size / 1e6:.1f} MB ({time.time() - t:.0f}s)")
    stories = {**existing, **stories}
    index = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "months": months,
             "manifest": IO.month_manifest().get("months", {}),
             "stories": [{"id": sid, "title": st["title"], "question": st["narrative"]["question"], "insights": len(st.get("insights", []))} for sid, st in stories.items()],
             "insights": insights_index(stories)}
    vres = F.CACHE / "sentiment_validation_result.json"
    if vres.exists():
        index["validation"] = json.loads(vres.read_text(encoding="utf-8"))
    write_json(F.OUT / "index.json", index)
    log(f"index.json: {len(index['insights'])} insights across {len(stories)} stories")
    # research notes generated from the same numbers the app shows
    from . import docs as D
    if "community" in stories:
        import pandas as pd
        pd.DataFrame(stories["community"]["matrix"]).to_csv(F.DOCS / "findings_candidate_matrix.csv", index=False)
        D.write_selection_note(stories["community"])
        log("docs/FINDINGS_COMMUNITY_SELECTION.md written")
    if "infinity_war" in stories or "bitcoin" in stories:
        D.write_event_comparison(stories.get("infinity_war"), stories.get("bitcoin"))
        log("docs/FINDINGS_EVENT_COMPARISON.md written")
    from .demo_guide import write_demo_guide
    write_demo_guide(stories)
    log("docs/FINDINGS_DEMO_GUIDE.md written")


if __name__ == "__main__":
    sys.exit(main())
