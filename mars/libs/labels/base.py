"""Label generation abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class LabelGenerator(ABC):
    """
    Base interface for target generation.

    Implementations should document when labels become known relative to
    feature availability to avoid lookahead bias.
    """

    def __init__(self, name: str = "base") -> None:
        self.name = name

    @abstractmethod
    def generate(self, data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Generate label columns aligned to an index.

        Returns a DataFrame with one or more label columns (e.g. direction, return).
        """

    def binary_direction(
        self, open_: pd.Series, close: pd.Series, name: str = "direction"
    ) -> pd.Series:
        """1 if close > open else 0."""
        return (close > open_).astype(int).rename(name)

    def session_return(
        self, open_: pd.Series, close: pd.Series, name: str = "return"
    ) -> pd.Series:
        """Simple session return (close - open) / open."""
        return ((close - open_) / open_).rename(name)
