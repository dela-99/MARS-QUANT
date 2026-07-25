"""Shared fixtures for M.A.R.S. unit tests."""
 
from __future__ import annotations
 
import numpy as np
import pandas as pd
import pytest
 
 
@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """Synthetic UTC OHLCV bars (deterministic)."""
    rng = np.random.default_rng(42)
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    # Random walk close
    rets = rng.normal(0, 0.001, size=n)
    close = 2000 * np.exp(np.cumsum(rets))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.0005, size=n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.0005, size=n))
    volume = rng.integers(100, 1000, size=n).astype(float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )
 
 
@pytest.fixture
def returns_series() -> pd.Series:
    rng = np.random.default_rng(0)
    return pd.Series(rng.normal(0.0005, 0.01, size=252))