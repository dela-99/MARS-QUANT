"""Visualization module for MA-TSM-001 Monte Carlo Robustness Validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

from mars.apps.research_lab.ma_tsm_monte_carlo import MonteCarloResults


def setup_style():
    """Configure consistent style for all charts."""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.figsize": (10, 6),
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def plot_equity_fan_chart(
    results: MonteCarloResults,
    output_path: Path,
    title: str | None = None,
    n_paths: int = 50,
):
    """Plot Monte Carlo equity paths with percentile bands (fan chart).
    
    Paths are normalized to show percentage growth from initial capital,
    avoiding visual compression from extreme outliers.
    """
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 7))

    if results.sample_paths.size == 0:
        print(f"  Warning: No sample paths for {results.method}")
        return

    n_trades = results.sample_paths.shape[1] - 1
    x = np.arange(n_trades + 1)

    # Normalize paths to percentage growth from initial capital
    # This avoids visual compression from extreme outliers on linear scale
    paths_pct = (results.sample_paths / results.initial_capital - 1) * 100

    # Plot sampled paths (light)
    n_show = min(n_paths, len(paths_pct))
    for i in range(n_show):
        ax.plot(x, paths_pct[i], alpha=0.08, color="steelblue", linewidth=0.5)

    # Plot percentile bands
    percentiles = [5, 25, 50, 75, 95]
    p5 = np.percentile(paths_pct, 5, axis=0)
    p95 = np.percentile(paths_pct, 95, axis=0)
    p25 = np.percentile(paths_pct, 25, axis=0)
    p75 = np.percentile(paths_pct, 75, axis=0)
    p50 = np.percentile(paths_pct, 50, axis=0)

    ax.fill_between(x, p5, p95, alpha=0.15, color="steelblue", label="5th-95th percentile")
    ax.fill_between(x, p25, p75, alpha=0.25, color="steelblue", label="25th-75th percentile")
    ax.plot(x, p50, color="darkblue", linewidth=2.5, label="Median")

    # Historical terminal return marker
    hist_return_pct = results.historical_terminal_return * 100
    ax.scatter([n_trades], [hist_return_pct],
               color="red", s=120, zorder=5, label="Historical", marker="*", edgecolors="white", linewidth=1.5)

    ax.set_xlabel("Trade Number")
    ax.set_ylabel("Cumulative Return (%)")
    ax.set_title(title or f"Monte Carlo Equity Fan Chart — {results.method}")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    # Format y-axis as percentage
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.1f}%"))

    # Add horizontal line at 0%
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5, linewidth=0.8)

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_terminal_return_distribution(
    results_list: list[MonteCarloResults],
    labels: list[str],
    output_path: Path,
):
    """Plot histogram of terminal returns for all methods."""
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 7))

    colors = ["steelblue", "orange", "green"]
    for res, label, color in zip(results_list, labels, colors):
        returns_pct = res.terminal_returns * 100
        ax.hist(returns_pct, bins=50, alpha=0.5, label=label, density=True, color=color, edgecolor="white", linewidth=0.5)

        # Mark percentiles
        for p in [5, 25, 50, 75, 95]:
            val = res.return_percentiles[p] * 100
            ax.axvline(val, color=color, linestyle="--", alpha=0.7, linewidth=1)
        # Mark historical
        hist_val = res.historical_terminal_return * 100
        ax.axvline(hist_val, color="red", linestyle="-", linewidth=2.5, label=f"Historical ({label})")

    ax.set_xlabel("Terminal Return (%)")
    ax.set_ylabel("Density")
    ax.set_title("Terminal Return Distribution — All Methods")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_max_drawdown_distribution(
    results_list: list[MonteCarloResults],
    labels: list[str],
    output_path: Path,
):
    """Plot histogram of maximum drawdowns for all methods."""
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 7))

    colors = ["steelblue", "orange", "green"]
    for res, label, color in zip(results_list, labels, colors):
        dd_pct = res.max_drawdown_pcts * 100
        ax.hist(dd_pct, bins=50, alpha=0.5, label=label, density=True, color=color, edgecolor="white", linewidth=0.5)

        # Mark percentiles
        for p in [5, 25, 50, 75, 95]:
            val = res.dd_percentiles[p] * 100
            ax.axvline(val, color=color, linestyle="--", alpha=0.7, linewidth=1)
        # Mark historical
        hist_val = res.historical_max_dd * 100
        ax.axvline(hist_val, color="red", linestyle="-", linewidth=2.5, label=f"Historical ({label})")

    ax.set_xlabel("Maximum Drawdown (%)")
    ax.set_ylabel("Density")
    ax.set_title("Maximum Drawdown Distribution — All Methods")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_losing_streak_distribution(
    results_list: list[MonteCarloResults],
    labels: list[str],
    output_path: Path,
):
    """Plot distribution of maximum losing streaks."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ["steelblue", "orange", "green"]
    max_streak = max(int(np.max(r.max_losing_streaks)) for r in results_list)

    for res, label, color in zip(results_list, labels, colors):
        streaks = res.max_losing_streaks
        bins = np.arange(-0.5, max_streak + 1.5, 1)
        ax.hist(streaks, bins=bins, alpha=0.5, label=label, density=True, color=color, edgecolor="white", linewidth=0.5, align="mid")

        # Mark historical
        hist_val = res.historical_max_streak
        ax.axvline(hist_val, color="red", linestyle="-", linewidth=2.5, label=f"Historical ({label})")

    ax.set_xlabel("Maximum Losing Streak (consecutive trades)")
    ax.set_ylabel("Probability")
    ax.set_title("Losing Streak Distribution — All Methods")
    ax.set_xticks(range(0, max_streak + 1, 2))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_historical_vs_simulated(
    results_list: list[MonteCarloResults],
    labels: list[str],
    output_path: Path,
):
    """Plot historical outcome vs simulated distributions (box plots)."""
    setup_style()
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    metrics = [
        ("terminal_returns", "Terminal Return (%)", lambda x: x * 100),
        ("max_drawdown_pcts", "Maximum Drawdown (%)", lambda x: x * 100),
        ("terminal_returns", "Terminal Return (%)", lambda x: x * 100),  # Use returns instead of equity for consistent scale
        ("max_losing_streaks", "Max Losing Streak", lambda x: x),
    ]

    # Custom y-labels for the four subplots (3rd one is returns but labeled as equity growth)
    y_labels = [
        "Terminal Return (%)",
        "Maximum Drawdown (%)",
        "Terminal Return (%)",  # Same as first but for different visual emphasis
        "Max Losing Streak",
    ]

    colors = ["steelblue", "orange", "green"]

    for idx, (attr, title, transform) in enumerate(metrics):
        ax = axes[idx]
        data = []
        for res, label, color in zip(results_list, labels, colors):
            vals = transform(getattr(res, attr))
            data.append(vals)

        bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, widths=0.6)
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)

        # Mark historical values
        for i, res in enumerate(results_list):
            attr_map = {
                "terminal_returns": "historical_terminal_return",
                "max_drawdown_pcts": "historical_max_dd",
                "max_losing_streaks": "historical_max_streak",
            }
            hist_attr = attr_map.get(attr)
            if hist_attr and hasattr(res, hist_attr):
                hist_val = transform([getattr(res, hist_attr)])[0]
                ax.scatter(i + 1, hist_val, color="red", s=120, zorder=5, marker="*", 
                          label="Historical" if i == 0 else "", edgecolors="white", linewidth=1.5)

        ax.set_title(title)
        ax.set_ylabel(y_labels[idx])
        ax.grid(True, alpha=0.3, axis="y")

    # Add legend to first subplot
    axes[0].legend(loc="upper right")

    fig.suptitle("Historical Outcome vs Simulated Distributions", fontsize=16)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_method_comparison(
    results_list: list[MonteCarloResults],
    labels: list[str],
    output_path: Path,
):
    """Plot comparison of reshuffling, resampling, and block bootstrap methods."""
    setup_style()
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()

    metrics = [
        ("terminal_returns", "Terminal Return (%)", lambda x: x * 100),
        ("max_drawdown_pcts", "Max Drawdown (%)", lambda x: x * 100),
        ("max_losing_streaks", "Max Losing Streak", lambda x: x),
    ]

    colors = ["steelblue", "orange", "green"]

    # Row 1: Overlaid histograms
    for idx, (attr, title, transform) in enumerate(metrics):
        ax = axes[idx]
        for res, label, color in zip(results_list, labels, colors):
            vals = transform(getattr(res, attr))
            ax.hist(vals, bins=40, alpha=0.4, label=label, density=True, color=color, edgecolor="white", linewidth=0.3)
        ax.set_title(title)
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3)

    # Row 2: Percentile comparison bar charts
    percentiles = [5, 25, 50, 75, 95]
    x = np.arange(len(percentiles))
    width = 0.25

    for idx, (attr, title, transform) in enumerate(metrics):
        ax = axes[idx + 3]
        for i, (res, label, color) in enumerate(zip(results_list, labels, colors)):
            if "return" in attr:
                pcts = [transform([res.return_percentiles[p]])[0] for p in percentiles]
            elif "drawdown" in attr:
                pcts = [transform([res.dd_percentiles[p]])[0] for p in percentiles]
            elif "streak" in attr:
                pcts = [res.streak_percentiles[p] for p in percentiles]
            else:
                pcts = [0] * len(percentiles)

            offset = (i - 1) * width
            bars = ax.bar(x + offset, pcts, width, label=label, color=color, alpha=0.7, edgecolor="white")

        ax.set_xticks(x)
        ax.set_xticklabels([f"{p}th" for p in percentiles])
        ax.set_title(f"{title} — Percentile Comparison")
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Method Comparison: Reshuffling vs Resampling vs Block Bootstrap", fontsize=16)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_dd_threshold_probabilities(
    results_list: list[MonteCarloResults],
    labels: list[str],
    output_path: Path,
):
    """Plot probability of exceeding drawdown thresholds."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ["steelblue", "orange", "green"]
    thresholds = list(results_list[0].prob_dd_thresholds.keys())
    x = np.arange(len(thresholds))
    width = 0.25

    for i, (res, label, color) in enumerate(zip(results_list, labels, colors)):
        probs = [res.prob_dd_thresholds[t] * 100 for t in thresholds]
        offset = (i - 1) * width
        bars = ax.bar(x + offset, probs, width, label=label, color=color, alpha=0.7, edgecolor="white")
        # Add value labels
        for bar, prob in zip(bars, probs):
            if prob > 0.1:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                       f"{prob:.1f}%", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{t*100:.0f}%" for t in thresholds])
    ax.set_xlabel("Drawdown Threshold")
    ax.set_ylabel("Probability of Exceeding Threshold (%)")
    ax.set_title("Probability of Drawdown Exceeding Thresholds")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def generate_all_charts(
    reshuffle: MonteCarloResults,
    resample: MonteCarloResults,
    block: MonteCarloResults | None,
    output_dir: Path,
):
    """Generate all required charts."""
    output_dir.mkdir(parents=True, exist_ok=True)

    results_list = [reshuffle, resample]
    labels = ["Reshuffling", "Resampling"]
    if block:
        results_list.append(block)
        labels.append(f"Block Bootstrap (len={block.method.split('=')[-1].rstrip(')')})")

    print("\nGenerating charts...")

    # 1. Equity fan chart for each method
    for res in results_list:
        safe_name = res.method.replace(" ", "_").replace("(", "").replace(")", "").replace("=", "").replace(",", "")
        plot_equity_fan_chart(
            res,
            output_dir / f"fan_chart_{safe_name}.png",
            title=f"Monte Carlo Equity Fan Chart — {res.method}",
        )

    # 2. Terminal return distribution
    plot_terminal_return_distribution(
        results_list, labels,
        output_dir / "terminal_return_distribution.png",
    )

    # 3. Maximum drawdown distribution
    plot_max_drawdown_distribution(
        results_list, labels,
        output_dir / "max_drawdown_distribution.png",
    )

    # 4. Losing streak distribution
    plot_losing_streak_distribution(
        results_list, labels,
        output_dir / "losing_streak_distribution.png",
    )

    # 5. Historical vs simulated
    plot_historical_vs_simulated(
        results_list, labels,
        output_dir / "historical_vs_simulated.png",
    )

    # 6. Method comparison
    plot_method_comparison(
        results_list, labels,
        output_dir / "method_comparison.png",
    )

    # 7. DD threshold probabilities
    plot_dd_threshold_probabilities(
        results_list, labels,
        output_dir / "dd_threshold_probabilities.png",
    )

    print(f"\nAll charts saved to {output_dir}")


if __name__ == "__main__":
    # Test with saved results
    results_path = Path("reports/monte_carlo/monte_carlo_results.json")
    if results_path.exists():
        with open(results_path) as f:
            data = json.load(f)

        # Reconstruct results objects (minimal)
        from dataclasses import dataclass

        @dataclass
        class VizResults:
            method: str
            n_simulations: int
            n_trades: int
            initial_capital: float
            terminal_equities: np.ndarray
            terminal_returns: np.ndarray
            max_drawdowns: np.ndarray
            max_drawdown_pcts: np.ndarray
            max_losing_streaks: np.ndarray
            equity_percentiles: dict
            return_percentiles: dict
            dd_percentiles: dict
            streak_percentiles: dict
            prob_loss: float
            prob_dd_thresholds: dict
            prob_streak_threshold: float
            historical_terminal_return: float
            historical_max_dd: float
            historical_max_streak: int
            sample_paths: np.ndarray

        def load_res(key: str) -> VizResults:
            d = data[key]
            # Note: terminal_equities etc are not in saved JSON, need to regenerate or store more
            # For now, skip and regenerate from main script
            return None

        print("Run from main script to generate charts with full data.")
    else:
        print(f"Results not found at {results_path}")