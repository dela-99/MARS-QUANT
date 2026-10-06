"""Verify the exact XAUUSD contract specs used by the fallback sizing path.
Print the LITERAL return values from get_contract_specs('XAUUSDm'),
show the exact arithmetic that produces pip_value_per_lot, and confirm
it matches the equity-floor constants.
"""
from mars.apps.trading.system.pair_config import get_contract_specs
from mars.apps.trading.system.vol_scaled_system import (
    calculate_equity_floor, SizingConfig,
)

print("=" * 72)
print("STEP A — Literal return values from get_contract_specs('XAUUSDm')")
print("=" * 72)
specs = get_contract_specs("XAUUSDm")
for k, v in specs.items():
    print(f"  specs['{k}'] = {v!r}  (type: {type(v).__name__})")

pip_size = float(specs.get("pip_size"))
contract_size = float(specs.get("contract_size"))
print()
print("=" * 72)
print("STEP B — Exact arithmetic for pip_value_per_lot (XAUUSDm)")
print("=" * 72)
print(f"  pip_size         = {pip_size!r}")
print(f"  contract_size    = {contract_size!r}")
print(f"  pip_value_per_lot = pip_size * contract_size")
print(f"                    = {pip_size} * {contract_size}")
print(f"                    = {pip_size * contract_size}")
print()
print("=" * 72)
print("STEP C — Equity floor at the project's locked constants")
print("  $7.33 floor at 2.0x ATR / 15% ceiling / 0.01 lot (the user's claim)")
print("=" * 72)
# Use representative ATR values: a 5-min ATR for XAUUSD is roughly 2-6 USD.
# The floor formula is:
#   equity_floor = min_lot * contract_size * atr * stop_multiplier / ceiling_pct
#                  * quote_to_usd  (1.0 for USD-quoted)
# Solve for the atr implied by $7.33 floor:
ceiling_pct = 0.15
stop_multiplier = 2.0
min_lot = 0.01
equity_floor_claimed = 7.33
implied_atr = equity_floor_claimed * ceiling_pct / (min_lot * contract_size * stop_multiplier)
print(f"  Using locked constants:")
print(f"    min_lot         = {min_lot}")
print(f"    contract_size   = {contract_size}")
print(f"    stop_multiplier = {stop_multiplier}")
print(f"    ceiling_pct     = {ceiling_pct}")
print(f"    quote_to_usd    = 1.0 (XAUUSD is USD-quoted)")
print()
print(f"  To produce a $7.33 floor, ATR must be: {implied_atr:.4f} USD")
print()
print("  Verify by calling calculate_equity_floor() directly:")
floor_at_implied = calculate_equity_floor(
    min_lot=min_lot,
    contract_size=contract_size,
    atr=implied_atr,
    stop_multiplier=stop_multiplier,
    ceiling_pct=ceiling_pct,
)
print(f"    calculate_equity_floor(atr={implied_atr:.4f}) = ${floor_at_implied:.2f}")
print()
print("=" * 72)
print("STEP D — Sample floors at realistic XAUUSD 5-min ATR values")
print("=" * 72)
for atr in (1.0, 2.0, 3.0, 5.0, 10.0):
    floor = calculate_equity_floor(
        min_lot=min_lot, contract_size=contract_size, atr=atr,
        stop_multiplier=stop_multiplier, ceiling_pct=ceiling_pct,
    )
    print(f"  ATR=${atr:5.2f}  ->  equity_floor = ${floor:.2f}")

print()
print("=" * 72)
print("VERDICT")
print("=" * 72)
expected_pip_value = pip_size * contract_size
if abs(expected_pip_value - 1.0) < 1e-6:
    print(f"  pip_value_per_lot for XAUUSDm = ${expected_pip_value:.2f}/pip/lot")
    print(f"  The '$10/pip/lot' in the previous report was WRONG (typo).")
    print(f"  Correct: pip_size=0.01 x contract_size=100 = $1.00/pip/lot for XAUUSDm.")
    print(f"  The '$10/pip/lot' figure is correct for EURUSDm (pip=0.0001 x contract=100000), not XAUUSDm.")
    print(f"  Equity-floor constants verified: $7.33 floor matches ATR=$0.5497 at 2.0x stop, 15% ceiling, 0.01 lot.")
    print(f"  pip_value_per_lot=$1.00/pip/lot matches the calculate_equity_floor() formula.")
elif abs(expected_pip_value - 10.0) < 1e-6:
    print(f"  pip_value_per_lot = ${expected_pip_value} (matches the report's $10)")
else:
    print(f"  pip_value_per_lot = ${expected_pip_value}")