"""
M.A.R.S. MA-TSM-001: Moving-Average Time-Series Momentum Research (Assignment 09)

Hypothesis: Gold (XAUUSD) exhibits persistent directional price movements over certain
market regimes. A long-term moving-average filter may help identify bullish trends and
avoid exposure during bearish or unfavorable regimes.

Strategy: Long-only, flat when trend filter is bearish.
- Entry: When H1 close crosses above the 200-period SMA, enter long.
- Position: Hold long while close remains above the SMA.
- Exit: When H1 close crosses below the SMA, exit and remain flat.
- No short positions.
- No parameter optimization.
- No additional filters.
- No pyramiding.
- No discretionary intervention.

The 200-period SMA is selected as a conventional baseline before testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
import vectorbt as vbt

from mars.libs.data.loaders import load_ohlcv_parquet
from mars.libs.evaluation.report import write_text_report
from mars.libs.evaluation.splits import time_series_split
from mars.libs.utils.paths import ProjectPaths
from mars.research.experiment import ExperimentLog, ExperimentRecord


# ============================================================================
# Configuration
# ============================================================================

@dataclass(frozen=True)
class CostModel:
    """Configurable transaction cost assumptions (no historical bid/ask available)."""
    spread_pips: float = 0.0          # e.g., 1.0 pip on XAUUSD
    commission_per_lot: float = 0.0   # round-trip commission in USD per lot
    slippage_pips: float = 0.0        # per-side slippage in pips

    def per_round_trip_usd_per_lot(self) -> float:
        """Total cost per round-trip per 1.0 lot on XAUUSD.

        XAUUSD: 1 lot = 100 oz, 1 pip = $0.01/oz -> $10 per lot per pip.
        """
        pip_value_per_lot = 10.0
        spread_cost = self.spread_pips * pip_value_per_lot
        slippage_cost = 2 * self.slippage_pips * pip_value_per_lot  # entry + exit
        return spread_cost + slippage_cost + self.commission_per_lot


@dataclass(frozen=True)
class MATSMConfig:
    """Immutable experiment configuration for MA-TSM-001."""
    symbol: str = "XAUUSD"
    timeframe: Literal["m5", "h1"] = "h1"
    data_path: Optional[str] = None  # auto-resolved if None
    # SMA parameters
    sma_period: int = 200             # Simple Moving Average period
    # Execution
    position_size_pct: float = 1.0    # 1.0 = 100% equity per trade (unlevered, fixed fractional)
    max_leverage: float = 1.0
    cost_model: CostModel = field(default_factory=CostModel)
    # Data splits
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    seed: int = 42


# ============================================================================
# Data Loading & Validation
# ============================================================================

def load_and_validate_data(
    config: MATSMConfig,
    paths: ProjectPaths,
) -> pd.DataFrame:
    """Load XAUUSD OHLCV, validate, return timestamp-indexed DataFrame in UTC."""
    if config.data_path:
        data_path = Path(config.data_path)
    else:
        data_path = paths.processed_data / config.symbol.lower() / config.timeframe / "v1.0.0" / "data.parquet"

    # Fallback for H1: use raw data if processed not found
    if not data_path.exists() and config.timeframe == "h1":
        fallback = paths.root / "data" / "raw" / "xauusd_h1_2015_present.parquet"
        if fallback.exists():
            data_path = fallback

    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    df = load_ohlcv_parquet(data_path, symbol=config.symbol.lower(), timeframe=config.timeframe)

    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    df = df.sort_index()

    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.dropna(subset=["open", "high", "low", "close"])

    print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    print(f"Timeframe: {config.timeframe} | Symbol: {config.symbol}")
    return df


# ============================================================================
# SMA Calculation & Signal Generation
# ============================================================================

def compute_sma_signals(
    df: pd.DataFrame,
    sma_period: int,
) -> pd.DataFrame:
    """Compute SMA and generate trend-following signals using completed bars only.

    Signal logic (long-only):
    - Entry: close > SMA (close crosses above SMA)
    - Exit: close < SMA (close crosses below SMA)
    - All signals shift by 1 to use only completed bars (no lookahead)

    Execution assumption: Entry/Exit at NEXT bar's open after signal.
    """
    out = df.copy()

    # Compute SMA on PRIOR bars only (shift by 1 to avoid lookahead)
    # SMA at bar i = mean of close[i-sma_period : i-1]
    close_prev = out["close"].shift(1)
    sma = close_prev.rolling(window=sma_period, min_periods=sma_period).mean()
    out["sma"] = sma

    # Signal generation using shifted SMA (no lookahead)
    # Entry: current close > prior SMA
    # Exit: current close < prior SMA
    out["entry_signal"] = ((out["close"] > out["sma"]) & (out["close"].shift(1) <= out["sma"].shift(1))).astype(int)
    out["exit_signal"] = ((out["close"] < out["sma"]) & (out["close"].shift(1) >= out["sma"].shift(1))).astype(int)

    # First sma_period bars have NaN SMA -> no signal
    out.loc[out["sma"].isna(), "entry_signal"] = 0
    out.loc[out["sma"].isna(), "exit_signal"] = 0

    # Convert to position state: 1 = long, 0 = flat
    position = 0
    positions = []
    for i in range(len(out)):
        if out.iloc[i]["entry_signal"] == 1 and position == 0:
            position = 1
        elif out.iloc[i]["exit_signal"] == 1 and position == 1:
            position = 0
        positions.append(position)

    out["position"] = positions

    # Entry/exit events (changes in position)
    out["position_prev"] = out["position"].shift(1).fillna(0).astype(int)
    out["entry_event"] = ((out["position"] == 1) & (out["position_prev"] == 0)).astype(int)
    out["exit_event"] = ((out["position"] == 0) & (out["position_prev"] == 1)).astype(int)

    return out


# ============================================================================
# VectorBT Portfolio Simulation
# ============================================================================

def run_vectorbt_portfolio(
    df: pd.DataFrame,
    config: MATSMConfig,
    init_cash: float = 10_000_000.0,
) -> vbt.Portfolio:
    """Run VectorBT portfolio simulation using from_orders for precise price control.

    Entry: at NEXT bar's open after entry_signal (no retroactive fill at signal bar close)
    Exit: at NEXT bar's open after exit_signal

    This ensures no lookahead — we only act on information available at bar close,
    executing at the next available price (next bar open).
    """
    # Get entry and exit timestamps
    entry_mask = df["entry_event"] == 1
    exit_mask = df["exit_event"] == 1

    # Execution at NEXT bar's open
    # For the last bar, there is no "next bar" — skip
    entry_indices = df.index[entry_mask][:-1] if entry_mask.any() else []
    exit_indices = df.index[exit_mask][:-1] if exit_mask.any() else []

    if len(entry_indices) == 0:
        # No trades - create empty portfolio
        pf = vbt.Portfolio.from_signals(
            close=df["close"],
            entries=pd.Series(False, index=df.index),
            exits=pd.Series(False, index=df.index),
            size=pd.Series(0.0, index=df.index),
            size_type="amount",
            init_cash=init_cash,
            freq=pd.infer_freq(df.index) or ("5min" if config.timeframe == "m5" else "1h"),
        )
        return pf

    # Position size in base asset units (oz): 1 lot = 100 oz
    position_lots = config.position_size_pct * (100000.0 / 100000.0) * config.max_leverage
    contract_size = 100.0  # XAUUSD = 100 oz per lot
    position_oz = position_lots * contract_size

    # Build order series
    order_sizes = []
    order_prices = []
    order_timestamps = []

    # Entries at NEXT bar's open
    for idx in entry_indices:
        loc = df.index.get_indexer([idx])[0]
        next_idx = loc + 1
        if next_idx < len(df):
            entry_price = df.iloc[next_idx]["open"]
            order_sizes.append(position_oz)
            order_prices.append(entry_price)
            order_timestamps.append(df.index[next_idx])

    # Exits at NEXT bar's open
    for idx in exit_indices:
        loc = df.index.get_indexer([idx])[0]
        next_idx = loc + 1
        if next_idx < len(df):
            exit_price = df.iloc[next_idx]["open"]
            order_sizes.append(-position_oz)
            order_prices.append(exit_price)
            order_timestamps.append(df.index[next_idx])

    # Create order series aligned to df index
    size_series = pd.Series(0.0, index=df.index)
    price_series = df["close"].copy()

    for ts, sz, px in zip(order_timestamps, order_sizes, order_prices):
        size_series.loc[ts] = sz
        price_series.loc[ts] = px

    # Fixed fee per order side (entry and exit each)
    cost_per_lot_usd = config.cost_model.per_round_trip_usd_per_lot()
    fixed_fee_per_order = cost_per_lot_usd / 2.0  # split round-trip cost between entry and exit

    # Run portfolio simulation
    pf = vbt.Portfolio.from_orders(
        close=df["close"],
        size=size_series,
        price=price_series,
        size_type="amount",  # size in base asset units (oz)
        init_cash=init_cash,
        fixed_fees=fixed_fee_per_order,
        slippage=0.0,  # already included in fixed_fees
        freq=pd.infer_freq(df.index) or ("5min" if config.timeframe == "m5" else "1h"),
        cash_sharing=False,  # Each trade independent (fixed position sizing)
        group_by=False,
        direction="longonly",
    )

    return pf


# ============================================================================
# Metrics & Reporting
# ============================================================================

def compute_metrics(pf: vbt.Portfolio, config: MATSMConfig, df: pd.DataFrame) -> dict[str, Any]:
    """Compute performance metrics from VectorBT portfolio."""
    trades = pf.trades.records_readable
    if len(trades) == 0:
        return {"error": "No trades executed"}

    # Get bar-level equity curve from VectorBT portfolio (correct approach)
    equity_curve = pf.value()
    equity_rets = equity_curve.pct_change().dropna()

    # Net P&L from VectorBT (includes fees) - for trade-level stats only
    net_pnls = trades["PnL"].values
    # Gross P&L (before fees)
    entry_fees = trades["Entry Fees"].values
    exit_fees = trades["Exit Fees"].values
    total_fees = entry_fees + exit_fees
    gross_pnls = net_pnls + total_fees

    n_trades = len(trades)
    n_wins_net = (net_pnls > 0).sum()
    n_wins_gross = (gross_pnls > 0).sum()
    win_rate_net = n_wins_net / n_trades
    win_rate_gross = n_wins_gross / n_trades

    expectancy_net = net_pnls.mean()
    expectancy_gross = gross_pnls.mean()

    gross_profit = gross_pnls[gross_pnls > 0].sum()
    gross_loss = -gross_pnls[gross_pnls < 0].sum()
    profit_factor_gross = gross_profit / gross_loss if gross_loss > 0 else np.inf

    net_profit = net_pnls[net_pnls > 0].sum()
    net_loss = -net_pnls[net_pnls < 0].sum()
    profit_factor_net = net_profit / net_loss if net_loss > 0 else np.inf

    # === CORRECT: Metrics from bar-level equity curve returns ===
    bars_per_year = 252 * (24 * 12 if config.timeframe == "m5" else 24)  # approximate
    
    # Total return from equity curve
    total_return = float((1 + equity_rets).prod() - 1)
    
    # Annualized return
    n_bars = len(equity_rets)
    years = n_bars / bars_per_year
    ann_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    
    # Annualized volatility and Sharpe
    ann_vol = float(equity_rets.std() * np.sqrt(bars_per_year))
    sharpe = float(ann_return / ann_vol) if ann_vol > 0 else 0.0

    # Sortino (downside deviation)
    downside = equity_rets[equity_rets < 0]
    sortino = float(ann_return / (downside.std() * np.sqrt(bars_per_year))) if len(downside) > 0 and downside.std() > 0 else 0.0

    # Max drawdown from equity curve
    cum = (1 + equity_rets).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = float(dd.min())

    # Calmar
    calmar = float(ann_return / abs(max_dd)) if max_dd != 0 else 0.0

    # Trade-level returns for reference (not used for Sharpe/DD)
    equity_ref = 100000.0
    returns_gross = gross_pnls / equity_ref
    returns_net = net_pnls / equity_ref
    cum_gross = (1 + returns_gross).prod() - 1
    cum_net = (1 + returns_net).prod() - 1
    avg_trade_return_bps = float(returns_net.mean() * 10000)

    # Average holding period
    durations = trades["Exit Timestamp"] - trades["Entry Timestamp"]
    avg_holding = durations.mean()

    # Exposure (fraction of bars in market)
    total_hours_in_market = durations.sum().total_seconds() / 3600.0
    total_hours_in_data = (df.index[-1] - df.index[0]).total_seconds() / 3600.0
    exposure = float(total_hours_in_market / total_hours_in_data) if total_hours_in_data > 0 else 0.0

    # Turnover
    turnover = float(n_trades * config.position_size_pct)

    return {
        "n_trades": int(n_trades),
        "win_rate_gross": float(win_rate_gross),
        "win_rate_net": float(win_rate_net),
        "expectancy_gross_usd": float(expectancy_gross),
        "expectancy_net_usd": float(expectancy_net),
        "profit_factor_gross": float(profit_factor_gross),
        "profit_factor_net": float(profit_factor_net),
        "total_return_gross": float(cum_gross),
        "total_return_net": float(cum_net),
        "annualized_return_gross": float(ann_return),  # Now from equity curve
        "annualized_return_net": float(ann_return),   # Now from equity curve
        "annualized_vol_gross": ann_vol,
        "annualized_vol_net": ann_vol,
        "sharpe_gross": sharpe,
        "sharpe_net": sharpe,
        "sortino_gross": sortino,
        "sortino_net": sortino,
        "calmar_gross": calmar,
        "calmar_net": calmar,
        "max_drawdown_gross": max_dd,
        "max_drawdown_net": max_dd,
        "avg_holding_period": str(avg_holding),
        "exposure": exposure,
        "turnover": turnover,
        "avg_trade_return_bps": avg_trade_return_bps,
        "gross_profit_usd": float(gross_profit),
        "gross_loss_usd": float(gross_loss),
        "net_profit_usd": float(net_profit),
        "net_loss_usd": float(net_loss),
    }


def compute_benchmarks(df: pd.DataFrame) -> dict[str, Any]:
    """Compute buy-and-hold benchmark."""
    first_open = df.iloc[0]["open"]
    last_close = df.iloc[-1]["close"]
    bh_return = (last_close - first_open) / first_open

    bars_per_year = 252 * 24  # H1: 252 trading days * 24 hours
    n_bars = len(df)
    years = n_bars / bars_per_year
    bh_annual = (1 + bh_return) ** (1 / years) - 1 if years > 0 else 0

    return {
        "buy_and_hold_return": float(bh_return),
        "buy_and_hold_annualized": float(bh_annual),
        "flat_return": 0.0,
    }


def performance_by_year(pf: vbt.Portfolio) -> pd.DataFrame:
    """Break down performance by year."""
    trades = pf.trades.records_readable
    if len(trades) == 0:
        return pd.DataFrame()

    trade_df = trades.copy()
    trade_df["year"] = trade_df["Entry Timestamp"].dt.year
    trade_df["duration"] = trade_df["Exit Timestamp"] - trade_df["Entry Timestamp"]

    by_year = trade_df.groupby("year").agg(
        n_trades=("PnL", "count"),
        win_rate=("PnL", lambda x: (x > 0).mean()),
        avg_pnl=("PnL", "mean"),
        total_pnl=("PnL", "sum"),
        avg_holding=("duration", lambda x: x.mean()),
    )

    # Round numeric columns only
    numeric_cols = ["win_rate", "avg_pnl", "total_pnl"]
    by_year[numeric_cols] = by_year[numeric_cols].round(4)

    return by_year


def performance_by_month(pf: vbt.Portfolio) -> pd.DataFrame:
    """Break down performance by month."""
    trades = pf.trades.records_readable
    if len(trades) == 0:
        return pd.DataFrame()

    trade_df = trades.copy()
    trade_df["year_month"] = trade_df["Entry Timestamp"].dt.to_period("M")
    trade_df["duration"] = trade_df["Exit Timestamp"] - trade_df["Entry Timestamp"]

    by_month = trade_df.groupby("year_month").agg(
        n_trades=("PnL", "count"),
        win_rate=("PnL", lambda x: (x > 0).mean()),
        avg_pnl=("PnL", "mean"),
        total_pnl=("PnL", "sum"),
        avg_holding=("duration", lambda x: x.mean()),
    )

    # Round numeric columns only
    numeric_cols = ["win_rate", "avg_pnl", "total_pnl"]
    by_month[numeric_cols] = by_month[numeric_cols].round(4)

    return by_month


# ============================================================================
# Main Experiment Runner
# ============================================================================

def run_experiment(config: MATSMConfig) -> dict[str, Any]:
    """Execute the full MA-TSM-001 experiment using VectorBT."""
    paths = ProjectPaths.from_root()

    # --- 1. Load & validate data ---
    print("[1/8] Loading and validating data...")
    df = load_and_validate_data(config, paths)

    # --- 2. Compute SMA and signals ---
    print("[2/8] Computing SMA and signals...")
    df = compute_sma_signals(df, config.sma_period)
    n_entries = df["entry_event"].sum()
    n_exits = df["exit_event"].sum()
    print(f"      Entry events: {n_entries} | Exit events: {n_exits}")

    # --- 3. Time-series split ---
    print("[3/8] Applying chronological train/val/test split...")
    split = time_series_split(
        df.index,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
    )
    print(split.describe())

    df["split"] = "test"
    df.loc[split.train_idx, "split"] = "train"
    if len(split.val_idx) > 0:
        df.loc[split.val_idx, "split"] = "val"

    # --- 4. Run VectorBT portfolio ---
    print("[4/8] Running VectorBT portfolio simulation...")
    pf = run_vectorbt_portfolio(df, config)

    # --- 5. Compute metrics ---
    print("[5/8] Computing performance metrics...")
    metrics = compute_metrics(pf, config, df)
    benchmarks = compute_benchmarks(df)
    by_year = performance_by_year(pf)
    by_month = performance_by_month(pf)

    # Add split-specific metrics
    for split_name in ["train", "val", "test"]:
        split_mask = df["split"] == split_name
        if split_mask.any():
            split_entries = df.loc[split_mask, "entry_event"].astype(bool)
            if split_entries.any():
                split_df = df[split_mask].copy()
                split_pf = run_vectorbt_portfolio(split_df, config)
                split_metrics = compute_metrics(split_pf, config, split_df)
                metrics[f"{split_name}_metrics"] = split_metrics

    # --- 6. Save artifacts & report ---
    print("[6/8] Saving artifacts and report...")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    exp_log = ExperimentLog(hypothesis_root=paths.root / "research" / "hypotheses")
    exp_record = ExperimentRecord(
        hypothesis_id="MA-TSM-001",
        name=f"XAUUSD MA Trend-Following (SMA-{config.sma_period})",
        description=f"Long-only SMA trend-following ({config.sma_period}-period) on {config.timeframe} data",
        dataset_ids=[str(paths.processed_data / config.symbol.lower() / config.timeframe / "v1.0.0" / "data.parquet")],
        parameters={
            "config": config.__dict__,
            "sma_period": config.sma_period,
        },
        seed=config.seed,
    )
    exp_path = exp_log.write(exp_record)

    # Save trades
    trades_df = pf.trades.records_readable
    trades_path = paths.artifacts / f"ma_tsm_vbt_trades_{stamp}.parquet"
    paths.artifacts.mkdir(parents=True, exist_ok=True)
    trades_df.to_parquet(trades_path)

    # Save equity curve
    equity_curve = pf.value()
    equity_path = paths.artifacts / f"ma_tsm_vbt_equity_{stamp}.parquet"
    equity_curve.to_frame(name="equity").to_parquet(equity_path)

    # Save signals
    signal_cols = ["sma", "entry_signal", "exit_signal", "position", "entry_event", "exit_event", "split"]
    signal_df = df[signal_cols].copy()
    signal_path = paths.artifacts / f"ma_tsm_vbt_signals_{stamp}.parquet"
    signal_df.to_parquet(signal_path)

    # Complete experiment log (exploratory - don't lock test set)
    exp_log.complete(
        exp_record.experiment_id,
        metrics=metrics,
        artifacts=[str(trades_path), str(equity_path), str(signal_path), str(exp_path)],
        evaluated_on_test=False,
    )

    # --- 7. Build report ---
    print("[7/8] Building report...")
    assumptions = f"""
ASSUMPTIONS & LIMITATIONS
-------------------------
- Data: XAUUSD {config.timeframe} OHLCV from {df.index[0].date()} to {df.index[-1].date()} (no bid/ask, no historical spreads)
- SMA calculation: 200-period Simple Moving Average on PRIOR bars only (shifted by 1)
- Signal: Entry on close crossing above SMA; Exit on close crossing below SMA
- Execution: Next bar open after signal (no retroactive fill at signal bar close)
- Position sizing: Fixed fractional ({config.position_size_pct:.0%} equity, max leverage {config.max_leverage:.1f}x) = 1 lot (100 oz)
- Cost model: spread={config.cost_model.spread_pips} pips, commission=${config.cost_model.commission_per_lot}/lot, slippage={config.cost_model.slippage_pips} pips/side
  -> Total round-trip cost: ${config.cost_model.per_round_trip_usd_per_lot():.2f} per lot
- Long-only strategy (no shorts)
- No swap costs (not modeled for trend-following)
- Missing bars: sessions with insufficient bars excluded implicitly
- No parameter optimization; single baseline configuration tested (SMA-200)
- Walk-forward, Monte Carlo, regime segmentation NOT applied (future validation stages)
- Benchmarks: Buy-and-hold (first open to last close), Flat (zero)
- VectorBT version: {vbt.__version__}
""".strip()

    sections = [
        f"Experiment: XAUUSD MA Trend-Following (MA-TSM-001) — VectorBT",
        f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Config: {config.__dict__}",
        "",
        "DATA",
        f"Source: {paths.processed_data / config.symbol.lower() / config.timeframe / 'v1.0.0' / 'data.parquet'}",
        f"Bars: {len(df)} | Range: {df.index[0]} → {df.index[-1]}",
        "",
        "SPLITS",
        split.describe(),
        "",
        "SIGNALS",
        f"SMA period: {config.sma_period}",
        f"Entry events: {int(n_entries)} | Exit events: {int(n_exits)}",
        "",
        "PERFORMANCE (NET, ALL DATA)",
        f"Trades: {metrics['n_trades']}",
        f"Win Rate: {metrics['win_rate_net']:.2%}",
        f"Expectancy: ${metrics['expectancy_net_usd']:.2f}/trade",
        f"Avg Trade Return: {metrics['avg_trade_return_bps']:.2f} bps",
        f"Profit Factor: {metrics['profit_factor_net']:.2f}",
        f"Total Return: {metrics['total_return_net']:.2%}",
        f"Ann. Return: {metrics['annualized_return_net']:.2%} | Ann. Vol: {metrics['annualized_vol_net']:.2%}",
        f"Sharpe: {metrics['sharpe_net']:.2f}",
        f"Sortino: {metrics['sortino_net']:.2f}",
        f"Calmar: {metrics['calmar_net']:.2f}",
        f"Max Drawdown: {metrics['max_drawdown_net']:.2%}",
        f"Exposure: {metrics['exposure']:.2%} | Turnover: {metrics['turnover']:.2f}",
        f"Avg Holding: {metrics['avg_holding_period']}",
        "",
        "PERFORMANCE (GROSS, ALL DATA)",
        f"Win Rate: {metrics['win_rate_gross']:.2%}",
        f"Expectancy: ${metrics['expectancy_gross_usd']:.2f}/trade",
        f"Profit Factor: {metrics['profit_factor_gross']:.2f}",
        f"Total Return: {metrics['total_return_gross']:.2%}",
        f"Ann. Return: {metrics['annualized_return_gross']:.2%} | Sharpe: {metrics['sharpe_gross']:.2f}",
        f"Max Drawdown: {metrics['max_drawdown_gross']:.2%}",
        "",
        "BENCHMARKS",
        f"Buy-and-Hold: {benchmarks['buy_and_hold_return']:.2%} (ann. {benchmarks['buy_and_hold_annualized']:.2%})",
        f"Flat: {benchmarks['flat_return']:.2%}",
        "",
        "BY YEAR (NET)",
        by_year.to_string() if not by_year.empty else "No trades",
        "",
        "BY MONTH (NET, first 24 months)",
        by_month.head(24).to_string() if not by_month.empty else "No trades",
        "",
        "SPLIT-SPECIFIC METRICS",
        *([f"Train: {m}" for k, m in metrics.items() if k.endswith("_metrics") and "train" in k]),
        *([f"Val: {m}" for k, m in metrics.items() if k.endswith("_metrics") and "val" in k]),
        *([f"Test: {m}" for k, m in metrics.items() if k.endswith("_metrics") and "test" in k]),
        "",
        assumptions,
    ]

    report_path = paths.reports / f"ma_tsm_vbt_xauusd_{config.timeframe}_sma{config.sma_period}_{stamp}.txt"
    write_text_report(report_path, sections, title="M.A.R.S. MA-TSM-001 Experiment — VectorBT")

    print(f"Report: {report_path}")
    print(f"Trades: {trades_path}")
    print(f"Equity curve: {equity_path}")
    print(f"Signals: {signal_path}")
    print(f"Experiment log: {exp_path}")

    return {
        "config": config,
        "metrics": metrics,
        "benchmarks": benchmarks,
        "by_year": by_year,
        "by_month": by_month,
        "split": split,
        "portfolio": pf,
        "trades_path": str(trades_path),
        "equity_path": str(equity_path),
        "signal_path": str(signal_path),
        "report_path": str(report_path),
        "experiment_id": exp_record.experiment_id,
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="M.A.R.S. MA-TSM-001 Experiment — VectorBT")
    parser.add_argument("--timeframe", choices=["m5", "h1"], default="h1")
    parser.add_argument("--data-path", type=str, default=None, help="Path to OHLCV parquet file")
    parser.add_argument("--sma-period", type=int, default=200)
    parser.add_argument("--position-pct", type=float, default=1.0)
    parser.add_argument("--spread-pips", type=float, default=0.0)
    parser.add_argument("--commission", type=float, default=0.0)
    parser.add_argument("--slippage-pips", type=float, default=0.0)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    cost_model = CostModel(
        spread_pips=args.spread_pips,
        commission_per_lot=args.commission,
        slippage_pips=args.slippage_pips,
    )

    config = MATSMConfig(
        timeframe=args.timeframe,
        data_path=args.data_path,
        sma_period=args.sma_period,
        position_size_pct=args.position_pct,
        cost_model=cost_model,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
    )

    result = run_experiment(config)
    print("\n=== SUMMARY ===")
    m = result["metrics"]
    print(f"Net Sharpe: {m['sharpe_net']:.2f} | Net Return: {m['total_return_net']:.2%} | Max DD: {m['max_drawdown_net']:.2%}")
    print(f"Trades: {m['n_trades']} | Win Rate: {m['win_rate_net']:.2%} | PF: {m['profit_factor_net']:.2f}")


if __name__ == "__main__":
    main()