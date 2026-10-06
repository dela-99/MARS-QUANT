import sqlite3

c = sqlite3.connect(r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db")
c.row_factory = sqlite3.Row

print("=== USDJPYm rows on 2026-10-05 ===")
for r in c.execute(
    "SELECT ticket, symbol, direction, requested_lots, filled_lots, "
    "filled_price, filled_sl, exit_time, exit_price, exit_reason, "
    "exit_profit, is_closed, timestamp, comment FROM fills "
    "WHERE symbol=? AND timestamp LIKE ? ORDER BY timestamp",
    ("USDJPYm", "2026-10-05%"),
).fetchall():
    print(dict(r))

print()
print("=== ALL FILLS SCHEMA (look for degraded column) ===")
for r in c.execute("PRAGMA table_info(fills)").fetchall():
    print(r)

print()
print("=== Recent fills (last 15) ===")
for r in c.execute(
    "SELECT ticket, symbol, direction, requested_lots, filled_lots, "
    "filled_price, exit_time, exit_price, exit_reason, exit_profit, "
    "is_closed, timestamp, comment FROM fills ORDER BY id DESC LIMIT 15"
).fetchall():
    print(dict(r))