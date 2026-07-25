"""Calendar / clock features (deterministic, no look-ahead)."""
 
from __future__ import annotations
 
from typing import Any, Optional
 
import numpy as np
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.features.base import FeatureResult, TimeFeature
 
 
class CalendarTimeFeature(TimeFeature):
    """
    Cyclical hour-of-day and day-of-week encodings.
 
    Uses sin/cos transforms to avoid ordinal discontinuities.
    """
 
    name = "calendar_time"
    version = "1.0.0"
    lookback = 0
 
    def output_columns(self) -> list[str]:
        return [
            "hour_sin",
            "hour_cos",
            "dow_sin",
            "dow_cos",
            "is_weekend",
        ]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("CalendarTimeFeature requires DatetimeIndex")
 
        idx = df.index
        # Convert to UTC for consistency if tz-aware
        if idx.tz is not None:
            hours = idx.tz_convert("UTC").hour + idx.tz_convert("UTC").minute / 60.0
            dow = idx.tz_convert("UTC").dayofweek.astype(float)
        else:
            hours = idx.hour + idx.minute / 60.0
            dow = idx.dayofweek.astype(float)
 
        out = pd.DataFrame(
            {
                "hour_sin": np.sin(2 * np.pi * hours / 24.0),
                "hour_cos": np.cos(2 * np.pi * hours / 24.0),
                "dow_sin": np.sin(2 * np.pi * dow / 7.0),
                "dow_cos": np.cos(2 * np.pi * dow / 7.0),
                "is_weekend": (dow >= 5).astype(float),
            },
            index=df.index,
        )
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)