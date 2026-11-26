"""
XAU-M5-PULLBACK-001 — Trend Pullback Continuation Strategy (M5 signals, M1/M5 execution).

Economically motivated: Trend continuation after pullback to EMA within 1 ATR.

Rules:
- H1 trend: EMA(50) slope (5 bars)
- M5 pullback: Price pulls back to EMA(20) within 1 ATR of EMA
- Entry: Pullback ends + candle closes back in trend direction
- Stop: Below pullback low (long) / above pullback high (short)
- Exit: Trend resumption failure (close crosses EMA against trend) or time
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd

from mars.libs.strategies.base import BaseStrategy, TradeSetup
from mars.libs.strategies.xau_scalping_donchian import (
    compute_atr, M5_MINUTES, H1_MINUTES,
    _require_timestamp
)


@dataclass(frozen=True)
class PullbackParams:
    """Immutable parameters for M5 Trend Pullback Continuation strategy."""
    # Signal parameters
    trend_ema_period: int = 50                # H1 trend EMA
    pullback_ema_period: int = 20             # M5 pullback EMA
    pullback_threshold_atr: float = 1.0       # Pullback within N ATR of EMA
    atr_period: int = 14                      # ATR period for stop
    atr_stop_mult: float = 2.0                # Stop distance = mult * ATR
    
    # Execution parameters
    max_hold_bars: int = 12                   # Max holding in execution bars
    risk_fraction: float = 0.01               # Risk per trade
    execution_timeframe: Literal["M1", "M5"] = "M5"
    
    # Risk parameters (Exness XAUUSDm)
    account_equity_usd: float = 30.0
    leverage: int = 2000
    min_lot: float = 0.01
    max_lot: float = 200.0
    lot_step: float = 0.01
    contract_size: float = 100.0
    point_size: float = 0.001
    pip_size: float = 0.01
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class PullbackSignalFrame:
    frame: pd.DataFrame
    params: PullbackParams
    execution_bars_used: int
    context_bars_used: int


def _compute_h1_trend(h1: pd.DataFrame, ema_period: int = 50, slope_bars: int = 5) -> pd.DataFrame:
    """Compute H1 trend from EMA slope."""
    h1_f = h1.copy()
    h1_ema = h1_f["close"].ewm(span=ema_period, adjust=False).mean()
    h1_ema_prev = h1_ema.shift(slope_bars)
    h1_trend = np.where(h1_ema > h1_ema_prev, 1, np.where(h1_ema < h1_ema_prev, -1, 0))
    
    h1_f["h1_ema"] = h1_ema
    h1_f["h1_ema_prev"] = h1_ema_prev
    h1_f["h1_trend"] = h1_trend
    h1_f["h1_completion"] = h1_f["timestamp"] + pd.Timedelta(minutes=H1_MINUTES)
    return h1_f


def compute_pullback_signals(
    execution_tf: pd.DataFrame,
    context_tf: pd.DataFrame,
    h1: pd.DataFrame,
    params: PullbackParams,
) -> PullbackSignalFrame:
    """
    Compute trend pullback continuation signals on M5.
    """
    tf_minutes = 1 if params.execution_timeframe == "M1" else 5
    
    exec_f = _require_timestamp(execution_tf, "execution_tf")
    ctx_f = _require_timestamp(context_tf, "context_tf")
    h1_f = _require_timestamp(h1, "h1")
    
    # --- H1 Trend ---
    h1_trend_df = _compute_h1_trend(h1_f, params.trend_ema_period, 5)
    
    # Align H1 to execution
    exec_f = exec_f.copy()
    exec_f["_pos"] = np.arange(len(exec_f))
    exec_f["exec_completion"] = exec_f["timestamp"] + pd.Timedelta(minutes=tf_minutes)
    
    aligned = pd.merge_asof(
        exec_f.sort_values("exec_completion"),
        h1_trend_df[["h1_completion", "h1_ema", "h1_ema_prev", "h1_trend"]].sort_values("h1_completion"),
        left_on="exec_completion",
        right_on="h1_completion",
        direction="backward",
    )
    aligned = aligned.sort_values("_pos").reset_index(drop=True)
    trend = aligned["h1_trend"].fillna(0).astype("int64")
    trend[aligned["h1_completion"].isna()] = 0
    
    # --- M5 Pullback EMA & ATR ---
    ctx_f = ctx_f.copy()
    ctx_f["ctx_completion"] = ctx_f["timestamp"] + pd.Timedelta(minutes=M5_MINUTES)
    
    pullback_ema = ctx_f["close"].ewm(span=params.pullback_ema_period, adjust=False).mean()
    atr_ctx = compute_atr(ctx_f, params.atr_period)
    stop_dist_ctx = params.atr_stop_mult * atr_ctx
    
    # Align context indicators to execution
    ctx_indicators = pd.DataFrame({
        "ctx_completion": ctx_f["ctx_completion"],
        "pullback_ema": pullback_ema,
        "atr": atr_ctx,
        "stop_distance": stop_dist_ctx,
    })
    
    aligned = pd.merge_asof(
        aligned.sort_values("exec_completion"),
        ctx_indicators.sort_values("ctx_completion"),
        left_on="exec_completion",
        right_on="ctx_completion",
        direction="backward",
    )
    aligned = aligned.sort_values("_pos").reset_index(drop=True)
    
    pullback_ema = aligned["pullback_ema"]
    atr = aligned["atr"]
    stop_distance = aligned["stop_distance"]
    close = aligned["close"]
    high = aligned["high"]
    low = aligned["low"]
    trend = aligned["h1_trend"]
    
    # --- Pullback Detection ---
    # Distance from close to pullback EMA (in ATR units)
    dist_to_ema_atr = (close - pullback_ema).abs() / atr
    pullback_long = (close < pullback_ema) & (dist_to_ema_atr <= params.pullback_threshold_atr) & (trend == 1)
    pullback_short = (close > pullback_ema) & (dist_to_ema_atr <= params.pullback_threshold_atr) & (trend == -1)
    
    # Track pullback state
    pullback_long_shifted = pullback_long.shift(1).fillna(False)
    pullback_short_shifted = pullback_short.shift(1).fillna(False)
    
    # Entry: Pullback ends + candle closes back in trend direction
    # Long: was in pullback, now close > pullback_ema (reclaimed EMA)
    # Short: was in pullback, now close < pullback_ema
    entry_long = pullback_long_shifted & (close > pullback_ema) & (trend == 1)
    entry_short = pullback_short_shifted & (close < pullback_ema) & (trend == -1)
    
    # Exit: Trend resumption failure (close crosses EMA against trend)
    exit_long = (trend == 1) & (close < pullback_ema)
    exit_short = (trend == -1) & (close > pullback_ema)
    
    max_hold = params.max_hold_bars
    
    out = pd.DataFrame({
        "timestamp": aligned["timestamp"],
        "open": aligned["open"],
        "high": aligned["high"],
        "low": aligned["low"],
        "close": aligned["close"],
        "spread": aligned["spread"] if "spread" in aligned.columns else np.nan,
        "volume": aligned["volume"] if "volume" in aligned.columns else np.nan,
        "trend_ema": aligned["h1_ema"],
        "pullback_ema": pullback_ema,
        "atr": atr,
        "stop_distance": stop_distance,
        "h1_trend": trend,
        "h1_completion": aligned["h1_completion"],
        "entry_long": entry_long,
        "entry_short": entry_short,
        "exit_long": exit_long,
        "exit_short": exit_short,
        "max_holding_bars": max_hold,
    })
    
    return PullbackSignalFrame(
        frame=out,
        params=params,
        execution_bars_used=len(out),
        context_bars_used=len(ctx_f),
    )


class XauM5PullbackStrategy(BaseStrategy):
    """BaseStrategy adapter for M5 Trend Pullback Continuation."""
    
    def __init__(self, params: Optional[PullbackParams] = None, symbol: str = "XAUUSDm"):
        super().__init__(name="XAU-M5-PULLBACK-001", symbol=symbol)
        self.params = params or PullbackParams()
    
    def generate_setups(
        self,
        market_data: pd.DataFrame,
        *,
        context_tf: Optional[pd.DataFrame] = None,
        h1: Optional[pd.DataFrame] = None,
        **kwargs: Any,
    ) -> List[TradeSetup]:
        ctx = context_tf if context_tf is not None else kwargs.get("context_tf")
        h1_f = h1 if h1 is not None else kwargs.get("h1")
        
        if ctx is None or (isinstance(ctx, pd.DataFrame) and ctx.empty):
            raise ValueError("XauM5PullbackStrategy.generate_setups requires context_tf")
        if h1_f is None or (isinstance(h1_f, pd.DataFrame) and h1_f.empty):
            raise ValueError("XauM5PullbackStrategy.generate_setups requires h1")
        
        signals = compute_pullback_signals(market_data, ctx, h1_f, self.params).frame
        setups: List[TradeSetup] = []
        
        for i in range(len(signals)):
            row = signals.iloc[i]
            side = "flat"
            if bool(row["entry_long"]):
                side = "long"
            elif bool(row["entry_short"]):
                side = "short"
            else:
                continue
            
            setups.append(TradeSetup(
                timestamp=row["timestamp"].to_pydatetime(),
                symbol=self.symbol,
                side=side,
                confidence=None,
                rationale=(
                    f"Pullback continuation: close {row['close']:.2f} reclaimed EMA({self.params.pullback_ema_period}) "
                    f"after pullback within {self.params.pullback_threshold_atr} ATR "
                    f"with H1 trend {int(row['h1_trend']):+d} "
                    f"[{self.params.execution_timeframe} execution]"
                ),
                metadata={
                    "stop_distance": float(row["stop_distance"]),
                    "atr": float(row["atr"]),
                    "pullback_ema": float(row["pullback_ema"]),
                    "trend": int(row["h1_trend"]),
                    "execution_timeframe": self.params.execution_timeframe,
                    "max_holding_bars": int(row["max_holding_bars"]),
                },
            ))
        return setups


__all__ = [
    "PullbackParams",
    "PullbackSignalFrame",
    "XauM5PullbackStrategy",
    "compute_pullback_signals",
]