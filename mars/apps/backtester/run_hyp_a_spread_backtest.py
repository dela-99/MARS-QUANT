"""
Re-run Hyp-A backtest with spread-aware engine.
Compares original (mid-price) vs spread-aware results.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from mars.libs.models.xgboost_model import XGBoostClassifierModel
from mars.libs.utils.paths import ProjectPaths
from mars.research.experiment import ExperimentLog
from mars.apps.backtester.spread_aware_backtest import (
    spread_aware_session_backtest,
    SpreadConfig,
)
from mars.libs.data.loaders import load_ohlcv_parquet


def main() -> None:
    parser = argparse.ArgumentParser(description="M.A.R.S. Hyp-A spread-aware backtest.")
    parser.add_argument("--model", type=str, required=True, help="Path to classifier joblib.")
    parser.add_argument(
        "--features",
        type=str,
        required=True,
        help="Processed feature parquet with london_direction and london_return.",
    )
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--commission", type=float, default=0.0002)
    parser.add_argument(
        "--spread-source",
        type=str,
        default="h1_raw",
        choices=["h1_raw", "h1_processed"],
        help="Where to get spread data from.",
    )
    args = parser.parse_args()

    # Load features
    df = pd.read_parquet(args.features)
    y_dir = df["london_direction"]
    y_ret = df["london_return"]
    X = df.drop(
        columns=[c for c in ("london_direction", "london_return", "symbol", "timeframe") if c in df.columns]
    )

    n = len(X)
    n_test = max(1, int(n * args.test_ratio))
    X_test = X.iloc[-n_test:]
    y_dir_test = y_dir.iloc[-n_test:]
    y_ret_test = y_ret.iloc[-n_test:]

    # TEST SET GUARD
    from mars.core.config import DEFAULT_CONFIG
    exp_log = ExperimentLog(hypothesis_root=DEFAULT_CONFIG.paths.hypotheses)
    exp_log.assert_can_evaluate_on_test("HYP-A-001")

    # Load model
    model = XGBoostClassifierModel.load(args.model)
    preds = model.predict(X_test)

    # Load spread data
    paths = ProjectPaths.from_root()
    if args.spread_source == "h1_raw":
        spread_df = pd.read_parquet(paths.raw_data / "xauusd_h1_2018_present.parquet")
    else:
        # Would need processed version with spread
        spread_df = pd.read_parquet(paths.raw_data / "xauusd_h1_2018_present.parquet")
    
    spread_df['time'] = pd.to_datetime(spread_df['time'])
    spread_df = spread_df.set_index('time')
    spread_series = spread_df['spread']

    # Run ORIGINAL backtest (mid-price, no spread)
    print("=== ORIGINAL (mid-price, commission only) ===")
    from mars.apps.backtester.run_hyp_a_backtest import simple_session_backtest
    orig_stats = simple_session_backtest(
        X_test, y_dir_test, y_ret_test, preds, commission=args.commission
    )
    for k, v in orig_stats.items():
        print(f"  {k}: {v}")

    # Run SPREAD-AWARE backtest
    print("\n=== SPREAD-AWARE (bid/ask fills) ===")
    spread_stats = spread_aware_session_backtest(
        X_test, y_dir_test, y_ret_test, preds,
        spread_series=spread_series,
        config=SpreadConfig(),
        commission=args.commission,
    )
    for k, v in spread_stats.items():
        print(f"  {k}: {v}")

    # Comparison
    print("\n=== COMPARISON ===")
    print(f"  Sharpe:     {orig_stats['sharpe_approx']:.4f} -> {spread_stats['sharpe_approx']:.4f}  ({spread_stats['sharpe_approx'] - orig_stats['sharpe_approx']:+.4f})")
    print(f"  Total Ret:  {orig_stats['total_return']*100:.2f}% -> {spread_stats['total_return_pct']:.2f}%  ({spread_stats['total_return_pct'] - orig_stats['total_return']*100:+.2f}%)")
    print(f"  Max DD:     {orig_stats['max_drawdown']*100:.2f}% -> {spread_stats['max_drawdown_pct']:.2f}%  ({spread_stats['max_drawdown_pct'] - orig_stats['max_drawdown']*100:+.2f}%)")
    print(f"  Profit Fact: {orig_stats.get('profit_factor', 'N/A')} -> {spread_stats['profit_factor']:.4f}")
    print(f"  Hit Rate:   {orig_stats['hit_rate']:.4f} -> {spread_stats['hit_rate']:.4f}")
    print(f"  Avg Spread Cost/trade: ${spread_stats['avg_spread_cost']:.4f}")
    print(f"  Total Spread Cost: ${spread_stats['total_spread_cost']:.2f}")

    # Save comparison
    import json
    comparison = {
        "original": orig_stats,
        "spread_aware": spread_stats,
        "deltas": {
            "sharpe": spread_stats['sharpe_approx'] - orig_stats['sharpe_approx'],
            "total_return_pct": spread_stats['total_return_pct'] - orig_stats['total_return']*100,
            "max_drawdown_pct": spread_stats['max_drawdown_pct'] - orig_stats['max_drawdown']*100,
        }
    }
    
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = paths.reports / f"hyp_a_spread_comparison_{stamp}.json"
    paths.reports.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"\nComparison saved to: {out_path}")


if __name__ == "__main__":
    main()