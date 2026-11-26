"""
Bar-level execution engine for XAU-SCALPING-DONCHIAN-001 (Assignment 22).

Extends the Version 1 XAU-MTF-DONCHIAN-001 backtester with:
- Configurable execution timeframe (M1 or M5)
- Max holding duration (time-based exit)
- $30 account risk engine integration with Exness XAUUSDm specs
- Signal/Execution separation (signals from compute_scalping_signals, execution here)
- Explicit fill conventions, cost model, rejection logging

Fill conventions (from Version 1, extended for scalping)
--------------------------------------------------------
1. **Entries** at the **open of the next available bar** after signal candle closes.
2. **Spread** from observed per-bar spread column (OHLC are bid prices):
   * Long entry pays ask -> open + spread
   * Long exit receives bid -> open
   * Short entry receives bid -> open
   * Short exit pays ask -> open + spread
   One round trip = one observed spread.
3. **Stop fills**: gap-aware conservative. If bar opens beyond stop -> fill at open.
   Otherwise fill at stop price.
4. **Same-bar ambiguity**: stop touch + close-based exit -> worse price, reason = that event.
5. **Time exit**: at max_holding_bars, exit at next bar open with reason "time_exit".
6. **Reversal**: Opposite signal while position open is IGNORED (no pyramiding, no reversal).
7. **End of data**: Final open position closed at last close with reason "end_of_data".

Cost model
----------
Only observed spread by default. Commission, slippage, swap are configurable
assumptions (default 0) and labelled as such in every run record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from mars.libs.risk.contract_aware import ContractAwareFixedFractionalRisk, InstrumentSpec
from mars.libs.strategies.xau_scalping_donchian import (
    ScalpingDonchianParams,
    ScalpingSignalFrame,
    compute_scalping_signals,
    M1_MINUTES,
    M5_MINUTES,
    H1_MINUTES,
)


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
# Cost & Execution Models
# ---------------------------------------------------------------------------


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
    time_exit_fill: str = "next_bar_open"
    reversal_policy: str = "opposite_signal_ignored"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Trade & Result Records
# ---------------------------------------------------------------------------


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
    # Scalping-specific
    execution_timeframe: str = "M5"
    max_holding_bars: int = 0
    time_exit_triggered: bool = False

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
    params: ScalpingDonchianParams
    cost_model: CostModel
    execution_model: ExecutionModel
    spec: InstrumentSpec
    starting_equity: float
    bars_in_market: int
    total_bars: int
    final_equity: float
    # Scalping stats
    time_exits: int = 0
    stop_exits: int = 0
    mid_exits: int = 0
    end_of_data_exits: int = 0

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
                    "execution_timeframe", "max_holding_bars", "time_exit_triggered",
                ]
            )
        return pd.DataFrame([t.to_dict() for t in self.trades])

    def run_record(self) -> Dict[str, Any]:
        return {
            "strategy_id": "XAU-SCALPING-DONCHIAN-001",
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
            "exit_breakdown": {
                "time_exits": self.time_exits,
                "stop_exits": self.stop_exits,
                "mid_exits": self.mid_exits,
                "end_of_data_exits": self.end_of_data_exits,
            },
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class XauScalpingDonchianBacktester:
    """Event-driven bar-level backtester for XAU-SCALPING-DONCHIAN-001."""

    def __init__(
        self,
        params: Optional[ScalpingDonchianParams] = None,
        *,
        spec: Optional[InstrumentSpec] = None,
        cost_model: Optional[CostModel] = None,
        execution_model: Optional[ExecutionModel] = None,
        risk_policy: Optional[ContractAwareFixedFractionalRisk] = None,
    ) -> None:
        self.params = params or ScalpingDonchianParams()
        self.spec = spec or self._default_spec()
        self.cost_model = cost_model or CostModel()
        self.execution_model = execution_model or ExecutionModel()

        # Risk policy: use $30 account equity for sizing, but preserve $10k for research comparability
        # The risk_fraction is 1% of whatever equity is passed to evaluate()
        if risk_policy is None:
            self.risk_policy = ContractAwareFixedFractionalRisk(
                spec=self.spec,
                risk_fraction=self.params.risk_fraction,
                enforce_volume_rules=True,
            )
        else:
            self.risk_policy = risk_policy

    def _default_spec(self) -> InstrumentSpec:
        """Exness XAUUSDm verified specifications."""
        return InstrumentSpec(
            symbol="XAUUSDm",
            contract_size=100.0,       # troy ounces per lot
            pip_size=0.01,             # 1 pip = 0.01 price units
            point_size=0.001,          # broker tick
            quote_currency="USD",
            volume_min=0.01,           # Exness min lot
            volume_max=200.0,          # Exness max lot
            volume_step=0.01,          # Exness lot step
            volume_spec_source="mt5.live",
            spec_source="mt5.live",
        )

    # ------------------------------------------------------------------
    def run(
        self,
        execution_tf: pd.DataFrame,
        context_tf: pd.DataFrame,
        h1: pd.DataFrame,
    ) -> BacktestResult:
        """
        Run the backtest over the supplied execution, context, and H1 frames.

        Parameters
        ----------
        execution_tf: Execution timeframe (M1 or M5 per params.execution_timeframe)
        context_tf: Context timeframe (M5 when execution=M1; same as execution_tf when M5)
        h1: H1 timeframe for regime
        """
        signals = compute_scalping_signals(
            execution_tf, context_tf, h1, self.params
        ).frame

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
        entry_short = signals["entry_short"].to_numpy(dtype=bool)
        exit_long = signals["exit_long"].to_numpy(dtype=bool)
        exit_short = signals["exit_short"].to_numpy(dtype=bool)
        max_holding_bars = signals["max_holding_bars"].to_numpy(dtype=int)
        h1_regime = signals["h1_regime"].to_numpy(dtype=int)

        point = self.spec.point_size
        mult = self.cost_model.spread_multiplier
        fallback = self.cost_model.fallback_spread_points
        slippage_price = self.cost_model.slippage_points * point

        # Observed spread in price units
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
        pending_entry: Optional[Dict[str, Any]] = None
        pending_exit: Optional[Dict[str, Any]] = None
        bars_in_market = 0

        # Exit reason counters
        time_exits = 0
        stop_exits = 0
        mid_exits = 0
        end_of_data_exits = 0

        tf_minutes = M1_MINUTES if self.params.execution_timeframe == "M1" else M5_MINUTES

        for i in range(n):
            bar_open = o[i]
            bar_high = h[i]
            bar_low = l[i]
            bar_close = c[i]
            spr = spread_price[i]
            max_hb = max_holding_bars[i] if i < len(max_holding_bars) else 6

            # ---- (A) Execute pending entry at this bar's open --------------
            if position is None and pending_entry is not None:
                side = pending_entry["side"]
                stop_distance = pending_entry["stop_distance"]
                atr_val = pending_entry["atr"]

                # OHLC are BID prices:
                # Long entry buys at ask -> bid_open + spread
                # Short entry sells at bid -> bid_open
                raw = bar_open + (spr if side > 0 else 0.0)
                fill = raw + (side * slippage_price)

                from mars.libs.strategies.base import TradeSetup
                setup = TradeSetup(
                    timestamp=pd.Timestamp(ts[i]).to_pydatetime(),
                    symbol=self.spec.symbol,
                    side="long" if side > 0 else "short",
                    rationale="XAU-SCALPING-DONCHIAN-001 entry",
                    metadata={"stop_distance": stop_distance},
                )

                # Use account_equity_usd for live feasibility, but research uses starting_equity
                # Pass quote_to_usd=1.0 for XAUUSDm (USD-quoted)
                decision = self.risk_policy.evaluate(
                    setup,
                    equity=realized_equity,
                    quote_to_usd=1.0,
                )

                if decision.approved:
                    position = {
                        "side": side,
                        "entry_index": i,
                        "entry_time": pd.Timestamp(ts[i]),
                        "entry_price": float(fill),
                        "lots": float(decision.size),
                        "stop_distance": float(stop_distance),
                        "stop": float(fill - side * stop_distance),
                        "atr": float(atr_val),
                        "entry_spread": float(spr),
                        "mae": float(fill),
                        "mfe": float(fill),
                        "equity_before": realized_equity,
                        "entry_session": session_of(pd.Timestamp(ts[i])),
                        "bars": 0,
                        "max_holding_bars": int(max_hb),
                    }
                else:
                    rejected.append({
                        "time": str(pd.Timestamp(ts[i])),
                        "side": "long" if side > 0 else "short",
                        "reason": decision.reason,
                        "metadata": {k: v for k, v in decision.metadata.items()},
                    })
                pending_entry = None

            # ---- (B) Manage open position on this bar ---------------------
            if position is not None:
                side = position["side"]
                position["bars"] += 1
                bars_in_market += 1

                # Update MAE/MFE
                if side > 0:
                    position["mae"] = min(position["mae"], bar_low)
                    position["mfe"] = max(position["mfe"], bar_high)
                else:
                    position["mae"] = max(position["mae"], bar_high)
                    position["mfe"] = min(position["mfe"], bar_low)

                # Check stop hit
                stop_hit = (bar_low <= position["stop"]) if side > 0 else (bar_high >= position["stop"])
                stop_fill = None
                if stop_hit:
                    # Gap aware: fill at open when bar opened beyond stop
                    stop_fill = (
                        min(position["stop"], bar_open)
                        if side > 0
                        else max(position["stop"], bar_open)
                    )

                # Check time exit (max holding bars reached)
                time_exit = position["bars"] >= position["max_holding_bars"]
                time_fill = None
                if time_exit:
                    # Time exit at next bar open (handled after signal eval)
                    # But we mark it now so we don't enter a new position
                    time_fill = bar_open if side > 0 else bar_open + spr

                # Check structural exit (Donchian midpoint cross)
                exit_fill = None
                exit_reason = None
                if pending_exit is not None:
                    # Long exits sell at bid, short exits buy at ask
                    exit_fill = bar_open if side > 0 else bar_open + spr
                    exit_reason = pending_exit["reason"]

                # Collect exit candidates
                candidates: List[tuple] = []
                if stop_fill is not None:
                    candidates.append((stop_fill, "stop"))
                if time_fill is not None:
                    candidates.append((time_fill, "time_exit"))
                if exit_fill is not None:
                    candidates.append((exit_fill, exit_reason))

                if candidates:
                    if side > 0:
                        chosen = min(candidates, key=lambda x: x[0])
                    else:
                        chosen = max(candidates, key=lambda x: x[0])

                    # Count exit type
                    if chosen[1] == "time_exit":
                        time_exits += 1
                    elif chosen[1] == "stop":
                        stop_exits += 1
                    elif chosen[1] in ("donchian_mid_exit",):
                        mid_exits += 1

                    trade = self._close_trade(
                        position, chosen[0], pd.Timestamp(ts[i]), chosen[1],
                        realized_equity, spr, i, time_exit_triggered=(chosen[1] == "time_exit"),
                    )
                    realized_equity = trade.equity_after
                    trades.append(trade)
                    position = None
                    pending_exit = None

            # ---- (C) Evaluate signals at this bar's close --------------------
            if position is None:
                if pending_entry is None:
                    # Skip signals with NaN stop_distance (insufficient data for ATR)
                    sd = stop_dist[i]
                    atr_val = atr[i]
                    if np.isfinite(sd) and np.isfinite(atr_val) and sd > 0:
                        if entry_long[i]:
                            pending_entry = {
                                "side": 1,
                                "stop_distance": float(sd),
                                "atr": float(atr_val),
                            }
                        elif entry_short[i]:
                            pending_entry = {
                                "side": -1,
                                "stop_distance": float(sd),
                                "atr": float(atr_val),
                            }
            else:
                side = position["side"]
                if side > 0 and exit_long[i]:
                    pending_exit = {"reason": "donchian_mid_exit"}
                elif side < 0 and exit_short[i]:
                    pending_exit = {"reason": "donchian_mid_exit"}
                # Opposite entry signals ignored while position open

            # Mark to market for equity curve
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
            final_price = float(c[-1]) if position["side"] > 0 else float(c[-1]) + float(spread_price[-1])
            trade = self._close_trade(
                position, final_price, pd.Timestamp(ts[-1]), "end_of_data",
                realized_equity, spread_price[-1], n - 1, time_exit_triggered=False,
            )
            realized_equity = trade.equity_after
            trades.append(trade)
            equity_curve[-1] = realized_equity
            end_of_data_exits += 1

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
            time_exits=time_exits,
            stop_exits=stop_exits,
            mid_exits=mid_exits,
            end_of_data_exits=end_of_data_exits,
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
        time_exit_triggered: bool = False,
    ) -> Trade:
        """Close a position and build the ledger row."""
        side = position["side"]
        lots = position["lots"]
        entry_price = position["entry_price"]
        contract = self.spec.contract_size

        gross = (exit_price - entry_price) * side * lots * contract

        # Spread cost: long pays on entry, short pays on exit (one spread per round trip)
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
            execution_timeframe=self.params.execution_timeframe,
            max_holding_bars=position["max_holding_bars"],
            time_exit_triggered=time_exit_triggered,
        )


__all__ = [
    "BacktestResult",
    "CostModel",
    "ExecutionModel",
    "Trade",
    "XauScalpingDonchianBacktester",
    "session_of",
]