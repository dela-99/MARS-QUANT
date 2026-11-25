#!/usr/bin/env python3
"""Compute correct aggregate metrics for all three cost scenarios."""

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

# Three cost scenarios
scenarios = {
    "zero": CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0),
    "scenario1": CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5),
    "scenario2": CostModel(spread_pips=2.0, commission_per_lot=1.0, slippage_pips=1.0),
}

results = {}

for name, cost_model in scenarios.items():
    print(f"\n{'='*60}")
    print(f"Processing {name}...")
    print(f"{'='*60}")
    
    wf_config = WalkForwardConfig(
        sma_period=200,
        initial_train_years=2,
        oos_window_months=6,
        step_months=6,
        position_size_pct=1.0,
        max_leverage=1.0,
        cost_model=cost_model,
        seed=42,
    )
    
    windows = create_walkforward_windows(df.index, wf_config.initial_train_years, wf_config.oos_window_months, wf_config.step_months)
    
    all_oos_returns = []
    window_metrics = []
    
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
        
        bars_per_year = 252 * 24
        ann_ret = equity_rets.mean() * bars_per_year
        ann_vol = equity_rets.std() * np.sqrt(bars_per_year)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        
        cum = (1 + equity_rets).cumprod()
        peak = cum.cummax()
        dd = (cum - peak) / peak
        max_dd = dd.min()
        
        total_return = (1 + equity_rets).prod() - 1
        
        window_metrics.append({
            'idx': i+1,
            'return': float(total_return),
            'sharpe': float(sharpe),
            'max_dd': float(max_dd),
        })
    
    all_rets = pd.concat(all_oos_returns)
    bars_per_year = 252 * 24
    
    agg_return = float((1 + all_rets).prod() - 1)
    ann_ret_agg = all_rets.mean() * bars_per_year
    ann_vol_agg = all_rets.std() * np.sqrt(bars_per_year)
    agg_sharpe = float(ann_ret_agg / ann_vol_agg) if ann_vol_agg > 0 else 0
    
    cum_agg = (1 + all_rets).cumprod()
    peak_agg = cum_agg.cummax()
    dd_agg = (cum_agg - peak_agg) / peak_agg
    agg_max_dd = float(dd_agg.min())
    
    returns_list = [w['return'] for w in window_metrics]
    sharpes_list = [w['sharpe'] for w in window_metrics]
    dds_list = [w['max_dd'] for w in window_metrics]
    
    sorted_returns = sorted(returns_list, reverse=True)
    top_25 = max(1, len(sorted_returns) // 4)
    top_contrib = float(sum(sorted_returns[:top_25]) / sum(returns_list)) if sum(returns_list) != 0 else 0
    
    results[name] = {
        'aggregate_return': agg_return,
        'aggregate_sharpe': agg_sharpe,
        'aggregate_max_dd': agg_max_dd,
        'mean_window_return': float(np.mean(returns_list)),
        'median_window_return': float(np.median(returns_list)),
        'std_window_return': float(np.std(returns_list)),
        'mean_window_sharpe': float(np.mean(sharpes_list)),
        'median_window_sharpe': float(np.median(sharpes_list)),
        'worst_window_dd': float(min(dds_list)),
        'mean_window_dd': float(np.mean(dds_list)),
        'top_25pct_contribution': top_contrib,
        'window_metrics': window_metrics,
    }
    
    print(f"  CORRECT Aggregate Return: {agg_return:.4%}")
    print(f"  CORRECT Aggregate Sharpe: {agg_sharpe:.4f}")
    print(f"  CORRECT Aggregate Max DD: {agg_max_dd:.4%}")
    print(f"  Mean Window Sharpe: {np.mean(sharpes_list):.4f}")
    print(f"  Median Window Sharpe: {np.median(sharpes_list):.4f}")
    print(f"  Worst Window DD: {min(dds_list):.4%}")

with open('audit_correct_metrics_all_scenarios.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\nSaved to audit_correct_metrics_all_scenarios.json")