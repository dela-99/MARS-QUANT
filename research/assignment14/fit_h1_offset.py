"""Assignment 14 — Phase B: fit the raw-H1 <-> M5 hour offset per day, exactly.

For each candidate shift D, aggregate the M5 window [t-D, t-D+1h) and compare its
OHLC to the raw H1 bar labelled t. Report the best D per day and its stability.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\RIDGE\MARS-QUANT")


def load_m5() -> pd.DataFrame:
    m5 = pd.read_parquet(ROOT / "data/processed/xauusdm/m5/v1.1.0/data.parquet")
    m5.index = pd.DatetimeIndex(m5.index).tz_convert("UTC")
    m5 = m5.sort_index()
    gap = m5.index.to_series().diff().dt.total_seconds()
    m5 = m5[gap.isna() | (gap == 300)]
    return m5[m5.index >= "2021-08-01"]


def main() -> None:
    raw = pd.read_parquet(ROOT / "data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet")
    raw["ts"] = pd.to_datetime(raw["time"], utc=True)
    raw = raw.set_index("ts").sort_index()
    m5 = load_m5()

    print("=" * 104)
    print("PER-DAY OFFSET FIT: raw H1 bar at label t  vs  M5 aggregate over [t-D, t-D+1h)")
    print("=" * 104)
    dates = ["2022-03-02", "2022-08-17", "2023-05-11", "2024-04-02", "2025-02-21", "2025-09-25"]
    for day in dates:
        day_start = pd.Timestamp(day, tz="UTC")
        r = raw.loc[(raw.index >= day_start) & (raw.index < day_start + pd.Timedelta(days=1))]
        if r.empty:
            print(f"\n{day}: no raw H1 rows")
            continue
        print(f"\n--- {day} (raw H1 rows={len(r)}, first={r.index[0]}, last={r.index[-1]}) ---")
        print(f"  {'D(h)':>5} {'n_matched':>10} {'median|dC|':>11} {'median|dO|':>10} {'exact%':>8}")
        results = []
        for D in range(-6, 7):
            diffs_c, diffs_o, exact = [], [], 0
            for t, row in r.iterrows():
                w0 = t - pd.Timedelta(hours=D)
                w = m5.loc[(m5.index >= w0) & (m5.index < w0 + pd.Timedelta(hours=1))]
                if len(w) < 10:      # require a reasonably complete hour
                    continue
                diffs_c.append(abs(float(row["close"]) - float(w["close"].iloc[-1])))
                diffs_o.append(abs(float(row["open"]) - float(w["open"].iloc[0])))
                if abs(float(row["close"]) - float(w["close"].iloc[-1])) < 1e-9:
                    exact += 1
            if not diffs_c:
                continue
            mc, mo = pd.Series(diffs_c).median(), pd.Series(diffs_o).median()
            results.append((D, len(diffs_c), mc, mo, exact / len(diffs_c)))
            print(f"  {D:>5} {len(diffs_c):>10} {mc:>11.4f} {mo:>10.4f} {exact/len(diffs_c):>7.2%}")
        best = min(results, key=lambda x: x[2])
        print(f"  --> BEST D = {best[0]}h   median|dClose| = ${best[2]:.4f}   "
              f"median|dOpen| = ${best[3]:.4f}   exact close match = {best[4]:.2%}")

    # Stability of the best D over the whole overlap, sampled monthly
    print("\n" + "=" * 104)
    print("MONTHLY BEST-D (sample of months)")
    print("=" * 104)
    rows = []
    for ym in pd.date_range("2021-09-01", "2025-09-01", freq="3MS"):
        day = (ym + pd.Timedelta(days=10)).tz_localize("UTC")
        r = raw.loc[(raw.index >= day) & (raw.index < day + pd.Timedelta(days=1))]
        if r.empty:
            continue
        best = None
        for D in range(-6, 7):
            dc = []
            for t, row in r.iterrows():
                w0 = t - pd.Timedelta(hours=D)
                w = m5.loc[(m5.index >= w0) & (m5.index < w0 + pd.Timedelta(hours=1))]
                if len(w) < 10:
                    continue
                dc.append(abs(float(row["close"]) - float(w["close"].iloc[-1])))
            if not dc:
                continue
            med = float(pd.Series(dc).median())
            if best is None or med < best[1]:
                best = (D, med)
        rows.append({"month": str(ym.date()), "best_D_h": best[0], "median_dClose": round(best[1], 4)})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
