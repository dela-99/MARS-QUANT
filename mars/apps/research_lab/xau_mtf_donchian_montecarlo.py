"""
Monte Carlo robustness analysis for XAU-MTF-DONCHIAN-001 (Assignment 14, section G).

Two distinct experiments are run, because they answer different questions:

**Trade reshuffling (sequence risk)**
    The observed set of trade outcomes is kept intact and only the *order* is
    permuted.  This isolates sequence risk: how much of the drawdown is caused
    by the particular ordering of the realised trades rather than by the
    outcomes themselves.  The terminal P&L is identical across permutations by
    construction, so only the drawdown and the path shape vary.

**Trade resampling (outcome distribution)**
    Trades are drawn with replacement from the observed outcome distribution.
    This widens the distribution of terminal P&L and answers "what could have
    happened", while discarding the dependence structure between trades.

Both simulations are labelled as assuming i.i.d. trade outcomes.  That
assumption is known to be false for breakout systems (wins and losses cluster
by volatility regime), so the results are an *upper bound on apparent
robustness*, not evidence of edge.

Assumptions are printed with every run and stored in the output payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MonteCarloConfig:
    """Monte Carlo configuration.  Every field is recorded in the output."""

    n_simulations: int = 2_000
    seed: int = 20_260_924
    percentiles: tuple = (5, 25, 50, 75, 95)
    confidence_level: float = 0.95
    assumptions: tuple = (
        "Trade outcomes are drawn i.i.d. from the observed distribution.",
        "Trade sequencing carries no information beyond the outcome multiset "
        "(reshuffling) or is replaced by sampling with replacement (resampling).",
        "Position sizing is proportional to equity, so each simulated trade is "
        "scaled by the equity path it occurs on.",
        "Costs are already embedded in the observed per-trade net P&L and are not "
        "re-sampled.",
        "No regime or volatility clustering is modelled: the i.i.d. assumption is "
        "known to understate the tail for breakout systems.",
    )
    limitations: tuple = (
        "Resampled results are a dispersion estimate, not a forecast.",
        "The number of observed trades bounds the resolution of the outcome "
        "distribution; small samples cannot support strong inference.",
        "Results describe the strategy as specified, not the strategy family.",
    )


def _equity_path(pnls: np.ndarray, starting_equity: float) -> np.ndarray:
    """Compound a sequence of trade P&Ls (equity-relative) into an equity path."""
    equity = starting_equity
    path = np.empty(len(pnls) + 1, dtype=float)
    path[0] = equity
    for i, pnl in enumerate(pnls):
        equity += pnl
        path[i + 1] = equity
    return path


def _max_drawdown_from_path(path: np.ndarray) -> float:
    peak = np.maximum.accumulate(path)
    dd = path - peak
    return float(dd.min())


def run_reshuffle(
    trade_pnls: np.ndarray,
    starting_equity: float,
    config: MonteCarloConfig,
) -> Dict[str, Any]:
    """Permute the order of the observed trades and measure path risk."""
    n = len(trade_pnls)
    rng = np.random.default_rng(config.seed)
    terminal = np.empty(config.n_simulations, dtype=float)
    max_dd = np.empty(config.n_simulations, dtype=float)
    paths = np.empty((config.n_simulations, n + 1), dtype=float)
    for s in range(config.n_simulations):
        order = rng.permutation(n)
        path = _equity_path(trade_pnls[order], starting_equity)
        paths[s] = path
        terminal[s] = path[-1]
        max_dd[s] = _max_drawdown_from_path(path)
    return {
        "experiment": "reshuffle",
        "n_trades": n,
        "paths": paths,
        "terminal_equity": terminal,
        "max_drawdown": max_dd,
        "terminal_equity_mean": float(terminal.mean()),
        "terminal_equity_std": float(terminal.std(ddof=1)),
        "max_drawdown_mean": float(max_dd.mean()),
        "max_drawdown_p05": float(np.percentile(max_dd, 5)),
        "max_drawdown_p95": float(np.percentile(max_dd, 95)),
    }


def run_resample(
    trade_pnls: np.ndarray,
    starting_equity: float,
    config: MonteCarloConfig,
) -> Dict[str, Any]:
    """Bootstrap the trade outcomes and measure outcome dispersion."""
    n = len(trade_pnls)
    rng = np.random.default_rng(config.seed + 1)
    terminal = np.empty(config.n_simulations, dtype=float)
    max_dd = np.empty(config.n_simulations, dtype=float)
    paths = np.empty((config.n_simulations, n + 1), dtype=float)
    for s in range(config.n_simulations):
        sample = rng.choice(trade_pnls, size=n, replace=True)
        path = _equity_path(sample, starting_equity)
        paths[s] = path
        terminal[s] = path[-1]
        max_dd[s] = _max_drawdown_from_path(path)
    return {
        "experiment": "resample",
        "n_trades": n,
        "paths": paths,
        "terminal_equity": terminal,
        "max_drawdown": max_dd,
        "terminal_equity_mean": float(terminal.mean()),
        "terminal_equity_std": float(terminal.std(ddof=1)),
        "terminal_equity_p05": float(np.percentile(terminal, 5)),
        "terminal_equity_p95": float(np.percentile(terminal, 95)),
        "max_drawdown_mean": float(max_dd.mean()),
        "max_drawdown_p05": float(np.percentile(max_dd, 5)),
        "max_drawdown_p95": float(np.percentile(max_dd, 95)),
    }


def summarise(
    observed_pnls: np.ndarray,
    starting_equity: float,
    config: MonteCarloConfig,
) -> Dict[str, Any]:
    """Run both experiments and return a JSON-safe summary."""
    reshuffle = run_reshuffle(observed_pnls, starting_equity, config)
    resample = run_resample(observed_pnls, starting_equity, config)
    observed_path = _equity_path(observed_pnls, starting_equity)
    observed_dd = _max_drawdown_from_path(observed_path)

    def bands(paths: np.ndarray) -> Dict[str, float]:
        out = {}
        for p in config.percentiles:
            out[f"p{p}"] = float(np.percentile(paths, p))
        return out

    return {
        "config": {
            "n_simulations": config.n_simulations,
            "seed": config.seed,
            "percentiles": list(config.percentiles),
            "assumptions": list(config.assumptions),
            "limitations": list(config.limitations),
        },
        "observed": {
            "n_trades": int(len(observed_pnls)),
            "terminal_equity": float(observed_path[-1]),
            "terminal_return": float(observed_path[-1] / starting_equity - 1.0),
            "max_drawdown": observed_dd,
            "max_drawdown_pct": float(observed_dd / observed_path.max()),
            "mean_trade_pnl": float(observed_pnls.mean()),
        },
        "reshuffle": {
            "terminal_equity_mean": reshuffle["terminal_equity_mean"],
            "terminal_equity_std": reshuffle["terminal_equity_std"],
            "max_drawdown_mean": reshuffle["max_drawdown_mean"],
            "max_drawdown_p05": reshuffle["max_drawdown_p05"],
            "max_drawdown_p95": reshuffle["max_drawdown_p95"],
            "max_drawdown_bands": bands(reshuffle["max_drawdown"]),
        },
        "resample": {
            "terminal_equity_mean": resample["terminal_equity_mean"],
            "terminal_equity_std": resample["terminal_equity_std"],
            "terminal_equity_p05": resample["terminal_equity_p05"],
            "terminal_equity_p95": resample["terminal_equity_p95"],
            "max_drawdown_mean": resample["max_drawdown_mean"],
            "max_drawdown_p05": resample["max_drawdown_p05"],
            "max_drawdown_p95": resample["max_drawdown_p95"],
            "terminal_bands": bands(resample["terminal_equity"]),
            "max_drawdown_bands": bands(resample["max_drawdown"]),
        },
        "_paths": {
            "reshuffle": reshuffle["paths"],
            "resample": resample["paths"],
            "observed": observed_path,
        },
    }


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------


def plot_fan_and_distributions(
    summary: Dict[str, Any],
    out_dir: Path,
    *,
    label: str = "XAU-MTF-DONCHIAN-001",
    threshold: Optional[float] = None,
) -> Dict[str, str]:
    """
    Write the equity fan chart and the two distribution charts.

    Returns a mapping of chart name to written file path.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = summary["_paths"]
    config = summary["config"]
    written: Dict[str, str] = {}

    # --- equity fan chart -------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    for ax, key, title in (
        (axes[0], "reshuffle", "Trade reshuffling (sequence risk)"),
        (axes[1], "resample", "Trade resampling (outcome dispersion)"),
    ):
        sim_paths = paths[key]
        median = np.median(sim_paths, axis=0)
        p5 = np.percentile(sim_paths, 5, axis=0)
        p25 = np.percentile(sim_paths, 25, axis=0)
        p75 = np.percentile(sim_paths, 75, axis=0)
        p95 = np.percentile(sim_paths, 95, axis=0)
        x = np.arange(sim_paths.shape[1])
        ax.fill_between(x, p5, p95, color="#1f3b57", alpha=0.18, label="p5-p95")
        ax.fill_between(x, p25, p75, color="#1f3b57", alpha=0.38, label="p25-p75")
        ax.plot(x, median, color="#1f3b57", lw=1.8, label="median")
        ax.plot(x, paths["observed"], color="#d1495b", lw=1.6, label="observed")
        if threshold is not None:
            ax.axhline(threshold, color="#666", ls="--", lw=1.0, label="threshold")
        ax.set_title(title)
        ax.set_xlabel("trade number")
        ax.set_ylabel("equity (USD)")
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8)
    fig.suptitle(f"{label} — Monte Carlo equity fan ({config['n_simulations']:,} simulations)")
    fig.tight_layout()
    fan_path = out_dir / "monte_carlo_equity_fan.png"
    fig.savefig(fan_path, dpi=130)
    plt.close(fig)
    written["equity_fan"] = str(fan_path)

    # --- distributions -----------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))

    obs_dd = summary["observed"]["max_drawdown"]
    dd = paths["reshuffle"]
    ax = axes[0]
    # recompute per-simulation drawdown from the stored paths
    peaks = np.maximum.accumulate(dd, axis=1)
    dd_series = (dd - peaks).min(axis=1)
    ax.hist(dd_series, bins=60, color="#1f3b57", alpha=0.8)
    ax.axvline(obs_dd, color="#d1495b", lw=1.8, label=f"observed {obs_dd:,.0f}")
    ax.set_title("Reshuffle: max drawdown distribution")
    ax.set_xlabel("max drawdown (USD)")
    ax.legend(fontsize=8)

    res_paths = paths["resample"]
    peaks = np.maximum.accumulate(res_paths, axis=1)
    dd_series = (res_paths - peaks).min(axis=1)
    ax = axes[1]
    ax.hist(dd_series, bins=60, color="#3d5a80", alpha=0.85)
    ax.axvline(obs_dd, color="#d1495b", lw=1.8, label=f"observed {obs_dd:,.0f}")
    ax.set_title("Resample: max drawdown distribution")
    ax.set_xlabel("max drawdown (USD)")
    ax.legend(fontsize=8)

    ax = axes[2]
    terminals = res_paths[:, -1]
    ax.hist(terminals, bins=60, color="#5b8c5a", alpha=0.85)
    ax.axvline(paths["observed"][-1], color="#d1495b", lw=1.8,
               label=f"observed {paths['observed'][-1]:,.0f}")
    ax.axvline(float(np.percentile(terminals, 5)), color="#333", ls="--", lw=1.0, label="p5")
    ax.axvline(float(np.percentile(terminals, 95)), color="#333", ls=":", lw=1.0, label="p95")
    ax.set_title("Resample: terminal equity distribution")
    ax.set_xlabel("terminal equity (USD)")
    ax.legend(fontsize=8)

    fig.suptitle(f"{label} — Monte Carlo distributions")
    fig.tight_layout()
    dist_path = out_dir / "monte_carlo_distributions.png"
    fig.savefig(dist_path, dpi=130)
    plt.close(fig)
    written["distributions"] = str(dist_path)
    return written


__all__ = [
    "MonteCarloConfig",
    "plot_fan_and_distributions",
    "run_reshuffle",
    "run_resample",
    "summarise",
]
