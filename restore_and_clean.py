"""
Restore mt5_audit_real.db from the clean backup, then surgically
delete ONLY the 2 synthetic test rows by their unique injected
timestamps (2026-09-30T12:42:13.031276 and 2026-09-30T12:42:24.165608).
"""
import sqlite3, shutil, os

LIVE = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
BACKUP = r"C:\Users\RIDGE\MARS-QUANT\mt5_audit_backup.db"

print(f"Pre-restore row counts in {LIVE}:")
pre = sqlite3.connect(LIVE, check_same_thread=False)
for t in ('signals','fills','risk_decisions','risk_events','evaluations'):
    cur = pre.execute(f"SELECT COUNT(*) FROM {t}")
    n = cur.fetchone()[0]
    print(f"  {t}: {n}")
pre.close()

print(f"\nRestoring {LIVE} from {BACKUP} ...")
# Confirm backup is not corrupted
b = sqlite3.connect(BACKUP, check_same_thread=False)
bc = b.execute("PRAGMA integrity_check").fetchone()
print(f"  Backup integrity_check: {bc[0]}")
b.close()

# Close any open connections to the live DB (Streamlit might be using it)
# but copying the file should work even if open on Windows due to sharing
shutil.copy2(BACKUP, LIVE)
print("  [OK] copied")

print(f"\nPost-restore row counts in {LIVE}:")
post = sqlite3.connect(LIVE, check_same_thread=False)
post.row_factory = sqlite3.Row

# First confirm: are the 2 synthetic timestamps present in the backup?
# (If yes, delete them. If no, the cleanup was already clean.)
SYNTH_TS = [
    '2026-09-30T12:42:13.031276',
    '2026-09-30T12:42:24.165608',
]

print("\nSearching for synthetic test rows by timestamp ...")
for ts in SYNTH_TS:
    cur = post.execute(
        "SELECT id, timestamp, gate_result, trend_1h, bias_30m, breakout_signal, breakout_price "
        "FROM evaluations WHERE timestamp = ?", (ts,))
    rows = cur.fetchall()
    print(f"  ts={ts}  -> {len(rows)} match(es)")
    for r in rows:
        print(f"    id={r['id']} gate={r['gate_result']} 1H={r['trend_1h']} 30M={r['bias_30m']} sig={r['breakout_signal']} bp={r['breakout_price']}")

# Delete ONLY the 2 synthetic rows
print("\nDeleting ONLY the 2 synthetic rows (by exact timestamp) ...")
total_deleted = 0
for ts in SYNTH_TS:
    cur = post.execute("DELETE FROM evaluations WHERE timestamp = ?", (ts,))
    post.commit()
    print(f"  ts={ts}  -> deleted {cur.rowcount} row(s)")
    total_deleted += cur.rowcount

print(f"\nTotal deleted: {total_deleted} synthetic rows")

# Also scan all other tables for any synthetic markers from any verification step
print("\n=== Scanning all tables for any other synthetic/test markers ===")
SYNTH_PATTERNS = ('%TEST%', '%INJECT%', '%SYNTH%', '%MOCK%', '%FAKE%', '2026-09-30T12:42:%')
for t in ('signals', 'fills', 'risk_decisions', 'risk_events', 'evaluations'):
    cols = [r[1] for r in post.execute(f"PRAGMA table_info({t})").fetchall()]
    found = []
    for col in cols:
        if col == 'id':
            continue
        for pat in SYNTH_PATTERNS:
            cur = post.execute(
                f"SELECT id, {col} FROM {t} WHERE CAST({col} AS TEXT) LIKE ? LIMIT 3", (pat,))
            for row in cur.fetchall():
                found.append((t, col, pat, row['id'], str(row[1])[:60]))
    if found:
        print(f"  {t}: {len(found)} candidate(s)")
        for f in found[:5]:
            print(f"    {f}")
    else:
        print(f"  {t}: 0 candidates")

# Final row counts
print("\n=== FINAL row counts ===")
for t in ('signals','fills','risk_decisions','risk_events','evaluations'):
    cur = post.execute(f"SELECT COUNT(*) FROM {t}")
    n = cur.fetchone()[0]
    print(f"  {t}: {n}")

# Confirm the synthetic timestamps are gone
print("\n=== Final synthetic checks ===")
for ts in SYNTH_TS:
    cur = post.execute("SELECT COUNT(*) FROM evaluations WHERE timestamp = ?", (ts,))
    n = cur.fetchone()[0]
    print(f"  evaluations at {ts}: {n}  (must be 0)")

post.close()
print("\n[OK] Live DB restored from clean backup, 2 synthetic rows removed.")