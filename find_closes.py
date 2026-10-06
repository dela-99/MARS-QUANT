"""Step 2: For each of the 7 unmatched fills, query MT5 history to find the actual close.

For each ticket:
  - Get the deal via history_deals_get(ticket=ticket)
  - From the deal, extract position_id
  - Query history_deals_get(position=position_id) to find the exit deal(s)
  - Filter for entry=1 (exit deals)
"""
import sys
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

import sqlite3
from datetime import datetime, timedelta

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"

# 7 unmatched fills from list_unmatched.py
UNMATCHED = [
    (3307251388, "XAUUSDm", "SELL", 0.01, "2026-10-01T00:29:16"),
    (3307254709, "XAUUSDm", "SELL", 0.01, "2026-10-01T00:30:02"),
    (3316210022, "XAUUSDm", "BUY",  0.01, "2026-10-02T12:31:38"),
    (3316462923, "XAUUSDm", "BUY",  0.01, "2026-10-02T12:35:03"),
    (3325045333, "USDJPYm", "BUY",  0.06, "2026-10-05T12:41:12"),
    (3325060832, "USDJPYm", "BUY",  0.06, "2026-10-05T12:45:01"),
    (3325121545, "USDJPYm", "BUY",  0.01, "2026-10-05T12:53:52"),
]

# Connect to MT5
import MetaTrader5 as mt5
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    sys.exit(1)
print("MT5 connected.")
print(f"Account: #{mt5.account_info().login}")
print()

def show_deal(d):
    """Print key fields of a deal."""
    return {
        "ticket": d.ticket,
        "order": d.order,
        "position_id": d.position_id,
        "symbol": d.symbol,
        "type": "BUY" if d.type == 0 else "SELL",
        "entry": "ENTRY" if d.entry == 0 else "EXIT",
        "volume": d.volume,
        "price": d.price,
        "commission": d.commission,
        "swap": d.swap,
        "profit": d.profit,
        "time": datetime.fromtimestamp(d.time).isoformat(),
        "reason": getattr(d, 'reason', None),
    }

results = []
for ticket, symbol, direction, lots, entry_time in UNMATCHED:
    print(f"=== ticket={ticket}  {symbol}  {direction}  {lots} lots  entry={entry_time} ===")

    # Step 2a: get the entry deal itself
    deals = mt5.history_deals_get(ticket=ticket)
    if not deals or len(deals) == 0:
        print(f"  history_deals_get(ticket={ticket}) → empty/NONE")
        results.append({"ticket": ticket, "found_entry_deal": False, "position_id": None})
        continue

    entry_deal = deals[0]
    entry_info = show_deal(entry_deal)
    pos_id_from_entry = entry_info["position_id"]
    print(f"  entry deal: position_id={pos_id_from_entry}, time={entry_info['time']}, profit={entry_info['profit']}")
    results.append({
        "ticket": ticket, "found_entry_deal": True,
        "position_id": pos_id_from_entry,
        "entry_time": entry_info["time"],
    })

    # Step 2b: get all deals for this position (entry + exit)
    if pos_id_from_entry:
        pos_deals = mt5.history_deals_get(position=pos_id_from_entry)
    else:
        pos_deals = []
    print(f"  history_deals_get(position={pos_id_from_entry}) → {len(pos_deals) if pos_deals else 0} deals")

    exit_deal = None
    if pos_deals:
        for d in pos_deals:
            info = show_deal(d)
            tag = "EXIT" if info["entry"] == "EXIT" else "ENTRY"
            print(f"    [{tag}] {info['type']:>4}  px={info['price']}  vol={info['volume']}  "
                  f"profit={info['profit']}  swap={info['swap']}  comm={info['commission']}  "
                  f"time={info['time']}  reason={info['reason']}")
            if info["entry"] == "EXIT":
                if exit_deal is None or info["time"] > exit_deal["time"]:
                    exit_deal = info
        if exit_deal:
            results[-1]["exit_deal"] = exit_deal
            results[-1]["exit_found"] = True
        else:
            results[-1]["exit_found"] = False
    print()

mt5.shutdown()

print("=== Summary ===")
for r in results:
    flag = "✓" if r.get("exit_found") else "✗"
    print(f"  {flag} ticket={r['ticket']}  pos_id={r.get('position_id')}  "
          f"exit_found={r.get('exit_found', 'N/A')}")