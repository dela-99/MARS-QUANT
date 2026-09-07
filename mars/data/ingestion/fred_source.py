"""FRED (Federal Reserve Economic Data) market data ingestor.

Fetches macro time series (DXY, real yields, VIX) from FRED API.
Implements DataIngestor interface for plug-and-play with the ingestion pipeline.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from mars.core.timeframes import Timeframe


class FREDIngestor:
    """Pull macro time series from FRED API.

    Returns a raw DataFrame with timestamp index and value column.
    Requires FRED_API_KEY environment variable or passed via constructor.
    """

    # FRED series IDs for key macro indicators
    FRED_SERIES = {
        "DXY": "DTWEXBGS",          # Trade Weighted U.S. Dollar Index: Broad, Goods & Services
        "DXY_ALT": "DTWEXAFEGS",    # Trade Weighted U.S. Dollar Index: Advanced Foreign Economies
        "REAL_YIELD_10Y": "DFII10", # Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, Inflation-Indexed
        "NOMINAL_YIELD_10Y": "DGS10", # Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity
        "VIX": "VIXCLS",            # CBOE Volatility Index: VIX
        "SP500": "SP500",           # S&P 500 Index
        "BAA_YIELD": "BAA",         # Moody's Seasoned Baa Corporate Bond Yield
        "AAA_YIELD": "AAA",         # Moody's Seasoned Aaa Corporate Bond Yield
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        """
        Parameters
        ----------
        api_key: FRED API key. If None, reads from FRED_API_KEY env var.
        cache_dir: Directory to cache raw CSV downloads. If None, no caching.
        """
        try:
            from fredapi import Fred
        except ImportError as exc:
            raise ImportError(
                "fredapi package required for FREDIngestor. Install with: pip install fredapi"
            ) from exc

        self.api_key = api_key
        self.fred = Fred(api_key=api_key)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def ingest(
        self,
        symbol: str = "",
        timeframe: Optional[Timeframe] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """
        Fetch FRED series and return as DataFrame.

        Parameters
        ----------
        symbol: FRED series ID or alias from FRED_SERIES (e.g., "DXY", "REAL_YIELD_10Y", "VIX")
        timeframe: Expected timeframe (used for validation)
        start/end: Date range filter (applied after fetch)
        **kwargs:
            series_id: Override FRED series ID directly
            observation_start/observation_end: Passed to fredapi
        """
        # Resolve series ID
        series_id = kwargs.get("series_id")
        if not series_id:
            series_id = self.FRED_SERIES.get(symbol.upper(), symbol.upper())

        # Fetch from FRED
        obs_start = kwargs.get("observation_start", start)
        obs_end = kwargs.get("observation_end", end)

        series = self.fred.get_series(
            series_id,
            observation_start=obs_start,
            observation_end=obs_end,
        )

        if series is None or len(series) == 0:
            raise RuntimeError(f"No data returned from FRED for series '{series_id}'")

        # Convert to DataFrame
        df = series.to_frame(name="value")
        df.index.name = "timestamp"
        df = df.reset_index()

        # Ensure timestamp is datetime and UTC
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Add metadata columns
        df["series_id"] = series_id
        df["symbol"] = symbol.upper()

        # Optional time filter (in case FRED returned more than requested)
        if start is not None:
            start_ts = pd.Timestamp(start, tz="UTC")
            df = df[df["timestamp"] >= start_ts]
        if end is not None:
            end_ts = pd.Timestamp(end, tz="UTC")
            df = df[df["timestamp"] <= end_ts]

        # Cache if enabled
        if self.cache_dir:
            cache_file = self.cache_dir / f"{series_id}_{start or 'all'}_{end or 'all'}.csv"
            df.to_csv(cache_file, index=False)

        return df

    def ingest_multiple(
        self,
        symbols: list[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        **kwargs: Any,
    ) -> dict[str, pd.DataFrame]:
        """Fetch multiple FRED series at once.

        Returns dict mapping symbol -> DataFrame.
        """
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.ingest(symbol=symbol, start=start, end=end, **kwargs)
            except Exception as e:
                print(f"Warning: Failed to fetch {symbol}: {e}")
        return results


def get_default_fred_series() -> list[str]:
    """Return the default set of macro series for Hyp-C."""
    return ["DXY", "REAL_YIELD_10Y", "VIX"]