"""Deterministic momentum features (vectorized, no look-ahead)."""
 
from __future__ import annotations
 
from typing import Any, Optional
 
import numpy as np
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.features.base import FeatureResult, MomentumFeature
 
 
class LogReturnFeature(MomentumFeature):
    """1-period log return of close. Lookback = 1 (uses t-1 close)."""
 
    name = "log_return"
    version = "1.0.0"
    lookback = 1
 
    def output_columns(self) -> list[str]:
        return ["log_return"]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        self.validate_inputs(df)
        close = df["close"].astype(float)
        out = pd.DataFrame(
            {"log_return": np.log(close / close.shift(1))},
            index=df.index,
        )
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)
 
 
class RollingMomentumFeature(MomentumFeature):
    """
    Rolling sum of log returns over ``window`` bars.
 
    Uses only past data: at bar t, sum of log returns from t-window+1 … t
    which depends on close[t-window] … close[t] (standard, no future).
    """
 
    name = "rolling_momentum"
    version = "1.0.0"
 
    def __init__(self, window: int = 10) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window
        self.lookback = window
 
    def output_columns(self) -> list[str]:
        return [f"momentum_{self.window}"]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        self.validate_inputs(df)
        close = df["close"].astype(float)
        log_ret = np.log(close / close.shift(1))
        col = f"momentum_{self.window}"
        out = pd.DataFrame(
            {col: log_ret.rolling(self.window, min_periods=self.window).sum()},
            index=df.index,
        )
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)