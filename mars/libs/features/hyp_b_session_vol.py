"""
Hypothesis B feature engineering: Session-aware volatility/range prediction.

Features are computed from COMPLETED sessions only — no lookahead into the target session.
Targets (next-session ATR%) are produced separately by the label module.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pytz

from mars.libs.data.loaders import to_price_index
from mars.libs.features.indicators import add_baseline_indicators


FEATURE_COLUMNS = [
    "day_of_week",
    "session_id",              # 0=Asia, 1=London, 2=Overlap, 3=NY
    "current_session_range",   # range of most recently COMPLETED session
    "atr_at_session_close",    # ATR at close of completed session
    "realized_vol_trailing_5", # realized vol over last 5 completed sessions
    "realized_vol_trailing_20",# realized vol over last 20 completed sessions
    "tick_volume_proxy",       # sum of tick_volume in completed session
]


SESSION_DEFS_UTC = {
    "asia": (0, 8),
    "london": (8, 13),      # London morning only (non-overlap)
    "overlap": (13, 17),    # London/NY overlap
    "ny": (17, 22),         # NY afternoon
}


class HypBSessionVolFeatures:
    """
    Daily tabular features for session volatility prediction (Hypothesis B).

    Input: normalized OHLCV with UTC timestamps.
    Output: one row per session boundary with features from COMPLETED sessions only.
    """

    def __init__(self) -> None:
        self.feature_names = list(FEATURE_COLUMNS)
        self._is_fitted = False

    def transform(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Build daily feature rows. Returns a DataFrame indexed by date with FEATURE_COLUMNS."""
        features_df, _ = self.transform_with_sessions(market_data)
        return features_df

    def transform_with_sessions(
        self, market_data: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Same as transform, but also returns a companion frame of session-level data
        used by label generation and GARCH baseline.

        Returns
        -------
        features : pd.DataFrame
            One row per session boundary, indexed by date.
        session_meta : pd.DataFrame
            Session-level OHLCV for each completed session (for labels + GARCH).
            Columns: session_id, session_open, session_high, session_low, session_close,
                     session_volume, session_range, atr_at_close, realized_vol,
                     next_session_open
        """
        price = to_price_index(market_data)
        price = add_baseline_indicators(price)

        feature_rows: List[Dict[str, Any]] = []
        meta_rows: List[Dict[str, Any]] = []

        # Build session-level data first
        session_data = self._build_session_data(price)
        if len(session_data) < 21:  # need at least 20 for trailing_20
            return pd.DataFrame(columns=FEATURE_COLUMNS), pd.DataFrame()

        # Generate features at each session boundary (after session closes)
        for i in range(1, len(session_data)):
            prev_session = session_data.iloc[i - 1]  # completed session
            curr_session = session_data.iloc[i]       # current/target session

            # Features from the COMPLETED session only
            features = self._extract_features(session_data, i)
            if features is not None:
                features["date"] = prev_session.name.date()
                feature_rows.append(features)
                meta_rows.append({
                    "date": prev_session.name.date(),
                    "session_id": int(prev_session["session_id"]),
                    "session_open": prev_session["session_open"],
                    "session_high": prev_session["session_high"],
                    "session_low": prev_session["session_low"],
                    "session_close": prev_session["session_close"],
                    "session_volume": prev_session["session_volume"],
                    "session_range": prev_session["session_range"],
                    "atr_at_close": prev_session["atr_at_close"],
                    "realized_vol": prev_session["realized_vol"],
                    "next_session_open": curr_session["session_open"],
                    "next_session_high": curr_session["session_high"],
                    "next_session_low": curr_session["session_low"],
                    "next_session_close": curr_session["session_close"],
                })

        if not feature_rows:
            return pd.DataFrame(columns=FEATURE_COLUMNS), pd.DataFrame()

        features_df = pd.DataFrame(feature_rows)
        features_df["date"] = pd.to_datetime(features_df["date"])
        # Use a unique session key: date + session_id
        features_df["session_key"] = features_df["date"].astype(str) + "_" + features_df["session_id"].astype(str)
        features_df = features_df.set_index("session_key").sort_index()
        features_df = features_df[FEATURE_COLUMNS]
        features_df = features_df.dropna()

        meta_df = pd.DataFrame(meta_rows)
        meta_df["date"] = pd.to_datetime(meta_df["date"])
        meta_df["session_key"] = meta_df["date"].astype(str) + "_" + meta_df["session_id"].astype(str)
        meta_df = meta_df.set_index("session_key").sort_index()
        meta_df = meta_df.loc[features_df.index]

        self._is_fitted = True
        return features_df, meta_df

    def _build_session_data(self, price: pd.DataFrame) -> pd.DataFrame:
        """Slice price data into session bars using fixed UTC boundaries."""
        session_rows = []

        for day in price.index.normalize().unique():
            day_date = day.date()

            # Asia: 00:00-08:00 UTC
            try:
                asia = price.loc[str(day_date)].between_time("00:00", "07:59")
            except KeyError:
                asia = price.iloc[0:0]

            if not asia.empty:
                session_rows.append(self._make_session_row(
                    asia, day_date, session_id=0, name="Asia"
                ))

            # London: 08:00-13:00 UTC (non-overlap part)
            try:
                london = price.loc[str(day_date)].between_time("08:00", "12:59")
            except KeyError:
                london = price.iloc[0:0]

            if not london.empty:
                session_rows.append(self._make_session_row(
                    london, day_date, session_id=1, name="London"
                ))

            # Overlap: 13:00-17:00 UTC (London/NY overlap)
            try:
                overlap = price.loc[str(day_date)].between_time("13:00", "16:59")
            except KeyError:
                overlap = price.iloc[0:0]

            if not overlap.empty:
                session_rows.append(self._make_session_row(
                    overlap, day_date, session_id=2, name="Overlap"
                ))

            # NY: 17:00-22:00 UTC
            try:
                ny = price.loc[str(day_date)].between_time("17:00", "21:59")
            except KeyError:
                ny = price.iloc[0:0]

            if not ny.empty:
                session_rows.append(self._make_session_row(
                    ny, day_date, session_id=3, name="NY"
                ))

        if not session_rows:
            return pd.DataFrame()

        df = pd.DataFrame(session_rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        
        # Detect gaps between consecutive sessions
        # A gap is when the time between session end and next session start > 1 hour
        # (normal session transitions are at most ~1 hour, e.g., London close 17:00 -> NY open 17:00)
        # The key gap is between the LAST session of one day and FIRST session of next day
        df["gap_hours"] = (df.index.to_series() - df.index.to_series().shift(1)).dt.total_seconds() / 3600
        
        # Normal overnight gap: NY close (21:55) -> Asia open (07:55 next day) = ~10 hours
        # But wait: Asia 00:00-07:55, London 08:00-12:55, Overlap 13:00-16:55, NY 17:00-21:55
        # NY close 21:55 -> next day Asia open 00:00 = 2 hours 5 min
        # So normal overnight gap is ~2 hours between sessions
        # Multi-day feed outages are > 24 hours
        df["is_gap_after_feed_outage"] = df["gap_hours"] > 24  # multi-day outage
        df["is_large_gap"] = df["gap_hours"] > 8  # gap larger than normal overnight (2h) + buffer
        
        # Clean up temp columns
        df = df.drop(columns=["gap_hours"])
        
        return df

    def _make_session_row(
        self, session_bars: pd.DataFrame, day_date: datetime.date,
        session_id: int, name: str
    ) -> Dict[str, Any]:
        """Compute session-level statistics."""
        session_open = float(session_bars["open"].iloc[0])
        session_close = float(session_bars["close"].iloc[-1])
        session_high = float(session_bars["high"].max())
        session_low = float(session_bars["low"].min())
        session_volume = float(session_bars["volume"].sum())
        session_range = session_high - session_low
        session_return = (session_close - session_open) / session_open if session_open else np.nan
        atr_at_close = float(session_bars["ATRr_14"].iloc[-1]) if "ATRr_14" in session_bars.columns and pd.notna(session_bars["ATRr_14"].iloc[-1]) else np.nan
        realized_vol = abs(session_return)  # simple proxy for realized vol

        return {
            "timestamp": session_bars.index[-1],  # session end timestamp
            "date": day_date,
            "session_id": session_id,
            "session_name": name,
            "session_open": session_open,
            "session_high": session_high,
            "session_low": session_low,
            "session_close": session_close,
            "session_volume": session_volume,
            "session_range": session_range,
            "session_return": session_return,
            "atr_at_close": atr_at_close,
            "realized_vol": realized_vol,
        }

    def _extract_features(self, session_data: pd.DataFrame, idx: int) -> Optional[Dict[str, Any]]:
        """
        Extract features at session boundary `idx` (target session).
        Features come from session `idx-1` (completed) and trailing windows.
        """
        if idx < 1:
            return None

        completed = session_data.iloc[idx - 1]  # most recently completed session
        completed_idx = idx - 1

        # Check if the completed session itself follows a large gap (feed outage)
        if completed.get("is_large_gap", False):
            # Skip this session - it follows a gap, so its return is not a valid 5-min return
            return None

        # Trailing realized vol over COMPLETED sessions only
        # Exclude sessions that follow large gaps from the trailing window
        trailing_candidates_5 = session_data.iloc[max(0, completed_idx - 4):completed_idx + 1]
        trailing_candidates_20 = session_data.iloc[max(0, completed_idx - 19):completed_idx + 1]

        # Filter out sessions that follow large gaps
        trailing_5 = trailing_candidates_5[~trailing_candidates_5.get("is_large_gap", False)]
        trailing_20 = trailing_candidates_20[~trailing_candidates_20.get("is_large_gap", False)]

        realized_vol_5 = np.sqrt(trailing_5["session_return"].pow(2).mean()) if len(trailing_5) > 0 else np.nan
        realized_vol_20 = np.sqrt(trailing_20["session_return"].pow(2).mean()) if len(trailing_20) > 0 else np.nan

        # Current session range = range of the COMPLETED session
        current_session_range = completed["session_range"]

        # ATR at completed session close
        atr_at_session_close = completed["atr_at_close"]

        # Tick volume proxy = volume in completed session
        tick_volume_proxy = completed["session_volume"]

        # Day of week from completed session date
        day_of_week = completed.name.dayofweek if hasattr(completed.name, "dayofweek") else \
                      pd.Timestamp(completed.name).dayofweek

        return {
            "day_of_week": day_of_week,
            "session_id": int(completed["session_id"]),
            "current_session_range": current_session_range,
            "atr_at_session_close": atr_at_session_close,
            "realized_vol_trailing_5": realized_vol_5,
            "realized_vol_trailing_20": realized_vol_20,
            "tick_volume_proxy": tick_volume_proxy,
        }