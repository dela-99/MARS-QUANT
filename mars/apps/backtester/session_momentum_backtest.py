"""
M.A.R.S. Session Momentum Backtester: XAU-SESSION-MOM-001

Bar-level execution engine reusing Assignment 14 risk/execution conventions.
Long-only, session-hold strategy with stop-loss and observed spread costs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from mars.libs.risk.contract_aware import ContractAwareFixedFractionalRisk, InstrumentSpec
from mars.libs.strategies.xau_session_momentum import (
    SessionMomentumParams,
    compute_signals,
)


# ============================================================================
# Cost & Execution Models (reused from Assignment 14)
# ============================================================================

@dataclass(frozen=True)
class CostModel:
    """Transaction cost assumptions. Only spread_multiplier touches observed data."""

    spread_multiplier: float = 1.0
    commission_per_lot_round_trip: float = 0.0
    slippage_points: float = 0.0
    swap_per_lot_night: float = 0.0
    use_observed_spread: bool = True
    fallback_spread_points: float = 200.0
    cost_source: str = "observed_bar_spread"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionModel:
    """Fill conventions. Recorded verbatim in every run record."""

    entry_fill: str = "next_bar_open"
    stop_fill: str = "gap_aware_conservative"
    same_bar_priority: str = "worst_price"
    exit_fill: str = "next_bar_open"
    reversal_policy: str = "opposite_signal_ignored"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# Trade & Result Records
# ============================================================================

@dataclass
class Trade:
    """One closed trade in the ledger."""

    symbol: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    lots: float
    stop_price: float
    atr: float
    gross_pnl: float
    spread_cost: float
    commission: float
    swap: float
    net_pnl: float
    exit_reason: str
    holding_bars: int
    holding_minutes: float
    mae_price: float
    mfe_price: float
    r_multiple: float
    equity_before: float
    equity_after: float
    entry_session: str = ""
    exit_session: str = ""
    bars_in_market: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("entry_time", "exit_time"):
            d[k] = str(d[k])
        return d


@dataclass
class BacktestResult:
    """Result of one backtest run."""

    trades: List[Trade]
    equity_curve: pd.Series
    daily_equity: pd.Series
    rejected_signals: List[Dict[str, Any]]
    params: SessionMomentumParams
    cost_model: CostModel
    execution_model: ExecutionModel
    spec: InstrumentSpec
    starting_equity: float
    bars_in_market: int
    total_bars: int
    final_equity: float

    def trades_frame(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(
                columns=[
                    "symbol", "side", "entry_time", "entry_price", "exit_time",
                    "exit_price", "lots", "stop_price", "atr", "gross_pnl",
                    "spread_cost", "commission", "swap", "net_pnl", "exit_reason",
                    "holding_bars", "holding_minutes", "mae_price", "mfe_price",
                    "r_multiple", "equity_before", "equity_after",
                    "entry_session", "exit_session", "bars_in_market",
                ]
            )
        return pd.DataFrame([t.to_dict() for t in self.trades])

    def run_record(self) -> Dict[str, Any]:
        return {
            "strategy_id": "XAU-SESSION-MOM-001",
            "params": self.params.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "execution_model": self.execution_model.to_dict(),
            "instrument_spec": self.spec.to_dict(),
            "starting_equity": self.starting_equity,
            "final_equity": self.final_equity,
            "total_bars": self.total_bars,
            "bars_in_market": self.bars_in_market,
            "trades": len(self.trades),
            "rejected_signals": len(self.rejected_signals),
        }


# ============================================================================
# Session Labelling (Fixed UTC — matches strategy)
# ============================================================================

from datetime import time, timezone

SESSION_BOUNDS = [
    (0, 8, "asia"),
    (8, 14.5, "europe"),  # 14:30 = 14.5
    (14.5, 24, "us"),
]


def session_of(ts: pd.Timestamp) -> str:
    """Bucket a timestamp into a trading session using fixed UTC clock."""
    hour = ts.hour + ts.minute / 60.0
    for lo, hi, name in SESSION_BOUNDS:
        if lo <= hour < hi:
            return name
    return "us"  # fallback


# ============================================================================
# Backtester Engine
# ============================================================================

class SessionMomentumBacktester:
    """
    Event-driven bar-level backtester for XAU-SESSION-MOM-001.

    Reuses Assignment 14 conventions:
    - Entries at next bar open after signal (session open = first M5 bar)
    - Spread from observed per-bar column (bid prices in dataset)
    - Stop fills: gap-aware conservative
    - Same-bar priority: worst price for position
    - Long-only (no reversal, no pyramiding)
    - Final position closed at end_of_data
    """

    def __init__(
        self,
        params: Optional[SessionMomentumParams] = None,
        *,
        spec: Optional[InstrumentSpec] = None,
        cost_model: Optional[CostModel] = None,
        execution_model: Optional[ExecutionModel] = None,
        risk_policy: Optional[ContractAwareFixedFractionalRisk] = None,
    ) -> None:
        self.params = params or SessionMomentumParams()
        self.spec = spec or InstrumentSpec()
        self.cost_model = cost_model or CostModel()
        self.execution_model = execution_model or ExecutionModel()
        self.risk_policy = risk_policy or ContractAwareFixedFractionalRisk(
            spec=self.spec,
            risk_fraction=self.params.risk_fraction,
            enforce_volume_rules=True,
        )

    # ------------------------------------------------------------------
    def run(self, m5: pd.DataFrame, h1: Optional[pd.DataFrame] = None) -> BacktestResult:
        """Run the backtest over the supplied M5/H1 frames."""
        # Generate signals
        signals = compute_signals(m5, h1, self.params).frame
        n = len(signals)
        if n < 2:
            return BacktestResult(
                trades=[], equity_curve=pd.Series(dtype=float), daily_equity=pd.Series(dtype=float),
                rejected_signals=[], params=self.params, cost_model=self.cost_model,
                execution_model=self.execution_model, spec=self.spec,
                starting_equity=self.params.starting_equity, bars_in_market=0, total_bars=n,
                final_equity=self.params.starting_equity,
            )

        # Extract arrays for performance
        ts = signals["timestamp"].to_numpy()
        o = signals["open"].to_numpy(dtype=float)
        h = signals["high"].to_numpy(dtype=float)
        l = signals["low"].to_numpy(dtype=float)
        c = signals["close"].to_numpy(dtype=float)
        spread_pts = signals["spread"].to_numpy(dtype=float)
        atr = signals["atr"].to_numpy(dtype=float)
        stop_dist = signals["stop_distance"].to_numpy(dtype=float)
        entry_long = signals["entry_long"].to_numpy(dtype=bool)
        exit_long = signals["exit_long"].to_numpy(dtype=bool)
        # Short signals always false for this strategy
        entry_short = np.zeros(n, dtype=bool)
        exit_short = np.zeros(n, dtype=bool)

        # Cost model parameters
        point = self.spec.point_size
        mult = self.cost_model.spread_multiplier
        fallback = self.cost_model.fallback_spread_points
        slippage_price = self.cost_model.slippage_points * point

        # Observed spread in price units; bars with spread == 0 fall back to dataset median
        spread_price = np.where(
            np.isfinite(spread_pts), spread_pts, fallback
        ) * point * mult
        zero_mask = ~np.isfinite(spread_pts) | (spread_pts <= 0)
        if self.cost_model.use_observed_spread:
            median_pts = float(np.nanmedian(spread_pts[spread_pts > 0])) if np.any(spread_pts > 0) else fallback
            spread_price = np.where(zero_mask, median_pts * point * mult, spread_price)
        else:
            spread_price = np.full(n, fallback * point * mult)

        # Equity tracking
        equity = float(self.params.starting_equity)
        realized_equity = equity
        trades: List[Trade] = []
        rejected: List[Dict[str, Any]] = []
        equity_curve = np.empty(n, dtype=float)

        position: Optional[Dict[str, Any]] = None
        bars_in_market = 0

        for i in range(n):
            bar_open = o[i]
            bar_high = h[i]
            bar_low = l[i]
            bar_close = c[i]
            spr = spread_price[i]

            # ---- (A) Execute pending entry at this bar's open --------------
            if position is None:
                if entry_long[i]:
                    stop_distance = float(stop_dist[i])
                    # Long entry buys at ask -> bid_open + spread
                    raw = bar_open + spr
                    fill = raw + slippage_price

                    from mars.libs.strategies.base import TradeSetup
                    setup = TradeSetup(
                        timestamp=pd.Timestamp(ts[i]).to_pydatetime(),
                        symbol=self.spec.symbol,
                        side="long",
                        rationale="XAU-SESSION-MOM-001 entry",
                        metadata={"stop_distance": stop_distance},
                    )
                    decision = self.risk_policy.evaluate(setup, equity=realized_equity)
                    if decision.approved:
                        position = {
                            "side": 1,
                            "entry_index": i,
                            "entry_time": pd.Timestamp(ts[i]),
                            "entry_price": float(fill),
                            "lots": float(decision.size),
                            "stop_distance": float(stop_distance),
                            "stop": float(fill - stop_distance),
                            "atr": float(atr[i]),
                            "entry_spread": float(spr),
                            "mae": float(fill),
                            "mfe": float(fill),
                            "equity_before": realized_equity,
                            "entry_session": session_of(pd.Timestamp(ts[i])),
                            "bars": 0,
                        }
                    else:
                        rejected.append(
                            {
                                "time": str(pd.Timestamp(ts[i])),
                                "side": "long",
                                "reason": decision.reason,
                                "metadata": {k: v for k, v in decision.metadata.items()},
                            }
                        )

            # ---- (B) Manage open position on this bar ---------------------
            if position is not None:
                side = position["side"]
                position["bars"] += 1
                bars_in_market += 1

                if side > 0:
                    position["mae"] = min(position["mae"], bar_low)
                    position["mfe"] = max(position["mfe"], bar_high)
                else:
                    position["mae"] = max(position["mae"], bar_high)
                    position["mfe"] = min(position["mfe"], bar_low)

                # Check stop hit
                stop_hit = bar_low <= position["stop"]
                stop_fill = None
                if stop_hit:
                    # Gap aware: fill at open when bar opened beyond stop
                    stop_fill = min(position["stop"], bar_open)

                # Check session-close exit (time-based)
                exit_fill = None
                if exit_long[i]:
                    # Long exits sell at bid -> bar_open
                    exit_fill = bar_open

                # Same-bar priority: worst price for position
                candidates = []
                if stop_fill is not None:
                    candidates.append((stop_fill, "stop"))
                if exit_fill is not None:
                    candidates.append((exit_fill, "session_close"))

                if candidates:
                    # Long: worse = lower price
                    chosen_price, chosen_reason = min(candidates, key=lambda x: x[0])
                    trade = self._close_trade(
                        position, chosen_price, pd.Timestamp(ts[i]), chosen_reason,
                        realized_equity, spr, i,
                    )
                    realized_equity = trade.equity_after
                    trades.append(trade)
                    position = None

            # ---- (C) Mark to market for equity curve -----------------------
            unrealized = 0.0
            if position is not None:
                unrealized = (
                    (bar_close - position["entry_price"])
                    * position["side"]
                    * position["lots"]
                    * self.spec.contract_size
                )
            equity_curve[i] = realized_equity + unrealized

        # Close any position still open at end of data
        if position is not None:
            # Long exits at last close (bid)
            final_price = float(c[-1])
            trade = self._close_trade(
                position, final_price, pd.Timestamp(ts[-1]), "end_of_data",
                realized_equity, spread_price[-1], n - 1,
            )
            realized_equity = trade.equity_after
            trades.append(trade)
            equity_curve[-1] = realized_equity

        equity_series = pd.Series(equity_curve, index=pd.DatetimeIndex(ts), name="equity")
        daily = equity_series.resample("1D").last().ffill()

        return BacktestResult(
            trades=trades,
            equity_curve=equity_series,
            daily_equity=daily,
            rejected_signals=rejected,
            params=self.params,
            cost_model=self.cost_model,
            execution_model=self.execution_model,
            spec=self.spec,
            starting_equity=self.params.starting_equity,
            bars_in_market=bars_in_market,
            total_bars=n,
            final_equity=float(realized_equity),
        )

    # ------------------------------------------------------------------
    def _close_trade(
        self,
        position: Dict[str, Any],
        exit_price: float,
        exit_time: pd.Timestamp,
        reason: str,
        realized_equity: float,
        spread_at_exit: float,
        index: int,
    ) -> Trade:
        """Close a position and build the ledger row."""
        side = position["side"]
        lots = position["lots"]
        entry_price = position["entry_price"]
        contract = self.spec.contract_size

        gross = (exit_price - entry_price) * side * lots * contract

        # Spread paid: long pays on entry (already in entry_price), short pays on exit
        # For long: spread is embedded in entry_price (paid ask), exit receives bid
        # So exactly one observed spread crossed per round trip
        spread_paid = position["entry_spread"] if side > 0 else float(spread_at_exit)
        spread_cost = float(spread_paid) * lots * contract

        commission = self.cost_model.commission_per_lot_round_trip * lots
        nights = max(0, (exit_time - position["entry_time"]).days)
        swap = self.cost_model.swap_per_lot_night * nights * lots
        net = gross - commission - swap - spread_cost

        holding_bars = max(1, index - position["entry_index"] + 1)
        holding_minutes = (exit_time - position["entry_time"]).total_seconds() / 60.0
        stop_distance = position["stop_distance"]
        r_multiple = net / (stop_distance * lots * contract) if stop_distance > 0 else 0.0

        return Trade(
            symbol=self.spec.symbol,
            side="long" if side > 0 else "short",
            entry_time=position["entry_time"],
            entry_price=entry_price,
            exit_time=exit_time,
            exit_price=exit_price,
            lots=lots,
            stop_price=position["stop"],
            atr=position["atr"],
            gross_pnl=gross,
            spread_cost=spread_cost,
            commission=commission,
            swap=swap,
            net_pnl=net,
            exit_reason=reason,
            holding_bars=holding_bars,
            holding_minutes=holding_minutes,
            mae_price=position["mae"],
            mfe_price=position["mfe"],
            r_multiple=r_multiple,
            equity_before=realized_equity,
            equity_after=realized_equity + net,
            entry_session=position["entry_session"],
            exit_session=session_of(exit_time),
            bars_in_market=position["bars"],
        )


__all__ = [
    "SessionMomentumBacktester",
    "BacktestResult",
    "CostModel",
    "ExecutionModel",
    "Trade",
    "session_of",
]