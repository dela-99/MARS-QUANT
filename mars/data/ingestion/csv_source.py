"""CSV market data ingestor for raw CSV exports (Dukascopy, HistData, etc.)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from mars.core.timeframes import Timeframe


class CSVIngestor:
    """Load bars from a local CSV file path."""

    # Map common CSV timestamp column names to standard
    TIMESTAMP_COLUMNS = ("time", "timestamp", "datetime", "date", "<DATE>", "<TIME>")
    
    def __init__(self, path: Union[str, Path], sep: str = ",", **read_csv_kwargs) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"CSV not found: {self.path}")
        self.sep = sep
        self.read_csv_kwargs = read_csv_kwargs

    def ingest(
        self,
        symbol: str = "",
        timeframe: Optional[Timeframe] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """
        Load and return raw bars from CSV.

        Parameters
        ----------
        symbol: str
            Expected symbol (e.g., "XAUUSD") — used for validation if present in CSV
        timeframe: Timeframe
            Expected timeframe — used for validation
        start/end: datetime
            Optional time filters (UTC)
        **kwargs:
            parse_dates: list of columns to parse as dates (default: auto-detect)
            timestamp_column: explicit timestamp column name
            tz: source timezone if CSV timestamps are not UTC (default: UTC)
            sep: CSV separator (default: auto-detect from constructor)
        """
        # First, read just the header to detect timestamp column
        header = pd.read_csv(self.path, nrows=0, sep=self.sep)
        columns = header.columns.tolist()

        # Find which timestamp columns actually exist (excluding <DATE> and <TIME> since we'll handle them specially)
        timestamp_cols = [c for c in self.TIMESTAMP_COLUMNS if c in columns and c not in ("<DATE>", "<TIME>")]
        if not timestamp_cols and not ("<DATE>" in columns and "<TIME>" in columns):
            raise ValueError(f"No timestamp column found in CSV. Tried: {self.TIMESTAMP_COLUMNS}. Available: {columns}")

        # Read CSV WITHOUT parsing <DATE> and <TIME> as dates - we'll handle them manually
        # Force <DATE> and <TIME> to be read as strings to prevent pandas from inferring dates
        dtype = {"<DATE>": str, "<TIME>": str} if "<DATE>" in columns and "<TIME>" in columns else {}
        parse_dates = kwargs.get("parse_dates", timestamp_cols)
        df = pd.read_csv(self.path, sep=self.sep, parse_dates=parse_dates, dtype=dtype, **self.read_csv_kwargs)

        # Handle the case where we have separate <DATE> and <TIME> columns
        # Combine them into a single timestamp
        if "<DATE>" in df.columns and "<TIME>" in df.columns:
            # Combine DATE and TIME into a single timestamp
            # DATE is like "2020.01.02", TIME is like "00:00:00"
            df["timestamp"] = pd.to_datetime(df["<DATE>"].astype(str) + " " + df["<TIME>"].astype(str), utc=True, format="%Y.%m.%d %H:%M:%S")
        else:
            # Find timestamp column
            timestamp_col = kwargs.get("timestamp_column")
            if timestamp_col is None:
                for c in self.TIMESTAMP_COLUMNS:
                    if c in df.columns:
                        timestamp_col = c
                        break
            if timestamp_col is None:
                raise ValueError(f"No timestamp column found. Tried: {self.TIMESTAMP_COLUMNS}")

            # Ensure timestamp is datetime and UTC
            ts = pd.to_datetime(df[timestamp_col], utc=True)
            df = df.rename(columns={timestamp_col: "timestamp"})
            df["timestamp"] = ts

        # Handle source timezone if provided (e.g., US/Eastern for HistData)
        source_tz = kwargs.get("tz")
        if source_tz is not None:
            if ts.dt.tz is None:
                df["timestamp"] = ts.dt.tz_localize(source_tz).dt.tz_convert("UTC")
            else:
                df["timestamp"] = ts.dt.tz_convert("UTC")

        # Optional time filter
        if start is not None:
            start_ts = pd.Timestamp(start, tz="UTC")
            df = df[df["timestamp"] >= start_ts]
        if end is not None:
            end_ts = pd.Timestamp(end, tz="UTC")
            df = df[df["timestamp"] <= end_ts]

        # Validate symbol if present in CSV
        if symbol and "instrument" in df.columns:
            unique_symbols = df["instrument"].unique()
            if len(unique_symbols) == 1 and unique_symbols[0] != symbol:
                # Common alias mapping
                alias_map = {"GOLD": "XAUUSD", "XAU": "XAUUSD", "XAU/USD": "XAUUSD"}
                expected = alias_map.get(unique_symbols[0].upper(), unique_symbols[0].upper())
                if expected != symbol.upper():
                    raise ValueError(f"Symbol mismatch: CSV has '{unique_symbols[0]}', expected '{symbol}'")

        return df