"""Volatility features (realized vol, ATR)."""
 
from __future__ import annotations
 
from typing import Any, Optional
 
import numpy as np
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.features.base import FeatureResult, VolatilityFeature
 
 
class RealizedVolatilityFeature(VolatilityFeature):
    """Rolling standard deviation of log returns."""
 
    name = "realized_volatility"
    version = "1.0.0"
 
    def __init__(self, window: int = 20) -> None:
        self.window = window
        self.lookback = window
 
    def output_columns(self) -> list[str]:
        return [f"rvol_{self.window}"]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        self.validate_inputs(df)
        close = df["close"].astype(float)
        log_ret = np.log(close / close.shift(1))
        col = f"rvol_{self.window}"
        out = pd.DataFrame(
            {
                col: log_ret.rolling(self.window, min_periods=self.window).std()
            },
            index=df.index,
        )
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)
 
 
class ATRFeature(VolatilityFeature):
    """Average True Range (Wilder-style EMA approximation via ewm)."""
 
    name = "atr"
    version = "1.0.0"
 
    def __init__(self, window: int = 14) -> None:
        self.window = window
        self.lookback = window
 
    def output_columns(self) -> list[str]:
        return [f"atr_{self.window}"]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        self.validate_inputs(df)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        # Wilder's smoothing ≈ ewm with alpha = 1/window
        atr = tr.ewm(alpha=1.0 / self.window, min_periods=self.window, adjust=False).mean()
        col = f"atr_{self.window}"
        out = pd.DataFrame({col: atr}, index=df.index)
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)