"""Verify compute_expectancy_breakdown() numbers with corrected tags."""
import sys
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

for m in list(sys.modules.keys()):
    if "dashboard" in m or "mars" in m:
        del sys.modules[m]

import dashboard
bd = dashboard.compute_expectancy_breakdown()

print(f"=== compute_expectancy_breakdown() with corrected tags ===")
print(f"source: {bd['source']}\n")

for k in ("all", "system", "manual", "degraded"):
    m = bd.get(k, {})
    print(f"--- {k} ---")
    print(f"  is_empty:       {m.get('is_empty')}")
    print(f"  n_trades:       {m.get('n_trades')}")
    print(f"  win_rate:       {m.get('win_rate')}")
    print(f"  expectancy_R:   {m.get('expectancy_R')}")
    print(f"  profit_factor:  {m.get('profit_factor')}")
    print(f"  gross_profit_usd: {m.get('gross_profit_usd')}")
    print(f"  gross_loss_usd:   {m.get('gross_loss_usd')}")
    print(f"  breakdown:      {m.get('breakdown')}")
    print()