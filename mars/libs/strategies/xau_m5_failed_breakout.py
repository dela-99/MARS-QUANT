"""
XAU-M5-FAILED-BREAKOUT-001 — Failed Breakout Reversal Strategy (M5 signals, M1/M5 execution).

Economically motivated: Reversal after Donchian/Bollinger breakout fails within N bars.

Rules:
- Donchian/Bollinger breakout on M5
- Failure: Price closes back inside channel within `failure_bars`
- Entry: Reversal candle in opposite direction
- Stop: Tight (0.5-1 ATR) beyond failure extreme
- Exit: Opposite band hit or time (very short hold)
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
class FailedBreakoutParams:
    """Immutable parameters for M5 Failed Breakout Reversal strategy."""
    # Signal parameters
    donchian_lookback: int = 20             # Donchian lookback
    bb_period: int = 20                     # Bollinger Band period
    bb_std: float = 2.0                     # Bollinger Band std multiplier
    failure_bars: int = 3                   # Bars to confirm failure
    atr_period: int = 14                    # ATR period for stop
    atr_stop_mult: float = 1.0              # Stop distance = mult * ATR (tight)
    
    # Execution parameters
    max_hold_bars: int = 3                  # Max holding in execution bars (very short)
    risk_fraction: float = 0.01             # Risk per trade
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
class FailedBreakoutSignalFrame:
    frame: pd.DataFrame
    params: FailedBreakoutParams
    execution_bars_used: int
    context_bars_used: int


def compute_failed_breakout_signals(
    execution_tf: pd.DataFrame,
    context_tf: pd.DataFrame,
    h1: pd.DataFrame,
    params: FailedBreakoutParams,
) -> FailedBreakoutSignalFrame:
    """
    Compute failed breakout reversal signals on M5.
    """
    tf_minutes = 1 if params.execution_timeframe == "M1" else 5
    
    exec_f = _require_timestamp(execution_tf, "execution_tf")
    ctx_f = _require_timestamp(context_tf, "context_tf")
    h1_f = _require_timestamp(h1, "h1")
    
    # --- H1 Regime (simple EMA slope) ---
    h1_ema = h1_f["close"].ewm(span=20, adjust=False).mean()
    h1_ema_prev = h1_ema.shift(5)
    h1_regime = np.where(h1_ema > h1_ema_prev, 1, np.where(h1_ema < h1_ema_prev, -1, 0))
    
    h1_f = h1_f.copy()
    h1_f["h1_ema"] = h1_ema
    h1_f["h1_ema_prev"] = h1_ema_prev
    h1_f["h1_regime"] = h1_regime
    h1_f["h1_completion"] = h1_f["timestamp"] + pd.Timedelta(minutes=H1_MINUTES)
    
    # Align H1 to execution
    exec_f = exec_f.copy()
    exec_f["_pos"] = np.arange(len(exec_f))
    exec_f["exec_completion"] = exec_f["timestamp"] + pd.Timedelta(minutes=tf_minutes)
    
    aligned = pd.merge_asof(
        exec_f.sort_values("exec_completion"),
        h1_f[["h1_completion", "h1_ema", "h1_ema_prev", "h1_regime"]].sort_values("h1_completion"),
        left_on="exec_completion",
        right_on="h1_completion",
        direction="backward",
    )
    aligned = aligned.sort_values("_pos").reset_index(drop=True)
    regime = aligned["h1_regime"].fillna(0).astype("int64")
    regime[aligned["h1_completion"].isna()] = 0
    
    # --- M5 Donchian & Bollinger Bands ---
    ctx_f = ctx_f.copy()
    ctx_f["ctx_completion"] = ctx_f["timestamp"] + pd.Timedelta(minutes=M5_MINUTES)
    
    # Donchian
    prior_high = ctx_f["high"].shift(1)
    prior_low = ctx_f["low"].shift(1)
    donchian_high = prior_high.rolling(params.donchian_lookback, min_periods=params.donchian_lookback).max()
    donchian_low = prior_low.rolling(params.donchian_lookback, min_periods=params.donchian_lookback).min()
    donchian_mid = (donchian_high + donchian_low) / 2.0
    
    # Bollinger Bands
    bb_mid = ctx_f["close"].rolling(params.bb_period, min_periods=params.bb_period).mean()
    bb_std = ctx_f["close"].rolling(params.bb_period, min_periods=params.bb_period).std()
    bb_upper = bb_mid + params.bb_std * bb_std
    bb_lower = bb_mid - params.bb_std * bb_std
    
    # ATR for stops
    atr_ctx = compute_atr(ctx_f, params.atr_period)
    stop_dist_ctx = params.atr_stop_mult * atr_ctx
    
    # Align context indicators to execution
    ctx_indicators = pd.DataFrame({
        "ctx_completion": ctx_f["ctx_completion"],
        "donchian_high": donchian_high,
        "donchian_low": donchian_low,
        "donchian_mid": donchian_mid,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
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
    
    donchian_high = aligned["donchian_high"]
    donchian_low = aligned["donchian_low"]
    donchian_mid = aligned["donchian_mid"]
    bb_upper = aligned["bb_upper"]
    bb_lower = aligned["bb_lower"]
    bb_mid = aligned["bb_mid"]
    atr = aligned["atr"]
    stop_distance = aligned["stop_distance"]
    close = aligned["close"]
    high = aligned["high"]
    low = aligned["low"]
    regime = aligned["h1_regime"]
    
    # --- Breakout Detection ---
    # Breakout: close > donchian_high (long breakout) or close < donchian_low (short breakout)
    breakout_long = close > donchian_high
    breakout_short = close < donchian_low
    
    # Track breakout state
    breakout_long_active = breakout_long.copy()
    breakout_short_active = breakout_short.copy()
    
    # Failure detection: within failure_bars, price closes back inside channel
    # For each bar, check if there was a breakout in the last failure_bars that failed
    failure_long = pd.Series(False, index=aligned.index)
    failure_short = pd.Series(False, index=aligned.index)
    
    for i in range(len(aligned)):
        if i >= params.failure_bars:
            # Check if there was a long breakout in the last failure_bars that now failed
            recent_long_breakout = breakout_long.iloc[i - params.failure_bars:i].any()
            if recent_long_breakout and close.iloc[i] < donchian_high.iloc[i]:
                failure_long.iloc[i] = True
            
            recent_short_breakout = breakout_short.iloc[i - params.failure_bars:i].any()
            if recent_short_breakout and close.iloc[i] > donchian_low.iloc[i]:
                failure_short.iloc[i] = True
    
    # Entry: Reversal candle in opposite direction after failure
    # Long entry on failure_short (short breakout failed, go long)
    # Short entry on failure_long (long breakout failed, go short)
    entry_long = failure_short & (close > bb_mid)  # Reversal up from lower band
    entry_short = failure_long & (close < bb_mid)  # Reversal down from upper band
    
    # Exit: Opposite band hit
    exit_long = close > bb_upper
    exit_short = close < bb_lower
    
    max_hold = params.max_hold_bars
    
    out = pd.DataFrame({
        "timestamp": aligned["timestamp"],
        "open": aligned["open"],
        "high": aligned["high"],
        "low": aligned["low"],
        "close": aligned["close"],
        "spread": aligned["spread"] if "spread" in aligned.columns else np.nan,
        "volume": aligned["volume"] if "volume" in aligned.columns else np.nan,
        "donchian_high": donchian_high,
        "donchian_low": donchian_low,
        "donchian_mid": donchian_mid,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
        "atr": atr,
        "stop_distance": stop_distance,
        "h1_ema": aligned["h1_ema"],
        "h1_ema_prev": aligned["h1_ema_prev"],
        "h1_regime": regime,
        "h1_completion": aligned["h1_completion"],
        "entry_long": entry_long,
        "entry_short": entry_short,
        "exit_long": exit_long,
        "exit_short": exit_short,
        "max_holding_bars": max_hold,
    })
    
    return FailedBreakoutSignalFrame(
        frame=out,
        params=params,
        execution_bars_used=len(out),
        context_bars_used=len(ctx_f),
    )


class XauM5FailedBreakoutStrategy(BaseStrategy):
    """BaseStrategy adapter for M5 Failed Breakout Reversal."""
    
    def __init__(self, params: Optional[FailedBreakoutParams] = None, symbol: str = "XAUUSDm"):
        super().__init__(name="XAU-M5-FAILED-BREAKOUT-001", symbol=symbol)
        self.params = params or FailedBreakoutParams()
    
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
            raise ValueError("XauM5FailedBreakoutStrategy.generate_setups requires context_tf")
        if h1_f is None or (isinstance(h1_f, pd.DataFrame) and h1_f.empty):
            raise ValueError("XauM5FailedBreakoutStrategy.generate_setups requires h1")
        
        signals = compute_failed_breakout_signals(market_data, ctx, h1_f, self.params).frame
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
                    f"Failed breakout reversal: {side} after breakout failed "
                    f"with H1 regime {int(row['h1_regime']):+d} "
                    f"[{self.params.execution_timeframe} execution]"
                ),
                metadata={
                    "stop_distance": float(row["stop_distance"]),
                    "atr": float(row["atr"]),
                    "donchian_high": float(row["donchian_high"]),
                    "donchian_low": float(row["donchian_low"]),
                    "bb_upper": float(row["bb_upper"]),
                    "bb_lower": float(row["bb_lower"]),
                    "regime": int(row["h1_regime"]),
                    "execution_timeframe": self.params.execution_timeframe,
                    "max_holding_bars": int(row["max_holding_bars"]),
                },
            ))
        return setups


__all__ = [
    "FailedBreakoutParams",
    "FailedBreakoutSignalFrame",
    "XauM5FailedBreakoutStrategy",
    "compute_failed_breakout_signals",
]