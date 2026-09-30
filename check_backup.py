import sqlite3

backup = sqlite3.connect(r"C:\Users\RIDGE\MARS-QUANT\mt5_audit_backup.db", check_same_thread=False)
cur = backup.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('Tables in backup:', [r[0] for r in cur.fetchall()])
for t in ('signals','fills','risk_decisions','risk_events','evaluations'):
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'  {t}: {cur.fetchone()[0]} rows in backup')
backup.close()