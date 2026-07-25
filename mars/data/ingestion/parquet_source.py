"""Ingest from existing parquet files (legacy data migration helper)."""
 
from __future__ import annotations
 
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union
 
import pandas as pd
 
from mars.core.timeframes import Timeframe
 
 
class ParquetIngestor:
    """Load bars from a local parquet path (for reprocessing legacy datasets)."""
 
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
 
    def ingest(
        self,
        symbol: str = "",
        timeframe: Optional[Timeframe] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"Parquet not found: {self.path}")
        df = pd.read_parquet(self.path)
        # Optional time filter if a time-like column exists
        time_col = None
        for c in ("time", "timestamp", "datetime"):
            if c in df.columns:
                time_col = c
                break
        if time_col and (start is not None or end is not None):
            ts = pd.to_datetime(df[time_col])
            mask = pd.Series(True, index=df.index)
            if start is not None:
                mask &= ts >= pd.Timestamp(start)
            if end is not None:
                mask &= ts <= pd.Timestamp(end)
            df = df.loc[mask]
        return df