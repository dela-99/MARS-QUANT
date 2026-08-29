from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

ArrayLike = pd.DataFrame | pd.Series | np.ndarray

class BaseLearningModel(ABC):
    name = "base_learning_model"
    version = "1.0.0"
    task_type = "generic"
    estimator_type = "base"

    def __init__(self, random_state: int | None = 42, **parameters: Any) -> None:
        self.random_state = random_state
        self.parameters = dict(parameters)
        self.feature_columns_: list[str] = []
        self.is_fitted = False

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: ArrayLike, **kwargs: Any) -> "BaseLearningModel": ...

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray: ...

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError(f"{self.__class__.__name__} does not expose probabilities")

    @abstractmethod
    def save(self, path: str | Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> "BaseLearningModel": ...

    def _record_features(self, X: pd.DataFrame) -> None:
        self.feature_columns_ = list(X.columns)

    def _validate_features(self, X: pd.DataFrame) -> None:
        if self.feature_columns_ and list(X.columns) != self.feature_columns_:
            raise ValueError("feature schema mismatch")
