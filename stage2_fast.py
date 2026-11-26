#!/usr/bin/env python3
"""
Stage 2 - Strategy A: Structural Break on M5 (vectorized swing detection)
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

def compute_atr(df, period=14):
    high = df['<HIGH>']
    low = df['<LOW>']
    close = df['<CLOSE>']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def find_swings_vectorized(high, low, W):
    """Vectorized swing detection: pivot with W left and W right"""
    n = len(high)
    swing_high = np.full(n, False)
    swing_low = np.full(n, False)
    
    # Rolling max/min with window 2W+1, centered
    # A swing high at i means high[i] == max(high[i-W:i+W+1])
    # Use rolling window
    roll_max = pd.Series(high).rolling(2*W+1, center=True, min_periods=2*W+1).max().values
    roll_min = pd.Series(low).rolling(2*W+1, center=True, min_periods=2*W+1).min().values
    
    swing_high = (high == roll_max) & ~np.isnan(roll_max)
    swing_low = (low == roll_min) & ~np.isnan(roll_min)
    
    # Edge cases: first/last W bars can't be confirmed
    swing_high[:W] = False
    swing_high[-W:] = False
    swing_low[:W] = False
    swing_low[-W:] = False
    
    return swing_high, swing_low

def get_confirmed_swings(swing_high, swing_low, W):
    """Get last confirmed swing high/low for each bar t"""
    n = len(swing_high)
    confirmed_high = np.full(n, np.nan)
    confirmed_low = np.full(n, np.nan)
    
    last_high_val = np.nan
    last_low_val = np.nan
    
    for t in range(n):
        # Swing at index t-W-1 gets confirmed at t
        confirm_idx = t - W - 1
        if confirm_idx >= 0:
            if swing_high[confirm_idx]:
                last_high_val = confirm_idx  # Store index
            if swing_low[confirm_idx]:
                last_low_val = confirm_idx
        
        if not np.isnan(last_high_val):
            confirmed_high[t] = last_high_val  # Store index of swing
        if not np.isnan(last_low_val):
            confirmed_low[t] = last_low_val
    
    return confirmed_high, confirmed_low

def run_backtest_fast(df, W, a, b, cost_per_oz):
    """Vectorized-ish backtest"""
    n = len(df)
    close = df['<CLOSE>'].values
    high = df['<HIGH>'].values
    low = df['<LOW>'].values
    atr = df['atr'].values
    
    # Find swings
    swing_high, swing_low = find_swings_vectorized(high, low, W)
    confirmed_high_idx, confirmed_low_idx = get_confirmed_swings(swing_high, swing_low, W)
    
    trades = []
    position = 0
    entry_price = 0
    entry_idx = 0
    entry_atr = 0
    sl_price = 0
    tp_price = 0
    
    start_idx = W + 15  # Need ATR + confirmation
    
    for t in range(start_idx, n):
        if np.isnan(atr[t]):
            continue
        
        curr_atr = atr[t]
        curr_close = close[t]
        curr_high = high[t]
        curr_low = low[t]
        
        sh_idx = confirmed_high_idx[t]
        sl_idx = confirmed_low_idx[t]
        
        sh = high[int(sh_idx)] if not np.isnan(sh_idx) else np.nan
        sl = low[int(sl_idx)] if not np.isnan(sl_idx) else np.nan
        
        if position == 0:
            if not np.isnan(sh) and curr_close > sh:
                if (curr_close - sh) > MAX_BREAKOUT_ATR * curr_atr:
                    pass
                elif t + 1 < n:
                    entry_price = close[t]  # Next bar open ≈ current close
                    position = 1
                    entry_idx = t + 1
                    entry_atr = curr_atr
                    sl_price = entry_price - a * entry_atr
                    tp_price = entry_price + b * entry_atr
            elif not np.isnan(sl) and curr_close < sl:
                if (sl - curr_close) > MAX_BREAKOUT_ATR * curr_atr:
                    pass
                elif t + 1 < n:
                    entry_price = close[t]
                    position = -1
                    entry_idx = t + 1
                    entry_atr = curr_atr
                    sl_price = entry_price + a * entry_atr
                    tp_price = entry_price - b * entry_atr
        
        elif position == 1:
            sl_hit = curr_low <= sl_price
            tp_hit = curr_high >= tp_price
            time_exit = (t - entry_idx >= TIME_EXIT_BARS)
            
            if sl_hit or tp_hit or time_exit:
                if sl_hit and tp_hit:
                    exit_price = sl_price
                    reason = "SL"
                elif sl_hit:
                    exit_price = sl_price
                    reason = "SL"
                elif tp_hit:
                    exit_price = tp_price
                    reason = "TP"
                else:
                    exit_price = curr_close
                    reason = "TIME"
                
                pnl = (exit_price - entry_price) - cost_per_oz
                trades.append(pnl)
                position = 0
        
        elif position == -1:
            sl_hit = curr_high >= sl_price
            tp_hit = curr_low <= tp_price
            time_exit = (t - entry_idx >= TIME_EXIT_BARS)
            
            if sl_hit or tp_hit or time_exit:
                if sl_hit and tp_hit:
                    exit_price = sl_price
                    reason = "SL"
                elif sl_hit:
                    exit_price = sl_price
                    reason = "SL"
                elif tp_hit:
                    exit_price = tp_price
                    reason = "TP"
                else:
                    exit_price = curr_close
                    reason = "TIME"
                
                pnl = (entry_price - exit_price) - cost_per_oz
                trades.append(pnl)
                position = 0
    
    return np.array(trades) if trades else np.array([])

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
        'avg_win': pnl_array[pnl_array > 0].mean() if (pnl_array > 0).any() else 0,
        'avg_loss': pnl_array[pnl_array <= 0].mean() if (pnl_array <= 0).any() else 0,
    }

def main():
    print("=" * 60)
    print("STAGE 2 - STRATEGY A: STRUCTURAL BREAK (fast)")
    print("=" * 60)
    
    df = load_data()
    df['atr'] = compute_atr(df)
    print(f"Development data (2022-2023): {len(df)} bars")
    
    param_grid = list(itertools.product(W_VALUES, A_VALUES, B_VALUES))
    print(f"Testing {len(param_grid)} combinations...")
    
    results = []
    
    for W, a, b in param_grid:
        pnl = run_backtest_fast(df, W, a, b, HEADLINE_COST)
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
    for cost in COSTS:
        pnl = run_backtest_fast(df, int(best['W']), best['a'], best['b'], cost)
        stats = compute_stats(pnl)
        print(f"  Cost ${cost:.2f}: net=${stats['net']:.2f}  exp=${stats['exp']:.2f}  n={int(stats['n'])}")
    
    print("\n" + "=" * 60)
    print("STAGE 2 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()