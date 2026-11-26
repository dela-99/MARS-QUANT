"""
Tests for M5 Data Loader - verifies M1 data loading and daily-bar exclusion.
"""

from pathlib import Path
import pytest


def test_load_verified_m1_excludes_daily_bars():
    from mars.apps.research_lab.m5_data_loader import load_verified_m1_m5_h1
    
    m1, m5, h1, meta = load_verified_m1_m5_h1(Path("C:/Users/RIDGE/MARS-QUANT"))
    
    # M1 should only have true 1-minute bars (2021-2026; 2020 is daily)
    assert len(m1) > 1_000_000  # ~1.68M true M1 bars
    assert meta["m1_daily_years"] == [2020]  # Only 2020 has daily bars
    assert meta["m1_true_start"].year == 2021
    assert meta["m1_true_end"].year == 2026
    
    # Verify interval consistency: all M1 intervals should be 60 seconds
    intervals = m1.index.to_series().diff().dt.total_seconds().dropna()
    true_m1_mask = intervals == 60
    assert true_m1_mask.mean() > 0.99  # >99% true 1-min intervals


def test_period_slices_chronological():
    from mars.apps.research_lab.m5_data_loader import load_verified_m1_m5_h1
    
    _, _, _, meta = load_verified_m1_m5_h1(Path("C:/Users/RIDGE/MARS-QUANT"))
    
    slices = meta["period_slices"]
    assert slices["dev_start"] < slices["dev_end"] <= slices["val_start"] < slices["val_end"] <= slices["holdout_start"] < slices["holdout_end"]
    
    # Dev: 2020-2023, Val: 2024-2025, Holdout: 2026
    assert slices["dev_start"].year == 2020
    assert slices["dev_end"].year == 2024
    assert slices["val_start"].year == 2024
    assert slices["val_end"].year == 2026
    assert slices["holdout_start"].year == 2026


def test_m5_and_h1_loaded():
    from mars.apps.research_lab.m5_data_loader import load_verified_m1_m5_h1
    
    m1, m5, h1, meta = load_verified_m1_m5_h1(Path("C:/Users/RIDGE/MARS-QUANT"))
    
    # M5 and H1 should be loaded from processed data
    assert len(m5) > 300_000  # ~370k M5 bars
    assert len(h1) > 30_000   # ~31k H1 bars
    
    # All should have UTC timezone
    assert m1.index.tz is not None
    assert m5.index.tz is not None
    assert h1.index.tz is not None


def test_execution_mode_metadata():
    from mars.apps.research_lab.m5_data_loader import load_verified_m1_m5_h1
    
    _, _, _, meta = load_verified_m1_m5_h1(Path("C:/Users/RIDGE/MARS-QUANT"))
    
    # Check execution mode mapping
    modes = meta["execution_mode"]
    assert modes["dev_2020"] == "M5"
    assert modes["dev_2021_2023"] == "M1"
    assert modes["val_2024_2025"] == "M1"
    assert modes["holdout_2026"] == "M1"