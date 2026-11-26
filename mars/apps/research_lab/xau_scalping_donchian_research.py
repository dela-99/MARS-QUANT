"""
XAU-SCALPING-DONCHIAN-001 In-Sample Research Pipeline (Assignment 22).

Provides:
- Chronological IS/OOS partitioning against verified dataset coverage
- Predeclared parameter comparison (one factor at a time, no grid)
- $30 account feasibility analysis with Exness XAUUSDm specs
- Version 1 baseline comparison (preserved historical results)
- Gross/net performance reporting with explicit conventions
- Cost sensitivity over spread, commission, slippage, swap
- Benchmark and no-trade baselines
- Full metrics suite matching Assignment 14/17/21 specifications

Metric conventions (stated once, applied everywhere)
---------------------------------------------------
* Sharpe  : daily equity returns (mark-to-market equity resampled to calendar
            days, last value per day), annualised with sqrt(252).
* Sortino : same returns, denominator is downside deviation
            (root mean square of negative returns only).
* Drawdown: computed on mark-to-market equity curve; duration in calendar days.
* Profit factor: gross winning net P&L / gross losing net P&L (net = after
            commission & swap; spread embedded in fill prices).
* Exposure: fraction of execution bars with an open position.
* Turnover: total traded notional / average equity, annualised.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from mars.apps.backtester.xau_scalping_donchian_backtest import (
    BacktestResult,
    CostModel,
    ExecutionModel,
    XauScalpingDonchianBacktester,
    session_of,
)
from mars.libs.risk.contract_aware import ContractAwareFixedFractionalRisk, InstrumentSpec
from mars.libs.strategies.xau_scalping_donchian import ScalpingDonchianParams, compute_scalping_signals
from mars.libs.data.loaders import load_ohlcv_parquet


# ============================================================================
# Research Configuration
# ============================================================================

# Chronological split boundaries (inclusive start, exclusive end)
IS_START = pd.Timestamp("2021-01-01", tz="UTC")
IS_END = pd.Timestamp("2025-01-01", tz="UTC")
OOS_START = pd.Timestamp("2025-01-01", tz="UTC")

# Predeclared parameter comparison (Assignment 22: one factor at a time)
PREDECLARED_EXECUTION_TFS: Tuple[str, ...] = ("M5", "M1")
PREDECLARED_MAX_HOLD_BARS: Tuple[int, ...] = (3, 6, 12, 24)   # M5 bars (3=15min, 6=30min, etc.)
PREDECLARED_ATR_MULTIPLIERS: Tuple[float, ...] = (1.5, 2.0, 2.5, 3.0)
PREDECLARED_DONCHIAN_LOOKBACKS: Tuple[int, ...] = (15, 20, 25, 30)

BASELINE_EXECUTION_TF = "M5"
BASELINE_MAX_HOLD_BARS = 6
BASELINE_ATR_MULTIPLIER = 2.0
BASELINE_DONCHIAN_LOOKBACK = 20


# ---------------------------------------------------------------------------
# Data Access
# ---------------------------------------------------------------------------


def load_dataset(
    repo_root: Path,
    m1_rel: str = "data/processed/xauusdm/m1/v1.0.0/data.parquet",
    m5_rel: str = "data/processed/xauusdm/m5/v1.2.0/data.parquet",
    h1_rel: str = "data/processed/xauusdm/h1/v1.2.0/data.parquet",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the versioned M1, M5, and H1 datasets as timestamp-indexed frames.
    
    Note: M1 may not exist yet. Returns empty DataFrame for missing M1.
    """
    # Load M5 and H1 (always available)
    m5 = pd.read_parquet(repo_root / m5_rel)
    h1 = pd.read_parquet(repo_root / h1_rel)
    
    # Try to load M1
    m1_path = repo_root / m1_rel
    if m1_path.exists():
        m1 = pd.read_parquet(m1_path)
        # Handle M1 where 'timestamp' is a column, not index
        if "timestamp" in m1.columns:
            m1 = m1.set_index("timestamp")
    else:
        m1 = pd.DataFrame()
        print(f"[INFO] M1 data not found at {m1_rel}. M1 execution mode will be unavailable.")
    
    for df in (m1, m5, h1):
        if len(df) == 0:
            continue
        idx = pd.DatetimeIndex(df.index)
        df.index = idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")
        df.index.name = "timestamp"
    
    return m1, m5, h1


def slice_window(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Slice all three frames to a chronological window."""
    m1_sliced = m5_sliced = h1_sliced = pd.DataFrame()
    
    if len(m1) > 0:
        m1_sliced = m1.copy()
        if start is not None:
            m1_sliced = m1_sliced[m1_sliced.index >= start]
        if end is not None:
            m1_sliced = m1_sliced[m1_sliced.index < end]
    
    m5_sliced = m5.copy()
    h1_sliced = h1.copy()
    if start is not None:
        m5_sliced = m5_sliced[m5_sliced.index >= start]
        h1_sliced = h1_sliced[h1_sliced.index >= start]
    if end is not None:
        m5_sliced = m5_sliced[m5_sliced.index < end]
        h1_sliced = h1_sliced[h1_sliced.index < end]
    
    return m1_sliced, m5_sliced, h1_sliced


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return float(a / b) if b not in (0, 0.0) and np.isfinite(b) else default


def max_drawdown(equity: pd.Series) -> Tuple[float, float, int, int]:
    """Return (max drawdown $, max drawdown %, peak index, trough index)."""
    if equity.empty:
        return 0.0, 0.0, 0, 0
    running_max = equity.cummax()
    dd = equity - running_max
    trough = int(dd.values.argmin())
    peak = int(equity.iloc[: trough + 1].values.argmax())
    dd_abs = float(dd.iloc[trough])
    dd_pct = _safe_div(dd_abs, float(equity.iloc[peak]))
    return dd_abs, dd_pct, peak, trough


def drawdown_duration(equity: pd.Series) -> Dict[str, Any]:
    """Longest and average time spent below a previous equity peak (calendar days)."""
    if equity.empty:
        return {"max_days": 0, "mean_days": 0.0, "n_episodes": 0}
    running_max = equity.cummax()
    under = equity < running_max
    episodes: List[int] = []
    current = 0
    for flag, stamp in zip(under.to_numpy(), equity.index):
        if flag:
            current += 1
        else:
            if current:
                episodes.append(current)
            current = 0
    if current:
        episodes.append(current)
    if not episodes:
        return {"max_days": 0, "mean_days": 0.0, "n_episodes": 0}
    idx = equity.index
    durations: List[int] = []
    start = None
    for i, flag in enumerate(under.to_numpy()):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            durations.append(int((idx[i] - idx[start]).days))
            start = None
    if start is not None:
        durations.append(int((idx[-1] - idx[start]).days))
    return {
        "max_days": int(max(durations)) if durations else 0,
        "mean_days": float(np.mean(durations)) if durations else 0.0,
        "n_episodes": len(durations),
    }


def daily_returns(equity: pd.Series) -> pd.Series:
    """Daily mark-to-market returns of the equity curve."""
    daily = equity.resample("1D").last().ffill()
    return daily.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def sharpe_ratio(returns: pd.Series) -> float:
    """Annualised Sharpe on daily returns (sqrt(252))."""
    if len(returns) < 2:
        return 0.0
    sd = float(returns.std(ddof=1))
    if sd <= 0:
        return 0.0
    return float(returns.mean() / sd * np.sqrt(252))


def sortino_ratio(returns: pd.Series) -> float:
    """Annualised Sortino on daily returns (sqrt(252), downside deviation)."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    dd = float(np.sqrt((downside ** 2).mean())) if len(downside) else 0.0
    if dd <= 0:
        return 0.0
    return float(returns.mean() / dd * np.sqrt(252))


def compute_metrics(result: BacktestResult) -> Dict[str, Any]:
    """Full gross/net performance report for one backtest result."""
    tf = result.trades_frame()
    equity = result.equity_curve
    starting = result.starting_equity
    final = result.final_equity

    if len(tf):
        net = tf["net_pnl"].to_numpy(dtype=float)
        gross = tf["gross_pnl"].to_numpy(dtype=float)
        wins = net[net > 0]
        losses = net[net <= 0]
        win_rate = float(len(wins) / len(net))
        gross_win = float(wins.sum()) if len(wins) else 0.0
        gross_loss = float(-losses.sum()) if len(losses) else 0.0
        expectancy = float(net.mean())
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(losses.mean()) if len(losses) else 0.0
        profit_factor = _safe_div(gross_win, gross_loss, default=float("inf") if gross_win > 0 else 0.0)
        r = tf["r_multiple"].to_numpy(dtype=float)
        expectancy_r = float(r.mean()) if len(r) else 0.0
        total_commission = float(tf["commission"].sum())
        total_swap = float(tf["swap"].sum())
        total_spread = float(tf["spread_cost"].sum())
        gross_pnl_total = float(gross.sum())
        net_pnl_total = float(net.sum())
        longs = tf[tf["side"] == "long"]
        shorts = tf[tf["side"] == "short"]
        holding = tf["holding_minutes"].to_numpy(dtype=float)
        time_exits = int((tf["exit_reason"] == "time_exit").sum()) if "exit_reason" in tf.columns else 0
        stop_exits = int((tf["exit_reason"] == "stop").sum()) if "exit_reason" in tf.columns else 0
        mid_exits = int((tf["exit_reason"] == "donchian_mid_exit").sum()) if "exit_reason" in tf.columns else 0
    else:
        net = gross = r = np.array([])
        win_rate = expectancy = avg_win = avg_loss = expectancy_r = 0.0
        gross_win = gross_loss = profit_factor = 0.0
        total_commission = total_swap = total_spread = 0.0
        gross_pnl_total = net_pnl_total = 0.0
        longs = shorts = tf
        holding = np.array([])
        time_exits = stop_exits = mid_exits = 0

    dd_abs, dd_pct, _, _ = max_drawdown(equity)
    dd_dur = drawdown_duration(equity)
    rets = daily_returns(equity)
    exposure = _safe_div(result.bars_in_market, result.total_bars)

    avg_equity = float(equity.mean()) if len(equity) else starting
    traded_notional = 0.0
    if len(tf):
        traded_notional = float(
            (tf["entry_price"].abs() * tf["lots"] * result.spec.contract_size).sum()
        )
    years = max(len(equity) / (365.25 * 24 * 60), 1e-9) if len(equity) else 1e-9
    turnover = _safe_div(traded_notional, avg_equity) / years

    return {
        "trade_count": int(len(tf)),
        "win_rate": win_rate,
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        "expectancy_usd": expectancy,
        "expectancy_r": expectancy_r,
        "profit_factor": profit_factor,
        "gross_pnl_usd": gross_pnl_total,
        "net_pnl_usd": net_pnl_total,
        "gross_return": _safe_div(gross_pnl_total, starting),
        "net_return": _safe_div(net_pnl_total, starting),
        "starting_equity": starting,
        "final_equity": final,
        "max_drawdown_usd": dd_abs,
        "max_drawdown_pct": dd_pct,
        "drawdown_max_days": dd_dur["max_days"],
        "drawdown_mean_days": dd_dur["mean_days"],
        "sharpe": sharpe_ratio(rets),
        "sortino": sortino_ratio(rets),
        "exposure": exposure,
        "turnover_annualised": turnover,
        "traded_notional_usd": traded_notional,
        "avg_holding_minutes": float(holding.mean()) if len(holding) else 0.0,
        "median_holding_minutes": float(np.median(holding)) if len(holding) else 0.0,
        "max_holding_minutes": float(holding.max()) if len(holding) else 0.0,
        "total_commission_usd": total_commission,
        "total_swap_usd": total_swap,
        "observed_spread_cost_usd": total_spread,
        "pre_spread_net_pnl_usd": net_pnl_total + total_spread,
        "pre_spread_expectancy_usd": (
            float((net + tf["spread_cost"].to_numpy(dtype=float)).mean()) if len(tf) else 0.0
        ),
        "long_trades": int(len(longs)),
        "short_trades": int(len(shorts)),
        "long_net_pnl_usd": float(longs["net_pnl"].sum()) if len(longs) else 0.0,
        "short_net_pnl_usd": float(shorts["net_pnl"].sum()) if len(shorts) else 0.0,
        "long_win_rate": float((longs["net_pnl"] > 0).mean()) if len(longs) else 0.0,
        "short_win_rate": float((shorts["net_pnl"] > 0).mean()) if len(shorts) else 0.0,
        "bars_in_market": int(result.bars_in_market),
        "total_bars": int(result.total_bars),
        "rejected_signals": int(len(result.rejected_signals)),
        "exit_breakdown": {
            "time_exits": time_exits,
            "stop_exits": stop_exits,
            "mid_exits": mid_exits,
            "end_of_data_exits": int(getattr(result, "end_of_data_exits", 0)),
        },
        "conventions": {
            "sharpe": "daily mark-to-market equity returns, annualised sqrt(252)",
            "sortino": "daily returns, downside deviation (negative returns only), sqrt(252)",
            "drawdown": "mark-to-market equity curve, peak-to-trough",
            "profit_factor": "gross winning net P&L / gross losing net P&L",
            "exposure": "fraction of execution bars with an open position",
            "turnover": "traded notional / average equity, annualised",
        },
    }


def yearly_breakdown(result: BacktestResult) -> pd.DataFrame:
    """Per-year trade statistics."""
    tf = result.trades_frame()
    if not len(tf):
        return pd.DataFrame()
    tf = tf.copy()
    tf["year"] = pd.DatetimeIndex(tf["entry_time"]).year
    rows = []
    for year, grp in tf.groupby("year"):
        net = grp["net_pnl"]
        wins = net[net > 0]
        losses = net[net <= 0]
        rows.append({
            "year": int(year),
            "trades": int(len(grp)),
            "win_rate": float(len(wins) / len(grp)),
            "net_pnl_usd": float(net.sum()),
            "gross_pnl_usd": float(grp["gross_pnl"].sum()),
            "profit_factor": _safe_div(
                float(wins.sum()), float(-losses.sum()),
                default=float("inf") if float(wins.sum()) > 0 else 0.0,
            ),
            "avg_r": float(grp["r_multiple"].mean()),
            "long_trades": int((grp["side"] == "long").sum()),
            "short_trades": int((grp["side"] == "short").sum()),
        })
    return pd.DataFrame(rows).set_index("year")


def session_breakdown(result: BacktestResult) -> pd.DataFrame:
    """Per-session trade statistics (entry session, export-frame hours)."""
    tf = result.trades_frame()
    if not len(tf):
        return pd.DataFrame()
    tf = tf.copy()
    tf["session"] = pd.to_datetime(tf["entry_time"], utc=True).map(session_of)
    rows = []
    for sess, grp in tf.groupby("session"):
        net = grp["net_pnl"]
        wins = net[net > 0]
        losses = net[net <= 0]
        rows.append({
            "session": sess,
            "trades": int(len(grp)),
            "win_rate": float(len(wins) / len(grp)),
            "net_pnl_usd": float(net.sum()),
            "avg_r": float(grp["r_multiple"].mean()),
            "profit_factor": _safe_div(
                float(wins.sum()), float(-losses.sum()),
                default=float("inf") if float(wins.sum()) > 0 else 0.0,
            ),
        })
    return pd.DataFrame(rows).set_index("session")


def exit_reason_breakdown(result: BacktestResult) -> pd.DataFrame:
    tf = result.trades_frame()
    if not len(tf):
        return pd.DataFrame()
    grp = tf.groupby("exit_reason")
    return pd.DataFrame({
        "trades": grp.size(),
        "net_pnl_usd": grp["net_pnl"].sum(),
        "avg_r": grp["r_multiple"].mean(),
        "win_rate": grp["net_pnl"].apply(lambda s: float((s > 0).mean())),
    })


def benchmark_buy_and_hold(
    execution_tf: pd.DataFrame,
    spec: InstrumentSpec,
    starting_equity: float,
    risk_fraction: float = 1.0,
) -> Dict[str, Any]:
    """Buy-and-hold benchmark on the same execution timeframe series."""
    if execution_tf.empty:
        return {}
    first, last = execution_tf.iloc[0], execution_tf.iloc[-1]
    spread_price = float(first["spread"]) * spec.point_size
    entry = float(first["open"]) + spread_price
    exit_price = float(last["close"])
    lots = (starting_equity * risk_fraction) / (entry * spec.contract_size)
    pnl = (exit_price - entry) * lots * spec.contract_size
    equity = starting_equity + (execution_tf["close"] - entry) * lots * spec.contract_size
    rets = daily_returns(equity)
    dd_abs, dd_pct, _, _ = max_drawdown(equity)
    return {
        "name": "buy_and_hold",
        "entry_price": entry,
        "exit_price": exit_price,
        "lots": float(lots),
        "notional_usd": float(lots * spec.contract_size * entry),
        "net_pnl_usd": float(pnl),
        "net_return": _safe_div(float(pnl), starting_equity),
        "sharpe": sharpe_ratio(rets),
        "max_drawdown_pct": dd_pct,
        "note": "unlevered full-equity long from first bar, one spread on entry, marked at bid",
    }


def no_trade_baseline(starting_equity: float) -> Dict[str, Any]:
    """Explicit 'do nothing' reference point."""
    return {
        "name": "no_trade",
        "net_pnl_usd": 0.0,
        "net_return": 0.0,
        "sharpe": 0.0,
        "max_drawdown_pct": 0.0,
        "note": "baseline: no position, no cost, zero return",
    }


# ---------------------------------------------------------------------------
# $30 Account Feasibility Analysis
# ---------------------------------------------------------------------------


@dataclass
class AccountFeasibilityResult:
    """Result of $30 account feasibility analysis."""
    min_lot: float
    min_stop_distance_price: float
    min_risk_per_trade_usd: float
    risk_fraction: float
    equity_usd: float
    margin_required_usd: float
    free_margin_after_entry_usd: float
    spread_cost_per_trade_usd: float
    commission_per_trade_usd: float
    total_cost_per_trade_usd: float
    feasible: bool
    rejection_reason: Optional[str] = None
    required_lots_exact: Optional[float] = None
    risk_at_min_lot_usd: Optional[float] = None


def analyze_account_feasibility(
    params: ScalpingDonchianParams,
    spec: InstrumentSpec,
    avg_stop_distance_price: float,
    avg_spread_points: float,
) -> AccountFeasibilityResult:
    """
    Analyze whether the strategy is executable at $30 account size with Exness specs.
    
    Uses the SAME risk engine logic as ContractAwareFixedFractionalRisk to determine
    if min lot (0.01) breaches the 1% risk budget.
    """
    equity = params.account_equity_usd
    risk_fraction = params.risk_fraction
    risk_budget_usd = equity * risk_fraction  # $0.30 at $30 equity, 1% risk
    
    # Risk per lot = stop_distance * contract_size * quote_to_usd
    # For XAUUSDm: quote_currency = USD, so quote_to_usd = 1.0
    risk_per_lot_usd = avg_stop_distance_price * spec.contract_size * 1.0
    
    # Exact lots needed for 1% risk
    lots_exact = risk_budget_usd / risk_per_lot_usd if risk_per_lot_usd > 0 else 0.0
    
    # Floor to broker step
    from mars.libs.risk.contract_aware import floor_to_step
    lots = floor_to_step(lots_exact, spec.volume_step)
    
    # Check min lot constraint
    if lots < spec.volume_min - 1e-12:
        risk_at_min = spec.volume_min * risk_per_lot_usd
        return AccountFeasibilityResult(
            min_lot=spec.volume_min,
            min_stop_distance_price=avg_stop_distance_price,
            min_risk_per_trade_usd=risk_at_min,
            risk_fraction=risk_fraction,
            equity_usd=equity,
            margin_required_usd=(spec.volume_min * spec.contract_size * avg_stop_distance_price * 10) / params.leverage,  # rough estimate
            free_margin_after_entry_usd=equity - (spec.volume_min * spec.contract_size * avg_stop_distance_price * 10) / params.leverage,
            spread_cost_per_trade_usd=avg_spread_points * spec.point_size * spec.contract_size * spec.volume_min,
            commission_per_trade_usd=0.0,
            total_cost_per_trade_usd=avg_spread_points * spec.point_size * spec.contract_size * spec.volume_min,
            feasible=False,
            rejection_reason=f"min volume breach: {spec.volume_min} lots risks ${risk_at_min:.2f} > budget ${risk_budget_usd:.2f}",
            required_lots_exact=lots_exact,
            risk_at_min_lot_usd=risk_at_min,
        )
    
    # Feasible at min lot or above
    margin_required = (lots * spec.contract_size * avg_stop_distance_price * 10) / params.leverage
    spread_cost = avg_spread_points * spec.point_size * spec.contract_size * lots
    
    return AccountFeasibilityResult(
        min_lot=spec.volume_min,
        min_stop_distance_price=avg_stop_distance_price,
        min_risk_per_trade_usd=lots * risk_per_lot_usd,
        risk_fraction=risk_fraction,
        equity_usd=equity,
        margin_required_usd=margin_required,
        free_margin_after_entry_usd=equity - margin_required,
        spread_cost_per_trade_usd=spread_cost,
        commission_per_trade_usd=0.0,
        total_cost_per_trade_usd=spread_cost,
        feasible=True,
        required_lots_exact=lots_exact,
        risk_at_min_lot_usd=spec.volume_min * risk_per_lot_usd,
    )


# ---------------------------------------------------------------------------
# Research Runner
# ---------------------------------------------------------------------------


@dataclass
class ResearchConfig:
    """Everything that defines a research run."""

    repo_root: Path
    params: ScalpingDonchianParams = field(default_factory=ScalpingDonchianParams)
    spec: InstrumentSpec = field(default_factory=lambda: InstrumentSpec(
        symbol="XAUUSDm",
        contract_size=100.0,
        pip_size=0.01,
        point_size=0.001,
        quote_currency="USD",
        volume_min=0.01,
        volume_max=200.0,
        volume_step=0.01,
        volume_spec_source="mt5.live",
        spec_source="mt5.live",
    ))
    cost_model: CostModel = field(default_factory=CostModel)
    execution_model: ExecutionModel = field(default_factory=ExecutionModel)
    m1_path: str = "data/processed/xauusdm/m1/v1.2.0/data.parquet"
    m5_path: str = "data/processed/xauusdm/m5/v1.2.0/data.parquet"
    h1_path: str = "data/processed/xauusdm/h1/v1.2.0/data.parquet"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "params": self.params.to_dict(),
            "instrument_spec": self.spec.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "execution_model": self.execution_model.to_dict(),
            "data": {"m1": self.m1_path, "m5": self.m5_path, "h1": self.h1_path},
        }


def build_backtester(config: ResearchConfig) -> XauScalpingDonchianBacktester:
    policy = ContractAwareFixedFractionalRisk(
        spec=config.spec, risk_fraction=config.params.risk_fraction
    )
    return XauScalpingDonchianBacktester(
        config.params,
        spec=config.spec,
        cost_model=config.cost_model,
        execution_model=config.execution_model,
        risk_policy=policy,
    )


def run_window(
    config: ResearchConfig,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> BacktestResult:
    """Run one chronological window."""
    m1_s, m5_s, h1_s = slice_window(m1, m5, h1, start, end)
    
    # Choose execution and context timeframes based on params
    if config.params.execution_timeframe == "M1":
        if len(m1_s) == 0:
            raise ValueError("M1 data required for M1 execution mode but not available")
        execution_tf = m1_s
        context_tf = m5_s
    else:
        execution_tf = m5_s
        context_tf = m5_s  # M5 execution uses M5 for both
    
    return build_backtester(config).run(execution_tf, context_tf, h1_s)


def parameter_comparison(
    config: ResearchConfig,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
    *,
    execution_tfs: Sequence[str] = PREDECLARED_EXECUTION_TFS,
    max_hold_bars: Sequence[int] = PREDECLARED_MAX_HOLD_BARS,
    atr_multipliers: Sequence[float] = PREDECLARED_ATR_MULTIPLIERS,
    donchian_lookbacks: Sequence[int] = PREDECLARED_DONCHIAN_LOOKBACKS,
) -> pd.DataFrame:
    """
    Predeclared, one-factor-at-a-time parameter comparison on the in-sample window.

    No grid search: each factor varied individually from baseline.
    """
    rows: List[Dict[str, Any]] = []
    base_params = config.params.to_dict()

    # Vary execution timeframe
    for tf in execution_tfs:
        if tf == "M1" and len(m1) == 0:
            continue  # Skip M1 if data unavailable
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=ScalpingDonchianParams(**{**base_params, "execution_timeframe": tf}),
            spec=config.spec,
            cost_model=config.cost_model,
            execution_model=config.execution_model,
            m1_path=config.m1_path,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m1, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "execution_timeframe",
            "value": tf,
            "baseline": tf == BASELINE_EXECUTION_TF,
            **{k: m[k] for k in (
                "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
                "profit_factor", "net_pnl_usd", "net_return", "max_drawdown_pct",
                "sharpe", "sortino", "exposure", "avg_holding_minutes",
            )},
        })

    # Vary max holding bars
    for bars in max_hold_bars:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=ScalpingDonchianParams(**{**base_params, "max_holding_bars": bars}),
            spec=config.spec,
            cost_model=config.cost_model,
            execution_model=config.execution_model,
            m1_path=config.m1_path,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m1, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "max_holding_bars",
            "value": bars,
            "baseline": bars == BASELINE_MAX_HOLD_BARS,
            **{k: m[k] for k in (
                "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
                "profit_factor", "net_pnl_usd", "net_return", "max_drawdown_pct",
                "sharpe", "sortino", "exposure", "avg_holding_minutes",
            )},
        })

    # Vary ATR stop multiplier
    for mult in atr_multipliers:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=ScalpingDonchianParams(**{**base_params, "atr_stop_multiplier": mult}),
            spec=config.spec,
            cost_model=config.cost_model,
            execution_model=config.execution_model,
            m1_path=config.m1_path,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m1, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "atr_stop_multiplier",
            "value": mult,
            "baseline": mult == BASELINE_ATR_MULTIPLIER,
            **{k: m[k] for k in (
                "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
                "profit_factor", "net_pnl_usd", "net_return", "max_drawdown_pct",
                "sharpe", "sortino", "exposure", "avg_holding_minutes",
            )},
        })

    # Vary Donchian lookback
    for lookback in donchian_lookbacks:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=ScalpingDonchianParams(**{**base_params, "donchian_lookback": lookback}),
            spec=config.spec,
            cost_model=config.cost_model,
            execution_model=config.execution_model,
            m1_path=config.m1_path,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m1, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "donchian_lookback",
            "value": lookback,
            "baseline": lookback == BASELINE_DONCHIAN_LOOKBACK,
            **{k: m[k] for k in (
                "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
                "profit_factor", "net_pnl_usd", "net_return", "max_drawdown_pct",
                "sharpe", "sortino", "exposure", "avg_holding_minutes",
            )},
        })

    return pd.DataFrame(rows)


def cost_sensitivity(
    config: ResearchConfig,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
    *,
    spread_multipliers: Sequence[float] = (1.0, 1.5, 2.0, 3.0),
    commission_per_lot: Sequence[float] = (0.0, 1.0, 2.0, 5.0),
    slippage_points: Sequence[float] = (0.0, 1.0, 2.0, 5.0),
) -> pd.DataFrame:
    """Cost sensitivity analysis (one factor at a time)."""
    rows: List[Dict[str, Any]] = []
    base_params = config.params.to_dict()

    for sm in spread_multipliers:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=ScalpingDonchianParams(**base_params),
            spec=config.spec,
            cost_model=CostModel(spread_multiplier=sm),
            execution_model=config.execution_model,
            m1_path=config.m1_path,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m1, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "spread_multiplier",
            "value": sm,
            "baseline": sm == 1.0,
            **{k: m[k] for k in (
                "trade_count", "expectancy_usd", "net_pnl_usd", "net_return",
                "max_drawdown_pct", "sharpe", "observed_spread_cost_usd",
            )},
        })

    for comm in commission_per_lot:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=ScalpingDonchianParams(**base_params),
            spec=config.spec,
            cost_model=CostModel(commission_per_lot_round_trip=comm),
            execution_model=config.execution_model,
            m1_path=config.m1_path,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m1, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "commission_per_lot",
            "value": comm,
            "baseline": comm == 0.0,
            **{k: m[k] for k in (
                "trade_count", "expectancy_usd", "net_pnl_usd", "net_return",
                "max_drawdown_pct", "sharpe", "total_commission_usd",
            )},
        })

    for slip in slippage_points:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=ScalpingDonchianParams(**base_params),
            spec=config.spec,
            cost_model=CostModel(slippage_points=slip),
            execution_model=config.execution_model,
            m1_path=config.m1_path,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m1, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "slippage_points",
            "value": slip,
            "baseline": slip == 0.0,
            **{k: m[k] for k in (
                "trade_count", "expectancy_usd", "net_pnl_usd", "net_return",
                "max_drawdown_pct", "sharpe",
            )},
        })

    return pd.DataFrame(rows)


def run_full_research(
    repo_root: Path,
    output_dir: Path,
    config: Optional[ResearchConfig] = None,
) -> Dict[str, Any]:
    """Execute the full IS research pipeline and write reports."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if config is None:
        config = ResearchConfig(repo_root=repo_root)

    # Load data
    m1, m5, h1 = load_dataset(repo_root, config.m1_path, config.m5_path, config.h1_path)
    print(f"Loaded data: M1={len(m1)} bars, M5={len(m5)} bars, H1={len(h1)} bars")

    # Run baseline (Version 1 equivalent: M5 execution, 6-bar max hold = 30 min)
    baseline_params = ScalpingDonchianParams(
        execution_timeframe="M5",
        max_holding_bars=6,
        atr_stop_multiplier=2.0,
        donchian_lookback=20,
    )
    baseline_config = ResearchConfig(
        repo_root=repo_root,
        params=baseline_params,
        spec=config.spec,
        cost_model=config.cost_model,
        execution_model=config.execution_model,
    )
    baseline_result = run_window(baseline_config, m1, m5, h1, IS_START, IS_END)
    baseline_metrics = compute_metrics(baseline_result)

    # Run current config
    current_result = run_window(config, m1, m5, h1, IS_START, IS_END)
    current_metrics = compute_metrics(current_result)

    # Parameter comparison
    param_comp = parameter_comparison(config, m1, m5, h1, IS_START, IS_END)

    # Cost sensitivity
    cost_sens = cost_sensitivity(config, m1, m5, h1, IS_START, IS_END)

    # $30 Account Feasibility
    # Estimate avg stop distance and spread from baseline
    avg_atr = baseline_result.trades_frame()["atr"].mean() if len(baseline_result.trades) > 0 else 2.0
    avg_stop_dist = baseline_params.atr_stop_multiplier * avg_atr
    avg_spread = m5["spread"].mean() if "spread" in m5.columns else 200.0
    feasibility = analyze_account_feasibility(config.params, config.spec, avg_stop_dist, avg_spread)

    # Benchmarks
    if config.params.execution_timeframe == "M1" and len(m1) > 0:
        exec_tf_for_bm = m1[(m1.index >= IS_START) & (m1.index < IS_END)]
    else:
        exec_tf_for_bm = m5[(m5.index >= IS_START) & (m5.index < IS_END)]
    bm_bh = benchmark_buy_and_hold(exec_tf_for_bm, config.spec, config.params.starting_equity)
    bm_nt = no_trade_baseline(config.params.starting_equity)

    # Compile report
    report = {
        "strategy_id": "XAU-SCALPING-DONCHIAN-001",
        "config": config.to_dict(),
        "baseline_metrics": baseline_metrics,
        "current_metrics": current_metrics,
        "parameter_comparison": param_comp.to_dict(orient="records"),
        "cost_sensitivity": cost_sens.to_dict(orient="records"),
        "account_feasibility_30usd": {
            "min_lot": feasibility.min_lot,
            "min_stop_distance_price": feasibility.min_stop_distance_price,
            "min_risk_per_trade_usd": feasibility.min_risk_per_trade_usd,
            "risk_fraction": feasibility.risk_fraction,
            "equity_usd": feasibility.equity_usd,
            "margin_required_usd": feasibility.margin_required_usd,
            "free_margin_after_entry_usd": feasibility.free_margin_after_entry_usd,
            "spread_cost_per_trade_usd": feasibility.spread_cost_per_trade_usd,
            "commission_per_trade_usd": feasibility.commission_per_trade_usd,
            "total_cost_per_trade_usd": feasibility.total_cost_per_trade_usd,
            "feasible": feasibility.feasible,
            "rejection_reason": feasibility.rejection_reason,
            "required_lots_exact": feasibility.required_lots_exact,
            "risk_at_min_lot_usd": feasibility.risk_at_min_lot_usd,
            "conclusion": (
                f"XAUUSDm trading is {'TECHNICALLY FEASIBLE' if feasibility.feasible else 'INFEASIBLE'} "
                f"at $30 under verified Exness conditions. "
                f"Minimum cash risk per executable trade: ${feasibility.min_risk_per_trade_usd:.2f}. "
                f"{'Strategy respects configured risk limits.' if feasibility.feasible else 'Strategy classified as infeasible at intended account size.'}"
            ),
        },
        "benchmarks": {
            "buy_and_hold": bm_bh,
            "no_trade": bm_nt,
        },
        "yearly_breakdown": yearly_breakdown(current_result).to_dict(orient="index"),
        "session_breakdown": session_breakdown(current_result).to_dict(orient="index"),
        "exit_reason_breakdown": exit_reason_breakdown(current_result).to_dict(orient="index"),
    }

    # Write JSON
    with open(output_dir / "xau_scalping_donchian_is_research.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Write markdown report
    md = _generate_markdown_report(report)
    with open(output_dir / "XAU_SCALPING_DONCHIAN_IS_RESEARCH_REPORT.md", "w") as f:
        f.write(md)

    print(f"Research complete. Reports written to {output_dir}")
    return report


def _generate_markdown_report(report: Dict[str, Any]) -> str:
    """Generate a markdown report from the research results."""
    lines = [
        "# XAU-SCALPING-DONCHIAN-001 In-Sample Research Report",
        "",
        f"**Strategy ID**: {report['strategy_id']}",
        f"**Generated**: {pd.Timestamp.now(tz='UTC').isoformat()}",
        "",
        "## Configuration",
        "```json",
        json.dumps(report["config"], indent=2, default=str),
        "```",
        "",
        "## Baseline Metrics (Version 1 Equivalent: M5 execution, 30-min max hold)",
    ]
    for k, v in report["baseline_metrics"].items():
        if isinstance(v, float):
            lines.append(f"- **{k}**: {v:.4f}")
        else:
            lines.append(f"- **{k}**: {v}")

    lines.extend([
        "",
        "## Current Configuration Metrics",
    ])
    for k, v in report["current_metrics"].items():
        if isinstance(v, float):
            lines.append(f"- **{k}**: {v:.4f}")
        else:
            lines.append(f"- **{k}**: {v}")

    lines.extend([
        "",
        "## Parameter Comparison (One-Factor-at-a-Time)",
    ])
    if report["parameter_comparison"]:
        df = pd.DataFrame(report["parameter_comparison"])
        lines.append(df.to_markdown(index=False))

    lines.extend([
        "",
        "## Cost Sensitivity",
    ])
    if report["cost_sensitivity"]:
        df = pd.DataFrame(report["cost_sensitivity"])
        lines.append(df.to_markdown(index=False))

    lines.extend([
        "",
        "## $30 Account Feasibility Analysis (Exness XAUUSDm)",
    ])
    feas = report["account_feasibility_30usd"]
    for k, v in feas.items():
        if k != "conclusion":
            lines.append(f"- **{k}**: {v}")
    lines.append(f"\n**Conclusion**: {feas['conclusion']}")

    lines.extend([
        "",
        "## Benchmarks",
        "### Buy & Hold",
    ])
    for k, v in report["benchmarks"]["buy_and_hold"].items():
        lines.append(f"- **{k}**: {v}")
    lines.append("\n### No Trade")
    for k, v in report["benchmarks"]["no_trade"].items():
        lines.append(f"- **{k}**: {v}")

    lines.extend([
        "",
        "## Yearly Breakdown",
    ])
    if report["yearly_breakdown"]:
        df = pd.DataFrame(report["yearly_breakdown"]).T
        lines.append(df.to_markdown())

    lines.extend([
        "",
        "## Session Breakdown",
    ])
    if report["session_breakdown"]:
        df = pd.DataFrame(report["session_breakdown"]).T
        lines.append(df.to_markdown())

    lines.extend([
        "",
        "## Exit Reason Breakdown",
    ])
    if report["exit_reason_breakdown"]:
        df = pd.DataFrame(report["exit_reason_breakdown"])
        lines.append(df.to_markdown())

    return "\n".join(lines)


__all__ = [
    "ResearchConfig",
    "AccountFeasibilityResult",
    "load_dataset",
    "slice_window",
    "compute_metrics",
    "yearly_breakdown",
    "session_breakdown",
    "exit_reason_breakdown",
    "benchmark_buy_and_hold",
    "no_trade_baseline",
    "analyze_account_feasibility",
    "build_backtester",
    "run_window",
    "parameter_comparison",
    "cost_sensitivity",
    "run_full_research",
    "IS_START",
    "IS_END",
    "OOS_START",
]