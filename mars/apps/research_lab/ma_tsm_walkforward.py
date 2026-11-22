#!/usr/bin/env python3
"""
MA-TSM-001 Walk-Forward Validation

Expanding-window walk-forward validation for SMA-200 trend-following on XAUUSD H1.
Uses the existing MA-TSM-001 implementation and VectorBT infrastructure.
"""

import argparse
import json
import sys
import warnings
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from mars.apps.research_lab.ma_tsm_001 import (
    load_and_validate_data,
    compute_sma_signals,
    run_vectorbt_portfolio,
    compute_metrics,
    compute_benchmarks,
    MATSMConfig,
    CostModel,
    ProjectPaths,
)

warnings.filterwarnings("ignore", category=UserWarning, module="vectorbt")


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation."""
    sma_period: int = 200
    initial_train_years: int = 2
    oos_window_months: int = 6
    step_months: int = 6  # How much to expand each step (expanding = same as window)
    cost_model: CostModel = CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0)
    position_size_pct: float = 1.0
    max_leverage: float = 1.0
    seed: int = 42


@dataclass
class WindowResult:
    """Results for a single walk-forward window."""
    window_idx: int
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    n_train_bars: int
    n_oos_bars: int
    n_trades: int
    net_return: float
    ann_return: float
    sharpe: float
    max_drawdown: float
    profit_factor: float
    win_rate: float
    exposure: float
    avg_trade_return: float
    total_costs: float
    oos_returns: list[float] = field(default_factory=list)  # Bar-level OOS equity curve returns


def create_walkforward_windows(
    index: pd.DatetimeIndex,
    initial_train_years: int,
    oos_window_months: int,
    step_months: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """
    Create expanding walk-forward windows.

    Returns list of (train_start, train_end, oos_start, oos_end) tuples.
    """
    windows = []

    # Initial training period end
    train_start = index[0]
    initial_train_end = train_start + pd.DateOffset(years=initial_train_years)

    # Ensure we have enough data for initial training + at least one OOS window
    min_required = initial_train_end + pd.DateOffset(months=oos_window_months)
    if index[-1] < min_required:
        raise ValueError(f"Not enough data. Need at least {min_required}, have {index[-1]}")

    current_train_end = initial_train_end

    while True:
        oos_start = current_train_end
        oos_end = oos_start + pd.DateOffset(months=oos_window_months)

        # Check if we have enough data for this OOS window
        if oos_end > index[-1]:
            # Use remaining data as final window if it's at least 1 month
            oos_end = index[-1]
            if (oos_end - oos_start).days < 30:
                break

        windows.append((train_start, current_train_end, oos_start, oos_end))

        # Expand training window
        current_train_end = oos_end

        # Stop if we've used all data
        if current_train_end >= index[-1] - pd.DateOffset(months=1):
            break

    return windows


def run_single_window(
    df: pd.DataFrame,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    oos_start: pd.Timestamp,
    oos_end: pd.Timestamp,
    config: WalkForwardConfig,
) -> WindowResult:
    """Run backtest for a single walk-forward window."""

    # For SMA calculation, we need sma_period bars of history before train_start
    # The compute_sma_signals uses shift(1) on rolling mean, so it needs sma_period bars before the first signal
    warmup_bars = config.sma_period + 5  # extra buffer
    warmup_start_idx = max(0, df.index.get_loc(train_start) - warmup_bars)
    warmup_start = df.index[warmup_start_idx]

    # Training data includes warmup period, up to but NOT including oos_start
    train_data = df.loc[warmup_start:train_end].copy()

    # OOS data starts at oos_start (no overlap with train)
    oos_data = df.loc[oos_start:oos_end].copy()

    # Combine for signal generation (SMA needs continuous history)
    # Ensure no duplicate index at boundary
    combined = pd.concat([train_data, oos_data])
    combined = combined[~combined.index.duplicated(keep='first')]

    # Compute signals on combined data (SMA uses prior bars only via shift)
    signals = compute_sma_signals(combined, config.sma_period)

    # Extract OOS signals (these include entry/exit events for OOS period)
    oos_signals = signals.loc[oos_start:oos_end].copy()

    matsm_config = MATSMConfig(
        symbol="XAUUSD",
        timeframe="h1",
        sma_period=config.sma_period,
        position_size_pct=config.position_size_pct,
        max_leverage=config.max_leverage,
        cost_model=config.cost_model,
        seed=config.seed,
    )

    # Run portfolio on OOS signals (uses close prices from oos_signals DataFrame)
    pf = run_vectorbt_portfolio(oos_signals, matsm_config)

    # Capture bar-level OOS equity curve returns for correct aggregate computation
    equity_curve = pf.value()
    oos_returns = equity_curve.pct_change().dropna().tolist()

    # Compute metrics
    metrics = compute_metrics(pf, matsm_config, oos_data)

    # Calculate total costs from trades
    trades = pf.trades.records_readable
    total_costs = 0.0
    if len(trades) > 0:
        if "Fees" in trades.columns:
            total_costs = trades["Fees"].sum()

    return WindowResult(
        window_idx=0,  # Will be set by caller
        train_start=str(train_start),
        train_end=str(train_end),
        oos_start=str(oos_start),
        oos_end=str(oos_end),
        n_train_bars=len(train_data),
        n_oos_bars=len(oos_data),
        n_trades=metrics.get("n_trades", 0),
        net_return=metrics.get("total_return_net", 0.0),
        ann_return=metrics.get("annualized_return_net", 0.0),
        sharpe=metrics.get("sharpe_net", 0.0),
        max_drawdown=abs(metrics.get("max_drawdown_net", 0.0)),
        profit_factor=metrics.get("profit_factor_net", 0.0),
        win_rate=metrics.get("win_rate_net", 0.0),
        exposure=metrics.get("exposure", 0.0),
        avg_trade_return=metrics.get("avg_trade_return_bps", 0.0) / 10000,  # Convert from bps
        total_costs=total_costs,
        oos_returns=oos_returns,
    )


def run_walkforward(
    df: pd.DataFrame,
    wf_config: WalkForwardConfig,
) -> list[WindowResult]:
    """Run complete walk-forward validation."""

    windows = create_walkforward_windows(
        df.index,
        wf_config.initial_train_years,
        wf_config.oos_window_months,
        wf_config.step_months,
    )

    results = []
    for i, (train_start, train_end, oos_start, oos_end) in enumerate(windows):
        print(f"Window {i+1}/{len(windows)}: Train {train_start.date()} to {train_end.date()}, "
              f"OOS {oos_start.date()} to {oos_end.date()}")

        result = run_single_window(df, train_start, train_end, oos_start, oos_end, wf_config)
        result.window_idx = i + 1
        results.append(result)

    return results


def aggregate_results(results: list[WindowResult]) -> dict:
    """Compute aggregate OOS statistics from concatenated bar-level returns."""

    if not results:
        return {}

    returns = [r.net_return for r in results]
    sharpes = [r.sharpe for r in results]
    drawdowns = [r.max_drawdown for r in results]
    profit_factors = [r.profit_factor for r in results]
    win_rates = [r.win_rate for r in results]
    n_trades = [r.n_trades for r in results]

    profitable_windows = sum(1 for r in returns if r > 0)

    # === CORRECT: Concatenate all OOS bar-level returns for aggregate metrics ===
    all_oos_returns = []
    for r in results:
        if r.oos_returns:
            all_oos_returns.extend(r.oos_returns)

    if all_oos_returns:
        concat_rets = np.array(all_oos_returns)
        
        # Aggregate return from concatenated equity curve
        aggregate_return = float(np.prod(1 + concat_rets) - 1)
        
        # Aggregate Sharpe (correct: from bar-level returns)
        bars_per_year = 252 * 24
        ann_ret = float(np.mean(concat_rets) * bars_per_year)
        ann_vol = float(np.std(concat_rets) * np.sqrt(bars_per_year))
        aggregate_sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else 0.0
        
        # Aggregate max drawdown (correct: from concatenated equity curve)
        cum = np.cumprod(1 + concat_rets)
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        aggregate_max_dd = float(dd.min())
    else:
        # Fallback (should not happen)
        equity = 1.0
        equity_curve = [1.0]
        for r in returns:
            equity *= (1 + r)
            equity_curve.append(equity)
        aggregate_return = equity - 1.0
        
        if len(equity_curve) > 1:
            rets = np.diff(equity_curve) / equity_curve[:-1]
            aggregate_sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252 * 24)) if np.std(rets) > 0 else 0.0
        else:
            aggregate_sharpe = 0.0
        aggregate_max_dd = 0.0

    # Contribution of strongest windows (using per-window returns)
    sorted_returns = sorted(returns, reverse=True)
    top_25_pct = max(1, len(sorted_returns) // 4)
    top_contribution = sum(sorted_returns[:top_25_pct]) / sum(returns) if sum(returns) != 0 else 0

    return {
        "n_windows": len(results),
        "profitable_windows": profitable_windows,
        "profitable_pct": profitable_windows / len(results) * 100,
        "mean_oos_return": float(np.mean(returns)),
        "median_oos_return": float(np.median(returns)),
        "std_oos_return": float(np.std(returns)),
        "mean_oos_sharpe": float(np.mean(sharpes)),
        "median_oos_sharpe": float(np.median(sharpes)),
        "aggregate_oos_return": aggregate_return,
        "aggregate_oos_sharpe": aggregate_sharpe,
        "worst_oos_drawdown": aggregate_max_dd,  # Now correct aggregate DD
        "mean_oos_drawdown": float(np.mean(drawdowns)),
        "mean_profit_factor": float(np.mean(profit_factors)),
        "mean_win_rate": float(np.mean(win_rates)),
        "total_trades": sum(n_trades),
        "return_dispersion": float(np.std(returns)),
        "top_25pct_contribution": float(top_contribution),
        "min_return": float(min(returns)),
        "max_return": float(max(returns)),
    }


def save_results(
    results: list[WindowResult],
    aggregate: dict,
    config: WalkForwardConfig,
    output_dir: Path,
    suffix: str,
) -> None:
    """Save results to files."""

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save window results as CSV
    df_results = pd.DataFrame([asdict(r) for r in results])
    csv_path = output_dir / f"ma_tsm_wf_windows_{suffix}.csv"
    df_results.to_csv(csv_path, index=False)

    # Save aggregate results
    agg_path = output_dir / f"ma_tsm_wf_aggregate_{suffix}.json"
    with open(agg_path, "w") as f:
        json.dump(aggregate, f, indent=2, default=str)

    # Save config
    config_path = output_dir / f"ma_tsm_wf_config_{suffix}.json"
    with open(config_path, "w") as f:
        json.dump(asdict(config), f, indent=2, default=str)

    print(f"Results saved to {output_dir}")


def generate_report(
    results: list[WindowResult],
    aggregate: dict,
    config: WalkForwardConfig,
    output_dir: Path,
    suffix: str,
) -> str:
    """Generate text report."""

    lines = []
    lines.append("=" * 80)
    lines.append("MA-TSM-001 WALK-FORWARD VALIDATION REPORT")
    lines.append("=" * 80)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"SMA Period: {config.sma_period}")
    lines.append(f"Initial Training: {config.initial_train_years} years")
    lines.append(f"OOS Window: {config.oos_window_months} months")
    lines.append(f"Cost Model: spread={config.cost_model.spread_pips}, "
                 f"commission={config.cost_model.commission_per_lot}, "
                 f"slippage={config.cost_model.slippage_pips}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("INDIVIDUAL WINDOW RESULTS")
    lines.append("-" * 80)

    header = f"{'Win':>3} | {'Train Period':>22} | {'OOS Period':>22} | {'Trades':>6} | {'Return':>8} | {'Ann.Ret':>8} | {'Sharpe':>7} | {'MaxDD':>7} | {'PF':>5} | {'WR':>5} | {'Exposure':>7}"
    lines.append(header)
    lines.append("-" * len(header))

    for r in results:
        train_str = f"{r.train_start[:10]} to {r.train_end[:10]}"
        oos_str = f"{r.oos_start[:10]} to {r.oos_end[:10]}"
        lines.append(
            f"{r.window_idx:>3} | {train_str:>22} | {oos_str:>22} | "
            f"{r.n_trades:>6} | {r.net_return:>7.2%} | {r.ann_return:>7.2%} | "
            f"{r.sharpe:>6.2f} | {r.max_drawdown:>6.2%} | {r.profit_factor:>4.2f} | "
            f"{r.win_rate:>4.1%} | {r.exposure:>6.1%}"
        )

    lines.append("")
    lines.append("-" * 80)
    lines.append("AGGREGATE OOS STATISTICS")
    lines.append("-" * 80)

    lines.append(f"Number of windows:              {aggregate['n_windows']}")
    lines.append(f"Profitable windows:             {aggregate['profitable_windows']} ({aggregate['profitable_pct']:.1f}%)")
    lines.append(f"Mean OOS return:                {aggregate['mean_oos_return']:.2%}")
    lines.append(f"Median OOS return:              {aggregate['median_oos_return']:.2%}")
    lines.append(f"Std OOS return:                 {aggregate['std_oos_return']:.2%}")
    lines.append(f"Mean OOS Sharpe:                {aggregate['mean_oos_sharpe']:.2f}")
    lines.append(f"Median OOS Sharpe:              {aggregate['median_oos_sharpe']:.2f}")
    lines.append(f"Aggregate OOS return:           {aggregate['aggregate_oos_return']:.2%}")
    lines.append(f"Aggregate OOS Sharpe:           {aggregate['aggregate_oos_sharpe']:.2f}")
    lines.append(f"Worst OOS drawdown:             {aggregate['worst_oos_drawdown']:.2%}")
    lines.append(f"Mean OOS drawdown:              {aggregate['mean_oos_drawdown']:.2%}")
    lines.append(f"Mean profit factor:             {aggregate['mean_profit_factor']:.2f}")
    lines.append(f"Mean win rate:                  {aggregate['mean_win_rate']:.1%}")
    lines.append(f"Total trades:                   {aggregate['total_trades']}")
    lines.append(f"Return dispersion (std):        {aggregate['return_dispersion']:.2%}")
    lines.append(f"Top 25% windows contribution:   {aggregate['top_25pct_contribution']:.1%}")
    lines.append(f"Min window return:              {aggregate['min_return']:.2%}")
    lines.append(f"Max window return:              {aggregate['max_return']:.2%}")

    lines.append("")
    lines.append("-" * 80)
    lines.append("REGIME ANALYSIS")
    lines.append("-" * 80)

    # Analyze by year
    df_res = pd.DataFrame([asdict(r) for r in results])
    df_res['oos_year'] = pd.to_datetime(df_res['oos_start']).dt.year

    yearly = df_res.groupby('oos_year').agg(
        n_windows=('window_idx', 'count'),
        total_return=('net_return', 'sum'),
        avg_sharpe=('sharpe', 'mean'),
        max_dd=('max_drawdown', 'min'),
        total_trades=('n_trades', 'sum'),
    ).round(4)

    lines.append("Performance by Year:")
    for year, row in yearly.iterrows():
        lines.append(f"  {year}: {row['n_windows']} windows, return={row['total_return']:.2%}, "
                     f"avg Sharpe={row['avg_sharpe']:.2f}, max DD={row['max_dd']:.2%}, "
                     f"trades={row['total_trades']}")

    # Performance by quarter (for seasonality)
    df_res['oos_quarter'] = pd.to_datetime(df_res['oos_start']).dt.quarter
    quarterly = df_res.groupby('oos_quarter').agg(
        avg_return=('net_return', 'mean'),
        avg_sharpe=('sharpe', 'mean'),
    ).round(4)

    lines.append("\nPerformance by Quarter:")
    for q, row in quarterly.iterrows():
        lines.append(f"  Q{q}: avg return={row['avg_return']:.2%}, avg Sharpe={row['avg_sharpe']:.2f}")

    lines.append("")
    lines.append("=" * 80)

    report = "\n".join(lines)

    # Save report
    report_path = output_dir / f"ma_tsm_wf_report_{suffix}.txt"
    with open(report_path, "w") as f:
        f.write(report)

    return report


def create_visualizations(
    results: list[WindowResult],
    aggregate: dict,
    config: WalkForwardConfig,
    output_dir: Path,
    suffix: str,
) -> None:
    """Generate and save visualization charts from verified data."""

    df = pd.DataFrame([asdict(r) for r in results])
    df['oos_start_dt'] = pd.to_datetime(df['oos_start'])
    df['oos_end_dt'] = pd.to_datetime(df['oos_end'])

    # === CORRECT: Build equity curve from concatenated bar-level OOS returns ===
    all_oos_returns = []
    all_dates = []
    for r in results:
        if r.oos_returns:
            # Need to get actual dates for each bar - we'll reconstruct from the data
            # For now, use the index positions
            all_oos_returns.extend(r.oos_returns)
    
    if all_oos_returns:
        concat_rets = np.array(all_oos_returns)
        equity_curve = np.cumprod(1 + concat_rets)
        # Create date index for the concatenated returns (approximate)
        total_bars = len(equity_curve)
        dates = pd.date_range(start=df.iloc[0]['oos_start_dt'], periods=total_bars, freq='h')
    else:
        # Fallback (should not happen)
        equity = 1.0
        equity_curve = [1.0]
        dates = [df.iloc[0]['oos_start_dt']]
        for _, r in df.iterrows():
            equity *= (1 + r.net_return)
            equity_curve.append(equity)
            dates.append(r.oos_end_dt)
        equity_curve = np.array(equity_curve)

    # Set up style
    plt.style.use('seaborn-v0_8-darkgrid')
    fig_size = (14, 10)

    # Figure 1: OOS Equity Curve and Drawdown
    fig, axes = plt.subplots(2, 2, figsize=fig_size)
    fig.suptitle(f'MA-TSM-001 Walk-Forward Validation (SMA-{config.sma_period}, '
                 f'{config.cost_model.spread_pips}p/{config.cost_model.commission_per_lot}c/'
                 f'{config.cost_model.slippage_pips}s)', fontsize=14, fontweight='bold')

    # Equity curve
    ax = axes[0, 0]
    ax.plot(dates, equity_curve, 'b-', linewidth=2, label='Strategy Equity')
    ax.set_title('OOS Equity Curve (Concatenated Bar-Level Returns)')
    ax.set_ylabel('Equity Multiple')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.YearLocator())

    # Drawdown curve
    ax = axes[0, 1]
    equity_series = pd.Series(equity_curve)
    running_max = equity_series.expanding().max()
    drawdown = (equity_series - running_max) / running_max
    ax.fill_between(dates, drawdown, 0, color='red', alpha=0.3, label='Drawdown')
    ax.plot(dates, drawdown, 'r-', linewidth=1)
    ax.set_title('OOS Drawdown Curve (Correct Aggregate)')
    ax.set_ylabel('Drawdown')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.YearLocator())

    # Performance by window (per-window net returns)
    ax = axes[1, 0]
    colors = ['green' if r > 0 else 'red' for r in df['net_return']]
    bars = ax.bar(range(1, len(df) + 1), df['net_return'] * 100, color=colors, alpha=0.7, edgecolor='black')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_title('OOS Return by Window (Per-Window)')
    ax.set_xlabel('Window')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    # Add value labels on bars
    for i, (bar, val) in enumerate(zip(bars, df['net_return'] * 100)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + (0.5 if val >= 0 else -1.5),
                f'{val:.2f}%', ha='center', va='bottom' if val >= 0 else 'top', fontsize=8)

    # Annual/Regime performance
    ax = axes[1, 1]
    df['oos_year'] = df['oos_start_dt'].dt.year
    yearly = df.groupby('oos_year').agg(
        total_return=('net_return', 'sum'),
        avg_sharpe=('sharpe', 'mean'),
    ).reset_index()
    x = yearly['oos_year']
    width = 0.35
    ax2 = ax.twinx()
    bars1 = ax.bar(x - width/2, yearly['total_return'] * 100, width, label='Total Return (%)', color='steelblue', alpha=0.7)
    bars2 = ax2.bar(x + width/2, yearly['avg_sharpe'], width, label='Avg Sharpe', color='orange', alpha=0.7)
    ax.set_title('Annual Performance (Per-Window Aggregated)')
    ax.set_xlabel('Year')
    ax.set_ylabel('Total Return (%)', color='steelblue')
    ax2.set_ylabel('Avg Sharpe', color='orange')
    ax.tick_params(axis='y', labelcolor='steelblue')
    ax2.tick_params(axis='y', labelcolor='orange')
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_dir / f"ma_tsm_wf_charts_{suffix}.png", dpi=150, bbox_inches='tight')
    plt.close()

    # Figure 2: Return distribution & win rate
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f'MA-TSM-001 Walk-Forward - Return Distribution & Win Rate by Window', fontsize=14)

    # Return distribution
    ax = axes[0]
    ax.hist(df['net_return'] * 100, bins=min(10, len(df)), edgecolor='black', alpha=0.7, color='steelblue')
    ax.axvline(np.mean(df['net_return'] * 100), color='red', linestyle='--', linewidth=2, label=f'Mean: {np.mean(df["net_return"]*100):.1f}%')
    ax.axvline(np.median(df['net_return'] * 100), color='green', linestyle='--', linewidth=2, label=f'Median: {np.median(df["net_return"]*100):.1f}%')
    ax.set_title('OOS Return Distribution')
    ax.set_xlabel('Return (%)')
    ax.set_ylabel('Frequency')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Win rate by window
    ax = axes[1]
    ax.plot(range(1, len(df) + 1), df['win_rate'] * 100, 'o-', color='purple', linewidth=2, markersize=6)
    ax.axhline(y=np.mean(df['win_rate'] * 100), color='red', linestyle='--', label=f'Mean: {np.mean(df["win_rate"]*100):.1f}%')
    ax.set_title('Win Rate by Window')
    ax.set_xlabel('Window')
    ax.set_ylabel('Win Rate (%)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / f"ma_tsm_wf_distribution_{suffix}.png", dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Visualizations saved to {output_dir}")


def run_cost_scenarios(df: pd.DataFrame, base_config: WalkForwardConfig, output_dir: Path) -> dict:
    """Run walk-forward for all three cost scenarios."""

    scenarios = [
        ("zero", CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0)),
        ("scenario1", CostModel(spread_pips=1.0, commission_per_lot=0.5, slippage_pips=0.5)),
        ("scenario2", CostModel(spread_pips=2.0, commission_per_lot=1.0, slippage_pips=1.0)),
    ]

    all_results = {}

    for name, cost_model in scenarios:
        print(f"\n{'='*60}")
        print(f"Running cost scenario: {name}")
        print(f"{'='*60}")

        wf_config = WalkForwardConfig(
            sma_period=base_config.sma_period,
            initial_train_years=base_config.initial_train_years,
            oos_window_months=base_config.oos_window_months,
            step_months=base_config.step_months,
            cost_model=cost_model,
            position_size_pct=base_config.position_size_pct,
            max_leverage=base_config.max_leverage,
            seed=base_config.seed,
        )

        results = run_walkforward(df, wf_config)
        aggregate = aggregate_results(results)

        suffix = f"sma{base_config.sma_period}_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        save_results(results, aggregate, wf_config, output_dir, suffix)
        report = generate_report(results, aggregate, wf_config, output_dir, suffix)
        create_visualizations(results, aggregate, wf_config, output_dir, suffix)

        print(report)

        all_results[name] = {
            "results": results,
            "aggregate": aggregate,
            "config": wf_config,
        }

    return all_results


def create_cost_comparison_chart(all_results: dict, output_dir: Path, sma_period: int) -> None:
    """Create comparison chart across cost scenarios."""

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'MA-TSM-001 Walk-Forward: Cost Scenario Comparison (SMA-{sma_period})', fontsize=14, fontweight='bold')

    scenarios = ['zero', 'scenario1', 'scenario2']
    labels = ['Zero Costs', 'Spread 1pip / $0.5 comm / 0.5pip slip', 'Spread 2pip / $1.0 comm / 1.0pip slip']
    colors = ['green', 'orange', 'red']

    # Aggregate return comparison
    ax = axes[0, 0]
    agg_returns = [all_results[s]['aggregate']['aggregate_oos_return'] * 100 for s in scenarios]
    bars = ax.bar(labels, agg_returns, color=colors, alpha=0.7, edgecolor='black')
    for bar, val in zip(bars, agg_returns):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f'{val:.1f}%', ha='center', va='bottom')
    ax.set_title('Aggregate OOS Return by Cost Scenario')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    plt.setp(ax.get_xticklabels(), rotation=15, ha='right')

    # Aggregate Sharpe comparison
    ax = axes[0, 1]
    agg_sharpes = [all_results[s]['aggregate']['aggregate_oos_sharpe'] for s in scenarios]
    bars = ax.bar(labels, agg_sharpes, color=colors, alpha=0.7, edgecolor='black')
    for bar, val in zip(bars, agg_sharpes):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01, f'{val:.2f}', ha='center', va='bottom')
    ax.set_title('Aggregate OOS Sharpe by Cost Scenario')
    ax.set_ylabel('Sharpe Ratio')
    ax.grid(True, alpha=0.3, axis='y')
    plt.setp(ax.get_xticklabels(), rotation=15, ha='right')

    # Profitable windows %
    ax = axes[1, 0]
    prof_pcts = [all_results[s]['aggregate']['profitable_pct'] for s in scenarios]
    bars = ax.bar(labels, prof_pcts, color=colors, alpha=0.7, edgecolor='black')
    for bar, val in zip(bars, prof_pcts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{val:.1f}%', ha='center', va='bottom')
    ax.set_title('Profitable Windows % by Cost Scenario')
    ax.set_ylabel('% Profitable')
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_ylim(0, 100)
    plt.setp(ax.get_xticklabels(), rotation=15, ha='right')

    # Mean win rate
    ax = axes[1, 1]
    win_rates = [all_results[s]['aggregate']['mean_win_rate'] * 100 for s in scenarios]
    bars = ax.bar(labels, win_rates, color=colors, alpha=0.7, edgecolor='black')
    for bar, val in zip(bars, win_rates):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f'{val:.1f}%', ha='center', va='bottom')
    ax.set_title('Mean Win Rate by Cost Scenario')
    ax.set_ylabel('Win Rate (%)')
    ax.grid(True, alpha=0.3, axis='y')
    plt.setp(ax.get_xticklabels(), rotation=15, ha='right')

    plt.tight_layout()
    plt.savefig(output_dir / f"ma_tsm_wf_cost_comparison_sma{sma_period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                dpi=150, bbox_inches='tight')
    plt.close()

    # Also create window-by-window comparison
    fig, ax = plt.subplots(figsize=(14, 6))
    x = np.arange(len(all_results['zero']['results']))
    width = 0.25
    for i, (scenario, label, color) in enumerate(zip(scenarios, labels, colors)):
        returns = [r.net_return * 100 for r in all_results[scenario]['results']]
        ax.bar(x + i * width, returns, width, label=label, color=color, alpha=0.7, edgecolor='black')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_title('OOS Return by Window - Cost Scenario Comparison')
    ax.set_xlabel('Window')
    ax.set_ylabel('Return (%)')
    ax.set_xticks(x + width)
    ax.set_xticklabels([str(i+1) for i in x])
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_dir / f"ma_tsm_wf_window_comparison_sma{sma_period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Cost comparison charts saved to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="MA-TSM-001 Walk-Forward Validation")
    parser.add_argument("--sma-period", type=int, default=200, help="SMA period")
    parser.add_argument("--initial-train-years", type=int, default=2, help="Initial training years")
    parser.add_argument("--oos-window-months", type=int, default=6, help="OOS window months")
    parser.add_argument("--step-months", type=int, default=6, help="Step months (expanding)")
    parser.add_argument("--spread-pips", type=float, default=0.0, help="Spread in pips")
    parser.add_argument("--commission", type=float, default=0.0, help="Commission per lot")
    parser.add_argument("--slippage-pips", type=float, default=0.0, help="Slippage in pips")
    parser.add_argument("--position-size", type=float, default=1.0, help="Position size as fraction of equity")
    parser.add_argument("--max-leverage", type=float, default=1.0, help="Max leverage")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--run-all-scenarios", action="store_true", help="Run all three cost scenarios")
    args = parser.parse_args()

    print("Loading data...")
    paths = ProjectPaths.from_root()
    config = MATSMConfig(
        symbol="XAUUSD",
        timeframe="h1",
        sma_period=args.sma_period,
        data_path=None,
    )
    df = load_and_validate_data(config, paths)

    print(f"Data loaded: {len(df)} bars, {df.index[0]} to {df.index[-1]}")

    output_dir = Path("reports/walkforward")

    if args.run_all_scenarios:
        base_config = WalkForwardConfig(
            sma_period=args.sma_period,
            initial_train_years=args.initial_train_years,
            oos_window_months=args.oos_window_months,
            step_months=args.step_months,
            cost_model=CostModel(spread_pips=0.0, commission_per_lot=0.0, slippage_pips=0.0),
            position_size_pct=args.position_size,
            max_leverage=args.max_leverage,
            seed=args.seed,
        )
        all_results = run_cost_scenarios(df, base_config, output_dir)
        create_cost_comparison_chart(all_results, output_dir, args.sma_period)
    else:
        cost_model = CostModel(
            spread_pips=args.spread_pips,
            commission_per_lot=args.commission,
            slippage_pips=args.slippage_pips,
        )
        wf_config = WalkForwardConfig(
            sma_period=args.sma_period,
            initial_train_years=args.initial_train_years,
            oos_window_months=args.oos_window_months,
            step_months=args.step_months,
            cost_model=cost_model,
            position_size_pct=args.position_size,
            max_leverage=args.max_leverage,
            seed=args.seed,
        )

        results = run_walkforward(df, wf_config)
        aggregate = aggregate_results(results)

        suffix = f"sma{args.sma_period}_spread{args.spread_pips}_comm{args.commission}_slip{args.slippage_pips}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        save_results(results, aggregate, wf_config, output_dir, suffix)
        report = generate_report(results, aggregate, wf_config, output_dir, suffix)
        create_visualizations(results, aggregate, wf_config, output_dir, suffix)

        print(report)


if __name__ == "__main__":
    main()