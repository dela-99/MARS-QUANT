"""Step 2 (retry): MT5 history_deals_get needs date range set on the terminal.

Try alternative queries:
1. Set history range via history_deals_get(date_from, date_to)
2. Try history_orders_get first to find the order, then deals
3. Iterate all deals in window and search by symbol/time
"""
import sys
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

from datetime import datetime, timezone
import MetaTrader5 as mt5

if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

# Account info
ai = mt5.account_info()
print(f"Account: #{ai.login}, balance=${ai.balance}, equity=${ai.equity}")
print()

# Check current open positions
positions = mt5.positions_get()
print(f"Open positions: {len(positions) if positions else 0}")
for p in (positions or []):
    print(f"  {p.symbol} {p.ticket} vol={p.volume} px={p.price_open} time={datetime.fromtimestamp(p.time)}")
print()

# Set the date range — earliest fill is 2026-10-01, latest is 2026-10-05
date_from = datetime(2026, 9, 30, tzinfo=timezone.utc)
date_to = datetime(2026, 10, 7, tzinfo=timezone.utc)

# Try history_deals_get(date_from, date_to) — no ticket filter
all_deals = mt5.history_deals_get(date_from, date_to)
print(f"history_deals_get({date_from}, {date_to}) → {len(all_deals) if all_deals else 0} deals")
print()

# Look at all deals with our magic (123456)
all_deals_with_magic = [d for d in (all_deals or []) if getattr(d, 'magic', 0) == 123456]
print(f"  with magic=123456: {len(all_deals_with_magic)}")

# Look at all deals with comment='ok'
all_deals_ok = [d for d in (all_deals or []) if getattr(d, 'comment', '') == 'ok']
print(f"  with comment='ok': {len(all_deals_ok)}")
print()

# Find the 7 specific tickets
target_tickets = {3307251388, 3307254709, 3316210022, 3316462923,
                  3325045333, 3325060832, 3325121545}
hits = []
for d in (all_deals or []):
    if d.ticket in target_tickets:
        hits.append(d)
print(f"Direct ticket hits in date range: {len(hits)}")
for d in hits:
    print(f"  ticket={d.ticket} pos={d.position_id} {d.symbol} "
          f"{'BUY' if d.type==0 else 'SELL'} vol={d.volume} px={d.price} "
          f"entry={'ENTRY' if d.entry==0 else 'EXIT'} "
          f"profit={d.profit} comm={d.commission} swap={d.swap} "
          f"time={datetime.fromtimestamp(d.time).isoformat()} "
          f"reason={getattr(d, 'reason', None)}")

# Also look at the deal by DEAL ORDER (not by position) — try history_orders_get
print()
print("=== Try history_orders_get() for the 7 tickets ===")
# For these tickets, fill.ticket is the DEAL ticket, fill.order_id is the ORDER ticket
# So we need to find the orders first, then their deals
# Actually, let's just look at all orders and find any with order_id matching what we expect

# From the audit DB, get the order_id for each ticket
import sqlite3
DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
ticket_to_order = {r["ticket"]: r["order_id"] for r in c.execute(
    "SELECT ticket, order_id FROM fills WHERE is_closed=0"
).fetchall()}
print(f"order_id mapping: {ticket_to_order}")

# Now query orders
target_orders = set(ticket_to_order.values())
all_orders = mt5.history_orders_get(date_from, date_to)
print(f"history_orders_get({date_from}, {date_to}) → {len(all_orders) if all_orders else 0} orders")
matched_orders = [o for o in (all_orders or []) if o.ticket in target_orders]
print(f"  matching our 7: {len(matched_orders)}")
for o in matched_orders:
    print(f"    order ticket={o.ticket}  state={o.state}  "
          f"time_setup={datetime.fromtimestamp(o.time_setup).isoformat()}  "
          f"position_id={o.position_id}")

# Now for each matched order, get its deals
print()
print("=== For each matched order, history_deals_get(position=position_id) ===")
for o in matched_orders:
    pos_id = o.position_id
    deals = mt5.history_deals_get(position=pos_id)
    print(f"\n  order={o.ticket}  position_id={pos_id}  → {len(deals) if deals else 0} deals")
    if deals:
        for d in deals:
            print(f"    deal ticket={d.ticket}  {d.symbol}  "
                  f"{'BUY' if d.type==0 else 'SELL'}  vol={d.volume}  "
                  f"px={d.price}  entry={'ENTRY' if d.entry==0 else 'EXIT'}  "
                  f"profit={d.profit}  comm={d.commission}  swap={d.swap}  "
                  f"time={datetime.fromtimestamp(d.time).isoformat()}  "
                  f"reason={getattr(d, 'reason', None)}")

mt5.shutdown()