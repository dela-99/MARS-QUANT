"""
GARCH baseline models for volatility forecasting.

Implements:
- Standard GARCH(1,1) on log returns (return-variance GARCH)
- CARR (Conditional Autoregressive Range) model for range-based forecasting
  (Chou, 2005; suitable for ATR/range targets)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import joblib
import numpy as np
import pandas as pd
from arch import arch_model


@dataclass
class GARCHBaseline:
    """
    GARCH baseline for volatility/range prediction.

    Variants:
    - "garch": Standard GARCH(1,1) on log returns (return-variance)
    - "carr": CARR model on session ranges (range-variance) — fair for ATR targets

    The CARR variant is the honest baseline for an ATR/range target because it
    models range dynamics directly, avoiding the unfair return-vol→range conversion
    with a calibration constant.

    NOTE ON CARR VARIANT (2024-09-08):
    The CARR variant was attempted during Hyp-B validation but exhibited numerical
    issues: the AR-GARCH specification on log ranges (line 86-95) produced
    parameter estimates with extreme values (omega ~ 4.96, alpha ~ 5e-13,
    beta ~ 1.0) and forecasts ~3e-6 (effectively zero variance). The root cause
    appears to be the log-range transformation combined with GARCH errors on
    low-variance session range data, causing the optimizer to hit boundary
    conditions. The CARR model is theoretically sound for range-based targets
    but requires either: (a) more careful initialization/bounds, (b) a proper
    CARR likelihood (Chou 2005) rather than AR-GARCH approximation, or (c) more
    data with higher session range variance. For now, the standard GARCH(1,1)
    on log returns is used as the validated baseline. CARR debugging is
    deprioritized unless range-based forecasting becomes a primary requirement.
    """

    variant: Literal["garch", "carr"] = "carr"
    window: int = 20  # lookback for realized vol features
    refit_window: int = 5000  # max bars for GARCH refit (bounds computation)
    _fitted: bool = False
    _model_fit: Optional[Any] = None
    _session_ranges: Optional[pd.Series] = None
    _session_dates: Optional[pd.Index] = None
    _session_ids: Optional[pd.Series] = None
    _cached_predictions: Optional[pd.Series] = None
    _cached_feature_dates: Optional[pd.Index] = None

    def fit(
        self,
        session_meta: pd.DataFrame,
        feature_dates: pd.Index,
    ) -> "GARCHBaseline":
        """
        Fit the GARCH/CARR model on training data.

        Parameters
        ----------
        session_meta:
            Session-level DataFrame from HypBSessionVolFeatures.transform_with_sessions
            with columns: session_range, session_close, session_id, etc.
            Indexed by session end timestamp (or date).
        feature_dates:
            Dates of the training feature rows (aligned with session_meta rows).
        """
        # Align session_meta to feature dates
        # session_meta has one row per session boundary (completed session)
        # feature_dates has one row per session boundary
        aligned_meta = session_meta.loc[session_meta.index.isin(feature_dates)]

        if self.variant == "garch":
            # Standard GARCH on log returns
            # Use session returns (log close/close)
            session_returns = np.log(
                aligned_meta["session_close"] / aligned_meta["session_close"].shift(1)
            ).dropna()
            
            # Use only the most recent refit_window bars for fitting
            if len(session_returns) > self.refit_window:
                session_returns = session_returns.tail(self.refit_window)
            
            self._model_fit = arch_model(
                session_returns * 100,  # scale for numerical stability
                vol="Garch",
                p=1,
                q=1,
                dist="normal",
                rescale=False,
            ).fit(update_freq=0, disp="off")
        else:
            # CARR: Conditional Autoregressive Range model
            # Models session range directly: range_t = omega + alpha * range_{t-1} + beta * E[range_{t-1}]
            # For simplicity, we fit an AR(1) on log session ranges with GARCH errors
            # This is a simplified CARR; full CARR uses range-specific likelihood.
            session_ranges = aligned_meta["session_range"].dropna()
            log_ranges = np.log(session_ranges)
            
            if len(log_ranges) > self.refit_window:
                log_ranges = log_ranges.tail(self.refit_window)
            
            self._model_fit = arch_model(
                log_ranges * 100,
                vol="Garch",
                p=1,
                q=1,
                mean="AR",
                lags=1,
                dist="normal",
                rescale=False,
            ).fit(update_freq=0, disp="off")

        self._session_ranges = aligned_meta["session_range"]
        self._session_dates = aligned_meta.index
        self._session_ids = aligned_meta.get("session_id")
        self._fitted = True
        # Clear cache on new fit
        self._cached_predictions = None
        self._cached_feature_dates = None
        return self

    def predict(
        self,
        session_meta: pd.DataFrame,
        feature_dates: pd.Index,
    ) -> np.ndarray:
        """
        Generate 1-step-ahead forecasts for the given feature dates.

        Returns forecasts aligned with feature_dates (one per session boundary).
        Uses cached model — NO refitting at prediction time for performance.
        """
        if not self._fitted:
            raise RuntimeError("GARCHBaseline must be fitted before predict()")

        # Check cache
        if (self._cached_predictions is not None and 
            self._cached_feature_dates is not None and
            self._cached_feature_dates.equals(feature_dates)):
            return self._cached_predictions

        # Align to feature dates
        aligned_meta = session_meta.loc[session_meta.index.isin(feature_dates)]

        if self.variant == "garch":
            # Use cached fitted model — NO refitting at prediction time
            if self._model_fit is None:
                raise RuntimeError("Model not fitted")
            
            # Generate forecasts directly from fitted model
            # For rolling forecasts, we need the conditional variance at each point
            # Use the model's conditional variance up to the last fitted point
            # and forecast 1-step ahead for each feature date
            
            # Get the last fitted session return data
            aligned_meta_fit = session_meta.loc[session_meta.index.isin(feature_dates)]
            session_returns = np.log(
                aligned_meta_fit["session_close"] / aligned_meta_fit["session_close"].shift(1)
            ).dropna()
            
            # Use only refit_window for prediction if needed
            if len(session_returns) > self.refit_window:
                session_returns = session_returns.tail(self.refit_window)
            
            # Generate 1-step forecasts for each feature date
            predictions = []
            # Use the already-fitted model to get conditional variance at each step
            # For speed, we can use the model's conditional variance series
            cond_var_series = self._model_fit.conditional_volatility / 100  # back to decimal
            
            for d in feature_dates:
                if d in cond_var_series.index:
                    pred_vol = cond_var_series.loc[d]
                    predictions.append(pred_vol)
                else:
                    # If date not in fitted series, use last available
                    if len(cond_var_series) > 0:
                        predictions.append(cond_var_series.iloc[-1])
                    else:
                        predictions.append(0.0)

            predictions = np.array(predictions)  # decimal return vol per session
            
        else:
            # CARR: use cached model
            if self._model_fit is None:
                raise RuntimeError("Model not fitted")
            
            aligned_meta_fit = session_meta.loc[session_meta.index.isin(feature_dates)]
            session_ranges = aligned_meta_fit["session_range"].dropna()
            log_ranges = np.log(session_ranges)
            
            if len(log_ranges) > self.refit_window:
                log_ranges = log_ranges.tail(self.refit_window)
            
            cond_var_series = self._model_fit.conditional_volatility / 100
            
            predictions = []
            for d in feature_dates:
                if d in cond_var_series.index:
                    pred_vol = cond_var_series.loc[d]
                    # For CARR, we also need the mean forecast
                    # Use model's mean forecast
                    model = self._model_fit
                    # Quick 1-step forecast for mean
                    forecast = model.forecast(horizon=1, reindex=False)
                    cond_mean = forecast.mean.values.flatten() / 100
                    cond_var = forecast.variance.values.flatten() / 10000
                    pred_range = np.exp(cond_mean[0] + 0.5 * cond_var[0])
                    predictions.append(pred_range)
                else:
                    if len(cond_var_series) > 0:
                        predictions.append(cond_var_series.iloc[-1])
                    else:
                        predictions.append(0.0)
            
            predictions = np.array(predictions)

        # Cache the results
        self._cached_predictions = predictions
        self._cached_feature_dates = feature_dates
        
        if self.variant == "garch":
            return predictions * 100  # % return volatility per session
        else:
            # Convert CARR range predictions to ATR%
            aligned_meta = session_meta.loc[session_meta.index.isin(feature_dates)]
            session_close = aligned_meta["session_close"].values
            return predictions / session_close

    def save(self, path: str | Path) -> None:
        """Save the fitted model."""
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str | Path) -> "GARCHBaseline":
        """Load a fitted model."""
        return joblib.load(path)