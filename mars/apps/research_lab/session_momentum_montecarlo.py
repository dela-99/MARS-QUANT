"""
M.A.R.S. Session Momentum Monte Carlo Validation: XAU-SESSION-MOM-001

Two experiments per spec Section 12 (Paper 15 methodology):
1. Reshuffle (Sequence Risk): Permute trade order 10,000× → equity fan, DD distribution
2. Resample (Outcome Dispersion): Bootstrap trades 10,000× → terminal equity, DD distribution

Assumptions (recorded):
- i.i.d. trade outcomes (known false for session momentum — upper bound on robustness)
- Position sizing proportional to equity
- Costs embedded in observed net P&L (not re-sampled)
- No regime/clustering modelled
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mars.libs.utils.paths import ProjectPaths


# ============================================================================
# Configuration
# ============================================================================

@dataclass(frozen=True)
class MonteCarloConfig:
    """Monte Carlo simulation configuration."""

    n_simulations: int = 10_000
    seed: int = 20261125
    equity: float = 10_000.0
    risk_fraction: float = 0.01

    # Output
    output_dir: str = "reports/programme_01/session_momentum_001/mc"


# ============================================================================
# Reshuffle Experiment (Sequence Risk)
# ============================================================================

def run_reshuffle(
    trades: pd.DataFrame,
    config: MonteCarloConfig,
) -> Dict[str, Any]:
    """
    Reshuffle Experiment: Permute trade sequence to assess sequence risk.

    Each simulation:
    1. Randomly permute the trade order
    2. Recompute equity curve with compounding (position size ∝ equity)
    3. Record terminal equity, max DD, DD duration
    """
    np.random.seed(config.seed)

    net_pnls = trades["net_pnl"].values
    gross_pnls = trades["gross_pnl"].values
    lots = trades["lots"].values
    stop_distances = trades["stop_distance"].values if "stop_distance" in trades.columns else np.full(len(trades), 200.0 * 0.001)

    n_trades = len(net_pnls)
    if n_trades == 0:
        return {"error": "No trades to reshuffle"}

    # Observed metrics
    observed_equity = config.equity
    observed_curve = [observed_equity]
    for pnl in net_pnls:
        observed_equity += pnl
        observed_curve.append(observed_equity)
    observed_curve = np.array(observed_curve)
    observed_terminal = observed_curve[-1]
    observed_dd = compute_max_dd(observed_curve)
    observed_dd_duration = compute_max_dd_duration(observed_curve)

    # Simulations
    sim_terminal = np.zeros(config.n_simulations)
    sim_max_dd = np.zeros(config.n_simulations)
    sim_max_dd_dur = np.zeros(config.n_simulations, dtype=int)
    sim_equity_curves = []  # Store subset for fan chart

    for s in range(config.n_simulations):
        # Permute trade indices
        perm_idx = np.random.permutation(n_trades)

        equity = config.equity
        curve = [equity]
        peak = equity
        max_dd = 0.0
        dd_dur = 0
        max_dd_dur = 0
        in_dd = False

        for idx in perm_idx:
            # Position size proportional to equity (compounding)
            # Scale the P&L by equity ratio
            scale = equity / config.equity
            pnl = net_pnls[idx] * scale

            equity += pnl
            curve.append(equity)

            # Track drawdown
            if equity > peak:
                peak = equity
                in_dd = False
                dd_dur = 0
            else:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd
                if not in_dd:
                    in_dd = True
                    dd_dur = 1
                else:
                    dd_dur += 1
                if dd_dur > max_dd_dur:
                    max_dd_dur = dd_dur

        sim_terminal[s] = equity
        sim_max_dd[s] = max_dd
        sim_max_dd_dur[s] = max_dd_dur

        # Store subset for fan chart (every 100th sim)
        if s % 100 == 0 and len(sim_equity_curves) < 200:
            sim_equity_curves.append(np.array(curve))

    return {
        "experiment": "reshuffle",
        "n_simulations": config.n_simulations,
        "observed": {
            "terminal_equity": float(observed_terminal),
            "max_drawdown": float(observed_dd),
            "max_dd_duration": int(observed_dd_duration),
        },
        "simulated": {
            "terminal_equity": {
                "mean": float(sim_terminal.mean()),
                "std": float(sim_terminal.std()),
                "percentiles": {f"p{p}": float(np.percentile(sim_terminal, p)) for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]},
            },
            "max_drawdown": {
                "mean": float(sim_max_dd.mean()),
                "std": float(sim_max_dd.std()),
                "percentiles": {f"p{p}": float(np.percentile(sim_max_dd, p)) for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]},
            },
            "max_dd_duration": {
                "mean": float(sim_max_dd_dur.mean()),
                "std": float(sim_max_dd_dur.std()),
                "percentiles": {f"p{p}": int(np.percentile(sim_max_dd_dur, p)) for p in [50, 75, 90, 95, 99]},
            },
        },
        "p_values": {
            "terminal_equity_lt_p05": float((sim_terminal < np.percentile(sim_terminal, 5)).mean()),
            "max_dd_gt_p95": float((sim_max_dd > np.percentile(sim_max_dd, 95)).mean()),
        },
        "fan_curves": sim_equity_curves[:50],  # First 50 for plotting
        "assumptions": [
            "i.i.d. trade outcomes (known false for session momentum - upper bound on robustness)",
            "Position sizing proportional to equity",
            "Costs embedded in observed net P&L (not re-sampled)",
            "No regime/clustering modelled",
        ],
    }


# ============================================================================
# Resample Experiment (Outcome Dispersion)
# ============================================================================

def run_resample(
    trades: pd.DataFrame,
    config: MonteCarloConfig,
) -> Dict[str, Any]:
    """
    Resample Experiment: Bootstrap trade outcomes to assess outcome dispersion.

    Each simulation:
    1. Sample n_trades with replacement from observed net P&Ls
    2. Recompute equity curve with compounding
    3. Record terminal equity, max DD
    """
    np.random.seed(config.seed + 1)  # Different seed

    net_pnls = trades["net_pnl"].values
    n_trades = len(net_pnls)
    if n_trades == 0:
        return {"error": "No trades to resample"}

    # Observed metrics
    observed_equity = config.equity
    observed_curve = [observed_equity]
    for pnl in net_pnls:
        observed_equity += pnl
        observed_curve.append(observed_equity)
    observed_curve = np.array(observed_curve)
    observed_terminal = observed_curve[-1]
    observed_dd = compute_max_dd(observed_curve)

    # Simulations
    sim_terminal = np.zeros(config.n_simulations)
    sim_max_dd = np.zeros(config.n_simulations)
    sim_equity_curves = []

    for s in range(config.n_simulations):
        # Bootstrap sample
        sample_idx = np.random.choice(n_trades, size=n_trades, replace=True)
        sample_pnls = net_pnls[sample_idx]

        equity = config.equity
        curve = [equity]
        peak = equity
        max_dd = 0.0

        for pnl in sample_pnls:
            scale = equity / config.equity
            equity += pnl * scale
            curve.append(equity)

            if equity > peak:
                peak = equity
            else:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd

        sim_terminal[s] = equity
        sim_max_dd[s] = max_dd

        if s % 100 == 0 and len(sim_equity_curves) < 200:
            sim_equity_curves.append(np.array(curve))

    return {
        "experiment": "resample",
        "n_simulations": config.n_simulations,
        "observed": {
            "terminal_equity": float(observed_terminal),
            "max_drawdown": float(observed_dd),
        },
        "simulated": {
            "terminal_equity": {
                "mean": float(sim_terminal.mean()),
                "std": float(sim_terminal.std()),
                "percentiles": {f"p{p}": float(np.percentile(sim_terminal, p)) for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]},
            },
            "max_drawdown": {
                "mean": float(sim_max_dd.mean()),
                "std": float(sim_max_dd.std()),
                "percentiles": {f"p{p}": float(np.percentile(sim_max_dd, p)) for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]},
            },
        },
        "p_values": {
            "terminal_equity_lt_p05": float((sim_terminal < np.percentile(sim_terminal, 5)).mean()),
            "max_dd_gt_p95": float((sim_max_dd > np.percentile(sim_max_dd, 95)).mean()),
        },
        "fan_curves": sim_equity_curves[:50],
        "assumptions": [
            "i.i.d. trade outcomes (known false for session momentum - upper bound on robustness)",
            "Position sizing proportional to equity",
            "Costs embedded in observed net P&L (not re-sampled)",
            "No regime/clustering modelled",
        ],
    }


def compute_max_dd(equity_curve: np.ndarray) -> float:
    """Compute maximum drawdown from equity curve."""
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    return float(dd.min())


def compute_max_dd_duration(equity_curve: np.ndarray) -> int:
    """Compute maximum drawdown duration in periods."""
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    in_dd = dd < 0
    if not in_dd.any():
        return 0
    # Find consecutive True runs
    dd_groups = (in_dd != np.roll(in_dd, 1)).cumsum()
    # Use numpy to find max consecutive True
    max_dur = 0
    current_dur = 0
    for val in in_dd:
        if val:
            current_dur += 1
            max_dur = max(max_dur, current_dur)
        else:
            current_dur = 0
    return int(max_dur)


# ============================================================================
# Random Signal Baseline (Monte Carlo)
# ============================================================================

def run_random_signal_baseline(
    trades: pd.DataFrame,
    config: MonteCarloConfig,
) -> Dict[str, Any]:
    """
    Random Signal Baseline: Permute signal sequence to establish chance performance.

    This creates the "Random Signal" baseline from spec Section 10.3.
    """
    np.random.seed(config.seed + 2)

    net_pnls = trades["net_pnl"].values
    n_trades = len(net_pnls)

    # Simulate random signal: each session has p(signal=1) = observed signal rate
    signal_rate = 1.0  # We're permuting the actual trades, so rate is fixed by n_trades

    sim_terminal = np.zeros(config.n_simulations)
    sim_sharpe = np.zeros(config.n_simulations)
    sim_max_dd = np.zeros(config.n_simulations)

    for s in range(config.n_simulations):
        # Randomly decide which sessions get a signal (same n_trades as observed)
        # This is equivalent to shuffling the trade outcomes
        perm_idx = np.random.permutation(n_trades)

        equity = config.equity
        curve = [equity]
        peak = equity
        max_dd = 0.0

        for idx in perm_idx:
            scale = equity / config.equity
            equity += net_pnls[idx] * scale
            curve.append(equity)

            if equity > peak:
                peak = equity
            else:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd

        sim_terminal[s] = equity
        sim_max_dd[s] = max_dd

        # Sharpe
        returns = np.diff(curve) / curve[:-1]
        if len(returns) > 1 and returns.std() > 0:
            sim_sharpe[s] = returns.mean() / returns.std() * np.sqrt(252 * 288)

    return {
        "experiment": "random_signal_baseline",
        "n_simulations": config.n_simulations,
        "terminal_equity": {
            "mean": float(sim_terminal.mean()),
            "std": float(sim_terminal.std()),
            "percentiles": {f"p{p}": float(np.percentile(sim_terminal, p)) for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]},
        },
        "sharpe": {
            "mean": float(sim_sharpe.mean()),
            "std": float(sim_sharpe.std()),
            "percentiles": {f"p{p}": float(np.percentile(sim_sharpe, p)) for p in [5, 25, 50, 75, 95]},
        },
        "max_drawdown": {
            "mean": float(sim_max_dd.mean()),
            "std": float(sim_max_dd.std()),
            "percentiles": {f"p{p}": float(np.percentile(sim_max_dd, p)) for p in [5, 25, 50, 75, 95]},
        },
    }


# ============================================================================
# Combined MC Runner
# ============================================================================

def run_monte_carlo(
    trades_path: str,
    config: Optional[MonteCarloConfig] = None,
) -> Dict[str, Any]:
    """Run both Monte Carlo experiments and random signal baseline."""
    config = config or MonteCarloConfig()
    paths = ProjectPaths.from_root()

    print("=" * 70)
    print("M.A.R.S. Session Momentum Monte Carlo Validation")
    print("=" * 70)

    # Load trades
    print(f"\n[1/4] Loading trades from {trades_path}...")
    trades = pd.read_csv(paths.root / trades_path)
    print(f"      {len(trades)} trades loaded")

    # Experiment 1: Reshuffle
    print(f"\n[2/4] Running Reshuffle Experiment ({config.n_simulations:,} sims)...")
    reshuffle_results = run_reshuffle(trades, config)
    print(f"      Observed Terminal: ${reshuffle_results['observed']['terminal_equity']:.2f}")
    print(f"      Simulated Mean:    ${reshuffle_results['simulated']['terminal_equity']['mean']:.2f}")
    print(f"      Observed Max DD:   {reshuffle_results['observed']['max_drawdown']:.2%}")
    print(f"      Simulated Mean DD: {reshuffle_results['simulated']['max_drawdown']['mean']:.2%}")

    # Experiment 2: Resample
    print(f"\n[3/4] Running Resample Experiment ({config.n_simulations:,} sims)...")
    resample_results = run_resample(trades, config)
    print(f"      Observed Terminal: ${resample_results['observed']['terminal_equity']:.2f}")
    print(f"      Simulated Mean:    ${resample_results['simulated']['terminal_equity']['mean']:.2f}")
    print(f"      Observed Max DD:   {resample_results['observed']['max_drawdown']:.2%}")
    print(f"      Simulated Mean DD: {resample_results['simulated']['max_drawdown']['mean']:.2%}")

    # Experiment 3: Random Signal Baseline
    print(f"\n[4/4] Running Random Signal Baseline ({config.n_simulations:,} sims)...")
    random_results = run_random_signal_baseline(trades, config)
    print(f"      Random Mean Terminal: ${random_results['terminal_equity']['mean']:.2f}")
    print(f"      Random Mean Sharpe:   {random_results['sharpe']['mean']:.2f}")

    # Compile results
    results = {
        "strategy_id": "XAU-SESSION-MOM-001",
        "trades_source": trades_path,
        "config": {
            "n_simulations": config.n_simulations,
            "seed": config.seed,
            "equity": config.equity,
            "risk_fraction": config.risk_fraction,
        },
        "reshuffle": reshuffle_results,
        "resample": resample_results,
        "random_signal_baseline": random_results,
        "falsification_check": check_mc_falsification(reshuffle_results, resample_results),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save
    save_mc_results(results, config.output_dir)

    print("\n" + "=" * 70)
    print("MONTE CARLO VALIDATION COMPLETE")
    print("=" * 70)
    print(f"Results saved to: {config.output_dir}")

    return results


def check_mc_falsification(reshuffle: Dict, resample: Dict) -> Dict[str, Any]:
    """Check MC falsification criteria from spec Section 13."""
    checks = {
        "observed_dd_gt_p95_reshuffle": reshuffle["observed"]["max_drawdown"] >
            reshuffle["simulated"]["max_drawdown"]["percentiles"]["p95"],
        "observed_terminal_lt_p05_resample": resample["observed"]["terminal_equity"] <
            resample["simulated"]["terminal_equity"]["percentiles"]["p5"],
    }
    all_pass = not any(checks.values())  # Both should be FALSE to pass

    return {
        "checks": checks,
        "all_pass": all_pass,
        "verdict": "ADVANCES" if all_pass else "REJECTED (MC)",
        "notes": "Observed DD > p95 of reshuffle = sequence-dependent. "
                 "Observed terminal < p05 of resample = outcome unlikely under i.i.d."
    }


def save_mc_results(results: Dict[str, Any], output_dir: str) -> None:
    """Save MC results as JSON and report."""
    paths = ProjectPaths.from_root()
    out_path = paths.root / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    import json
    json_path = out_path / "mc_results.json"
    serializable = make_serializable(results)
    json_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    # Report
    report_path = out_path / "mc_report.md"
    report = generate_mc_report(results)
    report_path.write_text(report, encoding="utf-8")


def make_serializable(obj: Any) -> Any:
    """Convert numpy/pandas types to JSON-serializable."""
    if isinstance(obj, (np.integer, np.floating)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict()
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(v) for v in obj]
    if isinstance(obj, (datetime, pd.Timestamp)):
        return obj.isoformat()
    return obj


def generate_mc_report(results: Dict[str, Any]) -> str:
    """Generate human-readable MC report."""
    lines = [
        "# M.A.R.S. Session Momentum Monte Carlo Report",
        f"**Strategy:** {results['strategy_id']}",
        f"**Trades Source:** {results['trades_source']}",
        f"**Config:** {results['config']['n_simulations']:,} sims, seed={results['config']['seed']}, equity=${results['config']['equity']:.0f}",
        f"**Date:** {results['timestamp']}",
        "",
        "## Assumptions (Recorded)",
    ]
    for a in results["reshuffle"]["assumptions"]:
        lines.append(f"- {a}")

    lines.extend(["", "## Reshuffle Experiment (Sequence Risk)"])
    r = results["reshuffle"]
    lines.extend([
        f"- Observed Terminal Equity: ${r['observed']['terminal_equity']:.2f}",
        f"- Simulated Mean: ${r['simulated']['terminal_equity']['mean']:.2f} (σ=${r['simulated']['terminal_equity']['std']:.2f})",
        f"- Observed Max DD: {r['observed']['max_drawdown']:.2%}",
        f"- Simulated Mean Max DD: {r['simulated']['max_drawdown']['mean']:.2%} (σ={r['simulated']['max_drawdown']['std']:.2%})",
        "",
        "### Percentiles (Terminal Equity)",
    ])
    for p, v in r['simulated']['terminal_equity']['percentiles'].items():
        lines.append(f"- {p}: ${v:.2f}")

    lines.extend(["", "### Percentiles (Max Drawdown)"])
    for p, v in r['simulated']['max_drawdown']['percentiles'].items():
        lines.append(f"- {p}: {v:.2%}")

    lines.extend(["", "## Resample Experiment (Outcome Dispersion)"])
    r = results["resample"]
    lines.extend([
        f"- Observed Terminal Equity: ${r['observed']['terminal_equity']:.2f}",
        f"- Simulated Mean: ${r['simulated']['terminal_equity']['mean']:.2f} (σ=${r['simulated']['terminal_equity']['std']:.2f})",
        f"- Observed Max DD: {r['observed']['max_drawdown']:.2%}",
        f"- Simulated Mean Max DD: {r['simulated']['max_drawdown']['mean']:.2%} (σ={r['simulated']['max_drawdown']['std']:.2%})",
    ])

    lines.extend(["", "## Random Signal Baseline"])
    r = results["random_signal_baseline"]
    lines.extend([
        f"- Mean Terminal Equity: ${r['terminal_equity']['mean']:.2f}",
        f"- Mean Sharpe: {r['sharpe']['mean']:.2f}",
        f"- Mean Max DD: {r['max_drawdown']['mean']:.2%}",
    ])

    lines.extend(["", "## Falsification Criteria (MC)"])
    fc = results["falsification_check"]
    for check, passed in fc["checks"].items():
        status = "❌ FAIL (Falsified)" if passed else "✅ PASS"
        lines.append(f"- {check}: {status}")
    lines.append(f"\n**Overall Verdict: {fc['verdict']}**")
    lines.append(f"*{fc['notes']}*")

    return "\n".join(lines)


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run XAU-SESSION-MOM-001 Monte Carlo Validation")
    parser.add_argument("--trades", type=str, required=True, help="Path to trades CSV")
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--n_sims", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--output", type=str, default="reports/programme_01/session_momentum_001/mc")
    args = parser.parse_args()

    config = MonteCarloConfig(
        n_simulations=args.n_sims,
        seed=args.seed,
        equity=args.equity,
        output_dir=args.output,
    )
    run_monte_carlo(args.trades, config)