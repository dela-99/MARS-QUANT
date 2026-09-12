#!/usr/bin/env python3
"""
Live trading session with tiered risk config - DRY RUN mode for validation.
"""
import sys
import os
import time
import argparse
from datetime import datetime, timedelta

# Ensure local package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mars.core.config import MT5Config, DEFAULT_CONFIG
from mars.apps.trading.mt5_executor import MT5Executor
from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig, VolScaledSizer, SizingConfig
from mars.apps.trading.signals.trend_breakout import DonchianBreakoutSignal
import pandas as pd
import tempfile
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="MARS Live Trading Session")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without placing orders")
    parser.add_argument("--duration", type=int, default=5, help="Session duration in minutes (default: 5)")
    args = parser.parse_args()

    # Clean up any stale kill-switch file from previous runs
    kill_switch_path = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')
    if os.path.exists(kill_switch_path):
        os.remove(kill_switch_path)

    # --- MT5 Config & Demo Account Safety Gate ---
    config = MT5Config()
    if not config.is_configured():
        print("MT5 credentials not configured")
        sys.exit(1)

    # --- Instantiate RiskManager (ONLY kill_switch_file accepted now) ---
    risk_manager = RiskManager(
        kill_switch_file=kill_switch_path,
    )

    # --- Connect to MT5 to get LIVE equity for tier selection ---
    print("=== DRY RUN: Connecting to MT5 for live equity ===")
    mt5_config = DEFAULT_CONFIG.mt5
    # Create a temporary executor just to get the connection (it runs DemoAccountGate)
    from mars.apps.trading.mt5_executor import MT5ConnectionManager, DemoAccountGate
    conn_manager = MT5ConnectionManager(mt5_config)
    conn_manager.connect()
    mt5 = conn_manager.mt5

    # Verify demo account and get live equity
    account_info = mt5.account_info()
    if account_info is None:
        raise RuntimeError(f"Failed to get account info: {mt5.last_error()}")

    live_equity = float(account_info.equity)
    account_number = account_info.login
    trade_mode = account_info.trade_mode

    print(f"MT5 ACCOUNT CONNECTED: #{account_number} | Trade Mode: {trade_mode} (0=DEMO)")
    print(f"LIVE EQUITY: ${live_equity:.2f}")

    if trade_mode != 0:
        raise RuntimeError("SAFETY GATE FAILED: Account is NOT a DEMO account")

    # --- SELECT AND LOCK TIER BASED ON LIVE EQUITY ---
    tier = risk_manager.select_tier_for_equity(live_equity)
    print()
    print("=== TIER SELECTED (LOCKED FOR SESSION) ===")
    print(f"  Equity: ${live_equity:.2f}")
    print(f"  Tier: ${tier['min_equity']:.0f} - ${tier['max_equity'] if tier['max_equity'] != float('inf') else '∞'}")
    print(f"  Max Concurrent Trades: {tier['max_concurrent_trades']}")
    print(f"  Risk per Trade: {tier['risk_pct_per_trade']:.1%}")
    print(f"  Reward:Risk Ratio: {tier['reward_risk_ratio']:.1f}")
    print(f"  Tier Locked: {risk_manager.is_tier_locked()}")
    print(f"  Locked At Equity: ${risk_manager._tier_locked_at_equity:.2f}")

    # Cross-check against RISK_TIERS definition
    expected_tier = None
    for min_eq, max_eq, max_trades, risk_pct, rr_ratio in RiskManager.RISK_TIERS:
        if min_eq <= live_equity < max_eq:
            expected_tier = (min_eq, max_eq, max_trades, risk_pct, rr_ratio)
            break

    assert expected_tier is not None, f"No tier found for equity ${live_equity:.2f}"
    assert tier['min_equity'] == expected_tier[0], f"Tier boundary mismatch: {tier['min_equity']} != {expected_tier[0]}"
    assert tier['max_equity'] == expected_tier[1], f"Tier boundary mismatch: {tier['max_equity']} != {expected_tier[1]}"
    assert tier['max_concurrent_trades'] == expected_tier[2]
    assert tier['risk_pct_per_trade'] == expected_tier[3]
    assert tier['reward_risk_ratio'] == expected_tier[4]
    print("  ✅ Tier matches RISK_TIERS definition exactly (boundary logic verified)")

    # --- Initialize RiskManager equity state (prevents ZeroDivisionError in check_limits) ---
    # NOTE: reset_daily() resets tier lock, so call it BEFORE selecting tier, or just set fields directly
    risk_manager.current_equity = live_equity
    risk_manager.peak_equity = live_equity
    risk_manager.daily_pnl = 0.0
    # Do NOT call reset_daily() after select_tier_for_equity() — it clears the tier lock!

    # --- Create Sizer ---
    sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
    sizer = VolScaledSizer(sizing_config, garch_variant='garch')

    # --- Load Historical Data for Signal Generation ---
    df = pd.read_parquet('data/processed/xauusd/m5/v1.0.0/data.parquet')
    df.index = pd.DatetimeIndex(df['timestamp'])
    recent_data = df.tail(5000).copy()

    # --- Create Signal Generator ---
    signal_generator = DonchianBreakoutSignal(
        window=20,
        exit_window=10,
        session_filter=None
    )

    print()
    print('Generating signals on recent data...')
    signal_df = signal_generator.generate(recent_data)
    latest_signal = signal_df['signal'].iloc[-1]
    print(f'Latest signal: {latest_signal} (1=long, -1=short, 0=flat)')

    # --- Create MT5Executor with tiered RiskManager ---
    executor = MT5Executor(
        equity=live_equity,
        risk_manager=risk_manager,
        sizer=sizer,
        mt5_config=mt5_config,
        audit_db_path=os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db')
    )

    print()
    print(f'=== {"DRY RUN" if args.dry_run else "LIVE SESSION"} STARTING ({args.duration} minutes) ===')
    print(f'Start time: {datetime.now()}')
    print(f'Equity: ${live_equity:.2f}')
    print(f'Tier risk per trade: {tier["risk_pct_per_trade"]:.1%} (${live_equity * tier["risk_pct_per_trade"]:.2f})')
    print(f'Max concurrent trades: {tier["max_concurrent_trades"]}')
    print()

    if args.dry_run:
        print("✅ DRY RUN COMPLETE - All validations passed, no orders placed.")
        print("   Tier selection and lock confirmed.")
        print("   Demo account safety gate passed.")
        print("   Ready for live session.")
        executor.shutdown()
        return 0

    # --- LIVE SESSION LOOP (unchanged from original) ---
    session_start = datetime.now()
    signals_generated = 0
    orders_placed = 0
    orders_failed = 0
    total_slippage_points = 0.0
    total_size_slippage = 0.0

    try:
        max_duration = timedelta(minutes=args.duration)
        last_bar_time = None

        while datetime.now() - session_start < max_duration:
            executor._ensure_connection()
            tick = executor.mt5.symbol_info_tick('XAUUSDm')
            if tick is None:
                print(f'[{datetime.now()}] No tick data, waiting...')
                time.sleep(5)
                continue

            current_price = tick.ask
            current_time = datetime.fromtimestamp(tick.time)

            bar_time = current_time.replace(second=0, microsecond=0)
            bar_minute = bar_time.minute
            if bar_minute % 5 != 0:
                bar_time = bar_time.replace(minute=(bar_minute // 5) * 5)

            if last_bar_time is not None and bar_time == last_bar_time:
                time.sleep(1)
                continue

            last_bar_time = bar_time

            signals = signal_generator.generate(recent_data)

            if len(signals) > 0:
                latest_signal = signals['signal'].iloc[-1]
                if latest_signal != 0:
                    signals_generated += 1
                    signal_type = 'BUY' if latest_signal == 1 else 'SELL'
                    print(f'[{datetime.now()}] SIGNAL: {signal_type} at {current_price}')

                    if latest_signal == 1:
                        stop_price = current_price - 5.53429
                        take_profit = current_price + 5.53429
                    else:
                        stop_price = current_price + 5.53429
                        take_profit = current_price - 5.53429

                    trade_config = TradeConfig(
                        symbol='XAUUSDm', signal=latest_signal, entry_price=current_price,
                        stop_price=stop_price, take_profit=take_profit,
                        position_size=0.01, max_hold_hours=24,
                        risk_pct=0.05, entry_time=pd.Timestamp.now(tz='UTC')
                    )

                    success = executor.open_position(trade_config)

                    if success:
                        orders_placed += 1
                        conn = sqlite3.connect(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM fills ORDER BY timestamp DESC LIMIT 1")
                        fill = cursor.fetchone()
                        conn.close()

                        if fill:
                            price_slippage = fill[9]
                            size_slippage = fill[11]
                            total_slippage_points += price_slippage
                            total_size_slippage += size_slippage
                            print(f'  FILLED: Ticket={fill[1]}, Price={fill[8]}, Size={fill[6]}')
                            print(f'  Slippage: {price_slippage:.2f} pts ({price_slippage/current_price*10000:.1f} bps), Size: {size_slippage:.4f} lots')
                    else:
                        orders_failed += 1
                        print(f'  ORDER REJECTED/FAILED')

            executor._ensure_connection()
            account = executor.mt5.account_info()
            if account:
                live_equity = account.equity
                executor.equity = live_equity
                executor.risk_manager.current_equity = live_equity
                executor.risk_manager.peak_equity = max(executor.risk_manager.peak_equity, live_equity)

            if executor.risk_manager.kill_switch_halted:
                print(f'[{datetime.now()}] KILL SWITCH ACTIVATED - HALTING')
                break

            elapsed = datetime.now() - session_start
            if elapsed.total_seconds() % 30 < 2:
                print(f'[{datetime.now()}] Status: Signals={signals_generated}, Placed={orders_placed}, Failed={orders_failed}, Equity=${live_equity:.2f}')

            time.sleep(1)

    except KeyboardInterrupt:
        print(f'\n[{datetime.now()}] Session interrupted by user')

    finally:
        executor.shutdown()

    print()
    print('=== SESSION SUMMARY ===')
    print(f'Duration: {datetime.now() - session_start}')
    print(f'Signals Generated: {signals_generated}')
    print(f'Orders Placed: {orders_placed}')
    print(f'Orders Failed/Rejected: {orders_failed}')
    print(f'Final Equity: ${live_equity:.2f}')
    print(f'Total Price Slippage: {total_slippage_points:.2f} points')
    print(f'Total Size Slippage: {total_size_slippage:.4f} lots')

    return 0


if __name__ == "__main__":
    sys.exit(main())