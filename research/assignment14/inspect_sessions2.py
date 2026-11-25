"""Assignment 14 — Phase B: precise session-break and timezone characterisation.

Per calendar day (in the file's native frame) report bar counts, first/last bar and
intra-day gaps, to locate the daily break. Per ISO week report open/close timestamps,
to detect DST discontinuities and pin the frame (UTC vs broker server time).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\RIDGE\MARS-QUANT")
CONS = ROOT / "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv"


def load() -> pd.DataFrame:
    df = pd.read_csv(CONS, sep="\t")
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]
    raw = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
    df["ts"] = pd.to_datetime(raw, errors="coerce", utc=True)
    df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    gap = df["ts"].diff().dt.total_seconds()
    same_tod = df["ts"].dt.time == df["ts"].shift(1).dt.time
    d1 = ((same_tod) & (gap % 86400 == 0) & (gap >= 86400)).fillna(False)
    d1.iloc[0] = True  # first 2020 bar is part of the daily block too
    df["is_d1"] = d1
    return df


def main() -> None:
    df = load()
    m5 = df[~df["is_d1"]].reset_index(drop=True)
    print(f"M5 rows={len(m5)}  {m5['ts'].iloc[0]} -> {m5['ts'].iloc[-1]}")

    print("\n" + "=" * 100)
    print("A. PER-CALENDAR-DAY STRUCTURE (native frame)")
    print("=" * 100)
    m5["date"] = m5["ts"].dt.date
    g = m5.groupby("date")
    bars = g.size()
    first = g["ts"].min().dt.strftime("%H:%M")
    last = g["ts"].max().dt.strftime("%H:%M")
    summary = pd.DataFrame({"bars": bars, "first": first, "last": last})
    print("  bar-count distribution (top12):")
    print("   ", dict(summary["bars"].value_counts().head(12)))
    print("  first-bar time-of-day distribution (top12):")
    print("   ", dict(summary["first"].value_counts().head(12)))
    print("  last-bar time-of-day distribution (top12):")
    print("   ", dict(summary["last"].value_counts().head(12)))
    print("\n  typical full day (most common bar count):")
    common = summary["bars"].value_counts().index[0]
    print(summary[summary["bars"] == common].head(8).to_string())

    print("\n" + "=" * 100)
    print("B. INTRA-DAY GAP DISTRIBUTION (gaps inside one calendar date)")
    print("=" * 100)
    intraday = m5.groupby("date")["ts"].diff().dt.total_seconds()
    vc = intraday.value_counts()
    print("  top12:", {int(k): int(v) for k, v in vc.head(12).items()})
    big = intraday[(intraday > 300) & (intraday < 20000)]
    end_ts = m5.loc[big.index, "ts"]
    print("  break-END clock times (top12):", dict(end_ts.dt.strftime("%H:%M").value_counts().head(12)))
    print("  break-START clock times (top12):",
          dict(end_ts.shift(1).loc[big.index].dt.strftime("%H:%M").value_counts().head(12)))

    print("\n" + "=" * 100)
    print("C. WEEKLY OPEN/CLOSE — DST DISCONTINUITY SCAN")
    print("=" * 100)
    iso = m5["ts"].dt.isocalendar()
    key = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    w = m5.groupby(key)["ts"]
    wk = pd.DataFrame({"open": w.min(), "close": w.max()})
    wk["open_t"] = wk["open"].dt.strftime("%H:%M")
    wk["close_t"] = wk["close"].dt.strftime("%H:%M")
    wk["open_dow"] = wk["open"].dt.strftime("%a")
    odd = wk[(wk["open_t"] != "00:00") | (wk["close_t"] != "23:55")]
    print(f"  weeks total={len(wk)}  non-standard weeks={len(odd)}")
    print(odd.to_string())

    print("\n  distinct weekly open/close patterns by calendar month:")
    wk["month"] = wk["open"].dt.to_period("M").astype(str)
    pat = wk.groupby("month").agg(
        open_t=("open_t", lambda s: ",".join(sorted(set(s)))),
        close_t=("close_t", lambda s: ",".join(sorted(set(s)))),
        n=("open", "size"),
    )
    print(pat.to_string())

    print("\n" + "=" * 100)
    print("D. DAILY BREAK POSITION vs MONTH (DST probe)")
    print("=" * 100)
    brk = pd.DataFrame({"date": intraday.index.map(lambda d: str(d)),
                         "gap": intraday})
    brk = brk[brk["gap"] > 300].copy()
    brk["end"] = m5.loc[brk.index, "ts"].dt.strftime("%H:%M")
    brk["month"] = m5.loc[brk.index, "ts"].dt.to_period("M").astype(str)
    bm = brk.groupby("month")["end"].agg(lambda s: s.value_counts().head(3).to_dict())
    for m, d in bm.items():
        print(f"    {m}: {d}")


if __name__ == "__main__":
    main()
