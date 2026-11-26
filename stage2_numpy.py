#!/usr/bin/env python3
"""
Stage 2 - Strategy A: Structural Break on M5 (numpy-only, no pandas rolling)
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
import itertools
warnings.filterwarnings('ignore')

RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")
DATA_PATH = RESULTS_DIR / "xauusd_m5_clean.parquet"

COSTS = [0.30, 0.50, 0.80]
HEADLINE_COST = 0.50
TIME_EXIT_BARS = 20
MAX_BREAKOUT_ATR = 5.0

W_VALUES = [5, 10, 20]
A_VALUES = [1.0, 1.5, 2.0]
B_VALUES = [2.0, 3.0, 4.0]

def load_data():
    df = pd.read_parquet(DATA_PATH)
    df = df[df.index.dayofweek < 5].copy()
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    df = df[diffs != 65].copy()
    df = df[df['<SPREAD>'] > 0].copy()
    df = df[(df.index >= '2022-01-01') & (df.index < '2024-01-01')].copy()
    return df

def compute_atr_numpy(high, low, close, period=14):
    """Numpy ATR"""
    n = len(high)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.full(n, np.nan)
    # Simple moving average
    for i in range(period-1, n):
        atr[i] = tr[i-period+1:i+1].mean()
    return atr

def find_swings_numpy(high, low, W):
    """Numpy swing detection: pivot with W left and W right"""
    n = len(high)
    swing_high = np.zeros(n, dtype=bool)
    swing_low = np.zeros(n, dtype=bool)
    
    # For each index i from W to n-W-1, check if it's max/min in [i-W, i+W]
    for i in range(W, n - W):
        window_high = high[i-W:i+W+1]
        window_low = low[i-W:i+W+1]
        if high[i] == window_high.max():
            swing_high[i] = True
        if low[i] == window_low.min():
            swing_low[i] = True
    
    return swing_high, swing_low

def get_confirmed_swings_numpy(swing_high, swing_low, W, high, low):
    """Get last confirmed swing high/low values for each bar"""
    n = len(swing_high)
    confirmed_high_val = np.full(n, np.nan)
    confirmed_low_val = np.full(n, np.nan)
    
    last_high_val = np.nan
    last_low_val = np.nan
    
    for t in range(n):
        confirm_idx = t - W - 1
        if confirm_idx >= 0:
            if swing_high[confirm_idx]:
                last_high_val = high[confirm_idx]
            if swing_low[confirm_idx]:
                last_low_val = low[confirm_idx]
        
        confirmed_high_val[t] = last_high_val
        confirmed_low_val[t] = last_low_val
    
    return confirmed_high_val, confirmed_low_val

def run_backtest_numpy(close, high, low, atr, confirmed_high, confirmed_low, W, a, b, cost_per_oz):
    """Numpy backtest loop"""
    n = len(close)
    start_idx = W + 15
    
    pnl_list = []
    position = 0
    entry_price = 0
    entry_idx = 0
    sl_price = 0
    tp_price = 0
    
    for t in range(start_idx, n):
        if np.isnan(atr[t]):
            continue
        
        curr_atr = atr[t]
        curr_close = close[t]
        curr_high = high[t]
        curr_low = low[t]
        sh = confirmed_high[t]
        sl = confirmed_low[t]
        
        if position == 0:
            if not np.isnan(sh) and curr_close > sh:
                if (curr_close - sh) <= MAX_BREAKOUT_ATR * curr_atr:
                    if t + 1 < n:
                        entry_price = close[t]
                        position = 1
                        entry_idx = t + 1
                        sl_price = entry_price - a * curr_atr
                        tp_price = entry_price + b * curr_atr
            elif not np.isnan(sl) and curr_close < sl:
                if (sl - curr_close) <= MAX_BREAKOUT_ATR * curr_atr:
                    if t + 1 < n:
                        entry_price = close[t]
                        position = -1
                        entry_idx = t + 1
                        sl_price = entry_price + a * curr_atr
                        tp_price = entry_price - b * curr_atr
        
        elif position == 1:
            sl_hit = curr_low <= sl_price
            tp_hit = curr_high >= tp_price
            time_exit = (t - entry_idx >= TIME_EXIT_BARS)
            
            if sl_hit or tp_hit or time_exit:
                if sl_hit and tp_hit:
                    exit_price = sl_price
                elif sl_hit:
                    exit_price = sl_price
                elif tp_hit:
                    exit_price = tp_price
                else:
                    exit_price = curr_close
                
                pnl_list.append(exit_price - entry_price - cost_per_oz)
                position = 0
        
        elif position == -1:
            sl_hit = curr_high >= sl_price
            tp_hit = curr_low <= tp_price
            time_exit = (t - entry_idx >= TIME_EXIT_BARS)
            
            if sl_hit or tp_hit or time_exit:
                if sl_hit and tp_hit:
                    exit_price = sl_price
                elif sl_hit:
                    exit_price = sl_price
                elif tp_hit:
                    exit_price = tp_price
                else:
                    exit_price = curr_close
                
                pnl_list.append(entry_price - exit_price - cost_per_oz)
                position = 0
    
    return np.array(pnl_list) if pnl_list else np.array([])

def compute_stats(pnl_array):
    if len(pnl_array) == 0:
        return {'n': 0, 'net': 0, 'wr': 0, 'exp': 0, 'sharpe': 0, 'max_dd': 0, 'max_dd_pct': 0}
    
    cum = np.cumsum(pnl_array)
    running_max = np.maximum.accumulate(cum)
    dd = running_max - cum
    max_dd = dd.max()
    peak_idx = dd.argmax()
    max_dd_pct = (max_dd / running_max[peak_idx] * 100) if running_max[peak_idx] != 0 else 0
    
    sharpe = pnl_array.mean() / pnl_array.std(ddof=1) * np.sqrt(252) if pnl_array.std() > 0 else 0
    
    return {
        'n': len(pnl_array),
        'net': pnl_array.sum(),
        'wr': (pnl_array > 0).mean(),
        'exp': pnl_array.mean(),
        'sharpe': sharpe,
        'max_dd': max_dd,
        'max_dd_pct': max_dd_pct,
    }

def main():
    print("=" * 60)
    print("STAGE 2 - STRATEGY A: STRUCTURAL BREAK (numpy)")
    print("=" * 60)
    
    df = load_data()
    print(f"Development data (2022-2023): {len(df)} bars")
    
    high = df['<HIGH>'].values
    low = df['<LOW>'].values
    close = df['<CLOSE>'].values
    
    atr = compute_atr_numpy(high, low, close)
    
    param_grid = list(itertools.product(W_VALUES, A_VALUES, B_VALUES))
    print(f"Testing {len(param_grid)} combinations...")
    
    results = []
    
    # Pre-compute swings for each W
    swing_cache = {}
    for W in W_VALUES:
        swing_high, swing_low = find_swings_numpy(high, low, W)
        confirmed_high, confirmed_low = get_confirmed_swings_numpy(swing_high, swing_low, W, high, low)
        swing_cache[W] = (confirmed_high, confirmed_low)
    
    for W, a, b in param_grid:
        confirmed_high, confirmed_low = swing_cache[W]
        pnl = run_backtest_numpy(close, high, low, atr, confirmed_high, confirmed_low, W, a, b, HEADLINE_COST)
        stats = compute_stats(pnl)
        stats.update({'W': W, 'a': a, 'b': b})
        results.append(stats)
        
        print(f"W={W}, a={a}, b={b}: n={stats['n']:3d}  net={stats['net']:7.2f}  wr={stats['wr']:.3f}  exp={stats['exp']:6.2f}  sharpe={stats['sharpe']:5.2f}  dd={stats['max_dd']:6.2f}")
    
    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULTS_DIR / "stage2_grid_results.csv", index=False)
    
    best = results_df.loc[results_df['net'].idxmax()]
    print(f"\n=== BEST (by net PnL at ${HEADLINE_COST}/oz) ===")
    print(f"W={int(best['W'])}, a={best['a']}, b={best['b']}")
    print(f"  Trades: {int(best['n'])}")
    print(f"  Net PnL: ${best['net']:.2f}")
    print(f"  Win Rate: {best['wr']:.3f}")
    print(f"  Expectancy: ${best['exp']:.2f}/trade")
    print(f"  Sharpe: {best['sharpe']:.2f}")
    print(f"  Max DD: ${best['max_dd']:.2f} ({best['max_dd_pct']:.1f}%)")
    
    print(f"\n=== COST SENSITIVITY (best params) ===")
    confirmed_high, confirmed_low = swing_cache[int(best['W'])]
    for cost in COSTS:
        pnl = run_backtest_numpy(close, high, low, atr, confirmed_high, confirmed_low, int(best['W']), best['a'], best['b'], cost)
        stats = compute_stats(pnl)
        print(f"  Cost ${cost:.2f}: net=${stats['net']:.2f}  exp=${stats['exp']:.2f}  n={int(stats['n'])}")
    
    print("\n" + "=" * 60)
    print("STAGE 2 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()