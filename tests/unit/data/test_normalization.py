"""Tests for OHLCV normalizer."""
 
from __future__ import annotations
 
import pandas as pd
import pytest
 
from mars.data.normalization.ohlcv import OHLCVNormalizer
 
 
def test_normalize_mt5_like_columns():
    raw = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=5, freq="h"),
            "open": [1, 2, 3, 4, 5],
            "high": [1.5, 2.5, 3.5, 4.5, 5.5],
            "low": [0.5, 1.5, 2.5, 3.5, 4.5],
            "close": [1.2, 2.2, 3.2, 4.2, 5.2],
            "tick_volume": [10, 20, 30, 40, 50],
        }
    )
    norm = OHLCVNormalizer(source_timezone="UTC")
    out = norm.normalize(raw)
    assert list(out.columns[:5]) == ["open", "high", "low", "close", "volume"]
    assert isinstance(out.index, pd.DatetimeIndex)
    assert str(out.index.tz) == "UTC"
    assert out.index.is_monotonic_increasing
    assert not out.index.duplicated().any()
 
 
def test_normalize_deduplicates():
    raw = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01 00:00",
                "2024-01-01 00:00",
                "2024-01-01 01:00",
            ],
            "open": [1, 1, 2],
            "high": [1, 1, 2],
            "low": [1, 1, 2],
            "close": [1, 1, 2],
        }
    )
    out = OHLCVNormalizer().normalize(raw)
    assert len(out) == 2
 
 
def test_empty_raises():
    with pytest.raises(ValueError):
        OHLCVNormalizer().normalize(pd.DataFrame())