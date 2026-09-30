import sqlite3, sys
db = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
c = sqlite3.connect(db)
cur = c.cursor()
cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM evaluations WHERE symbol='XAUUSDm'")
print('XAUUSDm evaluations now:', cur.fetchone())
cur.execute("SELECT DISTINCT trend_1h, bias_30m FROM evaluations WHERE symbol='XAUUSDm'")
print('All distinct (1H, 30M) combos seen this DB:', cur.fetchall())
cur.execute("SELECT timestamp, trend_1h, bias_30m FROM evaluations WHERE symbol='XAUUSDm' ORDER BY timestamp DESC LIMIT 12")
print('Last 12 XAU evals (newest first):')
for r in cur.fetchall():
    print(' ', r)