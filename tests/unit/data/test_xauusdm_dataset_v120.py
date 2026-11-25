"""
Data-gate tests for the Exness XAUUSDm datasets (Assignment 14, Phase B).

These tests lock in the findings that the data finalisation resolved:

* the 2020 file and the first half of the 2021 file are **daily** bars and must
  never appear in the M5 dataset;
* the file named "XAUUSDm_M5_2024 jan to feb.csv" contains the **full 2024
  calendar year** - contents are authoritative, the filename is wrong;
* the built M5 dataset contains no daily-interval rows and passes every
  integrity check;
* the excluded daily block is preserved as a separate D1 dataset (not deleted);
* the H1 dataset is derived from the M5 dataset, so both live in one frame;
* the raw Exness H1 export sits on a different hour grid than the M5 export.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mars.libs.data.xauusdm_exness import (
    CANONICAL_COLUMNS,
    D1_VERSION,
    H1_VERSION,
    M5_VERSION,
    _read_exness_csv,
    build_datasets,
    inventory_sources,
    sha256_file,
    split_m5_and_d1,
    validate_m5,
)

ROOT = Path(__file__).resolve().parents[3]
RAW_M5 = ROOT / "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv"
M5_PATH = ROOT / f"data/processed/xauusdm/m5/{M5_VERSION}/data.parquet"
H1_PATH = ROOT / f"data/processed/xauusdm/h1/{H1_VERSION}/data.parquet"
D1_PATH = ROOT / f"data/processed/xauusdm/d1/{D1_VERSION}/data.parquet"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def raw_frame():
    return _read_exness_csv(RAW_M5)


@pytest.fixture(scope="module")
def split_frames(raw_frame):
    return split_m5_and_d1(raw_frame)


@pytest.fixture(scope="module")
def m5_data():
    return pd.read_parquet(M5_PATH)


@pytest.fixture(scope="module")
def h1_data():
    return pd.read_parquet(H1_PATH)


# ---------------------------------------------------------------------------
# The 2020 / 2021 daily-bar finding
# ---------------------------------------------------------------------------


class TestDailyIntervalExclusion:
    def test_raw_file_starts_with_a_daily_block(self, split_frames):
        m5, d1 = split_frames
        assert len(d1) == 478
        assert d1["timestamp"].iloc[0] == pd.Timestamp("2020-01-02", tz="UTC")
        assert d1["timestamp"].iloc[-1] == pd.Timestamp("2021-07-16", tz="UTC")

    def test_daily_block_is_contiguous_and_midnight_anchored(self, split_frames):
        _, d1 = split_frames
        assert set(d1["timestamp"].dt.time) == {pd.Timestamp("00:00:00").time()}

    def test_daily_block_has_no_spread(self, split_frames):
        _, d1 = split_frames
        assert int(d1["spread"].sum()) == 0

    def test_no_daily_rows_survive_in_the_m5_dataset(self, split_frames):
        m5, _ = split_frames
        gap = m5["timestamp"].diff().dt.total_seconds().dropna()
        assert int((gap % 86_400 == 0).sum()) == 0

    def test_m5_dataset_starts_after_the_daily_block(self, m5_data):
        first = pd.DatetimeIndex(m5_data.index)[0]
        assert first > pd.Timestamp("2021-07-16", tz="UTC")

    def test_excluded_daily_block_is_preserved_not_deleted(self):
        assert D1_PATH.exists()
        d1 = pd.read_parquet(D1_PATH)
        assert len(d1) == 478
        assert pd.DatetimeIndex(d1.index)[0] == pd.Timestamp("2020-01-02", tz="UTC")

    def test_source_2020_file_is_entirely_daily(self):
        inv = inventory_sources()
        f2020 = next(i for i in inv if "2020" in i.filename)
        assert f2020.inferred_timeframe == "D1"
        assert f2020.m5_rows == 0
        assert f2020.daily_rows == 311

    def test_source_2021_file_has_a_daily_prefix(self):
        inv = inventory_sources()
        f2021 = next(i for i in inv if "2021" in i.filename)
        assert f2021.daily_rows == 167
        assert f2021.m5_rows == 32_475


# ---------------------------------------------------------------------------
# The 2024 filename inconsistency
# ---------------------------------------------------------------------------


class TestFilenameVsContent:
    def test_2024_file_is_flagged_as_mislabelled(self):
        inv = inventory_sources()
        f2024 = next(i for i in inv if "2024" in i.filename)
        assert f2024.filename_mislabelled
        assert "jan to feb" in f2024.filename

    def test_2024_file_actually_contains_the_full_year(self):
        inv = inventory_sources()
        f2024 = next(i for i in inv if "2024" in i.filename)
        assert f2024.m5_rows == 70_773
        assert f2024.daily_rows == 0
        assert f2024.start.startswith("2024-01-01")
        assert f2024.end.startswith("2024-12-31")

    def test_m5_dataset_contains_a_full_2024(self, m5_data):
        year = m5_data[m5_data.index.year == 2024]
        assert len(year) == 70_773
        assert year.index[0].month == 1
        assert year.index[-1].month == 12


# ---------------------------------------------------------------------------
# The built M5 dataset
# ---------------------------------------------------------------------------


class TestM5Dataset:
    def test_file_exists(self):
        assert M5_PATH.exists()

    def test_columns_are_canonical(self, m5_data):
        assert list(m5_data.columns) == list(CANONICAL_COLUMNS)

    def test_index_is_utc_and_monotonic(self, m5_data):
        idx = pd.DatetimeIndex(m5_data.index)
        assert idx.tz is not None
        assert str(idx.tz) == "UTC"
        assert idx.is_monotonic_increasing
        assert not idx.has_duplicates

    def test_no_ohlc_violations(self, m5_data):
        df = m5_data
        bad = (
            (df["high"] < df["low"])
            | (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
        )
        assert int(bad.sum()) == 0

    def test_prices_are_positive(self, m5_data):
        assert bool((m5_data[["open", "high", "low", "close"]] > 0).all().all())

    def test_no_missing_values(self, m5_data):
        assert int(m5_data.isna().sum().sum()) == 0

    def test_spread_is_non_negative_and_preserved(self, m5_data):
        assert int((m5_data["spread"] < 0).sum()) == 0
        # The observed spread survived the build (median ~200 points).
        assert float(m5_data["spread"].median()) > 0

    def test_tick_volume_is_preserved(self, m5_data):
        assert int(m5_data["tick_volume"].sum()) > 0
        assert int(m5_data["tick_volume"].max()) > 0

    def test_real_volume_is_zero_because_the_exporter_has_none(self, m5_data):
        assert int(m5_data["volume"].sum()) == 0

    def test_all_intervals_are_five_minute_or_a_market_closure(self, m5_data):
        gap = pd.Series(pd.DatetimeIndex(m5_data.index)).diff().dt.total_seconds().dropna()
        non_300 = gap[gap != 300]
        # Every non-300s interval must be accounted for as a closure or a
        # documented in-session outage - never a whole-day (daily bar) interval.
        assert int((gap % 86_400 == 0).sum()) == 0
        assert len(non_300) == 1_384
        report = validate_m5(m5_data.reset_index(), expect_five_minute=True)
        classified = (
            report.session_break_gaps
            + report.intraday_closure_gaps
            + report.multi_day_closure_gaps
            + report.in_session_outage_gaps
        )
        assert classified == len(non_300)
        # The overwhelming majority are the one-hour daily session break.
        assert report.session_break_gaps == 1_032

    def test_validation_gate_passes(self, m5_data):
        frame = m5_data.reset_index()
        report = validate_m5(frame, expect_five_minute=True)
        assert report.passed, report.failures
        assert report.duplicate_timestamps == 0
        assert report.ohlc_violations == 0
        assert report.missing_values == 0
        assert report.daily_interval_rows == 0

    def test_manifest_records_provenance_and_checksums(self):
        manifest_path = M5_PATH.parent / "_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == M5_VERSION
        assert len(manifest["checksum"]) == 64
        assert manifest["checksum"] == sha256_file(M5_PATH)
        assert manifest["transformations"]
        assert manifest["known_issues"]
        assert manifest["validation"]["passed"] is True

    def test_rebuild_is_deterministic(self, tmp_path):
        result = build_datasets(repo_root=ROOT, write=False)
        again = build_datasets(repo_root=ROOT, write=False)
        pd.testing.assert_frame_equal(result["m5"], again["m5"])
        pd.testing.assert_frame_equal(result["h1"], again["h1"])


# ---------------------------------------------------------------------------
# The H1 dataset and its provenance
# ---------------------------------------------------------------------------


class TestH1Dataset:
    def test_file_exists(self):
        assert H1_PATH.exists()

    def test_h1_is_derived_from_the_m5_dataset(self, h1_data, m5_data):
        # Same frame, same source: the first H1 bar must not precede the first
        # M5 bar and the last must not follow the last M5 bar.
        assert pd.DatetimeIndex(h1_data.index)[0] >= pd.DatetimeIndex(m5_data.index)[0]
        assert pd.DatetimeIndex(h1_data.index)[-1] <= pd.DatetimeIndex(m5_data.index)[-1]

    def test_h1_has_no_duplicate_timestamps(self, h1_data):
        assert not pd.DatetimeIndex(h1_data.index).has_duplicates

    def test_h1_ohlc_is_valid(self, h1_data):
        df = h1_data
        assert bool((df["high"] >= df["low"]).all())
        assert bool((df["high"] >= df[["open", "close"]].max(axis=1)).all())
        assert bool((df["low"] <= df[["open", "close"]].min(axis=1)).all())

    def test_h1_aggregates_the_m5_bars_correctly(self, m5_data, h1_data):
        """Spot check three hourly buckets against the M5 source bars."""
        idx = pd.DatetimeIndex(m5_data.index)
        for hour in ["2022-03-02 09:00", "2024-06-12 14:00", "2025-11-05 03:00"]:
            start = pd.Timestamp(hour, tz="UTC")
            if start not in idx:
                continue
            window = m5_data[(idx >= start) & (idx < start + pd.Timedelta(hours=1))]
            if window.empty or start not in pd.DatetimeIndex(h1_data.index):
                continue
            h1_bar = h1_data.loc[start]
            assert h1_bar["open"] == pytest.approx(window["open"].iloc[0])
            assert h1_bar["high"] == pytest.approx(window["high"].max())
            assert h1_bar["low"] == pytest.approx(window["low"].min())
            assert h1_bar["close"] == pytest.approx(window["close"].iloc[-1])

    def test_manifest_documents_the_raw_h1_grid_offset(self):
        manifest = json.loads((H1_PATH.parent / "_manifest.json").read_text(encoding="utf-8"))
        joined = " ".join(manifest["known_issues"])
        assert "grid" in joined.lower()
        assert "offset" in joined.lower()


class TestRawH1Provenance:
    def test_raw_h1_and_legacy_processed_h1_share_the_same_source(self):
        """The processed H1 v1.0.0 file is the SAME Exness series, extended."""
        raw = pd.read_parquet(ROOT / "data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet")
        proc = pd.read_parquet(ROOT / "data/processed/xauusd/h1/v1.0.0/data.parquet")
        raw = raw.assign(ts=pd.to_datetime(raw["time"], utc=True)).set_index("ts").sort_index()
        proc = proc.assign(ts=pd.to_datetime(proc["time"], utc=True)).set_index("ts").sort_index()
        common = raw.index.intersection(proc.index)
        assert len(common) == 63_239
        agreement = (raw.loc[common, "close"].round(6) == proc.loc[common, "close"].round(6)).mean()
        assert agreement == 1.0
        # The processed file only extends the raw coverage.
        assert pd.DatetimeIndex(proc.index)[-1] > pd.DatetimeIndex(raw.index)[-1]
