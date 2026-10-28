# Atlas V2: completion report

Branch `atlas-narrative-v2`, built on `main` at `992462c` (the V1 Atlas, untouched; the pre-Atlas pipeline remains at tag `v1-baseline`). Nothing was pushed; no history was rewritten.

## What changed

**The application** (`atlas/web/`) was rebuilt around *Discover → Explore → Understand → Verify*:

- **Start**: a scroll-driven opening with two real pairs (one large but ordinary, one small but surprising) and one map that turns from the raw hairball into "chance vs surprise" and then into the surprising links alone, with the legend (size, line, colour, "distance is not a measurement") beside it.
- **Discoveries**: four guided stories whose every number is produced by `atlas/build_atlas.py` — *What popularity hides*, *Neighbours and strangers*, *Connectors and sealed rooms*, *When crowds arrive and leave*. Each step moves the real map (callouts, highlighted edges, selections), shows the evidence and the caveats beside it, and ends with a takeaway plus actions to check the finding independently.
- **Guided tour** (`assets/tour.js`): ten steps that drive the real pages (map views, a profile, two discoveries, the technical walkthrough, the limits); start, back/next, exit, and resume from a pill after navigating away.
- **The map**: three line views (surprising / chance vs surprise / raw), colour by detected group or by the pre-analysis label (same name = same colour), period selector, "back to overview", a drawer with the strongest overlaps, the pairs a community shares *fewer* commenters with than chance, and what raw overlap would have shown; selected nodes land beside the drawer, not under it.
- **Profiles, Compare**: three-way verdicts (surprising / within chance / fewer than chance) with p-values; period comparison with a support floor and the churn baseline; months as well as quarters.
- **How it's made**: nine real pipeline stages from `pipeline.json` (input, transformation, output, why, a worked example, the tests that guard the stage, what would go wrong), BiCM at an intuitive and a technical level, a toy example through the real model, and badges separating precomputed, computed-in-browser and historical (V1) material.
- **Scope & limits**: what can and cannot be concluded, including that the submitted bridge-turnover hypothesis is not answered here, the pooled-vs-quarter caveat, the affinity ceiling of the giants, and the 24 keyword labels the network disagrees with.

**The analysis** (`network_analysis/affinity.py`, `atlas/build_atlas.py`): a lower-tail test (pairs that share *fewer* commenters than chance; "avoided" rule: FDR 1 %, affinity ≤ 0.5, expected ≥ 20) end to end, p-values per pair in the published files, `pipeline.json` facts, a `--stories-only` mode (seconds, no Parquet) that also refreshes the facts file, atomic JSON writes, and new tests (`TestLowerTail`, artifact consistency, pipeline facts).

## Findings, and how they were validated

Six analysts proposed candidate insights, each attacked by two skeptics; a truth audit recomputed every published number; after the build, five independent reviewers (numbers, report, front-end, first-time visitor, privacy) and two skeptics per finding reviewed the finished product. Ten confirmed findings were fixed (wording that dropped a qualifier, a colour bug, the retracted crypto reading surviving in the tour and README, pooled ratios presented as quarterly, a narrow-viewport capture that was not narrow, and others). What the audit changed:

- **Crowds** — the V1 reading "ties tighten after the exodus" is retracted. Affinity is relative to an expectation that scales with size; r/Bitcoin–r/CryptoCurrency went 3.37× → 9.8× while the share of r/Bitcoin commenters also in r/CryptoCurrency moved 24 % → 28 %. The story now shows the obvious and the careful reading, two crowds arriving (The Last Jedi, Infinity War) and the general tendency (growth vs affinity drift ρ = −0.52; vs raw-overlap drift ρ = +0.79).
- **Popularity** — 8 of the 10 best-connected communities by raw overlap are hubs (not all); the largest shared audience that is never a surprising link (r/AskReddit–r/worldnews, 470,607 vs 472,898 expected); the ceiling (r/AskReddit at most ≈1.2×); 36 of 170 subreddits whose raw and adjusted top-five lists share no name.
- **Neighbours and strangers** — "consistent with shared nationality" with a control (same topic across the border 0.28×); strangers (r/linux–r/MakeupAddiction 0.042×; beauty/craft vs tech 0.18×, 0.16–0.17× by quarter); political opponents all above chance.
- **Connectors** — the hub-vs-topical gap is not significant and no longer claimed; sealed vs porous clusters (Politics & news 66 % outward, Support & health 37 %); r/AskReddit keeps all 26 links inside its cluster.
- **Communities** — stated as 6 major (plus 2 small groups and 1 isolate); they *partly* follow the labels (ARI 0.48).

Details and the decision log: `docs/V2_DESIGN_DECISIONS.md`.

## Tests and checks

- `python -m pytest tests/`: **111 passed, 1 skipped** (the skip needs the optional `bicm` package).
- Every story step and every route (including malformed arguments) exercised in a real browser with no console errors; headless captures of 22 views at 1440×900 and two at 390×844 (`docs/screenshots/`), inspected.
- Documents regenerated from the artifacts: `docs/FINAL_REPORT.{md,html,pdf}`, `docs/DEMO_SCRIPT.md`, `docs/presentation/Community_Atlas.pptx`, `docs/demo/atlas_walkthrough.mp4` (captioned screenshots, 150 s — not a screen recording).
- Privacy sweep: no salts, tokens, author hashes or usernames in the diff; hard-coded local paths removed from tracked files; `.claude/` ignored.

## Launch

```bash
pip install -r requirements.txt
python atlas/serve.py              # http://127.0.0.1:8000 — Start → "Take the 5-minute tour"
python -m pytest tests/
streamlit run data_curation/dashboard.py     # Data & Pipeline Console
python atlas/build_atlas.py --stories-only   # regenerate stories.json + pipeline facts in seconds
python tools/build_docs.py --pdf && (cd tools/deck && npm run build) && python tools/capture_screens.py && python tools/make_walkthrough_video.py
```

## Remaining limitations

- One sample of 170 subreddits over 12 months, commenters only, no text: which audiences meet is a fact in the data, why is not; events are associations.
- Affinity is relative to a size-dependent expectation; the giants are capped near 1 by construction and sharp size changes move the ratio even when cross-posting does not (hence the cross-posting share beside it).
- Pooled (whole-window) affinities are lower than quarterly ones and not comparable with them.
- The lower-tail test cannot mark small pairs (floor: expected ≥ 20); its count depends on that floor.
- The newcomer share for The Last Jedi month (70 %) uses the window as its look-back, so early months have less history (later months ≈ 29 %).
- The guided tour was verified in Chrome (desktop and 390 px emulation); other browsers were not tested. The video is a captioned slideshow of real screenshots.
- `docs/CONTRIBUTION_MATRIX.md` rows for the Atlas and V2 phases are still "to confirm" by the team.
