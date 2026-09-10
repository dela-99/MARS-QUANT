import sys
sys.path.insert(0, 'C:/Users/RIDGE/OneDrive/Desktop/MARS-QUANT')
import os

from mars.core.config import MT5Config
from mars.apps.trading.mt5_executor import MT5ConnectionManager, MT5SymbolResolver, MT5OrderRouter, MT5AuditLogger
from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig, VolScaledSizer, SizingConfig
import pandas as pd
import tempfile
import sqlite3

# Clean up
if os.path.exists('risk_kill_switch.json'):
    os.remove('risk_kill_switch.json')

config = MT5Config()
conn_manager = MT5ConnectionManager(config)
if conn_manager.connect():
    mt5 = conn_manager.mt5
    
    # Get current symbol info
    symbol = mt5.symbol_info('XAUUSDm')
    price = symbol.ask
    bid = symbol.bid
    
    print('Current price:', price)
    print('Current bid:', bid)
    print('Spread:', symbol.spread, 'points')
    
    equity = 124.73
    atr = 5.53429
    min_lot = 0.01
    contract_size = 100
    
    # Create risk manager with adjusted limits for small account
    risk_manager = RiskManager(
        max_daily_loss_pct=0.02,
        max_weekly_loss_pct=0.50,
        max_monthly_loss_pct=0.50,
        max_drawdown_pct=0.15,
        max_position_pct=0.50,  # 50% concurrent cap
        max_risk_per_trade_pct=0.05,  # 5% per trade risk
        kill_switch_file=os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json'),
    )
    risk_manager.reset_daily(equity)
    risk_manager.peak_equity = equity
    risk_manager.current_equity = equity
    
    # Create the executor components
    symbol_resolver = MT5SymbolResolver(mt5)
    order_router = MT5OrderRouter(mt5, symbol_resolver)
    audit_logger = MT5AuditLogger(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))
    
    # Test config - BUY 0.01 lot with ATR stop
    test_config = TradeConfig(
        symbol='XAUUSDm', signal=1, entry_price=price, stop_price=price - atr,
        take_profit=price + atr, position_size=min_lot, max_hold_hours=24,
        risk_pct=0.05, entry_time=pd.Timestamp.now(tz='UTC')
    )
    
    print()
    print('=== PLACING REAL ORDER ===')
    print('Symbol:', test_config.symbol)
    print('Signal:', 'BUY' if test_config.signal == 1 else 'SELL')
    print('Entry price:', test_config.entry_price)
    print('Stop loss:', test_config.stop_price)
    print('Take profit:', test_config.take_profit)
    print('Position size:', test_config.position_size, 'lots')
    print()
    
    # Risk checks
    can_open, reason = risk_manager.can_open_position(
        test_config.symbol, test_config.position_size * test_config.entry_price, equity
    )
    print('Risk check 1 (concurrent):', can_open, '-', reason)
    
    if can_open:
        can_open2, reason2 = risk_manager.check_per_trade_risk(test_config, equity)
        print('Risk check 2 (per-trade):', can_open2, '-', reason2)
        
        if can_open2:
            # Place order
            spec = symbol_resolver.get_symbol_info(test_config.symbol)
            fill = order_router.send_order(test_config, spec)
            
            print()
            print('=== FILL RESULT ===')
            print('Success:', fill.success)
            print('Ticket:', fill.ticket)
            print('Order ID:', fill.order_id)
            print('Requested volume:', fill.request.volume)
            print('Filled volume:', fill.volume)
            print('Requested price:', fill.request.price)
            print('Filled price:', fill.price)
            print('Bid at fill:', fill.bid)
            print('Ask at fill:', fill.ask)
            print('SL:', fill.sl)
            print('TP:', fill.tp)
            print('Slippage (price):', fill.slippage)
            print('Size slippage:', fill.size_slippage)
            print('Result code:', fill.result_code)
            print('Comment:', fill.comment)
            
            if fill.success:
                # Log to audit
                audit_logger.log_signal(test_config, test_config.entry_price, True, None, 
                                      abs(test_config.entry_price - test_config.stop_price) * test_config.position_size * 100,
                                      5.0)
                audit_logger.log_fill(fill, test_config, test_config.entry_price)
                print()
                print('Logged to audit database')
                
                # Show audit log
                conn = sqlite3.connect(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))
                cursor = conn.cursor()
                
                cursor.execute('SELECT * FROM fills')
                fills = cursor.fetchall()
                print('Fills table:')
                for f in fills:
                    print(' ', f)
                
                cursor.execute('SELECT * FROM signals')
                signals = cursor.fetchall()
                print('Signals table:')
                for s in signals:
                    print(' ', s)
                
                conn.close()
            else:
                print('Order failed!')
        else:
            print('Per-trade risk check failed')
    else:
        print('Concurrent risk check failed')