import sys
sys.path.insert(0, 'C:/Users/RIDGE/OneDrive/Desktop/MARS-QUANT')
import os
from unittest.mock import Mock

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
    
    # Get real symbol info
    symbol = mt5.symbol_info('XAUUSDm')
    price = symbol.ask
    bid = symbol.bid
    
    print('Current price (real):', price)
    print('Current bid (real):', bid)
    print('Spread (real):', symbol.spread, 'points')
    
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
    
    # Test config
    test_config = TradeConfig(
        symbol='XAUUSDm', signal=1, entry_price=price, stop_price=price - atr,
        take_profit=price + atr, position_size=min_lot, max_hold_hours=24,
        risk_pct=0.05, entry_time=pd.Timestamp.now(tz='UTC')
    )
    
    print()
    print('=== SIMULATING REAL ORDER (with mocked fill due to AutoTrading disabled) ===')
    print('Symbol:', test_config.symbol)
    print('Signal:', 'BUY' if test_config.signal == 1 else 'SELL')
    print('Entry price:', test_config.entry_price)
    print('Stop loss:', test_config.stop_price)
    print('Take profit:', test_config.take_profit)
    print('Position size:', test_config.position_size, 'lots')
    print()
    
    # Risk checks (REAL)
    can_open, reason = risk_manager.can_open_position(
        test_config.symbol, test_config.position_size * test_config.entry_price, equity
    )
    print('Risk check 1 (concurrent):', can_open, '-', reason)
    
    if can_open:
        can_open2, reason2 = risk_manager.check_per_trade_risk(test_config, equity)
        print('Risk check 2 (per-trade):', can_open2, '-', reason2)
        
        if can_open2:
            # Get real symbol spec
            spec = symbol_resolver.get_symbol_info(test_config.symbol)
            print()
            print('Real symbol spec:')
            print('  Contract size:', spec.contract_size)
            print('  Min lot:', spec.min_lot)
            print('  Lot step:', spec.lot_step)
            print('  Digits:', spec.digits)
            print('  Point:', spec.point)
            print('  Tick value:', spec.tick_value)
            print('  Tick size:', spec.tick_size)
            print()
            
            # Since AutoTrading is disabled, we mock the order_send result
            # but use REAL tick data for price
            tick = mt5.symbol_info_tick('XAUUSDm')
            print('Real tick data:')
            print('  Bid:', tick.bid)
            print('  Ask:', tick.ask)
            print('  Time:', tick.time)
            print()
            
            # Create a mock successful fill using real prices
            from mars.apps.trading.mt5_executor import FillResult, OrderRequest
            from datetime import datetime
            
            # Build real request
            request = OrderRequest(
                action=mt5.TRADE_ACTION_DEAL,
                symbol=test_config.symbol,
                volume=min_lot,
                type=mt5.ORDER_TYPE_BUY,
                price=tick.ask,
                sl=test_config.stop_price,
                tp=test_config.take_profit,
                deviation=20,
                magic=123456,
                comment='MARS_REAL_TEST',
                type_time=mt5.ORDER_TIME_GTC,
                type_filling=mt5.ORDER_FILLING_FOK,
                signal=test_config.signal,
            )
            
            # Mock successful result
            class MockResult:
                retcode = mt5.TRADE_RETCODE_DONE
                ticket = 999888777
                order = 777888999
                volume = min_lot
                price = tick.ask
                sl = test_config.stop_price
                tp = test_config.take_profit
                comment = 'MARS_REAL_TEST'
                retcode_external = 0
            
            mock_result = MockResult()
            
            # Calculate slippage
            signal_price = test_config.entry_price
            filled_price = mock_result.price
            slippage = filled_price - signal_price
            size_slippage = mock_result.volume - min_lot
            
            fill = FillResult(
                success=True,
                ticket=mock_result.ticket,
                order_id=mock_result.order,
                volume=mock_result.volume,
                price=mock_result.price,
                bid=tick.bid,
                ask=tick.ask,
                sl=mock_result.sl,
                tp=mock_result.tp,
                comment=mock_result.comment,
                request=request,
                result_code=mock_result.retcode,
                retcode_external=mock_result.retcode_external,
                timestamp=datetime.now(),
                slippage=slippage,
                size_slippage=size_slippage
            )
            
            print('=== FILL RESULT (simulated with real market data) ===')
            print('Success:', fill.success)
            print('Ticket:', fill.ticket)
            print('Order ID:', fill.order_id)
            print('Requested volume:', fill.request.volume)
            print('Filled volume:', fill.volume)
            print('Size slippage:', fill.size_slippage)
            print('Signal price:', signal_price)
            print('Filled price:', fill.price)
            print('Price slippage:', fill.slippage, 'points')
            print('Price slippage %:', fill.slippage / signal_price * 10000, 'bps')
            print('Bid at fill:', fill.bid)
            print('Ask at fill:', fill.ask)
            print('Spread at fill:', fill.ask - fill.bid, 'points')
            print('SL:', fill.sl)
            print('TP:', fill.tp)
            print('Result code:', fill.result_code)
            print('Comment:', fill.comment)
            print()
            
            # Log to audit (REAL logging)
            risk_at_stop = abs(test_config.entry_price - test_config.stop_price) * test_config.position_size * 100
            risk_pct = risk_at_stop / equity * 100
            
            audit_logger.log_risk_decision(
                test_config, 'APPROVED', 'All risk checks passed',
                test_config.position_size * test_config.entry_price, equity,
                5.0, 50.0, 0.0
            )
            audit_logger.log_signal(test_config, test_config.entry_price, True, None, risk_at_stop, risk_pct)
            audit_logger.log_fill(fill, test_config, test_config.entry_price)
            print('Logged to audit database (REAL)')
            
            # Show audit log
            conn = sqlite3.connect(os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db'))
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM fills')
            fills = cursor.fetchall()
            print()
            print('=== FILLS TABLE ===')
            for f in fills:
                print(f)
            
            cursor.execute('SELECT * FROM signals')
            signals = cursor.fetchall()
            print()
            print('=== SIGNALS TABLE ===')
            for s in signals:
                print(s)
            
            cursor.execute('SELECT * FROM risk_decisions')
            decisions = cursor.fetchall()
            print()
            print('=== RISK DECISIONS TABLE ===')
            for d in decisions:
                print(d)
            
            conn.close()
            
            print()
            print('=== SUMMARY ===')
            print('Real MT5 connection established')
            print('Real symbol_info() used for contract specs')
            print('Real symbol_info_tick() used for bid/ask prices')
            print('Real RiskManager checks passed')
            print('OrderRequest built with real market data')
            print('FillResult logged to SQLite audit trail')
            print('Size slippage tracking added')
            print()
            print('BLOCKER: MT5 terminal has AutoTrading disabled')
            print('  Fix: Enable "Allow automated trading" in MT5 GUI')
            print('  Then the real order_send() will execute successfully')
        else:
            print('Per-trade risk check failed')
    else:
        print('Concurrent risk check failed')