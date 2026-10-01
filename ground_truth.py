"""
Step 1 — Query MT5 directly for ground truth on every position.

Independent of the app / audit DB. Uses raw mt5.history_deals_get()
and mt5.positions_get() against account #476944496.
"""
import MetaTrader5 as mt5
import json, os
from datetime import datetime, timezone, timedelta

ACCOUNT = 476944496

print("=" * 80)
print(f"MT5 GROUND TRUTH — Account #{ACCOUNT}")
print("=" * 80)

assert mt5.initialize(), f"MT5 init failed: {mt5.last_error()}"

acct = mt5.account_info()
if not acct:
    print(f"Failed to get account info: {mt5.last_error()}")
    raise SystemExit(1)

print(f"  Account:        #{acct.login}")
print(f"  Trade mode:     {acct.trade_mode}  (0=DEMO, others=REAL/live)")
print(f"  Balance:        ${acct.balance:,.2f}")
print(f"  Equity:         ${acct.equity:,.2f}")
print(f"  Currency:       {acct.currency}")
print(f"  Leverage:       1:{acct.leverage}")
# Get server time from a tick instead
_t = mt5.symbol_info_tick("XAUUSDm")
print(f"  Server time:    {datetime.fromtimestamp(_t.time, tz=timezone.utc).isoformat()}  (from XAUUSDm tick)")
print()

# --- Open positions (still live in broker) ---
print("=" * 80)
print("OPEN POSITIONS — currently held per broker")
print("=" * 80)
positions = mt5.positions_get()
if positions is None:
    print(f"  positions_get() failed: {mt5.last_error()}")
elif len(positions) == 0:
    print("  (none — broker reports zero open positions)")
else:
    for i, p in enumerate(positions, 1):
        print(f"  [{i}] ticket={p.ticket}  {p.symbol}  {p.type_name}  "
              f"volume={p.volume}  open_price={p.price_open}  "
              f"sl={p.sl}  tp={p.tp}  profit=${p.profit:+.2f}  "
              f"opened={datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat()}")

# --- History of all deals (entry + exit) for the last 14 days ---
print()
print("=" * 80)
print("DEAL HISTORY (last 14 days) — every fill the broker recorded")
print("=" * 80)
date_from = datetime.now(tz=timezone.utc) - timedelta(days=14)
date_to = datetime.now(tz=timezone.utc) + timedelta(hours=1)
deals = mt5.history_deals_get(date_from, date_to)
if deals is None:
    print(f"  history_deals_get() failed: {mt5.last_error()}")
elif len(deals) == 0:
    print("  (no deals in last 14 days)")
else:
    print(f"  Total deals: {len(deals)}")
    print()
    print(f"  {'deal_id':>12}  {'order':>10}  {'pos_id':>10}  "
          f"{'symbol':10}  {'type':12}  {'entry':>2}  "
          f"{'volume':>8}  {'price':>10}  {'profit':>10}  {'time':19}  {'reason':16}")
    print("  " + "-" * 138)
    for d in deals:
        dtime = datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(timespec='seconds')
        type_name = ("BUY" if d.type == 0 else
                     "SELL" if d.type == 1 else
                     f"type={d.type}")
        entry = ("in" if d.entry == 0 else
                 "out" if d.entry == 1 else
                 "inout" if d.entry == 2 else
                 f"entry={d.entry}")
        reason = ("CLIENT" if d.reason == 0 else
                  "EXPERT" if d.reason == 3 else
                  "MOBILE" if d.reason == 4 else
                  "WEB" if d.reason == 5 else
                  "SL" if d.reason == 6 else
                  "TP" if d.reason == 7 else
                  "SO" if d.reason == 8 else
                  f"reason={d.reason}")
        # TradeDeal uses .ticket (not .deal)
        print(f"  {d.ticket:>12}  {d.order:>10}  {d.position_id:>10}  "
              f"{d.symbol:10}  {type_name:12}  {entry:>2}  "
              f"{d.volume:>8.2f}  {d.price:>10.3f}  {d.profit:>+10.2f}  "
              f"{d.time:>10}  {reason:16}")
        print(f"  {'':>12}  {'':>10}  {'':>10}  {'':10}  {'':12}  {'':>2}  "
              f"{'':>8}  {'':>10}  {'':>10}  {dtime:19}  {'':16}")

# --- Cross-reference: for each ticket, find the entry + exit deals ---
print()
print("=" * 80)
print("POSITION-BY-POSITION RECONCILIATION")
print("=" * 80)
if deals is None or len(deals) == 0:
    print("  (no deals to reconcile)")
else:
    # Group deals by position_id
    by_pos: dict[int, list] = {}
    for d in deals:
        by_pos.setdefault(d.position_id, []).append(d)
    for pos_id, pds in sorted(by_pos.items()):
        pds.sort(key=lambda d: d.time)
        entry_deals = [d for d in pds if d.entry == 0]
        exit_deals = [d for d in pds if d.entry == 1]
        total_profit = sum(d.profit for d in exit_deals)
        commission = sum(d.commission for d in pds)
        swap = sum(d.swap for d in pds)
        state = "OPEN" if not exit_deals else "CLOSED"
        print(f"\n  Position #{pos_id}  state={state}")
        print(f"    entry deals:  {len(entry_deals)}")
        for d in entry_deals:
            print(f"      deal_id={d.ticket}  order={d.order}  {d.symbol}  type={d.type}  vol={d.volume}  price={d.price}  time={d.time}")
        print(f"    exit deals:   {len(exit_deals)}")
        for d in exit_deals:
            print(f"      deal_id={d.ticket}  order={d.order}  {d.symbol}  type={d.type}  vol={d.volume}  price={d.price}  profit={d.profit:+.2f}  reason={d.reason}  time={d.time}")
        print(f"    realized profit: ${total_profit:+.2f}  commission: ${commission:+.2f}  swap: ${swap:+.2f}  NET: ${total_profit + commission + swap:+.2f}")

# --- Cross-reference audit DB fills vs MT5 ground truth ---
print()
print("=" * 80)
print("AUDIT-DB FILLS CROSS-REFERENCED AGAINST MT5")
print("=" * 80)

import sqlite3, tempfile
DB = os.path.join(tempfile.gettempdir(), "mt5_audit_real.db")
if os.path.exists(DB):
    conn = sqlite3.connect(DB, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, timestamp, ticket, symbol, direction, filled_lots,
               filled_price, profit, mt5_ticket, retcode
        FROM fills ORDER BY timestamp
    """)
    db_fills = cur.fetchall()
    conn.close()
    print(f"\n  Audit DB has {len(db_fills)} fill row(s):")
    if db_fills:
        print(f"  {'db_id':>5}  {'db_ts':19}  {'ticket':>12}  {'symbol':10}  "
              f"{'dir':4}  {'lots':>6}  {'db_price':>10}  {'db_profit':>10}  {'retcode':>7}")
        print("  " + "-" * 110)
        for r in db_fills:
            print(f"  {r[0]:>5}  {r[1]:19}  {r[2] or 'NULL':>12}  {r[3] or 'NULL':10}  "
                  f"{r[4] or 'NULL':4}  {r[5] or 0:>6.2f}  {r[6] or 0:>10.3f}  {r[7] or 0:>+10.2f}  "
                  f"{r[9] or 0:>7}")

    # For each audit fill, find the corresponding MT5 deal and the closing deal
    print(f"\n  Ground truth cross-reference:")
    mt5_deals = {d.ticket: d for d in (deals or [])}
    for r in db_fills:
        db_id, db_ts, ticket, symbol, direction, lots, price, profit, mt5_ticket, retcode = r
        if mt5_ticket and mt5_ticket in mt5_deals:
            entry = mt5_deals[mt5_ticket]
            # Find the exit deal for this position
            exits = [d for d in (deals or []) if d.position_id == entry.position_id and d.entry == 1]
            exit_str = "none (position still open or never opened)"
            if exits:
                ex = exits[0]
                exit_str = (f"closed by deal {ex.ticket} @ {ex.price} "
                            f"profit={ex.profit:+.2f} reason={ex.reason} "
                            f"at {datetime.fromtimestamp(ex.time, tz=timezone.utc).isoformat(timespec='seconds')}")
            print(f"  audit row {db_id} (ticket={mt5_ticket}): entry confirmed; {exit_str}")
        elif ticket and ticket in mt5_deals:
            entry = mt5_deals[ticket]
            exits = [d for d in (deals or []) if d.position_id == entry.position_id and d.entry == 1]
            exit_str = "none"
            if exits:
                ex = exits[0]
                exit_str = (f"closed by deal {ex.ticket} @ {ex.price} "
                            f"profit={ex.profit:+.2f}")
            print(f"  audit row {db_id} (ticket={ticket}, no mt5_ticket stored): entry found; {exit_str}")
        else:
            print(f"  audit row {db_id} (ticket={ticket}, mt5_ticket={mt5_ticket}): NOT FOUND in MT5 history")
else:
    print(f"  Audit DB not found at {DB}")

# --- Also: history orders for full picture ---
print()
print("=" * 80)
print("ORDER HISTORY (last 14 days) — what the broker recorded as orders")
print("=" * 80)
orders = mt5.history_orders_get(date_from, date_to)
if orders is None:
    print(f"  history_orders_get() failed: {mt5.last_error()}")
elif len(orders) == 0:
    print("  (no orders in last 14 days)")
else:
    for o in orders:
        st = ("HISTORY" if hasattr(o, 'state') and o.state else "?")
        otime = datetime.fromtimestamp(o.time_setup, tz=timezone.utc).isoformat(timespec='seconds')
        print(f"  order={o.order}  ticket={o.ticket}  {o.symbol}  type={o.type}  "
              f"vol={o.volume_initial}  state={o.state}  setup={otime}  "
              f"filled={o.volume_current}/{o.volume_initial}")

mt5.shutdown()