"""Inspect parquet index types for all symbols to understand the dtype bug."""
import pandas as pd
import os

paths = {
    'XAUUSDm': r"C:\Users\RIDGE\MARS-QUANT\data\processed\xauusd\m5\v1.0.0\data.parquet",
    'EURUSDm':  r"C:\Users\RIDGE\MARS-QUANT\data\processed\eurusd\m5\v1.0.0\data.parquet",
    'USDJPYm':  r"C:\Users\RIDGE\MARS-QUANT\data\processed\usdjpy\m5\v1.0.0\data.parquet",
    'EURGBPm':  r"C:\Users\RIDGE\MARS-QUANT\data\processed\eurgbp\m5\v1.0.0\data.parquet",
}
for sym, p in paths.items():
    if not os.path.exists(p):
        print(f"  {sym}: FILE NOT FOUND")
        continue
    df = pd.read_parquet(p)
    print(f"  {sym}:")
    print(f"     shape:        {df.shape}")
    print(f"     columns:      {list(df.columns)}")
    print(f"     index.dtype:  {df.index.dtype}")
    print(f"     index first 3: {df.index[:3].tolist()}")
    print(f"     index last 3:  {df.index[-3:].tolist()}")
    if 'timestamp' in df.columns:
        print(f"     timestamp col dtype: {df['timestamp'].dtype}")
        print(f"     timestamp first 3: {df['timestamp'].head(3).tolist()}")
    print()