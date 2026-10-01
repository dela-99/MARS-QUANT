"""Test: run schema migration + reconcile_from_broker against the live DB."""
import sys, os
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

import sqlite3, tempfile
import MetaTrader5 as mt5

DB = os.path.join(tempfile.gettempdir(), "mt5_audit_real.db")

# 1) Apply schema migration by instantiating AuditLogger (init_db is idempotent)
from mars.apps.trading.mt5_executor import MT5AuditLogger
from dataclasses import dataclass

# We need a TradeConfig to instantiate MT5AuditLogger — just give it anything
@dataclass
class _FakeConfig:
    symbol: str = "XAUUSDm"
    risk_per_trade: float = 0.03
    signal: int = 0
    stop_price: float = 0.0
    take_profit: float = 0.0
    entry_price: float = 0.0
    position_size: float = 0.0
    entry_time: object = None
    max_hold_hours: float = 4.0

assert mt5.initialize(), f"MT5 init failed: {mt5.last_error()}"
acct = mt5.account_info()
print(f"Connected to MT5 account #{acct.login}")

al = MT5AuditLogger(DB, mt5)
print(f"AuditLogger ready (DB at {DB})")

# 2) Check fills schema now has exit columns
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()
cols = [r[1] for r in cur.execute("PRAGMA table_info(fills)").fetchall()]
print(f"\nFills table columns ({len(cols)}):")
for c in cols:
    print(f"  {c}")
new_cols = ["position_id","exit_time","exit_price","exit_reason","exit_commission","exit_swap","exit_profit","exit_deal_ticket","is_closed"]
missing = [c for c in new_cols if c not in cols]
print(f"\nNew exit columns present: {len(new_cols) - len(missing)}/{len(new_cols)}")
if missing:
    print(f"  Missing: {missing}")
else:
    print("  All migration columns added successfully.")

# 3) Show fills BEFORE reconciliation
print("\n=== fills BEFORE reconciliation ===")
cur.execute("""
    SELECT id, ticket, symbol, direction, filled_price, exit_price, exit_profit, exit_reason, is_closed
    FROM fills ORDER BY timestamp
""")
for r in cur.fetchall():
    print(f"  id={r[0]} ticket={r[1]} {r[2]:8} {r[3]:4} entry={r[4]:.3f} exit={r[5] or 'NULL':>8} "
          f"profit={r[6] or 0:+.2f} reason={r[7] or 'NULL':>12} closed={r[8] or 0}")

# 4) Run reconcile
print("\n=== Calling reconcile_from_broker() ===")
result = al.reconcile_from_broker(days_back=30)
print(f"Result: {result}")

# 5) Show fills AFTER reconciliation
print("\n=== fills AFTER reconciliation ===")
cur.execute("""
    SELECT id, ticket, symbol, direction, filled_price, exit_price, exit_profit, exit_reason, is_closed, exit_time
    FROM fills ORDER BY timestamp
""")
for r in cur.fetchall():
    print(f"  id={r[0]} ticket={r[1]} {r[2]:8} {r[3]:4} entry={r[4]:.3f} exit={r[5] or 'NULL':>8} "
          f"profit={r[6] or 0:+.2f} reason={r[7] or 'NULL':>12} closed={r[8] or 0}  exit_time={r[9]}")

# 6) Compute expectancy from the now-reconciled fills
print("\n=== COMPUTING EXPECTANCY (real close data) ===")
cur.execute("""
    SELECT id, ticket, symbol, direction, filled_price, exit_price, exit_profit,
           exit_commission, exit_swap, filled_sl, filled_lots
    FROM fills WHERE is_closed = 1
""")
closed = cur.fetchall()
print(f"Closed trades found: {len(closed)}")
if closed:
    rows = []
    for r in closed:
        entry = r[4]
        exit_p = r[5]
        profit = r[6] or 0
        commission = r[7] or 0
        swap = r[8] or 0
        sl = r[9]
        lots = r[10] or 0
        # Compute R multiple: profit / (sl_distance * lots * 100)
        sl_distance = abs(entry - sl) if sl else 0
        if sl_distance > 0 and lots > 0:
            risk_dollars = sl_distance * lots * 100
            net_pnl = profit + commission + swap
            R = net_pnl / risk_dollars
        else:
            R = None
        rows.append((r[1], r[2], r[3], entry, exit_p, net_pnl, R))
        print(f"  ticket={r[1]} {r[2]:8} {r[3]:4} entry={entry:.3f} exit={exit_p} net_pnl={net_pnl:+.2f}  R={R}")

    Rs = [r[6] for r in rows if r[6] is not None]
    if Rs:
        wins = [r for r in Rs if r > 0]
        losses = [r for r in Rs if r <= 0]
        win_rate = len(wins) / len(Rs)
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        expectancy_R = win_rate * avg_win + (1 - win_rate) * avg_loss
        gross_profit = sum(r[5] for r in rows if r[5] > 0)
        gross_loss = abs(sum(r[5] for r in rows if r[5] <= 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        print()
        print(f"  Total trades:    {len(Rs)}")
        print(f"  Win rate:        {win_rate*100:.1f}%")
        print(f"  Avg win (R):     {avg_win:+.2f}")
        print(f"  Avg loss (R):    {avg_loss:+.2f}")
        print(f"  Expectancy (R):  {expectancy_R:+.3f}")
        print(f"  Profit factor:   {profit_factor:.2f}")
        print(f"  Gross profit:    ${gross_profit:,.2f}")
        print(f"  Gross loss:      ${gross_loss:,.2f}")

conn.close()
mt5.shutdown()