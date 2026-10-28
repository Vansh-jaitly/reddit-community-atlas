# 🕸️ Network Analysis Engine — Plain English Guide

This folder contains the core network science algorithms used to analyze community structures and cross-community brokers on Reddit.

---

## 1. What Each Module Does (In Simple Terms)

### 📄 `bipartite.py` (Connecting Users & Subreddits)
- Creates a 2-sided graph connecting **users** on one side to **subreddits** on the other side.
- Edges indicate that a user posted at least one comment in that subreddit during the quarter.

### 📄 `projection.py` (Subreddit-to-Subreddit Connections)
- Converts the 2-sided user-subreddit graph into a 1-sided **subreddit-to-subreddit network**.
- Two subreddits are connected if users comment in both of them.
- **Why Cosine Similarity on Presence?**  
  Raw comment counts favor huge subreddits (like `gaming` or `politics`). Cosine similarity evaluates the *percentage of user overlap*, ensuring small niche subreddits are evaluated fairly.

### 📄 `backbone.py` (Cutting Out Network Noise)
- Implements the **Serrano Disparity Filter**.
- Without filtering, nearly every subreddit connects to every other subreddit, creating an unreadable "hairball".
- The disparity filter prunes weak, random connections while preserving the essential structural backbone of the network.

### 📄 `community.py` (Grouping Related Subreddits)
- Runs the **Leiden Algorithm** to discover clusters of subreddits that naturally group together (e.g. finance subreddits, gaming subreddits, support groups).
- Sweeps resolution parameters across multiple random seeds to find the cleanest, highest-quality communities.

### 📄 `brokerage.py` (Finding Cross-Community Brokers)
- Calculates the **Participation Coefficient ($P$)** for each active user.
- **How $P$ works**:
  - A user active in 10 subreddits that are all in the *same* community gets a low $P$ score.
  - A user active in 2 subreddits belonging to 2 *different* communities gets a high $P$ score.
- Flags the top 1% of users with the highest $P$ scores as active **brokers**.

### 📄 `anchored_matching.py` (Tracking Communities Over Time)
- Matches community IDs in each quarter to a single global "anchor" reference partition.
- Prevents errors in earlier quarters from messing up later quarters (Anchored Matching vs. Chained Matching).

### 📄 `stability_analysis.py` (Testing the Core Hypothesis)
- Measures **Position Stability**: Do the same pairs of communities stay connected across quarters?
- Measures **Person Stability**: Do the exact same users occupy those bridge positions across quarters?
- Compares the two scores to test **Hypothesis H1** (Position Stability > Person Stability).
- Runs **degree-preserving null models** ($\ge 200$ random permutations) to prove the results are statistically significant and not random chance.

### 📄 `run_network_pipeline.py` (The Main Runner)
- Executes all the steps above in sequence across all available quarters.
- Saves results to `data/logs/network_results.json`.

---

## 2. How to Run

Run the complete network analysis engine from your terminal:

```bash
python network_analysis/run_network_pipeline.py
```

To run on a specific quarter:
```bash
python network_analysis/run_network_pipeline.py --quarter 2018Q1
```

