import sys
sys.path.insert(0, 'C:/Users/RIDGE/OneDrive/Desktop/MARS-QUANT')
import os
import time
from datetime import datetime, timedelta

from mars.core.config import MT5Config
from mars.apps.trading.mt5_executor import MT5ConnectionManager, MT5SymbolResolver, MT5OrderRouter, MT5AuditLogger
from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig, VolScaledSizer, SizingConfig
from mars.apps.trading.signals.trend_breakout import DonchianBreakoutSignal, MACrossoverSignal, CombinedTrendSignal, TrendSignalFactory
import pandas as pd
import tempfile
import sqlite3

# Clean up
if os.path.exists('risk_kill_switch.json'):
    os.remove('risk_kill_switch.json')

config = MT5Config()
conn_manager = MT5ConnectionManager(config)
if not conn_manager.connect():
    print("Failed to connect to MT5")
    sys.exit(1)

mt5 = conn_manager.mt5

# Get real symbol info
symbol = mt5.symbol_info('XAUUSDm')
price = symbol.ask
bid = symbol.bid

print('Connected to MT5 DEMO account #476944496')
print('Symbol: XAUUSDm')
print(f'Price: {price}, Bid: {bid}, Spread: {symbol.spread} points')

equity = 124.73
atr = 5.53429
min_lot = 0.01

# Create risk manager with adjusted limits for small account
risk_manager = RiskManager(
    max_daily_loss_pct=0.02,
    max_weekly_loss_pct=0.50,
    max_monthly_loss_pct=0.50,
    max_drawdown_pct=0.15,
    max_position_pct=0.50,
    max_risk_per_trade_pct=0.05,
    kill_switch_file=os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json'),
)
risk_manager.reset_daily(equity)
risk_manager.peak_equity = equity
risk_manager.current_equity = equity

# Create the executor components with REAL MT5 connection
symbol_resolver = MT5SymbolResolver(mt5)
order_router = MT5OrderRouter(mt5, symbol_resolver)
audit_logger = MT5AuditLogger(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))

# Load historical data for signal generation
df = pd.read_parquet('data/processed/xauusd/m5/v1.0.0/data.parquet')
df.index = pd.DatetimeIndex(df['timestamp'])

# Use recent data for signal generation
recent_data = df.tail(5000).copy()

# Create signal generator
signal_generator = DonchianBreakoutSignal(
    window=20,
    exit_window=10,
    session_filter=None
)

# Generate signals on recent data
print('Generating signals on recent data...')
signal_df = signal_generator.generate(recent_data)

# Get the latest signal
latest_signal = signal_df['signal'].iloc[-1]
print(f'Latest signal: {latest_signal} (1=long, -1=short, 0=flat)')
print()

print('=== STARTING UNATTENDED DEMO SESSION ===')
print(f'Start time: {datetime.now()}')
print(f'Equity: ${equity:.2f}')
print(f'Max risk per trade: 5% (${equity * 0.05:.2f})')
print(f'Max concurrent: 50% (${equity * 0.50:.2f})')
print(f'Min lot: {min_lot}')
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
    # Run for 30 minutes (or until interrupted)
    max_duration = timedelta(minutes=30)
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
            # Round to nearest 5-minute boundary
            bar_time = bar_time.replace(minute=(bar_minute // 5) * 5)
        
        if last_bar_time is not None and bar_time == last_bar_time:
            time.sleep(1)
            continue
        
        last_bar_time = bar_time
        
        # Update recent data with latest bar
        # For simplicity, just use the latest price for signal check
        # In production, you'd append the new bar and re-generate signals
        
        # Generate signal using the latest data
        # We need to get the signal for the most recent bar
        signals = signal_generator.generate(recent_data)
        
        if len(signals) > 0:
            latest_signal = signals['signal'].iloc[-1]
            if latest_signal != 0:
                signals_generated += 1
                signal_type = 'BUY' if latest_signal == 1 else 'SELL'
                print(f'[{datetime.now()}] SIGNAL: {signal_type} at {current_price}')
                
                # Risk checks
                can_open, reason = risk_manager.can_open_position(
                    'XAUUSDm', min_lot * current_price, equity
                )
                
                if not can_open:
                    orders_rejected_risk += 1
                    print(f'  REJECTED (concurrent risk): {reason}')
                    audit_logger.log_risk_event(
                        'REJECTED_CONCURRENT', reason, equity, 0.0, 0.0, 
                        risk_manager.kill_switch_halted
                    )
                    continue
                
                # Create trade config
                if latest_signal == 1:  # Long
                    stop_price = current_price - atr
                    take_profit = current_price + atr
                else:  # Short
                    stop_price = current_price + atr
                    take_profit = current_price - atr
                
                trade_config = TradeConfig(
                    symbol='XAUUSDm', signal=latest_signal, entry_price=current_price,
                    stop_price=stop_price, take_profit=take_profit,
                    position_size=min_lot, max_hold_hours=24,
                    risk_pct=0.05, entry_time=pd.Timestamp.now(tz='UTC')
                )
                
                # Per-trade risk check
                can_open, reason = risk_manager.check_per_trade_risk(trade_config, equity)
                
                if not can_open:
                    orders_rejected_risk += 1
                    print(f'  REJECTED (per-trade risk): {reason}')
                    audit_logger.log_risk_event(
                        'REJECTED_PER_TRADE', reason, equity, 0.0, 0.0,
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
                    risk_pct = risk_at_stop / equity * 100
                    
                    audit_logger.log_risk_decision(
                        trade_config, 'APPROVED', 'All risk checks passed',
                        trade_config.position_size * trade_config.entry_price, equity,
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
                        'ORDER_FAILED', fill.comment, equity, 0.0, 0.0,
                        risk_manager.kill_switch_halted
                    )
        
        # Update equity from account
        account = mt5.account_info()
        if account:
            equity = account.equity
            risk_manager.current_equity = equity
            risk_manager.peak_equity = max(risk_manager.peak_equity, equity)
        
        # Check kill switch
        if risk_manager.kill_switch_halted:
            print(f'[{datetime.now()}] KILL SWITCH ACTIVATED - HALTING')
            break
        
        # Print status every 5 minutes
        elapsed = datetime.now() - session_start
        if elapsed.total_seconds() % 300 < 2:
            print(f'[{datetime.now()}] Status: Signals={signals_generated}, Placed={orders_placed}, Rejected={orders_rejected_risk}, Failed={orders_failed}, Equity=${equity:.2f}')
        
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
print(f'Final Equity: ${equity:.2f}')
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