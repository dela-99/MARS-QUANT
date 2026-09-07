"""
Macro regime features for Hyp-C: DXY momentum, real yield momentum, VIX, etc.

Features are computed from FRED macro time series (daily frequency).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "dxy_momentum_5",
    "dxy_momentum_20",
    "real_yield_10y_level",
    "real_yield_10y_momentum_5",
    "real_yield_10y_momentum_20",
    "vix_level",
    "vix_momentum_5",
    "vix_momentum_20",
]


class MacroRegimeFeatures:
    """
    Daily macro regime features for Hyp-C.

    Input: normalized macro DataFrames (one per series) with UTC timestamps.
    Output: one row per trading day with macro regime features.
    """

    def __init__(self) -> None:
        self.feature_names = list(FEATURE_COLUMNS)
        self._is_fitted = False

    def transform(
        self,
        macro_data: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Build daily feature rows from macro series.

        Parameters
        ----------
        macro_data: dict mapping series name -> DataFrame with DatetimeIndex and 'close' column
                    Expected keys: 'DXY', 'REAL_YIELD_10Y', 'VIX'

        Returns
        -------
        features : pd.DataFrame
            One row per trading day with FEATURE_COLUMNS, indexed by date.
        """
        # Align all series to common daily index
        # Use business day frequency for alignment
        dxy = macro_data.get("DXY")
        real_yield = macro_data.get("REAL_YIELD_10Y")
        vix = macro_data.get("VIX")

        if dxy is None:
            raise ValueError("DXY series is required")

        # Get common date index (intersection of all available series)
        common_index = dxy.index
        if real_yield is not None:
            common_index = common_index.intersection(real_yield.index)
        if vix is not None:
            common_index = common_index.intersection(vix.index)

        common_index = common_index.sort_values()

        if len(common_index) < 21:  # need at least 20 for momentum_20
            raise RuntimeError(f"Insufficient overlapping data: {len(common_index)} days")

        # Reindex all series to common index
        dxy_aligned = dxy.reindex(common_index)["close"]
        real_yield_aligned = real_yield.reindex(common_index)["close"] if real_yield is not None else None
        vix_aligned = vix.reindex(common_index)["close"] if vix is not None else None

        # Compute features
        feature_rows = []

        for i, date in enumerate(common_index):
            if i < 20:  # need 20 days for momentum_20
                continue

            row = {"date": date.date()}

            # DXY momentum
            dxy_5 = dxy_aligned.iloc[i-5:i+1]
            dxy_20 = dxy_aligned.iloc[i-20:i+1]
            row["dxy_momentum_5"] = (dxy_5.iloc[-1] / dxy_5.iloc[0] - 1) if len(dxy_5) == 6 else np.nan
            row["dxy_momentum_20"] = (dxy_20.iloc[-1] / dxy_20.iloc[0] - 1) if len(dxy_20) == 21 else np.nan

            # Real yield level and momentum
            if real_yield_aligned is not None:
                ry_5 = real_yield_aligned.iloc[i-5:i+1]
                ry_20 = real_yield_aligned.iloc[i-20:i+1]
                row["real_yield_10y_level"] = real_yield_aligned.iloc[i]
                row["real_yield_10y_momentum_5"] = (ry_5.iloc[-1] - ry_5.iloc[0]) if len(ry_5) == 6 else np.nan
                row["real_yield_10y_momentum_20"] = (ry_20.iloc[-1] - ry_20.iloc[0]) if len(ry_20) == 21 else np.nan
            else:
                row["real_yield_10y_level"] = np.nan
                row["real_yield_10y_momentum_5"] = np.nan
                row["real_yield_10y_momentum_20"] = np.nan

            # VIX level and momentum
            if vix_aligned is not None:
                row["vix_level"] = vix_aligned.iloc[i]
                vix_5 = vix_aligned.iloc[i-5:i+1]
                vix_20 = vix_aligned.iloc[i-20:i+1]
                row["vix_momentum_5"] = (vix_5.iloc[-1] / vix_5.iloc[0] - 1) if len(vix_5) == 6 else np.nan
                row["vix_momentum_20"] = (vix_20.iloc[-1] / vix_20.iloc[0] - 1) if len(vix_20) == 21 else np.nan
            else:
                row["vix_level"] = np.nan
                row["vix_momentum_5"] = np.nan
                row["vix_momentum_20"] = np.nan

            feature_rows.append(row)

        if not feature_rows:
            return pd.DataFrame(columns=FEATURE_COLUMNS)

        features_df = pd.DataFrame(feature_rows)
        features_df["date"] = pd.to_datetime(features_df["date"])
        features_df = features_df.set_index("date").sort_index()
        features_df = features_df[FEATURE_COLUMNS]
        features_df = features_df.dropna()

        self._is_fitted = True
        return features_df

    def transform_with_target(
        self,
        macro_data: dict[str, pd.DataFrame],
        dxy_series: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Same as transform, but also returns the target (DXY 20-session momentum regime).

        Returns
        -------
        features : pd.DataFrame
        target : pd.DataFrame with columns ['dxy_momentum_regime'] (0=risk-on, 1=neutral, 2=risk-off)
        """
        features = self.transform(macro_data)

        # Build target from DXY 20-session momentum
        # Risk-on: DXY down > 0.5% over 20 sessions
        # Neutral: |change| <= 0.5%
        # Risk-off: DXY up > 0.5% over 20 sessions
        dxy_close = macro_data["DXY"].reindex(features.index)["close"]
        dxy_momentum_20 = dxy_close.pct_change(20)

        def label_regime(momentum: float) -> int:
            if pd.isna(momentum):
                return np.nan
            if momentum > 0.005:  # DXY up > 0.5%
                return 2  # risk-off
            elif momentum < -0.005:  # DXY down > 0.5%
                return 0  # risk-on
            else:
                return 1  # neutral

        target = dxy_momentum_20.apply(label_regime)
        target.name = "dxy_momentum_regime"
        target_df = pd.DataFrame(target).dropna()

        # Align features to target
        features_aligned = features.loc[target_df.index]
        target_df = target_df.loc[features_aligned.index]

        return features_aligned, target_df