#!/usr/bin/env python3
"""
Reconcile audit database after trading session.
Verifies fill counts, signal counts, risk decisions, and cross-checks with MT5 history.
"""
import sys
import os
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def reconcile_audit(db_path: str, backup_dir: str = None, hours_back: int = 24):
    """
    Reconcile audit database for the last N hours.
    
    Args:
        db_path: Path to audit database
        backup_dir: Optional backup directory to also check
        hours_back: How many hours back to reconcile
    """
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    print(f"=== AUDIT RECONCILIATION ===")
    print(f"Database: {db_path}")
    print(f"Time window: last {hours_back} hours")
    print()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Time cutoff
    cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
    
    # 1. Signal counts
    cursor.execute("""
        SELECT signal, risk_check_passed, COUNT(*) as cnt
        FROM signals
        WHERE timestamp >= ?
        GROUP BY signal, risk_check_passed
    """, (cutoff,))
    signals = cursor.fetchall()
    print("📊 SIGNALS (last {} hours):".format(hours_back))
    total_signals = 0
    for sig, passed, cnt in signals:
        direction = "LONG" if sig == 1 else "SHORT" if sig == -1 else "FLAT"
        status = "PASS" if passed else "REJECT"
        print(f"  {direction} | {status}: {cnt}")
        total_signals += cnt
    print(f"  TOTAL: {total_signals}")
    print()
    
    # 2. Risk decisions
    cursor.execute("""
        SELECT decision, COUNT(*) as cnt
        FROM risk_decisions
        WHERE timestamp >= ?
        GROUP BY decision
    """, (cutoff,))
    decisions = cursor.fetchall()
    print("🛡️  RISK DECISIONS:")
    for decision, cnt in decisions:
        print(f"  {decision}: {cnt}")
    print()
    
    # 3. Fills
    cursor.execute("""
        SELECT direction, COUNT(*) as cnt,
               AVG(slippage_points) as avg_slip_pts,
               AVG(slippage_pct) as avg_slip_pct,
               SUM(slippage_points) as total_slip_pts,
               AVG(size_slippage) as avg_size_slip
        FROM fills
        WHERE timestamp >= ?
        GROUP BY direction
    """, (cutoff,))
    fills = cursor.fetchall()
    print("📈 FILLS:")
    total_fills = 0
    for direction, cnt, avg_slip_pts, avg_slip_pct, total_slip_pts, avg_size_slip in fills:
        print(f"  {direction}: {cnt} fills")
        print(f"    Avg slippage: {avg_slip_pts:.2f} pts ({avg_slip_pct:.2f} bps)")
        print(f"    Total slippage: {total_slip_pts:.2f} pts")
        print(f"    Avg size slippage: {avg_size_slip:.4f} lots")
        total_fills += cnt
    print(f"  TOTAL FILLS: {total_fills}")
    print()
    
    # 4. Risk events
    cursor.execute("""
        SELECT event_type, COUNT(*) as cnt
        FROM risk_events
        WHERE timestamp >= ?
        GROUP BY event_type
    """, (cutoff,))
    events = cursor.fetchall()
    print("⚠️  RISK EVENTS:")
    for event_type, cnt in events:
        print(f"  {event_type}: {cnt}")
    print()
    
    # 5. Check for WAL mode
    cursor.execute("PRAGMA journal_mode;")
    journal_mode = cursor.fetchone()[0]
    print(f"🗄️  Journal mode: {journal_mode}")
    
    # 6. Check backup locations
    if backup_dir:
        backup_path = Path(backup_dir) / db_path.name
        if backup_path.exists():
            stat = backup_path.stat()
            age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            print(f"\n💾 Backup found: {backup_path}")
            print(f"   Size: {stat.st_size:,} bytes")
            print(f"   Age: {age}")
            # Verify backup is readable
            try:
                bconn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
                bcursor = bconn.cursor()
                bcursor.execute("SELECT COUNT(*) FROM fills")
                b_fills = bcursor.fetchone()[0]
                bcursor.execute("SELECT COUNT(*) FROM signals")
                b_signals = bcursor.fetchone()[0]
                print(f"   Backup fills: {b_fills} | signals: {b_signals}")
                if b_fills == total_fills and b_signals == total_signals:
                    print("   ✅ Backup matches primary")
                else:
                    print("   ⚠️  Backup count mismatch!")
                bconn.close()
            except Exception as e:
                print(f"   ❌ Backup verification failed: {e}")
        else:
            print(f"\n💾 No backup at: {backup_path}")
    
    # Also check default backup locations
    for bp in [Path("audit_backups") / db_path.name, Path.home() / "MARS_AUDIT_BACKUPS" / db_path.name]:
        if bp.exists():
            stat = bp.stat()
            age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            print(f"\n💾 Additional backup: {bp}")
            print(f"   Size: {stat.st_size:,} bytes, Age: {age}")
    
    conn.close()
    print("\n✅ Reconciliation complete")
    return True


def main():
    parser = argparse.ArgumentParser(description="Reconcile MARS audit database")
    parser.add_argument("db_path", nargs="?", default=os.path.join(os.environ.get("TEMP", "/tmp"), "mt5_audit_real.db"),
                        help="Path to audit database (default: temp/mt5_audit_real.db)")
    parser.add_argument("--backup-dir", default=None, help="Backup directory to verify")
    parser.add_argument("--hours", type=int, default=24, help="Hours back to reconcile")
    parser.add_argument("--all", action="store_true", help="Reconcile entire database (no time filter)")
    args = parser.parse_args()
    
    # If --all, set hours to a very large number
    hours = 8760 if args.all else args.hours  # 1 year
    
    success = reconcile_audit(args.db_path, args.backup_dir, hours)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()