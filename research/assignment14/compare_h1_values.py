"""Assignment 14 — Phase B: side-by-side raw-H1 vs M5-derived-H1 values + offset structure."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\RIDGE\MARS-QUANT")


def build_m5_h1() -> pd.DataFrame:
    m5 = pd.read_parquet(ROOT / "data/processed/xauusdm/m5/v1.1.0/data.parquet")
    m5.index = pd.DatetimeIndex(m5.index).tz_convert("UTC")
    m5 = m5.sort_index()
    gap = m5.index.to_series().diff().dt.total_seconds()
    m5 = m5[gap.isna() | (gap == 300)]          # drop the embedded daily block
    m5 = m5[m5.index >= "2021-08-01"]            # clean M5 era only
    return m5.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last",
         "tick_volume": "sum"}).dropna(subset=["close"])


def main() -> None:
    raw = pd.read_parquet(ROOT / "data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet")
    raw["ts"] = pd.to_datetime(raw["time"], utc=True)
    raw = raw.set_index("ts").sort_index()
    h1 = build_m5_h1()

    print("=" * 110)
    print("SIDE-BY-SIDE: raw H1 close vs M5-derived H1 close at SAME timestamp")
    print("=" * 110)
    common = raw.index.intersection(h1.index)
    sample = common[:: max(1, len(common) // 14)][:14]
    rows = []
    for t in sample:
        rows.append({
            "ts": t,
            "raw_close": round(float(raw.loc[t, "close"]), 3),
            "m5_close": round(float(h1.loc[t, "close"]), 3),
            "raw_open": round(float(raw.loc[t, "open"]), 3),
            "m5_open": round(float(h1.loc[t, "open"]), 3),
            "diff": round(float(raw.loc[t, "close"] - h1.loc[t, "close"]), 3),
            "raw_spread": int(raw.loc[t, "spread"]),
        })
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n" + "=" * 110)
    print("PRICE-LEVEL STATS ON THE FULL OVERLAP")
    print("=" * 110)
    a = raw.loc[common, "close"]
    b = h1.loc[common, "close"]
    d = (a - b)
    print(f"  n={len(common)}  raw mean=${a.mean():.3f}  m5 mean=${b.mean():.3f}")
    print(f"  signed diff: mean=${d.mean():.4f} median=${d.median():.4f} std=${d.std():.4f}")
    print(f"  |diff|: median=${d.abs().median():.4f} p90=${d.abs().quantile(.9):.4f} "
          f"p99=${d.abs().quantile(.99):.4f} max=${d.abs().max():.4f}")
    print(f"  exact match: {(d.abs() < 1e-9).mean():.4%}   within $0.5: {(d.abs() < 0.5).mean():.4%}")
    print(f"  correlation of closes: {a.corr(b):.6f}")

    # Monthly: does the disagreement vary by period?
    print("\n" + "=" * 110)
    print("DISAGREEMENT BY YEAR (same timestamp)")
    print("=" * 110)
    dd = pd.DataFrame({"raw": a, "m5": b})
    dd["diff"] = dd["raw"] - dd["m5"]
    dd["year"] = dd.index.year
    g = dd.groupby("year")["diff"].agg(["size", "mean", "median", lambda s: s.abs().median()])
    g.columns = ["n", "mean_diff", "median_diff", "median_abs_diff"]
    print(g.to_string())

    # Best lag per year -> does the offset drift?
    print("\n" + "=" * 110)
    print("BEST HOUR LAG PER YEAR (raw shifted vs m5-derived)")
    print("=" * 110)
    for year in sorted(dd["year"].unique()):
        sub_a = raw.loc[raw.index.year == year, "close"]
        best = None
        for lag in range(-6, 7):
            s = sub_a.copy()
            s.index = s.index + pd.Timedelta(hours=lag)
            c = s.index.intersection(h1.index)
            if len(c) < 50:
                continue
            diff = (s.loc[c] - h1.loc[c, "close"]).abs()
            med = float(diff.median())
            if best is None or med < best[1]:
                best = (lag, med, len(c))
        print(f"  {year}: best lag={best[0]:>3}h  median|diff|=${best[1]:.4f}  n={best[2]}")

    # Sanity: what does the M5 series say the H1 bar at the SAME clock hour contains?
    print("\n" + "=" * 110)
    print("M5 HOUR-BY-HOUR CHECK (2022-03-02, a clean Wednesday)")
    print("=" * 110)
    m5 = pd.read_parquet(ROOT / "data/processed/xauusdm/m5/v1.1.0/data.parquet")
    m5.index = pd.DatetimeIndex(m5.index).tz_convert("UTC")
    m5 = m5.sort_index()
    day = m5.loc["2022-03-02"]
    print(day[["open", "high", "low", "close"]].head(30).to_string())
    r = raw.loc["2022-03-02"]
    print("\n  raw H1 for 2022-03-02:")
    print(r[["open", "high", "low", "close"]].to_string())


if __name__ == "__main__":
    main()
