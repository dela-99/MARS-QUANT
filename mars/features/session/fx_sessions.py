"""
FX session labeling features (UTC-based research definitions).
 
Session windows (UTC) — research defaults, not trading rules:
    Asia:   22:00 previous day → 07:59
    London: 08:00 → 16:59
    NY:     13:00 → 21:59  (includes overlap with London)
"""
 
from __future__ import annotations
 
from typing import Any, Optional
 
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.features.base import FeatureResult, SessionFeature
 
 
class FXSessionFeature(SessionFeature):
    """Binary session flags and overlap indicator."""
 
    name = "fx_session"
    version = "1.0.0"
    lookback = 0
 
    def output_columns(self) -> list[str]:
        return [
            "is_asia",
            "is_london",
            "is_ny",
            "is_london_ny_overlap",
        ]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("FXSessionFeature requires DatetimeIndex")
 
        idx = df.index
        if idx.tz is not None:
            hours = idx.tz_convert("UTC").hour
        else:
            hours = idx.hour
 
        is_asia = (hours >= 22) | (hours < 8)
        is_london = (hours >= 8) & (hours < 17)
        is_ny = (hours >= 13) & (hours < 22)
        is_overlap = (hours >= 13) & (hours < 17)
 
        out = pd.DataFrame(
            {
                "is_asia": is_asia.astype(float),
                "is_london": is_london.astype(float),
                "is_ny": is_ny.astype(float),
                "is_london_ny_overlap": is_overlap.astype(float),
            },
            index=df.index,
        )
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)