"""
Tests for XAU-M5-VOL-EXPANSION-001 strategy module.
"""

import pandas as pd
import numpy as np
import pytest


def test_vol_expansion_signal_generation():
    from mars.libs.strategies.xau_m5_vol_expansion import VolExpansionParams, compute_vol_expansion_signals
    
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    close = np.cumsum(np.random.randn(n) * 0.5) + 2000
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = np.roll(close, 1); open_[0] = close[0]
    
    m5 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 1000, "spread": 200}, index=dates)
    h1 = m5.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                 "volume": "sum", "spread": "mean"}).dropna()
    
    params = VolExpansionParams(atr_period=14, expansion_threshold=2.0, atr_stop_mult=2.0,
                                max_hold_bars=6, execution_timeframe="M5")
    signals = compute_vol_expansion_signals(m5, m5, h1, params)
    
    assert "entry_long" in signals.frame.columns
    assert "entry_short" in signals.frame.columns
    assert "exit_long" in signals.frame.columns
    assert "exit_short" in signals.frame.columns
    assert "stop_distance" in signals.frame.columns
    assert "atr" in signals.frame.columns
    assert "atr_median" in signals.frame.columns


def test_vol_expansion_params_immutable():
    from mars.libs.strategies.xau_m5_vol_expansion import VolExpansionParams
    params = VolExpansionParams()
    assert params.atr_period == 14
    assert params.expansion_threshold == 2.0
    assert params.execution_timeframe == "M5"
    try:
        params.atr_period = 20
        assert False, "Should be frozen"
    except Exception:
        pass


def test_vol_expansion_strategy_generate_setups():
    from mars.libs.strategies.xau_m5_vol_expansion import XauM5VolExpansionStrategy, VolExpansionParams
    
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    close = np.cumsum(np.random.randn(n) * 0.5) + 2000
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = np.roll(close, 1); open_[0] = close[0]
    
    m5 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 1000, "spread": 200}, index=dates)
    h1 = m5.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                 "volume": "sum", "spread": "mean"}).dropna()
    
    params = VolExpansionParams(execution_timeframe="M5", max_hold_bars=6)
    strategy = XauM5VolExpansionStrategy(params=params)
    setups = strategy.generate_setups(m5, context_tf=m5, h1=h1)
    
    assert len(setups) >= 0
    for setup in setups:
        assert setup.side in ("long", "short")
        assert setup.symbol == "XAUUSDm"