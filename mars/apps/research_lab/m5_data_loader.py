"""
Verified M1/M5/H1 Data Loader for M5 Strategy Research.

Loads and verifies true M1 bars (2022-2026 only), excludes daily-bar years (2020-2021),
and provides M5/H1 from processed parquet. Returns execution mode metadata.
"""

from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
import numpy as np

from mars.libs.data.loaders import load_ohlcv_parquet

TRADING_DATA_DIR = Path("C:/Users/RIDGE/trading-data")

M1_FILES = {
    2020: "XAUUSDm_M1_202001020000_202012310000.csv",
    2021: "XAUUSDm_M1_202101030000_202112310000.csv",
    2022: "XAUUSDm_M1_202201022305_202212302157.csv",
    2023: "XAUUSDm_M1_202301022301_202312292157.csv",
    2024: "XAUUSDm_M1_202401012305_202412310000.csv",
    2025: "XAUUSDm_M1_202501012305_202512310000.csv",
    2026: "XAUUSDm_M1_202601012305_202610092057.csv",
}


def _load_m1_csv(path: Path) -> pd.DataFrame:
    """Load single M1 CSV, normalize columns, parse timestamps."""
    df = pd.read_csv(path, sep="\t", header=0)
    df.columns = ["date", "time", "open", "high", "low", "close", "tick_volume", "volume", "spread"]
    df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[["open", "high", "low", "close", "tick_volume", "volume", "spread"]]
    df.columns = ["open", "high", "low", "close", "volume", "real_volume", "spread"]
    return df


def _is_true_m1(df: pd.DataFrame) -> pd.Series:
    """Return boolean mask for true 1-minute intervals."""
    intervals = df.index.to_series().diff().dt.total_seconds()
    return intervals == 60


def load_verified_m1_m5_h1(repo_root: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Load and verify M1, M5, H1 data with coverage metadata."""
    # Load M1 files
    m1_frames = []
    daily_years = []
    for year, fname in M1_FILES.items():
        path = TRADING_DATA_DIR / fname
        if not path.exists():
            continue
        df = _load_m1_csv(path)
        mask = _is_true_m1(df)
        true_bars = int(mask.sum())
        total_bars = len(df)
        if true_bars / max(total_bars, 1) < 0.5:
            daily_years.append(year)
            continue  # Skip daily-bar years
        m1_frames.append(df[mask])
    
    m1 = pd.concat(m1_frames).sort_index() if m1_frames else pd.DataFrame()
    
    # Load M5 and H1 from processed
    m5 = load_ohlcv_parquet(repo_root / "data/processed/xauusdm/m5/v1.2.0/data.parquet")
    h1 = load_ohlcv_parquet(repo_root / "data/processed/xauusdm/h1/v1.2.0/data.parquet")
    
    # Convert to timestamp-indexed DataFrames
    if "timestamp" in m5.columns:
        m5 = m5.set_index("timestamp")
    if m5.index.tz is None:
        m5.index = m5.index.tz_localize("UTC")
    else:
        m5.index = m5.index.tz_convert("UTC")
    
    if "timestamp" in h1.columns:
        h1 = h1.set_index("timestamp")
    if h1.index.tz is None:
        h1.index = h1.index.tz_localize("UTC")
    else:
        h1.index = h1.index.tz_convert("UTC")
    
    # Ensure M1 has UTC index
    if len(m1) and m1.index.tz is None:
        m1.index = m1.index.tz_localize("UTC")
    elif len(m1):
        m1.index = m1.index.tz_convert("UTC")
    
    # Coverage metadata
    m1_true_start = m1.index[0] if len(m1) else None
    m1_true_end = m1.index[-1] if len(m1) else None
    
    # Period slices
    dev_start = pd.Timestamp("2020-01-01", tz="UTC")
    dev_end = pd.Timestamp("2024-01-01", tz="UTC")
    val_start = pd.Timestamp("2024-01-01", tz="UTC")
    val_end = pd.Timestamp("2026-01-01", tz="UTC")
    holdout_start = pd.Timestamp("2026-01-01", tz="UTC")
    holdout_end = pd.Timestamp("2026-12-31", tz="UTC")
    
    coverage = {
        "m1_true_start": m1_true_start,
        "m1_true_end": m1_true_end,
        "m1_daily_years": daily_years,
        "m1_total_bars": len(m1),
        "period_slices": {
            "dev_start": dev_start, "dev_end": dev_end,
            "val_start": val_start, "val_end": val_end,
            "holdout_start": holdout_start, "holdout_end": holdout_end,
        },
        "execution_mode": {
            "dev_2020": "M5",       # M1 is daily bars
            "dev_2021_2023": "M1",  # M1 is true
            "val_2024_2025": "M1",
            "holdout_2026": "M1",
        }
    }
    
    return m1, m5, h1, coverage


__all__ = ["load_verified_m1_m5_h1"]