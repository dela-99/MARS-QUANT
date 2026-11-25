"""
Bar-level execution engine for XAU-MTF-DONCHIAN-001 (Assignment 14, section C).

The engine is deliberately explicit about every fill convention, because those
conventions decide whether a backtest is credible.

Fill conventions
----------------
1. **Entries** are executed at the **open of the next available bar** after the
   signal candle closes.  A signal close is never used as a fill price.
2. **Spread** is applied from the *observed* per-bar spread column.  The OHLC in
   the dataset are bid prices, so:
     * a long entry pays the ask  -> ``open + spread``
     * a long exit  receives the bid -> ``open``
     * a short entry receives the bid -> ``open``
     * a short exit  pays the ask    -> ``open + spread``
   One round trip therefore costs exactly one observed spread.
3. **Stop fills** are gap aware and conservative: if the bar opens beyond the
   stop the fill is the **open** (the price that was actually available),
   otherwise the fill is the stop price.
4. **Same-bar ambiguity**: when a bar contains both a stop touch and a pending
   close-based exit, the trade is closed at the **worse** of the two available
   prices and the recorded reason is the event that produced that price.
5. **Reversal**: an opposite-direction signal while a position is open is
   *ignored*.  The position is closed only by the initial stop or by the
   Donchian-midpoint exit.  There is no pyramiding and no same-bar reversal.
6. The final open position (if any) is closed at the last close with reason
   ``end_of_data``.

Cost model
----------
Only the *observed* spread is used by default.  Commission, slippage and swap
are configurable **assumptions** (default 0) and are labelled as such in every
run record; no broker cost is invented.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from mars.libs.risk.contract_aware import ContractAwareFixedFractionalRisk, InstrumentSpec
from mars.libs.strategies.xau_mtf_donchian import MtfDonchianParams, compute_signals


@dataclass(frozen=True)
class CostModel:
    """Transaction cost assumptions.  Only ``spread_multiplier`` touches observed data."""

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
    """Fill conventions.  Recorded verbatim in every run record."""

    entry_fill: str = "next_bar_open"
    stop_fill: str = "gap_aware_conservative"
    same_bar_priority: str = "worst_price"
    exit_fill: str = "next_bar_open"
    reversal_policy: str = "opposite_signal_ignored"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
    params: MtfDonchianParams
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
            "strategy_id": "XAU-MTF-DONCHIAN-001",
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


# ---------------------------------------------------------------------------
# Session labelling (export-frame hours; see the data report for the anchor)
# ---------------------------------------------------------------------------

_SESSION_BOUNDS = ((0, 7, "Asia"), (7, 12, "London"), (12, 17, "Overlap"), (17, 21, "NY"), (21, 24, "Late"))


def session_of(ts: pd.Timestamp) -> str:
    """Bucket a timestamp into a trading session using the export frame's clock."""
    hour = ts.hour
    for lo, hi, name in _SESSION_BOUNDS:
        if lo <= hour < hi:
            return name
    return "Late"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MtfDonchianBacktester:
    """Event-driven bar-level backtester for XAU-MTF-DONCHIAN-001."""

    def __init__(
        self,
        params: Optional[MtfDonchianParams] = None,
        *,
        spec: Optional[InstrumentSpec] = None,
        cost_model: Optional[CostModel] = None,
        execution_model: Optional[ExecutionModel] = None,
        risk_policy: Optional[ContractAwareFixedFractionalRisk] = None,
    ) -> None:
        self.params = params or MtfDonchianParams()
        self.spec = spec or InstrumentSpec()
        self.cost_model = cost_model or CostModel()
        self.execution_model = execution_model or ExecutionModel()
        self.risk_policy = risk_policy or ContractAwareFixedFractionalRisk(
            spec=self.spec, risk_fraction=self.params.risk_fraction
        )

    # ------------------------------------------------------------------
    def run(self, m5: pd.DataFrame, h1: pd.DataFrame) -> BacktestResult:
        """Run the backtest over the supplied M5/H1 frames."""
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

        ts = signals["timestamp"].to_numpy()
        o = signals["open"].to_numpy(dtype=float)
        h = signals["high"].to_numpy(dtype=float)
        l = signals["low"].to_numpy(dtype=float)
        c = signals["close"].to_numpy(dtype=float)
        spread_pts = signals["spread"].to_numpy(dtype=float)
        atr = signals["atr"].to_numpy(dtype=float)
        stop_dist = signals["stop_distance"].to_numpy(dtype=float)
        entry_long = signals["entry_long"].to_numpy(dtype=bool)
        entry_short = signals["entry_short"].to_numpy(dtype=bool)
        exit_long = signals["exit_long"].to_numpy(dtype=bool)
        exit_short = signals["exit_short"].to_numpy(dtype=bool)

        point = self.spec.point_size
        mult = self.cost_model.spread_multiplier
        fallback = self.cost_model.fallback_spread_points
        slippage_price = self.cost_model.slippage_points * point

        # Observed spread in price units; bars with spread == 0 fall back to the
        # dataset median so that the cost model never silently assumes zero cost.
        spread_price = np.where(
            np.isfinite(spread_pts), spread_pts, fallback
        ) * point * mult
        zero_mask = ~np.isfinite(spread_pts) | (spread_pts <= 0)
        if self.cost_model.use_observed_spread:
            median_pts = float(np.nanmedian(spread_pts[spread_pts > 0])) if np.any(spread_pts > 0) else fallback
            spread_price = np.where(zero_mask, median_pts * point * mult, spread_price)
        else:
            spread_price = np.full(n, fallback * point * mult)

        equity = float(self.params.starting_equity)
        realized_equity = equity
        trades: List[Trade] = []
        rejected: List[Dict[str, Any]] = []
        equity_curve = np.empty(n, dtype=float)

        position: Optional[Dict[str, Any]] = None
        pending_entry: Optional[Dict[str, Any]] = None
        pending_exit: Optional[Dict[str, Any]] = None
        bars_in_market = 0

        for i in range(n):
            bar_open = o[i]
            bar_high = h[i]
            bar_low = l[i]
            bar_close = c[i]
            spr = spread_price[i]

            # ---- (A) execute a pending entry at this bar's open --------------
            if position is None and pending_entry is not None:
                side = pending_entry["side"]
                stop_distance = pending_entry["stop_distance"]
                # OHLC in the dataset are BID prices:
                #   long entry  buys at the ask -> bid_open + spread
                #   short entry sells at the bid -> bid_open
                raw = bar_open + (spr if side > 0 else 0.0)
                fill = raw + (side * slippage_price)
                from mars.libs.strategies.base import TradeSetup

                setup = TradeSetup(
                    timestamp=pd.Timestamp(ts[i]).to_pydatetime(),
                    symbol=self.spec.symbol,
                    side="long" if side > 0 else "short",
                    rationale="XAU-MTF-DONCHIAN-001 entry",
                    metadata={"stop_distance": stop_distance},
                )
                decision = self.risk_policy.evaluate(setup, equity=realized_equity)
                if decision.approved:
                    position = {
                        "side": side,
                        "entry_index": i,
                        "entry_time": pd.Timestamp(ts[i]),
                        "entry_price": float(fill),
                        "lots": float(decision.size),
                        "stop_distance": float(stop_distance),
                        "stop": float(fill - side * stop_distance),
                        "atr": float(pending_entry["atr"]),
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
                            "side": "long" if side > 0 else "short",
                            "reason": decision.reason,
                            "metadata": {k: v for k, v in decision.metadata.items()},
                        }
                    )
                pending_entry = None

            # ---- (B) manage an open position on this bar ---------------------
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

                stop_hit = (bar_low <= position["stop"]) if side > 0 else (bar_high >= position["stop"])
                stop_fill = None
                if stop_hit:
                    # Gap aware: fill at the open when the bar opened beyond the stop.
                    stop_fill = (
                        min(position["stop"], bar_open)
                        if side > 0
                        else max(position["stop"], bar_open)
                    )
                exit_fill = None
                if pending_exit is not None:
                    # Long exits sell at the bid, short exits buy at the ask.
                    exit_fill = bar_open if side > 0 else bar_open + spr

                candidates: List[tuple] = []
                if stop_fill is not None:
                    candidates.append((stop_fill, "stop"))
                if exit_fill is not None:
                    candidates.append((exit_fill, pending_exit["reason"]))
                if candidates:
                    if side > 0:
                        chosen = min(candidates, key=lambda x: x[0])
                    else:
                        chosen = max(candidates, key=lambda x: x[0])
                    trade = self._close_trade(
                        position, chosen[0], pd.Timestamp(ts[i]), chosen[1],
                        realized_equity, spr, i,
                    )
                    realized_equity = trade.equity_after
                    trades.append(trade)
                    position = None
                    pending_exit = None

            # ---- (C) evaluate signals at this bar's close --------------------
            if position is None:
                if pending_entry is None:
                    if entry_long[i]:
                        pending_entry = {
                            "side": 1,
                            "stop_distance": float(stop_dist[i]),
                            "atr": float(atr[i]),
                        }
                    elif entry_short[i]:
                        pending_entry = {
                            "side": -1,
                            "stop_distance": float(stop_dist[i]),
                            "atr": float(atr[i]),
                        }
            else:
                side = position["side"]
                if side > 0 and exit_long[i]:
                    pending_exit = {"reason": "donchian_mid_exit"}
                elif side < 0 and exit_short[i]:
                    pending_exit = {"reason": "donchian_mid_exit"}
                # Opposite entry signals are ignored while a position is open
                # (no reversal, no pyramiding).

            # mark to market for the equity curve
            unrealized = 0.0
            if position is not None:
                unrealized = (
                    (bar_close - position["entry_price"])
                    * position["side"]
                    * position["lots"]
                    * self.spec.contract_size
                )
            equity_curve[i] = realized_equity + unrealized

        # Close any position still open at the end of the sample.
        if position is not None:
            # A short is liquidated by buying at the ask, so the spread applies.
            final_price = float(c[-1]) if position["side"] > 0 else float(c[-1]) + float(spread_price[-1])
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
        # The observed spread is embedded in the fill prices.  A long pays it on
        # entry (buys at the ask) and a short pays it on exit (buys back at the
        # ask), so exactly one observed spread is crossed per round trip.
        spread_paid = (
            position["entry_spread"] if side > 0 else float(spread_at_exit)
        )
        spread_cost = float(spread_paid) * lots * contract
        commission = self.cost_model.commission_per_lot_round_trip * lots
        nights = max(0, (exit_time - position["entry_time"]).days)
        swap = self.cost_model.swap_per_lot_night * nights * lots
        net = gross - commission - swap

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
    "BacktestResult",
    "CostModel",
    "ExecutionModel",
    "MtfDonchianBacktester",
    "Trade",
    "session_of",
]
