"""
XAU-M5-VOL-EXPANSION-001 — Volatility Expansion Strategy (M5 signals, M1/M5 execution).

Economically motivated: Breakout on volatility expansion (ATR spike) with volume confirmation.

Rules:
- Volatility expansion: ATR(14) > expansion_threshold * median(ATR(14), 20 bars)
- Volume confirmation: tick_volume > median(20 bars) if enabled
- Entry: Breakout in direction of expansion candle
- Stop: ATR * atr_stop_mult
- Exit: Volatility contraction (ATR < median) or time
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
class VolExpansionParams:
    """Immutable parameters for M5 Volatility Expansion strategy."""
    # Signal parameters
    atr_period: int = 14                      # ATR period
    expansion_threshold: float = 2.0          # ATR ratio vs 20-bar median for expansion
    volume_confirm: bool = True               # Require volume confirmation
    atr_stop_mult: float = 2.0                # Stop distance = mult * ATR
    
    # Execution parameters
    max_hold_bars: int = 6                    # Max holding in execution bars
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
class VolExpansionSignalFrame:
    frame: pd.DataFrame
    params: VolExpansionParams
    execution_bars_used: int
    context_bars_used: int


def compute_vol_expansion_signals(
    execution_tf: pd.DataFrame,
    context_tf: pd.DataFrame,
    h1: pd.DataFrame,
    params: VolExpansionParams,
) -> VolExpansionSignalFrame:
    """
    Compute volatility expansion signals on M5.
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
    
    # --- M5 Volatility & Volume ---
    ctx_f = ctx_f.copy()
    ctx_f["ctx_completion"] = ctx_f["timestamp"] + pd.Timedelta(minutes=M5_MINUTES)
    
    atr_ctx = compute_atr(ctx_f, params.atr_period)
    atr_median = atr_ctx.rolling(20, min_periods=20).median()
    volume_median = ctx_f["volume"].rolling(20, min_periods=20).median() if "volume" in ctx_f.columns else pd.Series(np.nan, index=ctx_f.index)
    
    # Expansion: ATR > threshold * median
    expansion = atr_ctx > (params.expansion_threshold * atr_median)
    
    # Volume confirmation
    if params.volume_confirm and "volume" in ctx_f.columns:
        vol_confirm = ctx_f["volume"] > volume_median
    else:
        vol_confirm = pd.Series(True, index=ctx_f.index)
    
    # Direction of expansion candle
    expansion_dir = np.where(ctx_f["close"] > ctx_f["open"], 1, -1)
    
    # Align context indicators to execution
    ctx_indicators = pd.DataFrame({
        "ctx_completion": ctx_f["ctx_completion"],
        "atr": atr_ctx,
        "atr_median": atr_median,
        "expansion": expansion,
        "vol_confirm": vol_confirm,
        "expansion_dir": expansion_dir,
        "stop_distance": params.atr_stop_mult * atr_ctx,
    })
    
    aligned = pd.merge_asof(
        aligned.sort_values("exec_completion"),
        ctx_indicators.sort_values("ctx_completion"),
        left_on="exec_completion",
        right_on="ctx_completion",
        direction="backward",
    )
    aligned = aligned.sort_values("_pos").reset_index(drop=True)
    
    atr = aligned["atr"]
    atr_median = aligned["atr_median"]
    expansion = aligned["expansion"].fillna(False)
    vol_confirm = aligned["vol_confirm"].fillna(True)
    expansion_dir = aligned["expansion_dir"]
    stop_distance = aligned["stop_distance"]
    close = aligned["close"]
    regime = aligned["h1_regime"]
    
    # --- Entry/Exit Signals ---
    # Entry: Expansion + volume confirm + regime alignment
    entry_long = expansion & vol_confirm & (expansion_dir == 1) & (regime == 1)
    entry_short = expansion & vol_confirm & (expansion_dir == -1) & (regime == -1)
    
    # Exit: Volatility contraction (ATR falls below median)
    contraction = atr < atr_median
    exit_long = contraction & (regime == 1)
    exit_short = contraction & (regime == -1)
    
    max_hold = params.max_hold_bars
    
    out = pd.DataFrame({
        "timestamp": aligned["timestamp"],
        "open": aligned["open"],
        "high": aligned["high"],
        "low": aligned["low"],
        "close": aligned["close"],
        "spread": aligned["spread"] if "spread" in aligned.columns else np.nan,
        "volume": aligned["volume"] if "volume" in aligned.columns else np.nan,
        "atr": atr,
        "atr_median": atr_median,
        "expansion": expansion,
        "expansion_dir": expansion_dir,
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
    
    return VolExpansionSignalFrame(
        frame=out,
        params=params,
        execution_bars_used=len(out),
        context_bars_used=len(ctx_f),
    )


class XauM5VolExpansionStrategy(BaseStrategy):
    """BaseStrategy adapter for M5 Volatility Expansion."""
    
    def __init__(self, params: Optional[VolExpansionParams] = None, symbol: str = "XAUUSDm"):
        super().__init__(name="XAU-M5-VOL-EXPANSION-001", symbol=symbol)
        self.params = params or VolExpansionParams()
    
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
            raise ValueError("XauM5VolExpansionStrategy.generate_setups requires context_tf")
        if h1_f is None or (isinstance(h1_f, pd.DataFrame) and h1_f.empty):
            raise ValueError("XauM5VolExpansionStrategy.generate_setups requires h1")
        
        signals = compute_vol_expansion_signals(market_data, ctx, h1_f, self.params).frame
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
                    f"Vol expansion: ATR {row['atr']:.2f} > {self.params.expansion_threshold}x median {row['atr_median']:.2f} "
                    f"dir {int(row['expansion_dir']):+d} with H1 regime {int(row['h1_regime']):+d} "
                    f"[{self.params.execution_timeframe} execution]"
                ),
                metadata={
                    "stop_distance": float(row["stop_distance"]),
                    "atr": float(row["atr"]),
                    "atr_median": float(row["atr_median"]),
                    "expansion_dir": int(row["expansion_dir"]),
                    "regime": int(row["h1_regime"]),
                    "execution_timeframe": self.params.execution_timeframe,
                    "max_holding_bars": int(row["max_holding_bars"]),
                },
            ))
        return setups


__all__ = [
    "VolExpansionParams",
    "VolExpansionSignalFrame",
    "XauM5VolExpansionStrategy",
    "compute_vol_expansion_signals",
]