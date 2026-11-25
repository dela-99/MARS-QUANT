#!/usr/bin/env python3
"""Audit script for MA-TSM-001 walk-forward validation."""

import pandas as pd
import numpy as np
import vectorbt as vbt

from mars.apps.research_lab.ma_tsm_walkforward import (
    WalkForwardConfig,
    run_walkforward,
    run_single_window,
    aggregate_results,
    create_walkforward_windows,
)
from mars.apps.research_lab.ma_tsm_001 import (
    load_and_validate_data,
    compute_sma_signals,
    run_vectorbt_portfolio,
    compute_metrics,
    MATSMConfig,
    CostModel,
    ProjectPaths,
)

# Load full data
paths = ProjectPaths.from_root()
matsm_config = MATSMConfig(
    symbol="XAUUSD",
    timeframe="h1",
    sma_period=200,
    data_path=None,
)
df = load_and_validate_data(matsm_config, paths)
print(f"Full data: {len(df)} bars, {df.index[0]} to {df.index[-1]}")

# Run walk-forward with scenario 1
wf_config = WalkForwardConfig(
    sma_period=200,
    initial_train_years=2,
    oos_window_months=6,
    step_months=6,
    position_size_pct=1.0,
    max_leverage=1.0,
    cost_model=CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
    seed=42,
)

# Create windows
windows = create_walkforward_windows(df.index, wf_config.initial_train_years, wf_config.oos_window_months, wf_config.step_months)
print(f"Number of windows: {len(windows)}")

# Run each window and collect detailed data
all_oos_equity_curves = []
all_oos_returns = []
window_details = []

for i, (train_start, train_end, oos_start, oos_end) in enumerate(windows):
    print(f"Window {i+1}: Train {train_start.date()} to {train_end.date()}, OOS {oos_start.date()} to {oos_end.date()}")
    
    # Run single window
    result = run_single_window(df, train_start, train_end, oos_start, oos_end, wf_config)
    
    # Get the actual OOS equity curve from VectorBT
    warmup_bars = wf_config.sma_period + 5
    warmup_start_idx = max(0, df.index.get_loc(train_start) - warmup_bars)
    warmup_start = df.index[warmup_start_idx]
    
    train_data = df.loc[warmup_start:train_end].copy()
    oos_data = df.loc[oos_start:oos_end].copy()
    combined = pd.concat([train_data, oos_data])
    combined = combined[~combined.index.duplicated(keep='first')]
    
    signals = compute_sma_signals(combined, wf_config.sma_period)
    oos_signals = signals.loc[oos_start:oos_end].copy()
    
    matsm_config = MATSMConfig(
        symbol="XAUUSD",
        timeframe="h1",
        sma_period=wf_config.sma_period,
        position_size_pct=wf_config.position_size_pct,
        max_leverage=wf_config.max_leverage,
        cost_model=wf_config.cost_model,
        seed=wf_config.seed,
    )
    
    pf = run_vectorbt_portfolio(oos_signals, matsm_config)
    equity = pf.value()
    
    # Get bar-level returns from equity curve
    equity_rets = equity.pct_change().dropna()
    
    # Store for aggregate calculation
    all_oos_equity_curves.append(equity)
    all_oos_returns.append(equity_rets)
    
    # Compute correct Sharpe from bar-level returns
    bars_per_year = 252 * 24
    ann_ret = equity_rets.mean() * bars_per_year
    ann_vol = equity_rets.std() * np.sqrt(bars_per_year)
    correct_sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    
    # Compute correct max drawdown from equity curve
    cum = (1 + equity_rets).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    correct_max_dd = dd.min()
    
    print(f"  Reported: Return={result.net_return:.4%}, Sharpe={result.sharpe:.4f}, MaxDD={result.max_drawdown:.4%}")
    print(f"  Correct:  Return={result.net_return:.4%}, Sharpe={correct_sharpe:.4f}, MaxDD={correct_max_dd:.4%}")
    print(f"  Trades: {result.n_trades}, OOS bars: {len(oos_data)}")
    
    window_details.append({
        "idx": i+1,
        "reported_return": result.net_return,
        "reported_sharpe": result.sharpe,
        "reported_dd": result.max_drawdown,
        "correct_sharpe": correct_sharpe,
        "correct_dd": correct_max_dd,
        "n_trades": result.n_trades,
        "equity_rets": equity_rets,
    })

print("="*80)
print("AGGREGATE ANALYSIS")
print("="*80)

# Concatenate all OOS returns
all_rets_concat = pd.concat(all_oos_returns)
print(f"Total OOS bars with returns: {len(all_rets_concat)}")

# Aggregate return (compounded)
agg_return = (1 + all_rets_concat).prod() - 1
print(f"Aggregate OOS Return (from concat returns): {agg_return:.4%}")

# Aggregate Sharpe (correct - from bar-level returns)
bars_per_year = 252 * 24
ann_ret_agg = all_rets_concat.mean() * bars_per_year
ann_vol_agg = all_rets_concat.std() * np.sqrt(bars_per_year)
agg_sharpe = ann_ret_agg / ann_vol_agg if ann_vol_agg > 0 else 0
print(f"Aggregate OOS Sharpe (correct, bar-level): {agg_sharpe:.4f}")

# Aggregate max drawdown (correct - from concat equity curve)
cum_agg = (1 + all_rets_concat).cumprod()
peak_agg = cum_agg.cummax()
dd_agg = (cum_agg - peak_agg) / peak_agg
agg_max_dd = dd_agg.min()
print(f"Aggregate Max Drawdown (correct): {agg_max_dd:.4%}")

# Compare with reported aggregate
returns = [w["reported_return"] for w in window_details]
sharpes = [w["reported_sharpe"] for w in window_details]
drawdowns = [w["reported_dd"] for w in window_details]

# Reported aggregate (from aggregate_results)
equity_curve = [1.0]
for r in returns:
    equity_curve.append(equity_curve[-1] * (1 + r))
reported_agg_return = equity_curve[-1] - 1
reported_agg_sharpe = np.mean(np.diff(equity_curve) / equity_curve[:-1]) / np.std(np.diff(equity_curve) / equity_curve[:-1]) * np.sqrt(bars_per_year)
reported_worst_dd = min(drawdowns)

print(f"Reported Aggregate Return: {reported_agg_return:.4%}")
print(f"Reported Aggregate Sharpe: {reported_agg_sharpe:.4f}")
print(f"Reported Worst Window DD: {reported_worst_dd:.4%}")

# Mean window Sharpe
mean_window_sharpe = np.mean(sharpes)
median_window_sharpe = np.median(sharpes)
print(f"Mean Window Sharpe (reported): {mean_window_sharpe:.4f}")
print(f"Median Window Sharpe (reported): {median_window_sharpe:.4f}")

# Correct mean window Sharpe
correct_sharpes = [w["correct_sharpe"] for w in window_details]
print(f"Mean Window Sharpe (correct): {np.mean(correct_sharpes):.4f}")
print(f"Median Window Sharpe (correct): {np.median(correct_sharpes):.4f}")

# Correct worst window DD
correct_dds = [w["correct_dd"] for w in window_details]
print(f"Worst Window DD (correct): {min(correct_dds):.4%}")