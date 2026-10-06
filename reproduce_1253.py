"""Reproduce 12:53 trade conditions and compute pre-floor position_size."""
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

import sqlite3
c = sqlite3.connect(r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db")
c.row_factory = sqlite3.Row

# 12:53:52 trade details from the audit DB
trade_1253 = c.execute(
    "SELECT ticket, timestamp, direction, filled_price, filled_sl, filled_tp, "
    "requested_lots, filled_lots, spread_at_fill, signal_price "
    "FROM fills WHERE ticket=3325121545"
).fetchone()
print(f"=== 12:53 trade ===")
for k, v in dict(trade_1253).items():
    print(f"  {k}: {v}")
print()

# risk_decisions around 12:53
print(f"=== risk_decisions 12:50-12:55 ===")
for r in c.execute(
    "SELECT * FROM risk_decisions WHERE timestamp >= '2026-10-05T12:50' "
    "AND timestamp <= '2026-10-05T12:55' ORDER BY timestamp"
).fetchall():
    d = dict(r)
    cols = [k for k in d.keys() if 'equity' in k.lower() or 'timestamp' in k.lower()]
    print(f"  {dict((k,d[k]) for k in cols)}")
print()

# Compute trade 12:53 SL distance in pips
fp = trade_1253['filled_price']
sl = trade_1253['filled_sl']
tp = trade_1253['filled_tp']
sp = trade_1253['signal_price']

# From signal_price (the close used by signal):
sl_from_signal = abs(sp - sl) / 0.01
tp_from_signal = abs(tp - sp) / 0.01
print(f"=== Distance from signal_price ({sp}) ===")
print(f"  SL pips = {sl_from_signal:.2f}  (target was 31.6)")
print(f"  TP pips = {tp_from_signal:.2f}  (target was 94.8)")
print(f"  RR = {tp_from_signal/sl_from_signal:.4f}")
print()

# From filled_price (the actual broker fill):
sl_from_fill = abs(fp - sl) / 0.01
tp_from_fill = abs(tp - fp) / 0.01
print(f"=== Distance from filled_price ({fp}) ===")
print(f"  SL pips = {sl_from_fill:.2f}  (gap = {sl_from_fill - 31.6:+.2f})")
print(f"  TP pips = {tp_from_fill:.2f}  (gap = {tp_from_fill - 94.8:+.2f})")
print(f"  RR = {tp_from_fill/sl_from_fill:.4f}")
print()

# Spread at fill
spread = trade_1253['spread_at_fill']
print(f"spread_at_fill = {spread:.5f}  (USDJPYm expected ~0.010)")
print(f"  → entry gap signal→fill = {fp - sp:.5f}  (= {((fp - sp)/0.01):.2f} pips)")
print()

# Equity at time of trade — let's look for the most recent risk_decisions row
print(f"=== Most recent risk_decisions before 12:53 ===")
for r in c.execute(
    "SELECT timestamp, * FROM risk_decisions WHERE timestamp <= '2026-10-05T12:53:52' "
    "ORDER BY timestamp DESC LIMIT 5"
).fetchall():
    d = dict(r)
    print(f"  ts={d['timestamp']}  columns={list(d.keys())[:8]}")
print()

# Try to find equity column
schema = c.execute("PRAGMA table_info(risk_decisions)").fetchall()
print(f"risk_decisions schema (first 12 cols): {schema[:12]}")
print()

# Sample one row to see structure
sample = c.execute("SELECT * FROM risk_decisions WHERE timestamp <= '2026-10-05T12:53:52' "
                   "ORDER BY timestamp DESC LIMIT 1").fetchone()
if sample:
    print(f"Sample row keys: {list(dict(sample).keys())}")
    print(f"Sample row values: {dict(sample)}")
print()

c.close()