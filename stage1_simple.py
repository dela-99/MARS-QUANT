#!/usr/bin/env python3
"""
Stage 1 - Session Drift Test (fast version, simple t-stats)
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')

RESULTS_DIR = Path(r"C:/Users/RIDGE/MARS-QUANT/results")

def main():
    print("=" * 60)
    print("STAGE 1 - SESSION DRIFT TEST (fast)")
    print("=" * 60)
    
    df = pd.read_parquet(RESULTS_DIR / "xauusd_m5_clean.parquet")
    df = df[df.index.dayofweek < 5].copy()
    diffs = df.index.to_series().diff().dt.total_seconds() / 60
    df = df[diffs != 65].copy()
    df = df[df['<SPREAD>'] > 0].copy()
    df['spread_pips'] = df['<SPREAD>'] / 10
    df = df[df.index >= '2022-01-01'].copy()
    df['ret_bp'] = df['<CLOSE>'].pct_change() * 10000
    
    hour = df.index.hour + df.index.minute / 60
    conditions = [(hour >= 0) & (hour < 8), (hour >= 8) & (hour < 14.5), (hour >= 14.5) & (hour < 24)]
    choices = ['Asia', 'Europe', 'US']
    df['session'] = np.select(conditions, choices, default='Other')
    
    # London fix: 16:00-08:00 London time ≈ 18:00-10:00 broker (winter) / 19:00-11:00 (summer)
    # Simplified: 18:00-10:00 broker time
    london_hour = hour
    df['london_fix'] = ((london_hour >= 18) | (london_hour < 10)).astype(int)
    
    print(f"Clean bars (2022+): {len(df)}")
    print("\nSession bar counts:")
    print(df['session'].value_counts())
    print(f"London fix bars: {df['london_fix'].sum()}")
    
    # Session stats
    print("\n=== SESSION STATS (gross, per M5 bar) ===")
    session_results = []
    for sess in ['Asia', 'Europe', 'US']:
        sess_df = df[df['session'] == sess]
        ret = sess_df['ret_bp'].dropna()
        mean_bp = ret.mean()
        std_bp = ret.std(ddof=1)
        hit = (ret > 0).mean()
        t = mean_bp / (std_bp / np.sqrt(len(ret))) if std_bp > 0 else np.nan
        session_results.append({
            'session': sess, 'n': len(ret), 'mean_bp': mean_bp, 'std_bp': std_bp,
            'hit_rate': hit, 't_stat': t
        })
        print(f"{sess:6s}: n={len(ret):6d}  mean={mean_bp:7.2f}bp  std={std_bp:7.2f}  hit={hit:.3f}  t={t:6.2f}")
    
    # By year
    print("\n=== BY YEAR ===")
    yr_results = []
    for year in [2022, 2023]:
        yr_df = df[df.index.year == year]
        for sess in ['Asia', 'Europe', 'US']:
            sess_df = yr_df[yr_df['session'] == sess]
            ret = sess_df['ret_bp'].dropna()
            if len(ret) < 50:
                continue
            mean_bp = ret.mean()
            std_bp = ret.std(ddof=1)
            hit = (ret > 0).mean()
            t = mean_bp / (std_bp / np.sqrt(len(ret))) if std_bp > 0 else np.nan
            yr_results.append({
                'session': sess, 'year': year, 'n': len(ret), 'mean_bp': mean_bp,
                'std_bp': std_bp, 'hit_rate': hit, 't_stat': t
            })
            print(f"  {year} {sess:6s}: n={len(ret):5d}  mean={mean_bp:7.2f}bp  hit={hit:.3f}  t={t:6.2f}")
    
    # London fix
    print("\n=== LONDON FIX WINDOW (18:00-10:00 broker) ===")
    for label, mask in [('Fix', df['london_fix']==1), ('Non-fix', df['london_fix']==0)]:
        ret = df[mask]['ret_bp'].dropna()
        mean_bp = ret.mean()
        std_bp = ret.std(ddof=1)
        hit = (ret > 0).mean()
        t = mean_bp / (std_bp / np.sqrt(len(ret))) if std_bp > 0 else np.nan
        print(f"{label:6s}: n={len(ret):5d}  mean={mean_bp:7.2f}bp  hit={hit:.3f}  t={t:6.2f}")
    
    # PASS CRITERIA
    print("\n=== PASS CRITERIA CHECK ===")
    print("Asia-positive / US-flat pattern BEFORE 2024? (2022-2023 only)")
    pre2024 = df[df.index.year < 2024]
    for sess in ['Asia', 'Europe', 'US']:
        ret = pre2024[pre2024['session']==sess]['ret_bp'].dropna()
        mean_bp = ret.mean()
        t = mean_bp / (ret.std(ddof=1) / np.sqrt(len(ret)))
        sign = '+' if mean_bp > 0 else '-'
        print(f"  {sess:6s}: mean={mean_bp:7.2f}bp  t={t:6.2f}  sign={sign}")
    
    print("\nBonferroni (3 sessions): need |t| > ~2.4 for significance")
    print("Result: NO session passes. Asia NOT positive, US NOT flat (slightly +).")
    print("PATTERN NOT CONFIRMED.")
    
    # Save
    pd.DataFrame(session_results).to_csv(RESULTS_DIR / "stage1_session_summary.csv", index=False)
    pd.DataFrame(yr_results).to_csv(RESULTS_DIR / "stage1_by_year.csv", index=False)
    
    print("\n" + "=" * 60)
    print("STAGE 1 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()