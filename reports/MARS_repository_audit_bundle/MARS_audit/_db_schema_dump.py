import sqlite3, os, json, sys

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
if not os.path.exists(DB):
    print("DB not found")
    sys.exit(0)

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("TABLES:", len(tables))
for name, sql in tables:
    print(f"\n=== {name} ===")
    # Strip newlines for compactness
    s = sql.replace("\n", " ") if sql else ""
    print(s)
    cur2 = con.cursor()
    cur2.execute(f"SELECT COUNT(*) FROM {name}")
    print(f"-- rows: {cur2.fetchone()[0]}")

# indexes
cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
idx = cur.fetchall()
print("\n\nINDEXES:", len(idx))
for name, tbl, sql in idx:
    print(f"  {tbl}.{name}: {sql.replace(chr(10),' ')}")

# PRAGMA table_info for fills (most mutated)
print("\n\nFILLS columns:")
cur.execute("PRAGMA table_info(fills)")
for r in cur.fetchall():
    print("  ", r)

print("\n\nEVALUATIONS columns:")
cur.execute("PRAGMA table_info(evaluations)")
for r in cur.fetchall():
    print("  ", r)
con.close()