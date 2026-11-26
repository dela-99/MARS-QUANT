"""
XAU-M5-DISPLACEMENT-MR-001 — Displacement Mean Reversion Strategy (M5 signals, M1/M5 execution).

Economically motivated: Reversion to VWAP after displacement beyond ATR bands.

Rules:
- VWAP(20) as mean reference
- Displacement: Close > VWAP + displacement_atr_mult * ATR (short) or < VWAP - ... (long)
- Reversion: Candle closes back toward VWAP
- Entry: Reversion confirmation
- Stop: Beyond displacement extreme
- Exit: Cross VWAP or opposite band or time
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
class DisplacementMRParams:
    """Immutable parameters for M5 Displacement Mean Reversion strategy."""
    # Signal parameters
    vwap_period: int = 20                   # VWAP period
    displacement_atr_mult: float = 2.5      # Displacement threshold in ATR units
    reversion_confirm_bars: int = 1         # Bars to confirm reversion
    atr_period: int = 14                    # ATR period
    atr_stop_mult: float = 1.5              # Stop distance = mult * ATR
    
    # Execution parameters
    max_hold_bars: int = 6                  # Max holding in execution bars
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
class DisplacementMRSignalFrame:
    frame: pd.DataFrame
    params: DisplacementMRParams
    execution_bars_used: int
    context_bars_used: int


def _compute_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Compute VWAP (Volume Weighted Average Price)."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    volume = df["volume"] if "volume" in df.columns else df["tick_volume"] if "tick_volume" in df.columns else pd.Series(1.0, index=df.index)
    
    vwap_num = (typical_price * volume).rolling(period, min_periods=period).sum()
    vwap_den = volume.rolling(period, min_periods=period).sum()
    
    return vwap_num / vwap_den


def compute_displacement_mr_signals(
    execution_tf: pd.DataFrame,
    context_tf: pd.DataFrame,
    h1: pd.DataFrame,
    params: DisplacementMRParams,
) -> DisplacementMRSignalFrame:
    """
    Compute displacement mean reversion signals on M5.
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
    
    # --- M5 VWAP & ATR ---
    ctx_f = ctx_f.copy()
    ctx_f["ctx_completion"] = ctx_f["timestamp"] + pd.Timedelta(minutes=M5_MINUTES)
    
    vwap = _compute_vwap(ctx_f, params.vwap_period)
    atr_ctx = compute_atr(ctx_f, params.atr_period)
    
    # Displacement bands
    upper_band = vwap + params.displacement_atr_mult * atr_ctx
    lower_band = vwap - params.displacement_atr_mult * atr_ctx
    
    stop_dist_ctx = params.atr_stop_mult * atr_ctx
    
    # Align context indicators to execution
    ctx_indicators = pd.DataFrame({
        "ctx_completion": ctx_f["ctx_completion"],
        "vwap": vwap,
        "upper_band": upper_band,
        "lower_band": lower_band,
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
    
    vwap = aligned["vwap"]
    upper_band = aligned["upper_band"]
    lower_band = aligned["lower_band"]
    atr = aligned["atr"]
    stop_distance = aligned["stop_distance"]
    close = aligned["close"]
    regime = aligned["h1_regime"]
    
    # --- Displacement Detection ---
    # Displacement: close beyond bands
    displaced_long = close < lower_band   # Oversold - long opportunity
    displaced_short = close > upper_band  # Overbought - short opportunity
    
    # Reversion confirmation: candle closes back toward VWAP
    # Long reversion: was displaced long, now close > lower_band (moved up toward VWAP)
    # Short reversion: was displaced short, now close < upper_band (moved down toward VWAP)
    displaced_long_shifted = displaced_long.shift(params.reversion_confirm_bars).fillna(False)
    displaced_short_shifted = displaced_short.shift(params.reversion_confirm_bars).fillna(False)
    
    entry_long = displaced_long_shifted & (close > lower_band)
    entry_short = displaced_short_shifted & (close < upper_band)
    
    # Exit: Cross VWAP or opposite band
    exit_long = close > vwap
    exit_short = close < vwap
    
    max_hold = params.max_hold_bars
    
    out = pd.DataFrame({
        "timestamp": aligned["timestamp"],
        "open": aligned["open"],
        "high": aligned["high"],
        "low": aligned["low"],
        "close": aligned["close"],
        "spread": aligned["spread"] if "spread" in aligned.columns else np.nan,
        "volume": aligned["volume"] if "volume" in aligned.columns else np.nan,
        "vwap": vwap,
        "upper_band": upper_band,
        "lower_band": lower_band,
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
    
    return DisplacementMRSignalFrame(
        frame=out,
        params=params,
        execution_bars_used=len(out),
        context_bars_used=len(ctx_f),
    )


class XauM5DisplacementMRStrategy(BaseStrategy):
    """BaseStrategy adapter for M5 Displacement Mean Reversion."""
    
    def __init__(self, params: Optional[DisplacementMRParams] = None, symbol: str = "XAUUSDm"):
        super().__init__(name="XAU-M5-DISPLACEMENT-MR-001", symbol=symbol)
        self.params = params or DisplacementMRParams()
    
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
            raise ValueError("XauM5DisplacementMRStrategy.generate_setups requires context_tf")
        if h1_f is None or (isinstance(h1_f, pd.DataFrame) and h1_f.empty):
            raise ValueError("XauM5DisplacementMRStrategy.generate_setups requires h1")
        
        signals = compute_displacement_mr_signals(market_data, ctx, h1_f, self.params).frame
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
                    f"Displacement MR: {side} reversion from "
                    f"{'lower' if side == 'long' else 'upper'} band {row['lower_band' if side == 'long' else 'upper_band']:.2f} "
                    f"toward VWAP {row['vwap']:.2f} "
                    f"with H1 regime {int(row['h1_regime']):+d} "
                    f"[{self.params.execution_timeframe} execution]"
                ),
                metadata={
                    "stop_distance": float(row["stop_distance"]),
                    "atr": float(row["atr"]),
                    "vwap": float(row["vwap"]),
                    "upper_band": float(row["upper_band"]),
                    "lower_band": float(row["lower_band"]),
                    "regime": int(row["h1_regime"]),
                    "execution_timeframe": self.params.execution_timeframe,
                    "max_holding_bars": int(row["max_holding_bars"]),
                },
            ))
        return setups


__all__ = [
    "DisplacementMRParams",
    "DisplacementMRSignalFrame",
    "XauM5DisplacementMRStrategy",
    "compute_displacement_mr_signals",
]