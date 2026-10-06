"""Test: does XAUUSDm GARCH fit fail when called after 3 other fits in sequence?

Hypothesis: the arch library / global optimization state accumulates NaN.
"""
import sys
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

import pandas as pd
from mars.apps.trading.system.pair_config import get_data_path
from mars.apps.trading.system.vol_scaled_system import VolScaledSizer

results = []
for symbol in ["EURUSDm", "USDJPYm", "EURGBPm", "XAUUSDm"]:
    path = get_data_path(symbol)
    df = pd.read_parquet(path).sort_index()
    recent = df.tail(2000)
    sizer = VolScaledSizer(garch_variant='garch')
    try:
        sizer.fit(recent)
        fv = sizer.forecast_vol(recent)
        results.append((symbol, "OK", len(fv), float(fv.iloc[-1])))
    except Exception as e:
        results.append((symbol, "FAIL", 0, str(e)[:80]))

print("=== Run 1 (all 4 in sequence) ===")
for r in results:
    print(f"  {r}")

print()
print("=== Run 2: XAUUSDm only (after above state pollution) ===")
path = get_data_path("XAUUSDm")
df = pd.read_parquet(path).sort_index()
recent = df.tail(2000)
sizer = VolScaledSizer(garch_variant='garch')
try:
    sizer.fit(recent)
    fv = sizer.forecast_vol(recent)
    print(f"  XAUUSDm OK after EUR/USDJPY/EURGBP ran first: len={len(fv)}, last={fv.iloc[-1]:.4f}")
except Exception as e:
    print(f"  XAUUSDm *** FAILED *** {type(e).__name__}: {str(e)[:120]}")