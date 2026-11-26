#!/usr/bin/env python3
"""
Stage 1 - Session Drift Test for XAUUSD M5
UTC sessions per spec: Asia 00:00-08:00, Europe 08:00-14:30, US 14:30-24:00
London PM fix to next AM fix (London local time).

IMPORTANT: Data is in BROKER SERVER TIME (GMT+2/3 with DST), NOT UTC.
We analyze using the data's native timebase and map sessions accordingly.
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')

RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")

def load_clean_data():
    """Load and preprocess data per Stage 0 recommendations"""
    df = pd.read_parquet(RESULTS_DIR / "xauusd_m5_clean.parquet")
    
    # Drop weekends
    df = df[df.index.dayofweek < 5].copy()
    
    # Drop DST transition bars (65-min intervals)
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    df = df[diffs != 65].copy()
    
    # Drop zero-spread bars
    df = df[df['<SPREAD>'] > 0].copy()
    
    # Convert spread to pips
    df['spread_pips'] = df['<SPREAD>'] / 10
    
    # Restrict to 2022-01-01 onward for development
    df = df[df.index >= '2022-01-01'].copy()
    
    # Calculate returns (bp) - close-to-close
    df['ret_bp'] = df['<CLOSE>'].pct_change() * 10000  # basis points
    
    return df

def assign_sessions(df):
    """Assign session labels based on BROKER TIME (GMT+2/3)"""
    # Broker time sessions (GMT+2 winter / GMT+3 summer)
    # Asia: 00:00-08:00 broker time
    # Europe: 08:00-14:30 broker time  
    # US: 14:30-24:00 broker time
    hour = df.index.hour + df.index.minute / 60
    
    conditions = [
        (hour >= 0) & (hour < 8),
        (hour >= 8) & (hour < 14.5),
        (hour >= 14.5) & (hour < 24)
    ]
    choices = ['Asia', 'Europe', 'US']
    df['session'] = np.select(conditions, choices, default='Other')
    
    # London PM fix to next AM fix (London local = broker - 2 or -3 depending on DST)
    # London fix at 16:00 London time = 18:00/19:00 broker time
    # Next AM fix at 08:00 London time = 10:00/11:00 broker time
    # This spans overnight. We'll compute separately.
    
    return df

def london_fix_sessions(df):
    """London PM fix (16:00 London) to next AM fix (08:00 London)"""
    # London time = broker time - 2 (winter) or -3 (summer)
    # Approximate: assume broker is GMT+2 (winter) / GMT+3 (summer)
    # Use a simple heuristic: DST in EU is last Sun Mar to last Sun Oct
    def is_dst(dt):
        # EU DST: last Sunday March to last Sunday October
        year = dt.year
        # Last Sunday March
        mar31 = pd.Timestamp(year, 3, 31)
        dst_start = mar31 - pd.Timedelta(days=mar31.weekday() + 1 if mar31.weekday() < 6 else 0)
        # Last Sunday October
        oct31 = pd.Timestamp(year, 10, 31)
        dst_end = oct31 - pd.Timedelta(days=oct31.weekday() + 1 if oct31.weekday() < 6 else 0)
        return dst_start <= dt < dst_end
    
    df = df.copy()
    df['is_dst'] = df.index.to_series().apply(is_dst)
    df['london_hour'] = df.index.hour + df.index.minute/60 - df['is_dst'].astype(int)*3 - (~df['is_dst']).astype(int)*2
    
    # London fix window: 16:00 to next 08:00 London time
    # This crosses midnight, so we need to handle date change
    df['london_fix'] = ((df['london_hour'] >= 16) | (df['london_hour'] < 8)).astype(int)
    
    return df

def block_bootstrap_tstat(returns, n_blocks=200, block_size=20):
    """Block bootstrap t-stat for autocorrelated returns - optimized"""
    n = len(returns)
    if n < block_size * 2:
        return np.nan, np.nan
    
    mean_ret = returns.mean()
    std_ret = returns.std(ddof=1)
    t_stat = mean_ret / (std_ret / np.sqrt(n)) if std_ret > 0 else np.nan
    
    # Block bootstrap for robust SE - reduced iterations
    n_blocks_avail = n // block_size
    if n_blocks_avail < 2:
        return t_stat, np.nan
    
    # Pre-split returns into blocks
    blocks = [returns.iloc[i*block_size:(i+1)*block_size].values for i in range(n_blocks_avail)]
    
    block_means = []
    for _ in range(n_blocks):
        idx = np.random.randint(0, n_blocks_avail, n_blocks_avail)
        sample = np.concatenate([blocks[i] for i in idx])
        if len(sample) > 1:
            block_means.append(sample.mean())
    
    if len(block_means) > 10:
        boot_se = np.std(block_means, ddof=1)
        boot_t = mean_ret / boot_se if boot_se > 0 else np.nan
    else:
        boot_t = np.nan
    
    return t_stat, boot_t

def analyze_session(df, session_name, cost_bp=50):  # $0.50/oz ≈ 50bp at $1000/oz, ~25bp at $2000
    """Analyze a single session"""
    sess_df = df[df['session'] == session_name].copy()
    if len(sess_df) < 100:
        return None
    
    ret = sess_df['ret_bp'].dropna()
    
    # Gross stats
    mean_gross = ret.mean()
    std_gross = ret.std(ddof=1)
    hit_rate = (ret > 0).mean()
    t_stat, boot_t = block_bootstrap_tstat(ret)
    
    # Net of cost (round-trip cost applied per trade opportunity)
    # For session drift, we're looking at mean return per bar, not per trade
    # Cost per bar depends on trading frequency. As drift test, report gross.
    # But also show net assuming 1 trade per session day (conservative)
    
    return {
        'session': session_name,
        'n_bars': len(ret),
        'mean_bp': mean_gross,
        'std_bp': std_gross,
        'hit_rate': hit_rate,
        't_stat': t_stat,
        'boot_t': boot_t
    }

def analyze_by_year_decade(df):
    """Breakdown by year and decade"""
    results = []
    
    for session in ['Asia', 'Europe', 'US']:
        sess_df = df[df['session'] == session].copy()
        if len(sess_df) < 100:
            continue
            
        # By year
        for year in sorted(sess_df.index.year.unique()):
            yr_df = sess_df[sess_df.index.year == year]
            ret = yr_df['ret_bp'].dropna()
            if len(ret) < 50:
                continue
            mean_bp = ret.mean()
            std_bp = ret.std(ddof=1)
            hit = (ret > 0).mean()
            t, bt = block_bootstrap_tstat(ret)
            results.append({
                'session': session, 'period': str(year), 'type': 'year',
                'n': len(ret), 'mean_bp': mean_bp, 'std_bp': std_bp,
                'hit_rate': hit, 't_stat': t, 'boot_t': bt
            })
        
        # By decade (2020s only in our data)
        dec_df = sess_df[sess_df.index.year >= 2020]
        ret = dec_df['ret_bp'].dropna()
        if len(ret) >= 50:
            mean_bp = ret.mean()
            std_bp = ret.std(ddof=1)
            hit = (ret > 0).mean()
            t, bt = block_bootstrap_tstat(ret)
            results.append({
                'session': session, 'period': '2020s', 'type': 'decade',
                'n': len(ret), 'mean_bp': mean_bp, 'std_bp': std_bp,
                'hit_rate': hit, 't_stat': t, 'boot_t': bt
            })
    
    return pd.DataFrame(results)

def main():
    print("=" * 60)
    print("STAGE 1 - SESSION DRIFT TEST")
    print("=" * 60)
    
    df = load_clean_data()
    print(f"Clean bars (2022+): {len(df)}")
    
    df = assign_sessions(df)
    df = london_fix_sessions(df)
    
    # Session distribution
    print("\nSession bar counts:")
    print(df['session'].value_counts())
    print(f"London fix bars: {df['london_fix'].sum()}")
    
    # Overall session stats (gross)
    print("\n=== SESSION STATS (gross, per M5 bar) ===")
    session_results = []
    for sess in ['Asia', 'Europe', 'US']:
        res = analyze_session(df, sess)
        if res:
            session_results.append(res)
            print(f"{sess:6s}: n={res['n_bars']:6d}  mean={res['mean_bp']:7.2f}bp  std={res['std_bp']:7.2f}  hit={res['hit_rate']:.3f}  t={res['t_stat']:6.2f}  boot_t={res['boot_t']:6.2f}")
    
    # By year/decade
    print("\n=== BY YEAR ===")
    yr_results = analyze_by_year_decade(df)
    for _, row in yr_results.iterrows():
        print(f"{row['session']:6s} {row['period']:>5s}: n={row['n']:5d}  mean={row['mean_bp']:7.2f}bp  hit={row['hit_rate']:.3f}  t={row['t_stat']:6.2f}  boot_t={row['boot_t']:6.2f}")
    
    # London fix window
    print("\n=== LONDON FIX WINDOW (16:00-08:00 London) ===")
    fix_df = df[df['london_fix'] == 1]
    ret = fix_df['ret_bp'].dropna()
    mean_bp = ret.mean()
    std_bp = ret.std(ddof=1)
    hit = (ret > 0).mean()
    t, bt = block_bootstrap_tstat(ret)
    print(f"London fix: n={len(ret):5d}  mean={mean_bp:7.2f}bp  hit={hit:.3f}  t={t:6.2f}  boot_t={bt:6.2f}")
    
    # Non-fix
    nonfix_df = df[df['london_fix'] == 0]
    ret = nonfix_df['ret_bp'].dropna()
    mean_bp = ret.mean()
    hit = (ret > 0).mean()
    t, bt = block_bootstrap_tstat(ret)
    print(f"Non-fix:     n={len(ret):5d}  mean={mean_bp:7.2f}bp  hit={hit:.3f}  t={t:6.2f}  boot_t={bt:6.2f}")
    
    # PASS CRITERIA CHECK
    print("\n=== PASS CRITERIA CHECK ===")
    print("Asia-positive / US-flat pattern BEFORE 2024?")
    print("(Note: Our clean data starts 2022. Pre-2024 = 2022-2023 only)")
    
    pre2024 = df[df.index.year < 2024]
    for sess in ['Asia', 'Europe', 'US']:
        sess_df = pre2024[pre2024['session'] == sess]
        ret = sess_df['ret_bp'].dropna()
        if len(ret) > 0:
            mean_bp = ret.mean()
            t, _ = block_bootstrap_tstat(ret)
            sign = '+' if mean_bp > 0 else '-'
            print(f"  {sess:6s}: mean={mean_bp:7.2f}bp  t={t:6.2f}  sign={sign}")
    
    # Bonferroni: 3 sessions tested, alpha=0.05/3=0.0167, t>2.4 approx
    print("\nBonferroni-corrected threshold (3 sessions): t > ~2.4")
    
    # Save results
    sess_summary = pd.DataFrame(session_results)
    sess_summary.to_csv(RESULTS_DIR / "stage1_session_summary.csv", index=False)
    yr_results.to_csv(RESULTS_DIR / "stage1_by_year.csv", index=False)
    
    print("\n" + "=" * 60)
    print("STAGE 1 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()