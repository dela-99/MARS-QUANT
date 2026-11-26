"""
XAU-M5-MOMENTUM-001 — Momentum Continuation Strategy (M5 signals, M1/M5 execution).

Economically motivated: Trend continuation after Donchian breakout confirmed by H1 EMA regime.

Rules:
- H1 regime: EMA(ema_period) slope over 5 bars (long if rising, short if falling)
- M5 entry: Close breaks above prior Donchian(lookback_bars) high (long)
            OR below prior Donchian low (short)
- Stop: ATR(atr_period) * atr_stop_mult from entry
- Exit: Close crosses Donchian midpoint against position OR stop hit
- Time exit: max_hold_bars execution bars
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
class MomentumParams:
    """Immutable parameters for M5 Momentum Continuation strategy."""
    # Signal parameters
    lookback_bars: int = 20           # Donchian lookback for breakout
    momentum_threshold: float = 0.0   # Minimum momentum (close - donchian_high) for entry
    ema_period: int = 20              # EMA period for momentum filter
    atr_period: int = 14              # ATR period for stop
    atr_stop_mult: float = 2.0        # Stop distance = mult * ATR
    
    # Execution parameters
    max_hold_bars: int = 6            # Max holding in execution bars
    risk_fraction: float = 0.01       # Risk per trade
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
class MomentumSignalFrame:
    frame: pd.DataFrame
    params: MomentumParams
    execution_bars_used: int
    context_bars_used: int


def _compute_h1_regime(h1: pd.DataFrame, ema_period: int = 20, slope_bars: int = 5) -> pd.DataFrame:
    """Compute H1 regime from EMA slope."""
    h1_f = h1.copy()
    h1_ema = h1_f["close"].ewm(span=ema_period, adjust=False).mean()
    h1_ema_prev = h1_ema.shift(slope_bars)
    h1_regime = np.where(h1_ema > h1_ema_prev, 1, np.where(h1_ema < h1_ema_prev, -1, 0))
    
    h1_f["h1_ema"] = h1_ema
    h1_f["h1_ema_prev"] = h1_ema_prev
    h1_f["h1_regime"] = h1_regime
    h1_f["h1_completion"] = h1_f["timestamp"] + pd.Timedelta(minutes=H1_MINUTES)
    return h1_f


def compute_momentum_signals(
    execution_tf: pd.DataFrame,
    context_tf: pd.DataFrame,
    h1: pd.DataFrame,
    params: MomentumParams,
) -> MomentumSignalFrame:
    """
    Compute momentum continuation signals on M5.
    
    Rules:
    - H1 regime: EMA(ema_period) slope over 5 bars (long if rising, short if falling)
    - M5 entry: Close breaks above prior Donchian(lookback_bars) high (long)
                OR below prior Donchian low (short)
    - Stop: ATR(atr_period) * atr_stop_mult from entry
    - Exit: Close crosses Donchian midpoint against position OR stop hit
    - Time exit: max_hold_bars execution bars
    """
    tf_minutes = 1 if params.execution_timeframe == "M1" else 5
    
    exec_f = _require_timestamp(execution_tf, "execution_tf")
    ctx_f = _require_timestamp(context_tf, "context_tf")
    h1_f = _require_timestamp(h1, "h1")
    
    lookback = params.lookback_bars
    
    # --- H1 Regime ---
    h1_regime_df = _compute_h1_regime(h1_f, params.ema_period, 5)
    
    # Align H1 to execution
    exec_f = exec_f.copy()
    exec_f["_pos"] = np.arange(len(exec_f))
    exec_f["exec_completion"] = exec_f["timestamp"] + pd.Timedelta(minutes=tf_minutes)
    
    aligned = pd.merge_asof(
        exec_f.sort_values("exec_completion"),
        h1_regime_df[["h1_completion", "h1_ema", "h1_ema_prev", "h1_regime"]].sort_values("h1_completion"),
        left_on="exec_completion",
        right_on="h1_completion",
        direction="backward",
    )
    aligned = aligned.sort_values("_pos").reset_index(drop=True)
    regime = aligned["h1_regime"].fillna(0).astype("int64")
    regime[aligned["h1_completion"].isna()] = 0
    
    # --- Donchian Channel on Context (M5) ---
    ctx_f = ctx_f.copy()
    ctx_f["ctx_completion"] = ctx_f["timestamp"] + pd.Timedelta(minutes=M5_MINUTES)
    
    prior_high = ctx_f["high"].shift(1)
    prior_low = ctx_f["low"].shift(1)
    donchian_high_ctx = prior_high.rolling(lookback, min_periods=lookback).max()
    donchian_low_ctx = prior_low.rolling(lookback, min_periods=lookback).min()
    donchian_mid_ctx = (donchian_high_ctx + donchian_low_ctx) / 2.0
    
    # ATR on context
    atr_ctx = compute_atr(ctx_f, params.atr_period)
    stop_dist_ctx = params.atr_stop_mult * atr_ctx
    
    # Align context indicators to execution
    ctx_indicators = pd.DataFrame({
        "ctx_completion": ctx_f["ctx_completion"],
        "donchian_high": donchian_high_ctx,
        "donchian_low": donchian_low_ctx,
        "donchian_mid": donchian_mid_ctx,
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
    atr = aligned["atr"]
    stop_distance = aligned["stop_distance"]
    close = aligned["close"]
    
    # --- Entry/Exit Signals ---
    # Momentum: close breaks donchian level with regime confirmation
    momentum_long = (close - donchian_high) > params.momentum_threshold
    momentum_short = (donchian_low - close) > params.momentum_threshold
    
    entry_long = momentum_long & (regime == 1)
    entry_short = momentum_short & (regime == -1)
    
    # Exit: cross donchian midpoint against position
    exit_long = close < donchian_mid
    exit_short = close > donchian_mid
    
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
    
    return MomentumSignalFrame(
        frame=out,
        params=params,
        execution_bars_used=len(out),
        context_bars_used=len(ctx_f),
    )


class XauM5MomentumStrategy(BaseStrategy):
    """BaseStrategy adapter for M5 Momentum Continuation."""
    
    def __init__(self, params: Optional[MomentumParams] = None, symbol: str = "XAUUSDm"):
        super().__init__(name="XAU-M5-MOMENTUM-001", symbol=symbol)
        self.params = params or MomentumParams()
    
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
            raise ValueError("XauM5MomentumStrategy.generate_setups requires context_tf")
        if h1_f is None or (isinstance(h1_f, pd.DataFrame) and h1_f.empty):
            raise ValueError("XauM5MomentumStrategy.generate_setups requires h1")
        
        signals = compute_momentum_signals(market_data, ctx, h1_f, self.params).frame
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
                    f"Momentum breakout: close {row['close']:.2f} vs "
                    f"Donchian({self.params.lookback_bars}) "
                    f"{'high' if side == 'long' else 'low'} {row['donchian_high' if side == 'long' else 'donchian_low']:.2f} "
                    f"with H1 EMA({self.params.ema_period}) regime {int(row['h1_regime']):+d} "
                    f"[{self.params.execution_timeframe} execution]"
                ),
                metadata={
                    "stop_distance": float(row["stop_distance"]),
                    "atr": float(row["atr"]),
                    "donchian_high": float(row["donchian_high"]),
                    "donchian_low": float(row["donchian_low"]),
                    "donchian_mid": float(row["donchian_mid"]),
                    "regime": int(row["h1_regime"]),
                    "execution_timeframe": self.params.execution_timeframe,
                    "max_holding_bars": int(row["max_holding_bars"]),
                },
            ))
        return setups


__all__ = [
    "MomentumParams",
    "MomentumSignalFrame",
    "XauM5MomentumStrategy",
    "compute_momentum_signals",
]