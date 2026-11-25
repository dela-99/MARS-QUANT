"""Assignment 14 — Phase B: session-boundary, timezone and D1/M5 classification forensics.

Answers:
  1. Which consolidated rows are daily-interval (not M5)?
  2. Are the MT5 export timestamps UTC or broker server time? (DST drift test)
  3. What are the real session boundaries (weekly open/close) and the daily break?
  4. What do the spread units mean (points -> USD)?
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\RIDGE\MARS-QUANT")
SRC = Path(r"C:\Users\RIDGE\trading-data")
CONS = ROOT / "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv"


def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]
    raw = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
    df["ts"] = pd.to_datetime(raw, errors="coerce", utc=True)
    return df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)


def classify_d1(df: pd.DataFrame) -> pd.Series:
    """True where the row is part of a daily-interval block.

    A row is daily-interval iff its time-of-day equals the previous row's
    time-of-day AND the gap to the previous row is an exact multiple of 86400s.
    M5 rows are 300s apart, so this cannot fire on them.
    """
    gap = df["ts"].diff().dt.total_seconds()
    same_tod = df["ts"].dt.time == df["ts"].shift(1).dt.time
    mult = (gap % 86400 == 0) & (gap >= 86400)
    return (same_tod & mult).fillna(False)


def main() -> None:
    print("=" * 100)
    print("1. D1 BLOCK CLASSIFICATION PER RAW FILE")
    print("=" * 100)
    for f in sorted(SRC.glob("XAUUSDm_M5_*.csv")):
        df = load_raw(f)
        d1 = classify_d1(df)
        print(f"\n--- {f.name} ---")
        print(f"  rows={len(df)}  daily_rows={int(d1.sum())}  m5_rows={int((~d1).sum())}")
        if d1.any():
            blk = df[d1]
            print(f"  daily block: {blk['ts'].iloc[0]} -> {blk['ts'].iloc[-1]}")
            print(f"  daily time-of-day values: {sorted({str(t) for t in blk['ts'].dt.time})[:6]}")
            tod = df.loc[~d1, "ts"].dt.time
            print(f"  m5 time-of-day sample: {sorted({str(t) for t in tod})[:4]} ... n_unique={tod.nunique()}")

    print("\n" + "=" * 100)
    print("2. CONSOLIDATED FILE — D1 BLOCKS")
    print("=" * 100)
    cons = load_raw(CONS)
    d1 = classify_d1(cons)
    print(f"  total={len(cons)}  daily_rows={int(d1.sum())}  m5_rows={int((~d1).sum())}")
    idx = np.flatnonzero(d1.to_numpy())
    if len(idx):
        breaks = np.flatnonzero(np.diff(idx) > 1)
        starts = np.concatenate([[0], breaks + 1])
        ends = np.concatenate([breaks, [len(idx) - 1]])
        for s, e in zip(starts, ends):
            rows = cons.loc[idx[s]:idx[e]]
            print(f"  D1 BLOCK: {rows['ts'].iloc[0]} -> {rows['ts'].iloc[-1]}  n={e - s + 1}  "
                  f"tod={sorted({str(t) for t in rows['ts'].dt.time})}")

    m5 = cons[~d1].reset_index(drop=True)
    print(f"\n  TRUE M5 DATASET: {len(m5)} rows  {m5['ts'].iloc[0]} -> {m5['ts'].iloc[-1]}")
    print(f"  rows per year: " + ", ".join(
        f"{y}:{v}" for y, v in m5['ts'].dt.year.value_counts().sort_index().items()))
    gap = m5["ts"].diff().dt.total_seconds()
    vc = gap.value_counts()
    print("  gap histogram (top10):", {int(k): int(v) for k, v in vc.head(10).items()})

    print("\n" + "=" * 100)
    print("3. SESSION BOUNDARIES / TIMEZONE (M5 only)")
    print("=" * 100)
    # Weekly open (first bar of each ISO week) and weekly close (last bar)
    iso = m5["ts"].dt.isocalendar()
    key = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    g = m5.groupby(key)
    opens = g["ts"].min()
    closes = g["ts"].max()
    open_tod = opens.dt.strftime("%H:%M")
    close_tod = closes.dt.strftime("%H:%M")
    print("  weekly OPEN time-of-day distribution:")
    print("   ", dict(open_tod.value_counts().head(8)))
    print("  weekly CLOSE time-of-day distribution:")
    print("   ", dict(close_tod.value_counts().head(8)))
    print("\n  weekly open/close by month (first 6 + DST boundary samples):")
    sample = pd.DataFrame({"open": opens, "close": closes}).reset_index()
    sample["month"] = sample["open"].dt.to_period("M").astype(str)
    for m in ["2021-08", "2021-10", "2021-12", "2022-01", "2022-04", "2022-07", "2022-10",
              "2023-03", "2023-04", "2023-11", "2024-03", "2024-11", "2025-03", "2025-11"]:
        sel = sample[sample["month"] == m]
        if len(sel):
            print(f"    {m}: opens={sorted(sel['open'].dt.strftime('%H:%M').unique())} "
                  f"closes={sorted(sel['close'].dt.strftime('%H:%M').unique())}")

    # Daily break: consecutive gap > 300s within a trading day
    print("\n  intraday break structure (gaps 600..20000s) by hour-of-day:")
    intraday = gap[(gap > 300) & (gap < 20000)]
    if len(intraday):
        brk_end_hour = (m5["ts"].iloc[1:][intraday.index - 1].dt.hour)
        print("   ", dict(brk_end_hour.value_counts().sort_index().head(12)))
        print("    gap value counts:", {int(k): int(v) for k, v in intraday.value_counts().head(6).items()})

    print("\n" + "=" * 100)
    print("4. SPREAD UNITS")
    print("=" * 100)
    sp = pd.to_numeric(m5["spread"], errors="coerce")
    for y in sorted(m5["ts"].dt.year.unique()):
        s = sp[m5["ts"].dt.year == y]
        s = s[s > 0]
        print(f"  {y}: n={len(s)} median={s.median():.0f} p90={s.quantile(.9):.0f} max={s.max():.0f} "
              f"-> @point=0.001: median=${s.median()*0.001:.3f} max=${s.max()*0.001:.3f}")
    tv = pd.to_numeric(m5["tickvol"], errors="coerce")
    print(f"\n  tickvol: sum={tv.sum():.0f} median={tv.median():.0f} max={tv.max():.0f} zero_rows={int((tv==0).sum())}")
    vol = pd.to_numeric(m5["vol"], errors="coerce") if "vol" in m5.columns else None
    if vol is not None:
        print(f"  <VOL> (real volume): sum={vol.sum():.0f} nonzero={int((vol!=0).sum())} "
              f"-> {'ALL ZERO (Exness tick-volume only)' if vol.sum()==0 else 'has values'}")


if __name__ == "__main__":
    main()
