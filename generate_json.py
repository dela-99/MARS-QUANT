#!/usr/bin/env python
"""Generate JSON summary from CSV trade files."""

from pathlib import Path
import pandas as pd
import json


def main():
    output_dir = Path('C:/Users/RIDGE/MARS-QUANT/research_output/m5_strategy_research_20261124')

    strategies = ['momentum', 'pullback', 'vol_expansion', 'failed_breakout', 'displacement_mr']
    periods = ['dev', 'val', 'holdout']

    all_results = {}

    for strategy_name in strategies:
        strategy_results = {}
        for period in periods:
            ledger_path = output_dir / f'{strategy_name}_{period}_trades.csv'
            if ledger_path.exists() and ledger_path.stat().st_size > 10:
                df = pd.read_csv(ledger_path)
                if len(df) > 0:
                    net = df['net_pnl'].to_numpy(dtype=float)
                    wins = net[net > 0]
                    losses = net[net <= 0]
                    win_rate = float(len(wins) / len(net))
                    gross_win = float(wins.sum()) if len(wins) else 0.0
                    gross_loss = float(-losses.sum()) if len(losses) else 0.0
                    expectancy = float(net.mean())
                    avg_win = float(wins.mean()) if len(wins) else 0.0
                    avg_loss = float(losses.mean()) if len(losses) else 0.0
                    profit_factor = gross_win / gross_loss if gross_loss > 0 else (float('inf') if gross_win > 0 else 0.0)
                    gross_pnl_total = float(df['gross_pnl'].sum())
                    net_pnl_total = float(net.sum())
                    total_commission = float(df['commission'].sum()) if 'commission' in df.columns else 0.0
                    total_swap = float(df['swap'].sum()) if 'swap' in df.columns else 0.0
                    total_slippage = float(df['slippage'].sum()) if 'slippage' in df.columns else 0.0
                    total_spread = float(df['spread_cost'].sum()) if 'spread_cost' in df.columns else 0.0
                    
                    # Build equity curve
                    starting_equity = 1000.0
                    equity = starting_equity + df['net_pnl'].cumsum()
                    running_max = equity.cummax()
                    dd = equity - running_max
                    max_dd = float(dd.min()) if len(dd) else 0.0
                    max_dd_pct = max_dd / float(equity[running_max.idxmax()]) if len(equity) and running_max.max() != 0 else 0.0
                    
                    # Daily returns for Sharpe
                    if 'entry_time' in df.columns:
                        df['entry_time'] = pd.to_datetime(df['entry_time'])
                        df = df.sort_values('entry_time')
                        equity.index = df['entry_time']
                    daily = equity.resample('1D').last().ffill() if len(equity) > 1 else pd.Series([starting_equity])
                    rets = daily.pct_change().dropna()
                    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
                    
                    holding = df['holding_minutes'].to_numpy(dtype=float) if 'holding_minutes' in df.columns else np.array([])
                else:
                    win_rate = expectancy = avg_win = avg_loss = profit_factor = 0.0
                    gross_pnl_total = net_pnl_total = 0.0
                    total_commission = total_swap = total_slippage = total_spread = 0.0
                    max_dd = max_dd_pct = sharpe = 0.0
                    holding = np.array([])
                    equity = pd.Series([1000.0])

                strategy_results[period] = {
                    'metrics': {
                        'trade_count': int(len(df)),
                        'win_rate': win_rate,
                        'avg_win_usd': avg_win,
                        'avg_loss_usd': avg_loss,
                        'expectancy_usd': expectancy,
                        'expectancy_r': 0.0,
                        'profit_factor': profit_factor,
                        'gross_pnl_usd': gross_pnl_total,
                        'net_pnl_usd': net_pnl_total,
                        'net_return': net_pnl_total / 1000.0,
                        'max_drawdown_usd': max_dd,
                        'max_drawdown_pct': max_dd_pct,
                        'sharpe': sharpe,
                        'avg_holding_minutes': float(holding.mean()) if len(holding) else 0.0,
                        'median_holding_minutes': float(np.median(holding)) if len(holding) else 0.0,
                        'total_commission_usd': total_commission,
                        'total_swap_usd': total_swap,
                        'total_slippage_usd': total_slippage,
                        'total_spread_cost_usd': total_spread,
                        'cost_breakdown': {
                            'spread': total_spread,
                            'commission': total_commission,
                            'swap': total_swap,
                            'slippage': total_slippage,
                            'total': total_spread + total_commission + total_swap + total_slippage,
                        },
                    },
                    'trades': df.to_dict(orient='records') if len(df) else [],
                    'equity_curve': {str(k): v for k, v in equity.to_dict().items()} if len(equity) else {},
                    'execution_mode': 'M1',
                    'feasibility': {'feasible': False, 'min_equity_required_usd': 1000},
                    'rejected_signals': 0,
                    'exit_breakdown': {
                        'time_exits': 0,
                        'stop_exits': 0,
                        'mid_exits': 0,
                        'end_of_data_exits': 0,
                    },
                }
            else:
                # Empty period
                strategy_results[period] = {
                    'metrics': {
                        'trade_count': 0,
                        'win_rate': 0.0,
                        'avg_win_usd': 0.0,
                        'avg_loss_usd': 0.0,
                        'expectancy_usd': 0.0,
                        'expectancy_r': 0.0,
                        'profit_factor': 0.0,
                        'gross_pnl_usd': 0.0,
                        'net_pnl_usd': 0.0,
                        'net_return': 0.0,
                        'max_drawdown_usd': 0.0,
                        'max_drawdown_pct': 0.0,
                        'sharpe': 0.0,
                        'avg_holding_minutes': 0.0,
                        'median_holding_minutes': 0.0,
                        'total_commission_usd': 0.0,
                        'total_swap_usd': 0.0,
                        'total_slippage_usd': 0.0,
                        'total_spread_cost_usd': 0.0,
                        'cost_breakdown': {
                            'spread': 0.0,
                            'commission': 0.0,
                            'swap': 0.0,
                            'slippage': 0.0,
                            'total': 0.0,
                        },
                    },
                    'trades': [],
                    'equity_curve': {},
                    'execution_mode': 'M1',
                    'feasibility': {'feasible': False, 'min_equity_required_usd': 1000},
                    'rejected_signals': 0,
                    'exit_breakdown': {
                        'time_exits': 0,
                        'stop_exits': 0,
                        'mid_exits': 0,
                        'end_of_data_exits': 0,
                    },
                }
        all_results[strategy_name] = strategy_results

    with open(output_dir / 'm5_strategy_research_results.json', 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    print('JSON summary generated!')


if __name__ == '__main__':
    import numpy as np
    main()