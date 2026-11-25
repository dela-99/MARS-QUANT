"""Assignment 14 — Phase B: measure the raw-H1 vs M5-derived-H1 time-grid offset.

The raw Exness H1 export and the M5 CSV export appear to label bars on different
hour grids. Find the lag (in hours) that maximises close-price agreement, and
report the residual dispersion so the offset is quantified rather than assumed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\RIDGE\MARS-QUANT")


def main() -> None:
    raw = pd.read_parquet(ROOT / "data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet")
    raw["ts"] = pd.to_datetime(raw["time"], utc=True)
    raw = raw.set_index("ts").sort_index()

    m5 = pd.read_parquet(ROOT / "data/processed/xauusdm/m5/v1.1.0/data.parquet")
    m5.index = pd.DatetimeIndex(m5.index).tz_convert("UTC")
    m5 = m5.sort_index()
    # Keep only true M5 rows: exclude the embedded daily block
    gap = m5.index.to_series().diff().dt.total_seconds()
    m5_ok = m5[(gap.isna()) | (gap == 300)]
    h1 = m5_ok.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last",
         "tick_volume": "sum"}).dropna(subset=["close"])

    print(f"raw H1 : {len(raw):>7} rows  {raw.index.min()} -> {raw.index.max()}")
    print(f"m5->H1 : {len(h1):>7} rows  {h1.index.min()} -> {h1.index.max()}")

    print("\n--- lag scan: raw H1 shifted by k hours vs M5-derived H1 ---")
    print(f"{'lag_h':>6} {'n_overlap':>9} {'close_exact%':>13} {'median_abs_diff':>17} {'mean_abs_diff':>15}")
    best = None
    for lag in range(-6, 7):
        shifted = raw.copy()
        shifted.index = shifted.index + pd.Timedelta(hours=lag)
        common = shifted.index.intersection(h1.index)
        if len(common) < 100:
            print(f"{lag:>6} {len(common):>9}  (too few)")
            continue
        a = shifted.loc[common, "close"].to_numpy()
        b = h1.loc[common, "close"].to_numpy()
        exact = float((a == b).mean())
        diff = abs(a - b)
        med = float(pd.Series(diff).median())
        mean = float(pd.Series(diff).mean())
        print(f"{lag:>6} {len(common):>9} {exact:>12.4%} {med:>17.4f} {mean:>15.4f}")
        if best is None or exact > best[1]:
            best = (lag, exact, med, mean, len(common))
    print(f"\n  BEST: lag={best[0]}h  exact_close_match={best[1]:.4%}  "
          f"median|diff|=${best[2]:.4f}  mean|diff|=${best[3]:.4f}  n={best[4]}")

    # Hour-of-day grid comparison
    print("\n--- hour-of-day bar counts (raw H1 vs M5-derived H1) ---")
    rh = raw.index.hour.value_counts().sort_index()
    mh = h1.index.hour.value_counts().sort_index()
    print(f"  hour : raw_H1_days   m5_H1_days")
    for h in range(24):
        print(f"   {h:>2}  : {int(rh.get(h,0)):>10}  {int(mh.get(h,0)):>10}")

    # Do the two series overlap in *price path* at all? correlation of returns
    common = raw.index.intersection(h1.index)
    a = raw.loc[common, "close"]
    b = h1.loc[common, "close"]
    ra = a.pct_change().dropna()
    rb = b.pct_change().dropna()
    j = pd.concat([ra, rb], axis=1).dropna()
    j.columns = ["raw", "m5"]
    print(f"\n  same-timestamp return correlation: {j['raw'].corr(j['m5']):.6f}  (n={len(j)})")
    shifted_h1 = h1.copy()
    shifted_h1.index = shifted_h1.index + pd.Timedelta(hours=best[0])
    common2 = raw.index.intersection(shifted_h1.index)
    a2 = raw.loc[common2, "close"].pct_change().dropna()
    b2 = shifted_h1.loc[common2, "close"].pct_change().dropna()
    j2 = pd.concat([a2, b2], axis=1).dropna()
    j2.columns = ["raw", "m5"]
    print(f"  lagged return correlation:        {j2['raw'].corr(j2['m5']):.6f}  (n={len(j2)})")


if __name__ == "__main__":
    main()
