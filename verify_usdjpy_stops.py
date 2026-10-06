"""Verify USDJPYm stop/target distances vs configured risk_pips=31.6, rr_ratio=3.0."""
import sqlite3

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=== USDJPYm 2026-10-05 fills: distance vs configured 31.6 pips ===")
for r in c.execute(
    "SELECT ticket, timestamp, direction, filled_price, filled_sl, "
    "filled_tp, requested_lots, filled_lots, is_closed, exit_time, exit_price, "
    "exit_reason, exit_profit, comment "
    "FROM fills WHERE symbol='USDJPYm' AND timestamp LIKE '2026-10-05%' "
    "ORDER BY timestamp"
).fetchall():
    d = dict(r)
    fp = d["filled_price"]
    sl = d["filled_sl"]
    tp = d["filled_tp"]
    if fp is None or tp is None or sl is None:
        continue
    sl_pips = abs(fp - sl) / 0.01  # USDJPY pip_size
    tp_pips = abs(tp - fp) / 0.01
    sl_buf = sl_pips - 31.6
    tp_buf = tp_pips - 31.6 * 3.0
    print(f"  ticket={d['ticket']}  dir={d['direction']}  lots={d['filled_lots']}")
    print(f"    price={fp:.6f}  SL={sl:.6f}  TP={tp:.6f}")
    print(f"    SL_pips={sl_pips:.2f}  (Δ vs 31.6 = +{sl_buf:+.2f})")
    print(f"    TP_pips={tp_pips:.2f}  (Δ vs 94.8 = +{tp_buf:+.2f})  RR={tp_pips/sl_pips:.4f}")
    print(f"    spread_at_fill={d['comment']!r}  exit={d['exit_time']} {d['exit_price']} {d['exit_reason']}")
    print()

print("=== Looking for spread_at_fill value ===")
for r in c.execute(
    "SELECT ticket, timestamp, direction, filled_price, filled_sl, filled_tp, "
    "requested_lots, filled_lots, spread_at_fill, is_closed "
    "FROM fills WHERE symbol='USDJPYm' AND timestamp LIKE '2026-10-05%' "
    "ORDER BY timestamp"
).fetchall():
    d = dict(r)
    print(f"  ticket={d['ticket']}  spread_at_fill={d['spread_at_fill']}  lots={d['filled_lots']}")

print()
print("=== Other context columns ===")
for r in c.execute(
    "SELECT ticket, slippage_points, slippage_pct, size_slippage, "
    "requested_sl, requested_tp, signal_price "
    "FROM fills WHERE symbol='USDJPYm' AND timestamp LIKE '2026-10-05%' "
    "ORDER BY timestamp"
).fetchall():
    print(f"  {dict(r)}")

c.close()