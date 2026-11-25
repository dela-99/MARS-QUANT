"""Assignment 14 — Phase B: daily-vs-M5 boundary detection + H1 provenance reconciliation.

Part 1: find the exact D1 -> M5 transition inside the Exness "2021 jan to dec" file
         and confirm which consolidated rows are daily-interval.
Part 2: profile every raw H1 source (Exness + legacy OANDA) and both processed H1
         datasets to reconcile raw coverage vs processed coverage through 2026-04.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SRC = Path(r"C:\Users\RIDGE\trading-data")
ROOT = Path(r"C:\Users\RIDGE\MARS-QUANT")


def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]
    raw = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
    df["ts"] = pd.to_datetime(raw, errors="coerce", utc=True)
    return df


def boundary_report() -> None:
    print("=" * 100)
    print("PART 1 — D1 vs M5 BOUNDARY DETECTION")
    print("=" * 100)
    for name in ["XAUUSDm_M5_2020_1_12.csv", "XAUUSDm_M5_2021 jan to dec.csv"]:
        df = load_raw(SRC / name)
        df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        gap = df["ts"].diff().dt.total_seconds()
        daily = gap > 3600  # anything coarser than H1 => not M5
        print(f"\n--- {name} ---")
        print(f"  rows={len(df)}  daily_interval_rows={int(daily.sum())}  "
              f"first_ts={df['ts'].iloc[0]}  last_ts={df['ts'].iloc[-1]}")
        # where does the first true M5 bar appear?
        m5 = gap == 300
        first_m5_i = int(m5[m5].index[0]) if m5.any() else None
        if first_m5_i is not None:
            print(f"  FIRST true M5 bar: {df['ts'].iloc[first_m5_i]} (row {first_m5_i})")
            print(f"  LAST  daily bar  : {df['ts'].iloc[first_m5_i - 1]}")
            print(f"  daily bars before transition: {first_m5_i}")
        # rows that are daily *after* the first M5 bar (i.e. embedded holes)
        if first_m5_i is not None:
            after = gap.iloc[first_m5_i:]
            n_after_daily = int((after > 3600).sum())
            print(f"  coarse gaps AFTER first M5 bar: {n_after_daily}")

    # Consolidated file: classify every row by the interval that precedes it
    print("\n--- consolidated (data/raw/xauusdm/m5/exness/...) row classification ---")
    cons = load_raw(ROOT / "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv")
    cons = cons.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    gap = cons["ts"].diff().dt.total_seconds()
    cons["coarse"] = gap > 3600
    coarse_rows = cons[cons["coarse"]]
    print(f"  total rows={len(cons)}  coarse_preceded_rows={len(coarse_rows)}")
    if len(coarse_rows):
        print(f"  coarse-preceded row date range: {coarse_rows['ts'].min()} -> {coarse_rows['ts'].max()}")
        by_year = coarse_rows["ts"].dt.year.value_counts().sort_index()
        print("  coarse rows per year: " + ", ".join(f"{y}:{v}" for y, v in by_year.items()))
        # contiguous block boundaries
        idx = coarse_rows.index.to_numpy()
        breaks = np.flatnonzero(np.diff(idx) > 1) if len(idx) > 1 else []
        starts = [0] + (breaks + 1).tolist()
        ends = breaks + [len(idx) - 1]
        print("  contiguous coarse blocks (block_start -> block_end, n_rows):")
        for s, e in zip(starts, ends):
            blk = cons.loc[idx[s]:idx[e]]
            print(f"    {blk['ts'].iloc[0]} -> {blk['ts'].iloc[-1]}  n={e - s + 1}")


def profile_parquet(path: Path, label: str) -> None:
    if not path.exists():
        print(f"\n--- {label}: MISSING ({path}) ---")
        return
    df = pd.read_parquet(path)
    print(f"\n--- {label} ---")
    print(f"  path={path}")
    print(f"  rows={len(df)}  cols={list(df.columns)}")
    idx = None
    for cand in ("timestamp", "time", "date"):
        if cand in df.columns:
            idx = cand
            break
    if idx:
        ts = pd.to_datetime(df[idx], utc=True, errors="coerce")
        print(f"  index_col={idx}  range: {ts.min()} -> {ts.max()}")
        print(f"  tz={ts.dt.tz}  dup_ts={int(ts.duplicated().sum())}  monotonic={ts.is_monotonic_increasing}")
        d = ts.diff().dropna().dt.total_seconds()
        vc = d.value_counts()
        print(f"  modal_interval={int(vc.index[0])}s share={round(float(vc.iloc[0]/len(d)),4)}  top5={dict(list(vc.head(5).items()))}")
        print(f"  rows per year: " + ", ".join(f"{y}:{v}" for y, v in ts.dt.year.value_counts().sort_index().items()))
        print(f"  spread col present: {'spread' in df.columns}; nonzero spread rows: "
              f"{int((pd.to_numeric(df['spread'], errors='coerce').fillna(0) != 0).sum()) if 'spread' in df.columns else 'n/a'}")


def main() -> None:
    boundary_report()
    print("\n" + "=" * 100)
    print("PART 2 — H1 PROVENANCE")
    print("=" * 100)
    profile_parquet(ROOT / "data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet",
                    "RAW H1 Exness (deduplicated 2015-2025)")
    for y in (2015, 2018, 2020, 2025):
        profile_parquet(ROOT / f"data/raw/xauusd_h1_{y}_present.parquet",
                        f"RAW H1 legacy xauusd_h1_{y}_present.parquet")
    profile_parquet(ROOT / "data/processed/xauusdm/h1/v1.1.0/data.parquet",
                    "PROCESSED H1 xauusdm v1.1.0 (resampled from M5)")
    profile_parquet(ROOT / "data/processed/xauusd/h1/v1.0.0/data.parquet",
                    "PROCESSED H1 xauusd v1.0.0 (OANDA GOLD legacy)")


if __name__ == "__main__":
    import numpy as np  # noqa: E402  (used inside boundary_report)
    main()
