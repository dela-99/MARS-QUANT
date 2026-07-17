"""Feature pipeline abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

import pandas as pd


class FeaturePipeline(ABC):
    """
    Base interface for market → feature matrix transforms.

    Implementations may optionally ``fit`` on training data (e.g. scalers,
    vocabulary). Baseline Hyp-A features are stateless beyond indicator windows.
    """

    def __init__(self, name: str = "base") -> None:
        self.name = name
        self._feature_names: List[str] = []
        self._is_fitted: bool = False

    @property
    def feature_names(self) -> List[str]:
        return list(self._feature_names)

    def fit(self, market_data: pd.DataFrame, y: Optional[pd.Series] = None) -> "FeaturePipeline":
        """Fit any trainable state. Default is a no-op that records readiness."""
        self._is_fitted = True
        return self

    @abstractmethod
    def transform(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Transform OHLCV (or session-level) data into a feature matrix."""

    def fit_transform(
        self, market_data: pd.DataFrame, y: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        return self.fit(market_data, y).transform(market_data)

    def set_feature_names(self, names: Sequence[str]) -> None:
        self._feature_names = list(names)
