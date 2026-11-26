#!/usr/bin/env python3
"""
Stage 2c - Opening Range Breakout (ORB)
Development period: 2022-01-01 to 2023-12-31 (UTC)
Setup A: London 08:00-08:30 range
Setup B: New York 09:30-10:00 range
Entry: first M5 close above/below range, entry at next bar open
Stop = opposite side of range, Target = 1R, Time exit 3h after range end
SL/TP same bar -> SL first
Costs: $0.00 and $0.50/oz
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo
warnings.filterwarnings('ignore')

DATA_DIR = Path(r"C:/Users/RIDGE/trading-data")
RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")

DEV_START = pd.Timestamp('2022-01-01', tz='UTC')
DEV_END = pd.Timestamp('2023-12-31 23:59:59', tz='UTC')

# Also define naive versions for comparison with broker time
DEV_START_NAIVE = pd.Timestamp('2022-01-01')
DEV_END_NAIVE = pd.Timestamp('2023-12-31 23:59:59')

COSTS = [0.00, 0.50]

# Timezone objects
LONDON_TZ = ZoneInfo('Europe/London')
NY_TZ = ZoneInfo('America/New_York')
UTC_TZ = ZoneInfo('UTC')

def load_and_convert_to_utc():
    """Load all M5 files, convert broker time to UTC"""
    files = sorted(DATA_DIR.glob("XAUUSDm_M5_*.csv"))
    dfs = []
    for f in files:
        df = pd.read_csv(f, sep='\t')
        df['datetime'] = pd.to_datetime(df['<DATE>'] + ' ' + df['<TIME>'], format='%Y.%m.%d %H:%M:%S')
        df = df.set_index('datetime').sort_index()
        dfs.append(df)
    combined = pd.concat(dfs, ignore_index=False).sort_index()
    
    # Broker time -> UTC
    # Broker: GMT+2 (winter), GMT+3 (summer EU DST)
    # EU DST: last Sunday March 01:00 UTC to last Sunday October 01:00 UTC
    # In broker local time: DST starts last Sun Mar 03:00, ends last Sun Oct 04:00
    idx = combined.index  # tz-naive
    
    def last_sunday_naive(year, month):
        d = pd.Timestamp(year, month, 31)
        offset = (d.dayofweek + 1) % 7
        return d - pd.Timedelta(days=offset)
    
    # DST transition in broker local time
    # DST starts: last Sunday March at 03:00 broker time
    # DST ends: last Sunday October at 04:00 broker time
    dst_starts = idx.map(lambda d: last_sunday_naive(d.year, 3) + pd.Timedelta(hours=3))
    dst_ends = idx.map(lambda d: last_sunday_naive(d.year, 10) + pd.Timedelta(hours=4))
    
    is_dst = (idx >= dst_starts) & (idx < dst_ends)
    
    # Offset: 2 hours normally, 3 hours during DST
    offset_hours = np.where(is_dst, 3, 2)
    utc_idx = idx - pd.to_timedelta(offset_hours, unit='h')
    
    combined_utc = combined.copy()
    combined_utc.index = utc_idx
    combined_utc = combined_utc.sort_index()
    combined_utc.index = combined_utc.index.tz_localize('UTC')
    
    return combined_utc

def preprocess(df):
    """Standard preprocessing"""
    df = df[df.index.dayofweek < 5].copy()  # Drop weekends
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    df = df[diffs != 65].copy()  # Drop DST transition bars
    df = df[df['<SPREAD>'] > 0].copy()
    df['spread_pips'] = df['<SPREAD>'] / 10
    df['spread_dollars'] = df['<SPREAD>'] / 10 * 1.0  # 1 pip = $1 per oz
    return df

def get_daily_range(df_utc, session_name):
    """
    Get opening range for each day.
    session_name: 'London' or 'New_York'
    Returns DataFrame with columns: date, range_high, range_low, range_start_idx, range_end_idx
    """
    # Convert to local time
    if session_name == 'London':
        local_idx = df_utc.index.tz_convert(LONDON_TZ)
        range_start_hour, range_start_min = 8, 0
    else:  # New_York
        local_idx = df_utc.index.tz_convert(NY_TZ)
        range_start_hour, range_start_min = 9, 30
    
    df_local = df_utc.copy()
    df_local.index = local_idx
    
    # Group by local date
    ranges = []
    for date, day_df in df_local.groupby(df_local.index.date):
        # Find range period: first 30 min after range_start
        range_start = pd.Timestamp.combine(date, pd.Timestamp.min.time().replace(hour=range_start_hour, minute=range_start_min))
        range_start = range_start.tz_localize(local_idx.tz)
        range_end = range_start + pd.Timedelta(minutes=30)
        
        range_bars = day_df[(day_df.index >= range_start) & (day_df.index < range_end)]
        if len(range_bars) < 5:  # Need at least 5 M5 bars (25 min)
            continue
        
        range_high = range_bars['<HIGH>'].max()
        range_low = range_bars['<LOW>'].min()
        
        # Find indices in UTC dataframe
        utc_range_start = range_start.tz_convert(UTC_TZ)
        utc_range_end = range_end.tz_convert(UTC_TZ)
        
        ranges.append({
            'date': date,
            'range_high': range_high,
            'range_low': range_low,
            'range_size': range_high - range_low,
            'utc_range_start': utc_range_start,
            'utc_range_end': utc_range_end,
            'local_range_start': range_start,
            'local_range_end': range_end
        })
    
    return pd.DataFrame(ranges).set_index('date')

def run_orb_backtest(df_utc, ranges_df, cost_per_oz):
    """
    Run ORB backtest for a single setup.
    Entry: first M5 close above range_high (long) or below range_low (short)
    Entry at next bar open
    Stop = opposite side of range, Target = 1R (range_size)
    Time exit: 3 hours after range end
    """
    trades = []
    
    for date, row in ranges_df.iterrows():
        range_high = row['range_high']
        range_low = row['range_low']
        range_size = row['range_size']
        utc_range_end = row['utc_range_end']
        time_exit = utc_range_end + pd.Timedelta(hours=3)
        
        # Get bars after range end until time exit
        mask = (df_utc.index > utc_range_end) & (df_utc.index <= time_exit)
        day_bars = df_utc[mask].copy()
        
        if len(day_bars) == 0:
            continue
        
        position = 0
        entry_price = 0
        sl_price = 0
        tp_price = 0
        entry_idx = 0
        
        for i, (ts, bar) in enumerate(day_bars.iterrows()):
            if position == 0:
                # Check for breakout
                if bar['<CLOSE>'] > range_high:
                    # Long signal
                    if i + 1 < len(day_bars):
                        entry_price = day_bars.iloc[i+1]['<OPEN>']
                        sl_price = range_low
                        tp_price = entry_price + range_size  # 1R
                        position = 1
                        entry_idx = i + 1
                elif bar['<CLOSE>'] < range_low:
                    # Short signal
                    if i + 1 < len(day_bars):
                        entry_price = day_bars.iloc[i+1]['<OPEN>']
                        sl_price = range_high
                        tp_price = entry_price - range_size  # 1R
                        position = -1
                        entry_idx = i + 1
            
            elif position == 1:
                # Long position
                sl_hit = bar['<LOW>'] <= sl_price
                tp_hit = bar['<HIGH>'] >= tp_price
                time_exit_hit = (i >= entry_idx + int(3 * 60 / 5))  # 3 hours = 36 M5 bars
                
                if sl_hit or tp_hit or time_exit_hit or i == len(day_bars) - 1:
                    if sl_hit and tp_hit:
                        exit_price = sl_price  # SL first
                    elif sl_hit:
                        exit_price = sl_price
                    elif tp_hit:
                        exit_price = tp_price
                    else:
                        exit_price = bar['<CLOSE>']
                    
                    pnl = (exit_price - entry_price) - cost_per_oz
                    trades.append({
                        'date': date,
                        'side': 'long',
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'range_size': range_size,
                        'exit_reason': 'SL' if sl_hit else ('TP' if tp_hit else 'TIME')
                    })
                    position = 0
                    break  # One trade per day
            
            elif position == -1:
                # Short position
                sl_hit = bar['<HIGH>'] >= sl_price
                tp_hit = bar['<LOW>'] <= tp_price
                time_exit_hit = (i >= entry_idx + int(3 * 60 / 5))
                
                if sl_hit or tp_hit or time_exit_hit or i == len(day_bars) - 1:
                    if sl_hit and tp_hit:
                        exit_price = sl_price  # SL first
                    elif sl_hit:
                        exit_price = sl_price
                    elif tp_hit:
                        exit_price = tp_price
                    else:
                        exit_price = bar['<CLOSE>']
                    
                    pnl = (entry_price - exit_price) - cost_per_oz
                    trades.append({
                        'date': date,
                        'side': 'short',
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'range_size': range_size,
                        'exit_reason': 'SL' if sl_hit else ('TP' if tp_hit else 'TIME')
                    })
                    position = 0
                    break  # One trade per day
    
    return pd.DataFrame(trades) if trades else pd.DataFrame()

def compute_stats(trades_df, cost_per_oz):
    """Compute performance statistics"""
    if len(trades_df) == 0:
        return {
            'n': 0, 'trades_per_year': 0, 'avg_stop': 0,
            'gross_exp': 0, 'net_exp': 0, 'win_rate': 0,
            'gross_t': 0
        }
    
    pnl = trades_df['pnl'].values
    gross_pnl = pnl + cost_per_oz
    gross_exp = gross_pnl.mean()
    net_exp = pnl.mean()
    win_rate = (pnl > 0).mean()
    avg_stop = trades_df['range_size'].mean()
    gross_t = gross_exp / (gross_pnl.std(ddof=1) / np.sqrt(len(gross_pnl))) if gross_pnl.std() > 0 else 0
    trades_per_year = len(trades_df) / 2  # 2 years
    
    return {
        'n': len(trades_df),
        'trades_per_year': trades_per_year,
        'avg_stop': avg_stop,
        'gross_exp': gross_exp,
        'net_exp': net_exp,
        'win_rate': win_rate,
        'gross_t': gross_t
    }

def spread_by_utc_hour(df_utc):
    """Spread distribution by UTC hour"""
    df_utc = df_utc.copy()
    df_utc['utc_hour'] = df_utc.index.hour
    spread_stats = df_utc.groupby('utc_hour')['spread_dollars'].agg(['mean', 'median', lambda x: x.quantile(0.9)]).round(4)
    spread_stats.columns = ['mean', 'median', 'p90']
    return spread_stats

def main():
    print("=" * 70)
    print("STAGE 2c - OPENING RANGE BREAKOUT")
    print("=" * 70)
    
    # Load and convert
    df_utc = load_and_convert_to_utc()
    print(f"Loaded UTC data: {len(df_utc)} bars, {df_utc.index.min()} to {df_utc.index.max()}")
    
    # Preprocess
    df_utc = preprocess(df_utc)
    print(f"After preprocessing: {len(df_utc)} bars")
    
    # Restrict to development period
    df_dev = df_utc[(df_utc.index >= DEV_START) & (df_utc.index <= DEV_END)].copy()
    print(f"Development period (2022-2023): {len(df_dev)} bars, {df_dev.index.min()} to {df_dev.index.max()}")
    
    # Also keep a naive version for DST calculations if needed
    df_dev_naive = df_dev.copy()
    df_dev_naive.index = df_dev_naive.index.tz_convert(None)
    
    # Spread by UTC hour
    print("\n--- SPREAD BY UTC HOUR ($ per oz) ---")
    spread_stats = spread_by_utc_hour(df_dev)
    print(f"{'Hour':>4}  {'Mean':>8}  {'Median':>8}  {'P90':>8}")
    for hour in range(24):
        if hour in spread_stats.index:
            row = spread_stats.loc[hour]
            print(f"{hour:>4}  {row['mean']:>8.4f}  {row['median']:>8.4f}  {row['p90']:>8.4f}")
        else:
            print(f"{hour:>4}  {'N/A':>8}  {'N/A':>8}  {'N/A':>8}")
    
    # Setup A: London 08:00-08:30
    print("\n--- SETUP A: LONDON 08:00-08:30 RANGE ---")
    london_ranges = get_daily_range(df_dev, 'London')
    print(f"Days with valid range: {len(london_ranges)}")
    
    for cost in COSTS:
        trades = run_orb_backtest(df_dev, london_ranges, cost)
        stats = compute_stats(trades, cost)
        print(f"  Cost ${cost:.2f}: trades={stats['n']}  trades/yr={stats['trades_per_year']:.1f}  "
              f"avg_stop=${stats['avg_stop']:.4f}  gross_exp=${stats['gross_exp']:.4f}  "
              f"net_exp=${stats['net_exp']:.4f}  wr={stats['win_rate']:.3f}  gross_t={stats['gross_t']:.2f}")
    
    # Per-year for London
    for cost in COSTS:
        trades = run_orb_backtest(df_dev, london_ranges, cost)
        if len(trades) > 0:
            trades['year'] = trades['date'].apply(lambda d: d.year)
            print(f"  Cost ${cost:.2f} per-year gross expectancy:")
            for yr in [2022, 2023]:
                yr_trades = trades[trades['year'] == yr]
                if len(yr_trades) > 0:
                    gross_pnl = yr_trades['pnl'] + cost
                    gross_exp = gross_pnl.mean()
                    gross_t = gross_exp / (gross_pnl.std(ddof=1) / np.sqrt(len(gross_pnl))) if gross_pnl.std() > 0 else 0
                    print(f"    {yr}: n={len(yr_trades)}  gross_exp=${gross_exp:.4f}  gross_t={gross_t:.2f}")
    
    # Setup B: New York 09:30-10:00
    print("\n--- SETUP B: NEW YORK 09:30-10:00 RANGE ---")
    ny_ranges = get_daily_range(df_dev, 'New_York')
    print(f"Days with valid range: {len(ny_ranges)}")
    
    for cost in COSTS:
        trades = run_orb_backtest(df_dev, ny_ranges, cost)
        stats = compute_stats(trades, cost)
        print(f"  Cost ${cost:.2f}: trades={stats['n']}  trades/yr={stats['trades_per_year']:.1f}  "
              f"avg_stop=${stats['avg_stop']:.4f}  gross_exp=${stats['gross_exp']:.4f}  "
              f"net_exp=${stats['net_exp']:.4f}  wr={stats['win_rate']:.3f}  gross_t={stats['gross_t']:.2f}")
    
    # Per-year for NY
    for cost in COSTS:
        trades = run_orb_backtest(df_dev, ny_ranges, cost)
        if len(trades) > 0:
            trades['year'] = trades['date'].apply(lambda d: d.year)
            print(f"  Cost ${cost:.2f} per-year gross expectancy:")
            for yr in [2022, 2023]:
                yr_trades = trades[trades['year'] == yr]
                if len(yr_trades) > 0:
                    gross_pnl = yr_trades['pnl'] + cost
                    gross_exp = gross_pnl.mean()
                    gross_t = gross_exp / (gross_pnl.std(ddof=1) / np.sqrt(len(gross_pnl))) if gross_pnl.std() > 0 else 0
                    print(f"    {yr}: n={len(yr_trades)}  gross_exp=${gross_exp:.4f}  gross_t={gross_t:.2f}")
    
    # Log to trials.csv
    trials_rows = []
    
    for setup_name, ranges_df in [('London_0800', london_ranges), ('NY_0930', ny_ranges)]:
        for cost in COSTS:
            trades = run_orb_backtest(df_dev, ranges_df, cost)
            stats = compute_stats(trades, cost)
            trials_rows.append({
                'stage': 'stage2c',
                'setup': setup_name,
                'W': np.nan, 'a': np.nan, 'b': np.nan,
                'cost': cost,
                'net_pnl': stats['net_exp'] * stats['n'] if stats['n'] > 0 else 0,
                'expectancy': stats['net_exp'],
                'win_rate': stats['win_rate'],
                'sharpe': np.nan,
                'max_dd': np.nan,
                'n_trades': stats['n'],
                'timeframe': 'M5',
                'trades_per_year': stats['trades_per_year'],
                'avg_stop_dist': stats['avg_stop'],
                'gross_exp': stats['gross_exp'],
                'cost_pct_stop': (cost / stats['avg_stop'] * 100) if stats['avg_stop'] > 0 else 0,
                'gross_t': stats['gross_t']
            })
    
    # Append to trials.csv
    existing = pd.read_csv(RESULTS_DIR / "trials.csv")
    new_trials = pd.DataFrame(trials_rows)
    combined = pd.concat([existing, new_trials], ignore_index=True)
    combined.to_csv(RESULTS_DIR / "trials.csv", index=False)
    
    print("\n" + "=" * 70)
    print("STAGE 2c COMPLETE - Logged to trials.csv")
    print("=" * 70)

if __name__ == "__main__":
    main()