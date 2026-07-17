"""Market data loaders and normalization helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from mars.libs.data.schemas import REQUIRED_CANDLE_COLUMNS
from mars.libs.data.validation import validate_ohlcv


# Common vendor / broker column aliases → canonical names
_COLUMN_ALIASES: dict[str, str] = {
    "time": "timestamp",
    "datetime": "timestamp",
    "date": "timestamp",
    "tick_volume": "volume",
    "real_volume": "volume",
    "vol": "volume",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "Time": "timestamp",
}


def normalize_ohlcv(
    df: pd.DataFrame,
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    assume_utc: bool = True,
) -> pd.DataFrame:
    """
    Normalize a raw OHLCV frame to the M.A.R.S. candle contract.

    - Renames common aliases (``time`` → ``timestamp``, ``tick_volume`` → ``volume``)
    - Ensures UTC timezone on the timestamp index
    - Optionally stamps symbol / timeframe metadata columns
    """
    out = df.copy()

    # Prefer a single volume source when multiple aliases exist (MT5 exports both).
    if "volume" not in out.columns:
        if "tick_volume" in out.columns:
            out = out.rename(columns={"tick_volume": "volume"})
            out = out.drop(columns=["real_volume"], errors="ignore")
        elif "real_volume" in out.columns:
            out = out.rename(columns={"real_volume": "volume"})
        elif "Volume" in out.columns:
            out = out.rename(columns={"Volume": "volume"})
        elif "vol" in out.columns:
            out = out.rename(columns={"vol": "volume"})

    rename_map = {
        c: _COLUMN_ALIASES[c]
        for c in out.columns
        if c in _COLUMN_ALIASES and _COLUMN_ALIASES[c] not in out.columns
    }
    # Avoid mapping two sources onto the same target name
    seen_targets: set[str] = set()
    filtered: dict[str, str] = {}
    for src, tgt in rename_map.items():
        if tgt in seen_targets or tgt in out.columns:
            continue
        filtered[src] = tgt
        seen_targets.add(tgt)
    out = out.rename(columns=filtered)

    # If index already holds time and no timestamp column exists
    if "timestamp" not in out.columns:
        if isinstance(out.index, pd.DatetimeIndex):
            out = out.reset_index()
            # first column after reset is usually the former index name
            if out.columns[0] != "timestamp":
                out = out.rename(columns={out.columns[0]: "timestamp"})
        else:
            raise ValueError(
                "Cannot normalize OHLCV: no 'timestamp'/'time' column and index is not DatetimeIndex."
            )

    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=False)
    if assume_utc:
        if out["timestamp"].dt.tz is None:
            out["timestamp"] = out["timestamp"].dt.tz_localize("UTC")
        else:
            out["timestamp"] = out["timestamp"].dt.tz_convert("UTC")

    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if symbol is not None:
        out["symbol"] = symbol
    if timeframe is not None:
        out["timeframe"] = timeframe

    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    out = out.reset_index(drop=True)
    return out


def load_ohlcv_parquet(
    path: str | Path,
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    validate: bool = True,
) -> pd.DataFrame:
    """
    Load an OHLCV parquet file and normalize to the candle schema.

    Parameters
    ----------
    path:
        Path to a parquet file (e.g. ``data/raw/xauusd_h1_2018_present.parquet``).
    symbol / timeframe:
        Optional metadata stamps if not present in the file.
    validate:
        If True, run structural validation after normalization.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"OHLCV file not found: {path}")

    raw = pd.read_parquet(path)
    # Infer symbol/timeframe from filename if not provided
    stem = path.stem.lower()  # e.g. xauusd_h1_2018_present
    parts = stem.split("_")
    inferred_symbol = parts[0] if parts else None
    inferred_tf = parts[1] if len(parts) > 1 else None

    df = normalize_ohlcv(
        raw,
        symbol=symbol or inferred_symbol,
        timeframe=timeframe or inferred_tf,
    )

    if validate:
        validate_ohlcv(df)

    return df


def to_price_index(df: pd.DataFrame) -> pd.DataFrame:
    """Return a timestamp-indexed OHLCV frame (useful for session slicing)."""
    out = df.copy()
    if "timestamp" in out.columns:
        out = out.set_index("timestamp")
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    return out.sort_index()
