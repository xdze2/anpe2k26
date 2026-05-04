# Active Ranking and Optimal Information Gathering

A synthesis of methods for ranking candidates efficiently when each comparison or measurement is costly.

---

## Problem framing

The general setting: a set of N candidates, each with a latent "quality" or "relevance" score. We cannot observe scores directly — we can only make costly comparisons (matches, user feedback, API calls). The goal is to recover a useful ranking (full order, or top-K) with as few queries as possible.

This sits at the intersection of three fields:

- **Active learning** — choose the most informative query next
- **Bayesian optimal experiment design** — formalize "informative" via information theory
- **Curiosity-driven exploration** (robotics) — intrinsic motivation to reduce model uncertainty

---

## Core metric: information gain

All methods below ultimately optimize some version of:

```
Score(query) = Information_Gain(query) / Cost(query)
```

where information gain is typically **entropy reduction** in the model's posterior:

```
IG(x) = H(model) − E[H(model | observe x)]
```

Pick the query that shrinks your uncertainty the most per unit cost.

---

## Pair selection strategies

### Random pairing
Draw pairs uniformly at random. Simple baseline. Requires **O(N²)** matches for full ranking, **O(N log N)** for top-K (but with a large constant).

### Adaptive pairing (closest ratings)
After each match, sort candidates by current score and pair adjacent neighbors — i.e. the pair whose outcome is most uncertain (closest to 50/50 expected result). This is the **ELO nearest-neighbor** heuristic.

- Gain: ~3–5× fewer matches than random for the same rank accuracy
- Complexity: **O(N log N)** matches
- Connection: equivalent to Swiss tournament pairing in chess

### Boundary-focused pairing (top-K)
When only the top-K matters, focus all matches within a **contested zone** around the Kth-rank threshold. Nodes far above or below the boundary are settled; ignore them.

- Pool = nodes within window W of the current Kth-highest score
- Gain: further reduction over adaptive pairing when K << N
- Complexity: roughly **O(K log K + K)** once the boundary is located

### BALD — Bayesian Active Learning by Disagreement
Each candidate has a score **distribution** (mean + variance) rather than a point estimate. Pick the pair where the two distributions overlap most — maximum mutual information between the match outcome and the model parameters.

```
Score(a, b) = MI(winner; model_params) = H(winner) − E[H(winner | params)]
```

Theoretically optimal but requires a Bayesian model (e.g. Gaussian Process or Bayesian NN) and is more expensive to compute.

### Thompson Sampling
Maintain a posterior distribution over scores. At each step:
1. Sample one set of scores from the posterior
2. Pick the match that looks most informative under that sample

Naturally balances exploration (uncertain nodes) and exploitation (settled ranking). No explicit entropy calculation needed.

---

## Preference elicitation (user feedback)

When the "match" is a user comparison (e.g. "do you prefer A or B?"), the same framework applies but with two additional considerations:

**Cost has two components**: API/fetch cost and user cognitive load. Pairwise comparisons are more sample-efficient than rating or ranking tasks.

**Pair selection rule**: ask about pairs that **disambiguate competing preference hypotheses**. If the model is uncertain whether the user weights price vs. eco-score, show two products that differ strongly on exactly those dimensions.

```
Score(pair_i_j) = MI(user_choice; preference_params) / user_effort_cost
```

**Expected Value of Information (EVOI)** is the formal Bayesian criterion: select the query that maximizes expected posterior decision quality (recommendation accuracy) over all possible user responses.

---

## Cost-aware query selection

When two types of queries exist (e.g. fetch product info vs. ask user), normalize scores and pick the best across types:

```
best_action = argmax over all query types [IG(query) / Cost(query)]
```

Decision heuristics:

| Situation | Preferred action |
|---|---|
| Many candidates with incomplete descriptions | Fetch product info first |
| High posterior entropy over preferences | Ask user feedback |
| Products well-described, model can't rank them | Ask user feedback |
| Very limited budget | Pairwise comparisons on top-K only |

---

## Measuring convergence

Rather than tracking raw scores (arbitrary scale), measure **ranking accuracy** directly:

- **Misclassified nodes**: number of candidates on the wrong side of the top-K boundary. Goes from K (worst) to 0 (perfect).
- **Mean absolute rank error**: average |predicted rank − true rank| across all candidates.
- **Kendall's tau**: rank correlation to the ground truth, from 0 to 1.

Averaging over multiple random seeds and plotting mean ± percentile bands reveals both convergence speed and variance across runs.

---

## Complexity summary

| Method | Matches to rank N | Matches for top-K |
|---|---|---|
| Exhaustive | O(N²) | O(N·K) |
| Random pairing | O(N² / log N) typical | O(N log N) |
| Adaptive (closest) | O(N log N) | O(N log N), smaller constant |
| Boundary-focused | — | O(K log K + N) to locate boundary |
| BALD / Thompson | O(N log N) | O(K log K + N) |

---

## Key references (from source conversation)

- **BALD**: Bayesian Active Learning by Disagreement — mutual information between predictions and model parameters
- **EVOI**: Expected Value of Information — Bayesian criterion for query selection in recommendation systems
- **UCB / Thompson Sampling**: Upper Confidence Bound and Thompson Sampling for exploration-exploitation
- **Cost-aware active learning**: `argmax [IG(x) / Cost(x)]` for budget-constrained settings
- **Active preference elicitation**: sequential pairwise comparisons with adaptive pair selection based on posterior entropy
- **Fisher information**: theoretical basis for optimal active learning query selection
