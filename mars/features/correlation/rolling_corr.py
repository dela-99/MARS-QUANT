"""Rolling autocorrelation of returns (single-asset)."""
 
from __future__ import annotations
 
from typing import Any, Optional
 
import numpy as np
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.features.base import CorrelationFeature, FeatureResult
 
 
class RollingAutocorrFeature(CorrelationFeature):
    """Rolling lag-1 autocorrelation of log returns."""
 
    name = "rolling_autocorr"
    version = "1.0.0"
 
    def __init__(self, window: int = 50) -> None:
        self.window = window
        self.lookback = window + 1
 
    def output_columns(self) -> list[str]:
        return [f"autocorr_lag1_{self.window}"]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        self.validate_inputs(df)
        close = df["close"].astype(float)
        log_ret = np.log(close / close.shift(1))
        col = f"autocorr_lag1_{self.window}"
        ac = log_ret.rolling(self.window, min_periods=self.window).corr(log_ret.shift(1))
        out = pd.DataFrame({col: ac}, index=df.index)
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)