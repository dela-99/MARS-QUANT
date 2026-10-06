"""Reproduce 12:53 trade conditions and run both sizing paths.

Trade 3325121545:
  filled_price=158.233, filled_sl=157.906, signal_price=158.222
  requested_lots=0.01, filled_lots=0.01
  equity at time = $192.63

This script:
1. Reconstructs the signal conditions.
2. Runs the FIXED GARCH sizer path (post timestamp-promotion fix).
3. Runs the FALLBACK path (contract_specs-based).
4. Prints the pre-floor position_size from each path.
"""
import sys, os
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

import pandas as pd
import numpy as np

# Trade conditions
entry_price = 158.233   # filled_price (broker ASK)
signal_price = 158.222  # signal's reference price (BID close)
stop_price = 157.906
take_profit = 159.170
equity = 192.63

print(f"=== 12:53 trade conditions ===")
print(f"  signal_price (BID close): {signal_price}")
print(f"  filled_price (broker ASK): {entry_price}   ← entry slippage = {(entry_price-signal_price)/0.01:.2f} pips")
print(f"  stop_price:  {stop_price}   distance from signal = {(signal_price-stop_price)/0.01:.2f} pips")
print(f"  take_profit: {take_profit} distance from signal = {(take_profit-signal_price)/0.01:.2f} pips")
print(f"  equity at trade time: ${equity}")
print()

# USDJPYm contract specs from pair_config
from mars.apps.trading.system.pair_config import get_contract_specs
specs = get_contract_specs("USDJPYm")
print(f"=== contract_specs for USDJPYm ===")
print(f"  {specs}")
print(f"  pip_size:     {specs.get('pip_size')}")
print(f"  contract_size: {specs.get('contract_size')}")
print()

# Method 1: FALLBACK path (post-fix contract_specs-based)
print(f"=== PATH 1: FALLBACK (fixed-fractional, contract_specs-based) ===")
contract_specs = specs
stop_distance = abs(entry_price - stop_price)
pip_size = float(contract_specs.get("pip_size", 0.0001))
contract_size = float(contract_specs.get("contract_size", 100000.0))
pip_value_per_lot = pip_size * contract_size
stop_distance_pips = stop_distance / pip_size if pip_size > 0 else stop_distance
risk_per_lot = stop_distance_pips * pip_value_per_lot
target_risk = equity * 0.01
pre_floor_fallback = target_risk / risk_per_lot
print(f"  stop_distance = {stop_distance:.4f}")
print(f"  stop_distance_pips = {stop_distance_pips:.2f}")
print(f"  pip_value_per_lot = pip_size × contract_size = {pip_size} × {contract_size} = ${pip_value_per_lot}")
print(f"  risk_per_lot = {stop_distance_pips:.2f} × ${pip_value_per_lot} = ${risk_per_lot:,.2f}")
print(f"  target_risk = ${equity} × 1% = ${target_risk:.4f}")
print(f"  >>> pre-floor position_size = ${target_risk:.4f} / ${risk_per_lot:,.2f} = {pre_floor_fallback:.6f} lots")
print(f"  >>> post-floor (max(0.01, ...)): {max(0.01, round(pre_floor_fallback, 2))} lots")
print(f"  ⚠️  For JPY pair: $1000/pip/lot is wrong; correct ≈ $6.32/pip/lot at this price")
correct_pip_value = pip_size * contract_size / entry_price
correct_risk_per_lot = stop_distance_pips * correct_pip_value
correct_position_size = target_risk / correct_risk_per_lot
print(f"  ▶ CORRECT (with /current_price JPY→USD): pip_value=${correct_pip_value:.4f}, "
      f"pre-floor={correct_position_size:.4f} lots")
print()

# Method 2: GARCH sizer path (post-fix with timestamp promotion)
print(f"=== PATH 2: GARCH sizer (vol forecast) ===")
from mars.apps.trading.system.vol_scaled_system import VolScaledSizer
from mars.apps.trading.system.pair_config import get_data_path

# Load same data as the session would
data_path = get_data_path("USDJPYm")
df = pd.read_parquet(data_path)
if not pd.api.types.is_datetime64_any_dtype(df.index) and "timestamp" in df.columns:
    df = df.set_index("timestamp").sort_index()
recent = df.tail(2000)

sizer = VolScaledSizer()
sizer.fit(recent)
forecast_vol = sizer.forecast_vol(recent)
latest_vol = forecast_vol.iloc[-1]  # annualized % vol (per the code's expectation)
print(f"  forecast_vol() latest = {latest_vol:.6f} (annualized %)")
print(f"    NOTE: this is the raw forecast from GARCH. Annualization assumption: × sqrt(252*4)")
print(f"    Annualize check: {latest_vol} (already in % form per code's belief)")

# Now run the GARCH sizing math as in poll_cycle
target_vol = sizer.config.target_vol  # 0.15
kelly_fraction = sizer.config.kelly_fraction  # 0.5
leverage = (target_vol / (latest_vol / 100)) * kelly_fraction
leverage = max(sizer.config.min_leverage, min(sizer.config.max_leverage, leverage))
position_value = equity * leverage
contract_multiplier = float(specs.get("contract_size", 100.0))
position_size = position_value / (signal_price * contract_multiplier)
max_position_value = equity * sizer.config.max_position_pct
max_contracts = max_position_value / (signal_price * contract_multiplier)
pre_floor_garch = min(position_size, max_contracts)

print(f"  leverage = (0.15 / ({latest_vol:.6f}/100)) × 0.5 = {leverage:.2f}  (clipped to [{sizer.config.min_leverage}, {sizer.config.max_leverage}])")
print(f"  position_value = ${equity} × {leverage:.2f} = ${position_value:.4f}")
print(f"  position_size (raw) = ${position_value:.4f} / ({signal_price} × {contract_multiplier}) = {position_value/(signal_price*contract_multiplier):.8f} lots")
print(f"  max_position_value = ${equity} × {sizer.config.max_position_pct} = ${max_position_value:.4f}")
print(f"  max_contracts = ${max_position_value:.4f} / ({signal_price} × {contract_multiplier}) = {max_contracts:.8f} lots")
print(f"  >>> pre-floor position_size = min(raw, max) = {pre_floor_garch:.8f} lots")
print(f"  >>> post-floor: {max(0.01, round(pre_floor_garch, 2))} lots")
print()

print(f"=== SUMMARY: which path produced the 0.01 we see? ===")
print(f"  Both paths: pre-floor << 0.01 → both clamp to 0.01 minimum lot.")
print(f"  Both pre-floor values would correspond to ESSENTIALLY ZERO position.")
print(f"  Audit DB shows requested_lots=0.01 (the floor), so we cannot tell which path")
print(f"  ran live. Both end at 0.01 either way.")
print()
print(f"  ⚠️ The fallback formula's pip_value_per_lot = ${pip_value_per_lot} for USDJPYm is wrong:")
print(f"     - $1000/pip/lot (current) treats JPY as the account currency")
print(f"     - Correct: pip_size × contract_size / entry_price = {correct_pip_value:.4f}/pip/lot")
print(f"     - Missing: JPY→USD conversion. The 0.01 min lot currently masks the 158× error.")
print(f"     - For higher-equity accounts (>~3000 USD on USDJPYm), this would under-size by 158×.")