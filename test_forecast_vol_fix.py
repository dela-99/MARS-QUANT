"""Verify forecast_vol() works on real production parquets (int64 index)."""
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

from mars.apps.trading.system.vol_scaled_system import VolScaledSizer
from mars.apps.trading.system.pair_config import get_data_path

symbols = ["EURUSDm", "USDJPYm", "EURGBPm", "XAUUSDm"]

print("=== forecast_vol() on real parquets (int64 index) ===")
for symbol in symbols:
    path = get_data_path(symbol)
    print(f"\n--- {symbol} → {path}")
    df = pd.read_parquet(path)
    print(f"  index.dtype before: {df.index.dtype}, has timestamp col: {'timestamp' in df.columns}")
    recent = df.tail(2000)
    sizer = VolScaledSizer()
    try:
        sizer.fit(recent)
        print(f"  fit(): OK")
        forecast = sizer.forecast_vol(recent)
        print(f"  forecast_vol(): OK, len={len(forecast)}, "
              f"non-null={int(forecast.notna().sum())}, "
              f"first={forecast.iloc[0] if len(forecast) else 'n/a'}, "
              f"last={forecast.iloc[-1] if len(forecast) else 'n/a'}")
    except Exception as e:
        print(f"  *** FAILED *** {type(e).__name__}: {e}")

print("\n=== forecast_vol() on parquet AFTER timestamp → index promotion ===")
for symbol in symbols:
    path = get_data_path(symbol)
    df = pd.read_parquet(path)
    if not pd.api.types.is_datetime64_any_dtype(df.index) and 'timestamp' in df.columns:
        df = df.set_index('timestamp').sort_index()
    recent = df.tail(2000)
    sizer = VolScaledSizer()
    try:
        sizer.fit(recent)
        forecast = sizer.forecast_vol(recent)
        print(f"  {symbol}: forecast_vol() OK, len={len(forecast)}, "
              f"index.dtype={forecast.index.dtype}, "
              f"last={forecast.iloc[-1]:.4f}")
    except Exception as e:
        print(f"  {symbol}: *** FAILED *** {type(e).__name__}: {e}")