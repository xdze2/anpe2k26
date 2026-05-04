---
title: "Curiosity-driven exploration in robotics algorithms"
created: 2026-05-04
description: "Claude conversation with 4 messages"
---

**You**

in robotics, how the notion of "curiosity" is used? how this related to the notion of exploration/exploitation?

my concern is about finding an algorithm or method, to identify the optimal next information gathering step (costly) based on the current information, and also on a prediction a model could make...

---

**Claude**

I'll walk you through how curiosity is formalized in robotics and how it connects to your problem of optimal information gathering.Now let me search for more specific connections to active learning and information theory:Great! Now let me search for the exploration-exploitation tradeoff connection:Excellent! Now I have enough context to give you a comprehensive answer. Let me synthesize this for you:

## How "Curiosity" is Formalized in Robotics

Curiosity-based exploration denotes a class of algorithms where agents are intrinsically motivated to seek novel, unpredictable, or informative experiences, typically via an internal reward signal. Rather than treating curiosity as a vague concept, roboticists operationalize it through three main mechanisms:

1. **Prediction Error / Model Disagreement**: Intrinsic motivation algorithms drive actions toward activities that maximize information gain and learning progress. Prediction errors are computed as the discrepancy between expected sensory inputs and actual observations.

2. **Information Gain**: Curiosity is defined as the unsupervised act of moving through the world to seek novel observations with high information content. Observation data from paths that maximize information gain results in better terrain models.

3. **Novelty Seeking**: Robots prioritize states they haven't visited or observations they haven't made before.

---

## The Exploration-Exploitation Connection

The relationship is direct and fundamental:

- **Exploration** = Curiosity-driven behavior (seeking novel, informative states)
- **Exploitation** = Using what you've already learned (following the current best policy)

The exploration-exploitation tradeoff is the challenge of balancing gathering new information about the environment (exploration) and using existing knowledge to maximize rewards (exploitation).

Since extrinsic feedback in real-world environments is often sparse or delayed, agents equipped only with task rewards may fail to explore sufficiently. Curiosity-driven approaches therefore enable data-efficient, robust, and generalizable learning.

---

## Your Core Problem: Optimal Information Gathering Under Cost

This is exactly what **active learning** and **optimal experimental design** formalize. Here are the main frameworks:

### 1. **Information-Theoretic Acquisition Functions**

Bayesian optimal experiment design methods can be understood as approximations to information-theoretic quantities: mutual information between predictions and model parameters (expected information gain or BALD), and mutual information between predictions and test samples (expected predictive information gain).

**For your problem**, the key metric is:

```
Information Gain(x) = H(Y) - E[H(Y|x)]
```

Where:

- `H(Y)` = entropy of your model's predictions before measurement
- `E[H(Y|x)]` = expected entropy after observing point `x`

Points with high information gain **reduce your model's uncertainty the most**.

### 2. **Uncertainty-Based Methods (UCB & Thompson Sampling)**

Upper Confidence Bound (UCB) and Thompson Sampling (TS) explicitly model uncertainty with confidence intervals or probability distributions to drive the exploration process. Both encompass current knowledge (mean) and related uncertainty (variance).

Thompson Sampling uses probability distributions to naturally balance exploration and exploitation. Options you're uncertain about naturally get more exploration, while proven winners get exploited more often.

**For your robotics problem**, this means:

```
Score(x) = mean_prediction(x) + c × uncertainty(x)
```

Or using Thompson sampling: **sample from the posterior over your model's parameters and pick actions that look best under those samples.**

### 3. **Cost-Aware Active Learning**

This is crucial for your "costly" measurement scenario. The goal becomes:

```
argmax_x [Information_Gain(x) / Cost(x)]
```

Or in a Bayesian optimization context:

```
argmax_x [Expected_Improvement(x) - λ × Cost(x)]
```

Where `λ` weights cost vs. information gain.

A prior distribution over unknown parameters is updated to a posterior after each experiment. For the next measurement, one chooses the experiment that shrinks uncertainty the most while considering the cost-benefit tradeoff.

---

## Recommended Algorithms for Your Use Case

Given that you want to identify optimal next measurement steps based on current information and model predictions:

| Algorithm                                           | Best For                                         | Key Idea                                                        |
| --------------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------- |
| **BALD (Bayesian Active Learning by Disagreement)** | Classification/uncertainty                       | Pick points where your model is most uncertain                  |
| **Expected Information Gain**                       | General case                                     | Pick points that reduce posterior entropy the most              |
| **Uncertainty Sampling + Cost**                     | Cost-constrained                                 | `Score = Uncertainty(x) / Cost(x)`                              |
| **Thompson Sampling**                               | Non-stationary, exploration-exploitation balance | Sample from posterior, pick best under sample                   |
| **Mutual Information Maximization**                 | Structure learning                               | Pick measurements that distinguish between competing hypotheses |
| **Expected Improvement (EI)**                       | Optimization-focused                             | Balance exploiting good regions vs. exploring uncertain ones    |

---

## Practical Implementation Sketch

```python
def select_next_measurement(model, candidates, cost_fn, budget_remaining):
    predictions = model.predict(candidates)  # mean & uncertainty

    # Information gain for each candidate
    ig = compute_information_gain(predictions)

    # Cost-adjusted score
    scores = ig / np.array([cost_fn(x) for x in candidates])

    # Or Thompson-like: sample model params, pick highest expected reward
    # theta ~ posterior()
    # scores = [reward_under_theta(x) for x in candidates]

    # Weighted toward high-score candidates
    best_idx = np.argmax(scores)
    return candidates[best_idx]
```

---

## Key References for Deeper Dive

- Unifying Active Learning frameworks via Fisher Information and Information-Theoretic Quantities (covers BALD, EI, and connections)
- Information-Theoretic Confidence Bounds for Reinforcement Learning (Thompson sampling + information gain)
- Active Inference and Artificial Reasoning (KL divergence for action selection, Bayesian model reduction)

The key insight: **your "curiosity" should be quantified as whichever information-theoretic quantity (mutual information, entropy reduction, KL divergence) best captures what your model needs to learn, then select measurements that maximize that quantity per unit cost.**

---

**You**

Let me describe my setup, I have:

- a list of candidates (products for example), an user may be interested in
- a partial user preference text (what the user want)
- a partial description of each candidates product

At each step I can:

- fetch more info and complete a product description
- ask feedback from the user on some product (from the description I have)

I update the user-preference text from the (indirect user feedback)

---

**Claude**

This is a classic **active learning in recommendation systems** problem. Let me map your setup to the frameworks we discussed and identify the optimal strategy.Now let me search for expected value of information and decision-theoretic approaches:Perfect! Now let me search for information about hybrid approaches and feature-based queries:Excellent! Now I have all the information I need. Let me create a comprehensive framework for the user's specific problem.Now let me create a comprehensive framework diagram for your specific problem:Perfect! Now let me give you the concrete algorithms:

## Your Problem Mapped to Active Learning

You have a **dual-query scenario** with two independent information sources:

1. **Product information queries** (fetching more description details) — expensive API calls
2. **User feedback queries** (asking pairwise comparisons or explicit preferences) — expensive cognitive load

---

## Framework: Expected Value of Information (EVOI)

Expected value of information (EVOI) is a principled Bayesian criterion for selecting queries such that posterior decision quality is maximized in expectation over possible user responses. EVOI requires selecting queries such that the expected utility (user satisfaction with recommendations) improves the most.

For your two-stage problem:

### **Stage 1: Information Gathering (Fetch Product Details)**

Score each **missing product attribute** (e.g., "brand", "material", "warranty"):

```
Score(attribute_j, product_i) =
    Information_Gain(x_ij) / Cost_fetch(x_ij)

where:
  Information_Gain(x_ij) = H(predictions | no x_ij) - H(predictions | has x_ij)
  Cost_fetch = API cost (seconds, $, API quota)
  H() = entropy of your model's rankings
```

**Intuition**: Fetch the missing attribute that, when filled in, most _reduces uncertainty about which products you should rank highest_.

### **Stage 2: Preference Learning (Ask User Feedback)**

In active learning for preference elicitation, users are sequentially and adaptively queried, selecting preferred options among small subsets of offered alternatives. Learning efficiency depends on the alternatives offered at each time epoch.

Score each **candidate comparison** (which two products to ask about):

```
Score(product_pair_(i,j)) =
    Mutual_Information(comparison_result, user_preferences) / Cost_feedback

where:
  Mutual_Information ≈ expected reduction in posterior entropy over preference parameters
  Cost_feedback = user effort (time, mental load)
```

**Intuition**: Ask about products that **disambiguate between competing preference models** the most. If your current model is torn between "user prefers eco-friendly products" vs "user wants cheap products", ask about two products that differ strongly on those dimensions.

---

## Concrete Algorithm: Cost-Aware EVOI

Here's a practical implementation:

### **Step 1: Maintain State**

```python
class RecommendationState:
    def __init__(self):
        # Products with partial descriptions
        self.products = [
            {
                'id': 'p1',
                'known_attrs': {'price': 100, 'brand': 'Nike'},
                'missing_attrs': {'material', 'warranty', 'reviews'}
            },
            # ...
        ]

        # User preference model (Bayesian)
        self.pref_model = BayesianPreferenceModel()
        # posterior over: weights on [price, eco-score, popularity, ...]

        # Partial user preference text
        self.user_preference_text = "I like outdoor gear that's durable"
```

### **Step 2: Score Information Queries**

```python
def score_information_queries(state):
    """Score fetching missing product attributes."""
    scores = {}

    for product in state.products:
        for missing_attr in product['missing_attrs']:
            # Current uncertainty about recommendations
            current_rankings = state.pref_model.predict_all(
                products=state.products,
                text=state.user_preference_text
            )
            current_entropy = compute_entropy(current_rankings.probabilities)

            # Hypothetical entropy if we fill in this attribute
            # (use posterior predictive: integrate over likely values)
            likely_values = state.pref_model.sample_attribute_posteriors(
                product, missing_attr, n_samples=10
            )

            expected_entropy_after = np.mean([
                compute_entropy(state.pref_model.predict_all(
                    products={**product, missing_attr: val},
                    text=state.user_preference_text
                ).probabilities)
                for val in likely_values
            ])

            information_gain = current_entropy - expected_entropy_after
            cost = cost_of_fetching(missing_attr)  # Time, API quota, $

            scores[(product['id'], missing_attr)] = information_gain / cost

    return scores
```

### **Step 3: Score Preference Queries**

```python
def score_preference_queries(state):
    """Score asking user to compare products."""
    scores = {}

    # Generate candidate pairs: diverse products, uncertain model
    candidate_pairs = generate_candidate_pairs(
        state.products,
        diversity_strategy='high_mutual_info'
    )

    for pair_idx, (prod_a, prod_b) in enumerate(candidate_pairs):
        # Mutual information: if user says A > B, how much do we learn?
        # = entropy_before - E[entropy_after | user_feedback]

        prior_preference = state.pref_model.predict_comparison(
            prod_a, prod_b, text=state.user_preference_text
        )  # P(A > B | current model)

        # Two scenarios: user picks A, or user picks B
        entropy_if_a_wins = state.pref_model.posterior_entropy(
            observation=(prod_a, prod_b, 'A'),
            text=state.user_preference_text
        )

        entropy_if_b_wins = state.pref_model.posterior_entropy(
            observation=(prod_a, prod_b, 'B'),
            text=state.user_preference_text
        )

        # Expected entropy after (weighted by likelihood of each outcome)
        expected_entropy_after = (
            prior_preference * entropy_if_a_wins +
            (1 - prior_preference) * entropy_if_b_wins
        )

        current_entropy = state.pref_model.entropy()
        mutual_info = current_entropy - expected_entropy_after

        cost = cost_of_user_comparison(prod_a, prod_b)  # Effort, time

        # Diversity bonus: penalize pairs that are too similar
        diversity_penalty = diversity_score(prod_a, prod_b)

        scores[pair_idx] = (mutual_info * diversity_penalty) / cost

    return scores
```

### **Step 4: Choose Next Action**

```python
def select_next_query(state, budget_remaining):
    """Compare both types and pick the best."""
    info_scores = score_information_queries(state)
    pref_scores = score_preference_queries(state)

    # Normalize to [0, 1] for fair comparison
    info_scores_norm = normalize(info_scores)
    pref_scores_norm = normalize(pref_scores)

    # Find best from each category
    best_info_query = max(info_scores_norm.items(), key=lambda x: x[1])
    best_pref_query = max(pref_scores_norm.items(), key=lambda x: x[1])

    # Decide which to execute
    if best_info_query[1] > best_pref_query[1]:
        product_id, attr = best_info_query[0]
        action = ('fetch_info', product_id, attr)
    else:
        pair_idx = best_pref_query[0]
        prod_a, prod_b = candidate_pairs[pair_idx]
        action = ('ask_feedback', prod_a, prod_b)

    return action
```

### **Step 5: Update After Observation**

```python
def update_state(state, action, observation):
    """Incorporate new data."""
    if action[0] == 'fetch_info':
        product_id, attr = action[1], action[2]
        state.products[product_id][attr] = observation  # The fetched value
        state.products[product_id]['missing_attrs'].remove(attr)

    elif action[0] == 'ask_feedback':
        prod_a, prod_b, winner = action[1], action[2], observation
        # Bayesian update: condition posterior on this comparison
        state.pref_model.update(
            comparison=(prod_a, prod_b),
            winner=winner,
            text=state.user_preference_text
        )

        # Optionally: update preference text from implicit feedback
        state.user_preference_text = refine_text(
            state.user_preference_text,
            comparison=(prod_a, prod_b),
            winner=winner
        )
```

---

## Key Decision Rules

Considering queries at different levels of granularity to optimize user information acquisition is crucial to provide good user experience. Based on the Fisher information matrix, theoretically optimal active learning strategy can be derived.

### **When to Fetch Info vs Ask Feedback**

| Scenario                                                                 | Action                                      | Rationale                                                                |
| ------------------------------------------------------------------------ | ------------------------------------------- | ------------------------------------------------------------------------ |
| Many products with **incomplete descriptions** (>50% missing attrs)      | **Fetch product info**                      | High information gain relative to cost; narrows search space             |
| Model **very uncertain** about user preferences (high posterior entropy) | **Ask user feedback**                       | Direct reduction in preference uncertainty; EVOI highest                 |
| Products **already well-described** but model **can't rank** them        | **Ask user feedback**                       | Model has enough info; needs calibration                                 |
| User has **clear partial preference** (minimal text)                     | **Fetch info** first, then **ask feedback** | Better to gather context before asking comparisons                       |
| Time/budget **very limited**                                             | **Ask feedback on top-K candidates only**   | Pairwise comparisons are more "sample efficient" than fetching all attrs |

---

## Implementation Tips

**1. Entropy Estimation**
Use your model's predictions with uncertainty (e.g., Bayesian NN, Gaussian Process):

```python
def compute_entropy(ranking_probs):
    """Ranking entropy: how uncertain is the top-k order?"""
    # ranking_probs = [P(rank=1 for each product), ...]
    return -np.sum(ranking_probs * np.log(ranking_probs + 1e-10))
```

**2. Candidate Pair Selection**
Pairwise comparisons are more effective for preference learning than choice sets with multiple options. Active learning can find the most preferred choice based exclusively on pairwise comparisons.

```python
def generate_candidate_pairs(products, diversity_strategy='high_mutual_info'):
    """Avoid redundant pairs (too similar) and uninformative pairs."""
    pairs = []
    for i, p1 in enumerate(products):
        for j in range(i+1, len(products)):
            p2 = products[j]

            # Skip if too similar (both highly preferred or both poor)
            score_diff = abs(predict_score(p1) - predict_score(p2))
            if score_diff < threshold:
                continue

            # Skip if very far apart (one clearly better than other)
            if score_diff > upper_threshold:
                continue

            pairs.append((p1, p2))

    return pairs[:k]  # Top-k most informative
```

**3. Cost Modeling**
Be honest about costs:

```python
def cost_of_fetching(attribute):
    """Seconds + API cost."""
    lookup_time = {
        'reviews': 2.5,      # External API call
        'specifications': 0.3,  # Local DB
        'images': 1.0,
    }
    api_cost = {'reviews': 0.005, ...}  # $ per call
    return lookup_time[attribute] + 100 * api_cost[attribute]

def cost_of_user_comparison(prod_a, prod_b):
    """Estimated seconds of user time."""
    # ~10-15 sec per comparison
    # +2 sec if products very different (requires more reading)
    similarity = cosine_sim(prod_a.features, prod_b.features)
    return 12 + 2 * (1 - similarity)
```

---

## Which Framework to Use?

- Gradient-based optimization for Bayesian preference elicitation enables efficiently constructing queries with maximum EVOI in large item spaces by using differentiable networks optimized via gradient methods. **Use this if**: you have deep learning models and large candidate sets.

- **BALD (Bayesian Active Learning by Disagreement)** — simpler, works with any model. **Use this if**: you want a quick baseline.

- **Thompson Sampling** — naturally balances exploration (learning) vs exploitation (good recommendations). **Use this if**: you want a simpler algorithm that doesn't require explicit entropy calculations.

---

## Putting It Together: Pseudocode

```python
for step in range(max_steps):
    # Current state: partial products, user feedback so far

    # Score all possible queries
    info_scores = score_information_queries(state)
    pref_scores = score_preference_queries(state)

    # Normalize and compare
    best_info = max(info_scores.items(), key=lambda x: x[1])
    best_pref = max(pref_scores.items(), key=lambda x: x[1])

    if best_info[1] / cost_info > best_pref[1] / cost_pref:
        # Fetch product info
        product_id, attr = best_info[0]
        result = fetch_product_details(product_id, attr)
    else:
        # Ask user feedback
        prod_a, prod_b = best_pref[0]
        result = ask_user_comparison(prod_a, prod_b)

    # Update: both model and product database
    state = update_state(state, action, result)

    # Optionally: show user top-K recommendations so far
    recommendations = state.pref_model.predict_all(state.products)
    show_to_user(recommendations[:5])
```

This balances **data efficiency** (learning as much as possible per query) with **user experience** (asking questions that matter and showing good recommendations in the meantime).
