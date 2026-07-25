"""
OHLCV normalization: column renames, timezone localization, sorting, dedup.
 
Output contract:
    - DatetimeIndex named 'timestamp', tz-aware UTC
    - columns: open, high, low, close, volume [, spread]
    - ascending time order
    - first occurrence kept on duplicate timestamps
"""
 
from __future__ import annotations
 
from typing import Mapping, Optional
 
import pandas as pd
 
from mars.data.interfaces import DataNormalizer
 
# Common vendor / MT5 column aliases → canonical names
COLUMN_ALIASES: Mapping[str, str] = {
    "time": "timestamp",
    "Time": "timestamp",
    "datetime": "timestamp",
    "Date": "timestamp",
    "date": "timestamp",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "tick_volume": "volume",
    "real_volume": "volume",
    "Tick volume": "volume",
    "Spread": "spread",
}
 
CANONICAL_COLUMNS = ("open", "high", "low", "close", "volume")
 
 
class OHLCVNormalizer(DataNormalizer):
    """Normalize heterogeneous OHLCV frames into the M.A.R.S. canonical schema."""
 
    def __init__(
        self,
        source_timezone: str = "UTC",
        drop_extra: bool = False,
    ) -> None:
        """
        Args:
            source_timezone: timezone of naive timestamps before localization.
            drop_extra: if True, drop non-canonical columns after rename.
        """
        self.source_timezone = source_timezone
        self.drop_extra = drop_extra
 
    def normalize(self, df: pd.DataFrame, timezone: str = "UTC") -> pd.DataFrame:
        if df is None or df.empty:
            raise ValueError("Cannot normalize empty DataFrame")
 
        frame = df.copy()
 
        # Flatten MultiIndex columns if present
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [
                "_".join(str(x) for x in col if x is not None).strip("_")
                for col in frame.columns
            ]
 
        # Rename known aliases
        rename_map = {c: COLUMN_ALIASES[c] for c in frame.columns if c in COLUMN_ALIASES}
        frame = frame.rename(columns=rename_map)
 
        # Promote timestamp column to index if needed
        if "timestamp" in frame.columns:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
            frame = frame.set_index("timestamp")
        elif not isinstance(frame.index, pd.DatetimeIndex):
            # try common index name
            frame.index = pd.to_datetime(frame.index)
 
        frame.index = pd.DatetimeIndex(frame.index)
        frame.index.name = "timestamp"
 
        # Timezone handling
        if frame.index.tz is None:
            frame.index = frame.index.tz_localize(self.source_timezone)
        frame.index = frame.index.tz_convert(timezone)
 
        # Ensure volume exists
        if "volume" not in frame.columns:
            frame["volume"] = 0.0
 
        # Coerce numeric
        for col in ("open", "high", "low", "close", "volume"):
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if "spread" in frame.columns:
            frame["spread"] = pd.to_numeric(frame["spread"], errors="coerce")
 
        # Sort & deduplicate
        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep="first")]
 
        # Column order
        ordered = [c for c in CANONICAL_COLUMNS if c in frame.columns]
        if "spread" in frame.columns:
            ordered.append("spread")
        extras = [c for c in frame.columns if c not in ordered]
        if self.drop_extra:
            frame = frame[ordered]
        else:
            frame = frame[ordered + extras]
 
        return frame