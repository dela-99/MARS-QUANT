"""Tests for core feature modules — determinism and no look-ahead shape."""
 
from __future__ import annotations
 
import numpy as np
import pandas as pd
 
from mars.features.momentum.returns import LogReturnFeature, RollingMomentumFeature
from mars.features.volatility.realized import ATRFeature, RealizedVolatilityFeature
from mars.features.time.calender import CalendarTimeFeature
from mars.features.session.fx_sessions import FXSessionFeature
from mars.features.microstructure.candle_shape import CandleShapeFeature
 
 
def test_log_return_deterministic(ohlcv_df):
    feat = LogReturnFeature()
    a = feat.compute(ohlcv_df).data
    b = feat.compute(ohlcv_df).data
    pd.testing.assert_frame_equal(a, b)
    assert a["log_return"].isna().iloc[0]
    assert a["log_return"].notna().iloc[1]
 
 
def test_rolling_momentum_lookback(ohlcv_df):
    feat = RollingMomentumFeature(window=10)
    out = feat.compute(ohlcv_df).data
    assert out.iloc[:9].isna().all().all()
    assert out.iloc[10:].notna().any().any()
 
 
def test_atr_non_negative(ohlcv_df):
    out = ATRFeature(window=14).compute(ohlcv_df).data
    valid = out.dropna()
    assert (valid >= 0).all().all()
 
 
def test_realized_vol(ohlcv_df):
    out = RealizedVolatilityFeature(window=20).compute(ohlcv_df).data
    assert out.shape[0] == len(ohlcv_df)
 
 
def test_calendar_time(ohlcv_df):
    out = CalendarTimeFeature().compute(ohlcv_df).data
    assert set(out.columns) == {
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
        "is_weekend",
    }
    # sin^2 + cos^2 ≈ 1
    assert np.allclose(out["hour_sin"] ** 2 + out["hour_cos"] ** 2, 1.0)
 
 
def test_session_flags(ohlcv_df):
    out = FXSessionFeature().compute(ohlcv_df).data
    assert out[["is_asia", "is_london", "is_ny"]].isin([0.0, 1.0]).all().all()
 
 
def test_candle_shape_bounds(ohlcv_df):
    out = CandleShapeFeature().compute(ohlcv_df).data.dropna()
    assert (out["close_location"] >= 0).all()
    assert (out["close_location"] <= 1).all()