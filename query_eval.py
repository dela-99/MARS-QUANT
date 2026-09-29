import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM evaluations WHERE symbol='XAUUSDm'")
print("Total XAUUSDm evals:", cur.fetchone())

cur.execute("SELECT DISTINCT trend_1h, bias_30m FROM evaluations WHERE symbol='XAUUSDm'")
print("Distinct (1H, 30M) pairs:", cur.fetchall())

cur.execute("SELECT DISTINCT gate_result, rejection_reason FROM evaluations WHERE symbol='XAUUSDm'")
print("Distinct gate results:", cur.fetchall())

cur.execute("SELECT timestamp, gate_result, rejection_reason, trend_1h, bias_30m, breakout_signal FROM evaluations WHERE symbol='XAUUSDm' ORDER BY timestamp ASC LIMIT 3")
print("First 3 XAUUSDm evals (oldest):")
for r in cur.fetchall():
    print("  ", r)

cur.execute("SELECT timestamp, gate_result, rejection_reason, trend_1h, bias_30m, breakout_signal FROM evaluations WHERE symbol='XAUUSDm' ORDER BY timestamp DESC LIMIT 3")
print("Last 3 XAUUSDm evals (newest):")
for r in cur.fetchall():
    print("  ", r)