"""Reproduce the forecast_vol() datetime dtype error to pinpoint the exact source."""
import sys, os
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
import pandas as pd
import numpy as np

# Load USDJPYm data the same way fit_sizers does
from mars.apps.trading.system.pair_config import get_data_path
df = pd.read_parquet(get_data_path("USDJPYm")).sort_index()
recent = df.tail(2000)
print(f"Loaded USDJPYm: {len(recent)} rows")
print(f"Index dtype: {recent.index.dtype}")
print(f"Index first 3: {recent.index[:3].tolist()}")

# Run fit + forecast exactly as VolScaledSizer does
from mars.apps.trading.system.vol_scaled_system import VolScaledSizer, SizingConfig
sizer = VolScaledSizer(SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5), garch_variant='garch')

print("\n[1] Calling sizer.fit(recent)...")
try:
    sizer.fit(recent)
    print("    fit() succeeded")
except Exception as e:
    print(f"    fit() FAILED: {type(e).__name__}: {e}")
    raise

print("\n[2] Calling sizer.forecast_vol(recent)...")
try:
    fv = sizer.forecast_vol(recent)
    print(f"    forecast_vol() returned {len(fv)} values, last: {fv.iloc[-1] if len(fv) else 'n/a'}")
except Exception as e:
    import traceback
    print(f"    forecast_vol() FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()