"""Diagnose: which symbols have live fills, what fallback behavior was used."""
import sqlite3, tempfile, pandas as pd
from collections import Counter
c = sqlite3.connect(tempfile.gettempdir() + r'\mt5_audit_real.db', check_same_thread=False)

print("=== FILLS by symbol ===")
df = pd.read_sql_query("SELECT symbol, direction, filled_lots, profit, exit_profit, timestamp FROM fills ORDER BY timestamp", c)
print(df.to_string(index=False))

print("\n=== FILLS count per symbol ===")
print(df['symbol'].value_counts().to_string())

print("\n=== SIGNALS by symbol (deduped to bar-level) ===")
sigs = pd.read_sql_query("SELECT symbol, signal, rejection_reason, timestamp FROM signals ORDER BY timestamp", c)
print(sigs['symbol'].value_counts().to_string())

print("\n=== Any EURUSDm or USDJPYm activity? ===")
for sym in ('EURUSDm', 'USDJPYm', 'XAUUSDm'):
    sf = df[df['symbol'] == sym]
    sg = sigs[sigs['symbol'] == sym]
    print(f"  {sym}: {len(sf)} fills, {len(sg)} signals")

print("\n=== Search for any sizer-fit warnings in audit ===")
# We didn't log sizer failures; check risk_decisions for tier info
risk = pd.read_sql_query("SELECT * FROM risk_decisions ORDER BY timestamp", c)
print(risk[['timestamp','symbol','signal','decision','reason']].to_string(index=False))
c.close()