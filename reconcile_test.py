"""Call log_close_fill() directly on each of the 7 unmatched rows and capture what happens."""
import sys
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

import sqlite3
import MetaTrader5 as mt5

# Connect MT5
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

# Instantiate the executor with the MT5 module
from mars.apps.trading.mt5_executor import MT5Executor, MT5AuditLogger, TradeConfig

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"

# Build a fresh executor with the live MT5 connection
executor = MT5Executor.__new__(MT5Executor)
# Manually initialize the audit logger with mt5 module
logger = MT5AuditLogger(DB, mt5)
executor.audit_logger = logger

# Get the 7 unmatched row IDs
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = list(c.execute(
    "SELECT id, ticket, symbol, direction, filled_lots, filled_price, "
    "position_id, timestamp FROM fills WHERE is_closed = 0 ORDER BY timestamp"
).fetchall())
c.close()

print(f"=== Calling log_close_fill() on each of {len(rows)} open rows ===")
for row in rows:
    print(f"\n--- row id={row['id']}  ticket={row['ticket']}  "
          f"{row['symbol']}  {row['direction']}  {row['filled_lots']} lots  "
          f"px={row['filled_price']}  pos_id_in_db={row['position_id']}  "
          f"entry={row['timestamp']} ---")
    try:
        ok = logger.log_close_fill(row['id'])
        print(f"  log_close_fill() → {ok}")
    except Exception as e:
        print(f"  log_close_fill() *** RAISED *** {type(e).__name__}: {e}")

# Now run reconcile_from_broker
print("\n=== Running reconcile_from_broker() ===")
result = logger.reconcile_from_broker()
print(f"  fills_reconciled: {result['fills_reconciled']}")
print(f"  fills_unmatched:  {result['fills_unmatched']}")
print(f"  orphan_positions: {result['orphan_positions']}")

# Re-query DB to confirm changes
print("\n=== After-reconcile DB state for the 7 rows ===")
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
for r in c.execute(
    "SELECT id, ticket, symbol, is_closed, exit_time, exit_reason, exit_profit, exit_price "
    "FROM fills WHERE is_closed = 0 ORDER BY timestamp"
).fetchall():
    print(f"  STILL OPEN: id={r['id']}  ticket={r['ticket']}  {r['symbol']}  "
          f"is_closed={r['is_closed']}  exit_time={r['exit_time']}")
print(f"\n  Total open after: {c.execute('SELECT COUNT(*) FROM fills WHERE is_closed=0').fetchone()[0]}")
print(f"  Total closed after: {c.execute('SELECT COUNT(*) FROM fills WHERE is_closed=1').fetchone()[0]}")
c.close()

mt5.shutdown()