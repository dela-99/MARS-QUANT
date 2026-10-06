"""Step 3+4: Re-derive TRUE exit_reason for every closed fill using
ground-truth (exit_price vs filled_sl/filled_tp comparison), then
cross-check against corrected reason_map.

Authoritative MT5 DEAL_REASON_*:
  0=client 1=mobile 2=web 3=expert 4=sl_hit 5=tp_hit 6=stopout
  7=rollover 8=vmargin 9=split

Ground truth:
  exit_price == filled_sl  → real SL hit  → 'sl_hit'
  exit_price == filled_tp  → real TP hit  → 'tp_hit'
  otherwise               → manual close  → use corrected reason code
                            (mobile/web/client/expert)

A tolerance is needed because some brokers round SL/TP to whole-pip values
that may differ by a tiny amount from the requested SL/TP.
"""
import sys, os
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

import sqlite3
import MetaTrader5 as mt5

DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"

# Connect MT5 to fetch the actual deal.reason values for each ticket
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    raise SystemExit(1)

# Get all deals for our window
from datetime import datetime, timezone
date_from = datetime(2026, 9, 27, tzinfo=timezone.utc)
date_to = datetime(2026, 10, 7, tzinfo=timezone.utc)
all_deals = mt5.history_deals_get(date_from, date_to)
mt5.shutdown()

# Build a map: position_id → (exit_reason_code, exit_price, profit)
deal_index = {}
for d in (all_deals or []):
    if getattr(d, 'entry', None) == 1:  # exit deals
        deal_index.setdefault(d.position_id, []).append({
            "reason_code": d.reason,
            "exit_price": float(d.price),
            "profit": float(d.profit),
            "exit_time_ex": datetime.fromtimestamp(d.time).isoformat(),
            "deal_ticket": int(d.ticket),
        })

# Corrected reason map
REASON_MAP = {
    0: "client", 1: "mobile", 2: "web", 3: "expert",
    4: "sl_hit", 5: "tp_hit", 6: "stopout",
    7: "rollover", 8: "vmargin", 9: "split",
}

def pip_size_for(symbol):
    return {
        "XAUUSDm": 0.01,
        "USDJPYm": 0.01,
        "EURUSDm": 0.0001,
        "EURGBPm": 0.0001,
    }.get(symbol, 0.0001)

def derive_true_exit_reason(symbol, filled_price, filled_sl, filled_tp, exit_price, reason_code):
    """Return ('sl_hit' | 'tp_hit' | <reason_map[code]>, evidence_str)."""
    pip = pip_size_for(symbol)
    tol = pip * 0.5  # within half a pip — accounts for broker rounding
    if filled_sl and exit_price is not None and abs(exit_price - filled_sl) <= tol:
        return "sl_hit", f"exit_price {exit_price} == filled_sl {filled_sl} (±{tol:.4f})"
    if filled_tp and exit_price is not None and abs(exit_price - filled_tp) <= tol:
        return "tp_hit", f"exit_price {exit_price} == filled_tp {filled_tp} (±{tol:.4f})"
    # Manual close — use corrected reason map
    return REASON_MAP.get(reason_code, f"reason={reason_code}"), \
        f"exit_price {exit_price} ≠ sl {filled_sl} nor tp {filled_tp}; reason_code={reason_code}"

# Read all fills, re-derive, write back
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=== Re-derived exit reasons (ground truth: exit_price vs filled_sl/tp) ===\n")
print(f"{'id':>3} {'ticket':>10} {'dir':>5} {'symbol':>10} {'entry':>10} "
      f"{'sl':>10} {'tp':>10} {'exit_px':>10} {'rc':>3} {'old_reason':>12} "
      f"{'true_reason':>12} {'agree':>5} {'evidence'}")
print("-" * 160)

updates = []
for r in c.execute(
    "SELECT id, ticket, symbol, direction, filled_price, filled_sl, filled_tp, "
    "exit_price, exit_reason, position_id "
    "FROM fills WHERE is_closed=1 ORDER BY timestamp"
).fetchall():
    d = dict(r)
    sym = d["symbol"]
    fp = d["filled_price"]
    sl = d["filled_sl"]
    tp = d["filled_tp"]
    exit_px = d["exit_price"]
    rc = None
    if d["position_id"] and d["position_id"] in deal_index:
        rc = deal_index[d["position_id"]][0]["reason_code"]
    elif d["ticket"] in deal_index:
        # legacy fallback (position_id IS ticket for these)
        rc = deal_index[d["ticket"]][0]["reason_code"]
    true_reason, evidence = derive_true_exit_reason(sym, fp, sl, tp, exit_px, rc)
    old = d["exit_reason"] or ""
    agree = "✓" if true_reason == old else "✗"
    print(f"{d['id']:>3} {d['ticket']:>10} {d['direction']:>5} {sym:>10} "
          f"{fp if fp else 0:>10.4f} "
          f"{sl if sl else 0:>10.4f} "
          f"{tp if tp else 0:>10.4f} "
          f"{exit_px if exit_px else 0:>10.4f} "
          f"{rc if rc is not None else '?':>3} "
          f"{old:>12} {true_reason:>12} {agree:>5}  {evidence}")
    if true_reason != old:
        updates.append((true_reason, d["id"]))

print(f"\n=== Updates needed: {len(updates)} ===")
for reason, rid in updates:
    print(f"  id={rid} → '{reason}'")

# Apply updates automatically (no interactive prompt)
print()
if updates:
    for reason, rid in updates:
        c.execute("UPDATE fills SET exit_reason=? WHERE id=?", (reason, rid))
    c.commit()
    print(f"  ✓ Wrote {len(updates)} updates")
else:
    print("  No updates needed")
c.close()