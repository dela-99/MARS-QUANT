"""
Generic M5→M1 Execution Backtester.

Uses Assignment 23's M5ToM1Alignment for no-look-ahead alignment
and ExnessXAUUSDmCostModel (via CostAdapter) for itemized costs.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from mars.libs.execution.alignment import M5ToM1Alignment, create_aligned_execution_frame
from mars.libs.execution.cost_adapter import CostAdapter
from mars.libs.execution.cost_model import CostBreakdown
from mars.libs.risk.contract_aware import ContractAwareFixedFractionalRisk, InstrumentSpec
from mars.libs.strategies.xau_scalping_donchian import M1_MINUTES, M5_MINUTES


@dataclass
class Trade:
    """One closed trade with full cost breakdown."""
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
    slippage: float
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
    execution_timeframe: str = "M1"
    max_holding_bars: int = 0
    time_exit_triggered: bool = False
    # Cost breakdown from ExnessXAUUSDmCostModel
    cost_breakdown: Optional[CostBreakdown] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("entry_time", "exit_time"):
            d[k] = str(d[k])
        if self.cost_breakdown:
            d["cost_breakdown"] = self.cost_breakdown.to_dict()
        return d


@dataclass
class BacktestResult:
    trades: List[Trade]
    equity_curve: pd.Series
    daily_equity: pd.Series
    rejected_signals: List[Dict[str, Any]]
    params: Any
    cost_adapter: CostAdapter
    spec: InstrumentSpec
    starting_equity: float
    bars_in_market: int
    total_bars: int
    final_equity: float
    time_exits: int = 0
    stop_exits: int = 0
    mid_exits: int = 0
    end_of_data_exits: int = 0
    
    def trades_frame(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.to_dict() for t in self.trades])


def _session_of(ts: pd.Timestamp) -> str:
    hour = ts.hour
    if 0 <= hour < 7: return "Asia"
    elif 7 <= hour < 12: return "London"
    elif 12 <= hour < 17: return "Overlap"
    elif 17 <= hour < 21: return "NY"
    else: return "Late"


class M5M1ExecutionBacktester:
    """
    Generic M5-signal / M1-execution backtester.
    
    Uses Assignment 23's M5ToM1Alignment for no-look-ahead alignment
    and ExnessXAUUSDmCostModel (via CostAdapter) for itemized costs.
    """
    
    def __init__(
        self,
        params: Any,
        *,
        spec: Optional[InstrumentSpec] = None,
        cost_adapter: Optional[CostAdapter] = None,
        risk_policy: Optional[ContractAwareFixedFractionalRisk] = None,
    ):
        self.params = params
        self.spec = spec or InstrumentSpec(
            symbol="XAUUSDm", contract_size=100.0, pip_size=0.01, point_size=0.001,
            quote_currency="USD", volume_min=0.01, volume_max=200.0, volume_step=0.01,
            volume_spec_source="mt5.live", spec_source="mt5.live",
        )
        self.cost_adapter = cost_adapter
        self.risk_policy = risk_policy or ContractAwareFixedFractionalRisk(
            spec=self.spec, risk_fraction=getattr(params, "risk_fraction", 0.01)
        )
        self.aligner = M5ToM1Alignment()
    
    def run(
        self,
        m5_signals: pd.DataFrame,
        m1_execution: pd.DataFrame,
        h1: pd.DataFrame,
    ) -> BacktestResult:
        """
        Run backtest with M5 signals executed on M1 bars.
        
        Parameters
        ----------
        m5_signals: DataFrame from strategy's compute_*_signals() with columns:
            timestamp, open, high, low, close, spread, volume,
            donchian_high, donchian_low, donchian_mid, atr, stop_distance,
            h1_regime, entry_long, entry_short, exit_long, exit_short,
            max_holding_bars, h1_completion
        m1_execution: M1 OHLCV with timestamp, open, high, low, close, spread, volume
        h1: H1 OHLCV (for regime, already in signals but kept for completeness)
        """
        # Align M5 signals to M1 execution bars
        aligned = self.aligner.align_signals_to_execution(m5_signals, m1_execution)
        
        # Verify no look-ahead
        checks = self.aligner.check_no_lookahead(aligned)
        if not checks["passed"]:
            raise ValueError(f"Look-ahead detected in alignment: {checks}")
        
        n = len(aligned)
        if n < 2:
            return BacktestResult(
                trades=[], equity_curve=pd.Series(dtype=float), daily_equity=pd.Series(dtype=float),
                rejected_signals=[], params=self.params, cost_adapter=self.cost_adapter,
                spec=self.spec, starting_equity=getattr(self.params, "starting_equity", 10000.0),
                bars_in_market=0, total_bars=n, final_equity=getattr(self.params, "starting_equity", 10000.0),
            )
        
        # Extract arrays - use timestamp_x (M1 execution timestamp) as primary
        ts = aligned["timestamp_x"].to_numpy()
        o = aligned["open"].to_numpy(dtype=float)
        h = aligned["high"].to_numpy(dtype=float)
        l = aligned["low"].to_numpy(dtype=float)
        c = aligned["close"].to_numpy(dtype=float)
        spread_pts = aligned["spread"].to_numpy(dtype=float) if "spread" in aligned.columns else np.full(n, 200.0)
        
        # Signal columns (prefixed with m5_signal_)
        entry_long = aligned.get("m5_signal_entry_long", pd.Series(False, index=aligned.index)).to_numpy(dtype=bool)
        entry_short = aligned.get("m5_signal_entry_short", pd.Series(False, index=aligned.index)).to_numpy(dtype=bool)
        exit_long = aligned.get("m5_signal_exit_long", pd.Series(False, index=aligned.index)).to_numpy(dtype=bool)
        exit_short = aligned.get("m5_signal_exit_short", pd.Series(False, index=aligned.index)).to_numpy(dtype=bool)
        stop_dist = aligned.get("m5_signal_stop_distance", pd.Series(np.nan, index=aligned.index)).to_numpy(dtype=float)
        atr_arr = aligned.get("m5_signal_atr", pd.Series(np.nan, index=aligned.index)).to_numpy(dtype=float)
        donchian_mid = aligned.get("m5_signal_donchian_mid", pd.Series(np.nan, index=aligned.index)).to_numpy(dtype=float)
        max_hb = aligned.get("m5_signal_max_holding_bars", pd.Series(6, index=aligned.index)).to_numpy(dtype=int)
        h1_regime = aligned.get("m5_signal_h1_regime", pd.Series(0, index=aligned.index)).to_numpy(dtype=int)
        
        point_value = self.spec.contract_size * self.spec.point_size  # $0.10 per point per lot
        equity = float(getattr(self.params, "starting_equity", 10000.0))
        realized_equity = equity
        trades: List[Trade] = []
        rejected: List[Dict[str, Any]] = []
        equity_curve = np.empty(n, dtype=float)
        
        position: Optional[Dict[str, Any]] = None
        pending_entry: Optional[Dict[str, Any]] = None
        pending_exit: Optional[Dict[str, Any]] = None
        bars_in_market = 0
        time_exits = stop_exits = mid_exits = end_of_data_exits = 0
        
        for i in range(n):
            bar_open = o[i]
            bar_high = h[i]
            bar_low = l[i]
            bar_close = c[i]
            spr_pts = spread_pts[i]
            spread_price = spr_pts * self.spec.point_size
            max_h = int(max_hb[i]) if i < len(max_hb) else 6
            
            # (A) Execute pending entry at this bar's open
            if position is None and pending_entry is not None:
                side = pending_entry["side"]
                sd = pending_entry["stop_distance"]
                atr_val = pending_entry["atr"]
                
                # Entry fill: long pays ask (bid + spread), short receives bid
                raw_fill = bar_open + (spread_price if side > 0 else 0.0)
                fill_price = raw_fill  # Slippage handled in cost model
                
                from mars.libs.strategies.base import TradeSetup
                setup = TradeSetup(
                    timestamp=pd.Timestamp(ts[i]).to_pydatetime(),
                    symbol=self.spec.symbol,
                    side="long" if side > 0 else "short",
                    rationale="M5 signal executed on M1",
                    metadata={"stop_distance": sd},
                )
                
                decision = self.risk_policy.evaluate(
                    setup, equity=realized_equity, quote_to_usd=1.0
                )
                
                if decision.approved:
                    position = {
                        "side": side,
                        "entry_index": i,
                        "entry_time": pd.Timestamp(ts[i]),
                        "entry_price": float(fill_price),
                        "lots": float(decision.size),
                        "stop_distance": float(sd),
                        "stop": float(fill_price - side * sd),
                        "atr": float(atr_val),
                        "entry_spread_pts": float(spr_pts),
                        "mae": float(fill_price),
                        "mfe": float(fill_price),
                        "equity_before": realized_equity,
                        "entry_session": _session_of(pd.Timestamp(ts[i])),
                        "bars": 0,
                        "max_holding_bars": max_h,
                    }
                else:
                    rejected.append({
                        "time": str(pd.Timestamp(ts[i])),
                        "side": "long" if side > 0 else "short",
                        "reason": decision.reason,
                        "metadata": {k: v for k, v in decision.metadata.items()},
                    })
                pending_entry = None
            
            # (B) Manage open position
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
                
                # Check stop hit (intrabar)
                stop_hit = (bar_low <= position["stop"]) if side > 0 else (bar_high >= position["stop"])
                stop_fill = None
                if stop_hit:
                    # Gap-aware conservative: if opened beyond stop, fill at open
                    stop_fill = (
                        min(position["stop"], bar_open) if side > 0
                        else max(position["stop"], bar_open)
                    )
                
                # Check time exit
                time_exit = position["bars"] >= position["max_holding_bars"]
                time_fill = None
                if time_exit:
                    time_fill = bar_open if side > 0 else bar_open + spread_price
                
                # Check structural exit (midpoint cross)
                exit_fill = None
                exit_reason = None
                if pending_exit is not None:
                    exit_fill = bar_open if side > 0 else bar_open + spread_price
                    exit_reason = pending_exit["reason"]
                
                # Collect exit candidates, choose worst price
                candidates = []
                if stop_fill is not None:
                    candidates.append((stop_fill, "stop"))
                if time_fill is not None:
                    candidates.append((time_fill, "time_exit"))
                if exit_fill is not None:
                    candidates.append((exit_fill, exit_reason))
                
                if candidates:
                    if side > 0:
                        chosen_price, chosen_reason = min(candidates, key=lambda x: x[0])
                    else:
                        chosen_price, chosen_reason = max(candidates, key=lambda x: x[0])
                    
                    if chosen_reason == "time_exit":
                        time_exits += 1
                    elif chosen_reason == "stop":
                        stop_exits += 1
                    elif chosen_reason in ("donchian_mid_exit", "mid_exit", "vwap_exit", "band_exit"):
                        mid_exits += 1
                    
                    trade = self._close_trade(
                        position, chosen_price, pd.Timestamp(ts[i]), chosen_reason,
                        realized_equity, spread_price, i, time_exit_triggered=(chosen_reason == "time_exit"),
                        exit_spread_pts=spr_pts,
                    )
                    realized_equity = trade.equity_after
                    trades.append(trade)
                    position = None
                    pending_exit = None
            
            # (C) Evaluate signals at this bar's close
            if position is None:
                if pending_entry is None:
                    sd = stop_dist[i]
                    atr_val = atr_arr[i]
                    if np.isfinite(sd) and np.isfinite(atr_val) and sd > 0:
                        if entry_long[i]:
                            pending_entry = {"side": 1, "stop_distance": float(sd), "atr": float(atr_val)}
                        elif entry_short[i]:
                            pending_entry = {"side": -1, "stop_distance": float(sd), "atr": float(atr_val)}
            else:
                side = position["side"]
                if side > 0 and exit_long[i]:
                    pending_exit = {"reason": "donchian_mid_exit"}
                elif side < 0 and exit_short[i]:
                    pending_exit = {"reason": "donchian_mid_exit"}
            
            # Mark to market
            unrealized = 0.0
            if position is not None:
                unrealized = (bar_close - position["entry_price"]) * position["side"] * position["lots"] * self.spec.contract_size
            equity_curve[i] = realized_equity + unrealized
        
        # Close any open position at end
        if position is not None:
            final_price = float(c[-1]) if position["side"] > 0 else float(c[-1]) + float(spread_price)
            trade = self._close_trade(
                position, final_price, pd.Timestamp(ts[-1]), "end_of_data",
                realized_equity, float(spread_price), n - 1, time_exit_triggered=False,
                exit_spread_pts=spread_pts[-1],
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
            cost_adapter=self.cost_adapter,
            spec=self.spec,
            starting_equity=float(getattr(self.params, "starting_equity", 10000.0)),
            bars_in_market=bars_in_market,
            total_bars=n,
            final_equity=float(realized_equity),
            time_exits=time_exits,
            stop_exits=stop_exits,
            mid_exits=mid_exits,
            end_of_data_exits=end_of_data_exits,
        )
    
    def _close_trade(
        self,
        position: Dict[str, Any],
        exit_price: float,
        exit_time: pd.Timestamp,
        reason: str,
        realized_equity: float,
        spread_price: float,
        index: int,
        time_exit_triggered: bool,
        exit_spread_pts: float,
    ) -> Trade:
        side = position["side"]
        lots = position["lots"]
        entry_price = position["entry_price"]
        contract = self.spec.contract_size
        
        gross = (exit_price - entry_price) * side * lots * contract
        
        # Use detailed cost model if available
        if self.cost_adapter:
            cost_bd = self.cost_adapter.calculate_trade_cost(
                lots=lots,
                entry_spread_points=position["entry_spread_pts"],
                exit_spread_points=exit_spread_pts,
                hold_nights=max(0, (exit_time - position["entry_time"]).days),
                side="long" if side > 0 else "short",
                entry_price=entry_price,
            )
            spread_cost = cost_bd.spread_cost_usd
            commission = cost_bd.commission_usd
            swap = cost_bd.swap_usd
            slippage = cost_bd.slippage_usd
            net = gross - commission - swap - slippage
        else:
            # Fallback simple cost
            spread_cost = position["entry_spread_pts"] * self.spec.point_size * contract * lots if side > 0 else exit_spread_pts * self.spec.point_size * contract * lots
            commission = 0.0
            swap = 0.0
            slippage = 0.0
            net = gross - spread_cost
            cost_bd = None
        
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
            slippage=slippage,
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
            exit_session=_session_of(exit_time),
            execution_timeframe=getattr(self.params, "execution_timeframe", "M1"),
            max_holding_bars=position["max_holding_bars"],
            time_exit_triggered=time_exit_triggered,
            cost_breakdown=cost_bd,
        )


__all__ = ["M5M1ExecutionBacktester", "Trade", "BacktestResult"]