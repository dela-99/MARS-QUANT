"""
Tick data normalization for MT5 bid/ask/last history.

Output contract:
    - DatetimeIndex named 'timestamp', tz-aware UTC
    - columns: bid, ask, last, volume [, spread, flags]
    - ascending time order
    - first occurrence kept on duplicate timestamps
    - bid <= ask validated
"""

from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd

from mars.data.interfaces import DataNormalizer

# MT5 tick column aliases → canonical names
TICK_COLUMN_ALIASES: Mapping[str, str] = {
    "time": "timestamp",
    "Time": "timestamp",
    "datetime": "timestamp",
    "Date": "timestamp",
    "Bid": "bid",
    "Ask": "ask",
    "Last": "last",
    "Volume": "volume",
    "VolumeReal": "volume_real",
    "Spread": "spread",
    "Flags": "flags",
}

CANONICAL_TICK_COLUMNS = ("bid", "ask", "last", "volume")


class TickNormalizer(DataNormalizer):
    """Normalize heterogeneous tick frames into the M.A.R.S. canonical tick schema."""

    def __init__(
        self,
        source_timezone: str = "UTC",
        drop_extra: bool = False,
        compute_spread: bool = True,
    ) -> None:
        """
        Args:
            source_timezone: timezone of naive timestamps before localization.
            drop_extra: if True, drop non-canonical columns after rename.
            compute_spread: if True, compute spread = ask - bid when both present.
        """
        self.source_timezone = source_timezone
        self.drop_extra = drop_extra
        self.compute_spread = compute_spread

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
        rename_map = {c: TICK_COLUMN_ALIASES[c] for c in frame.columns if c in TICK_COLUMN_ALIASES}
        frame = frame.rename(columns=rename_map)

        # Handle duplicate columns after rename
        if frame.columns.duplicated().any():
            frame = frame.loc[:, ~frame.columns.duplicated(keep="first")]

        # Promote timestamp column to index if needed
        if "timestamp" in frame.columns:
            if isinstance(frame.index, pd.DatetimeIndex) and frame.index.name == "timestamp":
                pass
            else:
                frame = frame.set_index("timestamp")
        elif not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index)

        frame.index = pd.DatetimeIndex(frame.index)
        frame.index.name = "timestamp"

        # Timezone handling
        if frame.index.tz is None:
            frame.index = frame.index.tz_localize(self.source_timezone)
        frame.index = frame.index.tz_convert(timezone)

        # Coerce numeric columns
        for col in ("bid", "ask", "last", "volume", "volume_real", "spread"):
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")

        # Compute spread if requested and not present
        if self.compute_spread and "spread" not in frame.columns:
            if "bid" in frame.columns and "ask" in frame.columns:
                frame["spread"] = frame["ask"] - frame["bid"]

        # Sort & deduplicate
        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep="first")]

        # Column order
        ordered = [c for c in CANONICAL_TICK_COLUMNS if c in frame.columns]
        if "spread" in frame.columns:
            ordered.append("spread")
        if "volume_real" in frame.columns:
            ordered.append("volume_real")
        if "flags" in frame.columns:
            ordered.append("flags")
        extras = [c for c in frame.columns if c not in ordered]
        if self.drop_extra:
            frame = frame[ordered]
        else:
            frame = frame[ordered + extras]

        return frame


def validate_tick_integrity(df: pd.DataFrame) -> list[str]:
    """
    Validate tick data integrity.
    Returns list of issue descriptions (empty if all valid).
    """
    issues = []

    if "bid" not in df.columns or "ask" not in df.columns:
        issues.append("Missing bid or ask column")
        return issues

    # Check bid <= ask
    bad_order = df["bid"] > df["ask"]
    if bad_order.any():
        issues.append(f"Bid > Ask on {int(bad_order.sum())} rows")

    # Check positive prices
    for col in ("bid", "ask", "last"):
        if col in df.columns:
            non_pos = df[col] <= 0
            if non_pos.any():
                issues.append(f"Non-positive {col} on {int(non_pos.sum())} rows")

    # Check monotonic timestamps
    if not df.index.is_monotonic_increasing:
        issues.append("Timestamps not monotonically increasing")

    # Check for duplicate timestamps
    if df.index.duplicated().any():
        issues.append(f"Duplicate timestamps: {int(df.index.duplicated().sum())}")

    # Check spread sanity (if computed)
    if "spread" in df.columns:
        neg_spread = df["spread"] < 0
        if neg_spread.any():
            issues.append(f"Negative spread on {int(neg_spread.sum())} rows")
        # Extremely wide spread (more than 10% of mid price)
        if "bid" in df.columns and "ask" in df.columns:
            mid = (df["bid"] + df["ask"]) / 2
            wide = df["spread"] > mid * 0.1
            if wide.any():
                issues.append(f"Extremely wide spread (>10% mid) on {int(wide.sum())} rows")

    return issues


def resample_ticks_to_m1(
    ticks: pd.DataFrame,
    label: str = "right",
    closed: str = "right",
) -> pd.DataFrame:
    """
    Resample tick data to M1 OHLCV bars for cross-validation.

    Args:
        ticks: Normalized tick DataFrame with bid, ask, last, volume
        label: 'right' means bar timestamp = end of interval (M5 convention)
        closed: 'right' means interval is (t-1min, t]

    Returns:
        M1 OHLCV DataFrame with columns: open, high, low, close, volume, spread
    """
    if ticks.empty:
        return pd.DataFrame()

    # Use bid for OHLC (consistent with MT5 OHLCV being bid prices)
    price_col = "bid" if "bid" in ticks.columns else ("last" if "last" in ticks.columns else None)
    if price_col is None:
        raise ValueError("No suitable price column (bid/last) for resampling")

    # Resample to 1-minute bars
    ohlc = ticks[price_col].resample("1min", label=label, closed=closed).ohlc()
    ohlc.columns = ["open", "high", "low", "close"]

    # Volume = sum of tick volumes
    vol_col = "volume" if "volume" in ticks.columns else ("volume_real" if "volume_real" in ticks.columns else None)
    if vol_col:
        ohlc["volume"] = ticks[vol_col].resample("1min", label=label, closed=closed).sum()
    else:
        ohlc["volume"] = 0

    # Spread = mean spread (if available) or mean(ask-bid)
    if "spread" in ticks.columns:
        ohlc["spread"] = ticks["spread"].resample("1min", label=label, closed=closed).mean()
    elif "bid" in ticks.columns and "ask" in ticks.columns:
        spread = ticks["ask"] - ticks["bid"]
        ohlc["spread"] = spread.resample("1min", label=label, closed=closed).mean()
    else:
        ohlc["spread"] = 0

    # Drop incomplete bars (NaN)
    ohlc = ohlc.dropna(subset=["open", "high", "low", "close"])

    return ohlc


__all__ = [
    "TickNormalizer",
    "validate_tick_integrity",
    "resample_ticks_to_m1",
    "TICK_COLUMN_ALIASES",
    "CANONICAL_TICK_COLUMNS",
]