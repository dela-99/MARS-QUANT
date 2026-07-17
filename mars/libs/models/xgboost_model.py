"""XGBoost wrappers implementing the M.A.R.S. BaseModel interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from mars.libs.models.base import ArrayLike, BaseModel


class XGBoostClassifierModel(BaseModel):
    """Binary / multi-class XGBoost classifier with joblib serialization."""

    def __init__(
        self,
        name: str = "xgb_classifier",
        **xgb_params: Any,
    ) -> None:
        super().__init__(name=name)
        defaults = dict(
            objective="binary:logistic",
            eval_metric="logloss",
            n_estimators=500,
            learning_rate=0.05,
            max_depth=5,
            random_state=42,
            n_jobs=-1,
        )
        defaults.update(xgb_params)
        # use_label_encoder removed in newer xgboost; ignore if unsupported
        self.params = defaults
        self.model: Optional[xgb.XGBClassifier] = None
        self.feature_names_: Optional[list[str]] = None

    def fit(self, X: ArrayLike, y: ArrayLike, **kwargs: Any) -> "XGBoostClassifierModel":
        if isinstance(X, pd.DataFrame):
            self.feature_names_ = list(X.columns)
        self.model = xgb.XGBClassifier(**self.params)
        self.model.fit(X, y, **kwargs)
        self.is_fitted = True
        return self

    def predict(self, X: ArrayLike) -> np.ndarray:
        self._require_fitted()
        return self.model.predict(X)  # type: ignore[union-attr]

    def predict_proba(self, X: ArrayLike) -> np.ndarray:
        self._require_fitted()
        return self.model.predict_proba(X)  # type: ignore[union-attr]

    def save(self, path: str | Path) -> None:
        self._require_fitted()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "params": self.params,
                "feature_names": self.feature_names_,
                "name": self.name,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> "XGBoostClassifierModel":
        payload = joblib.load(path)
        # Support raw legacy joblib dumps of XGBClassifier
        if isinstance(payload, xgb.XGBClassifier):
            obj = cls(name="xgb_classifier_legacy")
            obj.model = payload
            obj.is_fitted = True
            return obj
        obj = cls(name=payload.get("name", "xgb_classifier"), **payload.get("params", {}))
        obj.model = payload["model"]
        obj.feature_names_ = payload.get("feature_names")
        obj.is_fitted = True
        return obj

    def _require_fitted(self) -> None:
        if not self.is_fitted or self.model is None:
            raise RuntimeError("Model is not fitted. Call fit() or load() first.")


class XGBoostRegressorModel(BaseModel):
    """XGBoost regressor with joblib serialization."""

    def __init__(self, name: str = "xgb_regressor", **xgb_params: Any) -> None:
        super().__init__(name=name)
        defaults = dict(
            objective="reg:squarederror",
            eval_metric="rmse",
            n_estimators=500,
            learning_rate=0.05,
            max_depth=5,
            random_state=42,
            n_jobs=-1,
        )
        defaults.update(xgb_params)
        self.params = defaults
        self.model: Optional[xgb.XGBRegressor] = None
        self.feature_names_: Optional[list[str]] = None

    def fit(self, X: ArrayLike, y: ArrayLike, **kwargs: Any) -> "XGBoostRegressorModel":
        if isinstance(X, pd.DataFrame):
            self.feature_names_ = list(X.columns)
        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(X, y, **kwargs)
        self.is_fitted = True
        return self

    def predict(self, X: ArrayLike) -> np.ndarray:
        if not self.is_fitted or self.model is None:
            raise RuntimeError("Model is not fitted.")
        return self.model.predict(X)

    def save(self, path: str | Path) -> None:
        if not self.is_fitted or self.model is None:
            raise RuntimeError("Model is not fitted.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "params": self.params,
                "feature_names": self.feature_names_,
                "name": self.name,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> "XGBoostRegressorModel":
        payload = joblib.load(path)
        if isinstance(payload, xgb.XGBRegressor):
            obj = cls(name="xgb_regressor_legacy")
            obj.model = payload
            obj.is_fitted = True
            return obj
        obj = cls(name=payload.get("name", "xgb_regressor"), **payload.get("params", {}))
        obj.model = payload["model"]
        obj.feature_names_ = payload.get("feature_names")
        obj.is_fitted = True
        return obj
