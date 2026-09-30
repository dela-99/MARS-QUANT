"""Audit + cleanup script — find injected test rows in mt5_audit_real.db."""
import sqlite3
import sys
from datetime import datetime, timezone

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"

print("=" * 78)
print("STEP 1 — Show the exact row that was inserted as 'injected test eval'")
print("=" * 78)

# From screenshot_2refreshes.py the script used these values:
#   gate_result='ALLOWED', trend_1h='LONG_BIAS', bias_30m='LONG_BIAS',
#   context_15m='TRADEABLE', context_15m_reason='Spread and ATR within normal range',
#   breakout_signal=1, breakout_price=4155.50, breakout_stop=4146.00
#   (refresh 2) breakout_price=4155.80, breakout_stop=4146.30
# Distinguishing marker: breakout_price in (4155.5, 4155.8) — no live eval uses those
# values (live eval breakout_price was always 0.0 for flat signals)

conn = sqlite3.connect(DB, check_same_thread=False)
try:
    cur = conn.cursor()

    cur.execute("""
        SELECT id, timestamp, symbol, gate_result, trend_1h, bias_30m,
               context_15m, breakout_signal, breakout_price, breakout_stop
        FROM evaluations
        WHERE breakout_price > 0
        ORDER BY id ASC
    """)
    injected = cur.fetchall()
    cols = [d[0] for d in cur.description]
    print(f"\nFound {len(injected)} evaluation row(s) with breakout_price > 0")
    print("(Live evaluations on Sep 29/30 all have breakout_price=0 because the")
    print(" 5M signal was flat — anything > 0 is synthetic)")
    if injected:
        print()
        print("  " + " | ".join(cols))
        for r in injected:
            print("  " + " | ".join(str(c) for c in r))

    # Row counts BEFORE cleanup
    print("\n" + "=" * 78)
    print("STEP 2 — Row counts BEFORE cleanup")
    print("=" * 78)
    counts_before = {}
    for t in ("signals", "fills", "risk_decisions", "risk_events", "evaluations"):
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        counts_before[t] = cur.fetchone()[0]
        print(f"  {t}: {counts_before[t]}")

    # STEP 2 — Delete the injected rows
    print("\n" + "=" * 78)
    print("STEP 2 — DELETE injected test rows")
    print("=" * 78)
    if injected:
        ids = [r[0] for r in injected]
        placeholders = ",".join("?" * len(ids))
        cur.execute(f"DELETE FROM evaluations WHERE id IN ({placeholders})", ids)
        conn.commit()
        print(f"  Deleted {cur.rowcount} row(s) with id in {ids}")

    # Verify the timestamps we generated are gone
    cur.execute("""
        SELECT id, timestamp FROM evaluations
        WHERE timestamp LIKE '2026-09-30T12:42:%'
    """)
    leftover = cur.fetchall()
    print(f"  Rows with our injected timestamps (12:42:*): {len(leftover)}")

    # STEP 3 — Look for OTHER suspicious rows from any verification step
    print("\n" + "=" * 78)
    print("STEP 3 — Scan all tables for synthetic/test markers")
    print("=" * 78)

    # Check signals
    cur.execute("""
        SELECT id, timestamp, symbol, signal, rejection_reason
        FROM signals
        WHERE rejection_reason LIKE '%TEST%' OR rejection_reason LIKE '%INJECT%'
           OR timestamp LIKE '2026-09-30T12:4%'
    """)
    susp_signals = cur.fetchall()
    print(f"  signals with TEST/INJECT markers: {len(susp_signals)}")

    cur.execute("""
        SELECT id, timestamp, symbol, decision, reason
        FROM risk_decisions
        WHERE reason LIKE '%TEST%' OR reason LIKE '%INJECT%'
           OR timestamp LIKE '2026-09-30T12:4%'
    """)
    susp_risks = cur.fetchall()
    print(f"  risk_decisions with TEST/INJECT markers: {len(susp_risks)}")

    cur.execute("""
        SELECT id, timestamp, symbol, direction, comment
        FROM fills
        WHERE comment LIKE '%TEST%' OR comment LIKE '%INJECT%'
           OR timestamp LIKE '2026-09-30T12:4%'
    """)
    susp_fills = cur.fetchall()
    print(f"  fills with TEST/INJECT markers: {len(susp_fills)}")

    cur.execute("""
        SELECT id, timestamp, event_type, details
        FROM risk_events
        WHERE details LIKE '%TEST%' OR details LIKE '%INJECT%'
           OR timestamp LIKE '2026-09-30T12:4%'
    """)
    susp_events = cur.fetchall()
    print(f"  risk_events with TEST/INJECT markers: {len(susp_events)}")

    # STEP 4 — Final row counts
    print("\n" + "=" * 78)
    print("STEP 4 — Row counts AFTER cleanup")
    print("=" * 78)
    counts_after = {}
    for t in ("signals", "fills", "risk_decisions", "risk_events", "evaluations"):
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        counts_after[t] = cur.fetchone()[0]
        delta = counts_after[t] - counts_before[t]
        print(f"  {t}: {counts_after[t]} (delta {delta:+d})")

    # Confirm the cleanup invariants
    print("\n" + "=" * 78)
    print("FINAL CHECKS")
    print("=" * 78)
    cur.execute("SELECT COUNT(*) FROM evaluations WHERE breakout_price > 0")
    still_injected = cur.fetchone()[0]
    print(f"  evaluations with breakout_price > 0 (synthetic marker): {still_injected}")
    cur.execute("SELECT COUNT(*) FROM evaluations WHERE timestamp LIKE '2026-09-30T12:42:%'")
    print(f"  evaluations at 2026-09-30T12:42:* timestamps: {cur.fetchone()[0]}")

    # DB row totals
    total = sum(counts_after.values())
    print(f"\n  Total real rows across all 5 tables: {total}")
finally:
    conn.close()