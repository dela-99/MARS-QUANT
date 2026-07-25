"""Tests for multi-timeframe engine and alignment."""
 
from __future__ import annotations
 
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.features.momentum.returns import LogReturnFeature
from mars.features.volatility.realized import ATRFeature
from mars.features.multi_timeframe.engine import MultiTimeframeFeatureEngine
from mars.features.alignment.engine import AlignmentEngine
 
 
def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    l = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    v = df["volume"].resample(rule).sum()
    out = pd.concat([o, h, l, c, v], axis=1)
    out.columns = ["open", "high", "low", "close", "volume"]
    return out.dropna()
 
 
def test_mtf_and_align(ohlcv_df):
    # ohlcv_df is hourly; synthesize M30 and M15 by resampling (for test only)
    # Actually H1 can't resample to M30 from H1 alone meaningfully —
    # use same frame labeled as different TFs for interface test, or upsample.
    df_h1 = ohlcv_df
    # Create finer grid by forward-filling (synthetic)
    df_m15 = df_h1.resample("15min").ffill().dropna()
    df_m5 = df_h1.resample("5min").ffill().dropna()
 
    engine = MultiTimeframeFeatureEngine(
        features=[LogReturnFeature(), ATRFeature(window=5)],
        prefix_with_timeframe=True,
    )
    bundle = engine.compute(
        {
            Timeframe.H1: df_h1,
            Timeframe.M15: df_m15,
            Timeframe.M5: df_m5,
        }
    )
    assert Timeframe.H1 in bundle.features
    assert any(c.startswith("h1__") for c in bundle.features[Timeframe.H1].columns)
 
    aligned = AlignmentEngine(base_timeframe=Timeframe.M5).align(bundle)
    assert len(aligned.features) == len(df_m5)
    # Coarser features present on base index
    assert any(c.startswith("h1__") for c in aligned.features.columns)