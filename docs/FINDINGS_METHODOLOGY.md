# Findings: methodology note

How the Findings stories are computed, which established methods were adopted, which were rejected and why, and what
the numbers can and cannot support. Thresholds are the ones in `findings/config.py`; every procedure below is the one
the code runs. The literature survey behind the choices was done with independent research agents whose references
were each checked against the source before being kept; only verified references appear here.

## 1 Data and its limits

The Atlas store holds 210.3 M comments by 2.45 M pseudonymous commenters in 170 subreddits (Oct 2017 – Sep 2018) with
only a salted author hash, subreddit, UTC timestamp and moderator flag per comment. The Findings store
(`data_curation/fetch_text.py`, same salt, same Arctic Shift shards via DuckDB) adds comment text, `parent_id`, score and
flair for 11 subreddits (two Marvel, five crypto, three debate communities and r/thewallstreet; 10.5 M comments with text, 9.8 M once deleted bodies are dropped) and reply structure
without text for 11 more plus r/movies in Mar–Jun 2018. A daily Bitcoin price series (Blockchain.com, cross-checked
against Coin Metrics; peak 16–17 Dec 2017 depending on source) is context only.

Limits carried into every story: counts are lower bounds (Pushshift-derived archives have gaps, Gaffney & Matias 2018;
≈ 7.5 % of bodies are deleted or removed); comments whose author is `[deleted]` keep their place in threads but form no
edge; AutoModerator is dropped; a "newcomer" is a user not active in that subreddit during a fixed lookback before the period (`config.NEWCOMER_LOOKBACK`: five months for the Infinity War windows, two for the Bitcoin months, the longest the store allows for the earliest compared period), so periods are compared on the same footing; a period whose lookback would reach before October 2017 has no newcomer share, and a user absent for the whole lookback counts as new on return
(Horta Ribeiro et al. 2021); 170 subreddits are a sample and Reddit is not the public. Only aggregates, agreement
statistics and anonymised network cores (`u1…`) are published; text, hashes and the labelled sample stay local.

## 2 Reply networks and community detection

**Edges are interactions present in the data.** A comment by A whose `parent_id` is `t1_<a comment by B>` gives the
directed edge A → B, weighted by the number of such replies (Buntain & Golbeck 2014; Medvedev et al. 2019). Replies to
posts (`t3_` parents, whose author is not in the comment store) and self-replies form no edge; a user enters a network
with at least two reply interactions. Communities and centralities use the undirected weighted simplification; direction
is kept for reciprocity. The focused community was chosen from a 14-candidate selection matrix computed over one quarter with the same graph
construction and Leiden procedure (30 seeds for every candidate); for speed the matrix ranks centralities with unweighted
betweenness and a 6-hop cutoff above 15,000 users, counts brokers only within the top 5 % of betweenness, and takes the
modularity excess as unweighted Q minus the rewired baseline (`docs/FINDINGS_COMMUNITY_SELECTION.md`).

**Communities.** Leiden with the modularity objective at resolution 1.0, run to convergence from 30 seeds (Traag,
Waltman & van Eck 2019; 10 seeds above 6,000 users, 3 above 50,000, and 5 for the Bitcoin months that are not key
months); the best-modularity partition is shown together with the mean adjusted Rand index and adjusted mutual
information against the other runs (Good, de Montjoye & Clauset 2010 on the degeneracy of modularity). Because
modularity finds structure in random graphs and has a resolution limit (Fortunato & Hric 2016; Peixoto 2023), the same
procedure runs on degree-preserving rewirings of each graph (Maslov & Sneppen 2002; 20 for the focused community's year network and 5 for its quarterly networks, 5 for
event windows up to 6,000 users and 2 above that or for context communities, because Leiden run to convergence on a
rewired 100,000-user graph takes many minutes) and Q is always printed beside the rewired baseline. For the focused community two further checks are
published: an Infomap partition (map equation, Rosvall & Bergstrom 2008; AMI against Leiden and its number of modules)
and a resolution scan (γ ∈ {0.5, 1, 1.5, 2}) so the reader can see whether the chosen partition sits on a plateau.
Louvain was not used (it can emit disconnected communities); stochastic block models were not run (no `graph-tool` in the
environment) and are named as the inferential alternative.

**Readable core.** The drawn network is the smallest k-core (Seidman 1983) with at most 150 nodes (floor 30), largest
component kept; k and the shares of nodes, ties and replies it covers are printed under every drawing. Every summary
statistic and every broker table is computed on the full graph; metrics shown on the core's nodes are recomputed on the core
against the same full-network clusters (one partition for the drawing, the tables and the insights) and labelled as such. Positions come from a seeded Fruchterman–Reingold layout and are illustration, not measurement.

## 3 Brokerage and bridges

Per node, on the full graph: betweenness with reply counts as proximities (distance = 1/replies; Brandes 2001), Freeman-
normalised; Everett & Valente (2016) EV-brokerage (betweenness per tie) beside it, because betweenness scales with degree
in tree-like reply graphs (Barthélemy 2004); the Guimerà & Amaral (2005) participation coefficient over the Leiden
communities; degree and strength; and Burt constraint only as a descriptive ego-level overlay (its bounds depend on degree,
Everett & Borgatti 2020). Graphs above 6,000 users skip closeness and eigenvector centrality and estimate betweenness from 2,000 random source nodes (pivot sampling, rescaled to the full graph); the biggest graphs (above 50,000 users) run Leiden from 3 seeds instead of 30.

A **broker** is a node with participation ≥ 0.6 that exchanges replies with ≥ 3 communities; the five highest by
betweenness are listed per window. For the focused community, every r/marvelstudios window and the key months of r/bitcoin and r/cryptocurrency, each
listed broker's betweenness is tested against degree-preserving rewirings of the same graph (100 for the
focused community, 50 for event windows) and carries a z-score and an empirical p-value when the graph has at most 3,000
users; above that, which is every network on which a broker card is judged (the focused community's quarterly networks list their brokers descriptively, without a significance column), a full betweenness pass per rewiring is not affordable and the test
is replaced by the broker's percentile among users of similar degree (±25 %, or the 30 nearest in degree when fewer
than ten), labelled as such in the tables. Gould–Fernandez brokerage roles
were not computed (they presuppose exogenous groups for every node) and are named as the extension.

## 4 Sentiment on Reddit text

**Default.** VADER (Hutto & Gilbert 2014; `vaderSentiment` 3.3.2): compound ≥ 0.05 positive, ≤ −0.05 negative, the
authors' thresholds fixed before any validation. Bodies are cleaned of links, quoted lines and markdown; deleted bodies are
unscored; empty text is neutral. The alternative the review recommends, the Twitter-trained RoBERTa classifier (Barbieri
et al. 2020), is not run as the default: CPU inference over 10.5 M comments is not feasible here, and the one peer-reviewed
Reddit comparison found no advantage over VADER (accuracy 0.66 vs 0.69 on 200 posts, Sharma & Sirts 2024).

**Topic words.** The VADER lexicon scores plot and market vocabulary as sentiment (*kill* −3.7, *dead* −3.3, *war* −2.9,
*villain* −2.6, *crash* −1.7, *dump* −1.6; vaderSentiment lexicon). For the two event stories the primary score is
therefore a **domain-neutralised VADER**: the listed topic words (`config.DOMAIN_NEUTRAL`, chosen before results and
printed with each story) are removed from the lexicon, so a sentence is scored on its remaining words. The standard score
is computed for every comment as well and shown beside the neutralised one in the Infinity War window table and in every comparison table of both event stories (the Bitcoin phase and month tables carry the neutralised score only); the
focused community uses standard VADER.

**What is aggregated.** VADER's compound is not an interval scale (Ribeiro et al. 2016), so the primary aggregate is the
share of negative (and positive) comments with a bootstrap 95 % CI; the mean compound and the mean of per-user means are
reported beside it because comments by the same user are not independent. Windows are compared on the negative share with
Cohen's h, a 500-resample bootstrap CI and a two-sided permutation p-value (1,000 relabellings; 300 for the strict-threshold and standard-VADER sensitivity columns), and on the mean compound
with Cohen's d; an insight about tone requires the two to agree in direction.

**Validation** (`findings/validation.py`). A stratified sample — three subreddit groups (Marvel, crypto, debate) × three
months (Dec 2017, Apr 2018, Aug 2018) × three VADER labels × 12 comments of ≥ 15 characters, up to 324 — is exported
without VADER's label visible. Labels follow Mohammad's (2016) instruction to judge the language, not the writer's view of
the topic. The protocol calls for two team members to label independently with Cohen's κ reported against the .67/.80
conventions (Artstein & Poesio 2008) and disagreements adjudicated; the labels shipped with this build were produced by
three independent language-model annotators with majority vote, and are disclosed as such — they stand in for, and should
be replaced by, the team's own labels before submission. VADER is then scored against the labels (accuracy, macro-F1, κ,
confusion matrix); the gold set never tunes thresholds (van Atteveldt et al. 2021).

**Measured agreement (this build).** On the 324-comment sample, three independent language-model annotators agreed with
each other almost perfectly (Fleiss' κ 0.92; 306 of 324 rows unanimous) and called 70 % of this VADER-balanced sample
neutral. VADER's ±0.05 label matched their majority label for 47.8 % of comments (macro-F1 0.44, Cohen's κ 0.22; positive
vs negative alone 67 % on 86 comments; by group: Marvel 48 %, crypto 51 %, debate 44 %). The confusion matrix shows the
error is one-directional: of 227 comments the annotators called neutral, VADER labelled 65 positive and 65 negative. At a
stricter ±0.3 threshold agreement rises to 56.8 % (κ 0.25). Consequences adopted: absolute positive/negative shares are
reported as VADER shares, not as the share of opinionated comments; every event claim rests on *changes* in shares between
windows (a constant over-labelling moves little between windows), requires the mean compound to agree in direction, and
is shown beside the strict-threshold version and the standard-lexicon version; the κ of 0.22 is quoted in the app and in
every story's limitations. The labels are a disclosed stand-in for the team's own double coding (see §4 above).

**Failure modes stated in the stories:** a three-token negation window; no sarcasm handling (untagged sarcasm is roughly
ten times the 0.25 % tagged `/s`; Khodak et al. 2018); slang that flips polarity (*sick*, *insane*); short comments that hit
no lexicon word score exactly 0, so most crypto comments are neutral (Narman & Damir Uulu 2020) and polar shares rest on
a minority; individual accuracy does not guarantee unbiased proportions (Hopkins & King 2010).

## 5 Polarization: three concepts and the operational definitions adopted

*Sentiment polarity* is a property of text and is reported as **tone**, never as polarization: the same stance is voiced
in positive or negative language (Mohammad, Sobhani & Kiritchenko 2017).

*Stance or disagreement* gets no classifier: even humans fully agree on only a third of Reddit reply pairs (Pougue-Biyong
et al. 2021). The only position data are self-declared flairs in the debate communities, mapped by published, ordered
keyword rules to camps (left / right / centre; red / blue / purple / black), each user taking the camp of their most
frequent recognised flair; coverage is printed wherever camps are used.

*Affective polarization* is animosity between identity groups (Iyengar et al. 2019), measured online as the cross- versus
within-group gap in reply tone (Marchal 2022; De Francisci Morales et al. 2021). Adopted definitions: **segregation** =
Krackhardt & Stern (1988) E–I index of reply weights over camps, with its value under degree-preserving rewirings (z-score
and two-sided p; 100 rewirings, at most 30 on graphs above 200,000 ties), because raw structural polarization scores are high on random graphs of the same degree sequence
(Salloum, Chen & Kivelä 2022); **cross-camp tone** = mean compound of cross-camp minus within-camp replies, tested by
1,000 label permutations (≥ 30 replies per side), worded as a proxy for affective polarization between self-declared camps.
No community is called "polarized" as a whole; the event stories, which have no camps, report tone only; a tone gap between
Leiden clusters is clustering of tone, not disagreement.

## 6 Event windows and temporal comparison (no causal claims)

Windows are fixed before any result exists (Bernal, Cummins & Gasparrini 2017): the Infinity War windows in `config.py`,
the Bitcoin surge baseline (1 Oct – 15 Nov 2017) and its five key months in `findings/stories.py`. **Infinity War:** anchor
27 Apr 2018 (US release); *before* 2 Mar – 19 Apr, *release* 20 Apr – 10 May, *after* 11 May – 28 Jun — 7, 3 and 7 whole
weeks, so weekday composition is matched. The before window is the baseline (Lin et al. 2014). Volume is read three ways:
daily comments indexed to the before-window median (robust z-scores from the MAD); the level change at the release from a
segmented regression of log daily comments with day-of-week terms and a slope change (Bernal et al. 2017; the level shift's t statistic uses Newey–West standard errors with a Bartlett kernel because daily residuals are autocorrelated, and the residual lag-1 autocorrelation is published beside it), with the same
model run on all 170 communities so the lead community's coefficient is reported as a percentile of that distribution
(Chandrasekharan et al. 2020); and the daily total over the other 168 communities (the two story communities excluded) screened for archive gaps (days below
half the median are listed). Frame-wide figures (the 170-community bar chart and the regression percentile) come from the Atlas store, which keeps accounts with at least five comments in a quarter and drops `[deleted]` authors, so its counts run about 9 % below the text store's for r/marvelstudios; the page and the narrative say which store each number comes from. Change points (binary segmentation, BIC-style penalty, segments ≥ 7 days, ≤ 3 points; Truong,
Oudre & Vayatis 2020) are descriptive.

**Crypto decline:** phases come from the price series through a zigzag filter (extrema confirmed by ≥ 40 % counter-moves; the last turning point before the window ends is provisional when its
counter-move has not reached that threshold, and the page labels it so),
not from typed-in dates; months are the unit of network comparison; consecutive phases are compared as in §4 (a turning-point day closes the phase it ends, so no day is counted twice); the volume-surge and tone-shift detectors run on all five crypto communities and the structure detectors on the two with monthly networks (r/bitcoin, r/cryptocurrency). Price and
discussion are aligned by UTC day and related by Spearman ρ at lags −7 … +7 between daily log returns and daily mean tone
or the change in log comments — differenced series, since level correlations of trending series are spurious (Dean &
Dunsmuir 2016); the full lag table is published and the largest |ρ| is quoted descriptively, never as prediction or cause
(Shojaie & Fox 2021); both series are daily and aligned by UTC day, so a lag of ± 1 day lies within the alignment uncertainty
and the sign of a one-day lag is not read as a direction.

Network summaries per window or month are descriptive: density and modularity depend on size (Tantardini et al. 2019).
Quarterly cluster persistence in the focused community is the adjusted Rand index over users present in both quarters.

## 7 Insight generation rules

Insights are rule-based facts in the DataShot / QuickInsights sense (Wang et al. 2020; Ding et al. 2019): eight detectors
emit a record with the observed value, the evidence that fired it, the period and scope, why it matters, an interpretation,
a confidence tier, limitations and a link to the view showing the data (Hullman & Diakopoulos 2011).

| Detector | Fires when | Confidence |
|---|---|---|
| Volume surge | a day ≥ 3 robust SD (MAD) above the baseline median | high if ≥ 3 such days |
| Sentiment shift | negative-share Cohen's h ≥ 0.10, permutation p ≤ 0.001, CI excludes 0, mean compound agrees in direction | high if per-user p ≤ 0.01 |
| Cluster tone gap | ≥ 8 scored members per cluster, gap ≥ 0.10, p ≤ 0.01 | high if p ≤ 0.001 |
| Broker | on the full network: top betweenness (≥ 20 users), participation ≥ 0.6, ≥ 3 clusters; rewiring z and p (≤ 3,000 users) or degree-matched percentile | high if ≥ 2× the runner-up over all users (the card names it; the Brokers table lists only users meeting the rule) |
| Cross-camp tone | ≥ 100 replies per side, gap ≥ 0.05, p ≤ 0.001 | high |
| Camp mixing | E–I index of camp-flaired replies against 100 degree-preserving rewirings, \|z\| ≥ 3 (two-sided p, floored at 1/101) | high if \|z\| ≥ 5 and p ≤ 0.01 |
| Sealed cluster | ≥ 10 members, E–I ≤ −0.6 | descriptive |
| Structure change | Δ largest component ≥ 0.15 or Δ modularity ≥ 0.10 between consecutive windows | descriptive |

Within each story every detector's permutation p-value enters a Benjamini–Hochberg correction over the number of
candidate patterns actually tested, including the tests whose pattern did not pass its own threshold; the q-value and
that count are stored on the record, an insight with q > 0.01 drops to
medium confidence and one with q > 0.05 is removed (the multiple-comparisons problem in visual analysis, Zgraggen et al.
2018). Sentences are templates filled with computed values; no language model writes, paraphrases or ranks any insight
(Thomson & Reiter 2020). Stories follow an author-driven stem — question, context, observation, visualization,
explanation, conclusion, limitations — that hands off to free exploration (Segel & Heer 2010).

## 8 What we will not claim

- **Causation:** no event and no price move *caused* anything; every comparison is a temporal association.
- **Opinion:** tone is not approval, stance or disagreement; negative language is not polarization; the affective-
  polarization proxy applies only to self-declared camps inside one debate community.
- **Influence or identity:** brokers are structural positions (Stovel & Shaw 2012); ids are `u1…`; identity and intent are
  not sought and must not be.
- **Truth of clusters:** one partition with published seed agreement, rewired baseline and cross-checks; the drawing is not
  evidence.
- **Representativeness or completeness:** 11 or 170 subreddits are not Reddit; sarcasm is unquantified; networks of
  different sizes are not directly comparable.
- **Borrowed accuracy:** the agreement measured on our own sample, never VADER's 0.96 F1 on tweets.

## References

- Artstein, R., & Poesio, M. (2008). Inter-coder agreement for computational linguistics. *Computational Linguistics* 34(4). https://aclanthology.org/J08-4004/
- Barbieri, F., Camacho-Collados, J., Espinosa Anke, L., & Neves, L. (2020). TweetEval: Unified benchmark and comparative evaluation for tweet classification. *Findings of EMNLP 2020*. https://aclanthology.org/2020.findings-emnlp.148/
- Barthélemy, M. (2004). Betweenness centrality in large complex networks. *European Physical Journal B* 38. https://arxiv.org/abs/cond-mat/0309436
- Bernal, J. L., Cummins, S., & Gasparrini, A. (2017). Interrupted time series regression for the evaluation of public health interventions: a tutorial. *International Journal of Epidemiology* 46(1). https://academic.oup.com/ije/article/46/1/348/2622842
- Brandes, U. (2001). A faster algorithm for betweenness centrality. *Journal of Mathematical Sociology* 25(2). https://doi.org/10.1080/0022250X.2001.9990249
- Buntain, C., & Golbeck, J. (2014). Identifying social roles in reddit using network structure. *WWW '14 Companion*. https://archives.iw3c2.org/www2014/proceedings/companion/p615.pdf
- Chandrasekharan, E., Jhaver, S., Bruckman, A., & Gilbert, E. (2020). Quarantined! Examining the effects of a community-wide moderation intervention on Reddit. arXiv:2009.11483. https://arxiv.org/abs/2009.11483
- Dean, R. T., & Dunsmuir, W. T. M. (2016). Dangers and uses of cross-correlation in analyzing time series in perception, performance, movement, and neuroscience. *Behavior Research Methods* 48(2). https://researchers.westernsydney.edu.au/en/publications/dangers-and-uses-of-cross-correlation-in-analyzing-time-series-in/
- De Francisci Morales, G., Monti, C., & Starnini, M. (2021). No echo in the chambers of political interactions on Reddit. *Scientific Reports* 11, 2818. https://www.nature.com/articles/s41598-021-81531-x
- Ding, R., Han, S., Xu, Y., Zhang, H., & Zhang, D. (2019). QuickInsights: Quick and automatic discovery of insights from multi-dimensional data. *SIGMOD 2019*. https://www.microsoft.com/en-us/research/uploads/prod/2019/05/QuickInsights-camera-ready-final.pdf
- Everett, M. G., & Borgatti, S. P. (2020). Unpacking Burt's constraint measure. *Social Networks* 62. https://doi.org/10.1016/j.socnet.2020.02.001
- Everett, M. G., & Valente, T. W. (2016). Bridging, brokerage and betweenness. *Social Networks* 44. https://doi.org/10.1016/j.socnet.2015.09.001
- Fortunato, S., & Hric, D. (2016). Community detection in networks: A user guide. *Physics Reports* 659. https://arxiv.org/abs/1608.00163
- Freeman, L. C. (1977). A set of measures of centrality based on betweenness. *Sociometry* 40(1). https://doi.org/10.2307/3033543
- Gaffney, D., & Matias, J. N. (2018). Caveat emptor, computational social science: Large-scale missing data in a widely-published Reddit corpus. *PLoS ONE* 13(7). https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0200162
- Good, B. H., de Montjoye, Y.-A., & Clauset, A. (2010). Performance of modularity maximization in practical contexts. *Physical Review E* 81, 046106. https://doi.org/10.1103/PhysRevE.81.046106
- Guimerà, R., & Amaral, L. A. N. (2005). Functional cartography of complex metabolic networks. *Nature* 433. https://doi.org/10.1038/nature03288
- Hopkins, D. J., & King, G. (2010). A method of automated nonparametric content analysis for social science. *American Journal of Political Science* 54(1). https://gking.harvard.edu/files/words.pdf
- Horta Ribeiro, M., Jhaver, S., Zannettou, S., Blackburn, J., Stringhini, G., De Cristofaro, E., & West, R. (2021). Do platform migrations compromise content moderation? Evidence from r/The_Donald and r/Incels. *PACM HCI* 5 (CSCW2). https://arxiv.org/abs/2010.10397
- Hullman, J., & Diakopoulos, N. (2011). Visualization rhetoric: Framing effects in narrative visualization. *IEEE TVCG* 17(12). https://mucollective.northwestern.edu/files/2011-VisRhetoric-InfoVis.pdf
- Hutto, C. J., & Gilbert, E. (2014). VADER: A parsimonious rule-based model for sentiment analysis of social media text. *ICWSM-14*. https://doi.org/10.1609/icwsm.v8i1.14550
- Hutto, C. J. vaderSentiment repository (vaderSentiment.py, vader_lexicon.txt). https://github.com/cjhutto/vaderSentiment
- Iyengar, S., Lelkes, Y., Levendusky, M., Malhotra, N., & Westwood, S. J. (2019). The origins and consequences of affective polarization in the United States. *Annual Review of Political Science* 22. https://doi.org/10.1146/annurev-polisci-051117-073034
- Khodak, M., Saunshi, N., & Vodrahalli, K. (2018). A large self-annotated corpus for sarcasm. *LREC 2018*. https://aclanthology.org/L18-1102/
- Krackhardt, D., & Stern, R. N. (1988). Informal networks and organizational crises: An experimental simulation. *Social Psychology Quarterly* 51(2). https://doi.org/10.2307/2786835
- Lin, Y.-R., Keegan, B., Margolin, D., & Lazer, D. (2014). Rising tides or rising stars? Dynamics of shared attention on Twitter during media events. *PLoS ONE* 9(5). https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0094093
- Marchal, N. (2022). "Be nice or leave me alone": An intergroup perspective on affective polarization in online political discussions. *Communication Research* 49(3). https://doi.org/10.1177/00936502211042516
- Maslov, S., & Sneppen, K. (2002). Specificity and stability in topology of protein networks. *Science* 296. https://arxiv.org/abs/cond-mat/0205380
- Medvedev, A. N., Lambiotte, R., & Delvenne, J.-C. (2019). The anatomy of Reddit: An overview of academic research. *Dynamics On and Of Complex Networks III*. https://arxiv.org/abs/1810.10881
- Mohammad, S. M. (2016). A practical guide to sentiment annotation: Challenges and solutions. *WASSA 2016*. https://aclanthology.org/W16-0429/
- Mohammad, S. M., Sobhani, P., & Kiritchenko, S. (2017). Stance and sentiment in tweets. *ACM Transactions on Internet Technology* 17(3). https://arxiv.org/abs/1605.01655
- Narman, H. S., & Damir Uulu, A. (2020). Impacts of positive and negative comments of social media users to cryptocurrency. ICNC 2020 (author PDF). https://hsnarman.github.io/CONF/20-ICNC-TopComment.pdf
- Peixoto, T. P. (2023). Descriptive vs. inferential community detection in networks: Pitfalls, myths, and half-truths. Cambridge University Press (Elements). https://arxiv.org/abs/2112.00183
- Pougue-Biyong, J., Semenova, V., Matton, A., Han, R., Kim, A., Lambiotte, R., & Farmer, D. (2021). DEBAGREEMENT: A comment-reply dataset for (dis)agreement detection in online debates. *NeurIPS 2021 Datasets and Benchmarks*. https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/file/6f3ef77ac0e3619e98159e9b6febf557-Paper-round2.pdf
- Ribeiro, F. N., Araújo, M., Gonçalves, P., Gonçalves, M. A., & Benevenuto, F. (2016). SentiBench: a benchmark comparison of state-of-the-practice sentiment analysis methods. *EPJ Data Science* 5, 23. https://arxiv.org/abs/1512.01818
- Rosvall, M., & Bergstrom, C. T. (2008). Maps of random walks on complex networks reveal community structure. *PNAS* 105(4). https://doi.org/10.1073/pnas.0706851105
- Salloum, A., Chen, T. H. Y., & Kivelä, M. (2022). Separating polarization from noise: Comparison and normalization of structural polarization measures. *PACM HCI* 6 (CSCW1). https://arxiv.org/abs/2101.07009
- Segel, E., & Heer, J. (2010). Narrative visualization: Telling stories with data. *IEEE TVCG* 16(6). https://idl.uw.edu/papers/narrative
- Seidman, S. B. (1983). Network structure and minimum degree. *Social Networks* 5(3). https://doi.org/10.1016/0378-8733(83)90028-X
- Sharma, N., & Sirts, K. (2024). Context is important in depressive language: A study of the interaction between the sentiments and linguistic markers in Reddit discussions. *WASSA 2024*. https://aclanthology.org/2024.wassa-1.28/
- Shojaie, A., & Fox, E. B. (2021). Granger causality: A review and recent advances. arXiv:2105.02675. https://arxiv.org/abs/2105.02675
- Stovel, K., & Shaw, L. (2012). Brokerage. *Annual Review of Sociology* 38. https://doi.org/10.1146/annurev-soc-081309-150054
- Tantardini, M., Ieva, F., Tajoli, L., & Piccardi, C. (2019). Comparing methods for comparing networks. *Scientific Reports* 9, 17557. https://doi.org/10.1038/s41598-019-53708-y
- Thomson, C., & Reiter, E. (2020). A gold standard methodology for evaluating accuracy in data-to-text systems. *INLG 2020*. https://aclanthology.org/2020.inlg-1.22/
- Traag, V. A., Waltman, L., & van Eck, N. J. (2019). From Louvain to Leiden: Guaranteeing well-connected communities. *Scientific Reports* 9, 5233. https://arxiv.org/abs/1810.08473
- Truong, C., Oudre, L., & Vayatis, N. (2020). Selective review of offline change point detection methods. *Signal Processing* 167. https://arxiv.org/abs/1801.00718
- van Atteveldt, W., van der Velden, M. A. C. G., & Boukes, M. (2021). The validity of sentiment analysis: Comparing manual annotation, crowd-coding, dictionary approaches, and machine learning algorithms. *Communication Methods and Measures* 15(2). https://doi.org/10.1080/19312458.2020.1869198
- Wang, Y., Sun, Z., Zhang, H., Cui, W., Xu, K., Ma, X., & Zhang, D. (2020). DataShot: Automatic generation of fact sheets from tabular data. *IEEE TVCG* 26(1). https://microsoft.com/en-us/research/uploads/prod/2019/08/VIS2019_DataShot.pdf
- Zgraggen, E., Zhao, Z., Zeleznik, R., & Kraska, T. (2018). Investigating the effect of the multiple comparisons problem in visual analysis. *CHI 2018*. https://dspace.mit.edu/handle/1721.1/137892
