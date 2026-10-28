# Speaker notes — Beyond the Hairball

## Slide 1 — Title
- **Says:** project title, longitudinal Reddit analysis, 2018 Q1–Q3, 170 subreddits.
- **Means:** sets the research frame before any method appears.
- **Do NOT claim:** any finding on this slide.

## Slide 2 — Research question
- **Says:** bridges have a structural side (does the position persist?) and a staffing side (do the people persist?).
- **Means:** the two quantities are measured separately throughout.
- **Do NOT claim:** that either one was confirmed.

## Slide 3 — Data scale
- **Says:** 170 subreddits, 3 quarters, 171.6M raw / 161.7M retained, ≈94.2% retention.
- **Means:** the experiment runs on genuinely large longitudinal data, not a sample.
- **Do NOT claim:** that scale alone validates the network representation.

## Slide 4 — Pipeline
- **Says:** comments → bipartite data → overlap → network → communities → brokers → positions → temporal comparison, with privacy and reproducibility rails.
- **Means:** every stage is inspectable and rerunnable.
- **Do NOT claim:** results; this slide is machinery only.

## Slide 5 — Measurement lens
- **Says:** a connection means shared audience, normalized by size; every shared user can create an edge.
- **Means:** foreshadows why the network becomes dense.
- **Do NOT claim:** that dense edges are meaningful relationships.

## Slide 6 — Hairball
- **Says:** 14,343 of 14,365 possible pairs connected (99.85%).
- **Means:** the projection stopped discriminating; almost everything connects to almost everything.
- **Do NOT claim:** that Reddit has no structure — only that this lens cannot resolve it.

## Slide 7 — Full vs backbone
- **Says:** full graph 14,343 edges vs α=0.3 backbone 5,981 edges; backbone is display-only.
- **Means:** visual clarity is not statistical validity.
- **Do NOT claim:** the backbone communities are findings.

## Slide 8 — Communities
- **Says:** 4 groups, seed ARI 0.88–0.94, quality Q ≤ 0 at every tested resolution.
- **Means:** reproducible across seeds yet structurally unconvincing.
- **Do NOT claim:** these are real communities; the gate failed.

## Slide 9 — Saturation
- **Says:** 6/6 pairs bridged, ~4–5.6k occupants each.
- **Means:** the detector selects everything, so it measures nothing selective.
- **Do NOT claim:** that six bridges were discovered.

## Slide 10 — Temporal
- **Says:** width Jaccard ≈0.50 both transitions, correlations 1.00/0.96, mapping 100%/100% then 75%/96%; descriptive only.
- **Means:** the tracking machinery runs, but the tracked objects failed validity.
- **Do NOT claim:** persistence of real bridge structure.

## Slide 11 — Turnover
- **Says:** observed 0.055/0.027 vs Monte Carlo null means 0.324/0.378; descriptive only.
- **Means:** an interesting directional pattern that is not inferentially admissible.
- **Do NOT claim:** support for the turnover hypothesis.

## Slide 12 — Failed / did not fail
- **Says:** pipeline worked; measurement lens did not.
- **Means:** the central lesson of the project.
- **Do NOT claim:** anything beyond this distinction.

## Slide 13 — Story
- **Says:** the negative result became the methodological finding.
- **Means:** the data showed the lens could not see bridges, not that bridges don't exist.
- **Do NOT claim:** the hypothesis is false.

## Slide 14 — Next step
- **Says:** move from "who overlaps?" to "who overlaps more than expected?"; two candidate families.
- **Means:** the next experiment controls degree-driven overlap.
- **Do NOT claim:** a chosen method — selection comes later, on validity grounds.

## Slide 15 — Takeaways
- **Says:** pipeline works at scale; first representation too dense; failure directs the next experiment.
- **Means:** close on what is known, not what was hoped.
- **Do NOT claim:** more than these three sentences.

## Slide 16 — References
- **Says:** the seven methodological sources actually used.
- **Means:** every method on slides 4–5 and 14 traces to a citation.
- **Do NOT claim:** broader literature coverage than these seven.

## Appendix A — Resolution profile
- **Says:** quality non-positive at γ = 0.5–1.5.
- **Means:** the gate failure is robust to resolution choice, not an artifact of γ=1.
- **Do NOT claim:** a better resolution exists in the tested range.

## Appendix B — Reproducibility
- **Says:** coverage, tests, hashes, determinism, manifests.
- **Means:** answers "how do you know the pipeline is trustworthy?"
- **Do NOT claim:** this validates the science — it validates the software.

## Appendix C — Gates
- **Says:** the five gates and their descriptive-only fallback.
- **Means:** shows unsupported claims were structurally prevented, not merely avoided.
- **Do NOT claim:** gates prove the negative — they enforce honesty about it.
