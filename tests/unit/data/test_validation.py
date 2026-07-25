"""Tests for market data validation checks."""
 
from __future__ import annotations
 
import numpy as np
import pandas as pd
 
from mars.core.timeframes import Timeframe
from mars.data.validation.pipeline import MarketDataValidator
from mars.data.validation.checks import check_ohlc_consistency, check_duplicates
 
 
def test_ohlc_inconsistency_detected(ohlcv_df):
    df = ohlcv_df.copy()
    df.iloc[10, df.columns.get_loc("high")] = df.iloc[10]["low"] - 1
    issues = check_ohlc_consistency(df)
    assert any(i.code == "OHLC_INCONSISTENT" for i in issues)
 
 
def test_duplicates_detected(ohlcv_df):
    df = pd.concat([ohlcv_df.iloc[:5], ohlcv_df.iloc[:1]])
    issues = check_duplicates(df)
    assert any(i.code == "DUPLICATE_TIMESTAMPS" for i in issues)
 
 
def test_validator_passes_clean_data(ohlcv_df):
    report = MarketDataValidator().validate(ohlcv_df, Timeframe.H1)
    assert report.passed
    assert report.row_count == len(ohlcv_df)