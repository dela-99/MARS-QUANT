"""
Feature validation suite.
 
Every feature should support:
    - ADF stationarity
    - Information Coefficient (IC)
    - Correlation with forward returns
    - Variance Inflation Factor (VIF)
    - Missing value analysis
    - Feature importance (optional model-based)
"""
 
from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import Any, Optional
 
import numpy as np
import pandas as pd
 
 
@dataclass
class FeatureValidationReport:
    feature_name: str
    n_obs: int
    missing_pct: float
    adf_stat: Optional[float] = None
    adf_pvalue: Optional[float] = None
    is_stationary: Optional[bool] = None
    ic_spearman: Optional[float] = None
    ic_pearson: Optional[float] = None
    forward_return_corr: Optional[float] = None
    vif: Optional[float] = None
    importance: Optional[float] = None
    extras: dict[str, Any] = field(default_factory=dict)
 
    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "n_obs": self.n_obs,
            "missing_pct": self.missing_pct,
            "adf_stat": self.adf_stat,
            "adf_pvalue": self.adf_pvalue,
            "is_stationary": self.is_stationary,
            "ic_spearman": self.ic_spearman,
            "ic_pearson": self.ic_pearson,
            "forward_return_corr": self.forward_return_corr,
            "vif": self.vif,
            "importance": self.importance,
            **self.extras,
        }
 
 
class FeatureValidator:
    """Run statistical diagnostics on feature columns."""
 
    def __init__(
        self,
        forward_horizon: int = 1,
        adf_pvalue_threshold: float = 0.05,
    ) -> None:
        self.forward_horizon = forward_horizon
        self.adf_pvalue_threshold = adf_pvalue_threshold
 
    def missing_analysis(self, series: pd.Series) -> float:
        if len(series) == 0:
            return 1.0
        return float(series.isna().mean())
 
    def adf_test(self, series: pd.Series) -> tuple[Optional[float], Optional[float], Optional[bool]]:
        clean = series.dropna()
        if len(clean) < 20:
            return None, None, None
        try:
            from statsmodels.tsa.stattools import adfuller
        except ImportError:
            return None, None, None
        try:
            stat, pvalue, *_ = adfuller(clean.values, autolag="AIC")
            return float(stat), float(pvalue), bool(pvalue < self.adf_pvalue_threshold)
        except Exception:
            return None, None, None
 
    def information_coefficient(
        self,
        feature: pd.Series,
        forward_returns: pd.Series,
    ) -> tuple[Optional[float], Optional[float]]:
        aligned = pd.concat([feature, forward_returns], axis=1, join="inner").dropna()
        if len(aligned) < 10:
            return None, None
        x, y = aligned.iloc[:, 0], aligned.iloc[:, 1]
        pearson = float(x.corr(y, method="pearson"))
        spearman = float(x.corr(y, method="spearman"))
        return spearman, pearson
 
    def forward_return_correlation(
        self,
        feature: pd.Series,
        close: pd.Series,
    ) -> Optional[float]:
        fwd = np.log(close.shift(-self.forward_horizon) / close)
        aligned = pd.concat([feature, fwd], axis=1, join="inner").dropna()
        if len(aligned) < 10:
            return None
        return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
 
    def variance_inflation_factor(
        self,
        features: pd.DataFrame,
        target_col: str,
    ) -> Optional[float]:
        """
        VIF for ``target_col`` against other columns.
        VIF = 1 / (1 - R^2) from regression on other features.
        """
        if target_col not in features.columns or features.shape[1] < 2:
            return None
        frame = features.dropna()
        if len(frame) < features.shape[1] + 5:
            return None
        y = frame[target_col].values
        X = frame.drop(columns=[target_col]).values
        # add intercept
        X_ = np.column_stack([np.ones(len(X)), X])
        try:
            beta, *_ = np.linalg.lstsq(X_, y, rcond=None)
            y_hat = X_ @ beta
            ss_res = np.sum((y - y_hat) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            if ss_tot == 0:
                return None
            r2 = 1.0 - ss_res / ss_tot
            if r2 >= 1.0:
                return float("inf")
            return float(1.0 / (1.0 - r2))
        except Exception:
            return None
 
    def feature_importance_mutual_info(
        self,
        feature: pd.Series,
        forward_returns: pd.Series,
    ) -> Optional[float]:
        try:
            from sklearn.feature_selection import mutual_info_regression
        except ImportError:
            return None
        aligned = pd.concat([feature, forward_returns], axis=1, join="inner").dropna()
        if len(aligned) < 20:
            return None
        X = aligned.iloc[:, 0].values.reshape(-1, 1)
        y = aligned.iloc[:, 1].values
        try:
            mi = mutual_info_regression(X, y, random_state=42)
            return float(mi[0])
        except Exception:
            return None
 
    def validate_feature(
        self,
        feature: pd.Series,
        close: Optional[pd.Series] = None,
        feature_matrix: Optional[pd.DataFrame] = None,
        name: Optional[str] = None,
    ) -> FeatureValidationReport:
        fname = name or str(feature.name or "feature")
        report = FeatureValidationReport(
            feature_name=fname,
            n_obs=int(feature.notna().sum()),
            missing_pct=self.missing_analysis(feature),
        )
        adf_stat, adf_p, stationary = self.adf_test(feature)
        report.adf_stat = adf_stat
        report.adf_pvalue = adf_p
        report.is_stationary = stationary
 
        if close is not None:
            fwd = np.log(close.shift(-self.forward_horizon) / close)
            spearman, pearson = self.information_coefficient(feature, fwd)
            report.ic_spearman = spearman
            report.ic_pearson = pearson
            report.forward_return_corr = self.forward_return_correlation(feature, close)
            report.importance = self.feature_importance_mutual_info(feature, fwd)
 
        if feature_matrix is not None and fname in feature_matrix.columns:
            report.vif = self.variance_inflation_factor(feature_matrix, fname)
 
        return report
 
    def validate_matrix(
        self,
        features: pd.DataFrame,
        close: Optional[pd.Series] = None,
    ) -> list[FeatureValidationReport]:
        return [
            self.validate_feature(
                features[col],
                close=close,
                feature_matrix=features,
                name=str(col),
            )
            for col in features.columns
        ]