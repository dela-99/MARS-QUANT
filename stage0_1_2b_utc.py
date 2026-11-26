#!/usr/bin/env python3
"""
Stage 0, 1, 2b re-run with:
- All data files combined (2020-2023 for development)
- UTC conversion from broker time (GMT+2/3 with DST)
- Stage 0: coverage by year
- Stage 1: session drift by year/decade, UTC-corrected
- Stage 2b: M5/M15/H1/H4, fixed params W=10, a=1.5, b=3, costs $0/$0.50
  Plus per-year gross expectancy and t-stat per timeframe
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')

DATA_DIR = Path(r"C:/Users/RIDGE/trading-data")
RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")

# Fixed parameters for Stage 2b
W = 10
A = 1.5
B = 3.0
TIME_EXIT_BARS = 20
MAX_BREAKOUT_ATR = 5.0
COSTS = [0.00, 0.50]

# ============================================================
# UTC CONVERSION: Broker time (GMT+2/3 with EU DST) -> UTC
# ============================================================
def broker_to_utc(df):
    """Convert broker server time to UTC.
    Broker: GMT+2 (winter), GMT+3 (summer DST).
    EU DST: last Sunday March 01:00 UTC -> last Sunday October 01:00 UTC
    In broker time: DST starts last Sunday March 03:00, ends last Sunday October 04:00
    """
    idx = df.index
    year = idx.year
    
    # Compute DST start/end for each year
    def last_sunday(year, month):
        # Last Sunday of month
        if month == 3:
            d = pd.Timestamp(year, 3, 31)
        else:  # October
            d = pd.Timestamp(year, 10, 31)
        # Day of week: Monday=0, Sunday=6
        offset = (d.dayofweek + 1) % 7  # days to subtract to get to Sunday
        return d - pd.Timedelta(days=offset)
    
    dst_start = idx.map(lambda d: last_sunday(d.year, 3))
    dst_end = idx.map(lambda d: last_sunday(d.year, 10))
    
    # In broker time, DST is active from last Sun Mar 03:00 to last Sun Oct 04:00
    # But our data is in broker local time, so:
    is_dst = (idx >= dst_start + pd.Timedelta(hours=3)) & (idx < dst_end + pd.Timedelta(hours=4))
    
    # Offset: GMT+2 normally, GMT+3 during DST
    offset_hours = np.where(is_dst, 3, 2)
    utc_idx = idx - pd.to_timedelta(offset_hours, unit='h')
    
    df_utc = df.copy()
    df_utc.index = utc_idx
    return df_utc.sort_index()

def load_all_data():
    """Load and combine all CSV files"""
    files = sorted(DATA_DIR.glob("XAUUSDm_M5_*.csv"))
    dfs = []
    for f in files:
        df = pd.read_csv(f, sep='\t')
        df['datetime'] = pd.to_datetime(df['<DATE>'] + ' ' + df['<TIME>'], format='%Y.%m.%d %H:%M:%S')
        df = df.set_index('datetime').sort_index()
        dfs.append(df)
    combined = pd.concat(dfs, ignore_index=False).sort_index()
    return combined

def preprocess(df):
    """Standard preprocessing: drop weekends, DST transitions, zero spread"""
    df = df[df.index.dayofweek < 5].copy()
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    df = df[diffs != 65].copy()  # Drop 65-min DST bars
    df = df[df['<SPREAD>'] > 0].copy()
    df['spread_pips'] = df['<SPREAD>'] / 10
    return df

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

def resample_ohlc(df, rule):
    return df.resample(rule).agg({
        '<OPEN>': 'first', '<HIGH>': 'max', '<LOW>': 'min', '<CLOSE>': 'last',
        '<TICKVOL>': 'sum', '<VOL>': 'sum', '<SPREAD>': 'mean'
    }).dropna()

# ============================================================
# MAIN
# ============================================================
print("=" * 70)
print("STAGE 0/1/2b RE-RUN WITH UTC CONVERSION")
print("=" * 70)

# Load all data
df_raw = load_all_data()
print(f"\nRaw data: {len(df_raw)} bars, {df_raw.index.min()} to {df_raw.index.max()}")

# Convert to UTC
df_utc = broker_to_utc(df_raw)
print(f"UTC data: {len(df_utc)} bars, {df_utc.index.min()} to {df_utc.index.max()}")

# Preprocess
df_clean = preprocess(df_utc)
print(f"Clean data: {len(df_clean)} bars")

# Restrict to development period (up to 2023-12-31)
df_dev = df_clean[df_clean.index <= '2023-12-31'].copy()
print(f"Development period (2000-2023): {len(df_dev)} bars, {df_dev.index.min()} to {df_dev.index.max()}")

# ============================================================
# STAGE 0: Coverage by year
# ============================================================
print("\n" + "=" * 70)
print("STAGE 0: COVERAGE BY YEAR (UTC)")
print("=" * 70)
yearly = df_dev.groupby(df_dev.index.year).size()
expected_per_year = 252 * 24 * 12  # 72576 for M5 24/5
print(f"{'Year':>6}  {'Bars':>8}  {'Expected':>8}  {'Coverage':>8}")
for yr, cnt in yearly.items():
    cov = cnt / expected_per_year * 100
    print(f"{yr:>6}  {cnt:>8}  {expected_per_year:>8}  {cov:>7.1f}%")

# ============================================================
# STAGE 1: Session Drift (UTC sessions)
# ============================================================
print("\n" + "=" * 70)
print("STAGE 1: SESSION DRIFT (UTC sessions)")
print("=" * 70)

# UTC sessions: Asia 00-08, Europe 08-14:30, US 14:30-24
hour = df_dev.index.hour + df_dev.index.minute / 60
conditions = [
    (hour >= 0) & (hour < 8),
    (hour >= 8) & (hour < 14.5),
    (hour >= 14.5) & (hour < 24)
]
choices = ['Asia', 'Europe', 'US']
df_dev['session'] = np.select(conditions, choices, default='Other')

df_dev['ret_bp'] = df_dev['<CLOSE>'].pct_change() * 10000

print(f"\n{'Session':>6}  {'Bars':>8}  {'Mean_bp':>8}  {'Hit%':>6}  {'t-stat':>7}")
for sess in ['Asia', 'Europe', 'US']:
    ret = df_dev[df_dev['session']==sess]['ret_bp'].dropna()
    mean_bp = ret.mean()
    std_bp = ret.std(ddof=1)
    hit = (ret > 0).mean()
    t = mean_bp / (std_bp / np.sqrt(len(ret))) if std_bp > 0 else 0
    print(f"{sess:>6}  {len(ret):>8}  {mean_bp:>8.2f}  {hit*100:>5.1f}%  {t:>7.2f}")

# By year
print(f"\n{'Year':>4}  {'Session':>6}  {'Bars':>6}  {'Mean_bp':>8}  {'Hit%':>6}  {'t-stat':>7}")
for yr in sorted(df_dev.index.year.unique()):
    yr_df = df_dev[df_dev.index.year == yr]
    for sess in ['Asia', 'Europe', 'US']:
        ret = yr_df[yr_df['session']==sess]['ret_bp'].dropna()
        if len(ret) < 50:
            continue
        mean_bp = ret.mean()
        std_bp = ret.std(ddof=1)
        hit = (ret > 0).mean()
        t = mean_bp / (std_bp / np.sqrt(len(ret))) if std_bp > 0 else 0
        print(f"{yr:>4}  {sess:>6}  {len(ret):>6}  {mean_bp:>8.2f}  {hit*100:>5.1f}%  {t:>7.2f}")

# By decade
print(f"\n{'Decade':>6}  {'Session':>6}  {'Bars':>8}  {'Mean_bp':>8}  {'Hit%':>6}  {'t-stat':>7}")
for decade_start in [2000, 2010, 2020]:
    dec_df = df_dev[(df_dev.index.year >= decade_start) & (df_dev.index.year < decade_start+10)]
    if len(dec_df) == 0:
        continue
    for sess in ['Asia', 'Europe', 'US']:
        ret = dec_df[dec_df['session']==sess]['ret_bp'].dropna()
        if len(ret) < 50:
            continue
        mean_bp = ret.mean()
        std_bp = ret.std(ddof=1)
        hit = (ret > 0).mean()
        t = mean_bp / (std_bp / np.sqrt(len(ret))) if std_bp > 0 else 0
        print(f"{decade_start}s  {sess:>6}  {len(ret):>8}  {mean_bp:>8.2f}  {hit*100:>5.1f}%  {t:>7.2f}")

# ============================================================
# STAGE 2b: Cost vs Edge Screen (M5, M15, H1, H4)
# ============================================================
print("\n" + "=" * 70)
print("STAGE 2b: COST vs EDGE SCREEN (UTC, dev period)")
print("=" * 70)

timeframes = {
    'M5': df_dev,
    'M15': resample_ohlc(df_dev, '15min'),
    'H1': resample_ohlc(df_dev, '1h'),
    'H4': resample_ohlc(df_dev, '4h')
}

print(f"\n{'TF':>4}  {'Bars':>8}  {'Cost':>5}  {'Trades':>6}  {'Trades/yr':>8}  {'AvgStop':>8}  {'GrossExp':>9}  {'NetExp':>9}  {'Cost%Stop':>9}  {'GrossExp_t':>10}")
for tf_name, df in timeframes.items():
    high = df['<HIGH>'].values
    low = df['<LOW>'].values
    close = df['<CLOSE>'].values
    
    atr = compute_atr_numpy(high, low, close)
    swing_high, swing_low = find_swings_numpy(high, low, W)
    confirmed_high, confirmed_low = get_confirmed_swings_numpy(swing_high, swing_low, W, high, low)
    
    for cost in COSTS:
        pnl, stops = run_backtest_numpy(close, high, low, atr, confirmed_high, confirmed_low, W, A, B, cost)
        if len(pnl) == 0:
            print(f"{tf_name:>4}  {len(df):>8}  ${cost:>4.2f}  {'0':>6}  {'0':>8}  {'0':>8}  {'0':>9}  {'0':>9}  {'0':>9}  {'0':>10}")
            continue
        
        gross_pnl = pnl + cost
        gross_exp = gross_pnl.mean()
        net_exp = pnl.mean()
        avg_stop = stops.mean() if len(stops) > 0 else 0
        cost_pct_stop = (cost / avg_stop * 100) if avg_stop > 0 else 0
        trades_per_year = len(pnl) / (2023 - 2020 + 1)  # 2020-2023 inclusive = 4 years
        gross_t = gross_exp / (gross_pnl.std(ddof=1) / np.sqrt(len(gross_pnl))) if gross_pnl.std() > 0 else 0
        
        print(f"{tf_name:>4}  {len(df):>8}  ${cost:>4.2f}  {len(pnl):>6}  {trades_per_year:>8.1f}  ${avg_stop:>7.2f}  ${gross_exp:>8.3f}  ${net_exp:>8.3f}  {cost_pct_stop:>8.1f}%  {gross_t:>10.2f}")

# Per-year gross expectancy for each timeframe
print("\n" + "=" * 70)
print("PER-YEAR GROSS EXPECTANCY BY TIMEFRAME")
print("=" * 70)
print(f"{'TF':>4}  {'Year':>4}  {'Trades':>6}  {'GrossExp':>9}  {'Gross_t':>9}")
for tf_name, df in timeframes.items():
    high = df['<HIGH>'].values
    low = df['<LOW>'].values
    close = df['<CLOSE>'].values
    atr = compute_atr_numpy(high, low, close)
    swing_high, swing_low = find_swings_numpy(high, low, W)
    confirmed_high, confirmed_low = get_confirmed_swings_numpy(swing_high, swing_low, W, high, low)
    
    for yr in sorted(df.index.year.unique()):
        yr_mask = (df.index.year == yr)
        if yr_mask.sum() < 100:
            continue
        yr_high = high[yr_mask]
        yr_low = low[yr_mask]
        yr_close = close[yr_mask]
        yr_atr = atr[yr_mask]
        yr_conf_high = confirmed_high[yr_mask]
        yr_conf_low = confirmed_low[yr_mask]
        
        pnl, _ = run_backtest_numpy(yr_close, yr_high, yr_low, yr_atr, yr_conf_high, yr_conf_low, W, A, B, 0.00)
        if len(pnl) == 0:
            continue
        gross_exp = pnl.mean()
        gross_t = gross_exp / (pnl.std(ddof=1) / np.sqrt(len(pnl))) if pnl.std() > 0 else 0
        print(f"{tf_name:>4}  {yr:>4}  {len(pnl):>6}  ${gross_exp:>8.3f}  {gross_t:>9.2f}")

# Total trades over whole period (2000-2023) for each timeframe
print("\n" + "=" * 70)
print("TOTAL TRADES OVER DEVELOPMENT PERIOD (2000-2023)")
print("=" * 70)
for tf_name, df in timeframes.items():
    high = df['<HIGH>'].values
    low = df['<LOW>'].values
    close = df['<CLOSE>'].values
    atr = compute_atr_numpy(high, low, close)
    swing_high, swing_low = find_swings_numpy(high, low, W)
    confirmed_high, confirmed_low = get_confirmed_swings_numpy(swing_high, swing_low, W, high, low)
    pnl, _ = run_backtest_numpy(close, high, low, atr, confirmed_high, confirmed_low, W, A, B, 0.00)
    print(f"{tf_name:>4}: {len(pnl)} trades (gross expectancy=${pnl.mean():.3f})" if len(pnl) > 0 else f"{tf_name:>4}: 0 trades")

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)