"""
Verify the fix: after multiple evaluate_gate calls, the gate re-fetches every time.
Uses MockMT5 so we don't depend on a live terminal.
"""
import sys, os
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")

from unittest.mock import Mock, patch
import numpy as np
import pandas as pd
from datetime import datetime

# Build a Mock MT5 that returns synthetic 15M bars
mock_mt5 = Mock()
mock_mt5.TIMEFRAME_M5 = 5
mock_mt5.TIMEFRAME_M1 = 1
mock_mt5.TIMEFRAME_H1 = 16385

def fake_copy_rates_from_pos(symbol, tf, start_pos, count):
    tf_freq = {16385:'h', 16384:'30min', 15:'15min', 5:'5min'}.get(tf, '5min')
    base = 2000.0 if 'XAU' in symbol else 1.1
    np.random.seed(int(datetime.now().timestamp()) % 10000)  # mutate per call
    times = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=count, freq=tf_freq)
    data = []
    p = base
    for i in range(count):
        s = 0.001 if 'h' in tf_freq else 0.0005
        p *= (1 + np.random.normal(0, s))
        o, h, l, c = p, p*(1+abs(np.random.normal(0,s*0.4))), p*(1-abs(np.random.normal(0,s*0.4))), p
        data.append((int(times[i].timestamp()), o, h, l, c, 1000, 240, 0))
    dt = np.dtype([('time','i8'),('open','f8'),('high','f8'),('low','f8'),('close','f8'),('tick_volume','i8'),('spread','i4'),('real_volume','i8')])
    return np.array(data, dtype=dt)

mock_mt5.copy_rates_from_pos.side_effect = fake_copy_rates_from_pos

from mars.apps.trading.signals.mtf_gate import MTFGate

gate = MTFGate(mock_mt5, symbol='XAUUSDm')

# Call evaluate_gate 3 times; copy_rates_from_pos call count must increase each time
initial_call_count = mock_mt5.copy_rates_from_pos.call_count

ctx1 = gate.evaluate_gate(breakout_signal=1, breakout_price=0, breakout_stop=0)
after1 = mock_mt5.copy_rates_from_pos.call_count - initial_call_count
print(f"After 1st evaluate_gate: {after1} copy_rates_from_pos calls")

ctx2 = gate.evaluate_gate(breakout_signal=1, breakout_price=0, breakout_stop=0)
after2 = mock_mt5.copy_rates_from_pos.call_count - initial_call_count
print(f"After 2nd evaluate_gate: {after2} copy_rates_from_pos calls")

ctx3 = gate.evaluate_gate(breakout_signal=0, breakout_price=0, breakout_stop=0)
after3 = mock_mt5.copy_rates_from_pos.call_count - initial_call_count
print(f"After 3rd evaluate_gate: {after3} copy_rates_from_pos calls")

assert after3 > after2 > after1, f"BUG STILL THERE: gate not refetching per cycle ({after1}, {after2}, {after3})"
print(f"\nFIX VERIFIED: gate re-fetches every cycle (call counts: {after1}, {after2}, {after3})")
print(f"   Each evaluate_gate should trigger 4 fetches (1H, 30M, 15M, 5M) => delta=4 expected")
print(f"   Actual delta per cycle: {after2-after1} (cycle 2 - cycle 1), {after3-after2} (cycle 3 - cycle 2)")