"""Verify the 7 fills now have exit data after my direct reconcile_test.py calls."""
import sqlite3
DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=== All fills: closed status + exit data ===")
for r in c.execute(
    "SELECT id, ticket, symbol, direction, filled_lots, "
    "is_closed, exit_time, exit_reason, exit_profit, exit_price, "
    "exit_commission, exit_swap, exit_deal_ticket, "
    "degraded_sizing, comment "
    "FROM fills ORDER BY timestamp"
).fetchall():
    d = dict(r)
    is_closed = "✓" if d['is_closed'] else "○"
    print(f"  {is_closed} id={d['id']:3}  ticket={d['ticket']}  {d['symbol']:8}  "
          f"{d['direction']:4}  lots={d['filled_lots']}  "
          f"exit={d['exit_time']}  reason={d['exit_reason']}  "
          f"profit=${d['exit_profit']:.2f}  px={d['exit_price']}  "
          f"deg={d['degraded_sizing']}")

# Now also verify position_id is still NULL for these (because log_close_fill doesn't backfill position_id)
print("\n=== position_id for these fills (should still be NULL — the bug) ===")
for r in c.execute(
    "SELECT id, ticket, position_id FROM fills WHERE is_closed = 1"
).fetchall():
    print(f"  id={r['id']:3}  ticket={r['ticket']}  position_id={r['position_id']}")

print()
print(f"Total: open={c.execute('SELECT COUNT(*) FROM fills WHERE is_closed=0').fetchone()[0]}, "
      f"closed={c.execute('SELECT COUNT(*) FROM fills WHERE is_closed=1').fetchone()[0]}")