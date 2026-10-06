"""Tag the 2 USDJPYm trades (Oct 5 12:41:12 and 12:45:01) with degraded_sizing=1.

These trades were sized at 0.06 lots when the account equity (~7x above floor)
should have used 0.01 lots. Root cause: the sizer.fit() failed because the
parquet path used the broker suffix (USDJPYm -> usdjpym) instead of the
catalog key (usdjpy), AND the fallback formula used a hardcoded XAUUSD
contract_size of 100 instead of FX's 100000.

Both fixes are now in place in run_session_v3.py:
  - get_data_path(symbol) goes through MT5_SYMBOL_TO_CONFIG_KEY
  - get_contract_specs(symbol) returns per-symbol contract_size

This script backfills the audit DB so the Nov 3 6-week-baseline panel
can exclude / separately break out these 2 trades.
"""
import sqlite3

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"

DEGRADED_TICKETS = [3325045333, 3325060832]  # Oct 5 12:41:12 and 12:45:01

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=== Before: schema ===")
cols_before = [r[1] for r in c.execute("PRAGMA table_info(fills)").fetchall()]
print(f"  has degraded_sizing col: {'degraded_sizing' in cols_before}")

print("\n=== Before: target rows ===")
for r in c.execute(
    "SELECT ticket, symbol, requested_lots, filled_lots, filled_price, "
    "filled_sl, timestamp, exit_reason, is_closed FROM fills "
    "WHERE ticket IN (3325045333, 3325060832)"
).fetchall():
    print(f"  {dict(r)}")

# Add column if missing
if "degraded_sizing" not in cols_before:
    print("\n=== Adding degraded_sizing column ===")
    c.execute("ALTER TABLE fills ADD COLUMN degraded_sizing INTEGER DEFAULT 0")
    c.commit()
    print("  ALTER TABLE done")

# Tag the 2 trades
print("\n=== Tagging degraded trades ===")
c.executemany(
    "UPDATE fills SET degraded_sizing = 1 WHERE ticket = ?",
    [(t,) for t in DEGRADED_TICKETS],
)
c.commit()

print("\n=== After: target rows ===")
for r in c.execute(
    "SELECT ticket, symbol, requested_lots, filled_lots, filled_price, "
    "filled_sl, timestamp, exit_reason, is_closed, degraded_sizing FROM fills "
    "WHERE ticket IN (3325045333, 3325060832)"
).fetchall():
    print(f"  {dict(r)}")

print("\n=== Verify: total rows now flagged degraded_sizing=1 ===")
n = c.execute("SELECT COUNT(*) FROM fills WHERE degraded_sizing = 1").fetchone()[0]
print(f"  count={n}")

print("\n=== Verify: other USDJPYm trades (NOT tagged) ===")
for r in c.execute(
    "SELECT ticket, timestamp, requested_lots, filled_lots, degraded_sizing "
    "FROM fills WHERE symbol='USDJPYm' AND timestamp LIKE '2026-10-05%'"
).fetchall():
    print(f"  {dict(r)}")

c.close()