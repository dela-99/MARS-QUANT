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