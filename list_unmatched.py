"""Step 1: list all fills marked open/unmatched in audit DB."""
import sqlite3
DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=== All fills with is_closed=0 (still open per audit DB) ===")
for r in c.execute(
    "SELECT ticket, symbol, direction, timestamp AS entry_time, "
    "filled_price, filled_sl, filled_tp, requested_lots, filled_lots, "
    "is_closed, exit_time, exit_price, exit_reason, exit_profit, "
    "position_id, mt5_ticket, mt5_order_id, comment "
    "FROM fills WHERE is_closed = 0 ORDER BY timestamp"
).fetchall():
    d = dict(r)
    print(f"  ticket={d['ticket']}  {d['symbol']:8}  {d['direction']:4}  "
          f"lots={d['filled_lots']}  entry={d['entry_time']}  px={d['filled_price']}  "
          f"is_closed={d['is_closed']}  pos_id={d['position_id']}  "
          f"exit={d['exit_time']}  reason={d['exit_reason']}  comment={d['comment']!r}")
print()

print(f"Total open: {c.execute('SELECT COUNT(*) FROM fills WHERE is_closed=0').fetchone()[0]}")
print(f"Total closed: {c.execute('SELECT COUNT(*) FROM fills WHERE is_closed=1').fetchone()[0]}")
print(f"Total fills: {c.execute('SELECT COUNT(*) FROM fills').fetchone()[0]}")