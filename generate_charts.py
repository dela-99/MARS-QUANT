#!/usr/bin/env python
"""Generate equity curves and drawdown charts from CSV trade files."""

from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    output_dir = Path('C:/Users/RIDGE/MARS-QUANT/research_output/m5_strategy_research_20261124')

    strategies = ['momentum', 'pullback', 'vol_expansion', 'failed_breakout', 'displacement_mr']
    periods = ['dev', 'val', 'holdout']

    for strategy_name in strategies:
        fig, axes = plt.subplots(3, 2, figsize=(14, 10))
        fig.suptitle(f'{strategy_name.upper()} -- Equity Curves & Drawdowns')
        print(f'Generating charts for {strategy_name}...')

        for idx, period in enumerate(periods):
            ledger_path = output_dir / f'{strategy_name}_{period}_trades.csv'
            
            if not ledger_path.exists() or ledger_path.stat().st_size <= 10:
                # Empty strategy/period - create empty charts
                ax = axes[idx, 0]
                ax.text(0.5, 0.5, 'No trades', ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f'{period.capitalize()} Equity Curve')
                ax.set_ylabel('Equity ($)')
                ax.grid(True, alpha=0.3)
                
                ax = axes[idx, 1]
                ax.text(0.5, 0.5, 'No trades', ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f'{period.capitalize()} Drawdown %')
                ax.set_ylabel('Drawdown (%)')
                ax.grid(True, alpha=0.3)
                continue

            df = pd.read_csv(ledger_path)
            
            if len(df) == 0:
                ax = axes[idx, 0]
                ax.text(0.5, 0.5, 'No trades', ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f'{period.capitalize()} Equity Curve')
                ax.set_ylabel('Equity ($)')
                ax.grid(True, alpha=0.3)
                
                ax = axes[idx, 1]
                ax.text(0.5, 0.5, 'No trades', ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f'{period.capitalize()} Drawdown %')
                ax.set_ylabel('Drawdown (%)')
                ax.grid(True, alpha=0.3)
                continue

            # Build equity curve from trade P&L
            # Use entry_time if available, otherwise use index
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'])
                df = df.sort_values('entry_time')
            elif 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp')
            
            # Cumulative equity starting from 1000
            starting_equity = 1000.0
            equity = starting_equity + df['net_pnl'].cumsum()
            
            # Equity curve
            ax = axes[idx, 0]
            equity.plot(ax=ax, color='blue', linewidth=0.8)
            ax.set_title(f'{period.capitalize()} Equity Curve')
            ax.set_ylabel('Equity ($)')
            ax.grid(True, alpha=0.3)
            
            # Drawdown
            ax = axes[idx, 1]
            running_max = equity.cummax()
            dd = (equity - running_max) / running_max * 100
            dd.plot(ax=ax, color='red', linewidth=0.8)
            ax.fill_between(range(len(dd)), dd, 0, color='red', alpha=0.1)
            ax.set_title(f'{period.capitalize()} Drawdown %')
            ax.set_ylabel('Drawdown (%)')
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_dir / f'{strategy_name}_equity_drawdown.png', dpi=150)
        plt.close()

    print('All charts generated!')


if __name__ == '__main__':
    main()