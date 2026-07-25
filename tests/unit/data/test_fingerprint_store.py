"""Tests for fingerprinting and parquet store."""
 
from __future__ import annotations
 
from pathlib import Path
 
import pandas as pd
 
from mars.core.schemas import DatasetMetadata
from mars.core.timeframes import Timeframe
from mars.core.types import DatasetLayer
from mars.data.storage.parquet_store import ParquetDatasetStore
from mars.data.versioning.fingerprint import compute_fingerprint
 
 
def test_fingerprint_deterministic(ohlcv_df):
    a = compute_fingerprint(ohlcv_df)
    b = compute_fingerprint(ohlcv_df)
    assert a.digest == b.digest
    assert a.row_count == len(ohlcv_df)
 
 
def test_fingerprint_changes_with_data(ohlcv_df):
    a = compute_fingerprint(ohlcv_df)
    df2 = ohlcv_df.copy()
    df2.iloc[0, df2.columns.get_loc("close")] += 1.0
    b = compute_fingerprint(df2)
    assert a.digest != b.digest
 
 
def test_parquet_store_roundtrip(ohlcv_df, tmp_path: Path):
    store = ParquetDatasetStore(root=tmp_path)
    meta = DatasetMetadata(
        dataset_id="test_ds",
        layer=DatasetLayer.PROCESSED,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        version="1.0.0",
        source="test",
    )
    path = store.write(ohlcv_df, meta)
    assert path.exists()
    loaded = store.read(DatasetLayer.PROCESSED, "XAUUSD", Timeframe.H1, "1.0.0")
    assert len(loaded) == len(ohlcv_df)
    assert "close" in loaded.columns