"""Tests for raw data consolidation and integrity."""

import pytest
import pandas as pd
import hashlib
from pathlib import Path


class TestRawConsolidation:
    """Test Exness M5 raw file consolidation."""

    def test_all_source_files_exist(self):
        """Verify all 7 source files exist."""
        base = Path(r"C:\Users\RIDGE\trading-data")
        expected_files = [
            "XAUUSDm_M5_2020_1_12.csv",
            "XAUUSDm_M5_2021 jan to dec.csv",
            "XAUUSDm_M5_2022 jan to dec.csv",
            "XAUUSDm_M5_2023 jan to dec.csv",
            "XAUUSDm_M5_2024 jan to feb.csv",
            "XAUUSDm_M5_2025 jan to dec.csv",
            "XAUUSDm_M5_2026 jan to oct.csv",
        ]
        for f in expected_files:
            assert (base / f).exists(), f"Missing source file: {f}"

    def test_consolidated_raw_exists(self):
        """Verify consolidated raw file was created."""
        consolidated = Path("data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv")
        assert consolidated.exists(), "Consolidated raw file not created"

    def test_consolidated_row_count_matches_sum(self):
        """Consolidated rows should equal sum of source rows."""
        base = Path(r"C:\Users\RIDGE\trading-data")
        source_files = sorted(base.glob("XAUUSDm_M5_*.csv"))

        total_source_rows = 0
        for f in source_files:
            df = pd.read_csv(f, sep="\t")
            total_source_rows += len(df)

        consolidated = pd.read_csv(
            "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv", sep="\t"
        )
        assert len(consolidated) == total_source_rows, (
            f"Row count mismatch: consolidated={len(consolidated)}, "
            f"sources sum={total_source_rows}"
        )

    def test_no_duplicate_timestamps_in_consolidated(self):
        """Consolidated data should have zero duplicate timestamps."""
        df = pd.read_csv(
            "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv", sep="\t"
        )
        df["timestamp"] = pd.to_datetime(
            df["<DATE>"] + " " + df["<TIME>"], format="%Y.%m.%d %H:%M:%S"
        )
        dup_count = df["timestamp"].duplicated().sum()
        assert dup_count == 0, f"Found {dup_count} duplicate timestamps in consolidated data"

    def test_chronological_ordering(self):
        """Consolidated data should be chronologically ordered."""
        df = pd.read_csv(
            "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv", sep="\t"
        )
        df["timestamp"] = pd.to_datetime(
            df["<DATE>"] + " " + df["<TIME>"], format="%Y.%m.%d %H:%M:%S"
        )
        assert df["timestamp"].is_monotonic_increasing, "Data not chronologically ordered"

    def test_checksum_matches_catalog(self):
        """Consolidated file checksum should match catalog."""
        with open(
            "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv", "rb"
        ) as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        expected = "2175c0fcf6fc119a6700efe73fb8caec4ba2a4c839ec05895d6ec388b5a4dc4e"
        assert checksum == expected, f"Checksum mismatch: {checksum} != {expected}"

    def test_source_checksums_match_catalog(self):
        """Individual source file checksums should match catalog."""
        expected_checksums = {
            "XAUUSDm_M5_2020_1_12.csv": "d4cf24bcc9939e74043d1b22f79ff4f9bdda37e03ca15342103ac79f713d915c",
            "XAUUSDm_M5_2021 jan to dec.csv": "3a8cf30a2414aa8ddfef447539e608d3525f341d851341380b429313e81f868e",
            "XAUUSDm_M5_2022 jan to dec.csv": "b6df6a993b11e8a146ce1ca2cf4699c405328d54306990f572c37b4573eee67f",
            "XAUUSDm_M5_2023 jan to dec.csv": "680c52bb643d2bea3cdd56b2c702b9b97902f12ef0d234718a27f19ae0c437de",
            "XAUUSDm_M5_2024 jan to feb.csv": "b9643df616478c69ecf27c727b1010b95c5834aded3a2ed2a847383a5ea5a5a7",
            "XAUUSDm_M5_2025 jan to dec.csv": "e6c3db4f50f3580ccbf2a23c7291ad88cbd1563ee781966d2f4df56abb2c85f9",
            "XAUUSDm_M5_2026 jan to oct.csv": "a036c2759011a40959119fff7e56f3f75a74705f4151fcf89455181e045783f6",
        }
        base = Path(r"C:\Users\RIDGE\trading-data")
        for fname, expected in expected_checksums.items():
            fpath = base / fname
            with open(fpath, "rb") as f:
                actual = hashlib.sha256(f.read()).hexdigest()
            assert actual == expected, f"Checksum mismatch for {fname}: {actual} != {expected}"

    def test_preserved_spread_and_tickvol(self):
        """Consolidated data should preserve spread and tick_volume columns."""
        df = pd.read_csv(
            "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv", sep="\t"
        )
        assert "<SPREAD>" in df.columns, "Spread column missing"
        assert "<TICKVOL>" in df.columns, "Tick volume column missing"
        assert "<VOL>" in df.columns, "Volume column missing"

    def test_2020_daily_bars_documented(self):
        """2020 data should have daily intervals (86400s) with spread=0."""
        df = pd.read_csv(
            "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv", sep="\t"
        )
        df["timestamp"] = pd.to_datetime(
            df["<DATE>"] + " " + df["<TIME>"], format="%Y.%m.%d %H:%M:%S"
        )
        df = df.sort_values("timestamp")
        df["diff"] = df["timestamp"].diff().dt.total_seconds()

        # 2020 data should be at the start
        df_2020 = df[df["timestamp"].dt.year == 2020]
        assert len(df_2020) == 311, f"Expected 311 rows for 2020, got {len(df_2020)}"

        # Check intervals are daily (86400s) or multiples
        intervals_2020 = df_2020["diff"].dropna().unique()
        for interval in intervals_2020:
            assert interval % 86400 == 0, f"2020 interval {interval} not multiple of daily"

        # Spread should be 0 for 2020
        assert (df_2020["<SPREAD>"] == 0).all(), "2020 spread should be all zeros"


class TestDatasetIntegrity:
    """Test processed dataset integrity."""

    def test_m5_v110_integrity(self):
        """Test M5 v1.1.0 processed dataset."""
        df = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")

        # Basic structure
        assert len(df) == 370450, f"Expected 370450 rows, got {len(df)}"
        assert isinstance(df.index, pd.DatetimeIndex), "Index should be DatetimeIndex"
        assert df.index.tz is not None, "Index should be timezone-aware"
        assert str(df.index.tz) == "UTC", "Index should be UTC"

        # Columns
        expected_cols = ["open", "high", "low", "close", "tick_volume", "volume", "spread"]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

        # OHLC integrity
        assert (df["high"] >= df["low"]).all(), "OHLC violation: high < low"
        assert (df["high"] >= df["open"]).all(), "OHLC violation: high < open"
        assert (df["high"] >= df["close"]).all(), "OHLC violation: high < close"
        assert (df["low"] <= df["open"]).all(), "OHLC violation: low > open"
        assert (df["low"] <= df["close"]).all(), "OHLC violation: low > close"
        assert (df[["open", "high", "low", "close"]] > 0).all().all(), "Zero/negative prices found"

        # No duplicates
        assert df.index.duplicated().sum() == 0, "Duplicate timestamps in processed data"

        # Monotonic index
        assert df.index.is_monotonic_increasing, "Index not monotonic"

    def test_h1_v110_integrity(self):
        """Test H1 v1.1.0 processed dataset."""
        df = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        assert len(df) == 31376, f"Expected 31376 rows, got {len(df)}"
        assert isinstance(df.index, pd.DatetimeIndex), "Index should be DatetimeIndex"
        assert df.index.tz is not None and str(df.index.tz) == "UTC", "Index should be UTC"

        expected_cols = ["open", "high", "low", "close", "tick_volume", "volume", "spread"]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

        # OHLC integrity
        assert (df["high"] >= df["low"]).all(), "OHLC violation: high < low"
        assert (df[["open", "high", "low", "close"]] > 0).all().all(), "Zero/negative prices"

        # No duplicates
        assert df.index.duplicated().sum() == 0, "Duplicate timestamps"

    def test_m15_v100_integrity(self):
        """Test M15 v1.0.0 processed dataset."""
        df = pd.read_parquet("data/processed/xauusdm/m15/v1.0.0/data.parquet")
        assert len(df) == 123906
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.tz is not None and str(df.index.tz) == "UTC"
        assert (df["high"] >= df["low"]).all()
        assert df.index.duplicated().sum() == 0

    def test_m30_v100_integrity(self):
        """Test M30 v1.0.0 processed dataset."""
        df = pd.read_parquet("data/processed/xauusdm/m30/v1.0.0/data.parquet")
        assert len(df) == 62219
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.tz is not None and str(df.index.tz) == "UTC"
        assert (df["high"] >= df["low"]).all()
        assert df.index.duplicated().sum() == 0


class TestDuplicateDetection:
    """Test duplicate detection in raw H1 files."""

    def test_raw_h1_duplicates_count(self):
        """Verify 83,751 duplicates across 4 overlapping H1 files."""
        raw_files = [
            "data/raw/xauusd_h1_2015_present.parquet",
            "data/raw/xauusd_h1_2018_present.parquet",
            "data/raw/xauusd_h1_2020_present.parquet",
            "data/raw/xauusd_h1_2025_present.parquet",
        ]

        all_dfs = []
        for f in raw_files:
            df = pd.read_parquet(f)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            all_dfs.append(df)

        combined = pd.concat(all_dfs)
        dup_count = combined["time"].duplicated().sum()
        assert dup_count == 83751, f"Expected 83751 duplicates, got {dup_count}"

    def test_deduplicated_h1_no_duplicates(self):
        """Deduplicated H1 should have zero duplicates."""
        df = pd.read_parquet("data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        dup_count = df["time"].duplicated().sum()
        assert dup_count == 0, f"Deduplicated H1 has {dup_count} duplicates"

    def test_deduplicated_h1_row_count(self):
        """Deduplicated H1 should have 63,239 rows (same as 2015 file)."""
        df = pd.read_parquet("data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet")
        assert len(df) == 63239, f"Expected 63239 rows, got {len(df)}"


class TestH1SourceReconciliation:
    """Test H1 source reconciliation."""

    def test_raw_h1_2015_is_base(self):
        """2015 file should have the longest coverage."""
        df_2015 = pd.read_parquet("data/raw/xauusd_h1_2015_present.parquet")
        df_2015["time"] = pd.to_datetime(df_2015["time"], unit="s", utc=True)

        df_2018 = pd.read_parquet("data/raw/xauusd_h1_2018_present.parquet")
        df_2018["time"] = pd.to_datetime(df_2018["time"], unit="s", utc=True)

        df_2020 = pd.read_parquet("data/raw/xauusd_h1_2020_present.parquet")
        df_2020["time"] = pd.to_datetime(df_2020["time"], unit="s", utc=True)

        df_2025 = pd.read_parquet("data/raw/xauusd_h1_2025_present.parquet")
        df_2025["time"] = pd.to_datetime(df_2025["time"], unit="s", utc=True)

        # 2015 should start earliest
        assert df_2015["time"].min() <= df_2018["time"].min()
        assert df_2015["time"].min() <= df_2020["time"].min()
        assert df_2015["time"].min() <= df_2025["time"].min()

        # 2015 should end latest (or close to it)
        assert df_2015["time"].max() >= df_2018["time"].max() - pd.Timedelta(days=30)
        assert df_2015["time"].max() >= df_2020["time"].max() - pd.Timedelta(days=30)
        assert df_2015["time"].max() >= df_2025["time"].max() - pd.Timedelta(days=30)

    def test_processed_h1_v110_extends_beyond_raw(self):
        """Processed H1 v1.1.0 should extend beyond raw H1 (resampled from M5)."""
        raw_h1 = pd.read_parquet("data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet")
        raw_h1["time"] = pd.to_datetime(raw_h1["time"], utc=True)

        proc_h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        assert proc_h1.index.max() > raw_h1["time"].max(), (
            "Processed H1 should extend beyond raw H1 "
            f"(proc: {proc_h1.index.max()}, raw: {raw_h1['time'].max()})"
        )

    def test_processed_h1_v110_resampled_from_m5(self):
        """Processed H1 v1.1.0 should be resampled from M5 v1.1.0."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        # H1 date range should match M5 (resampled)
        assert h1.index.min() == m5.index.min().floor("h"), "H1 start should match M5 start floored to hour"
        assert h1.index.max() <= m5.index.max().floor("h"), "H1 end should not exceed M5 end"


class TestM5ToH1Aggregation:
    """Test M5 to H1 resampling correctness."""

    def test_h1_open_is_first_m5_open(self):
        """H1 open should equal first M5 open in the hour."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        # Check a sample hour
        sample_hour = h1.index[1000]
        m5_in_hour = m5[
            (m5.index >= sample_hour) & (m5.index < sample_hour + pd.Timedelta(hours=1))
        ]
        if len(m5_in_hour) > 0:
            assert h1.loc[sample_hour, "open"] == m5_in_hour["open"].iloc[0]

    def test_h1_high_is_max_m5_high(self):
        """H1 high should equal max M5 high in the hour."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        sample_hour = h1.index[2000]
        m5_in_hour = m5[
            (m5.index >= sample_hour) & (m5.index < sample_hour + pd.Timedelta(hours=1))
        ]
        if len(m5_in_hour) > 0:
            assert h1.loc[sample_hour, "high"] == m5_in_hour["high"].max()

    def test_h1_low_is_min_m5_low(self):
        """H1 low should equal min M5 low in the hour."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        sample_hour = h1.index[3000]
        m5_in_hour = m5[
            (m5.index >= sample_hour) & (m5.index < sample_hour + pd.Timedelta(hours=1))
        ]
        if len(m5_in_hour) > 0:
            assert h1.loc[sample_hour, "low"] == m5_in_hour["low"].min()

    def test_h1_close_is_last_m5_close(self):
        """H1 close should equal last M5 close in the hour."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        sample_hour = h1.index[4000]
        m5_in_hour = m5[
            (m5.index >= sample_hour) & (m5.index < sample_hour + pd.Timedelta(hours=1))
        ]
        if len(m5_in_hour) > 0:
            assert h1.loc[sample_hour, "close"] == m5_in_hour["close"].iloc[-1]

    def test_h1_volume_is_sum_m5_volume(self):
        """H1 volume should equal sum of M5 volumes in the hour."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        sample_hour = h1.index[5000]
        m5_in_hour = m5[
            (m5.index >= sample_hour) & (m5.index < sample_hour + pd.Timedelta(hours=1))
        ]
        if len(m5_in_hour) > 0:
            assert h1.loc[sample_hour, "volume"] == m5_in_hour["volume"].sum()

    def test_h1_spread_is_mean_m5_spread(self):
        """H1 spread should equal mean of M5 spreads in the hour."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        sample_hour = h1.index[6000]
        m5_in_hour = m5[
            (m5.index >= sample_hour) & (m5.index < sample_hour + pd.Timedelta(hours=1))
        ]
        if len(m5_in_hour) > 0:
            expected = m5_in_hour["spread"].mean()
            actual = h1.loc[sample_hour, "spread"]
            assert abs(actual - expected) < 0.01, f"Spread mismatch: {actual} != {expected}"


class TestMTFSynchronization:
    """Test MTF timeframe synchronization."""

    def test_m15_from_m5_resampling(self):
        """M15 should be correctly resampled from M5."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        m15 = pd.read_parquet("data/processed/xauusdm/m15/v1.0.0/data.parquet")

        sample_period = m15.index[1000]
        m5_in_period = m5[
            (m5.index >= sample_period) & (m5.index < sample_period + pd.Timedelta(minutes=15))
        ]
        if len(m5_in_period) > 0:
            assert m15.loc[sample_period, "open"] == m5_in_period["open"].iloc[0]
            assert m15.loc[sample_period, "high"] == m5_in_period["high"].max()
            assert m15.loc[sample_period, "low"] == m5_in_period["low"].min()
            assert m15.loc[sample_period, "close"] == m5_in_period["close"].iloc[-1]

    def test_m30_from_m15_resampling(self):
        """M30 should be correctly resampled from M15."""
        m15 = pd.read_parquet("data/processed/xauusdm/m15/v1.0.0/data.parquet")
        m30 = pd.read_parquet("data/processed/xauusdm/m30/v1.0.0/data.parquet")

        sample_period = m30.index[500]
        m15_in_period = m15[
            (m15.index >= sample_period) & (m15.index < sample_period + pd.Timedelta(minutes=30))
        ]
        if len(m15_in_period) > 0:
            assert m30.loc[sample_period, "open"] == m15_in_period["open"].iloc[0]
            assert m30.loc[sample_period, "high"] == m15_in_period["high"].max()
            assert m30.loc[sample_period, "low"] == m15_in_period["low"].min()
            assert m30.loc[sample_period, "close"] == m15_in_period["close"].iloc[-1]

    def test_h1_from_m30_resampling_chain(self):
        """H1 should be consistent with M5->M15->M30->H1 chain."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        h1_direct = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")

        # Resample M5->M15->M30->H1
        m15 = m5.resample("15min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last",
            "tick_volume": "sum", "volume": "sum", "spread": "mean"
        }).dropna()
        m30 = m15.resample("30min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last",
            "tick_volume": "sum", "volume": "sum", "spread": "mean"
        }).dropna()
        h1_chain = m30.resample("h").agg({
            "open": "first", "high": "max", "low": "min", "close": "last",
            "tick_volume": "sum", "volume": "sum", "spread": "mean"
        }).dropna()

        # Compare a sample
        common_idx = h1_direct.index.intersection(h1_chain.index)
        if len(common_idx) > 0:
            sample = common_idx[100]
            for col in ["open", "high", "low", "close"]:
                assert abs(h1_direct.loc[sample, col] - h1_chain.loc[sample, col]) < 0.01, (
                    f"Chain mismatch at {sample} for {col}: "
                    f"direct={h1_direct.loc[sample, col]}, chain={h1_chain.loc[sample, col]}"
                )


class TestCandleCompletion:
    """Test candle completion rules (no forming bars)."""

    def test_m5_last_bar_is_complete(self):
        """Last M5 bar should be complete (not forming)."""
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        # Last bar timestamp should be at a 5-minute boundary
        last_ts = m5.index[-1]
        assert last_ts.minute % 5 == 0, "Last M5 bar not at 5-minute boundary"
        assert last_ts.second == 0, "Last M5 bar has non-zero seconds"

    def test_h1_last_bar_is_complete(self):
        """Last H1 bar should be complete."""
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")
        last_ts = h1.index[-1]
        assert last_ts.minute == 0, "Last H1 bar not at hour boundary"
        assert last_ts.second == 0, "Last H1 bar has non-zero seconds"

    def test_m15_last_bar_is_complete(self):
        """Last M15 bar should be complete."""
        m15 = pd.read_parquet("data/processed/xauusdm/m15/v1.0.0/data.parquet")
        last_ts = m15.index[-1]
        assert last_ts.minute % 15 == 0, "Last M15 bar not at 15-minute boundary"
        assert last_ts.second == 0

    def test_m30_last_bar_is_complete(self):
        """Last M30 bar should be complete."""
        m30 = pd.read_parquet("data/processed/xauusdm/m30/v1.0.0/data.parquet")
        last_ts = m30.index[-1]
        assert last_ts.minute % 30 == 0, "Last M30 bar not at 30-minute boundary"
        assert last_ts.second == 0


class TestLookaheadProtection:
    """Test no look-ahead bias in data."""

    def test_no_future_data_in_m5(self):
        """M5 data should not contain future data relative to source."""
        # The consolidated raw data ends at 2026-10-09 20:55:00
        # Processed should not extend beyond this
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        assert m5.index.max() <= pd.Timestamp("2026-10-09 20:55:00", tz="UTC")

    def test_no_future_data_in_h1(self):
        """H1 data should not contain future data."""
        h1 = pd.read_parquet("data/processed/xauusdm/h1/v1.1.0/data.parquet")
        # H1 resampled from M5, so last bar should be at or before M5 last bar floored to hour
        m5 = pd.read_parquet("data/processed/xauusdm/m5/v1.1.0/data.parquet")
        max_h1_from_m5 = m5.index.max().floor("h")
        assert h1.index.max() <= max_h1_from_m5

    def test_mtf_gate_excludes_forming_bar(self):
        """MTF gate should exclude forming (current) bar from analysis."""
        # This is verified by code inspection of mtf_gate.py:
        # classify_trend_bias uses df['close'].iloc[:-1] (excludes last bar)
        # check_execution_context uses df['spread'].iloc[:-1] and atr.iloc[:-1]
        # This test documents the requirement
        import inspect
        from mars.apps.trading.signals.mtf_gate import MTFGate

        source = inspect.getsource(MTFGate.classify_trend_bias)
        assert "iloc[:-1]" in source, "classify_trend_bias should exclude forming bar"

        source2 = inspect.getsource(MTFGate.check_execution_context)
        assert "iloc[:-1]" in source2, "check_execution_context should exclude forming bar"


class TestCatalogLoading:
    """Test catalogue loading and checksum verification."""

    def test_catalog_exists(self):
        """Catalog file should exist."""
        assert Path("data/catalog.yaml").exists(), "Catalog file not found"

    def test_catalog_loads(self):
        """Catalog should load as valid YAML."""
        import yaml
        with open("data/catalog.yaml") as f:
            catalog = yaml.safe_load(f)
        assert catalog is not None
        assert "datasets" in catalog
        assert "catalog_version" in catalog

    def test_catalog_has_active_instrument(self):
        """Catalog should specify active instrument."""
        import yaml
        with open("data/catalog.yaml") as f:
            catalog = yaml.safe_load(f)
        assert catalog["active_instrument"] == "XAUUSDm"

    def test_catalog_has_mtf_requirements(self):
        """Catalog should document MTF requirements."""
        import yaml
        with open("data/catalog.yaml") as f:
            catalog = yaml.safe_load(f)
        assert "mtf_requirements" in catalog
        assert "active_timeframes" in catalog["mtf_requirements"]
        assert catalog["mtf_requirements"]["active_timeframes"] == ["1H", "30M", "15M", "5M"]

    def test_catalog_checksums_match_files(self):
        """Catalog checksums should match actual files."""
        import yaml
        with open("data/catalog.yaml") as f:
            catalog = yaml.safe_load(f)

        for ds in catalog["datasets"]:
            if "path" in ds and "checksum_sha256" in ds:
                path = Path(ds["path"])
                if path.exists():
                    with open(path, "rb") as f:
                        actual = hashlib.sha256(f.read()).hexdigest()
                    expected = ds["checksum_sha256"]
                    assert actual == expected, (
                        f"Checksum mismatch for {ds['id']}: {actual} != {expected}"
                    )

    def test_catalog_lineage_chain(self):
        """Catalog should document transformation lineage."""
        import yaml
        with open("data/catalog.yaml") as f:
            catalog = yaml.safe_load(f)

        # Find M5 v1.1.0
        m5_v110 = next(d for d in catalog["datasets"] if d["id"] == "xauusdm_m5_v1.1.0")
        assert "lineage" in m5_v110
        assert "transformations" in m5_v110

        # Find H1 v1.1.0
        h1_v110 = next(d for d in catalog["datasets"] if d["id"] == "xauusdm_h1_v1.1.0")
        assert "lineage" in h1_v110
        assert "source_checksum" in h1_v110
        assert h1_v110["source_checksum"] == m5_v110["checksum_sha256"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])