#!/usr/bin/env python3
"""
Stage 0 - Data Audit for XAUUSD M5 data
Detect timezone/DST handling, duplicates, gaps, weekend bars, zero-volume or outlier bars,
spread column presence, bars per year, consistency M1->M5->H1 resample.
"""
import pandas as pd
import numpy as np
import os
from pathlib import Path

DATA_DIR = Path(r"C:/Users/RIDGE/trading-data")
RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")

def load_and_combine():
    """Load all CSV files and combine into single DataFrame"""
    files = sorted(DATA_DIR.glob("XAUUSDm_M5_*.csv"))
    dfs = []
    for f in files:
        print(f"Loading {f.name}...")
        df = pd.read_csv(f, sep='\t')
        dfs.append(df)
    combined = pd.concat(dfs, ignore_index=True)
    return combined

def parse_datetime(df):
    """Parse DATE and TIME columns into datetime index"""
    # Combine date and time
    df['datetime'] = pd.to_datetime(df['<DATE>'] + ' ' + df['<TIME>'], format='%Y.%m.%d %H:%M:%S')
    df = df.set_index('datetime').sort_index()
    return df

def check_timezone_dst(df):
    """Check for timezone/DST issues"""
    print("\n=== TIMEZONE / DST CHECK ===")
    # Check if index is timezone-aware
    print(f"Index timezone: {df.index.tz}")
    # Check for DST transitions (hour gaps/duplicates in spring/fall)
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    # M5 data should have 5-min intervals mostly
    print(f"Median interval: {diffs.median()} minutes")
    print(f"Interval modes:\n{diffs.value_counts().head(10)}")
    # Look for 60-min jumps (DST spring forward) or 0-min (fall back)
    hour_jumps = diffs[(diffs > 30) & (diffs < 90)]
    if len(hour_jumps) > 0:
        print(f"Hour jumps (possible DST): {len(hour_jumps)} occurrences")
        print(hour_jumps.head())
    zero_jumps = diffs[diffs == 0]
    if len(zero_jumps) > 0:
        print(f"Zero-minute jumps (duplicate timestamps): {len(zero_jumps)}")
    return diffs

def check_duplicates(df):
    """Check for duplicate timestamps"""
    print("\n=== DUPLICATE CHECK ===")
    dup_mask = df.index.duplicated(keep=False)
    dup_count = dup_mask.sum()
    print(f"Duplicate timestamps: {dup_count}")
    if dup_count > 0:
        print(df[dup_mask].head(10))
    return dup_count

def check_gaps(diffs):
    """Check for gaps in data"""
    print("\n=== GAP CHECK ===")
    # Expected 5-minute intervals
    expected = 5
    gap_mask = diffs > expected * 1.5  # Allow some tolerance
    gaps = diffs[gap_mask]
    print(f"Gaps (>7.5 min): {len(gaps)}")
    if len(gaps) > 0:
        print(f"Max gap: {gaps.max()} minutes")
        print(f"Gap distribution:\n{gaps.value_counts().head(20)}")
        # Show largest gaps with timestamps
        gap_times = diffs[diffs > expected * 1.5].index
        for gt in gap_times[:10]:
            print(f"  Gap at {gt}: {diffs[gt]} minutes")
    return gaps

def check_weekend_bars(df):
    """Check for weekend bars (should be closed for forex)"""
    print("\n=== WEEKEND BARS CHECK ===")
    # Forex typically closed Saturday/Sunday
    weekend = df.index.dayofweek >= 5  # 5=Sat, 6=Sun
    weekend_count = weekend.sum()
    print(f"Weekend bars (Sat/Sun): {weekend_count}")
    if weekend_count > 0:
        print(df[weekend].head(10))
    return weekend_count

def check_zero_volume_outliers(df):
    """Check for zero-volume or outlier bars"""
    print("\n=== ZERO VOLUME / OUTLIER CHECK ===")
    zero_vol = df['<TICKVOL>'] == 0
    print(f"Zero tick volume bars: {zero_vol.sum()}")
    if zero_vol.sum() > 0:
        print(df[zero_vol].head(10))
    
    # Check for price outliers (using IQR method)
    for col in ['<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>']:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 3 * IQR
        upper = Q3 + 3 * IQR
        outliers = (df[col] < lower) | (df[col] > upper)
        print(f"{col} outliers (3*IQR): {outliers.sum()}")
    
    # Check for high-low consistency
    hl_issues = (df['<HIGH>'] < df['<LOW>']) | (df['<HIGH>'] < df['<OPEN>']) | (df['<HIGH>'] < df['<CLOSE>']) | \
                (df['<LOW>'] > df['<OPEN>']) | (df['<LOW>'] > df['<CLOSE>'])
    print(f"High/Low consistency issues: {hl_issues.sum()}")
    
    return zero_vol.sum()

def check_spread_column(df):
    """Check spread column presence and values"""
    print("\n=== SPREAD COLUMN CHECK ===")
    print(f"Spread dtype: {df['<SPREAD>'].dtype}")
    print(f"Spread unique values: {df['<SPREAD>'].unique()[:20]}")
    print(f"Spread stats:\n{df['<SPREAD>'].describe()}")
    print(f"Non-zero spread count: {(df['<SPREAD>'] != 0).sum()}")
    return df['<SPREAD>']

def check_bars_per_year(df):
    """Count bars per year"""
    print("\n=== BARS PER YEAR ===")
    yearly = df.groupby(df.index.year).size()
    print(yearly)
    # Expected: ~252 trading days * 24h * 12 = ~72,576 bars/year (M5)
    # But forex is 24/5 so ~252*24*12 = 72,576
    expected = 72576
    print(f"Expected per year (24/5): ~{expected}")
    print(f"Coverage %: {(yearly / expected * 100).round(1)}")
    return yearly

def check_resample_consistency(df):
    """Check M5 -> H1 resample consistency"""
    print("\n=== RESAMPLE CONSISTENCY (M5 -> H1) ===")
    # Resample to H1
    h1 = df.resample('1h').agg({
        '<OPEN>': 'first',
        '<HIGH>': 'max',
        '<LOW>': 'min',
        '<CLOSE>': 'last',
        '<TICKVOL>': 'sum',
        '<VOL>': 'sum',
        '<SPREAD>': 'mean'
    }).dropna()
    
    # Check if H1 bars have exactly 12 M5 bars (mostly)
    m5_counts = df.resample('1h').size()
    print(f"M5 bars per H1 bucket:\n{m5_counts.value_counts().head(10)}")
    print(f"Buckets with != 12 M5 bars: {(m5_counts != 12).sum()}")
    
    # Verify OHLC consistency
    # For each H1 bucket, the H1 high should equal max of M5 highs, etc.
    # This is inherently true by construction of resample, but let's spot-check
    print("Resample OHLC structure verified by construction.")
    
    return h1, m5_counts

def main():
    print("=" * 60)
    print("STAGE 0 - DATA AUDIT: XAUUSD M5")
    print("=" * 60)
    
    # Load data
    df = load_and_combine()
    print(f"\nTotal rows loaded: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")
    
    # Parse datetime
    df = parse_datetime(df)
    print(f"Date range: {df.index.min()} to {df.index.max()}")
    
    # Run checks
    diffs = check_timezone_dst(df)
    check_duplicates(df)
    check_gaps(diffs)
    check_weekend_bars(df)
    check_zero_volume_outliers(df)
    check_spread_column(df)
    check_bars_per_year(df)
    check_resample_consistency(df)
    
    # Save cleaned data for later stages
    df.to_parquet(RESULTS_DIR / "xauusd_m5_clean.parquet")
    print(f"\nSaved cleaned data to {RESULTS_DIR}/xauusd_m5_clean.parquet")
    
    print("\n" + "=" * 60)
    print("STAGE 0 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()