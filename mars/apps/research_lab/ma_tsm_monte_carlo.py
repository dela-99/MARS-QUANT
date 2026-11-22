"""
Monte Carlo Robustness Validation for MA-TSM-001 (SMA-200 Trend Following).

Methods:
1. Trade Reshuffling - Randomly reorder original trades (sequence risk)
2. Trade Resampling - Bootstrap with replacement (outcome distribution)
3. Dependence-Aware Block Bootstrap - If justified by autocorrelation

All methods use frozen strategy OOS trade data only.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

# Suppress scipy warnings for cleaner output
warnings.filterwarnings("ignore", category=RuntimeWarning)


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation."""
    n_simulations: int = 10_000
    seed: int = 42
    initial_capital: float = 10_000_000.0  # Match walkforward capital
    # Block length for block bootstrap
    block_length: int = 10
    # Drawdown thresholds to evaluate
    dd_thresholds: list[float] = field(default_factory=lambda: [0.05, 0.10, 0.15, 0.20])
    # Losing streak threshold (consecutive losing trades)
    streak_threshold: int = 5


@dataclass
class MonteCarloResults:
    """Results container for Monte Carlo simulation."""
    method: str
    n_simulations: int
    n_trades: int
    initial_capital: float

    # Terminal equity distribution
    terminal_equities: np.ndarray
    terminal_returns: np.ndarray  # as fraction of initial capital

    # Maximum drawdown distribution
    max_drawdowns: np.ndarray
    max_drawdown_pcts: np.ndarray  # as fraction

    # Losing streak distribution
    max_losing_streaks: np.ndarray

    # Percentile summaries
    equity_percentiles: dict[int, float]
    return_percentiles: dict[int, float]
    dd_percentiles: dict[int, float]
    streak_percentiles: dict[int, float]

    # Threshold probabilities
    prob_loss: float
    prob_dd_thresholds: dict[float, float]
    prob_streak_threshold: float

    # Historical observed values (for comparison)
    historical_terminal_return: float
    historical_max_dd: float
    historical_max_streak: int

    # Raw simulation paths for fan chart (sample for visualization)
    sample_paths: np.ndarray = field(default_factory=lambda: np.array([]))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "method": self.method,
            "n_simulations": self.n_simulations,
            "n_trades": self.n_trades,
            "initial_capital": self.initial_capital,
            "terminal_equity": {
                "mean": float(np.mean(self.terminal_equities)),
                "std": float(np.std(self.terminal_equities)),
                "percentiles": {str(k): float(v) for k, v in self.equity_percentiles.items()},
            },
            "terminal_return": {
                "mean": float(np.mean(self.terminal_returns)),
                "std": float(np.std(self.terminal_returns)),
                "percentiles": {str(k): float(v) for k, v in self.return_percentiles.items()},
            },
            "max_drawdown": {
                "mean": float(np.mean(self.max_drawdown_pcts)),
                "std": float(np.std(self.max_drawdown_pcts)),
                "percentiles": {str(k): float(v) for k, v in self.dd_percentiles.items()},
            },
            "max_losing_streak": {
                "mean": float(np.mean(self.max_losing_streaks)),
                "std": float(np.std(self.max_losing_streaks)),
                "percentiles": {str(k): float(v) for k, v in self.streak_percentiles.items()},
            },
            "probabilities": {
                "prob_loss": float(self.prob_loss),
                "prob_dd_thresholds": {str(k): float(v) for k, v in self.prob_dd_thresholds.items()},
                "prob_streak_threshold": float(self.prob_streak_threshold),
            },
            "historical_comparison": {
                "terminal_return": float(self.historical_terminal_return),
                "max_drawdown": float(self.historical_max_dd),
                "max_losing_streak": int(self.historical_max_streak),
            },
        }


def load_oos_trades(json_path: str | Path) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Load OOS trades from walk-forward JSON output."""
    with open(json_path) as f:
        data = json.load(f)

    pnl = np.array(data["trades_pnl"])
    returns = np.array(data["trades_returns"])
    details = data["trade_details"]

    # Add return_pct alias for test compatibility
    for d in details:
        if "return" in d and "return_pct" not in d:
            d["return_pct"] = d["return"]

    return pnl, returns, details


def compute_drawdown(equity_curve: np.ndarray) -> tuple[float, float]:
    """Compute maximum drawdown from equity curve.
    Returns (max_dd_absolute, max_dd_pct)."""
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    max_dd_pct = abs(np.min(dd)) if len(dd) > 0 else 0.0
    max_dd_abs = abs(np.min(equity_curve - peak)) if len(equity_curve) > 0 else 0.0
    return max_dd_abs, max_dd_pct


def compute_max_losing_streak(trade_returns: np.ndarray) -> int:
    """Compute maximum consecutive losing trades."""
    if len(trade_returns) == 0:
        return 0
    losing = trade_returns < 0
    streak = 0
    max_streak = 0
    for is_loss in losing:
        if is_loss:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def simulate_equity_path_from_returns(
    trade_returns: np.ndarray,
    initial_capital: float,
) -> tuple[np.ndarray, float, float, int]:
    """Simulate a single equity path from trade returns (compounding).
    Returns (equity_curve, terminal_return, max_dd_pct, max_streak)."""
    equity = np.zeros(len(trade_returns) + 1)
    equity[0] = initial_capital

    for i, ret in enumerate(trade_returns):
        equity[i + 1] = equity[i] * (1 + ret)

    terminal_return = (equity[-1] - initial_capital) / initial_capital
    _, max_dd_pct = compute_drawdown(equity)
    max_streak = compute_max_losing_streak(trade_returns)

    return equity, terminal_return, max_dd_pct, max_streak


def compute_historical_metrics(
    returns: np.ndarray,
    initial_capital: float,
) -> tuple[float, float, int]:
    """Compute historical terminal return, max DD, and max streak from returns."""
    equity, term_ret, max_dd, max_streak = simulate_equity_path_from_returns(
        returns, initial_capital
    )
    return term_ret, max_dd, max_streak


def run_reshuffling_mc(
    returns: np.ndarray,
    config: MonteCarloConfig,
    historical_terminal_return: float | None = None,
    historical_max_dd: float | None = None,
    historical_max_streak: int | None = None,
) -> MonteCarloResults:
    """Method 1: Trade Reshuffling - Randomly reorder original trades.
    Preserves all original trades, only changes sequence.
    """
    rng = np.random.default_rng(config.seed)
    n_trades = len(returns)

    # Compute historical metrics if not provided
    if historical_terminal_return is None or historical_max_dd is None or historical_max_streak is None:
        hist_term_ret, hist_max_dd, hist_max_streak = compute_historical_metrics(
            returns, config.initial_capital
        )
        historical_terminal_return = historical_terminal_return or hist_term_ret
        historical_max_dd = historical_max_dd or hist_max_dd
        historical_max_streak = historical_max_streak or hist_max_streak

    # Pre-allocate result arrays
    terminal_equities = np.zeros(config.n_simulations)
    terminal_returns = np.zeros(config.n_simulations)
    max_drawdowns = np.zeros(config.n_simulations)
    max_drawdown_pcts = np.zeros(config.n_simulations)
    max_losing_streaks = np.zeros(config.n_simulations, dtype=int)

    # Store sample paths for fan chart (first 200 simulations)
    n_sample_paths = min(200, config.n_simulations)
    sample_paths = np.zeros((n_sample_paths, n_trades + 1))

    for sim in range(config.n_simulations):
        # Reshuffle trade order
        idx = rng.permutation(n_trades)
        shuffled_returns = returns[idx]

        equity, term_ret, max_dd_pct, max_streak = simulate_equity_path_from_returns(
            shuffled_returns, config.initial_capital
        )

        terminal_equities[sim] = equity[-1]
        terminal_returns[sim] = term_ret
        max_drawdowns[sim] = max_dd_pct * equity[0]  # absolute
        max_drawdown_pcts[sim] = max_dd_pct
        max_losing_streaks[sim] = max_streak

        if sim < n_sample_paths:
            sample_paths[sim] = equity

    # Compute percentiles
    percentiles = [5, 25, 50, 75, 95]
    equity_percentiles = {p: np.percentile(terminal_equities, p) for p in percentiles}
    return_percentiles = {p: np.percentile(terminal_returns, p) for p in percentiles}
    dd_percentiles = {p: np.percentile(max_drawdown_pcts, p) for p in percentiles}
    streak_percentiles = {p: int(np.percentile(max_losing_streaks, p)) for p in percentiles}

    # Threshold probabilities
    prob_loss = np.mean(terminal_returns < 0)
    prob_dd_thresholds = {
        thresh: np.mean(max_drawdown_pcts > thresh) for thresh in config.dd_thresholds
    }
    prob_streak_threshold = np.mean(max_losing_streaks >= config.streak_threshold)

    return MonteCarloResults(
        method="Trade Reshuffling",
        n_simulations=config.n_simulations,
        n_trades=n_trades,
        initial_capital=config.initial_capital,
        terminal_equities=terminal_equities,
        terminal_returns=terminal_returns,
        max_drawdowns=max_drawdowns,
        max_drawdown_pcts=max_drawdown_pcts,
        max_losing_streaks=max_losing_streaks,
        equity_percentiles=equity_percentiles,
        return_percentiles=return_percentiles,
        dd_percentiles=dd_percentiles,
        streak_percentiles=streak_percentiles,
        prob_loss=prob_loss,
        prob_dd_thresholds=prob_dd_thresholds,
        prob_streak_threshold=prob_streak_threshold,
        historical_terminal_return=historical_terminal_return,
        historical_max_dd=historical_max_dd,
        historical_max_streak=historical_max_streak,
        sample_paths=sample_paths,
    )


def run_resampling_mc(
    returns: np.ndarray,
    config: MonteCarloConfig,
    historical_terminal_return: float | None = None,
    historical_max_dd: float | None = None,
    historical_max_streak: int | None = None,
) -> MonteCarloResults:
    """Method 2: Trade Resampling - Bootstrap with replacement.
    Assumes trades are independent and identically distributed.
    """
    rng = np.random.default_rng(config.seed + 1)  # Different seed
    n_trades = len(returns)

    # Compute historical metrics if not provided
    if historical_terminal_return is None or historical_max_dd is None or historical_max_streak is None:
        hist_term_ret, hist_max_dd, hist_max_streak = compute_historical_metrics(
            returns, config.initial_capital
        )
        historical_terminal_return = historical_terminal_return or hist_term_ret
        historical_max_dd = historical_max_dd or hist_max_dd
        historical_max_streak = historical_max_streak or hist_max_streak

    terminal_equities = np.zeros(config.n_simulations)
    terminal_returns = np.zeros(config.n_simulations)
    max_drawdowns = np.zeros(config.n_simulations)
    max_drawdown_pcts = np.zeros(config.n_simulations)
    max_losing_streaks = np.zeros(config.n_simulations, dtype=int)

    n_sample_paths = min(200, config.n_simulations)
    sample_paths = np.zeros((n_sample_paths, n_trades + 1))

    for sim in range(config.n_simulations):
        # Resample with replacement
        idx = rng.integers(0, n_trades, size=n_trades)
        resampled_returns = returns[idx]

        equity, term_ret, max_dd_pct, max_streak = simulate_equity_path_from_returns(
            resampled_returns, config.initial_capital
        )

        terminal_equities[sim] = equity[-1]
        terminal_returns[sim] = term_ret
        max_drawdowns[sim] = max_dd_pct * equity[0]
        max_drawdown_pcts[sim] = max_dd_pct
        max_losing_streaks[sim] = max_streak

        if sim < n_sample_paths:
            sample_paths[sim] = equity

    percentiles = [5, 25, 50, 75, 95]
    equity_percentiles = {p: np.percentile(terminal_equities, p) for p in percentiles}
    return_percentiles = {p: np.percentile(terminal_returns, p) for p in percentiles}
    dd_percentiles = {p: np.percentile(max_drawdown_pcts, p) for p in percentiles}
    streak_percentiles = {p: int(np.percentile(max_losing_streaks, p)) for p in percentiles}

    prob_loss = np.mean(terminal_returns < 0)
    prob_dd_thresholds = {
        thresh: np.mean(max_drawdown_pcts > thresh) for thresh in config.dd_thresholds
    }
    prob_streak_threshold = np.mean(max_losing_streaks >= config.streak_threshold)

    return MonteCarloResults(
        method="Trade Resampling (Bootstrap)",
        n_simulations=config.n_simulations,
        n_trades=n_trades,
        initial_capital=config.initial_capital,
        terminal_equities=terminal_equities,
        terminal_returns=terminal_returns,
        max_drawdowns=max_drawdowns,
        max_drawdown_pcts=max_drawdown_pcts,
        max_losing_streaks=max_losing_streaks,
        equity_percentiles=equity_percentiles,
        return_percentiles=return_percentiles,
        dd_percentiles=dd_percentiles,
        streak_percentiles=streak_percentiles,
        prob_loss=prob_loss,
        prob_dd_thresholds=prob_dd_thresholds,
        prob_streak_threshold=prob_streak_threshold,
        historical_terminal_return=historical_terminal_return,
        historical_max_dd=historical_max_dd,
        historical_max_streak=historical_max_streak,
        sample_paths=sample_paths,
    )


def check_dependence(trade_returns: np.ndarray, max_lag: int = 20) -> dict[str, Any]:
    """Check for serial dependence in trade returns.
    Returns dict with autocorrelation, volatility clustering, and trade clustering metrics.
    """
    n = len(trade_returns)
    if n < max_lag + 10:
        return {"warning": "Insufficient data for dependence analysis"}

    # 1. Autocorrelation of returns
    acf = []
    for lag in range(1, max_lag + 1):
        if n > lag:
            corr = np.corrcoef(trade_returns[:-lag], trade_returns[lag:])[0, 1]
            acf.append(corr if not np.isnan(corr) else 0.0)

    # Ljung-Box test for autocorrelation
    from scipy.stats import chi2
    lb_stat = n * (n + 2) * sum(a**2 / (n - i) for i, a in enumerate(acf, 1))
    lb_pval = 1 - chi2.cdf(lb_stat, max_lag)

    # 2. Volatility clustering - autocorrelation of squared returns
    sq_returns = trade_returns**2
    acf_sq = []
    for lag in range(1, max_lag + 1):
        if n > lag:
            corr = np.corrcoef(sq_returns[:-lag], sq_returns[lag:])[0, 1]
            acf_sq.append(corr if not np.isnan(corr) else 0.0)

    # 3. Trade clustering - check if wins/losses cluster
    # Runs test for randomness of win/loss sequence
    wins = (trade_returns > 0).astype(int)
    n_wins = wins.sum()
    n_losses = n - n_wins
    if n_wins > 0 and n_losses > 0:
        # Expected runs under randomness
        expected_runs = 2 * n_wins * n_losses / n + 1
        # Actual runs
        runs = 1 + np.sum(wins[:-1] != wins[1:])
        runs_z = (runs - expected_runs) / np.sqrt(
            2 * n_wins * n_losses * (2 * n_wins * n_losses - n) / (n**2 * (n - 1))
        )
        runs_pval = 2 * (1 - stats.norm.cdf(abs(runs_z)))
    else:
        runs = expected_runs = runs_z = runs_pval = np.nan

    # 4. Market regime dependence - check correlation with rolling volatility
    window = min(50, n // 4)
    if window > 10:
        roll_vol = pd.Series(trade_returns).rolling(window).std().dropna().values
        if len(roll_vol) > 10:
            vol_return_corr = np.corrcoef(
                trade_returns[-len(roll_vol):], roll_vol
            )[0, 1] if len(roll_vol) > 10 else np.nan
        else:
            vol_return_corr = np.nan
    else:
        vol_return_corr = np.nan

    return {
            "n_trades": n,
            "ljung_box_p": float(lb_pval),
            "runs_test_p": float(runs_pval) if not np.isnan(runs_pval) else np.nan,
            "dependence_detected": bool(
                lb_pval < 0.05 or
                (not np.isnan(runs_pval) and runs_pval < 0.05)
            ),
            "autocorrelation": {
                "acf": acf,
                "max_abs_acf": max(abs(a) for a in acf) if acf else 0,
                "ljung_box_stat": float(lb_stat),
                "ljung_box_pval": float(lb_pval),
                "significant_autocorr": lb_pval < 0.05,
            },
            "volatility_clustering": {
                "acf_squared": acf_sq,
                "max_abs_acf_sq": max(abs(a) for a in acf_sq) if acf_sq else 0,
            },
            "trade_clustering": {
                "runs_test_z": float(runs_z) if not np.isnan(runs_z) else np.nan,
                "runs_test_pval": float(runs_pval) if not np.isnan(runs_pval) else np.nan,
                "significant_clustering": runs_pval < 0.05 if not np.isnan(runs_pval) else False,
            },
            "regime_dependence": {
                "vol_return_corr": float(vol_return_corr) if not np.isnan(vol_return_corr) else np.nan,
            },
        }


def run_block_bootstrap_mc(
    returns: np.ndarray,
    config: MonteCarloConfig,
    historical_terminal_return: float | None = None,
    historical_max_dd: float | None = None,
    historical_max_streak: int | None = None,
    block_length: int | None = None,
) -> MonteCarloResults:
    """Method 3: Dependence-Aware Block Bootstrap (Moving Block Bootstrap).
    Resamples blocks of consecutive trades to preserve local dependence structure.
    """
    # Use config.block_length if not explicitly provided
    if block_length is None:
        block_length = config.block_length

    rng = np.random.default_rng(config.seed + 2)
    n_trades = len(returns)

    if block_length >= n_trades:
        block_length = max(1, n_trades // 4)

    n_blocks = int(np.ceil(n_trades / block_length))

    # Compute historical metrics if not provided
    if historical_terminal_return is None or historical_max_dd is None or historical_max_streak is None:
        hist_term_ret, hist_max_dd, hist_max_streak = compute_historical_metrics(
            returns, config.initial_capital
        )
        historical_terminal_return = historical_terminal_return or hist_term_ret
        historical_max_dd = historical_max_dd or hist_max_dd
        historical_max_streak = historical_max_streak or hist_max_streak

    terminal_equities = np.zeros(config.n_simulations)
    terminal_returns = np.zeros(config.n_simulations)
    max_drawdowns = np.zeros(config.n_simulations)
    max_drawdown_pcts = np.zeros(config.n_simulations)
    max_losing_streaks = np.zeros(config.n_simulations, dtype=int)

    n_sample_paths = min(200, config.n_simulations)
    sample_paths = np.zeros((n_sample_paths, n_trades + 1))

    for sim in range(config.n_simulations):
        # Moving block bootstrap: randomly select blocks with replacement
        block_starts = rng.integers(0, n_trades - block_length + 1, size=n_blocks)
        resampled_returns_list = []

        for start in block_starts:
            end = min(start + block_length, n_trades)
            resampled_returns_list.extend(returns[start:end])

        # Truncate to exactly n_trades
        resampled_returns = np.array(resampled_returns_list[:n_trades])

        equity, term_ret, max_dd_pct, max_streak = simulate_equity_path_from_returns(
            resampled_returns, config.initial_capital
        )

        terminal_equities[sim] = equity[-1]
        terminal_returns[sim] = term_ret
        max_drawdowns[sim] = max_dd_pct * equity[0]
        max_drawdown_pcts[sim] = max_dd_pct
        max_losing_streaks[sim] = max_streak

        if sim < n_sample_paths:
            sample_paths[sim] = equity

    percentiles = [5, 25, 50, 75, 95]
    equity_percentiles = {p: np.percentile(terminal_equities, p) for p in percentiles}
    return_percentiles = {p: np.percentile(terminal_returns, p) for p in percentiles}
    dd_percentiles = {p: np.percentile(max_drawdown_pcts, p) for p in percentiles}
    streak_percentiles = {p: int(np.percentile(max_losing_streaks, p)) for p in percentiles}

    prob_loss = np.mean(terminal_returns < 0)
    prob_dd_thresholds = {
        thresh: np.mean(max_drawdown_pcts > thresh) for thresh in config.dd_thresholds
    }
    prob_streak_threshold = np.mean(max_losing_streaks >= config.streak_threshold)

    return MonteCarloResults(
        method=f"Block Bootstrap (block_len={block_length})",
        n_simulations=config.n_simulations,
        n_trades=n_trades,
        initial_capital=config.initial_capital,
        terminal_equities=terminal_equities,
        terminal_returns=terminal_returns,
        max_drawdowns=max_drawdowns,
        max_drawdown_pcts=max_drawdown_pcts,
        max_losing_streaks=max_losing_streaks,
        equity_percentiles=equity_percentiles,
        return_percentiles=return_percentiles,
        dd_percentiles=dd_percentiles,
        streak_percentiles=streak_percentiles,
        prob_loss=prob_loss,
        prob_dd_thresholds=prob_dd_thresholds,
        prob_streak_threshold=prob_streak_threshold,
        historical_terminal_return=historical_terminal_return,
        historical_max_dd=historical_max_dd,
        historical_max_streak=historical_max_streak,
        sample_paths=sample_paths,
    )


def run_all_monte_carlo(
    trades_json_path: str | Path,
    config: MonteCarloConfig | None = None,
) -> tuple[
    MonteCarloResults,
    MonteCarloResults,
    MonteCarloResults | None,
    dict[str, Any],
]:
    """Run all three Monte Carlo methods and return results plus dependence analysis."""
    if config is None:
        config = MonteCarloConfig()

    # Load trade data
    pnl, returns, details = load_oos_trades(trades_json_path)

    # The walkforward used 10M initial capital per window (vectorbt cash_sharing=False behavior)
    # Use 10M to match walkforward scaling
    walkforward_initial_capital = 10_000_000.0

    # Compute historical metrics from original sequence on walkforward capital
    hist_equity, hist_term_ret, hist_max_dd, hist_max_streak = simulate_equity_path_from_returns(
        returns, walkforward_initial_capital
    )

    print(f"Loaded {len(pnl)} OOS trades")
    print(f"Walkforward initial capital: ${walkforward_initial_capital:,.0f}")
    print(f"Historical terminal return: {hist_term_ret:.4f} ({hist_term_ret*100:.2f}%)")
    print(f"Historical max drawdown: {hist_max_dd:.4f} ({hist_max_dd*100:.2f}%)")
    print(f"Historical max losing streak: {hist_max_streak}")

    # Check dependence
    print("\nChecking for serial dependence...")
    dependence = check_dependence(returns)
    print(f"  Ljung-Box p-value: {dependence['ljung_box_p']:.4f}")
    print(f"  Runs test p-value: {dependence['runs_test_p']:.4f}")
    print(f"  Dependence detected: {dependence['dependence_detected']}")

    # Method 1: Reshuffling
    print("\nRunning Method 1: Trade Reshuffling...")
    reshuffle_results = run_reshuffling_mc(
        returns, config
    )

    # Method 2: Resampling
    print("Running Method 2: Trade Resampling (Bootstrap)...")
    resample_results = run_resampling_mc(
        returns, config
    )

    # Method 3: Block Bootstrap (if dependence detected or always for comparison)
    print("Running Method 3: Block Bootstrap...")
    # Use block length based on autocorrelation decay or fixed
    block_results = run_block_bootstrap_mc(
        returns, config
    )

    return reshuffle_results, resample_results, block_results, dependence


def _json_safe(obj: Any) -> Any:
    """Convert numpy types to JSON-serializable Python types."""
    if isinstance(obj, (np.integer, np.floating)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_json_safe(v) for v in obj)
    return obj


def save_results(
    reshuffle: MonteCarloResults,
    resample: MonteCarloResults,
    block: MonteCarloResults | None,
    dependence: dict,
    output_dir: Path,
):
    """Save all results to JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "Trade Reshuffling": reshuffle.to_dict(),
        "Trade Resampling (Bootstrap)": resample.to_dict(),
        "Block Bootstrap": block.to_dict() if block else None,
        "dependence_analysis": _json_safe(dependence),
    }

    with open(output_dir / "monte_carlo_results.json", "w") as f:
        json.dump(data, f, indent=2)

    print(f"Results saved to {output_dir / 'monte_carlo_results.json'}")


if __name__ == "__main__":
    import sys

    trades_path = "reports/walkforward/oos_trades_for_mc.json"
    config = MonteCarloConfig(n_simulations=10_000, seed=42)

    reshuffle, resample, block, dependence = run_all_monte_carlo(trades_path, config)

    output_dir = Path("reports/monte_carlo")
    save_results(reshuffle, resample, block, dependence, output_dir)

    # Generate visualizations
    from mars.apps.research_lab.ma_tsm_monte_carlo_viz import generate_all_charts
    generate_all_charts(reshuffle, resample, block, output_dir)

    print("\n=== SUMMARY ===")
    for name, res in [("Reshuffling", reshuffle), ("Resampling", resample), ("Block Bootstrap", block)]:
        if res:
            print(f"\n{name}:")
            print(f"  Median terminal return: {res.return_percentiles[50]*100:.2f}%")
            print(f"  5th percentile return: {res.return_percentiles[5]*100:.2f}%")
            print(f"  Median max DD: {res.dd_percentiles[50]*100:.2f}%")
            print(f"  95th percentile max DD: {res.dd_percentiles[95]*100:.2f}%")
            print(f"  P(loss): {res.prob_loss:.2%}")
            print(f"  P(DD>10%): {res.prob_dd_thresholds.get(0.10, 0):.2%}")