"""Sentiment validation: a labelled sample to measure VADER against, and agreement statistics.

    python -m findings.validation export   # writes a stratified sample (local cache; text never leaves the machine)
    python -m findings.validation score    # reads the labelled sample and reports accuracy, macro-F1 and Cohen's kappa

The sample file carries comment id, subreddit, month, a 300-character excerpt and VADER's label; the `label` column
is for the human (or disclosed non-human) annotator: pos / neu / neg. Only the agreement statistics are published.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import config as F
from . import io as IO
from . import text as T

SAMPLE = F.CACHE / "sentiment_validation_sample.csv"


def export(n_per_cell: int = 12, seed: int = 42) -> pd.DataFrame:
    """Stratified by subreddit group (marvel / crypto / debate) x VADER label, from a few months."""
    rng = np.random.default_rng(seed)
    groups = {"marvel": ["marvelstudios", "marvel"], "crypto": ["bitcoin", "cryptocurrency"], "debate": ["capitalismvsocialism", "purplepilldebate"]}
    rows = []
    for gname, subs in groups.items():
        for month in ("2017-12", "2018-04", "2018-08"):
            if month not in IO.available_months():
                continue
            df = IO.comments(subs, f"{month}-01", f"{month}-28", with_text=True)
            df = df[~df["body"].isin(["[deleted]", "[removed]"]) & (df["body"].str.len() >= 15)]
            sent = T.load_sentiment([month])
            df = df.merge(sent[["id", "compound"]], on="id", how="inner")
            df["vader"] = T.label(df["compound"])
            for lab in ("pos", "neu", "neg"):
                part = df[df["vader"] == lab]
                take = part.sample(min(n_per_cell, len(part)), random_state=int(rng.integers(1e9))) if len(part) else part
                for _, r in take.iterrows():
                    rows.append({"id": r["id"], "group": gname, "subreddit": r["subreddit"], "month": month, "excerpt": T.clean_body(r["body"])[:300],
                                 "compound": round(float(r["compound"]), 3), "vader": lab, "label": ""})
    out = pd.DataFrame(rows).sample(frac=1, random_state=seed).reset_index(drop=True)
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(SAMPLE, index=False, encoding="utf-8")
    return out


def agreement(df: pd.DataFrame) -> dict:
    from sklearn.metrics import cohen_kappa_score, f1_score, accuracy_score, confusion_matrix
    d = df[df["label"].isin(["pos", "neu", "neg"])]
    labs = ["pos", "neu", "neg"]
    cm = confusion_matrix(d["label"], d["vader"], labels=labs)
    out = {"n": int(len(d)), "accuracy": round(float(accuracy_score(d["label"], d["vader"])), 3),
           "macro_f1": round(float(f1_score(d["label"], d["vader"], labels=labs, average="macro")), 3),
           "kappa": round(float(cohen_kappa_score(d["label"], d["vader"], labels=labs)), 3),
           "confusion": {a: {b: int(cm[i, j]) for j, b in enumerate(labs)} for i, a in enumerate(labs)},
           "binary_pos_neg_accuracy": None}
    b = d[d["label"].isin(["pos", "neg"]) & d["vader"].isin(["pos", "neg"])]
    if len(b):
        out["binary_pos_neg_accuracy"] = round(float((b["label"] == b["vader"]).mean()), 3)
        out["binary_n"] = int(len(b))
    for g, part in d.groupby("group"):
        out[f"accuracy_{g}"] = round(float((part["label"] == part["vader"]).mean()), 3)
    if "compound" in d:   # the same comparison at the stricter sensitivity threshold (reported, never tuned on)
        strict = T.label(d["compound"].to_numpy(dtype=float), F.STRICT_THRESH)
        out["strict_threshold"] = F.STRICT_THRESH
        out["accuracy_strict"] = round(float(accuracy_score(d["label"], strict)), 3)
        out["macro_f1_strict"] = round(float(f1_score(d["label"], strict, labels=labs, average="macro")), 3)
        out["kappa_strict"] = round(float(cohen_kappa_score(d["label"], strict, labels=labs)), 3)
        out["annotator_label_shares"] = d["label"].value_counts(normalize=True).round(3).to_dict()
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "export"
    if cmd == "export":
        s = export()
        print(f"wrote {SAMPLE} with {len(s)} rows; fill the 'label' column (pos/neu/neg) and run: python -m findings.validation score")
    else:
        d = pd.read_csv(SAMPLE, encoding="utf-8")
        print(agreement(d))
