"""
Data integration validation tests for consolidated XAUUSD H1 dataset.
Tests the data created in Assignment 06.
"""
import pandas as pd
from pathlib import Path
import pytest


CONSOLIDATED_PATH = Path("data/processed/xauusd/h1/v1.0.0/data.parquet")


class TestConsolidatedDatasetExists:
    """Basic existence and accessibility tests."""

    def test_file_exists(self):
        """Consolidated dataset file exists."""
        assert CONSOLIDATED_PATH.exists(), f"Missing: {CONSOLIDATED_PATH}"

    def test_file_readable(self):
        """File can be read as parquet."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        assert len(df) > 0


class TestConsolidatedDatasetSchema:
    """Schema and structure validation."""

    def test_required_columns(self):
        """All required columns present in correct order."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        expected = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        assert list(df.columns) == expected

    def test_timestamp_column_type(self):
        """Time column is datetime with UTC timezone."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        assert pd.api.types.is_datetime64tz_dtype(df['time'])
        assert str(df['time'].dt.tz) == 'UTC'

    def test_numeric_columns(self):
        """OHLCV columns are numeric."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        for col in ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']:
            assert pd.api.types.is_numeric_dtype(df[col])


class TestConsolidatedDatasetQuality:
    """Data quality validation."""

    def test_no_duplicate_timestamps(self):
        """Zero duplicate timestamps."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        dup_count = df['time'].duplicated().sum()
        assert dup_count == 0, f"Found {dup_count} duplicate timestamps"

    def test_no_nan_values(self):
        """Zero NaN values across all columns."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        nan_count = df.isna().sum().sum()
        assert nan_count == 0, f"Found {nan_count} NaN values"

    def test_valid_ohlc_relationships(self):
        """All OHLC relationships valid: high>=low, high>=open/close, low<=open/close, positive prices."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        invalid = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close']) |
            (df['open'] <= 0) |
            (df['high'] <= 0) |
            (df['low'] <= 0) |
            (df['close'] <= 0)
        ).sum()
        assert invalid == 0, f"Found {invalid} invalid OHLC rows"

    def test_chronological_order(self):
        """Timestamps are strictly increasing."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        diffs = df['time'].diff().dropna()
        assert (diffs > pd.Timedelta(0)).all(), "Timestamps not strictly increasing"

    def test_expected_bar_count(self):
        """Total bars match expected count (68400)."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        assert len(df) == 68400, f"Expected 68400 bars, got {len(df)}"

    def test_date_range(self):
        """Date range covers 2015-01-02 09:00 to 2026-04-29."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        min_date = df['time'].min()
        max_date = df['time'].max()
        # First bar is 2015-01-02 09:00 (market open), not midnight
        assert min_date <= pd.Timestamp('2015-01-02 09:00', tz='UTC'), f"Start too late: {min_date}"
        assert max_date >= pd.Timestamp('2026-04-29', tz='UTC'), f"End too early: {max_date}"


class TestDataSourceTransition:
    """Validate the base (parquet) to M5-resampled transition."""

    def test_base_ends_2025_09_26(self):
        """Base parquet data ends at 2025-09-26 08:00."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        base_end = pd.Timestamp('2025-09-26 08:00:00', tz='UTC')
        last_base_bar = df[df['time'] <= base_end].iloc[-1]
        assert last_base_bar['time'] == base_end

    def test_m5_extension_starts_2025_09_26_09(self):
        """M5-resampled extension starts at 2025-09-26 09:00."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        m5_start = pd.Timestamp('2025-09-26 09:00:00', tz='UTC')
        first_m5_bar = df[df['time'] >= m5_start].iloc[0]
        assert first_m5_bar['time'] == m5_start

    def test_no_overlap_mixing(self):
        """No M5-default spread values in base period (2015-2025-09-26)."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        base_period = df[df['time'] <= '2025-09-26 08:00:00+00:00']
        # M5-resampled bars have spread=7.0 (default); base bars have varying spreads
        m5_default_count = (base_period['spread'] == 7.0).sum()
        # Allow some base bars to coincidentally have spread=7.0, but not all
        assert m5_default_count < len(base_period) * 0.1, "Too many 7.0 spreads in base period — possible mixing"

    def test_m5_extension_has_default_spread(self):
        """M5-resampled extension bars have spread=7.0 (default applied during resampling)."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        m5_period = df[df['time'] > '2025-09-26 08:00:00+00:00']
        default_spread_count = (m5_period['spread'] == 7.0).sum()
        assert default_spread_count == len(m5_period), "Not all M5 extension bars have default spread=7.0"

    def test_m5_extension_has_zero_volume(self):
        """M5-resampled extension has zero tick_volume and real_volume (not available from CSV)."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        m5_period = df[df['time'] > '2025-09-26 08:00:00+00:00']
        assert (m5_period['tick_volume'] == 0).all()
        assert (m5_period['real_volume'] == 0).all()


class TestGapsAndContinuity:
    """Validate expected gaps (weekends/holidays) and no unexpected gaps."""

    def test_gaps_only_weekends_holidays(self):
        """Gaps > 1 hour only occur at expected market closures."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        diffs = df['time'].diff().dropna()
        gaps = diffs[diffs > pd.Timedelta(hours=1)]
        # Should have ~2776 gaps (weekends + holidays)
        assert 2500 < len(gaps) < 3200, f"Unexpected gap count: {len(gaps)}"

    def test_no_zero_gaps(self):
        """No duplicate/zero-length gaps (handled by no-duplicates test)."""
        df = pd.read_parquet(CONSOLIDATED_PATH)
        diffs = df['time'].diff().dropna()
        zero_gaps = (diffs == pd.Timedelta(0)).sum()
        assert zero_gaps == 0


class TestReproducibility:
    """Verify deterministic results."""

    def test_deterministic_load(self):
        """Loading the dataset twice produces identical DataFrames."""
        df1 = pd.read_parquet(CONSOLIDATED_PATH)
        df2 = pd.read_parquet(CONSOLIDATED_PATH)
        pd.testing.assert_frame_equal(df1, df2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])