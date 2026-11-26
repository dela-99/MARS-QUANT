#!/usr/bin/env python3
"""
Stage 2b - Cost vs Edge Screen
Timeframes: M5, M15, H1, H4 (resampled from M5)
Fixed params: W=10, a=1.5, b=3
Costs: 0.00 and 0.50 $/oz
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
import itertools
warnings.filterwarnings('ignore')

RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")
DATA_PATH = RESULTS_DIR / "xauusd_m5_clean.parquet"

# Fixed parameters
W = 10
A = 1.5
B = 3.0
TIME_EXIT_BARS = 20
MAX_BREAKOUT_ATR = 5.0
COSTS = [0.00, 0.50]

def load_data():
    df = pd.read_parquet(DATA_PATH)
    df = df[df.index.dayofweek < 5].copy()
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    df = df[diffs != 65].copy()
    df = df[df['<SPREAD>'] > 0].copy()
    df = df[(df.index >= '2022-01-01') & (df.index < '2024-01-01')].copy()
    return df

def resample_ohlc(df, rule):
    """Resample M5 to target timeframe"""
    return df.resample(rule).agg({
        '<OPEN>': 'first',
        '<HIGH>': 'max',
        '<LOW>': 'min',
        '<CLOSE>': 'last',
        '<TICKVOL>': 'sum',
        '<VOL>': 'sum',
        '<SPREAD>': 'mean'
    }).dropna()

def compute_atr_numpy(high, low, close, period=14):
    n = len(high)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.full(n, np.nan)
    for i in range(period-1, n):
        atr[i] = tr[i-period+1:i+1].mean()
    return atr

def find_swings_numpy(high, low, W):
    n = len(high)
    swing_high = np.zeros(n, dtype=bool)
    swing_low = np.zeros(n, dtype=bool)
    for i in range(W, n - W):
        window_high = high[i-W:i+W+1]
        window_low = low[i-W:i+W+1]
        if high[i] == window_high.max():
            swing_high[i] = True
        if low[i] == window_low.min():
            swing_low[i] = True
    return swing_high, swing_low

def get_confirmed_swings_numpy(swing_high, swing_low, W, high, low):
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
    n = len(close)
    start_idx = W + 15
    pnl_list = []
    stop_distances = []
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
                        stop_distances.append(a * curr_atr)
            elif not np.isnan(sl) and curr_close < sl:
                if (sl - curr_close) <= MAX_BREAKOUT_ATR * curr_atr:
                    if t + 1 < n:
                        entry_price = close[t]
                        position = -1
                        entry_idx = t + 1
                        sl_price = entry_price + a * curr_atr
                        tp_price = entry_price - b * curr_atr
                        stop_distances.append(a * curr_atr)
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
    return np.array(pnl_list) if pnl_list else np.array([]), np.array(stop_distances) if stop_distances else np.array([])

def compute_stats(pnl_array, stop_distances, cost_per_oz, years=2):
    if len(pnl_array) == 0:
        return {
            'trades_per_year': 0, 'avg_stop_dist': 0,
            'gross_exp': 0, 'net_exp': 0, 'cost_pct_stop': 0
        }
    gross_pnl = pnl_array + cost_per_oz
    gross_exp = gross_pnl.mean()
    net_exp = pnl_array.mean()
    avg_stop = stop_distances.mean() if len(stop_distances) > 0 else 0
    cost_pct_stop = (cost_per_oz / avg_stop * 100) if avg_stop > 0 else 0
    trades_per_year = len(pnl_array) / years
    return {
        'trades_per_year': trades_per_year,
        'avg_stop_dist': avg_stop,
        'gross_exp': gross_exp,
        'net_exp': net_exp,
        'cost_pct_stop': cost_pct_stop,
        'n_trades': len(pnl_array)
    }

def main():
    print("=" * 70)
    print("STAGE 2b - COST vs EDGE SCREEN")
    print("=" * 70)
    
    df_m5 = load_data()
    print(f"M5 bars (2022-2023): {len(df_m5)}")
    
    # Resample
    df_m15 = resample_ohlc(df_m5, '15min')
    df_h1 = resample_ohlc(df_m5, '1h')
    df_h4 = resample_ohlc(df_m5, '4h')
    
    print(f"M15 bars: {len(df_m15)}")
    print(f"H1 bars:  {len(df_h1)}")
    print(f"H4 bars:  {len(df_h4)}")
    
    timeframes = {
        'M5': df_m5,
        'M15': df_m15,
        'H1': df_h1,
        'H4': df_h4
    }
    
    all_results = []
    
    for tf_name, df in timeframes.items():
        print(f"\n--- {tf_name} ---")
        high = df['<HIGH>'].values
        low = df['<LOW>'].values
        close = df['<CLOSE>'].values
        
        atr = compute_atr_numpy(high, low, close)
        swing_high, swing_low = find_swings_numpy(high, low, W)
        confirmed_high, confirmed_low = get_confirmed_swings_numpy(swing_high, swing_low, W, high, low)
        
        for cost in COSTS:
            pnl, stops = run_backtest_numpy(close, high, low, atr, confirmed_high, confirmed_low, W, A, B, cost)
            stats = compute_stats(pnl, stops, cost, years=2)
            stats.update({'timeframe': tf_name, 'cost': cost, 'W': W, 'a': A, 'b': B})
            all_results.append(stats)
            print(f"  Cost ${cost:.2f}: trades/yr={stats['trades_per_year']:.1f}  stop=${stats['avg_stop_dist']:.2f}  gross_exp=${stats['gross_exp']:.2f}  net_exp=${stats['net_exp']:.2f}  cost%stop={stats['cost_pct_stop']:.1f}%  n={stats['n_trades']}")
    
    # Save to trials.csv
    trials_df = pd.DataFrame(all_results)
    trials_df.to_csv(RESULTS_DIR / "stage2b_results.csv", index=False)
    
    # Append to main trials.csv
    main_trials = []
    for r in all_results:
        main_trials.append({
            'stage': 'stage2b',
            'W': W, 'a': A, 'b': B,
            'cost': r['cost'],
            'net_pnl': r['net_exp'] * r['n_trades'],
            'expectancy': r['net_exp'],
            'win_rate': np.nan,
            'sharpe': np.nan,
            'max_dd': np.nan,
            'n_trades': r['n_trades'],
            'timeframe': r['timeframe'],
            'trades_per_year': r['trades_per_year'],
            'avg_stop_dist': r['avg_stop_dist'],
            'gross_exp': r['gross_exp'],
            'cost_pct_stop': r['cost_pct_stop']
        })
    
    # Read existing trials and append
    existing = pd.read_csv(RESULTS_DIR / "trials.csv")
    new_trials = pd.DataFrame(main_trials)
    combined = pd.concat([existing, new_trials], ignore_index=True)
    combined.to_csv(RESULTS_DIR / "trials.csv", index=False)
    
    print("\n" + "=" * 70)
    print("STAGE 2b COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()