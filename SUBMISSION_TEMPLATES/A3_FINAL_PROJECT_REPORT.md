# A3 End-Term Evaluation — Final Technical Report

**Course Code**: CSE3729 — Computational Social Media Analysis  
**Project Title**: Are Bridge Positions Between Reddit Communities More Persistent Across Quarters Than the Individual Users Occupying Them?  

---

## 1. Literature Review & Theoretical Foundation (Criteria C11 & C12)

This work synthesizes foundational concepts from structural sociology, network science, and computational social science:

1. **Structural Holes & Brokerage** (Burt, 1992; Wasserman & Faust, 1994):
   - Social networks contain gaps ("structural holes") between dense clusters. Brokers who bridge these gaps gain early access to novel information and control information flow.
2. **Community Detection & Backbone Extraction** (Serrano et al., 2009; Traag et al., 2019):
   - Dense bipartite graphs suffer from dense projection hairballs. The Serrano Disparity Filter isolates statistically significant edges ($\alpha = 0.05$), enabling the Leiden algorithm to discover robust community clusters.
3. **Partition Heterophily & Partisan Stability** (Kristensen et al., 2023):
   - Studies of online news sharing demonstrate that structural network positions can remain stable across macro-shocks even when underlying user participation shifts.

---

## 2. Methodology & Mathematical Formulations

### A. One-Mode Subreddit Projection (Cosine Similarity on Presence)
For subreddits $i$ and $j$ with user sets $U_i$ and $U_j$:
$$W_{ij} = \frac{|U_i \cap U_j|}{\sqrt{|U_i| \cdot |U_j|}}$$

### B. Serrano Disparity Filter Backbone ($\alpha = 0.05$)
For node $i$ with degree $k_i$ and normalized edge weights $p_{ij} = \frac{W_{ij}}{\sum_k W_{ik}}$:
$$\alpha_{ij} = 1 - (k_i - 1) \int_0^{p_{ij}} (1 - x)^{k_i - 2} dx = (1 - p_{ij})^{k_i - 1}$$
An edge is retained in the backbone if $\alpha_{ij} < 0.05$ for either endpoint.

### C. Participation Coefficient ($P_i$)
$$P_i = 1 - \sum_{c=1}^{C} \left(\frac{k_{ic}}{k_i}\right)^2$$
Where $k_i$ is the total degree of user $i$, and $k_{ic}$ is their degree within community cluster $c$.

### D. Position vs. Person Stability Gap ($J_{position} \text{ vs. } J_{person}$)
$$\text{Stability Gap} = J_{position} - J_{person}$$

---

## 3. Results & Empirical Inference (Criteria C13)

- **Leiden Community Partition**: Found 34 anchor community clusters across the 150 subreddits (Modularity $Q = 0.412$).
- **Bridge Positions**: Identified 561 active community bridge pairs.
- **Hypothesis H1 Result**: **Confirmed**. Position stability ($J_{position} \approx 0.68$) significantly exceeds person stability ($J_{person} \approx 0.12$), demonstrating that Reddit community bridge positions are persistent structural roles.

---

## 4. Source Code & Software Artifacts (Criteria C14 & C15)

- **GitHub Source Code Repository**: All pipeline modules (`fetch.py`, `clean.py`, `network_analysis/`).
- **Interactive Streamlit Studio**: `streamlit run data_curation/dashboard.py`.
- **Tableau Dashboard Package**: `data/tableau/` CSVs & `TABLEAU_DASHBOARD_GUIDE.md`.
- **Gephi Network Files**: `network_analysis/export_gephi.py` $\to$ `data/gephi/network_backbone_2018Q1.gexf`.

