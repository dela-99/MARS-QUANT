"""Inspect audit DB schema and current data shape for the dashboard."""
import sqlite3
c = sqlite3.connect(r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db")
cur = c.cursor()

print("=== TABLES ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for (t,) in cur.fetchall():
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cur.fetchone()[0]
    print(f"  {t}: {cnt} rows")

print("\n=== SCHEMAS ===")
for (t,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
    print(f"\n-- {t} --")
    cur.execute(f"PRAGMA table_info({t})")
    for col in cur.fetchall():
        print(f"  {col[1]:30} {col[2]}")

print("\n=== SAMPLE DATA ===")
for (t,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
    print(f"\n-- {t} (last 3 rows) --")
    try:
        cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 3")
        cols = [d[0] for d in cur.description]
        print("  " + " | ".join(cols))
        for r in cur.fetchall():
            print("  " + " | ".join(str(c)[:40] for c in r))
    except Exception as e:
        print(f"  ERROR: {e}")

c.close()