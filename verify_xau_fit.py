"""Verify whether XAUUSDm fit/forecast actually succeeds on the live data slice.

Live session uses `df.tail(2000)` after `pd.read_parquet(path).sort_index()`.
Re-run exactly what the session does.
"""
import sys
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

import pandas as pd
import numpy as np

from mars.apps.trading.system.pair_config import get_data_path
from mars.apps.trading.system.vol_scaled_system import VolScaledSizer

# Simulate EXACTLY what fit_sizers() does in run_session_v3.py
path = get_data_path("XAUUSDm")
df = pd.read_parquet(path)
df = df.sort_index()  # NOTE: NO timestamp promotion — this is the old call site
recent = df.tail(2000)

print(f"=== XAUUSDm parquet: {path} ===")
print(f"  full shape: {df.shape}, recent shape: {recent.shape}")
print(f"  full index.dtype: {df.index.dtype}")
print(f"  has timestamp col: {'timestamp' in df.columns}")
print(f"  recent tail 3:")
print(recent.tail(3).to_string())
print()

# Check for NaN/inf in the OHLC columns (the "y" for GARCH)
o = recent["open"]
c = recent["close"]
h = recent["high"]
l = recent["low"]
print(f"  NaN counts in recent[2000]: open={o.isna().sum()}, high={h.isna().sum()}, low={l.isna().sum()}, close={c.isna().sum()}")
print(f"  inf counts: open={np.isinf(o).sum()}, high={np.isinf(h).sum()}, low={np.isinf(l).sum()}, close={np.isinf(c).sum()}")
print(f"  zero counts (potential divide-by-zero in log): close_zeros={(c==0).sum()}, "
      f"open_zeros={(o==0).sum()}, high_zeros={(h==0).sum()}, low_zeros={(l==0).sum()}")
print()

# Now try the actual fit+forecast path
print("=== Try sizer.fit() + sizer.forecast_vol() ===")
try:
    sizer = VolScaledSizer(garch_variant='garch')
    sizer.fit(recent)
    print("  fit(): OK")
    try:
        fv = sizer.forecast_vol(recent)
        print(f"  forecast_vol(): OK, len={len(fv)}, last={fv.iloc[-1]:.6f}")
    except Exception as e:
        print(f"  forecast_vol(): *** FAILED *** {type(e).__name__}: {e}")
except Exception as e:
    print(f"  fit(): *** FAILED *** {type(e).__name__}: {e}")