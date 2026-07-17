"""
Lightweight backtest runner for Hyp-A direction signals.

Uses pre-computed daily features + a fitted classifier. Applies one trade per
day at London open logic via signal series (not full bar-by-bar engine).

For the original ``backtesting.py`` MLStrategy implementation, see:
``legacy/src/hyp_a_backtest_xgb_xauusd_h1_2018_2025.py``

Usage::

    python -m mars.apps.backtester.run_hyp_a_backtest \\
        --model models/mars_hyp_a_xgb_classifier_XXXX.joblib \\
        --features data/processed/mars_hyp_a_features_....parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from mars.libs.models.xgboost_model import XGBoostClassifierModel
from mars.libs.utils.paths import ProjectPaths


def simple_session_backtest(
    features: pd.DataFrame,
    y_direction: pd.Series,
    y_return: pd.Series,
    predictions: np.ndarray,
    *,
    commission: float = 0.0002,
) -> dict:
    """
    Vectorized one-trade-per-day PnL using realized london_return.

    If prediction==1 go long return; if 0 go short (-return).
    Commission charged twice (entry+exit) as fraction of notional.
    """
    pred = np.asarray(predictions)
    realized = y_return.loc[features.index].to_numpy()
    direction = y_direction.loc[features.index].to_numpy()

    # Long when pred=1, short when pred=0
    side = np.where(pred == 1, 1.0, -1.0)
    gross = side * realized
    net = gross - 2 * commission
    equity = np.cumprod(1.0 + net)
    total_return = float(equity[-1] - 1.0) if len(equity) else 0.0
    hit = float((pred == direction).mean()) if len(pred) else float("nan")
    sharpe = (
        float(np.mean(net) / (np.std(net) + 1e-12) * np.sqrt(252))
        if len(net) > 1
        else float("nan")
    )
    max_dd = float(np.min(equity / np.maximum.accumulate(equity) - 1.0)) if len(equity) else 0.0
    return {
        "n_trades": int(len(pred)),
        "hit_rate": hit,
        "total_return": total_return,
        "sharpe_approx": sharpe,
        "max_drawdown": max_dd,
        "mean_net_return": float(np.mean(net)) if len(net) else 0.0,
        "commission": commission,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="M.A.R.S. Hyp-A simple session backtest.")
    parser.add_argument("--model", type=str, required=True, help="Path to classifier joblib.")
    parser.add_argument(
        "--features",
        type=str,
        required=True,
        help="Processed feature parquet with london_direction and london_return.",
    )
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--commission", type=float, default=0.0002)
    args = parser.parse_args()

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

    model = XGBoostClassifierModel.load(args.model)
    preds = model.predict(X_test)
    stats = simple_session_backtest(
        X_test, y_dir_test, y_ret_test, preds, commission=args.commission
    )

    print("=== M.A.R.S. Hyp-A Session Backtest (test slice) ===")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(
        "\nNOTE: This is a research vectorized backtest, not a tick-level simulator. "
        "See docs for limitations (spread, session open timing, overnight risk)."
    )


if __name__ == "__main__":
    main()
