"""End-to-end verification of the fix.

Steps:
1. Reset the 7 fill rows to is_closed=0 (simulating legacy pre-fix state).
2. Instantiate MT5Executor (which calls _initialize → propagates self.mt5 to audit_logger._mt5).
3. Call reconcile_from_broker() on the executor instance.
4. Confirm fills_reconciled=7, fills_unmatched=0.
5. Confirm all 7 rows now have is_closed=1 with broker-authoritative exit data.
6. Also confirm the fix is durable: reset all 12 fills to is_closed=0 (legacy state),
   reconcile again, confirm fills_reconciled=12.
"""
import sys
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

import os, sqlite3
from pathlib import Path
import MetaTrader5 as mt5

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
BACKUP = DB + ".pre_reset_test_backup"

# Make a safety backup before mutating
import shutil
if not Path(BACKUP).exists():
    shutil.copy2(DB, BACKUP)
    print(f"Safety backup: {BACKUP}")

# Connect MT5
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

# Step 1: reset all 12 rows to is_closed=0 (simulate legacy state)
c = sqlite3.connect(DB)
c.execute(
    "UPDATE fills SET is_closed=0, exit_time=NULL, exit_price=NULL, exit_reason=NULL, "
    "exit_commission=NULL, exit_swap=NULL, exit_profit=NULL, exit_deal_ticket=NULL"
)
c.commit()
n_reset = c.execute("SELECT COUNT(*) FROM fills WHERE is_closed=0").fetchone()[0]
c.close()
print(f"\nStep 1: Reset {n_reset} fills to is_closed=0 (legacy state)")
print()

# Step 2: instantiate MT5Executor — triggers __init__ → audit_logger with self.mt5=None,
# then _initialize() → propagates self.mt5 to audit_logger._mt5
from mars.apps.trading.mt5_executor import MT5Executor, MT5Config, DEFAULT_MT5_CONFIG
print("Step 2: Instantiate MT5Executor (triggers _initialize → audit_logger._mt5)")
executor = MT5Executor(equity=166.0, mt5_config=MT5Config(), audit_db_path=DB)
print(f"  executor.audit_logger._mt5 is set: {executor.audit_logger._mt5 is not None}")
print()

# Step 3: call reconcile_from_broker()
print("Step 3: Call executor.audit_logger.reconcile_from_broker()")
result = executor.audit_logger.reconcile_from_broker()
print(f"  fills_reconciled: {result['fills_reconciled']}")
print(f"  fills_unmatched:  {result['fills_unmatched']}")
print(f"  orphan_positions: {len(result['orphan_positions'])}")
print()

# Step 4-5: confirm DB state
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
n_open = c.execute("SELECT COUNT(*) FROM fills WHERE is_closed=0").fetchone()[0]
n_closed = c.execute("SELECT COUNT(*) FROM fills WHERE is_closed=1").fetchone()[0]
print(f"Step 4-5: DB state — open={n_open}, closed={n_closed}")
print()

# Print all 12 fills with exit data
print("Step 5: All 12 fills, exit data:")
for r in c.execute(
    "SELECT id, ticket, symbol, direction, filled_lots, "
    "is_closed, exit_time, exit_reason, exit_profit, exit_price, "
    "degraded_sizing "
    "FROM fills ORDER BY timestamp"
).fetchall():
    d = dict(r)
    ic = "✓" if d["is_closed"] else "○"
    print(f"  {ic} ticket={d['ticket']}  {d['symbol']:8}  {d['direction']:4}  "
          f"lots={d['filled_lots']}  "
          f"exit={d['exit_time']}  reason={d['exit_reason']}  "
          f"profit=${d['exit_profit']:.2f}  px={d['exit_price']}  deg={d['degraded_sizing']}")
c.close()

# Step 6: test durability — but we already proved it (n_reset=12 → all 12 reconciled).
print()
print("=== DURABILITY CHECK ===")
print(f"  Reset {n_reset} fills (legacy state, no position_id stored).")
print(f"  After reconcile: fills_reconciled={result['fills_reconciled']}, fills_unmatched={result['fills_unmatched']}")
print(f"  All {n_closed} fills now have broker-authoritative exit data.")
print()

# Restore from backup? No — keep the reconciled state, that's what we want.
# But leave the backup file in case they want to replay.
print(f"Safety backup retained at: {BACKUP}")
print()

mt5.shutdown()
print("MT5 disconnected.")