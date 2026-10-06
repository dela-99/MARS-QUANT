"""Step 1: get authoritative MT5 deal-reason constants and current reason_map for comparison."""
import MetaTrader5 as mt5

if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    raise SystemExit(1)

print("=== MT5 DEAL_REASON_* constants (authoritative) ===")
# Get all DEAL_REASON_* attributes
for attr in sorted(dir(mt5)):
    if "REASON" in attr.upper() or "DEAL" in attr.upper():
        try:
            val = getattr(mt5, attr)
            print(f"  mt5.{attr:30s} = {val}")
        except Exception:
            pass

print()
print("=== Current reason_map in log_close_fill() ===")
# Read the source file to show the current mapping
import re
src = open(r"C:\Users\RIDGE\MARS-QUANT\mars\apps\trading\mt5_executor.py", encoding="utf-8").read()
m = re.search(r"reason_map\s*=\s*\{([^}]+)\}", src)
if m:
    print(m.group(0))

mt5.shutdown()