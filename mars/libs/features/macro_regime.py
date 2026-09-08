"""
Macro regime features for Hyp-C: DXY momentum, real yield momentum, VIX, etc.

Features are computed from FRED macro time series (daily frequency with publication lag applied).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "dxy_momentum_5",           # Short-term DXY momentum (predictive, not directly used in target)
    "real_yield_10y_level",     # Real yield level
    "real_yield_10y_momentum_5", # Real yield short momentum
    "real_yield_10y_momentum_20", # Real yield long momentum
    "vix_level",                # VIX level
    "vix_momentum_5",           # VIX short momentum
    "vix_momentum_20",          # VIX long momentum
]


class MacroRegimeFeatures:
    """
    Daily macro regime features for Hyp-C.

    Input: normalized macro DataFrames (one per series) with UTC timestamps
           already adjusted for FRED publication lag (timestamp = when data becomes available).
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
                    Index must be datetime (UTC) representing *available* dates (after publication lag).

        Returns
        -------
        features : pd.DataFrame
            One row per trading day with FEATURE_COLUMNS, indexed by date.
        """
        # Align all series to common daily index using merge_asof (backward)
        # to respect publication lag - we only use values available at or before each date
        dxy = macro_data.get("DXY")
        real_yield = macro_data.get("REAL_YIELD_10Y")
        vix = macro_data.get("VIX")

        if dxy is None:
            raise ValueError("DXY series is required")

        # All timestamps should already be lag-adjusted (available dates)
        # Use DXY index as the master timeline (most complete series)
        master_index = dxy.index.sort_values()

        # Reindex all series to master index using forward fill (last known value)
        # This simulates "most recent known value as of this date"
        dxy_aligned = dxy["close"].reindex(master_index).ffill()
        
        real_yield_aligned = None
        if real_yield is not None:
            real_yield_aligned = real_yield["close"].reindex(master_index).ffill()
        
        vix_aligned = None
        if vix is not None:
            vix_aligned = vix["close"].reindex(master_index).ffill()

        # Compute features
        feature_rows = []

        for i, date in enumerate(master_index):
            if i < 20:  # need 20 days for momentum_20
                continue

            # Skip if any required value is NaN
            if pd.isna(dxy_aligned.iloc[i]) or \
               (real_yield is not None and pd.isna(real_yield_aligned.iloc[i])) or \
               (vix is not None and pd.isna(vix_aligned.iloc[i])):
                continue

            row = {"date": date.date()}

            # DXY momentum
            dxy_5 = dxy_aligned.iloc[i-5:i+1]
            row["dxy_momentum_5"] = (dxy_5.iloc[-1] / dxy_5.iloc[0] - 1) if len(dxy_5) == 6 else np.nan

            # Real yield level and momentum
            if real_yield is not None and real_yield_aligned is not None:
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
            if vix is not None:
                vix_aligned = vix["close"].reindex(master_index).ffill()
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

        # Build target from DXY 20-session momentum on the lag-adjusted DXY
        # We need to get the DXY close values aligned with the features index
        # features.index is a date index (date only), dxy has timestamp index
        dxy_close = macro_data["DXY"]["close"]
        
        # Create a mapping from date to close value
        # dxy_close has timestamp index, we need to map to date
        dxy_close_by_date = dxy_close.groupby(dxy_close.index.date).last()
        
        # Reindex to features index (which is already date index)
        dxy_close_aligned = dxy_close_by_date.reindex(features.index)
        dxy_momentum_20 = dxy_close_aligned.pct_change(20)

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