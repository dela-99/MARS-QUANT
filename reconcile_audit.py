"""
MT5 Broker Truth Reconciliation Script
Compares MT5 deal history against internal audit log.
Run after every session to verify audit completeness.
"""
import sys
sys.path.insert(0, 'C:/Users/RIDGE/OneDrive/Desktop/MARS-QUANT')
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

from mars.core.config import MT5Config
from mars.apps.trading.mt5_executor import MT5ConnectionManager


def get_mt5_deals(session_start: datetime, session_end: datetime = None):
    """Pull all deals from MT5 history for the given time window."""
    config = MT5Config()
    conn_manager = MT5ConnectionManager(config)
    if not conn_manager.connect():
        raise RuntimeError("Failed to connect to MT5")
    
    mt5 = conn_manager.mt5
    if session_end is None:
        session_end = datetime.now()
    
    deals = mt5.history_deals_get(session_start, session_end)
    if deals is None:
        return []
    
    result = []
    for deal in deals:
        if deal.symbol == 'XAUUSDm' and deal.magic == 123456:
            result.append({
                'ticket': deal.ticket,
                'order': deal.order,
                'time': datetime.fromtimestamp(deal.time),
                'type': deal.type,  # 0=buy, 1=sell
                'entry': deal.entry,  # 0=entry, 1=exit
                'volume': deal.volume,
                'price': deal.price,
                'profit': deal.profit,
                'comment': deal.comment,
                'position_id': deal.position_id,
            })
    return result


def get_audit_fills(session_start: datetime, session_end: datetime = None):
    """Pull all fills from SQLite audit log for the given time window."""
    if session_end is None:
        session_end = datetime.now()
    
    conn = sqlite3.connect(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, ticket, order_id, symbol, direction,
               requested_lots, filled_lots, signal_price, filled_price,
               slippage_points, slippage_pct, size_slippage, spread_at_fill,
               comment
        FROM fills
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp
    """, (session_start.isoformat(), session_end.isoformat()))
    
    fills = cursor.fetchall()
    conn.close()
    
    result = []
    for f in fills:
        result.append({
            'timestamp': datetime.fromisoformat(f[0]),
            'ticket': f[1],
            'order_id': f[2],
            'symbol': f[3],
            'direction': f[4],
            'requested_lots': f[5],
            'filled_lots': f[6],
            'signal_price': f[7],
            'filled_price': f[8],
            'slippage_points': f[9],
            'slippage_pct': f[10],
            'size_slippage': f[11],
            'spread_at_fill': f[12],
            'comment': f[13],
        })
    return result


def reconcile(session_start: datetime, session_end: datetime = None):
    """Reconcile MT5 deals vs audit log."""
    print(f"\n{'='*60}")
    print(f"RECONCILIATION: {session_start} to {session_end or datetime.now()}")
    print(f"{'='*60}")
    
    mt5_deals = get_mt5_deals(session_start, session_end)
    audit_fills = get_audit_fills(session_start, session_end)
    
    print(f"\nMT5 Deals (entries only): {len([d for d in mt5_deals if d['entry'] == 0])}")
    print(f"Audit Fills: {len(audit_fills)}")
    
    # Filter to entry deals only (entry=0)
    mt5_entries = [d for d in mt5_deals if d['entry'] == 0]
    
    # Match by ticket (MT5 deal ticket = audit ticket)
    mt5_tickets = {d['ticket']: d for d in mt5_entries}
    audit_tickets = {f['ticket']: f for f in audit_fills}
    
    print(f"\n--- IN MT5 BUT NOT IN AUDIT ---")
    missing_in_audit = []
    for ticket, deal in mt5_tickets.items():
        if ticket not in audit_tickets:
            missing_in_audit.append(deal)
            print(f"  MISSING: Ticket={ticket}, Time={deal['time']}, "
                  f"{'BUY' if deal['type']==0 else 'SELL'} @ {deal['price']}, "
                  f"Vol={deal['volume']}, Comment={deal['comment']}")
    
    print(f"\n--- IN AUDIT BUT NOT IN MT5 ---")
    extra_in_audit = []
    for ticket, fill in audit_tickets.items():
        if ticket not in mt5_tickets:
            extra_in_audit.append(fill)
            print(f"  EXTRA: Ticket={ticket}, Time={fill['timestamp']}, "
                  f"{fill['direction']} @ {fill['filled_price']}, "
                  f"Comment={fill['comment']}")
    
    print(f"\n--- MATCHED ---")
    matched = 0
    for ticket in set(mt5_tickets.keys()) & set(audit_tickets.keys()):
        matched += 1
        deal = mt5_tickets[ticket]
        fill = audit_tickets[ticket]
        price_diff = abs(deal['price'] - fill['filled_price'])
        if price_diff > 0.01:
            print(f"  PRICE MISMATCH: Ticket={ticket}, MT5={deal['price']}, Audit={fill['filled_price']}, Diff={price_diff}")
    
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(mt5_entries)} MT5 entries, {len(audit_fills)} audit fills")
    print(f"  Matched: {matched}")
    print(f"  Missing in audit: {len(missing_in_audit)}")
    print(f"  Extra in audit: {len(extra_in_audit)}")
    
    if len(missing_in_audit) == 0 and len(extra_in_audit) == 0:
        print("  ✅ ZERO DISCREPANCIES - Audit log matches broker truth!")
    else:
        print("  ❌ DISCREPANCIES FOUND - Investigation required")
    print(f"{'='*60}\n")
    
    return {
        'mt5_count': len(mt5_entries),
        'audit_count': len(audit_fills),
        'matched': matched,
        'missing_in_audit': missing_in_audit,
        'extra_in_audit': extra_in_audit,
        'zero_discrepancy': len(missing_in_audit) == 0 and len(extra_in_audit) == 0,
    }


if __name__ == '__main__':
    # Reconcile the new session (~03:12 UTC)
    session_start = datetime(2026, 9, 10, 3, 10, 0)
    session_end = datetime.now()
    
    result = reconcile(session_start, session_end)
    
    # Exit with error code if discrepancies found
    if not result['zero_discrepancy']:
        sys.exit(1)