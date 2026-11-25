import sys
sys.path.insert(0, '.')
from mars.apps.research_lab.ma_tsm_monte_carlo import (
    MonteCarloConfig, load_oos_trades, run_reshuffling_mc, run_resampling_mc, run_block_bootstrap_mc, 
    simulate_equity_path_from_returns
)
import numpy as np

pnl, returns, details = load_oos_trades('reports/walkforward/oos_trades_for_mc.json')
config = MonteCarloConfig(n_simulations=10000, seed=42)

hist_equity, hist_term_ret, hist_max_dd, hist_max_streak = simulate_equity_path_from_returns(
    returns, config.initial_capital
)

reshuffle = run_reshuffling_mc(returns, config, hist_term_ret, hist_max_dd, hist_max_streak)
resample = run_resampling_mc(returns, config, hist_term_ret, hist_max_dd, hist_max_streak)
block = run_block_bootstrap_mc(returns, config, hist_term_ret, hist_max_dd, hist_max_streak)

# Check full data ranges for fan chart y-axis
print('=== FULL DATA RANGES ===')
for res, name in [(reshuffle, 'Reshuffle'), (resample, 'Resample'), (block, 'Block')]:
    paths = res.sample_paths
    y_min = paths.min()
    y_max = paths.max()
    print(f'{name}: min=${y_min:,.0f}, max=${y_max:,.0f}')
    print(f'  Ratio max/min: {y_max/y_min:.1f}x')
    hist_eq = res.initial_capital * (1 + res.historical_terminal_return)
    print(f'  Historical terminal equity: ${hist_eq:,.0f}')
    print(f'  Historical as fraction of range: {(hist_eq - y_min) / (y_max - y_min):.2%}')

print('\n=== HISTORICAL VS SIMULATED - BOX PLOT DATA ===')
for res, name in [(reshuffle, 'Reshuffle'), (resample, 'Resample'), (block, 'Block')]:
    # Terminal returns in %
    term_returns_pct = res.terminal_returns * 100
    hist_term_pct = res.historical_terminal_return * 100
    print(f'\n{name} Terminal Returns (%):')
    print(f'  Simulated: min={term_returns_pct.min():.2f}%, max={term_returns_pct.max():.2f}%, median={np.median(term_returns_pct):.2f}%')
    print(f'  Historical: {hist_term_pct:.2f}%')
    print(f'  Historical percentile rank: {np.mean(term_returns_pct <= hist_term_pct)*100:.1f}th percentile')
    
    # Max DD in %
    dd_pct = res.max_drawdown_pcts * 100
    hist_dd_pct = res.historical_max_dd * 100
    print(f'  Max DD (%): min={dd_pct.min():.2f}%, max={dd_pct.max():.2f}%, median={np.median(dd_pct):.2f}%')
    print(f'  Historical DD: {hist_dd_pct:.2f}%')
    print(f'  Historical DD percentile rank: {np.mean(dd_pct <= hist_dd_pct)*100:.1f}th percentile')
    
    # Terminal equity
    hist_eq = res.initial_capital * (1 + res.historical_terminal_return)
    print(f'  Terminal Equity: min=${res.terminal_equities.min():,.0f}, max=${res.terminal_equities.max():,.0f}, median=${np.median(res.terminal_equities):,.0f}')
    print(f'  Historical Equity: ${hist_eq:,.0f}')
    print(f'  Historical equity percentile rank: {np.mean(res.terminal_equities <= hist_eq)*100:.1f}th percentile')
    
    # Max streak
    hist_streak = res.historical_max_streak
    print(f'  Max Streak: min={res.max_losing_streaks.min()}, max={res.max_losing_streaks.max()}, median={np.median(res.max_losing_streaks):.0f}')
    print(f'  Historical Streak: {hist_streak}')
    print(f'  Historical streak percentile rank: {np.mean(res.max_losing_streaks <= hist_streak)*100:.1f}th percentile')