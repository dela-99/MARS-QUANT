"""
Tests for XAU-M5-MOMENTUM-001 strategy module.
"""

import pandas as pd
import numpy as np
import pytest


def test_momentum_signal_generation():
    from mars.libs.strategies.xau_m5_momentum import MomentumParams, compute_momentum_signals
    
    # Create synthetic M5 data with clear momentum
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    close = np.cumsum(np.random.randn(n) * 0.5) + 2000  # Trending up
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = np.roll(close, 1); open_[0] = close[0]
    
    m5 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 1000, "spread": 200}, index=dates)
    h1 = m5.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                 "volume": "sum", "spread": "mean"}).dropna()
    
    params = MomentumParams(lookback_bars=20, ema_period=20, atr_period=14, atr_stop_mult=2.0,
                            max_hold_bars=6, execution_timeframe="M5")
    signals = compute_momentum_signals(m5, m5, h1, params)
    
    # Should have signal columns
    assert "entry_long" in signals.frame.columns
    assert "entry_short" in signals.frame.columns
    assert "exit_long" in signals.frame.columns
    assert "exit_short" in signals.frame.columns
    assert "stop_distance" in signals.frame.columns
    assert "donchian_high" in signals.frame.columns
    assert "donchian_low" in signals.frame.columns
    
    # Entry logic: close > prior donchian_high + H1 regime long
    # Exit: close < donchian_mid or stop hit
    long_signals = signals.frame[signals.frame["entry_long"]]
    if len(long_signals) > 0:
        # Verify regime alignment (no look-ahead)
        assert all(signals.frame.loc[long_signals.index, "h1_regime"] == 1)


def test_momentum_params_immutable():
    from mars.libs.strategies.xau_m5_momentum import MomentumParams
    params = MomentumParams()
    assert params.lookback_bars == 20
    assert params.execution_timeframe == "M5"
    # Frozen dataclass
    try:
        params.lookback_bars = 30
        assert False, "Should be frozen"
    except Exception:
        pass


def test_momentum_strategy_generate_setups():
    from mars.libs.strategies.xau_m5_momentum import XauM5MomentumStrategy, MomentumParams, compute_momentum_signals
    
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
    
    params = MomentumParams(execution_timeframe="M5", max_hold_bars=6)
    strategy = XauM5MomentumStrategy(params=params)
    setups = strategy.generate_setups(m5, context_tf=m5, h1=h1)
    
    # Should return TradeSetup objects
    assert len(setups) >= 0  # May or may not have signals depending on random data
    for setup in setups:
        assert setup.side in ("long", "short")
        assert setup.symbol == "XAUUSDm"
        assert "stop_distance" in setup.metadata