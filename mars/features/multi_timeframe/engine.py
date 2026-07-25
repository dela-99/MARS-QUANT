"""
Multi-timeframe feature engine.
 
Computes features independently for each timeframe (H1, M30, M15, M5, M3).
Does NOT train separate models per timeframe — only feature computation.
Alignment / synchronization is handled by AlignmentEngine.
"""
 
from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import Iterable, Optional
 
import pandas as pd
 
from mars.core.timeframes import SUPPORTED_TIMEFRAMES, Timeframe
from mars.features.base import BaseFeature, FeatureResult
 
 
@dataclass
class MTFFeatureBundle:
    """Features keyed by timeframe, plus optional raw bars per TF."""
 
    features: dict[Timeframe, pd.DataFrame] = field(default_factory=dict)
    bars: dict[Timeframe, pd.DataFrame] = field(default_factory=dict)
    feature_names: dict[Timeframe, list[str]] = field(default_factory=dict)
 
    def timeframes(self) -> list[Timeframe]:
        return list(self.features.keys())
 
 
class MultiTimeframeFeatureEngine:
    """
    Run a list of BaseFeature instances on each provided timeframe frame.
 
    Usage:
        engine = MultiTimeframeFeatureEngine(features=[LogReturnFeature(), ATRFeature()])
        bundle = engine.compute({Timeframe.H1: df_h1, Timeframe.M15: df_m15})
    """
 
    def __init__(
        self,
        features: Optional[Iterable[BaseFeature]] = None,
        timeframes: Optional[tuple[Timeframe, ...]] = None,
        prefix_with_timeframe: bool = True,
    ) -> None:
        self.features = list(features or [])
        self.timeframes = timeframes or SUPPORTED_TIMEFRAMES
        self.prefix_with_timeframe = prefix_with_timeframe
 
    def add_feature(self, feature: BaseFeature) -> None:
        self.features.append(feature)
 
    def compute(
        self,
        bars_by_tf: dict[Timeframe, pd.DataFrame],
    ) -> MTFFeatureBundle:
        """
        Compute all registered features independently for each timeframe
        present in ``bars_by_tf``.
        """
        bundle = MTFFeatureBundle()
 
        for tf, bars in bars_by_tf.items():
            if tf not in self.timeframes:
                # still allow ad-hoc TFs if provided
                pass
            parts: list[pd.DataFrame] = []
            names: list[str] = []
            for feat in self.features:
                result: FeatureResult = feat.compute(bars, timeframe=tf)
                data = result.data.copy()
                if self.prefix_with_timeframe:
                    data.columns = [f"{tf.value.lower()}__{c}" for c in data.columns]
                parts.append(data)
                names.extend(list(data.columns))
 
            if parts:
                frame = pd.concat(parts, axis=1)
            else:
                frame = pd.DataFrame(index=bars.index)
 
            bundle.features[tf] = frame
            bundle.bars[tf] = bars
            bundle.feature_names[tf] = names
 
        return bundle