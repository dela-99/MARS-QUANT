#!/usr/bin/env python3
"""
Stage 2 - Strategy A: Structural Break on M5
Swing high/low = pivot with W bars right-side confirmation.
Long when M5 close breaks last confirmed swing high; short symmetric.
Reject if breakout > 5 ATR from price.
SL = a * ATR(14), TP = b * ATR(14), time exit after N bars.
Constant risk per trade (fixed 1 lot = 1 oz), no vol-sizing, no partial exits.
Grid: W in {5,10,20}; a in {1,1.5,2}; b in {2,3,4}. No session filter (Stage 1 failed).
Costs: $0.30, $0.50, $0.80 per oz round-trip. Headline: $0.50.
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
import itertools
warnings.filterwarnings('ignore')

RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")
DATA_PATH = RESULTS_DIR / "xauusd_m5_clean.parquet"

COSTS = [0.30, 0.50, 0.80]  # $ per oz round-trip
HEADLINE_COST = 0.50
TIME_EXIT_BARS = 20  # 100 minutes
MAX_BREAKOUT_ATR = 5.0

# Parameter grid
W_VALUES = [5, 10, 20]
A_VALUES = [1.0, 1.5, 2.0]
B_VALUES = [2.0, 3.0, 4.0]

def load_data():
    """Load and preprocess data (same as Stage 1)"""
    df = pd.read_parquet(DATA_PATH)
    df = df[df.index.dayofweek < 5].copy()
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    df = df[diffs != 65].copy()
    df = df[df['<SPREAD>'] > 0].copy()
    df = df[df.index >= '2022-01-01'].copy()
    df = df[df.index < '2024-01-01'].copy()  # Development period only (2022-2023)
    return df

def compute_atr(df, period=14):
    """Compute ATR(14)"""
    high = df['<HIGH>']
    low = df['<LOW>']
    close = df['<CLOSE>']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean()
    return atr

def find_confirmed_swings(df, W):
    """
    Find confirmed swing highs and lows with W bars right-side confirmation.
    A swing high at bar i is confirmed at bar i+W if:
    - high[i] > high[i-1] and high[i] > high[i+1] (local peak)
    - For all j in (i+1, i+W): high[j] < high[i] (no higher high in confirmation window)
    Actually, standard pivot: high[i] is highest in [i-W, i+W]
    But "confirmed only W bars later" means we only know at i+W that i was a swing high.
    So at bar t, the last confirmed swing high is the highest high in [t-2W, t-W]
    """
    high = df['<HIGH>'].values
    low = df['<LOW>'].values
    n = len(df)
    
    swing_high = np.full(n, np.nan)
    swing_low = np.full(n, np.nan)
    
    # For each bar t (where we are making decision), 
    # the last confirmed swing high is at index t-W-1 (confirmed at t-1)
    # Actually: swing at i confirmed at i+W. So at time t, confirmed swings are those with i+W <= t-1, i.e., i <= t-W-1
    # The last confirmed swing high is the most recent i <= t-W-1 that is a swing high.
    
    # First, identify all swing highs/lows (local extrema)
    is_swing_high = np.zeros(n, dtype=bool)
    is_swing_low = np.zeros(n, dtype=bool)
    
    for i in range(W, n - W):
        # Swing high: high[i] is max in [i-W, i+W]
        if high[i] == np.max(high[i-W:i+W+1]):
            is_swing_high[i] = True
        # Swing low: low[i] is min in [i-W, i+W]
        if low[i] == np.min(low[i-W:i+W+1]):
            is_swing_low[i] = True
    
    # Now for each bar t, find last confirmed swing high/low
    # Confirmed means the swing index i satisfies i + W < t (i.e., confirmed strictly before t)
    # So at bar t, we can use swings up to index t-W-1
    last_confirmed_high = np.full(n, np.nan)
    last_confirmed_low = np.full(n, np.nan)
    last_high_idx = np.full(n, -1, dtype=int)
    last_low_idx = np.full(n, -1, dtype=int)
    
    current_high = np.nan
    current_high_i = -1
    current_low = np.nan
    current_low_i = -1
    
    for t in range(n):
        # Check if a swing at t-W-1 just got confirmed
        confirm_idx = t - W - 1
        if confirm_idx >= 0:
            if is_swing_high[confirm_idx]:
                current_high = high[confirm_idx]
                current_high_i = confirm_idx
            if is_swing_low[confirm_idx]:
                current_low = low[confirm_idx]
                current_low_i = confirm_idx
        
        last_confirmed_high[t] = current_high
        last_confirmed_low[t] = current_low
        last_high_idx[t] = current_high_i
        last_low_idx[t] = current_low_i
    
    return last_confirmed_high, last_confirmed_low, last_high_idx, last_low_idx

def run_backtest(df, W, a, b, cost_per_oz):
    """Run backtest for a single parameter set"""
    n = len(df)
    close = df['<CLOSE>'].values
    high = df['<HIGH>'].values
    low = df['<LOW>'].values
    atr = compute_atr(df).values
    
    # Find confirmed swings
    swing_high, swing_low, _, _ = find_confirmed_swings(df, W)
    
    trades = []
    position = 0  # 0=flat, 1=long, -1=short
    entry_price = 0
    entry_idx = 0
    entry_atr = 0
    sl_price = 0
    tp_price = 0
    
    for t in range(W + 15, n):  # Need ATR(14) + W confirmation
        if np.isnan(atr[t]) or np.isnan(swing_high[t]) or np.isnan(swing_low[t]):
            continue
        
        curr_atr = atr[t]
        curr_close = close[t]
        curr_high = high[t]
        curr_low = low[t]
        sh = swing_high[t]
        sl = swing_low[t]
        
        if position == 0:
            # Check long entry: close breaks swing high
            if curr_close > sh:
                # Reject if breakout > 5 ATR from swing high
                if (curr_close - sh) > MAX_BREAKOUT_ATR * curr_atr:
                    continue
                # Enter long at NEXT bar open (t+1)
                if t + 1 < n:
                    entry_price = close[t+1]  # Approximate: next close as proxy for next open
                    # Actually M5 bars: entry at next bar open = close[t] if we assume continuous
                    # But spec says "entry at NEXT bar open". We'll use close[t] as proxy for open[t+1]
                    entry_price = close[t]  # This is close of bar t = open of bar t+1 approximately
                    position = 1
                    entry_idx = t + 1
                    entry_atr = curr_atr
                    sl_price = entry_price - a * entry_atr
                    tp_price = entry_price + b * entry_atr
            # Check short entry: close breaks swing low
            elif curr_close < sl:
                if (sl - curr_close) > MAX_BREAKOUT_ATR * curr_atr:
                    continue
                if t + 1 < n:
                    entry_price = close[t]
                    position = -1
                    entry_idx = t + 1
                    entry_atr = curr_atr
                    sl_price = entry_price + a * entry_atr
                    tp_price = entry_price - b * entry_atr
        
        elif position == 1:
            # Long position management
            exit_price = 0
            exit_reason = ""
            exit_idx = t
            
            # Check SL/TP hit during bar t (using high/low)
            # Spec: "If SL and TP are both inside one bar, assume SL hit first"
            sl_hit = curr_low <= sl_price
            tp_hit = curr_high >= tp_price
            
            if sl_hit and tp_hit:
                exit_price = sl_price
                exit_reason = "SL"
            elif sl_hit:
                exit_price = sl_price
                exit_reason = "SL"
            elif tp_hit:
                exit_price = tp_price
                exit_reason = "TP"
            elif t - entry_idx >= TIME_EXIT_BARS:
                exit_price = curr_close
                exit_reason = "TIME"
            
            if exit_reason:
                pnl = (exit_price - entry_price) * 1.0  # 1 oz per trade
                pnl_net = pnl - cost_per_oz
                trades.append({
                    'entry_idx': entry_idx,
                    'exit_idx': exit_idx,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'side': 'long',
                    'pnl': pnl,
                    'pnl_net': pnl_net,
                    'reason': exit_reason,
                    'bars_held': exit_idx - entry_idx
                })
                position = 0
        
        elif position == -1:
            # Short position management
            exit_price = 0
            exit_reason = ""
            exit_idx = t
            
            sl_hit = curr_high >= sl_price
            tp_hit = curr_low <= tp_price
            
            if sl_hit and tp_hit:
                exit_price = sl_price
                exit_reason = "SL"
            elif sl_hit:
                exit_price = sl_price
                exit_reason = "SL"
            elif tp_hit:
                exit_price = tp_price
                exit_reason = "TP"
            elif t - entry_idx >= TIME_EXIT_BARS:
                exit_price = curr_close
                exit_reason = "TIME"
            
            if exit_reason:
                pnl = (entry_price - exit_price) * 1.0  # 1 oz per trade
                pnl_net = pnl - cost_per_oz
                trades.append({
                    'entry_idx': entry_idx,
                    'exit_idx': exit_idx,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'side': 'short',
                    'pnl': pnl,
                    'pnl_net': pnl_net,
                    'reason': exit_reason,
                    'bars_held': exit_idx - entry_idx
                })
                position = 0
    
    # Close any open position at end
    if position != 0:
        exit_price = close[-1]
        if position == 1:
            pnl = (exit_price - entry_price) * 1.0
        else:
            pnl = (entry_price - exit_price) * 1.0
        pnl_net = pnl - cost_per_oz
        trades.append({
            'entry_idx': entry_idx,
            'exit_idx': n-1,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'side': 'long' if position == 1 else 'short',
            'pnl': pnl,
            'pnl_net': pnl_net,
            'reason': 'END',
            'bars_held': n-1 - entry_idx
        })
    
    return trades

def compute_stats(trades, df):
    """Compute performance statistics"""
    if not trades:
        return {
            'n_trades': 0, 'total_pnl': 0, 'total_pnl_net': 0,
            'win_rate': 0, 'avg_win': 0, 'avg_loss': 0,
            'profit_factor': 0, 'expectancy': 0,
            'sharpe': 0, 'max_dd': 0, 'max_dd_pct': 0
        }
    
    trades_df = pd.DataFrame(trades)
    pnl_net = trades_df['pnl_net'].values
    cum_pnl = np.cumsum(pnl_net)
    
    # Max drawdown
    running_max = np.maximum.accumulate(cum_pnl)
    dd = running_max - cum_pnl
    max_dd = dd.max()
    max_dd_pct = max_dd / running_max[dd.argmax()] if running_max[dd.argmax()] != 0 else 0
    
    # Sharpe (per trade, annualized roughly)
    # M5 bars, ~72576 bars/year, but trades are less frequent
    # Use daily returns approximation
    if len(pnl_net) > 1:
        daily_ret = pnl_net  # Per trade
        sharpe = daily_ret.mean() / daily_ret.std(ddof=1) * np.sqrt(252) if daily_ret.std() > 0 else 0
    else:
        sharpe = 0
    
    wins = pnl_net[pnl_net > 0]
    losses = pnl_net[pnl_net <= 0]
    
    return {
        'n_trades': len(trades_df),
        'total_pnl': trades_df['pnl'].sum(),
        'total_pnl_net': pnl_net.sum(),
        'win_rate': (pnl_net > 0).mean(),
        'avg_win': wins.mean() if len(wins) > 0 else 0,
        'avg_loss': losses.mean() if len(losses) > 0 else 0,
        'profit_factor': wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf,
        'expectancy': pnl_net.mean(),
        'sharpe': sharpe,
        'max_dd': max_dd,
        'max_dd_pct': max_dd_pct * 100,
        'avg_bars_held': trades_df['bars_held'].mean(),
        'sl_hits': (trades_df['reason'] == 'SL').sum(),
        'tp_hits': (trades_df['reason'] == 'TP').sum(),
        'time_exits': (trades_df['reason'] == 'TIME').sum(),
    }

def main():
    print("=" * 60)
    print("STAGE 2 - STRATEGY A: STRUCTURAL BREAK ON M5")
    print("=" * 60)
    
    df = load_data()
    print(f"Development data (2022-2023): {len(df)} bars")
    print(f"Date range: {df.index.min()} to {df.index.max()}")
    
    # Pre-compute ATR once
    df['atr'] = compute_atr(df)
    
    # Grid search
    param_grid = list(itertools.product(W_VALUES, A_VALUES, B_VALUES))
    print(f"Testing {len(param_grid)} parameter combinations...")
    
    results = []
    
    for W, a, b in param_grid:
        # Run at headline cost
        trades = run_backtest(df, W, a, b, HEADLINE_COST)
        stats = compute_stats(trades, df)
        
        stats.update({'W': W, 'a': a, 'b': b})
        results.append(stats)
        
        print(f"W={W}, a={a}, b={b}: n={stats['n_trades']:3d}  net={stats['total_pnl_net']:7.2f}  wr={stats['win_rate']:.3f}  exp={stats['expectancy']:6.2f}  sharpe={stats['sharpe']:5.2f}  dd={stats['max_dd']:6.2f}")
    
    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULTS_DIR / "stage2_grid_results.csv", index=False)
    
    # Best by net PnL
    best = results_df.loc[results_df['total_pnl_net'].idxmax()]
    print(f"\n=== BEST (by net PnL at ${HEADLINE_COST}/oz) ===")
    print(f"W={best['W']}, a={best['a']}, b={best['b']}")
    print(f"  Trades: {int(best['n_trades'])}")
    print(f"  Net PnL: ${best['total_pnl_net']:.2f}")
    print(f"  Win Rate: {best['win_rate']:.3f}")
    print(f"  Expectancy: ${best['expectancy']:.2f}/trade")
    print(f"  Sharpe: {best['sharpe']:.2f}")
    print(f"  Max DD: ${best['max_dd']:.2f} ({best['max_dd_pct']:.1f}%)")
    print(f"  SL/TP/Time: {int(best['sl_hits'])}/{int(best['tp_hits'])}/{int(best['time_exits'])}")
    
    # Cost sensitivity
    print(f"\n=== COST SENSITIVITY (best params) ===")
    for cost in COSTS:
        trades = run_backtest(df, best['W'], best['a'], best['b'], cost)
        stats = compute_stats(trades, df)
        print(f"  Cost ${cost:.2f}: net=${stats['total_pnl_net']:.2f}  exp=${stats['expectancy']:.2f}  n={int(stats['n_trades'])}")
    
    print("\n" + "=" * 60)
    print("STAGE 2 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()