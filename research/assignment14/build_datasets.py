"""Assignment 14 — Phase B runner: build + validate the versioned XAUUSDm datasets.

Usage:
    python research/assignment14/build_datasets.py [--no-write]

Prints a full build report and writes the datasets + manifests when --write
(the default).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mars.libs.data.xauusdm_exness import (  # noqa: E402
    D1_VERSION,
    H1_VERSION,
    M5_VERSION,
    build_datasets,
    reconcile_raw_h1_offset,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    print("=" * 100)
    print("ASSIGNMENT 14 — PHASE B: XAUUSDm DATASET BUILD")
    print("=" * 100)

    result = build_datasets(repo_root=ROOT, write=not args.no_write)

    print("\n--- SOURCE FILE INVENTORY (contents authoritative, filenames not trusted) ---")
    for inv in result["source_inventory"]:
        flag = "  <-- FILENAME MISLABELLED" if inv.filename_mislabelled else ""
        print(f"  {inv.filename}")
        print(f"     rows={inv.rows}  {inv.start} -> {inv.end}")
        print(f"     modal_interval={inv.modal_interval_seconds}s ({inv.inferred_timeframe})  "
              f"daily_rows={inv.daily_rows}  m5_rows={inv.m5_rows}{flag}")
        if inv.notes:
            print(f"     note: {inv.notes}")

    for key, label in (("m5", "M5"), ("d1", "D1 (excluded block)"), ("h1", "H1")):
        df = result[key]
        rep = result[f"{key}_report"]
        print("\n" + "=" * 100)
        print(f"{label} DATASET — validation {'PASS' if rep.passed else 'FAIL'}")
        print("=" * 100)
        print(f"  rows={rep.rows}  {rep.start} -> {rep.end}")
        print(f"  duplicate_timestamps={rep.duplicate_timestamps}  monotonic={rep.monotonic_increasing}")
        print(f"  ohlc_violations={rep.ohlc_violations}  non_positive_prices={rep.non_positive_prices}  "
              f"missing_values={rep.missing_values}")
        print(f"  negative_spread_rows={rep.negative_spread_rows}  zero_spread_rows={rep.zero_spread_rows}")
        print(f"  non_five_minute_intervals={rep.non_five_minute_intervals}")
        print(f"  interval_histogram={rep.interval_histogram}")
        print(f"  rows_per_year={rep.rows_per_year}")
        if rep.failures:
            print(f"  FAILURES: {rep.failures}")
        if rep.notes:
            print(f"  NOTES: {rep.notes}")

    print("\n" + "=" * 100)
    print("RAW H1 GRID RECONCILIATION")
    print("=" * 100)
    raw_h1 = ROOT / "data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet"
    rec = reconcile_raw_h1_offset(raw_h1, result["m5"])
    print(f"  distinct best shifts (hours): {rec['distinct_shifts_observed']}")
    print(f"  median |close diff| at best shift: ${rec['median_abs_close_diff_at_best_shift_usd']}")
    print("  per-sample:")
    for s in rec["samples"]:
        print(f"    {s['day']}  shift={s['best_shift_hours']:+d}h  "
              f"median|dClose|=${s['median_abs_close_diff']}")

    if not args.no_write:
        print("\n" + "=" * 100)
        print("WRITTEN DATASETS")
        print("=" * 100)
        for key, ver, tf in (("m5", M5_VERSION, "m5"), ("d1", D1_VERSION, "d1"), ("h1", H1_VERSION, "h1")):
            p = ROOT / "data/processed/xauusdm" / tf / ver / "data.parquet"
            print(f"  {tf.upper():>3} {ver}: {p}  exists={p.exists()}  bytes={p.stat().st_size if p.exists() else 0}")
        print("\n  manifests:")
        for key, ver, tf in (("m5", M5_VERSION, "m5"), ("d1", D1_VERSION, "d1"), ("h1", H1_VERSION, "h1")):
            p = ROOT / "data/processed/xauusdm" / tf / ver / "_manifest.json"
            print(f"    {p}  exists={p.exists()}")

    ok = result["m5_report"].passed and result["h1_report"].passed
    print(f"\nDATA GATE: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
