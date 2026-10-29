import sqlite3, os, json
DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()
print("=" * 70)
print("ROW COUNTS")
print("=" * 70)
for t in ['fills','signals','risk_decisions','risk_events','evaluations','pipeline_latency','loss_audit']:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    n = cur.fetchone()[0]
    print(f"{t:24s} {n}")

for tbl in ['fills', 'signals', 'evaluations', 'risk_decisions']:
    print()
    print("=" * 70)
    print(tbl.upper(), "COLUMNS")
    print("=" * 70)
    cur.execute(f"PRAGMA table_info({tbl})")
    for r in cur.fetchall():
        print(f"  {r[1]:30s} {r[2]}")

# Indexes
print()
print("INDEXES")
cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index'")
for r in cur.fetchall(): print(f"  {r[1]}.{r[0]}")

# Most recent activity
print()
print("MOST RECENT FILLS (5)")
cur.execute("SELECT id, symbol, direction, filled_lots, filled_price, timestamp, exit_time, exit_profit, exit_commission, exit_swap FROM fills ORDER BY id DESC LIMIT 5")
for r in cur.fetchall():
    print(" ", r)

print()
print("OPEN FILLS (no exit):")
cur.execute("SELECT COUNT(*) FROM fills WHERE exit_time IS NULL")
print(f"  open_count={cur.fetchone()[0]}")

print()
print("OPEN FILLS details:")
cur.execute("SELECT id, symbol, direction, mt5_ticket, filled_price, timestamp, filled_lots, is_closed, degraded_sizing FROM fills WHERE exit_time IS NULL ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    print(" ", r)
con.close()