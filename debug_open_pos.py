import sys, os
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

# Force fresh import
for m in list(sys.modules.keys()):
    if 'dashboard' in m or 'mars' in m:
        del sys.modules[m]

# Load just the function
import sqlite3
import pandas as pd

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
c = sqlite3.connect(DB)
fills = pd.read_sql("SELECT * FROM fills ORDER BY timestamp DESC LIMIT 500", c)
c.close()
print(f"Total fills loaded: {len(fills)}")
print(f"is_closed dtype: {fills['is_closed'].dtype}")
print(f"is_closed values: {fills['is_closed'].value_counts().to_dict()}")
print()
print("Open positions (is_closed == 0 or NaN):")
df = fills.copy()
df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
df = df.dropna(subset=["ts"])
df = df.sort_values("ts", ascending=False)
open_df = df[(df["is_closed"] == 0) | (df["is_closed"].isna())]
print(f"  count: {len(open_df)}")
print(open_df[["timestamp", "symbol", "direction", "filled_lots", "is_closed"]].head(10).to_string())
print()
print("Degraded_sizing values in OPEN fills:")
print(open_df[["symbol", "direction", "filled_lots", "degraded_sizing"]].head(10).to_string())