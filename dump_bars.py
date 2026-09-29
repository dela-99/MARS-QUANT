"""
Pull the actual 1H and 30M bars the MTF gate was using.
Replicates exactly what fetch_all_timeframes does.
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

assert mt5.initialize()
print("MT5 initialized, terminal:", mt5.terminal_info().name)
print("Now (server):", mt5.symbol_info_tick("XAUUSDm").time)

# Check symbol
si = mt5.symbol_info("XAUUSDm")
print("XAUUSDm:", "visible" if si and si.visible else "NOT VISIBLE — selecting")
if si and not si.visible:
    mt5.symbol_select("XAUUSDm", True)
    si = mt5.symbol_info("XAUUSDm")
print("  digits:", si.digits, "point:", si.point, "spread:", si.spread)
print("  current bid:", mt5.symbol_info_tick("XAUUSDm").bid)

# Timeframe constants
TF_H1 = 16385
TF_M30 = 16384
TF_M15 = 16383

def fetch(symbol, tf, n=100):
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n)
    if rates is None:
        print(f"  fetch failed for {symbol} tf={tf}: {mt5.last_error()}")
        return None
    df = pd.DataFrame(rates)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
    return df

print("\n=== 1H bars (last 15) ===")
h1 = fetch("XAUUSDm", TF_H1, 100)
print("Total 1H bars:", len(h1))
print("Earliest:", h1['timestamp'].iloc[0])
print("Latest (forming):", h1['timestamp'].iloc[-1])
print("Server current time:", datetime.utcfromtimestamp(mt5.symbol_info_tick("XAUUSDm").time))
print()
print(h1[['timestamp','open','high','low','close']].tail(15).to_string(index=False))

print("\n=== 30M bars (last 15) ===")
m30 = fetch("XAUUSDm", TF_M30, 100)
print("Total 30M bars:", len(m30))
print("Earliest:", m30['timestamp'].iloc[0])
print("Latest (forming):", m30['timestamp'].iloc[-1])
print()
print(m30[['timestamp','open','high','low','close']].tail(15).to_string(index=False))

print("\n=== 15M bars (last 15) ===")
m15 = fetch("XAUUSDm", TF_M15, 200)
print("Total 15M bars:", len(m15))
print("Earliest:", m15['timestamp'].iloc[0])
print("Latest (forming):", m15['timestamp'].iloc[-1])
print()
print(m15[['timestamp','open','high','low','close','spread']].tail(15).to_string(index=False))

mt5.shutdown()