"""
Reproduce EXACTLY what the MTF gate classifier computed at the decision moment.
The 30M timeframe is invalid on this broker (tf=16384 returns Invalid params),
so the gate falls back to RESAMPLING 15M -> 30M, exactly as per FALLBACK_RESAMPLE.
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

assert mt5.initialize()

print("=" * 78)
print("STEP 1 — Raw MT5 fetches at decision moment")
print("=" * 78)
print("Server time now:", datetime.fromtimestamp(mt5.symbol_info_tick("XAUUSDm").time, tz=timezone.utc).isoformat())

def fetch(tf, n):
    rates = mt5.copy_rates_from_pos("XAUUSDm", tf, 0, n)
    if rates is None:
        return None, mt5.last_error()
    df = pd.DataFrame(rates)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df = df.set_index('timestamp').sort_index()
    return df, None

# Match gate code exactly:
# 1H: 16385, 30M: 16384, 15M: 15 (TF_M15), 5M: 5
h1, e = fetch(16385, 100)
print(f"\n[1H fetch tf=16385, count=100] -> {len(h1)} bars | {h1.index[0]} .. {h1.index[-1]}")

m30_native, e = fetch(16384, 100)
if m30_native is None:
    print(f"[30M fetch tf=16384] -> FAILED: {e}  (this is why FALLBACK_RESAMPLE kicks in)")
else:
    print(f"[30M fetch] -> {len(m30_native)} bars")

m15, e = fetch(15, 200)
print(f"[15M fetch tf=15, count=200] -> {len(m15)} bars | {m15.index[0]} .. {m15.index[-1]}")

print("\n" + "=" * 78)
print("STEP 1a — Show the actual 15M bars (used as source for 30M resample)")
print("=" * 78)
print("Last 15 15M bars from MT5 (timestamps are forming-bar status, last row is forming):")
tail15 = m15[['open','high','low','close','spread']].tail(15).copy()
print(tail15.to_string())

print("\n" + "=" * 78)
print("STEP 1b — Resample 15M -> 30M (this is what the gate's _resample_timeframe does)")
print("=" * 78)
ohlcv = {'open':'first','high':'max','low':'min','close':'last','tick_volume':'sum'}
if 'spread' in m15.columns:
    ohlcv['spread'] = 'mean'
m30_resampled = m15.resample('30min').agg(ohlcv).dropna()
print(f"\nResampled 30M bars: {len(m30_resampled)} | {m30_resampled.index[0]} .. {m30_resampled.index[-1]}")
print("\nLast 15 RESAMPLED 30M bars (last row is forming):")
print(m30_resampled[['open','high','low','close']].tail(15).to_string())

print("\n" + "=" * 78)
print("STEP 2 — Replay the EXACT classifier computation")
print("=" * 78)

def classify(df, ema_window, lookback, name):
    if len(df) < ema_window + lookback + 1:
        return "NO_BIAS", None
    # EXACT logic from mtf_gate.py:282-314:
    # close_prices = df['close'].iloc[:-1]   # exclude forming bar
    # ema = close_prices.ewm(span=ema_window, adjust=False).mean()
    # ema_slope = ema.diff()
    # recent_slope = ema_slope.iloc[-lookback:].mean()
    close_prices = df['close'].iloc[:-1]
    ema = close_prices.ewm(span=ema_window, adjust=False).mean()
    ema_slope = ema.diff()
    recent_slope = ema_slope.iloc[-lookback:].mean()
    label = "LONG_BIAS" if recent_slope > 0 else ("SHORT_BIAS" if recent_slope < 0 else "NO_BIAS")
    print(f"\n[{name}] classifier:")
    print(f"  closed bars: {len(close_prices)} (excluded forming bar)")
    print(f"  EMA{ema_window} tail-15:")
    ema_tail = pd.DataFrame({
        'close': close_prices.tail(15).values,
        f'ema{ema_window}': ema.tail(15).values,
        f'ema_slope': ema_slope.tail(15).values,
    }, index=close_prices.index[-15:])
    print(ema_tail.to_string())
    print(f"\n  ema_slope.iloc[-{lookback}:].mean()  = {recent_slope:+.6f}")
    print(f"  --> classify_trend_bias returns: {label}")
    return label, recent_slope

label1h, slope1h = classify(h1, 50, 10, "1H classifier (ema_window=50, trend_lookback=10)")
label30, slope30 = classify(m30_resampled, 50, 8, "30M classifier (ema_window=50, bias_lookback=8)")

print("\n" + "=" * 78)
print("STEP 3 — Data freshness / staleness check")
print("=" * 78)
server_now = datetime.fromtimestamp(mt5.symbol_info_tick("XAUUSDm").time, tz=timezone.utc)
last_1h_bar = h1.index[-1]
last_30m_bar = m30_resampled.index[-1]
print(f"  Server time: {server_now}")
print(f"  Last 1H bar:  {last_1h_bar}  (delta: {(server_now - last_1h_bar.to_pydatetime()).total_seconds()/3600:.2f} h)")
print(f"  Last 30M bar: {last_30m_bar} (delta: {(server_now - last_30m_bar.to_pydatetime()).total_seconds()/60:.1f} min)")

print("\n" + "=" * 78)
print("STEP 4 — Verdict")
print("=" * 78)
print(f"  1H classify: {label1h} (slope {slope1h:+.6f})")
print(f"  30M classify: {label30} (slope {slope30:+.6f})")
print(f"  AGREE?  {'YES' if label1h == label30 else 'NO'}")

mt5.shutdown()