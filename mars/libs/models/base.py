"""Base model interface for M.A.R.S. estimators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

ArrayLike = Union[pd.DataFrame, pd.Series, np.ndarray]


class BaseModel(ABC):
    """
    Consistent fit / predict / save / load contract for research models.

    Wrappers around XGBoost, scikit-learn, and PyTorch should implement this.
    """

    def __init__(self, name: str = "base") -> None:
        self.name = name
        self.is_fitted: bool = False

    @abstractmethod
    def fit(self, X: ArrayLike, y: ArrayLike, **kwargs: Any) -> "BaseModel":
        ...

    @abstractmethod
    def predict(self, X: ArrayLike) -> np.ndarray:
        ...

    def predict_proba(self, X: ArrayLike) -> np.ndarray:
        """Optional for classifiers. Default raises."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement predict_proba.")

    @abstractmethod
    def save(self, path: str | Path) -> None:
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> "BaseModel":
        ...
