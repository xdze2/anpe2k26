import argparse

import numpy as np
import matplotlib.pyplot as plt

# uv run --with numpy --with matplotlib scripts/demo_elo.py
# uv run --with numpy --with matplotlib scripts/demo_elo.py --method adaptive
# uv run --with numpy --with matplotlib scripts/demo_elo.py --method both
# uv run --with numpy --with matplotlib scripts/demo_elo.py --method both --top 5

nbr_nodes = 35
NODE_FORCES = np.linspace(-10, 10, nbr_nodes)
TRUE_RANK = np.argsort(np.argsort(NODE_FORCES))  # rank of each node (0=worst)

K = 32
NBR_ITERATIONS = 500
NBR_SEEDS = 20  # runs averaged for the error plot
# ELO window around the Nth-rank threshold to define the contested zone
BOUNDARY_WINDOW = 100


def match(node_a: int, node_b: int) -> int:
    if NODE_FORCES[node_a] > NODE_FORCES[node_b]:
        return node_a
    else:
        return node_b


def pick_random(
    ratings: np.ndarray, rng: np.random.Generator, top_n: int | None
) -> tuple[int, int]:
    pool = _contested_pool(ratings, top_n)
    a, b = rng.choice(pool, size=2, replace=False)
    return int(a), int(b)


def pick_adaptive(
    ratings: np.ndarray, rng: np.random.Generator, top_n: int | None
) -> tuple[int, int]:
    pool = _contested_pool(ratings, top_n)
    order = pool[np.argsort(ratings[pool])]
    i = rng.integers(0, len(order) - 1)
    return int(order[i]), int(order[i + 1])


def _contested_pool(ratings: np.ndarray, top_n: int | None) -> np.ndarray:
    """Return node indices eligible for matching. With top_n, restrict to the
    contested zone around the Nth-rank boundary."""
    if top_n is None:
        return np.arange(len(ratings))
    threshold = np.sort(ratings)[::-1][top_n - 1]  # Nth highest rating
    in_window = np.abs(ratings - threshold) <= BOUNDARY_WINDOW
    pool = np.where(in_window)[0]
    if len(pool) < 2:
        pool = np.argsort(np.abs(ratings - threshold))[:2]
    return pool


def _misclassified(ratings: np.ndarray, top_n: int) -> int:
    """Number of nodes on the wrong side of the top-N boundary."""
    predicted_top = set(np.argsort(ratings)[::-1][:top_n])
    true_top = set(np.argsort(NODE_FORCES)[::-1][:top_n])
    return len(predicted_top.symmetric_difference(true_top)) // 2


def _rank_error(ratings: np.ndarray) -> float:
    """Mean absolute rank error across all nodes (0 = perfect)."""
    predicted_rank = np.argsort(np.argsort(ratings))
    return float(np.mean(np.abs(predicted_rank - TRUE_RANK)))


def run_elo(pick_fn, top_n: int | None, seed: int = 42) -> np.ndarray:
    ratings = np.zeros(nbr_nodes)
    history = [ratings.copy()]
    rng = np.random.default_rng(seed)

    for _ in range(NBR_ITERATIONS):
        a, b = pick_fn(ratings, rng, top_n)
        winner = match(a, b)

        expected_a = 1 / (1 + 10 ** ((ratings[b] - ratings[a]) / 400))
        score_a = 1.0 if winner == a else 0.0

        ratings[a] += K * (score_a - expected_a)
        ratings[b] += K * ((1 - score_a) - (1 - expected_a))

        history.append(ratings.copy())

    return np.array(history)  # shape: (NBR_ITERATIONS+1, nbr_nodes)


def compute_error_curve(pick_fn, top_n: int | None) -> np.ndarray:
    """Average error curve over NBR_SEEDS independent runs."""
    curves = []
    for seed in range(NBR_SEEDS):
        history = run_elo(pick_fn, top_n, seed=seed)
        if top_n:
            errors = [_misclassified(history[t], top_n) for t in range(len(history))]
        else:
            errors = [_rank_error(history[t]) for t in range(len(history))]
        curves.append(errors)
    return np.array(curves)  # shape: (NBR_SEEDS, NBR_ITERATIONS+1)


def plot_history(ax, history: np.ndarray, title: str, top_n: int | None) -> None:
    cmap = plt.colormaps["coolwarm"]
    true_top = set(np.argsort(NODE_FORCES)[::-1][:top_n]) if top_n else set()
    for i in range(nbr_nodes):
        color = cmap(i / (nbr_nodes - 1))
        lw = 2.0 if i in true_top else 0.8
        alpha = 0.9 if i in true_top else 0.4
        ax.plot(history[:, i], color=color, alpha=alpha, linewidth=lw)
    if top_n:
        boundary_force = np.sort(NODE_FORCES)[::-1][top_n - 1]
        ax.axhline(
            history[-1, np.where(NODE_FORCES == boundary_force)[0][0]],
            color="black", linestyle="--", linewidth=0.8, alpha=0.5,
            label=f"top-{top_n} boundary (final)",
        )
        ax.legend(fontsize=8)
    ax.set_xlabel("Iterations")
    ax.set_ylabel("ELO rating")
    ax.set_title(title)


def plot_error(ax, curves_by_method: dict, top_n: int | None) -> None:
    colors = {"random": "steelblue", "adaptive": "tomato"}
    steps = np.arange(NBR_ITERATIONS + 1)
    for label, curves in curves_by_method.items():
        mean = curves.mean(axis=0)
        lo = np.percentile(curves, 10, axis=0)
        hi = np.percentile(curves, 90, axis=0)
        c = colors.get(label, "gray")
        ax.plot(steps, mean, color=c, linewidth=1.8, label=label)
        ax.fill_between(steps, lo, hi, color=c, alpha=0.15)
    if top_n:
        ax.set_ylabel(f"Misclassified nodes (top-{top_n})")
        ax.set_title(f"Convergence — top-{top_n} error (mean ± p10/p90 over {NBR_SEEDS} seeds)")
    else:
        ax.set_ylabel("Mean absolute rank error")
        ax.set_title(f"Convergence — rank error (mean ± p10/p90 over {NBR_SEEDS} seeds)")
    ax.set_xlabel("Iterations")
    ax.legend()
    ax.set_ylim(bottom=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--method",
        choices=["random", "adaptive", "both"],
        default="random",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="Focus matches on the contested zone around rank N (boundary pairing)",
    )
    args = parser.parse_args()
    top_n = args.top
    suffix = f"_top{top_n}" if top_n else ""

    methods: dict = {}
    if args.method in ("random", "both"):
        methods["random"] = pick_random
    if args.method in ("adaptive", "both"):
        methods["adaptive"] = pick_adaptive

    # --- figure 1: ELO trajectories (single seed) ---
    n_methods = len(methods)
    fig1, axes1 = plt.subplots(1, n_methods, figsize=(8 * n_methods, 6), sharey=True)
    if n_methods == 1:
        axes1 = [axes1]
    for ax, (label, pick_fn) in zip(axes1, methods.items()):
        title = label.capitalize() + (" pairing" if not top_n else f" (top-{top_n} focus)")
        plot_history(ax, run_elo(pick_fn, top_n), title, top_n)
    fig1.tight_layout()
    out1 = f"scripts/elo_trajectories_{args.method}{suffix}.png"
    fig1.savefig(out1, dpi=150)
    print(f"Saved {out1}")

    # --- figure 2: error convergence averaged over seeds ---
    print(f"Computing error curves over {NBR_SEEDS} seeds…")
    error_curves = {label: compute_error_curve(fn, top_n) for label, fn in methods.items()}
    fig2, ax2 = plt.subplots(figsize=(9, 5))
    plot_error(ax2, error_curves, top_n)
    fig2.tight_layout()
    out2 = f"scripts/elo_error_{args.method}{suffix}.png"
    fig2.savefig(out2, dpi=150)
    print(f"Saved {out2}")

    plt.show()


main()
