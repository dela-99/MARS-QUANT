#!/usr/bin/env python
"""
Sensitivity analysis for DONCHIAN-001.

Runs:
1. Lookback sensitivity (entry: 20, 55, 100; exit: 10, 20, 55)
2. Cost sensitivity (spread: 0.5, 1.0, 2.0; commission: 0.0, 0.5, 1.0; slippage: 0.0, 0.5, 1.0)
"""

import json
from pathlib import Path
import pandas as pd

from mars.apps.research_lab.donchian_trend_vbt import (
    DonchianConfig,
    CostModel,
    ProjectPaths,
    load_and_validate_data,
    compute_donchian_channels,
    run_vectorbt_portfolio,
    compute_metrics,
    time_series_split,
)

# Suppress timezone warning
import warnings
warnings.filterwarnings("ignore", message="Converting to PeriodArray")


def run_config(config: DonchianConfig, df: pd.DataFrame, tag: str) -> dict:
    """Run a single configuration and return key metrics."""
    df_with_signals = compute_donchian_channels(df, config.entry_lookback, config.exit_lookback)
    split = time_series_split(
        df_with_signals.index,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
    )
    pf = run_vectorbt_portfolio(df_with_signals, config)
    metrics = compute_metrics(pf, config, df_with_signals)
    return {
        "tag": tag,
        "entry_lookback": config.entry_lookback,
        "exit_lookback": config.exit_lookback,
        "spread_pips": config.cost_model.spread_pips,
        "commission_per_lot": config.cost_model.commission_per_lot,
        "slippage_pips": config.cost_model.slippage_pips,
        "n_trades": metrics["n_trades"],
        "win_rate_net": metrics["win_rate_net"],
        "expectancy_net_usd": metrics["expectancy_net_usd"],
        "profit_factor_net": metrics["profit_factor_net"],
        "total_return_net": metrics["total_return_net"],
        "annualized_return_net": metrics["annualized_return_net"],
        "sharpe_net": metrics["sharpe_net"],
        "sortino_net": metrics["sortino_net"],
        "max_drawdown_net": metrics["max_drawdown_net"],
        "calmar_net": metrics["calmar_net"],
    }


def main():
    paths = ProjectPaths.from_root()
    base_config = DonchianConfig(
        symbol="XAUUSD",
        timeframe="h1",
        data_path=None,
        entry_lookback=55,
        exit_lookback=20,
        position_size_pct=1.0,
        max_leverage=1.0,
        cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
        train_ratio=0.7,
        val_ratio=0.15,
        test_ratio=0.15,
        seed=42,
    )

    print("Loading data...")
    df = load_and_validate_data(base_config, paths)
    print(f"Loaded {len(df)} bars")

    results = []

    # 1. Lookback sensitivity
    print("\n=== LOOKBACK SENSITIVITY ===")
    entry_lookbacks = [20, 55, 100]
    exit_lookbacks = [10, 20, 55]

    for entry_lb in entry_lookbacks:
        for exit_lb in exit_lookbacks:
            if entry_lb <= exit_lb:
                continue  # Entry lookback should be >= exit lookback for trend following
            config = DonchianConfig(
                symbol="XAUUSD",
                timeframe="h1",
                data_path=None,
                entry_lookback=entry_lb,
                exit_lookback=exit_lb,
                position_size_pct=1.0,
                max_leverage=1.0,
                cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
                train_ratio=0.7,
                val_ratio=0.15,
                test_ratio=0.15,
                seed=42,
            )
            tag = f"lookback_e{entry_lb}_x{exit_lb}"
            print(f"Running {tag}...")
            result = run_config(config, df, tag)
            results.append(result)
            print(f"  Trades: {result['n_trades']}, Net PF: {result['profit_factor_net']:.2f}, "
                  f"Ann.Ret: {result['annualized_return_net']:.2%}, Sharpe: {result['sharpe_net']:.2f}, "
                  f"MaxDD: {result['max_drawdown_net']:.2%}")

    # 2. Cost sensitivity
    print("\n=== COST SENSITIVITY ===")
    spread_values = [0.5, 1.0, 2.0]
    commission_values = [0.0, 0.5, 1.0]
    slippage_values = [0.0, 0.5, 1.0]

    for spread in spread_values:
        for comm in commission_values:
            for slip in slippage_values:
                config = DonchianConfig(
                    symbol="XAUUSD",
                    timeframe="h1",
                    data_path=None,
                    entry_lookback=55,
                    exit_lookback=20,
                    position_size_pct=1.0,
                    max_leverage=1.0,
                    cost_model=CostModel(spread_pips=spread, commission_per_lot=comm, slippage_pips=slip),
                    train_ratio=0.7,
                    val_ratio=0.15,
                    test_ratio=0.15,
                    seed=42,
                )
                tag = f"cost_s{spread}_c{comm}_sl{slip}"
                print(f"Running {tag}...")
                result = run_config(config, df, tag)
                results.append(result)
                print(f"  Trades: {result['n_trades']}, Net PF: {result['profit_factor_net']:.2f}, "
                      f"Ann.Ret: {result['annualized_return_net']:.2%}, Sharpe: {result['sharpe_net']:.2f}")

    # Save results
    results_df = pd.DataFrame(results)
    output_dir = paths.artifacts / "donchian_sensitivity"
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / f"sensitivity_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"\nResults saved to: {csv_path}")

    # Also save JSON for easier reading
    json_path = output_dir / f"sensitivity_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to: {json_path}")

    # Print summary tables
    print("\n=== LOOKBACK SENSITIVITY SUMMARY ===")
    lookback_results = [r for r in results if r["tag"].startswith("lookback")]
    if lookback_results:
        lb_df = pd.DataFrame(lookback_results)
        print(lb_df[["tag", "n_trades", "profit_factor_net", "annualized_return_net", "sharpe_net", "max_drawdown_net"]].to_string(index=False))

    print("\n=== COST SENSITIVITY SUMMARY ===")
    cost_results = [r for r in results if r["tag"].startswith("cost")]
    if cost_results:
        c_df = pd.DataFrame(cost_results)
        print(c_df[["tag", "n_trades", "profit_factor_net", "annualized_return_net", "sharpe_net", "max_drawdown_net"]].to_string(index=False))


if __name__ == "__main__":
    main()