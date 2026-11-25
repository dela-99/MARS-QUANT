"""Assignment 14 — Phase B raw source forensics (v2).

Correctly combines <DATE> + <TIME> columns from the MT5 export CSVs.

Resolves:
  1. The 2020 file (suspected daily-interval, 311 rows) — true frequency + provenance.
  2. The 2024 filename/date-range inconsistency.
  3. Real bar frequency per file (2021 row count is ~half of 2022-2025 — must explain).
  4. Gaps, duplicates, spread/tick-volume behaviour, session coverage.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

SRC = Path(r"C:\Users\RIDGE\trading-data")
CONSOLIDATED = Path(
    r"C:\Users\RIDGE\MARS-QUANT\data\raw\xauusdm\m5\exness\XAUUSDm_M5_2020_2026_raw.csv"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip() for c in df.columns]
    df.columns = [c.strip("<>").lower() for c in df.columns]
    return df


def to_ts(df: pd.DataFrame) -> pd.Series:
    if "date" in df.columns and "time" in df.columns:
        raw = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
    else:
        raw = df[df.columns[0]].astype(str).str.strip()
    return pd.to_datetime(raw, errors="coerce", utc=True)


def profile(path: Path) -> dict:
    df = load_raw(path)
    ts = to_ts(df)
    out: dict = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path),
                 "rows": len(df), "unparseable": int(ts.isna().sum())}
    ts = ts.dropna()
    out["first"] = str(ts.min())
    out["last"] = str(ts.max())
    out["dup_ts"] = int(ts.duplicated().sum())
    out["monotonic"] = bool(ts.is_monotonic_increasing)

    d = ts.diff().dropna().dt.total_seconds()
    if len(d):
        vc = d.value_counts()
        out["modal_interval_s"] = int(vc.index[0])
        out["modal_share"] = round(float(vc.iloc[0] / len(d)), 4)
        out["interval_top6"] = {int(k): int(v) for k, v in vc.head(6).items()}
        out["inferred_freq"] = _infer_freq(int(vc.index[0]))
        out["n_intervals_5min"] = int((d == 300).sum())
    else:
        out["modal_interval_s"] = None

    for col in ("tickvol", "spread", "vol"):
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            out[f"{col}_sum"] = float(s.sum())
            out[f"{col}_nonzero"] = int((s.fillna(0) != 0).sum())
            out[f"{col}_max"] = float(s.max()) if len(s) else None
            out[f"{col}_median_nz"] = float(s[s.fillna(0) != 0].median()) if out[f"{col}_nonzero"] else None

    # Hour-of-day coverage (UTC) — reveals session structure
    out["hour_hist"] = {int(h): int(c) for h, c in ts.dt.hour.value_counts().sort_index().items()}
    # Weekday coverage
    out["weekday_hist"] = {int(w): int(c) for w, c in ts.dt.dayofweek.value_counts().sort_index().items()}
    return out


def _infer_freq(sec: int) -> str:
    return {60: "M1", 300: "M5", 900: "M15", 1800: "M30", 3600: "H1",
            14400: "H4", 86400: "D1"}.get(sec, f"{sec}s")


def main() -> None:
    files = sorted(SRC.glob("XAUUSDm_M5_*.csv"))
    print("=" * 104)
    print("RAW EXNESS XAUUSDm M5 CSV FORENSICS  (DATE+TIME parsed)")
    print("=" * 104)
    for f in files:
        p = profile(f)
        print(f"\n--- {p['file']} ---")
        print(f"  rows={p['rows']}  sha256={p['sha256'][:16]}...")
        print(f"  range: {p['first']} -> {p['last']}")
        print(f"  dup_ts={p['dup_ts']}  monotonic={p['monotonic']}  unparseable={p['unparseable']}")
        print(f"  modal_interval={p['modal_interval_s']}s -> {p.get('inferred_freq')}  share={p.get('modal_share')}  "
              f"n_5min_gaps={p.get('n_intervals_5min')}")
        print(f"  interval_top6={p.get('interval_top6')}")
        for k in ("tickvol", "spread", "vol"):
            if f"{k}_sum" in p:
                print(f"  {k}: sum={p[f'{k}_sum']:.0f} nonzero={p[f'{k}_nonzero']} "
                      f"max={p[f'{k}_max']} median_nz={p[f'{k}_median_nz']}")
        print(f"  hour_hist={p['hour_hist']}")
        print(f"  weekday_hist={p['weekday_hist']}")

    print("\n" + "=" * 104)
    print("PER-FILE MONTHLY ROW COUNTS (looking for coverage holes)")
    print("=" * 104)
    for f in files:
        df = load_raw(f)
        ts = to_ts(df).dropna()
        m = ts.dt.to_period("M").value_counts().sort_index()
        print(f"\n{f.name}")
        print("   " + "  ".join(f"{k}:{v}" for k, v in m.items()))

    print("\n" + "=" * 104)
    print("CONSOLIDATED FILE CHECK")
    print("=" * 104)
    if CONSOLIDATED.exists():
        c = profile(CONSOLIDATED)
        print(f"  rows={c['rows']}  range: {c['first']} -> {c['last']}")
        print(f"  dup_ts={c['dup_ts']}  modal_interval={c['modal_interval_s']}s share={c.get('modal_share')}")
        print(f"  sha256={c['sha256']}")
        df = load_raw(CONSOLIDATED)
        ts = to_ts(df).dropna()
        print("  rows per year: " + ", ".join(
            f"{y}:{v}" for y, v in ts.dt.year.value_counts().sort_index().items()))
        d = ts.diff().dropna().dt.total_seconds()
        vc = d.value_counts()
        print("  gap histogram (top12):", {int(k): int(v) for k, v in vc.head(12).items()})
        print(f"  hour_hist={c['hour_hist']}")
        print(f"  weekday_hist={c['weekday_hist']}")
        # duplicate timestamps: are they identical rows or conflicts?
        dupmask = to_ts(df).duplicated(keep=False)
        if dupmask.any():
            dups = df[dupmask]
            print(f"  DUPLICATE TIMESTAMP rows={len(dups)}; unique ts={to_ts(df).duplicated().sum()}")
            print("  duplicate sample:")
            print(dups.head(4).to_string())
    else:
        print("  MISSING:", CONSOLIDATED)


if __name__ == "__main__":
    main()
