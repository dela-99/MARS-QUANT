#!/usr/bin/env python3
"""Quick verification of key windows to audit metrics."""

import pandas as pd
import numpy as np

from mars.apps.research_lab.ma_tsm_walkforward import (
    WalkForwardConfig,
    run_single_window,
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

# Analyze key windows: first, middle, last, and worst performers
# Window 1 (first), 5 (good), 8 (worst DD in report), 18 (best), 19 (last)
key_windows = [0, 4, 7, 17, 18]

for i in key_windows:
    train_start, train_end, oos_start, oos_end = windows[i]
    print(f"\n{'='*60}")
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
    
    # Also compute from trade-level (what current code does)
    trades = pf.trades.records_readable
    if len(trades) > 0:
        net_pnls = trades["PnL"].values
        equity_ref = 100000.0
        trade_returns = net_pnls / equity_ref
        ann_ret_trade = trade_returns.mean() * bars_per_year  # WRONG: uses trades/year
        ann_vol_trade = trade_returns.std() * np.sqrt(bars_per_year)
        sharpe_trade = ann_ret_trade / ann_vol_trade if ann_vol_trade > 0 else 0
        
        cum_curve = np.cumprod(1 + trade_returns)
        peak_curve = np.maximum.accumulate(cum_curve)
        dd_curve = (cum_curve - peak_curve) / peak_curve
        max_dd_trade = dd_curve.min()
    else:
        sharpe_trade = 0
        max_dd_trade = 0
    
    print(f"  Reported:   Return={result.net_return:.4%}, Sharpe={result.sharpe:.4f}, MaxDD={result.max_drawdown:.4%}")
    print(f"  Trade-level:               Sharpe={sharpe_trade:.4f}, MaxDD={max_dd_trade:.4%}")
    print(f"  Bar-level:                 Sharpe={correct_sharpe:.4f}, MaxDD={correct_max_dd:.4%}")
    print(f"  Trades: {result.n_trades}, OOS bars: {len(oos_data)}, Equity bars: {len(equity)}")