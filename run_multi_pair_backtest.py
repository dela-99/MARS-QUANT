#!/usr/bin/env python3
"""
Multi-Pair Backtest Runner for M.A.R.S. Trading System.

Runs the Donchian + MTF-gated strategy through backtest for
EURUSD, USDJPY, EURGBP using newly ingested M5 data.
Reports: Sharpe, max drawdown, win rate, profit factor per pair.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional

from mars.apps.trading.signals.trend_breakout import DonchianBreakoutSignal
from mars.apps.trading.system.vol_scaled_system import (
    VolScaledSizer, SizingConfig, RiskManager, TradeExecutor, TradeConfig
)
from mars.apps.trading.signals.mtf_gate import MTFGate
from mars.libs.evaluation.metrics import classification_metrics


# Symbol configurations
SYMBOL_CONFIGS = {
    'EURUSD': {
        'symbol': 'EURUSDm',
        'data_path': 'data/processed/eurusd/m5/v1.0.0/data.parquet',
        'pip_size': 0.0001,
        'contract_size': 100000,  # 1 lot = 100,000 units
    },
    'USDJPY': {
        'symbol': 'USDJPYm',
        'data_path': 'data/processed/usdjpy/m5/v1.0.0/data.parquet',
        'pip_size': 0.01,
        'contract_size': 100000,
    },
    'EURGBP': {
        'symbol': 'EURGBPm',
        'data_path': 'data/processed/eurgbp/m5/v1.0.0/data.parquet',
        'pip_size': 0.0001,
        'contract_size': 100000,
    },
    'XAUUSD': {
        'symbol': 'XAUUSDm',
        'data_path': 'data/processed/xauusd/m5/v1.0.0/data.parquet',
        'pip_size': 0.01,
        'contract_size': 100,
    },
}


def load_symbol_data(symbol: str, start: str = "2020-01-01") -> pd.DataFrame:
    """Load and prepare OHLCV data for a symbol."""
    config = SYMBOL_CONFIGS[symbol]
    df = pd.read_parquet(config['data_path'])
    
    # Handle timestamp column - it should be a datetime column
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()
    elif isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()
    else:
        raise ValueError(f"No timestamp column or datetime index found")
    
    # Filter by start date
    start_ts = pd.Timestamp(start, tz="UTC")
    df = df[df.index >= start_ts]
    
    # Ensure OHLC columns
    required_cols = ["open", "high", "low", "close"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    
    # Ensure volume column exists
    if "volume" not in df.columns:
        df["volume"] = 0.0
    
    return df[["open", "high", "low", "close", "volume"]]


def compute_equity_floor(symbol: str, risk_pct: float = 0.03, stop_mult: float = 2.0) -> float:
    """
    Compute equity floor for a symbol.
    
    floor = (min_lot × contract_size × stop_distance_in_price) / risk_pct
    stop_distance = ATR × stop_mult (using typical ATR for the pair)
    """
    config = SYMBOL_CONFIGS[symbol]
    min_lot = 0.01
    contract_size = config['contract_size']
    
    # Typical ATR values for M5 (approximate)
    typical_atr = {
        'EURUSD': 0.00045,   # ~4.5 pips
        'USDJPY': 0.045,     # ~4.5 pips  
        'EURGBP': 0.00040,   # ~4.0 pips
        'XAUUSD': 0.55,      # ~55 pips (0.55 points)
    }
    
    atr = typical_atr.get(symbol, 0.0005)
    stop_distance = atr * 2.0  # 2.0x ATR stop
    
    # Risk in currency per min lot at this stop distance
    risk_per_min_lot = min_lot * contract_size * (stop_distance / config['pip_size']) * config['pip_size']
    # Actually: risk = min_lot * contract_size * stop_distance (in price units)
    risk_per_min_lot = min_lot * contract_size * stop_distance
    
    # Equity needed so this risk equals risk_pct of equity
    equity_floor = risk_per_min_lot / risk_pct
    
    return equity_floor


def run_backtest_for_symbol(
    symbol: str,
    start: str = "2020-01-01",
    end: str = "2024-12-31",
    equity: float = 10000.0,
) -> Dict[str, Any]:
    """Run full backtest for a single symbol."""
    
    print(f"\n{'='*60}")
    print(f"BACKTEST: {symbol} M5")
    print(f"{'='*60}")
    
    config = SYMBOL_CONFIGS[symbol]
    
    # Load data
    print(f"Loading {symbol} M5 data...")
    df = load_symbol_data(symbol, start="2020-01-01")
    df = df[df.index <= pd.Timestamp(end, tz="UTC")]
    print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    # Create signal generator
    signal_generator = DonchianBreakoutSignal(
        window=20,
        exit_window=10,
        session_filter=None
    )
    
    # Create sizer
    sizing_config = SizingConfig(
        target_vol=0.15,
        max_leverage=3.0,
        min_leverage=0.01,
        kelly_fraction=0.5,
        max_position_pct=1.0,  # Allow full leverage range
    )
    sizer = VolScaledSizer(sizing_config, garch_variant='garch')
    
    # Fit sizer
    print("Fitting CARR vol model...")
    sizer.fit(df)
    
    # Generate signals
    print("Generating Donchian breakout signals...")
    signals_df = signal_generator.generate(df)
    signal_dist = signals_df['signal'].value_counts().to_dict()
    print(f"Signal distribution: {signal_dist}")
    
    # Get vol forecasts
    print("Generating vol forecasts...")
    forecast_vol = sizer.forecast_vol(df)
    
    # Compute position sizes
    print("Computing position sizes...")
    contract_mult = config['contract_size']  # Use contract_size from config
    positions_df = sizer.compute_position_size(
        df, signals_df['signal'], equity, forecast_vol, contract_multiplier=contract_mult
    )
    
    # Apply min lot floor
    min_lot = 0.01
    positions_df['position_size'] = positions_df['position_size'].clip(lower=min_lot)
    
    # Run simulation with RiskManager
    config = {
        'symbol': SYMBOL_CONFIGS[symbol]['symbol'],
        'pip_size': SYMBOL_CONFIGS[symbol]['pip_size'],
        'contract_size': SYMBOL_CONFIGS[symbol]['contract_size'],
    }
    
    results = run_simulation(
        df, signals_df, positions_df, equity, config,
        atr_window=14, stop_mult=2.0, reward_mult=2.5
    )
    
    return results


def run_simulation(
    df: pd.DataFrame,
    signals_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    equity: float,
    config: Dict,
    atr_window: int = 14,
    stop_mult: float = 2.0,
    reward_mult: float = 2.5,
) -> Dict[str, Any]:
    """Run the trading simulation."""
    from mars.libs.features.volatility.range import ATRFeature
    
    # Add ATR to dataframe
    atr_feat = ATRFeature(window=14)
    atr_result = atr_feat.compute(df)
    df = df.copy()
    df['ATRr_14'] = atr_result.data['atr']
    
    # Align all data
    common_idx = df.index.intersection(signals_df.index).intersection(positions_df.index)
    df = df.loc[common_idx]
    signals = signals_df.loc[common_idx]
    positions = positions_df.loc[common_idx]
    
    # Risk manager
    risk_manager = RiskManager(kill_switch_file=None)
    risk_manager.current_equity = equity
    risk_manager.peak_equity = equity
    risk_manager.select_tier_for_equity(equity)
    
    executor = TradeExecutor(equity, risk_manager, None)
    
    equity_curve = [equity]
    trades = []
    open_positions = {}
    
    for i, (timestamp, row) in enumerate(df.iterrows()):
        signal = signals['signal'].loc[timestamp] if timestamp in signals.index else 0
        position_size = positions['position_size'].loc[timestamp] if timestamp in positions.index else 0
        price = row['close']
        time = timestamp
        
        # Check exits on open positions
        for symbol in list(open_positions.keys()):
            pos = open_positions[symbol]
            if pos['signal'] == 1:
                # Long position
                if price <= pos['stop_price']:
                    pnl = (pos['stop_price'] - pos['entry_price']) * pos['position_size'] * 100
                    trades.append({'time': time, 'pnl': pnl, 'reason': 'SL'})
                    open_positions.pop(symbol, None)
                elif price >= pos['take_profit']:
                    pnl = (pos['take_profit'] - pos['entry_price']) * pos['position_size'] * 100
                    trades.append({'time': time, 'pnl': pnl, 'reason': 'TP'})
                    open_positions.pop(symbol, None)
            else:
                # Short position
                if price >= pos['stop_price']:
                    pnl = (pos['entry_price'] - pos['stop_price']) * pos['position_size'] * 100
                    trades.append({'time': time, 'pnl': pnl, 'reason': 'SL'})
                    open_positions.pop(symbol, None)
                elif price <= pos['take_profit']:
                    pnl = (pos['entry_price'] - pos['take_profit']) * pos['position_size'] * 100
                    trades.append({'time': time, 'pnl': pnl, 'reason': 'TP'})
                    open_positions.pop(symbol, None)
        
        # Enter new position
        prev_signal = signals['signal'].iloc[i-1] if i > 0 else 0
        if signal != 0 and signal != prev_signal and 'XAUUSD' not in open_positions and position_size > 0:
            atr = row.get('ATRr_14', 0.5)
            stop_distance = atr * 2.0
            
            if signal == 1:
                stop_price = price - stop_distance
                take_profit = price + stop_distance * 2.5
            else:
                stop_price = price + stop_distance
                take_profit = price - stop_distance * 2.5
            
            from mars.apps.trading.system.vol_scaled_system import TradeConfig
            config = TradeConfig(
                symbol='XAUUSD',
                signal=signal,
                entry_price=price,
                stop_price=stop_price,
                take_profit=take_profit,
                position_size=position_size,
                max_hold_hours=24,
                risk_pct=0.01,
                entry_time=time,
            )
            
            # Check risk
            can_open, _ = risk_manager.can_open_position(
                'XAUUSD', position_size * price, equity
            )
            if can_open:
                risk_manager.register_position_risk(
                    'XAUUSD', 
                    position_size * abs(price - stop_price) * 100
                )
                open_positions['XAUUSD'] = {
                    'entry_price': price,
                    'stop_price': stop_price,
                    'take_profit': take_profit,
                    'position_size': position_size,
                    'signal': signal,
                }
        
        equity_curve.append(equity + sum(t['pnl'] for t in trades))
    
    # Compute metrics
    trades_df = pd.DataFrame(trades)
    equity_series = pd.Series(equity_curve)
    
    if len(trades_df) == 0:
        return {'error': 'No trades executed'}
    
    total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
    
    # Sharpe
    returns = equity_series.pct_change().dropna()
    sharpe = returns.mean() / returns.std() * np.sqrt(252 * 288) if returns.std() > 0 else 0  # M5 bars
    
    # Max drawdown
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak
    max_dd = drawdown.min()
    
    # Win rate
    wins = (trades_df['pnl'] > 0).sum()
    losses = (trades_df['pnl'] < 0).sum()
    win_rate = wins / len(trades_df) if len(trades_df) > 0 else 0
    
    # Profit factor
    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Avg trade
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losses > 0 else 0
    
    return {
        'symbol': 'XAUUSD',  # placeholder
        'total_trades': len(trades_df),
        'total_return': total_return,
        'sharpe': sharpe,
        'max_drawdown': max_dd,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'equity_curve': equity_curve,
        'trades': trades,
    }


def format_results(results: Dict[str, Any], symbol: str) -> str:
    """Format backtest results for display."""
    if 'error' in results:
        return f"{symbol}: ERROR - {results['error']}"
    
    return f"""
{symbol} M5 BACKTEST RESULTS
{'='*50}
Total Trades:     {results['total_trades']}
Total Return:     {results['total_return']:.2%}
Sharpe Ratio:     {results['sharpe']:.2f}
Max Drawdown:     {results['max_drawdown']:.2%}
Win Rate:         {results['win_rate']:.2%}
Profit Factor:    {results['profit_factor']:.2f}
Avg Win:          ${results['avg_win']:.2f}
Avg Loss:         ${results['avg_loss']:.2f}
Gross Profit:     ${results['gross_profit']:.2f}
Gross Loss:       ${results['gross_loss']:.2f}
"""


def main():
    print("M.A.R.S. Multi-Pair Backtest")
    print("=" * 60)
    
    symbols = ['EURUSD', 'USDJPY', 'EURGBP', 'XAUUSD']
    all_results = {}
    
    for symbol in symbols:
        try:
            results = run_backtest_for_symbol(symbol, start="2022-01-01", end="2024-12-31", equity=10000.0)
            results['symbol'] = symbol
            all_results[symbol] = results
            print(format_results(results, symbol))
        except Exception as e:
            print(f"\n{symbol}: ERROR - {e}")
            import traceback
            traceback.print_exc()
            all_results[symbol] = {'error': str(e)}
    
    # Summary comparison
    print("\n" + "="*60)
    print("SUMMARY COMPARISON")
    print("="*60)
    print(f"{'Symbol':<10} {'Trades':>8} {'Return':>10} {'Sharpe':>8} {'MaxDD':>8} {'Win%':>8} {'PF':>8}")
    print("-"*60)
    for symbol, results in all_results.items():
        if 'error' not in results:
            print(f"{symbol:<10} {results['total_trades']:>8} {results['total_return']:>9.2%} {results['sharpe']:>8.2f} {results['max_drawdown']:>7.2%} {results['win_rate']:>7.2%} {results['profit_factor']:>8.2f}")
        else:
            print(f"{symbol:<10} {'ERROR':>8}")
    
    # Equity floors
    print("\n" + "="*60)
    print("EQUITY FLOORS (3% risk, 2.0x ATR stop, min_lot=0.01)")
    print("="*60)
    for symbol in ['EURUSD', 'USDJPY', 'EURGBP', 'XAUUSD']:
        floor = compute_equity_floor(symbol)
        print(f"{symbol}: ${floor:.2f}")
    
    return all_results


if __name__ == "__main__":
    main()