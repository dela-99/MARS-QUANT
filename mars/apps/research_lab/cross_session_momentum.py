"""
M.A.R.S. Cross-Session Momentum Experiment: XAUUSD H1/M5

Research Hypothesis (from "Who Moves the Price? Trading-Session Return 
Decomposition and Cross-Session Momentum in Gold and Silver Markets"):

Previous-session gold returns may predict returns during the following 
trading session.

Signal Rule:
- Positive previous-session return: enter long for the next session
- Otherwise: remain flat

Session Definitions (UTC, fixed — no DST adjustment):
- Asia:      00:00–08:00 UTC
- Europe:    08:00–14:30 UTC
- US:        14:30–24:00 UTC

Note: Fixed UTC definitions mean seasonal distortions occur during DST 
transitions (Europe/US sessions shift relative to local market hours). 
This is documented but not silently corrected.

No look-ahead bias: signal for session N uses only session N-1 data 
(available at session N open). Entry at session N open, exit at session N close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

from mars.libs.data.loaders import load_ohlcv_parquet
from mars.libs.evaluation.metrics import regression_metrics
from mars.libs.evaluation.report import write_text_report
from mars.libs.evaluation.splits import time_series_split, TimeSeriesSplitResult
from mars.libs.utils.paths import ProjectPaths
from mars.research.experiment import ExperimentLog, ExperimentRecord


# ============================================================================
# Session Definitions (Fixed UTC — no DST)
# ============================================================================

SessionName = Literal["asia", "europe", "us"]

SESSION_BOUNDARIES_UTC: dict[SessionName, tuple[time, time]] = {
    "asia": (time(0, 0, tzinfo=timezone.utc), time(8, 0, tzinfo=timezone.utc)),
    "europe": (time(8, 0, tzinfo=timezone.utc), time(14, 30, tzinfo=timezone.utc)),
    "us": (time(14, 30, tzinfo=timezone.utc), time(23, 59, 59, 999999, tzinfo=timezone.utc)),
}

SESSION_ORDER: list[SessionName] = ["asia", "europe", "us"]

# Mapping from session to its "next" session for signal application
SESSION_TRANSITIONS: dict[SessionName, SessionName] = {
    "asia": "europe",
    "europe": "us",
    "us": "asia",  # next day's Asia
}


@dataclass(frozen=True)
class CostModel:
    """Configurable transaction cost assumptions (no historical bid/ask available)."""
    spread_pips: float = 0.0          # e.g., 1.0 pip = $0.10 per lot on XAUUSD
    commission_per_lot: float = 0.0   # round-trip commission in USD per lot
    slippage_pips: float = 0.0        # per-side slippage in pips
    swap_per_lot_per_session: float = 0.0  # not used for intraday session holds

    def per_round_trip_usd_per_lot(self) -> float:
        """Total cost per round-trip per 1.0 lot."""
        # 1 pip on XAUUSD = $0.10 per lot (contract size = 100 oz, 1 pip = $0.01/oz)
        pip_value_per_lot = 10.0  # $10 per pip per standard lot (100 oz * $0.01)
        spread_cost = self.spread_pips * pip_value_per_lot
        slippage_cost = 2 * self.slippage_pips * pip_value_per_lot  # entry + exit
        return spread_cost + slippage_cost + self.commission_per_lot


@dataclass(frozen=True)
class ExperimentConfig:
    """Immutable experiment configuration."""
    symbol: str = "XAUUSD"
    timeframe: str = "m5"  # m5 or h1
    data_path: Optional[str] = None  # auto-resolved if None
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us")
    # Signal: "previous_session_return" (paper's rule) or "previous_session_direction"
    signal_mode: Literal["return", "direction"] = "direction"
    # Position sizing: fixed fractional of equity
    position_size_pct: float = 1.0  # 1.0 = 100% equity per trade (unlevered)
    max_leverage: float = 1.0
    # Cost model
    cost_model: CostModel = field(default_factory=CostModel)
    # Data splits
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    # Random seed for reproducibility
    seed: int = 42


# ============================================================================
# Data Loading & Session Slicing
# ============================================================================

def load_and_validate_data(
    config: ExperimentConfig,
    paths: ProjectPaths,
) -> pd.DataFrame:
    """Load XAUUSD OHLCV, validate, return timestamp-indexed DataFrame in UTC."""
    if config.data_path:
        data_path = Path(config.data_path)
    else:
        # Default to processed M5 data
        data_path = paths.processed_data / config.symbol.lower() / config.timeframe / "v1.0.0" / "data.parquet"
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    df = load_ohlcv_parquet(data_path, symbol=config.symbol.lower(), timeframe=config.timeframe)
    
    # Ensure timestamp index in UTC
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    
    df = df.sort_index()
    
    # Validate required columns
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Drop rows with NaN OHLC
    df = df.dropna(subset=["open", "high", "low", "close"])
    
    print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    print(f"Timeframe: {config.timeframe} | Symbol: {config.symbol}")
    return df


def assign_session_labels(
    df: pd.DataFrame,
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us"),
) -> pd.DataFrame:
    """Assign each bar to a session based on UTC hour."""
    df = df.copy()
    
    # Extract hour and minute from UTC timestamp
    hour = df.index.hour
    minute = df.index.minute
    
    def get_session(h: int, m: int) -> str:
        total_min = h * 60 + m
        if 0 <= total_min < 8 * 60:
            return "asia"
        elif 8 * 60 <= total_min < 14 * 60 + 30:
            return "europe"
        else:
            return "us"
    
    df["session"] = [get_session(h, m) for h, m in zip(hour, minute)]
    df["date"] = df.index.date
    return df


def compute_session_returns(
    df: pd.DataFrame,
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us"),
) -> pd.DataFrame:
    """
    Compute session-level OHLC and returns.
    
    For each (date, session):
    - Open = first bar's open in that session
    - Close = last bar's close in that session
    - Return = (close - open) / open
    - Direction = sign(return)
    """
    df = assign_session_labels(df, sessions)
    
    # Group by date + session
    grouped = df.groupby(["date", "session"])
    
    session_bars = grouped.agg(
        session_open=("open", "first"),
        session_high=("high", "max"),
        session_low=("low", "min"),
        session_close=("close", "last"),
        session_volume=("volume", "sum"),
        n_bars=("close", "count"),
    ).reset_index()
    
    # Compute return and direction
    session_bars["session_return"] = (
        (session_bars["session_close"] - session_bars["session_open"]) 
        / session_bars["session_open"]
    )
    session_bars["session_direction"] = np.sign(session_bars["session_return"])
    
    # Create a sortable session datetime (date + session start time)
    session_start_times = {
        "asia": time(0, 0),
        "europe": time(8, 0),
        "us": time(14, 30),
    }
    session_bars["session_start"] = pd.to_datetime([
        datetime.combine(row["date"], session_start_times[row["session"]], tzinfo=timezone.utc)
        for _, row in session_bars.iterrows()
    ])
    session_bars = session_bars.sort_values("session_start").reset_index(drop=True)
    
    # Add session sequence index for transition logic
    session_bars["session_idx"] = range(len(session_bars))
    
    return session_bars


def generate_signals(
    session_bars: pd.DataFrame,
    signal_mode: Literal["return", "direction"] = "direction",
    sessions: tuple[SessionName, ...] = ("asia", "europe", "us"),
) -> pd.DataFrame:
    """
    Generate cross-session momentum signals.
    
    Signal for session N is based on session N-1 return/direction.
    Signal becomes observable at session N open (no look-ahead).
    """
    bars = session_bars.copy()
    
    # Previous session return/direction
    bars["prev_session_return"] = bars["session_return"].shift(1)
    bars["prev_session_direction"] = bars["session_direction"].shift(1)
    
    # Signal: 1 = long, 0 = flat
    if signal_mode == "return":
        bars["signal"] = (bars["prev_session_return"] > 0).astype(int)
    else:  # direction
        bars["signal"] = (bars["prev_session_direction"] > 0).astype(int)
    
    # First session has no previous session -> flat
    bars.loc[0, "signal"] = 0
    
    # Next session for exit (entry at this session open, exit at next session open)
    # We track which session this signal applies to
    bars["entry_session"] = bars["session"]
    bars["exit_session"] = bars["session"].map(SESSION_TRANSITIONS)
    
    return bars


def simulate_trades(
    session_bars: pd.DataFrame,
    config: ExperimentConfig,
    df_bars: pd.DataFrame,
) -> pd.DataFrame:
    """
    Simulate trades at session boundaries.
    
    Entry: at session open price (first bar of session)
    Exit: at session close price (last bar of session)
    Position size: fixed fractional of equity
    Costs: applied per round-trip per lot
    """
    bars = session_bars.copy()
    
    # Get session open/close prices from the original bar data
    # Session open = first bar's open in session
    # Session close = last bar's close in session
    
    # We already have session_open and session_close from compute_session_returns
    bars["entry_price"] = bars["session_open"]
    bars["exit_price"] = bars["session_close"]
    
    # Position size in lots (simplified: 1 lot per 100k equity * position_size_pct)
    # XAUUSD contract size = 100 oz, 1 lot = 100 oz
    # For 100k equity at 100% position = 1 lot
    equity = 100000.0
    bars["position_lots"] = config.position_size_pct * (equity / 100000.0) * config.max_leverage
    
    # Gross P&L per lot
    bars["gross_pnl_per_lot"] = (
        (bars["exit_price"] - bars["entry_price"]) * bars["signal"] * bars["position_lots"] * 100.0
    )
    # 100 = contract size (oz per lot), $1 per oz per $1 price move
    
    # Cost per round-trip
    cost_per_lot = config.cost_model.per_round_trip_usd_per_lot()
    bars["cost_usd"] = bars["signal"] * bars["position_lots"] * cost_per_lot
    
    # Net P&L
    bars["net_pnl"] = bars["gross_pnl_per_lot"] - bars["cost_usd"]
    
    # Trade flag
    bars["is_trade"] = bars["signal"] == 1
    
    return bars


def compute_performance_metrics(
    trades: pd.DataFrame,
    equity: float = 100000.0,
    position_size_pct: float = 1.0,
) -> dict[str, Any]:
    """Compute comprehensive performance metrics."""
    if len(trades) == 0:
        return {"error": "No trades executed"}
    
    # Filter to actual trades only
    trade_pnl = trades[trades["is_trade"]].copy()
    
    if len(trade_pnl) == 0:
        return {"error": "No trades executed (all signals flat)"}
    
    gross_pnls = trade_pnl["gross_pnl_per_lot"].values
    net_pnls = trade_pnl["net_pnl"].values
    returns_gross = gross_pnls / equity
    returns_net = net_pnls / equity
    
    # Basic counts
    n_trades = len(trade_pnl)
    n_wins_gross = (gross_pnls > 0).sum()
    n_wins_net = (net_pnls > 0).sum()
    win_rate_gross = n_wins_gross / n_trades
    win_rate_net = n_wins_net / n_trades
    
    # Expectancy
    expectancy_gross = gross_pnls.mean()
    expectancy_net = net_pnls.mean()
    
    # Profit factor
    gross_profit = gross_pnls[gross_pnls > 0].sum()
    gross_loss = -gross_pnls[gross_pnls < 0].sum()
    profit_factor_gross = gross_profit / gross_loss if gross_loss > 0 else np.inf
    
    net_profit = net_pnls[net_pnls > 0].sum()
    net_loss = -net_pnls[net_pnls < 0].sum()
    profit_factor_net = net_profit / net_loss if net_loss > 0 else np.inf
    
    # Cumulative returns
    cum_gross = (1 + returns_gross).prod() - 1
    cum_net = (1 + returns_net).prod() - 1
    
    # Annualized return (assuming ~252 trading days * 3 sessions = 756 sessions/year)
    sessions_per_year = 252 * 3
    n_sessions = len(trades)
    years = n_sessions / sessions_per_year
    ann_return_gross = (1 + cum_gross) ** (1 / years) - 1 if years > 0 else 0
    ann_return_net = (1 + cum_net) ** (1 / years) - 1 if years > 0 else 0
    
    # Annualized volatility
    ann_vol_gross = returns_gross.std() * np.sqrt(sessions_per_year)
    ann_vol_net = returns_net.std() * np.sqrt(sessions_per_year)
    
    # Sharpe (risk-free = 0)
    sharpe_gross = ann_return_gross / ann_vol_gross if ann_vol_gross > 0 else 0
    sharpe_net = ann_return_net / ann_vol_net if ann_vol_net > 0 else 0
    
    # Max drawdown
    cum_curve_gross = np.cumprod(1 + returns_gross)
    cum_curve_net = np.cumprod(1 + returns_net)
    peak_gross = np.maximum.accumulate(cum_curve_gross)
    peak_net = np.maximum.accumulate(cum_curve_net)
    dd_gross = (cum_curve_gross - peak_gross) / peak_gross
    dd_net = (cum_curve_net - peak_net) / peak_net
    max_dd_gross = dd_gross.min()
    max_dd_net = dd_net.min()
    
    # Average holding period (all sessions are ~6-8h, but we count in sessions)
    avg_holding_sessions = 1.0  # each trade holds exactly 1 session
    
    # Exposure (fraction of sessions invested)
    exposure = n_trades / len(trades)
    
    # Turnover (sum of position changes / equity)
    turnover = n_trades * position_size_pct  # simplified
    
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
        "annualized_return_gross": float(ann_return_gross),
        "annualized_return_net": float(ann_return_net),
        "annualized_vol_gross": float(ann_vol_gross),
        "annualized_vol_net": float(ann_vol_net),
        "sharpe_gross": float(sharpe_gross),
        "sharpe_net": float(sharpe_net),
        "max_drawdown_gross": float(max_dd_gross),
        "max_drawdown_net": float(max_dd_net),
        "avg_holding_sessions": float(avg_holding_sessions),
        "exposure": float(exposure),
        "turnover": float(turnover),
        "gross_profit_usd": float(gross_profit),
        "gross_loss_usd": float(gross_loss),
        "net_profit_usd": float(net_profit),
        "net_loss_usd": float(net_loss),
    }


def compute_benchmarks(
    session_bars: pd.DataFrame,
    equity: float = 100000.0,
) -> dict[str, Any]:
    """Compute buy-and-hold and flat benchmarks."""
    # Buy-and-hold: first session open to last session close
    first_open = session_bars.iloc[0]["session_open"]
    last_close = session_bars.iloc[-1]["session_close"]
    bh_return = (last_close - first_open) / first_open
    bh_annual = (1 + bh_return) ** (1 / (len(session_bars) / (252 * 3))) - 1
    
    # Flat baseline: zero return
    
    return {
        "buy_and_hold_return": float(bh_return),
        "buy_and_hold_annualized": float(bh_annual),
        "flat_return": 0.0,
    }


def performance_by_session_and_year(
    trades: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Break down performance by session type and year."""
    trade_df = trades[trades["is_trade"]].copy()
    
    if len(trade_df) == 0:
        return pd.DataFrame(), pd.DataFrame()
    
    # By session
    trade_df["year"] = trade_df["session_start"].dt.year
    by_session = trade_df.groupby("session").agg(
        n_trades=("net_pnl", "count"),
        win_rate=("net_pnl", lambda x: (x > 0).mean()),
        avg_pnl=("net_pnl", "mean"),
        total_pnl=("net_pnl", "sum"),
    ).round(4)
    
    by_year = trade_df.groupby("year").agg(
        n_trades=("net_pnl", "count"),
        win_rate=("net_pnl", lambda x: (x > 0).mean()),
        avg_pnl=("net_pnl", "mean"),
        total_pnl=("net_pnl", "sum"),
    ).round(4)
    
    return by_session, by_year


def run_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Execute the full cross-session momentum experiment."""
    paths = ProjectPaths.from_root()
    
    # --- 1. Load & validate data ---
    print("[1/7] Loading and validating data...")
    df = load_and_validate_data(config, paths)
    
    # --- 2. Compute session returns ---
    print("[2/7] Computing session returns...")
    session_bars = compute_session_returns(df, config.sessions)
    print(f"      {len(session_bars)} sessions from {session_bars['session_start'].min()} to {session_bars['session_start'].max()}")
    
    # --- 3. Generate signals ---
    print("[3/7] Generating cross-session momentum signals...")
    session_bars = generate_signals(session_bars, config.signal_mode, config.sessions)
    n_signals = session_bars["signal"].sum()
    print(f"      {n_signals} long signals out of {len(session_bars)} sessions ({n_signals/len(session_bars):.1%})")
    
    # --- 4. Time-series split ---
    print("[4/7] Applying chronological train/val/test split...")
    split = time_series_split(
        session_bars.index,  # Use integer index for splitting
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
    )
    print(split.describe())
    
    session_bars["split"] = "test"
    session_bars.loc[split.train_idx, "split"] = "train"
    if len(split.val_idx) > 0:
        session_bars.loc[split.val_idx, "split"] = "val"
    
    # --- 5. Simulate trades ---
    print("[5/7] Simulating trades with cost model...")
    trades = simulate_trades(session_bars, config, df)
    
    # --- 6. Compute metrics ---
    print("[6/7] Computing performance metrics...")
    metrics = compute_performance_metrics(trades, position_size_pct=config.position_size_pct)
    benchmarks = compute_benchmarks(session_bars)
    by_session, by_year = performance_by_session_and_year(trades)
    
    # Add split-specific metrics
    for split_name in ["train", "val", "test"]:
        split_trades = trades[trades["split"] == split_name]
        if len(split_trades) > 0:
            split_metrics = compute_performance_metrics(split_trades)
            metrics[f"{split_name}_metrics"] = split_metrics
    
    # --- 7. Save artifacts & report ---
    print("[7/7] Saving artifacts and report...")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    # Experiment log
    exp_log = ExperimentLog(hypothesis_root=paths.root / "research" / "hypotheses")
    exp_record = ExperimentRecord(
        hypothesis_id="CSM-001",  # Cross-Session Momentum
        name="XAUUSD Cross-Session Momentum",
        description="Previous-session return predicts next-session return (Asia->Europe, Europe->US, US->Asia)",
        dataset_ids=[str(paths.processed_data / config.symbol.lower() / config.timeframe / "v1.0.0" / "data.parquet")],
        parameters={
            "config": config.__dict__,
            "signal_mode": config.signal_mode,
            "sessions": list(config.sessions),
        },
        seed=config.seed,
    )
    exp_path = exp_log.write(exp_record)
    
    # Save trades
    trades_path = paths.artifacts / f"csm_trades_{stamp}.parquet"
    paths.artifacts.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(trades_path)
    
    # Save session bars
    session_path = paths.artifacts / f"csm_sessions_{stamp}.parquet"
    session_bars.to_parquet(session_path)
    
    # Complete experiment log
    # For exploratory runs, don't lock test set (set evaluated_on_test=False)
    # Final validation run should use evaluated_on_test=True
    exp_log.complete(
        exp_record.experiment_id,
        metrics=metrics,
        artifacts=[str(trades_path), str(session_path), str(exp_path)],
        evaluated_on_test=False,  # Exploratory - don't lock test set
    )
    
    # Build report
    assumptions = f"""
ASSUMPTIONS & LIMITATIONS
-------------------------
- Data: XAUUSD {config.timeframe} OHLCV from {df.index[0].date()} to {df.index[-1].date()} (no bid/ask, no historical spreads)
- Session definitions: Fixed UTC (Asia 00-08, Europe 08-14:30, US 14:30-24) — NO DST adjustment
  -> Seasonal distortion: Europe/US local market hours shift relative to UTC in summer
- Signal: {config.signal_mode} of previous session; observable at next session open (no look-ahead)
- Entry: session open price (first bar); Exit: session close price (last bar)
- Position sizing: Fixed fractional ({config.position_size_pct:.0%} equity, max leverage {config.max_leverage:.1f}x)
- Cost model: spread={config.cost_model.spread_pips} pips, commission=${config.cost_model.commission_per_lot}/lot, slippage={config.cost_model.slippage_pips} pips/side
  -> Total round-trip cost: ${config.cost_model.per_round_trip_usd_per_lot():.2f} per lot
- No swap costs (intraday session holds only)
- Missing bars: sessions with < 2 bars excluded implicitly via groupby
- No optimization; single configuration tested
- Walk-forward, Monte Carlo, regime segmentation NOT applied (future validation stages)
- Benchmarks: Buy-and-hold (first open to last close), Flat (zero)
""".strip()
    
    sections = [
        f"Experiment: XAUUSD Cross-Session Momentum (CSM-001)",
        f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Config: {config.__dict__}",
        "",
        "DATA",
        f"Source: {paths.processed_data / config.symbol.lower() / config.timeframe / 'v1.0.0' / 'data.parquet'}",
        f"Bars: {len(df)} | Sessions: {len(session_bars)} | Range: {session_bars['session_start'].min()} → {session_bars['session_start'].max()}",
        f"Sessions: {', '.join(config.sessions)} (UTC, fixed, no DST)",
        "",
        "SPLITS",
        split.describe(),
        "",
        "SIGNALS",
        f"Mode: {config.signal_mode} | Long signals: {int(n_signals)}/{len(session_bars)} ({n_signals/len(session_bars):.1%})",
        "",
        "PERFORMANCE (NET, ALL DATA)",
        f"Trades: {metrics['n_trades']}",
        f"Win Rate: {metrics['win_rate_net']:.2%}",
        f"Expectancy: ${metrics['expectancy_net_usd']:.2f}/trade",
        f"Profit Factor: {metrics['profit_factor_net']:.2f}",
        f"Total Return: {metrics['total_return_net']:.2%}",
        f"Ann. Return: {metrics['annualized_return_net']:.2%} | Ann. Vol: {metrics['annualized_vol_net']:.2%}",
        f"Sharpe: {metrics['sharpe_net']:.2f}",
        f"Max Drawdown: {metrics['max_drawdown_net']:.2%}",
        f"Exposure: {metrics['exposure']:.2%} | Turnover: {metrics['turnover']:.2f}",
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
        "BY SESSION (NET)",
        by_session.to_string() if not by_session.empty else "No trades",
        "",
        "BY YEAR (NET)",
        by_year.to_string() if not by_year.empty else "No trades",
        "",
        "SPLIT-SPECIFIC METRICS",
        *([f"Train: {m}" for k, m in metrics.items() if k.endswith("_metrics") and "train" in k]),
        *([f"Val: {m}" for k, m in metrics.items() if k.endswith("_metrics") and "val" in k]),
        *([f"Test: {m}" for k, m in metrics.items() if k.endswith("_metrics") and "test" in k]),
        "",
        assumptions,
    ]
    
    report_path = paths.reports / f"csm_xauusd_{config.timeframe}_{stamp}.txt"
    write_text_report(report_path, sections, title="M.A.R.S. Cross-Session Momentum Experiment")
    
    print(f"Report: {report_path}")
    print(f"Trades: {trades_path}")
    print(f"Sessions: {session_path}")
    print(f"Experiment log: {exp_path}")
    
    return {
        "config": config,
        "metrics": metrics,
        "benchmarks": benchmarks,
        "by_session": by_session,
        "by_year": by_year,
        "split": split,
        "trades_path": str(trades_path),
        "session_path": str(session_path),
        "report_path": str(report_path),
        "experiment_id": exp_record.experiment_id,
    }


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="M.A.R.S. Cross-Session Momentum Experiment")
    parser.add_argument("--timeframe", choices=["m5", "h1"], default="m5")
    parser.add_argument("--data-path", type=str, default=None, help="Path to OHLCV parquet file")
    parser.add_argument("--signal-mode", choices=["return", "direction"], default="direction")
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
    
    config = ExperimentConfig(
        timeframe=args.timeframe,
        data_path=args.data_path,
        signal_mode=args.signal_mode,
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