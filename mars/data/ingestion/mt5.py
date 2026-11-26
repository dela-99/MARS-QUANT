"""
MetaTrader 5 market data ingestor.
 
Ingestion only — no trading. Requires MetaTrader5 package and a running terminal.
"""
 
from __future__ import annotations
 
from datetime import datetime
from typing import Any, Optional
 
import pandas as pd
 
from mars.core.config import MT5Config, DEFAULT_CONFIG
from mars.core.timeframes import Timeframe
 
 
class MT5Ingestor:
    """
    Pull OHLCV bars from MetaTrader 5.
 
    Returns a raw DataFrame with MT5 column names; pass through
    OHLCVNormalizer before validation / storage.
    """
 
    TIMEFRAME_MAP = {
        Timeframe.H1: "TIMEFRAME_H1",
        Timeframe.M30: "TIMEFRAME_M30",
        Timeframe.M15: "TIMEFRAME_M15",
        Timeframe.M5: "TIMEFRAME_M5",
        Timeframe.M3: "TIMEFRAME_M3",
        Timeframe.M1: "TIMEFRAME_M1",
    }
 
    def __init__(self, config: Optional[MT5Config] = None) -> None:
        self.config = config or DEFAULT_CONFIG.mt5
 
    def ingest(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        **kwargs: Any,
    ) -> pd.DataFrame:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise ImportError(
                "MetaTrader5 package is required for MT5Ingestor. "
                "Install with: pip install MetaTrader5"
            ) from exc

        # Try to initialize without credentials (connect to already-running terminal)
        if not mt5.initialize():
            # If that fails, try with explicit credentials
            if not self.config.is_configured():
                raise RuntimeError(
                    "MT5 credentials not configured. Set DEMO_ACCOUNT_NUMBER, "
                    "PASSWORD, SERVER in .env"
                )
            login = int(self.config.account_number)  # type: ignore[arg-type]
            if not mt5.initialize(
                login=login,
                password=self.config.password,
                server=self.config.server,
            ):
                raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

        try:
            # Verify we have a valid account connection
            acct = mt5.account_info()
            if acct is None:
                raise RuntimeError("MT5 connected but no account logged in")

            tf_attr = self.TIMEFRAME_MAP.get(timeframe, "TIMEFRAME_H1")
            mt5_tf = getattr(mt5, tf_attr)
            rates = mt5.copy_rates_range(symbol, mt5_tf, start, end)
            if rates is None or len(rates) == 0:
                raise RuntimeError(
                    f"No data from MT5 for {symbol} {timeframe.value} "
                    f"[{start} → {end}]: {mt5.last_error()}"
                )
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            return df
        finally:
            mt5.shutdown()

    def ingest_ticks(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        tick_type: int = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """
        Pull tick history from MetaTrader 5.

        Returns a raw DataFrame with MT5 tick columns:
        time, bid, ask, last, volume, time_msc, flags, volume_real

        Args:
            symbol: Trading symbol (e.g., "XAUUSDm")
            start: Start datetime (UTC)
            end: End datetime (UTC)
            tick_type: MT5 tick type constant (COPY_TICKS_ALL, COPY_TICKS_INFO, COPY_TICKS_TRADE).
                       Defaults to COPY_TICKS_ALL if available.
        """
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise ImportError(
                "MetaTrader5 package is required for MT5Ingestor. "
                "Install with: pip install MetaTrader5"
            ) from exc

        # Try to initialize without credentials (connect to already-running terminal)
        if not mt5.initialize():
            # If that fails, try with explicit credentials
            if not self.config.is_configured():
                raise RuntimeError(
                    "MT5 credentials not configured. Set DEMO_ACCOUNT_NUMBER, "
                    "PASSWORD, SERVER in .env"
                )
            login = int(self.config.account_number)  # type: ignore[arg-type]
            if not mt5.initialize(
                login=login,
                password=self.config.password,
                server=self.config.server,
            ):
                raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

        try:
            # Verify we have a valid account connection
            acct = mt5.account_info()
            if acct is None:
                raise RuntimeError("MT5 connected but no account logged in")

            if tick_type is None:
                tick_type = getattr(mt5, "COPY_TICKS_ALL", 0)
            ticks = mt5.copy_ticks_range(symbol, start, end, tick_type)
            if ticks is None or len(ticks) == 0:
                raise RuntimeError(
                    f"No tick data from MT5 for {symbol} "
                    f"[{start} → {end}]: {mt5.last_error()}"
                )
            df = pd.DataFrame(ticks)
            # Convert time from seconds since epoch to datetime
            df["time"] = pd.to_datetime(df["time"], unit="s")
            # time_msc is milliseconds since epoch
            if "time_msc" in df.columns:
                df["time_msc"] = pd.to_datetime(df["time_msc"], unit="ms")
            return df
        finally:
            mt5.shutdown()