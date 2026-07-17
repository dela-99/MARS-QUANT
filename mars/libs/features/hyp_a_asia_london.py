"""
Hypothesis A feature engineering: Asia session → London session prediction.

Preserves the original research logic from ``legacy/src/hyp_a_feature_engineering.py``:
features are computed only from the Asian session (and indicators known at Asia close).
Targets (London direction / return) are produced separately by the label module.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import pytz

from mars.libs.data.loaders import to_price_index
from mars.libs.features.base import FeaturePipeline
from mars.libs.features.indicators import add_baseline_indicators


FEATURE_COLUMNS = [
    "day_of_week",
    "asia_return",
    "asia_range",
    "atr_at_asia_close",
    "rsi_at_asia_close",
    "ema50_dist",
    "ema200_dist",
]


class HypAAsiaLondonFeatures(FeaturePipeline):
    """
    Daily tabular features for Asia → London (Hypothesis A).

    Input: normalized OHLCV with UTC timestamps.
    Output: one row per trading day with Asia-session features only.
    """

    def __init__(self, london_tz_name: str = "Europe/London") -> None:
        super().__init__(name="hyp_a_asia_london")
        self.london_tz = pytz.timezone(london_tz_name)
        self.set_feature_names(FEATURE_COLUMNS)

    def transform(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """
        Build daily feature rows.

        Returns a DataFrame indexed by date with FEATURE_COLUMNS.
        Rows with incomplete sessions or NaN indicators are dropped.
        """
        price = to_price_index(market_data)
        price = add_baseline_indicators(price)

        rows: List[Dict[str, Any]] = []
        for day in price.index.normalize().unique():
            row = self._features_for_day(price, day)
            if row is not None:
                rows.append(row)

        if not rows:
            return pd.DataFrame(columns=FEATURE_COLUMNS)

        out = pd.DataFrame(rows)
        out["date"] = pd.to_datetime(out["date"])
        out = out.set_index("date").sort_index()
        out = out[FEATURE_COLUMNS]
        out = out.dropna()
        self.set_feature_names(list(out.columns))
        self._is_fitted = True
        return out

    def transform_with_sessions(
        self, market_data: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Same as transform, but also returns a companion frame of session anchors
        used by label generation (asia_close_ts, london open/close prices).

        Returns
        -------
        features : pd.DataFrame
        session_meta : pd.DataFrame
            Columns: london_open, london_close (for labels), asia_close_ts
        """
        price = to_price_index(market_data)
        price = add_baseline_indicators(price)

        feature_rows: List[Dict[str, Any]] = []
        meta_rows: List[Dict[str, Any]] = []

        for day in price.index.normalize().unique():
            packed = self._day_bundle(price, day)
            if packed is None:
                continue
            features, meta = packed
            feature_rows.append(features)
            meta_rows.append(meta)

        if not feature_rows:
            empty_f = pd.DataFrame(columns=FEATURE_COLUMNS)
            empty_m = pd.DataFrame(columns=["london_open", "london_close", "asia_close_ts"])
            return empty_f, empty_m

        features_df = pd.DataFrame(feature_rows)
        features_df["date"] = pd.to_datetime(features_df["date"])
        features_df = features_df.set_index("date").sort_index()

        meta_df = pd.DataFrame(meta_rows)
        meta_df["date"] = pd.to_datetime(meta_df["date"])
        meta_df = meta_df.set_index("date").sort_index()

        # Drop rows with NaN features (indicator warm-up)
        valid = features_df[FEATURE_COLUMNS].notna().all(axis=1)
        features_df = features_df.loc[valid, FEATURE_COLUMNS]
        meta_df = meta_df.loc[features_df.index]

        self.set_feature_names(list(features_df.columns))
        self._is_fitted = True
        return features_df, meta_df

    def _features_for_day(
        self, price: pd.DataFrame, day: pd.Timestamp
    ) -> Optional[Dict[str, Any]]:
        packed = self._day_bundle(price, day)
        if packed is None:
            return None
        features, _ = packed
        return features

    def _day_bundle(
        self, price: pd.DataFrame, day: pd.Timestamp
    ) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
        try:
            asia_session, london_session = self._session_slices(price, day)
            if asia_session.empty or london_session.empty:
                return None

            asia_open = float(asia_session["open"].iloc[0])
            asia_close = float(asia_session["close"].iloc[-1])
            asia_high = float(asia_session["high"].max())
            asia_low = float(asia_session["low"].min())
            end_of_asia = asia_session.index[-1]

            atr = price.loc[end_of_asia].get("ATRr_14")
            rsi = price.loc[end_of_asia].get("RSI_14")
            ema50 = price.loc[end_of_asia].get("EMA_50")
            ema200 = price.loc[end_of_asia].get("EMA_200")

            features = {
                "date": day.date(),
                "day_of_week": int(day.dayofweek),
                "asia_return": (asia_close - asia_open) / asia_open if asia_open else float("nan"),
                "asia_range": asia_high - asia_low,
                "atr_at_asia_close": float(atr) if pd.notna(atr) else float("nan"),
                "rsi_at_asia_close": float(rsi) if pd.notna(rsi) else float("nan"),
                "ema50_dist": (
                    (asia_close - float(ema50)) / float(ema50)
                    if pd.notna(ema50) and float(ema50) != 0
                    else float("nan")
                ),
                "ema200_dist": (
                    (asia_close - float(ema200)) / float(ema200)
                    if pd.notna(ema200) and float(ema200) != 0
                    else float("nan")
                ),
            }
            meta = {
                "date": day.date(),
                "london_open": float(london_session["open"].iloc[0]),
                "london_close": float(london_session["close"].iloc[-1]),
                "asia_close_ts": end_of_asia,
            }
            return features, meta
        except Exception:
            return None

    def _session_slices(
        self, price: pd.DataFrame, day: pd.Timestamp
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        # Dynamic London session in local time, converted to UTC
        day_naive = day.to_pydatetime().replace(tzinfo=None) if hasattr(day, "to_pydatetime") else day
        if isinstance(day_naive, pd.Timestamp):
            day_date = day_naive.date()
        else:
            day_date = day_naive.date() if hasattr(day_naive, "date") else day

        london_open_local = self.london_tz.localize(datetime.combine(day_date, time(8, 0)))
        london_close_local = self.london_tz.localize(datetime.combine(day_date, time(17, 0)))
        london_open_utc = london_open_local.astimezone(pytz.utc)
        london_close_utc = london_close_local.astimezone(pytz.utc)

        previous_day = pd.Timestamp(day_date) - timedelta(days=1)
        try:
            asia_part1 = price.loc[str(previous_day.date())].between_time("22:00", "23:59")
        except KeyError:
            asia_part1 = price.iloc[0:0]
        try:
            asia_part2 = price.loc[str(day_date)].between_time("00:00", "07:59")
        except KeyError:
            asia_part2 = price.iloc[0:0]

        asia_session = pd.concat([asia_part1, asia_part2])
        london_session = price[(price.index >= london_open_utc) & (price.index < london_close_utc)]
        return asia_session, london_session
