"""Simulate the FIXED fit_sizers() path resolution for all symbols."""
from mars.apps.trading.system.pair_config import get_data_path
import pandas as pd
import os

print('=== Simulating fit_sizers() with the FIXED path resolution ===')
all_ok = True
for sym in ['XAUUSDm', 'EURUSDm', 'USDJPYm', 'EURGBPm']:
    data_path = get_data_path(sym)
    exists = os.path.exists(data_path)
    status = "EXISTS" if exists else "MISSING"
    print(f"  {sym:8} -> {data_path}  [{status}]")
    if exists:
        try:
            df = pd.read_parquet(data_path)
            n = len(df)
            last = df.index[-1] if hasattr(df.index, '__len__') and len(df) > 0 else 'n/a'
            print(f"             loaded {n} rows, last_ts={last}")
        except Exception as e:
            print(f"             load error: {e}")
            all_ok = False
    else:
        all_ok = False

print()
if all_ok:
    print("RESULT: All 4 symbols resolve to existing parquet files. Sizer fit will succeed.")
else:
    print("RESULT: Some symbols missing data.")