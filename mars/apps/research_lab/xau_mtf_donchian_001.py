"""
Research harness for XAU-MTF-DONCHIAN-001 (Assignment 14, sections E and F).

Provides:
  * chronological in-sample / out-of-sample partitioning against the *verified*
    dataset coverage (the M5 series starts 2021-07-16, not 2021-01-01);
  * a small, predeclared parameter comparison (one factor at a time, no grid);
  * gross / net performance reporting with explicitly stated conventions;
  * cost sensitivity over spread, commission, slippage and swap assumptions;
  * benchmark and no-trade baselines.

Metric conventions (stated once, applied everywhere)
----------------------------------------------------
* Sharpe  : daily equity returns (mark-to-market equity resampled to calendar
            days, last value per day), annualised with sqrt(252).
* Sortino : same returns, denominator is the downside deviation
            (root mean square of negative returns only).
* Drawdown: computed on the mark-to-market equity curve; duration is measured
            in calendar days from the peak until the equity recovers it.
* Profit factor: gross winning P&L / gross losing P&L, computed on NET trade
            P&L (after commission and swap; the observed spread is already
            embedded in the fill prices).
* Exposure: fraction of M5 bars with an open position.
* Turnover: total traded notional (sum of |entry price| * lots * contract size)
            divided by the average equity, annualised.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from mars.apps.backtester.mtf_donchian_backtest import (
    BacktestResult,
    CostModel,
    ExecutionModel,
    MtfDonchianBacktester,
    session_of,
)
from mars.libs.risk.contract_aware import ContractAwareFixedFractionalRisk, InstrumentSpec
from mars.libs.strategies.xau_mtf_donchian import MtfDonchianParams

#: Chronological split boundaries (inclusive start, exclusive end).
IS_START = pd.Timestamp("2021-01-01", tz="UTC")
IS_END = pd.Timestamp("2025-01-01", tz="UTC")
OOS_START = pd.Timestamp("2025-01-01", tz="UTC")

#: Predeclared parameter comparison grid (Assignment 14, section E).
PREDECLARED_DONCHIAN_LOOKBACKS: Tuple[int, ...] = (15, 20, 25, 30, 40)
PREDECLARED_ATR_MULTIPLIERS: Tuple[float, ...] = (1.5, 2.0, 2.5, 3.0)
BASELINE_DONCHIAN_LOOKBACK = 20
BASELINE_ATR_MULTIPLIER = 2.0


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


def load_dataset(
    repo_root: Path,
    m5_rel: str = "data/processed/xauusdm/m5/v1.2.0/data.parquet",
    h1_rel: str = "data/processed/xauusdm/h1/v1.2.0/data.parquet",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load the versioned M5 and H1 datasets as timestamp-indexed frames."""
    m5 = pd.read_parquet(repo_root / m5_rel)
    h1 = pd.read_parquet(repo_root / h1_rel)
    for df in (m5, h1):
        idx = pd.DatetimeIndex(df.index)
        df.index = idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")
        df.index.name = "timestamp"
    return m5, h1


def slice_window(
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Slice both frames to a chronological window."""
    m = m5
    h = h1
    if start is not None:
        m = m[m.index >= start]
        h = h[h.index >= start]
    if end is not None:
        m = m[m.index < end]
        h = h[h.index < end]
    return m.copy(), h.copy()


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
    else:
        net = gross = r = np.array([])
        win_rate = expectancy = avg_win = avg_loss = expectancy_r = 0.0
        gross_win = gross_loss = profit_factor = 0.0
        total_commission = total_swap = total_spread = 0.0
        gross_pnl_total = net_pnl_total = 0.0
        longs = shorts = tf
        holding = np.array([])

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
        "conventions": {
            "sharpe": "daily mark-to-market equity returns, annualised sqrt(252)",
            "sortino": "daily returns, downside deviation (negative returns only), sqrt(252)",
            "drawdown": "mark-to-market equity curve, peak-to-trough",
            "profit_factor": "gross winning net P&L / gross losing net P&L",
            "exposure": "fraction of M5 bars with an open position",
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
    m5: pd.DataFrame,
    spec: InstrumentSpec,
    starting_equity: float,
    risk_fraction: float = 1.0,
) -> Dict[str, Any]:
    """Buy-and-hold benchmark on the same M5 series.

    The position is sized so that the **notional equals the starting equity**
    (``lots = starting_equity / (entry_price * contract_size)``), i.e. an
    unlevered full-equity long.  One observed spread is paid on entry; the
    position is marked to market and no exit cost is charged, so this is a
    price-path reference rather than a strategy with the same holding rules.
    """
    if m5.empty:
        return {}
    first, last = m5.iloc[0], m5.iloc[-1]
    spread_price = float(first["spread"]) * spec.point_size
    entry = float(first["open"]) + spread_price          # buy at the ask
    exit_price = float(last["close"])                     # mark at the bid
    lots = (starting_equity * risk_fraction) / (entry * spec.contract_size)
    pnl = (exit_price - entry) * lots * spec.contract_size
    equity = starting_equity + (m5["close"] - entry) * lots * spec.contract_size
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
        "note": "unlevered full-equity long from the first bar, one observed spread "
                "paid on entry, marked to market at the bid",
    }


def no_trade_baseline(starting_equity: float) -> Dict[str, Any]:
    """The explicit 'do nothing' reference point."""
    return {
        "name": "no_trade",
        "net_pnl_usd": 0.0,
        "net_return": 0.0,
        "sharpe": 0.0,
        "max_drawdown_pct": 0.0,
        "note": "baseline: no position, no cost, zero return",
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class ResearchConfig:
    """Everything that defines a research run."""

    repo_root: Path
    params: MtfDonchianParams = field(default_factory=MtfDonchianParams)
    spec: InstrumentSpec = field(default_factory=InstrumentSpec)
    cost_model: CostModel = field(default_factory=CostModel)
    execution_model: ExecutionModel = field(default_factory=ExecutionModel)
    m5_path: str = "data/processed/xauusdm/m5/v1.2.0/data.parquet"
    h1_path: str = "data/processed/xauusdm/h1/v1.2.0/data.parquet"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "params": self.params.to_dict(),
            "instrument_spec": self.spec.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "execution_model": self.execution_model.to_dict(),
            "data": {"m5": self.m5_path, "h1": self.h1_path},
        }


def build_backtester(config: ResearchConfig) -> MtfDonchianBacktester:
    policy = ContractAwareFixedFractionalRisk(
        spec=config.spec, risk_fraction=config.params.risk_fraction
    )
    return MtfDonchianBacktester(
        config.params,
        spec=config.spec,
        cost_model=config.cost_model,
        execution_model=config.execution_model,
        risk_policy=policy,
    )


def run_window(
    config: ResearchConfig,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> BacktestResult:
    """Run one chronological window."""
    m, h = slice_window(m5, h1, start, end)
    return build_backtester(config).run(m, h)


def parameter_comparison(
    config: ResearchConfig,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
    *,
    lookbacks: Sequence[int] = PREDECLARED_DONCHIAN_LOOKBACKS,
    multipliers: Sequence[float] = PREDECLARED_ATR_MULTIPLIERS,
) -> pd.DataFrame:
    """
    Predeclared, one-factor-at-a-time parameter comparison on the in-sample window.

    No grid search is performed: the Donchian lookback is varied with the stop
    multiplier held at baseline, then the stop multiplier is varied with the
    lookback held at baseline.  Every tested configuration is recorded.
    """
    rows: List[Dict[str, Any]] = []

    for lookback in lookbacks:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=MtfDonchianParams(**{**config.params.to_dict(), "donchian_lookback": lookback}),
            spec=config.spec,
            cost_model=config.cost_model,
            execution_model=config.execution_model,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "donchian_lookback",
            "value": lookback,
            "baseline": lookback == BASELINE_DONCHIAN_LOOKBACK,
            **{k: m[k] for k in (
                "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
                "profit_factor", "net_pnl_usd", "net_return", "max_drawdown_pct",
                "sharpe", "sortino", "exposure",
            )},
        })

    for mult in multipliers:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=MtfDonchianParams(**{**config.params.to_dict(), "atr_stop_multiplier": mult}),
            spec=config.spec,
            cost_model=config.cost_model,
            execution_model=config.execution_model,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "factor": "atr_stop_multiplier",
            "value": mult,
            "baseline": mult == BASELINE_ATR_MULTIPLIER,
            **{k: m[k] for k in (
                "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
                "profit_factor", "net_pnl_usd", "net_return", "max_drawdown_pct",
                "sharpe", "sortino", "exposure",
            )},
        })

    return pd.DataFrame(rows)


def cost_sensitivity(
    config: ResearchConfig,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> pd.DataFrame:
    """
    Sensitivity of the frozen configuration to cost assumptions.

    The observed spread is always applied.  Commission, slippage and swap are
    *assumed scenarios* (clearly labelled) - no broker cost is invented.
    """
    scenarios = [
        ("observed_spread_only", CostModel(spread_multiplier=1.0)),
        ("spread_x0.5", CostModel(spread_multiplier=0.5)),
        ("spread_x2.0", CostModel(spread_multiplier=2.0)),
        ("plus_commission_3usd_rt", CostModel(spread_multiplier=1.0, commission_per_lot_round_trip=3.0)),
        ("plus_commission_7usd_rt", CostModel(spread_multiplier=1.0, commission_per_lot_round_trip=7.0)),
        ("plus_slippage_2pt", CostModel(spread_multiplier=1.0, slippage_points=2.0)),
        ("plus_swap_5usd_night", CostModel(spread_multiplier=1.0, swap_per_lot_night=5.0)),
        ("all_assumptions", CostModel(spread_multiplier=1.0, commission_per_lot_round_trip=3.0,
                                      slippage_points=1.0, swap_per_lot_night=2.0)),
    ]
    rows = []
    for name, cost in scenarios:
        cfg = ResearchConfig(
            repo_root=config.repo_root,
            params=config.params,
            spec=config.spec,
            cost_model=cost,
            execution_model=config.execution_model,
            m5_path=config.m5_path,
            h1_path=config.h1_path,
        )
        res = run_window(cfg, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "scenario": name,
            "spread_multiplier": cost.spread_multiplier,
            "commission_per_lot_rt": cost.commission_per_lot_round_trip,
            "slippage_points": cost.slippage_points,
            "swap_per_lot_night": cost.swap_per_lot_night,
            "trade_count": m["trade_count"],
            "net_pnl_usd": m["net_pnl_usd"],
            "net_return": m["net_return"],
            "profit_factor": m["profit_factor"],
            "sharpe": m["sharpe"],
            "max_drawdown_pct": m["max_drawdown_pct"],
        })
    return pd.DataFrame(rows)


def structural_ablation(
    config: ResearchConfig,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> pd.DataFrame:
    """
    In-sample **diagnostic** ablation of the strategy's structural components.

    This is NOT a parameter comparison and NOT used to select the frozen
    configuration: the configuration is frozen before the ablation runs and the
    ablation is evaluated on the in-sample window only, so the out-of-sample
    window is never consulted here.

    Variants:
      * ``baseline``       - the frozen configuration as specified;
      * ``long_only``      - short entries disabled;
      * ``short_only``     - long entries disabled;
      * ``no_h1_regime``   - the H1 regime filter is bypassed (every Donchian
                             breakout is taken).  Implemented by feeding the
                             engine an H1 series whose EMA always rises, so the
                             regime is long for all bars; the short leg is
                             disabled at the same time.
    """
    rows: List[Dict[str, Any]] = []

    variants = [
        ("baseline", config.params, None),
        ("long_only", MtfDonchianParams(**{**config.params.to_dict(),
                                           "allow_short": False}), None),
        ("short_only", MtfDonchianParams(**{**config.params.to_dict(),
                                            "allow_long": False}), None),
    ]
    for name, params, _ in variants:
        cfg = ResearchConfig(
            repo_root=config.repo_root, params=params, spec=config.spec,
            cost_model=config.cost_model, execution_model=config.execution_model,
            m5_path=config.m5_path, h1_path=config.h1_path,
        )
        res = run_window(cfg, m5, h1, start, end)
        m = compute_metrics(res)
        rows.append({
            "variant": name,
            **{k: m[k] for k in (
                "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
                "profit_factor", "net_pnl_usd", "pre_spread_net_pnl_usd",
                "sharpe", "max_drawdown_pct", "exposure",
            )},
        })

    # no_h1_regime: a synthetic always-rising H1 series makes the regime long
    # for every M5 bar, so every long Donchian breakout is taken.
    m, h = slice_window(m5, h1, start, end)
    synthetic_h1 = h.copy()
    synthetic_h1["close"] = synthetic_h1["close"].cummax() + 1.0
    synthetic_h1["open"] = synthetic_h1["close"]
    synthetic_h1["high"] = synthetic_h1["close"]
    synthetic_h1["low"] = synthetic_h1["close"]
    params = MtfDonchianParams(**{**config.params.to_dict(), "allow_short": False})
    cfg = ResearchConfig(
        repo_root=config.repo_root, params=params, spec=config.spec,
        cost_model=config.cost_model, execution_model=config.execution_model,
        m5_path=config.m5_path, h1_path=config.h1_path,
    )
    res = build_backtester(cfg).run(m, synthetic_h1)
    mtr = compute_metrics(res)
    rows.append({
        "variant": "no_h1_regime_long_leg",
        **{k: mtr[k] for k in (
            "trade_count", "win_rate", "expectancy_usd", "expectancy_r",
            "profit_factor", "net_pnl_usd", "pre_spread_net_pnl_usd",
            "sharpe", "max_drawdown_pct", "exposure",
        )},
    })
    return pd.DataFrame(rows)


__all__ = [
    "BASELINE_ATR_MULTIPLIER",
    "BASELINE_DONCHIAN_LOOKBACK",
    "IS_END",
    "IS_START",
    "OOS_START",
    "PREDECLARED_ATR_MULTIPLIERS",
    "PREDECLARED_DONCHIAN_LOOKBACKS",
    "ResearchConfig",
    "benchmark_buy_and_hold",
    "build_backtester",
    "compute_metrics",
    "cost_sensitivity",
    "daily_returns",
    "drawdown_duration",
    "exit_reason_breakdown",
    "load_dataset",
    "max_drawdown",
    "parameter_comparison",
    "run_window",
    "session_breakdown",
    "sharpe_ratio",
    "slice_window",
    "sortino_ratio",
    "structural_ablation",
    "yearly_breakdown",
]
