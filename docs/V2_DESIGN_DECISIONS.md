# Atlas V2: design decisions

Branch `atlas-narrative-v2`. The V1 atlas (branch `main`, commit `992462c`) remains runnable and unchanged; V1 of the
research pipeline is preserved at tag `v1-baseline`.

## The problem V2 solves

The first atlas was a capable explorer attached to a report. A first-time visitor met a hairball and a row of metric
cards before any question had been asked, had to infer what a line meant, and could only reach the discoveries by
already knowing to click them. The method (expected overlap, false-discovery rate) lived in prose on a methods page.
V2 is organised around four stages the visitor should pass through in order: **discover → explore → understand → verify**.

## Decisions

| Decision | Choice | Why | Alternatives considered |
|---|---|---|---|
| Opening | A scroll-driven sequence: a question with two real pairs (one big-but-ordinary, one small-but-surprising), then raw → "chance vs surprise" → adjusted on one map | The transformation *is* the argument; showing it beats describing it. Numbers come from `pairs_all.json` at load time | A static hero with a toggle (V1); a video; an animated intro with no interaction |
| The three map views | `raw` (every pair sharing a commenter), `surprise` (same edges, grey within chance, coloured when validated), `adjusted` (validated only) | The middle view answers "what did you throw away?", which both lay visitors and examiners ask | Only raw/adjusted (V1) |
| Encoding legend | One legend component (`legendHTML`) reused in the opening, the explorer ("How to read it") and the stories; it states that distance is a layout convenience | Every encoding must have a defensible meaning, and the layout must not be read as a measurement | Per-page ad hoc captions |
| Guided tour | An overlay (`tour.js`) that drives the real pages through a small page API (`registerPage`/`currentPage`); state in `sessionStorage`; detach by navigating, resume from a pill | A tour of screenshots would not prove the app works; the page API keeps the tour decoupled from page internals | Slides/screenshots; a modal wizard that re-implements the views |
| Discoveries | Each story keeps its map-driven steps and gains a takeaway step and "investigate it yourself" actions; evidence and caveats are collapsible | A story should end with something to remember and a way to check it, not a chart | Longer prose per story; more stories |
| Technical walkthrough | A 9-stage page (`#/pipeline`) fed by a new `pipeline.json`: real counts, a worked example with the breadth of the shared commenters, a toy BiCM example run through the real model, the test inventory, artifact hashes, and badges separating precomputed / in-browser / historical | Evaluators must see what runs where; the app is static and says so | Reusing the methods prose; a diagram image |
| Lower tail | The model now also flags pairs that share significantly *fewer* commenters than expected (`avoided`), with an effect-size floor (affinity ≤ 0.5, expected ≥ 20) so that huge pairs with trivial shortfalls are not flagged | It is the natural counterpart of the upper tail and makes "within chance" a three-way verdict (more / about / fewer) | Report upper tail only (V1) |
| p-values published | Two-significant-digit p-values per pair per period in the pairs files | Compare and the worked example can show the actual test result rather than a yes/no | Keep booleans only (smaller files) |
| Data size | Pairs files grow by ~30% (p-values) and `pipeline.json` is added; everything stays static JSON, total under 8 MB | No backend, hostable on GitHub Pages | A server-side API |
| Mobile | Sticky stage above scrolling steps; controls and drawers become bottom sheets; callouts hidden; stories stack | The demo may be shown on a phone or a narrow projector window | Desktop only |
| Accessibility | Keyboard navigation for the tour (arrows, Esc), stage track (arrows), lists as buttons; `aria-live` on narrative text; `prefers-reduced-motion` disables camera animation; skip link | Course and general practice | — |
| Colour | Unchanged validated palette (dark categorical slots); verdict colours green/orange reserved for surprising / fewer-than-chance | Consistent encodings across pages | — |

## What was deliberately not built

- No live statistical recomputation in the browser: the FDR procedure is global over all pairs and belongs in the
  pipeline; the page says plainly what is precomputed.
- No new data beyond the 12 months already processed: the stories hold at this scope, and a larger download would not
  change what co-commenting can show.
- No reply-network or text layer: the stored fields have neither, and claiming conversation or sentiment from
  co-presence would be false.

## Truthfulness rules carried into every screen

- Association, not causation, for anything dated.
- "Within chance" is the default state of a pair; "surprising" and "fewer than chance" are test results with a 1% FDR.
- The frame is a sample of 170 subreddits; nothing is said about Reddit as a whole.
- Every number on screen is read from a generated artifact (`atlas/web/data/*.json`); the report and deck are
  generated from the same files.

## Findings revised by the truth audit

Every claim in the discoveries, the report and the deck was recomputed from the published artifacts and challenged by independent reviewers before V2 shipped. What changed:

- **Crowds.** The V1 reading ("ties tightened after the crypto exodus") is dropped. Affinity compares observed overlap with an expectation that scales with community size, so r/Bitcoin–r/CryptoCurrency affinity rose 3.37× → 9.8× while the share of r/Bitcoin commenters also in r/CryptoCurrency moved only 24% → 28% (reverse share 38% → 21%, cosine 0.31 → 0.24). The discovery now shows the obvious reading, the careful reading, two crowds arriving (The Last Jedi: r/StarWars ×2.97 in a month, 70% newcomers; Infinity War) and the general tendency (growth vs affinity drift ρ = -0.52, vs raw-overlap drift ρ = 0.79).
- **Popularity.** "All ten best-connected communities are hubs" became 8 of 10 (all ten sit in the front-page cluster). Added: the largest shared audience that is never a surprising link (r/AskReddit – r/worldnews, 470,607 shared vs 472,898 expected, 1.00×), the affinity ceiling of the giants (r/AskReddit holds 62% of commenters, so at most about 1.2×) and the 36 of 170 subreddits whose raw and adjusted top-five lists share no name.
- **Neighbours.** "Nationality organises audiences" became "consistent with shared nationality in the two cases the frame contains", with a control: the same personal-finance topic across the border (r/PersonalFinanceCanada – r/UKPersonalFinance) shares 0.28× of expectation. A lower-tail test was added end to end (p-values per pair, the "avoided" rule: FDR 1%, affinity ≤ 0.5, expected ≥ 20), which turns the story into *neighbours and strangers*: r/linux – r/MakeupAddiction 0.042×, beauty/fashion/fibre-craft vs the tech cluster 0.18×, r/manga apart from 144 of 169; political opponents all share more than chance (21 of 21 pairs).
- **Connectors.** The hub-vs-topical participation gap is not statistically significant and is no longer claimed; r/NoStupidQuestions, a hub, sits among the top connectors and is labelled as such. Added: how sealed each cluster is (Politics & news sends 66% of its links outward, Support & health 37%, each against a degree-preserving rewiring) and r/AskReddit's 26 of 26 links inside its own cluster.
- **Communities.** "9 communities" is stated as 6 major communities plus 2 small groups and 1 isolate; they *partly* follow the frame categories (ARI 0.481), and 24 of 170 keyword labels disagree with the network's nearest category (listed on Scope & limits).
- **Measurement notes now stated in the app.** Pooled (whole-window) affinities are not comparable with quarterly ones; the submitted bridge-turnover hypothesis is not answered by this project; every number on a page is either precomputed by `atlas/build_atlas.py` (badge), computed in the browser from the published pairs files, or historical (V1).
