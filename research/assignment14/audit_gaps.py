"""Assignment 14 — Phase B: exhaustive gap audit on the M5 v1.2.0 dataset.

Every interval that is not exactly 300 s is enumerated and classified:
  * session break      -> the one-hour daily market closure
  * weekend           -> Friday close -> Sunday open
  * holiday/multi-day -> Christmas / New Year style closures
  * irregular         -> a missing bar *inside* a session (data loss - blocking)

The gap end timestamp is compared with the set of observed session-start times
to decide whether the gap is a closure or an in-session hole.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mars.libs.data.xauusdm_exness import split_m5_and_d1, _read_exness_csv  # noqa: E402


def main() -> None:
    raw = _read_exness_csv(ROOT / "data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv")
    m5, _ = split_m5_and_d1(raw)
    ts = m5["timestamp"].reset_index(drop=True)

    gap = ts.diff().dt.total_seconds()
    rows = []
    for i in range(1, len(ts)):
        g = float(gap.iloc[i])
        if g == 300.0:
            continue
        prev, cur = ts.iloc[i - 1], ts.iloc[i]
        rows.append({
            "gap_s": g,
            "prev": prev,
            "cur": cur,
            "missing_slots": int(round(g / 300)) - 1,
            "end_tod": cur.strftime("%H:%M"),
            "prev_dow": prev.strftime("%a"),
            "cur_dow": cur.strftime("%a"),
            "days": (cur.normalize() - prev.normalize()).days,
        })
    gdf = pd.DataFrame(rows)
    print(f"total non-300s gaps: {len(gdf)}")

    print("\n--- gap size histogram (all non-300s) ---")
    for size, n in Counter(gdf["gap_s"].astype(int)).most_common(30):
        print(f"   {size:>9}s  x{n}")

    # Session-start reference: the clock time at which the market resumes
    print("\n--- end-time-of-day histogram for non-300s gaps ---")
    for tod, n in Counter(gdf["end_tod"]).most_common(15):
        print(f"   {tod}  x{n}")

    # Classification
    def classify(r) -> str:
        if r["days"] >= 2:
            return "multi_day_closure"
        if r["gap_s"] >= 172_800:
            return "weekend"
        if 3900 <= r["gap_s"] <= 4000:
            return "session_break"
        if r["days"] == 1 and r["gap_s"] >= 3600:
            return "single_day_closure"
        return "irregular"

    gdf["cls"] = gdf.apply(classify, axis=1)
    print("\n--- classification ---")
    for cls, n in Counter(gdf["cls"]).most_common():
        print(f"   {cls:<22} x{n}")

    irr = gdf[gdf["cls"] == "irregular"].sort_values("gap_s", ascending=False)
    print(f"\n--- IRREGULAR (in-session / unexplained) gaps: {len(irr)} ---")
    if len(irr):
        cols = ["gap_s", "missing_slots", "prev", "cur", "end_tod", "prev_dow", "cur_dow"]
        with pd.option_context("display.width", 220, "display.max_rows", 200):
            print(irr[cols].to_string(index=False))

    print("\n--- multi-day / single-day closures (dates only, for holiday confirmation) ---")
    clo = gdf[gdf["cls"].isin(["multi_day_closure", "single_day_closure"])].sort_values("prev")
    print(f"  count={len(clo)}")
    with pd.option_context("display.width", 220, "display.max_rows", 200):
        print(clo[["gap_s", "prev", "cur", "cls"]].to_string(index=False))

    print("\n--- weekend gaps: distribution ---")
    wk = gdf[gdf["cls"] == "weekend"]
    print(f"  count={len(wk)}  sizes={dict(Counter(wk['gap_s'].astype(int)))}")
    print(f"  first={wk['prev'].min()}  last={wk['prev'].max()}")


if __name__ == "__main__":
    main()
