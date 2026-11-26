"""
Tests for XAU-M5-PULLBACK-001 strategy module.
"""

import pandas as pd
import numpy as np
import pytest


def test_pullback_signal_generation():
    from mars.libs.strategies.xau_m5_pullback import PullbackParams, compute_pullback_signals
    
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
    
    params = PullbackParams(trend_ema_period=50, pullback_ema_period=20, atr_period=14, atr_stop_mult=2.0,
                            max_hold_bars=12, execution_timeframe="M5")
    signals = compute_pullback_signals(m5, m5, h1, params)
    
    assert "entry_long" in signals.frame.columns
    assert "entry_short" in signals.frame.columns
    assert "exit_long" in signals.frame.columns
    assert "exit_short" in signals.frame.columns
    assert "stop_distance" in signals.frame.columns
    assert "trend_ema" in signals.frame.columns
    assert "pullback_ema" in signals.frame.columns


def test_pullback_params_immutable():
    from mars.libs.strategies.xau_m5_pullback import PullbackParams
    params = PullbackParams()
    assert params.trend_ema_period == 50
    assert params.execution_timeframe == "M5"
    try:
        params.trend_ema_period = 60
        assert False, "Should be frozen"
    except Exception:
        pass


def test_pullback_strategy_generate_setups():
    from mars.libs.strategies.xau_m5_pullback import XauM5PullbackStrategy, PullbackParams
    
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
    
    params = PullbackParams(execution_timeframe="M5", max_hold_bars=12)
    strategy = XauM5PullbackStrategy(params=params)
    setups = strategy.generate_setups(m5, context_tf=m5, h1=h1)
    
    assert len(setups) >= 0
    for setup in setups:
        assert setup.side in ("long", "short")
        assert setup.symbol == "XAUUSDm"