"""Assignment 14 — Phase B: probe processed-dataset index integrity + H1 provenance.

(a) Are the processed v1.1.0 parquet indexes genuinely broken (1970 epoch)?
(b) How dense is the raw Exness H1 series vs the M5-resampled H1?
(c) Does processed H1 v1.0.0 share the raw H1 source, and what does it add?
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(r"C:\Users\RIDGE\MARS-QUANT")


def probe_index(path: Path, label: str) -> None:
    print(f"\n### {label}\n  {path}")
    print("  parquet schema:")
    sch = pq.read_schema(path)
    print("   ", sch)
    df = pd.read_parquet(path)
    idx = df.index
    print(f"  df.index: type={type(idx).__name__} dtype={idx.dtype} name={idx.name!r}")
    print(f"  df.index[:3] = {list(idx[:3])}")
    try:
        print(f"  df.index.min()={idx.min()}  max()={idx.max()}")
    except Exception as e:  # noqa: BLE001
        print(f"  index min/max error: {e!r}")
    if "timestamp" in df.columns:
        col = df["timestamp"]
        print(f"  df['timestamp'] dtype={col.dtype} head={list(col[:3])}")
    print(f"  first 3 rows index repr:\n{df.head(3).to_string()}")


def hourly_coverage(path: Path, label: str, ts_col: str | None = None) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if ts_col and ts_col in df.columns:
        ts = pd.to_datetime(df[ts_col], utc=True)
    else:
        ts = pd.to_datetime(df.index, utc=True)
    df = df.assign(ts=ts).sort_values("ts")
    days = df["ts"].dt.floor("D")
    per_day = df.groupby(days).size()
    print(f"\n### {label}")
    print(f"  rows={len(df)}  range={df['ts'].iloc[0]} -> {df['ts'].iloc[-1]}")
    print(f"  calendar days covered={per_day.size}")
    print(f"  bars/day: median={per_day.median():.0f} mean={per_day.mean():.2f} "
          f"min={per_day.min()} max={per_day.max()}")
    print(f"  hour-of-day coverage (bars present per hour, count of hours with data):")
    hod = df["ts"].dt.hour.value_counts().sort_index()
    print("   ", {int(k): int(v) for k, v in hod.items()})
    gap = df["ts"].diff().dt.total_seconds().dropna()
    vc = gap.value_counts()
    print(f"  gap histogram (top8): {dict(list(vc.head(8).items()))}")
    return df[["ts", "open", "high", "low", "close"]]


def main() -> None:
    print("=" * 100)
    print("A. PROCESSED v1.1.0 INDEX INTEGRITY")
    print("=" * 100)
    probe_index(ROOT / "data/processed/xauusdm/m5/v1.1.0/data.parquet", "PROCESSED M5 v1.1.0")
    probe_index(ROOT / "data/processed/xauusdm/h1/v1.1.0/data.parquet", "PROCESSED H1 v1.1.0")

    print("\n" + "=" * 100)
    print("B. H1 DENSITY")
    print("=" * 100)
    raw_h1 = hourly_coverage(ROOT / "data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet",
                             "RAW H1 Exness 2015-2025", ts_col="time")
    proc_h1 = hourly_coverage(ROOT / "data/processed/xauusd/h1/v1.0.0/data.parquet",
                              "PROCESSED H1 v1.0.0 (legacy)", ts_col="time")
    m5_resampled = hourly_coverage(ROOT / "data/processed/xauusdm/h1/v1.1.0/data.parquet",
                                   "PROCESSED H1 v1.1.0 (resampled from M5)")

    print("\n" + "=" * 100)
    print("C. RAW vs PROCESSED H1 SOURCE RECONCILIATION")
    print("=" * 100)
    a = raw_h1.set_index("ts")
    b = proc_h1.set_index("ts")
    common = a.index.intersection(b.index)
    print(f"  raw H1 rows={len(a)}  processed v1.0.0 rows={len(b)}  common timestamps={len(common)}")
    if len(common):
        exact = (a.loc[common, "close"].round(6) == b.loc[common, "close"].round(6)).mean()
        print(f"  close-price agreement on common timestamps: {exact:.6%}")
    only_b = b.index.difference(a.index)
    print(f"  timestamps only in processed v1.0.0: {len(only_b)}  "
          f"range={only_b.min()} -> {only_b.max()}" if len(only_b) else "  none")
    only_a = a.index.difference(b.index)
    print(f"  timestamps only in raw H1: {len(only_a)}  "
          f"range={only_a.min()} -> {only_a.max()}" if len(only_a) else "  none")

    # Compare resampled-from-M5 H1 vs raw H1 on the overlap
    c = m5_resampled.set_index("ts")
    ov = a.index.intersection(c.index)
    print(f"\n  raw-H1 vs M5-resampled-H1 overlap: {len(ov)} timestamps")
    if len(ov):
        agree = (a.loc[ov, "close"].round(4) == c.loc[ov, "close"].round(4)).mean()
        print(f"  close agreement: {agree:.4%}")
        diff = (a.loc[ov, "close"] - c.loc[ov, "close"]).abs()
        print(f"  |close diff| median={diff.median():.6f} p99={diff.quantile(.99):.6f} max={diff.max():.6f}")


if __name__ == "__main__":
    main()
