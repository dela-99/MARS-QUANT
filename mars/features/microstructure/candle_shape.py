"""OHLCV-derived microstructure proxies (wick ratios, body size)."""
 
from __future__ import annotations
 
from typing import Any, Optional
 
import numpy as np
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.features.base import FeatureResult, MicrostructureFeature
 
 
class CandleShapeFeature(MicrostructureFeature):
    """Body/range and wick ratios. Fully contemporaneous (no lag needed)."""
 
    name = "candle_shape"
    version = "1.0.0"
    lookback = 0
 
    def output_columns(self) -> list[str]:
        return [
            "body_ratio",
            "upper_wick_ratio",
            "lower_wick_ratio",
            "close_location",
        ]
 
    def compute(
        self,
        df: pd.DataFrame,
        timeframe: Optional[Timeframe] = None,
        **kwargs: Any,
    ) -> FeatureResult:
        self.validate_inputs(df)
        o = df["open"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        c = df["close"].astype(float)
 
        rng = (h - l).replace(0, np.nan)
        body = (c - o).abs()
        upper = h - pd.concat([o, c], axis=1).max(axis=1)
        lower = pd.concat([o, c], axis=1).min(axis=1) - l
 
        out = pd.DataFrame(
            {
                "body_ratio": body / rng,
                "upper_wick_ratio": upper / rng,
                "lower_wick_ratio": lower / rng,
                "close_location": (c - l) / rng,
            },
            index=df.index,
        )
        return FeatureResult(data=out, metadata=self.metadata, timeframe=timeframe)