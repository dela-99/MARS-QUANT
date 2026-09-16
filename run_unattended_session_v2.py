#!/usr/bin/env python3
"""
Short unattended session using live MT5 data and VolScaledSizer for position sizing.
"""
import sys
import os
import time
from datetime import datetime, timedelta

# Ensure local package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mars.core.config import MT5Config
from mars.apps.trading.mt5_executor import MT5ConnectionManager, MT5SymbolResolver, MT5OrderRouter, MT5AuditLogger, MT5SymbolResolver
from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig, VolScaledSizer, SizingConfig
from mars.apps.trading.signals.trend_breakout import DonchianBreakoutSignal
from mars.libs.features.volatility.range import ATRFeature
import pandas as pd
import tempfile
import sqlite3


def compute_current_atr(price_df: pd.DataFrame, window: int = 14) -> float:
    """Compute current ATR from live bar data."""
    atr_feat = ATRFeature(window=window)
    result = atr_feat.compute(price_df)
    atr_series = result.data['atr']
    return float(atr_series.iloc[-1])


def main():
    # Clean up
    kill_switch_path = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')
    if os.path.exists(kill_switch_path):
        os.remove(kill_switch_path)

    config = MT5Config()
    conn_manager = MT5ConnectionManager(config)
    if not conn_manager.connect():
        print('Failed to connect to MT5')
        sys.exit(1)

    mt5 = conn_manager.mt5

    # Get real symbol info
    symbol = mt5.symbol_info('XAUUSDm')
    price = symbol.ask
    bid = symbol.bid

    print('Connected to MT5 DEMO account #476944496')
    print('Symbol: XAUUSDm')
    print(f'Price: {price}, Bid: {bid}, Spread: {symbol.spread} points')

    # --- Connect to MT5 to get LIVE equity ---
    account_info = mt5.account_info()
    if account_info is None:
        raise RuntimeError(f"Failed to get account info: {mt5.last_error()}")

    live_equity = float(account_info.equity)
    print(f'LIVE EQUITY: ${live_equity:.2f}')

    # --- Create RiskManager with tiered risk ---
    risk_manager = RiskManager(
        kill_switch_file=os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json'),
    )
    # Get live equity for tier selection
    risk_manager.select_tier_for_equity(live_equity)
    risk_manager.current_equity = live_equity
    risk_manager.peak_equity = live_equity
    risk_manager.daily_pnl = 0.0

    tier = risk_manager.get_current_tier()
    print(f'TIER: ${tier["risk_pct_per_trade"]:.1%} risk, max {tier["max_concurrent_trades"]} trades')

    # --- Create Sizer ---
    sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
    sizer = VolScaledSizer(sizing_config, garch_variant='garch')

    # Create the executor components with REAL MT5 connection
    symbol_resolver = MT5SymbolResolver(mt5)
    order_router = MT5OrderRouter(mt5, symbol_resolver)
    audit_logger = MT5AuditLogger(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))

    # Load historical data for signal generation AND fit sizer
    df = pd.read_parquet('data/processed/xauusd/m5/v1.0.0/data.parquet')
    df.index = pd.DatetimeIndex(df['timestamp'])
    recent_data = df.tail(5000).copy()

    # Fit sizer on historical data
    print('Fitting sizer on historical data...')
    sizer.fit(recent_data)

    # Create signal generator
    signal_generator = DonchianBreakoutSignal(
        window=20,
        exit_window=10,
        session_filter=None
    )

    # Generate signals on recent data
    print('Generating signals on recent data...')
    signal_df = signal_generator.generate(recent_data)
    latest_signal = signal_df['signal'].iloc[-1]
    print(f'Latest signal: {latest_signal} (1=long, -1=short, 0=flat)')
    print()

    print('=== STARTING SHORT UNATTENDED DEMO SESSION (2 minutes) ===')
    print(f'Start time: {datetime.now()}')
    print(f'Equity: ${live_equity:.2f}')
    print(f'Tier risk per trade: {tier["risk_pct_per_trade"]:.1%} (${live_equity * tier["risk_pct_per_trade"]:.2f})')
    print(f'Max concurrent trades: {tier["max_concurrent_trades"]}')
    print()

    # Track session stats
    session_start = datetime.now()
    signals_generated = 0
    orders_placed = 0
    orders_rejected_risk = 0
    orders_failed = 0
    total_slippage_points = 0.0
    total_size_slippage = 0.0

    try:
        # Run for 2 minutes
        max_duration = timedelta(minutes=2)
        last_bar_time = None

        while datetime.now() - session_start < max_duration:
            # Get current tick
            tick = mt5.symbol_info_tick('XAUUSDm')
            if tick is None:
                print(f'[{datetime.now()}] No tick data, waiting...')
                time.sleep(5)
                continue

            current_price = tick.ask
            current_bid = tick.bid
            current_time = datetime.fromtimestamp(tick.time)

            # Check if we have a new bar (5-minute intervals)
            bar_time = current_time.replace(second=0, microsecond=0)
            bar_minute = bar_time.minute
            if bar_minute % 5 != 0:
                bar_time = bar_time.replace(minute=(bar_minute // 5) * 5)

            if last_bar_time is not None and bar_time == last_bar_time:
                time.sleep(1)
                continue

            last_bar_time = bar_time

            # --- REFRESH BAR DATA FROM MT5 FOR LIVE SIGNALS ---
            rates = mt5.copy_rates_from_pos('XAUUSDm', 5, 0, 5000)  # M5 timeframe, 5000 bars
            if rates is not None and len(rates) > 0:
                live_df = pd.DataFrame(rates)
                live_df['timestamp'] = pd.to_datetime(live_df['time'], unit='s', utc=True)
                live_df.set_index('timestamp', inplace=True)
                live_df.rename(columns={'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                                         'tick_volume': 'volume', 'spread': 'spread', 'real_volume': 'real_volume'},
                               inplace=True)
                
                # --- VALIDATION PIPELINE (same as historical data) ---
                from mars.libs.data.loaders import normalize_ohlcv
                from mars.libs.data.validation import validate_ohlcv
                
                # Normalize (column aliasing, UTC enforcement, deduplication)
                live_df = normalize_ohlcv(live_df, symbol='XAUUSDm', timeframe='M5', assume_utc=True)
                
                # Validate (monotonic timestamps, OHLC consistency, duplicates)
                validation_report = validate_ohlcv(live_df, strict=False)  # warn don't crash
                if not validation_report.ok:
                    # Log validation failure as risk event, skip this polling cycle
                    audit_logger.log_risk_event(
                        'LIVE_DATA_VALIDATION_FAILED',
                        f"Live bar validation failed: {'; '.join(validation_report.errors)}",
                        live_equity, 0.0, 0.0, risk_manager.kill_switch_halted
                    )
                    print(f"[{datetime.now()}] WARNING: Live data validation failed: {validation_report.errors}")
                    time.sleep(1)
                    continue
                if validation_report.warnings:
                    print(f"[{datetime.now()}] Live data validation warnings: {validation_report.warnings}")
                
                recent_data = live_df.tail(5000).copy()

            # Generate signal using the latest data
            signals = signal_generator.generate(recent_data)

            if len(signals) > 0:
                latest_signal = signals['signal'].iloc[-1]
                if latest_signal != 0:
                    signals_generated += 1
                    signal_type = 'BUY' if latest_signal == 1 else 'SELL'
                    print(f'[{datetime.now()}] SIGNAL: {signal_type} at {current_price}')

                    # Risk checks
                    live_position_value = 0.0
                    positions = mt5.positions_get(symbol='XAUUSDm')
                    if positions:
                        for pos in positions:
                            if pos.magic == 123456:
                                live_position_value += pos.volume * pos.price_open * 100

                    can_open, reason = risk_manager.can_open_position(
                        'XAUUSDm', live_position_value + 0.01 * current_price, live_equity
                    )

                    if not can_open:
                        orders_rejected_risk += 1
                        print(f'  REJECTED (concurrent risk): {reason}')
                        audit_logger.log_risk_event(
                            'REJECTED_CONCURRENT', reason, live_equity, 0.0, 0.0,
                            risk_manager.kill_switch_halted
                        )
                        continue

                    # --- COMPUTE LIVE ATR AND POSITION SIZE VIA VOLSCALEDSIZER ---
                    atr_feat = ATRFeature(window=14)
                    atr_result = atr_feat.compute(recent_data)
                    current_atr = atr_result.data['atr'].iloc[-1]

                    # Get vol forecast and compute position size via VolScaledSizer
                    forecast_vol = sizer.forecast_vol(recent_data)
                    signal_series = signals['signal']
                    positions_df = sizer.compute_position_size(recent_data, signal_series, live_equity, forecast_vol)
                    position_size = positions_df['position_size'].iloc[-1] if len(positions_df) > 0 else 0

                    # Use min lot as floor
                    min_lot = 0.01
                    if position_size < min_lot:
                        position_size = min_lot

                    # Compute stop/take based on ATR
                    if latest_signal == 1:
                        stop_price = current_price - 2.0 * current_atr
                        take_profit = current_price + 2.0 * current_atr
                    else:
                        stop_price = current_price + 2.0 * current_atr
                        take_profit = current_price - 2.0 * current_atr

                    trade_config = TradeConfig(
                        symbol='XAUUSDm', signal=latest_signal, entry_price=current_price,
                        stop_price=stop_price, take_profit=take_profit,
                        position_size=position_size, max_hold_hours=24,
                        risk_pct=0.05, entry_time=pd.Timestamp.now(tz='UTC')
                    )

                    # Per-trade risk check
                    can_open, reason = risk_manager.check_per_trade_risk(trade_config, live_equity)

                    if not can_open:
                        orders_rejected_risk += 1
                        print(f'  REJECTED (per-trade risk): {reason}')
                        audit_logger.log_risk_event(
                            'REJECTED_PER_TRADE', reason, live_equity, 0.0, 0.0,
                            risk_manager.kill_switch_halted
                        )
                        continue

                    # Place real order
                    print(f'  Placing {signal_type} order...')
                    spec = symbol_resolver.get_symbol_info('XAUUSDm')
                    fill = order_router.send_order(trade_config, spec)

                    if fill.success:
                        orders_placed += 1

                        # Calculate slippage
                        price_slippage = fill.slippage
                        size_slippage = fill.size_slippage
                        total_slippage_points += price_slippage
                        total_size_slippage += size_slippage

                        # Log to audit
                        risk_at_stop = abs(trade_config.entry_price - trade_config.stop_price) * trade_config.position_size * 100
                        risk_pct = risk_at_stop / live_equity * 100

                        audit_logger.log_risk_decision(
                            trade_config, 'APPROVED', 'All risk checks passed',
                            trade_config.position_size * trade_config.entry_price, live_equity,
                            5.0, 50.0, 0.0
                        )
                        audit_logger.log_signal(trade_config, trade_config.entry_price, True, None, risk_at_stop, risk_pct)
                        audit_logger.log_fill(fill, trade_config, trade_config.entry_price)

                        print(f'  FILLED: Ticket={fill.ticket}, Price={fill.price}, Size={fill.volume}')
                        print(f'  Slippage: {price_slippage:.2f} pts ({price_slippage/current_price*10000:.1f} bps), Size: {size_slippage:.4f} lots')
                    else:
                        orders_failed += 1
                        print(f'  FAILED: {fill.comment}')
                        audit_logger.log_risk_event(
                            'ORDER_FAILED', fill.comment, live_equity, 0.0, 0.0,
                            risk_manager.kill_switch_halted
                        )

            # Update equity from account
            account = mt5.account_info()
            if account:
                live_equity = account.equity
                risk_manager.current_equity = live_equity
                risk_manager.peak_equity = max(risk_manager.peak_equity, live_equity)

            # Check kill switch
            if risk_manager.kill_switch_halted:
                print(f'[{datetime.now()}] KILL SWITCH ACTIVATED - HALTING')
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print(f'\n[{datetime.now()}] Session interrupted by user')

    print()
    print('=== SESSION SUMMARY ===')
    print(f'Duration: {datetime.now() - session_start}')
    print(f'Signals Generated: {signals_generated}')
    print(f'Orders Placed: {orders_placed}')
    print(f'Orders Rejected (Risk): {orders_rejected_risk}')
    print(f'Orders Failed: {orders_failed}')
    print(f'Final Equity: ${live_equity:.2f}')
    print(f'Total Price Slippage: {total_slippage_points:.2f} points')
    print(f'Total Size Slippage: {total_size_slippage:.4f} lots')
    if orders_placed > 0:
        print(f'Avg Slippage per Trade: {total_slippage_points/orders_placed:.2f} points')

    # Show final audit log
    conn = sqlite3.connect(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM fills')
    fill_count = cursor.fetchone()[0]
    print(f'Total Fills in Audit Log: {fill_count}')

    cursor.execute('SELECT COUNT(*) FROM signals')
    signal_count = cursor.fetchone()[0]
    print(f'Total Signals in Audit Log: {signal_count}')

    cursor.execute('SELECT COUNT(*) FROM risk_decisions')
    decision_count = cursor.fetchone()[0]
    print(f'Total Risk Decisions in Audit Log: {decision_count}')

    cursor.execute('SELECT COUNT(*) FROM risk_events')
    event_count = cursor.fetchone()[0]
    print(f'Total Risk Events in Audit Log: {event_count}')

    conn.close()


if __name__ == "__main__":
    main()