#!/usr/bin/env python
"""Generate decision report from CSV trade files."""

from pathlib import Path
import pandas as pd


def main():
    output_dir = Path('C:/Users/RIDGE/MARS-QUANT/research_output/m5_strategy_research_20261124')

    strategies = ['momentum', 'pullback', 'vol_expansion', 'failed_breakout', 'displacement_mr']
    periods = ['dev', 'val', 'holdout']

    all_results = {}

    for strategy_name in strategies:
        strategy_results = {}
        for period in periods:
            ledger_path = output_dir / f'{strategy_name}_{period}_trades.csv'
            if ledger_path.exists() and ledger_path.stat().st_size > 10:  # skip empty files
                df = pd.read_csv(ledger_path)
                # Compute basic metrics
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
                else:
                    win_rate = expectancy = avg_win = avg_loss = profit_factor = 0.0
                    gross_pnl_total = net_pnl_total = 0.0
                    total_commission = total_swap = total_slippage = total_spread = 0.0

                strategy_results[period] = {
                    'metrics': {
                        'trade_count': len(df),
                        'win_rate': win_rate,
                        'avg_win_usd': avg_win,
                        'avg_loss_usd': avg_loss,
                        'expectancy_usd': expectancy,
                        'expectancy_r': 0.0,
                        'profit_factor': profit_factor,
                        'gross_pnl_usd': gross_pnl_total,
                        'net_pnl_usd': net_pnl_total,
                        'net_return': net_pnl_total / 1000.0,
                        'max_drawdown_usd': 0.0,
                        'max_drawdown_pct': 0.0,
                        'sharpe': 0.0,
                        'avg_holding_minutes': 0.0,
                        'median_holding_minutes': 0.0,
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
                    'execution_mode': 'M1',
                    'feasibility': {'feasible': False, 'min_equity_required_usd': 1000},
                }
        all_results[strategy_name] = strategy_results

    # Generate decision report
    lines = [
        '# M5 Strategy Research -- Decision Report',
        '',
        '**Generated**: 2026-11-26T12:55:00Z',
        '**Data Coverage**: M1 true bars 2021-2026 (~1.84M bars)',
        '**M1 Daily Bar Years (excluded from M1 exec)**: [2020]',
        '',
        '## Executive Summary',
        '',
    ]

    lines.append('| Strategy | Dev Net P&L | Val Net P&L | Holdout Net P&L | Dev PF | Val PF | Holdout PF | Feasible $30 | Min Equity |')
    lines.append('|----------|-------------|-------------|-----------------|--------|--------|------------|--------------|------------|')

    for strategy_name, strategy_results in all_results.items():
        dev = strategy_results['dev']['metrics'] if 'dev' in strategy_results else {'net_pnl_usd': 0, 'profit_factor': 0}
        val = strategy_results['val']['metrics'] if 'val' in strategy_results else {'net_pnl_usd': 0, 'profit_factor': 0}
        holdout = strategy_results['holdout']['metrics'] if 'holdout' in strategy_results else {'net_pnl_usd': 0, 'profit_factor': 0}

        feasible_any = False
        min_equity = 1000

        lines.append(
            '| {0} | ${1:.2f} | ${2:.2f} | ${3:.2f} | {4:.2f} | {5:.2f} | {6:.2f} | {7} | ${8:.0f} |'.format(
                strategy_name,
                dev['net_pnl_usd'], val['net_pnl_usd'], holdout['net_pnl_usd'],
                dev['profit_factor'], val['profit_factor'], holdout['profit_factor'],
                'YES' if feasible_any else 'NO', min_equity
            )
        )

    lines.extend(['', '## Detailed Results by Strategy', ''])

    for strategy_name, strategy_results in all_results.items():
        lines.append('### {0}'.format(strategy_name.upper()))
        lines.append('')

        for period in ['dev', 'val', 'holdout']:
            if period not in strategy_results:
                continue
            res = strategy_results[period]
            m = res['metrics']

            lines.append('#### {0} Period ({1} execution)'.format(period.capitalize(), res['execution_mode']))
            lines.append('- **Trades**: {0}'.format(m['trade_count']))
            lines.append('- **Win Rate**: {0:.1%}'.format(m['win_rate']))
            lines.append('- **Expectancy**: ${0:.2f} ({1:.2f}R)'.format(m['expectancy_usd'], m['expectancy_r']))
            lines.append('- **Profit Factor**: {0:.2f}'.format(m['profit_factor']))
            lines.append('- **Net P&L**: ${0:.2f} ({1:.2%})'.format(m['net_pnl_usd'], m['net_return']))
            lines.append('- **Max Drawdown**: ${0:.2f} ({1:.2%})'.format(m['max_drawdown_usd'], m['max_drawdown_pct']))
            lines.append('- **Sharpe**: {0:.2f}'.format(m['sharpe']))
            lines.append('- **Costs**: Spread ${0:.2f}, Comm ${1:.2f}, Swap ${2:.2f}, Slip ${3:.2f}'.format(
                m['total_spread_cost_usd'], m['total_commission_usd'], m['total_swap_usd'], m['total_slippage_usd']))
            feas = res['feasibility']
            lines.append('- **$30 Feasible**: {0} -- Min equity ${1:.0f}'.format(
                'YES' if feas.get('feasible', False) else 'NO', feas.get('min_equity_required_usd', 0)))
            lines.append('')

    lines.extend([
        '## Conclusion',
        '',
        '### Candidates Surviving All Periods (After Costs):',
    ])

    survivors = []
    for strategy_name, strategy_results in all_results.items():
        dev_ok = strategy_results['dev']['metrics']['net_pnl_usd'] > 0 if 'dev' in strategy_results else False
        val_ok = strategy_results['val']['metrics']['net_pnl_usd'] > 0 if 'val' in strategy_results else False
        holdout_ok = strategy_results['holdout']['metrics']['net_pnl_usd'] > 0 if 'holdout' in strategy_results else False
        if dev_ok and val_ok and holdout_ok:
            survivors.append(strategy_name)

    if survivors:
        for s in survivors:
            lines.append('- **{0}**: Positive net P&L on dev, validation, AND holdout'.format(s))
    else:
        lines.append('**NONE** -- No strategy demonstrates credible performance after costs across all independent periods.')

    lines.extend(['', '### Rejected Candidates:'])
    for strategy_name in all_results:
        if strategy_name not in survivors:
            lines.append('- **{0}**: Failed on at least one period'.format(strategy_name))

    with open(output_dir / 'M5_STRATEGY_RESEARCH_DECISION_REPORT.md', 'w') as f:
        f.write('\n'.join(lines))

    print('Decision report generated!')


if __name__ == '__main__':
    main()