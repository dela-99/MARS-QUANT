"""Smoke tests for data normalization."""

import pandas as pd

from mars.libs.data.loaders import normalize_ohlcv
from mars.libs.data.validation import validate_ohlcv


def test_normalize_aliases():
    raw = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=5, freq="h"),
            "open": [1, 2, 3, 4, 5],
            "high": [2, 3, 4, 5, 6],
            "low": [0.5, 1.5, 2.5, 3.5, 4.5],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5],
            "tick_volume": [10, 11, 12, 13, 14],
        }
    )
    df = normalize_ohlcv(raw, symbol="xauusd", timeframe="h1")
    assert "timestamp" in df.columns
    assert "volume" in df.columns
    assert df["symbol"].iloc[0] == "xauusd"
    report = validate_ohlcv(df, strict=True)
    assert report.ok
    assert report.n_rows == 5
