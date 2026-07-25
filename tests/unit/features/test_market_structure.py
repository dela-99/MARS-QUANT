"""Tests for swing / BOS interfaces."""
 
from __future__ import annotations
 
from mars.features.market_structure.swings import (
    FractalSwingDetector,
    ZigZagSwingDetector,
    AdaptiveSwingDetector,
)
from mars.features.market_structure.structure import BOSDetector, CHOCHDetector
 
 
def test_fractal_swings_run(ohlcv_df):
    swings = FractalSwingDetector(left=2, right=2).detect(ohlcv_df)
    assert isinstance(swings, list)
    # On random walk we expect some swings
    assert len(swings) > 0
    kinds = {s.kind for s in swings}
    assert kinds <= {"high", "low"}
 
 
def test_zigzag_and_adaptive(ohlcv_df):
    zz = ZigZagSwingDetector(threshold_pct=0.002).detect(ohlcv_df)
    ad = AdaptiveSwingDetector().detect(ohlcv_df)
    assert isinstance(zz, list)
    assert isinstance(ad, list)
 
 
def test_bos_interchangeable_swing(ohlcv_df):
    bos1 = BOSDetector(FractalSwingDetector()).to_frame(ohlcv_df)
    bos2 = BOSDetector(ZigZagSwingDetector(threshold_pct=0.003)).to_frame(ohlcv_df)
    assert "bos_bull" in bos1.columns
    assert "bos_bear" in bos2.columns
    assert len(bos1) == len(ohlcv_df)
 
 
def test_choch_runs(ohlcv_df):
    frame = CHOCHDetector().to_frame(ohlcv_df)
    assert "choch_bull" in frame.columns