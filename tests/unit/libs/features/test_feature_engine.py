from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mars.core.timeframes import Timeframe
from mars.libs.features import (
    AlignmentEngine,
    ATRFeature,
    DataQualityValidator,
    FeaturePipeline,
    FeatureRegistry,
    FeatureValidator,
    FairValueGapFeature,
    LogTransformFeature,
    MultiTimeframeFeatureEngine,
    RSIFeature,
    RateOfChangeFeature,
    SessionFeature,
    TrendFeature,
)


def bars(freq="3min", periods=120, start="2026-01-05", tz="UTC"):
    idx = pd.date_range(start, periods=periods, freq=freq, tz=tz)
    close = pd.Series(np.linspace(100, 110, periods) + np.sin(np.arange(periods) / 3), index=idx)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.arange(periods) + 1,
        },
        index=idx,
    )


def test_feature_metadata_versioning_and_determinism():
    df = bars()
    feature = RSIFeature(window=7)
    a = feature.compute(df).data
    b = feature.compute(df).data
    pd.testing.assert_frame_equal(a, b)
    assert feature.metadata.version == "1.0.0"
    assert feature.metadata.mathematical_definition
    assert feature.metadata.parameters["window"] == 7


def test_registry_and_pipeline():
    registry = FeatureRegistry()
    registry.register(RateOfChangeFeature)
    feature = registry.create("momentum.roc@1.0.0", window=3)
    out = FeaturePipeline([feature, LogTransformFeature()]).transform(bars())
    assert {"roc", "log_close", "log_return"}.issubset(out.columns)


def test_feature_validator_reports_nans_and_outputs():
    report = FeatureValidator().validate(ATRFeature(window=5), bars())
    assert report.passed
    assert report.nan_count["atr"] >= 4
    assert report.version == "1.0.0"


def test_data_quality_detects_duplicates_nans_and_timezone():
    df = bars().copy()
    df.iloc[0, 0] = np.nan
    dup = pd.concat([df, df.iloc[[0]]]).sort_index()
    report = DataQualityValidator(expected_frequency="3min", allow_weekends=True).validate(dup)
    assert report.duplicate_timestamps == 1
    assert report.nan_values == 2
    assert report.timezone_consistent
    assert not report.passed


def test_alignment_uses_closed_higher_timeframe_bars_only():
    m3_index = pd.date_range("2026-01-05 00:00", periods=30, freq="3min", tz="UTC")
    h1_index = pd.date_range("2026-01-05 00:00", periods=3, freq="1h", tz="UTC")
    m3 = pd.DataFrame({"m3__x": range(len(m3_index))}, index=m3_index)
    h1 = pd.DataFrame({"h1__context": [10, 20, 30]}, index=h1_index)
    aligned = AlignmentEngine(base_timeframe=Timeframe.M3).align({Timeframe.M3: m3, Timeframe.H1: h1}).data
    assert pd.isna(aligned.loc[pd.Timestamp("2026-01-05 00:57", tz="UTC"), "h1__context"])
    assert aligned.loc[pd.Timestamp("2026-01-05 01:00", tz="UTC"), "h1__context"] == 10


def test_multi_timeframe_engine_outputs_one_aligned_dataset():
    h1 = bars("1h", 12)
    m30 = bars("30min", 24)
    m15 = bars("15min", 48)
    m5 = bars("5min", 144)
    m3 = bars("3min", 240)
    engine = MultiTimeframeFeatureEngine(
        features=[RateOfChangeFeature(window=2), SessionFeature(), FairValueGapFeature(), TrendFeature(fast=3, slow=5)],
        base_timeframe=Timeframe.M3,
        validate_data=False,
    )
    ds = engine.compute({Timeframe.H1: h1, Timeframe.M30: m30, Timeframe.M15: m15, Timeframe.M5: m5, Timeframe.M3: m3})
    assert len(ds.data) == len(m3)
    assert "m3__roc" in ds.data.columns
    assert "h1__roc" in ds.data.columns
    assert ds.metadata["alignment"]["closed_bar_only"] is True


def test_no_prohibited_responsibilities_in_public_feature_api():
    import mars.libs.features as features

    names = set(features.__all__)
    assert not {"Broker", "Order", "TradeExecutor", "Strategy"} & names
