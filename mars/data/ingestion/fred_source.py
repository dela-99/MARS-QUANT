from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
from pandas.tseries.offsets import BDay

from mars.core.timeframes import Timeframe


class FREDIngestor:
    """Pull macro time series from FRED API.

    Returns a raw DataFrame with timestamp index and value column.
    Requires FRED_API_KEY environment variable or passed via constructor.

    Publication lag handling:
    - FRED series (especially DFII10, DTWEXBGS) are typically published with
      a 1-business-day lag (value for date T becomes available on T+1).
    - By default, this ingestor shifts all timestamps forward by 1 business day
      so that the timestamp represents when the data becomes *available*,
      not the reference date. This prevents look-ahead bias.
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
        publication_lag_bdays: int = 1,
    ) -> None:
        """
        Parameters
        ----------
        api_key: FRED API key. If None, reads from FRED_API_KEY env var.
        cache_dir: Directory to cache raw CSV downloads. If None, no caching.
        publication_lag_bdays: Number of business days to shift timestamps forward
            to account for FRED publication lag. Default=1 (next business day).
            Set to 0 to disable lag adjustment (not recommended for research).
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
        self.publication_lag_bdays = publication_lag_bdays
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
        Fetch FRED series and return as DataFrame with publication-lag-adjusted timestamps.

        Parameters
        ----------
        symbol: FRED series ID or alias from FRED_SERIES (e.g., "DXY", "REAL_YIELD_10Y", "VIX")
        timeframe: Expected timeframe (used for validation)
        start/end: Date range filter (applied after fetch, in *available* date space)
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

        # CRITICAL: Apply publication lag shift
        # FRED timestamps are the *reference dates* (e.g., value for 2024-01-15).
        # That value becomes available on the next business day.
        # Shift forward by publication_lag_bdays business days so the timestamp
        # represents when the data is *actually available* for trading decisions.
        if self.publication_lag_bdays > 0:
            df["timestamp"] = df["timestamp"] + BDay(self.publication_lag_bdays)

        # Convert to DataFrame
        df = df.rename(columns={"value": "close"})
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