#!/usr/bin/env python3
"""Compute correct aggregate metrics from full walk-forward."""

import pandas as pd
import numpy as np
import json

from mars.apps.research_lab.ma_tsm_walkforward import (
    WalkForwardConfig,
    create_walkforward_windows,
)
from mars.apps.research_lab.ma_tsm_001 import (
    load_and_validate_data,
    compute_sma_signals,
    run_vectorbt_portfolio,
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
print(f"Full data: {len(df)} bars")

# Config
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

all_oos_returns = []
window_correct_metrics = []

for i, (train_start, train_end, oos_start, oos_end) in enumerate(windows):
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
    equity_rets = equity.pct_change().dropna()
    
    all_oos_returns.append(equity_rets)
    
    # Correct window metrics
    bars_per_year = 252 * 24
    ann_ret = equity_rets.mean() * bars_per_year
    ann_vol = equity_rets.std() * np.sqrt(bars_per_year)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    
    cum = (1 + equity_rets).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()
    
    total_return = (1 + equity_rets).prod() - 1
    
    window_correct_metrics.append({
        'idx': i+1,
        'oos_start': str(oos_start),
        'oos_end': str(oos_end),
        'return': total_return,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'n_bars': len(equity_rets),
    })
    print(f"Window {i+1}: Return={total_return:.4%}, Sharpe={sharpe:.4f}, MaxDD={max_dd:.4%}")

# Concatenate all OOS returns
all_rets = pd.concat(all_oos_returns)
print(f"\nTotal OOS bars: {len(all_rets)}")

# Correct aggregate metrics
agg_return = (1 + all_rets).prod() - 1
print(f"\nCORRECT Aggregate OOS Return: {agg_return:.4%}")

ann_ret_agg = all_rets.mean() * bars_per_year
ann_vol_agg = all_rets.std() * np.sqrt(bars_per_year)
agg_sharpe = ann_ret_agg / ann_vol_agg if ann_vol_agg > 0 else 0
print(f"CORRECT Aggregate OOS Sharpe: {agg_sharpe:.4f}")

cum_agg = (1 + all_rets).cumprod()
peak_agg = cum_agg.cummax()
dd_agg = (cum_agg - peak_agg) / peak_agg
agg_max_dd = dd_agg.min()
print(f"CORRECT Aggregate Max Drawdown: {agg_max_dd:.4%}")

# Window-level correct stats
returns = [w['return'] for w in window_correct_metrics]
sharpes = [w['sharpe'] for w in window_correct_metrics]
dds = [w['max_dd'] for w in window_correct_metrics]

print(f"\n--- Correct Window-Level Statistics ---")
print(f"Mean Return: {np.mean(returns):.4%}")
print(f"Median Return: {np.median(returns):.4%}")
print(f"Std Return: {np.std(returns):.4%}")
print(f"Mean Sharpe: {np.mean(sharpes):.4f}")
print(f"Median Sharpe: {np.median(sharpes):.4f}")
print(f"Worst Window DD: {min(dds):.4%}")
print(f"Mean Window DD: {np.mean(dds):.4%}")

# Top 25% contribution
sorted_returns = sorted(returns, reverse=True)
top_25 = max(1, len(sorted_returns) // 4)
top_contrib = sum(sorted_returns[:top_25]) / sum(returns) if sum(returns) != 0 else 0
print(f"Top 25% window contribution: {top_contrib:.4%}")

# Save for report
with open('audit_correct_metrics_scenario1.json', 'w') as f:
    json.dump({
        'aggregate_return': float(agg_return),
        'aggregate_sharpe': float(agg_sharpe),
        'aggregate_max_dd': float(agg_max_dd),
        'mean_window_return': float(np.mean(returns)),
        'median_window_return': float(np.median(returns)),
        'std_window_return': float(np.std(returns)),
        'mean_window_sharpe': float(np.mean(sharpes)),
        'median_window_sharpe': float(np.median(sharpes)),
        'worst_window_dd': float(min(dds)),
        'mean_window_dd': float(np.mean(dds)),
        'top_25pct_contribution': float(top_contrib),
        'window_metrics': window_correct_metrics,
    }, f, indent=2)

print("\nSaved to audit_correct_metrics_scenario1.json")