import sys
sys.path.insert(0, 'C:/Users/RIDGE/OneDrive/Desktop/MARS-QUANT')
import os
import tempfile
import sqlite3
import pandas as pd
from unittest.mock import Mock

sys.path.insert(0, 'C:/Users/RIDGE/OneDrive/Desktop/MARS-QUANT')

from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig, VolScaledSizer, SizingConfig
from mars.apps.trading.mt5_executor import MT5SymbolResolver, MT5OrderRouter, MT5AuditLogger, MT5SymbolResolver

# Clean up
if os.path.exists('risk_kill_switch.json'):
    os.remove('risk_kill_switch.json')

equity = 100000
kill_switch_file = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')

risk_manager = RiskManager(
    max_daily_loss_pct=0.02, max_weekly_loss_pct=0.50,
    max_monthly_loss_pct=0.50, max_drawdown_pct=0.15,
    max_position_pct=0.30, max_risk_per_trade_pct=0.01,
    kill_switch_file=os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json'),
)
risk_manager.reset_daily(equity)
risk_manager.peak_equity = equity
risk_manager.current_equity = equity

# Create mock MT5
from unittest.mock import Mock
mock_mt5 = Mock()
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.ORDER_FILLING_FOK = 0

mock_account = Mock()
mock_account.login = 476944496
mock_account.trade_mode = 0
mock_account.balance = 100000.0
mock_account.equity = 100000.0
mock_account.currency = 'USD'
mock_account.leverage = 2000
mock_mt5.account_info.return_value = mock_account

mock_symbol = Mock()
mock_symbol.name = 'XAUUSDm'
mock_symbol.trade_contract_size = 100.0
mock_symbol.volume_min = 0.01
mock_symbol.volume_max = 200.0
mock_symbol.volume_step = 0.01
mock_symbol.digits = 3
mock_symbol.point = 0.001
mock_symbol.spread = 260
mock_symbol.bid = 4414.36
mock_symbol.ask = 4414.62
mock_symbol.visible = True
mock_symbol.trade_tick_size = 0.001
mock_symbol.trade_tick_value = 1.0
mock_symbol.swap_long = -1.5
mock_symbol.swap_short = -0.5
mock_symbol.margin_initial = 1000.0
mock_symbol.margin_maintenance = 500.0
mock_symbol.session_deals = 0
mock_symbol.session_buy_orders = 0
mock_symbol.session_sell_orders = 0
mock_symbol.time = 1704067200

mock_mt5.symbol_info.return_value = mock_symbol
mock_mt5.symbol_info_tick.return_value = Mock(bid=4414.36, ask=4414.62)
mock_mt5.order_send.return_value = Mock(
    retcode=10009,
    ticket=123456789,
    order=987654321,
    volume=0.5,
    price=4414.62,
    sl=4400.0,
    tp=4450.0,
    comment='MARS_1_100000'
)
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.ORDER_FILLING_FOK = 0

# Test the executor
from mars.apps.trading.mt5_executor import MT5SymbolResolver, MT5OrderRouter, MT5AuditLogger, MT5SymbolResolver

equity = 100000
kill_switch_file = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')

risk_manager = RiskManager(
    max_daily_loss_pct=0.02, max_weekly_loss_pct=0.50,
    max_monthly_loss_pct=0.50, max_drawdown_pct=0.15,
    max_position_pct=0.30, max_risk_per_trade_pct=0.01,
    kill_switch_file=os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json'),
)
risk_manager.reset_daily(equity)
risk_manager.peak_equity = equity
risk_manager.current_equity = equity

sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
sizer = VolScaledSizer(sizing_config, garch_variant='garch')

mock_mt5 = Mock()
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.ORDER_FILLING_FOK = 0

mock_account = Mock()
mock_account.login = 476944496
mock_account.trade_mode = 0
mock_account.balance = 100000.0
mock_account.equity = 100000.0
mock_account.currency = 'USD'
mock_account.leverage = 2000
mock_mt5.account_info.return_value = mock_account

mock_symbol = Mock()
mock_symbol.name = 'XAUUSDm'
mock_symbol.trade_contract_size = 100.0
mock_symbol.volume_min = 0.01
mock_symbol.volume_max = 200.0
mock_symbol.volume_step = 0.01
mock_symbol.digits = 3
mock_symbol.point = 0.001
mock_symbol.spread = 260
mock_symbol.bid = 4414.36
mock_symbol.ask = 4414.62
mock_symbol.visible = True
mock_symbol.trade_tick_size = 0.001
mock_symbol.trade_tick_value = 1.0
mock_symbol.swap_long = -1.5
mock_symbol.swap_short = -0.5
mock_symbol.margin_initial = 1000.0
mock_symbol.margin_maintenance = 500.0
mock_symbol.session_deals = 0
mock_symbol.session_buy_orders = 0
mock_symbol.session_sell_orders = 0
mock_symbol.time = 1704067200

mock_mt5.symbol_info.return_value = mock_symbol
mock_mt5.symbol_info_tick.return_value = Mock(bid=4414.36, ask=4414.62)
mock_mt5.order_send.return_value = Mock(
    retcode=10009,
    ticket=123456789,
    order=987654321,
    volume=0.5,
    price=4414.62,
    sl=4400.0,
    tp=4450.0,
    comment='MARS_1_100000'
)
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.ORDER_FILLING_FOK = 0

# Test the executor
class MockMT5Executor:
    def __init__(self, equity, risk_manager, sizer, mock_mt5):
        self.equity = equity
        self.risk_manager = risk_manager
        self.sizer = sizer
        self.mt5 = mock_mt5
        self.symbol_resolver = MT5SymbolResolver(mock_mt5)
        self.order_router = MT5OrderRouter(mock_mt5, MT5SymbolResolver(mock_mt5))
        self.audit_logger = MT5AuditLogger(os.path.join(tempfile.gettempdir(), 'mt5_audit.db'))
        self.open_positions = {}
        self.closed_trades = []
        self.equity_curve = [equity]
    
    def open_position(self, config):
        signal_price = config.entry_price
        risk_at_stop = abs(config.entry_price - config.stop_price) * config.position_size * 100
        risk_pct = risk_at_stop / self.equity * 100 if self.equity > 0 else 0
        
        can_open, reason = self.risk_manager.can_open_position(
            config.symbol, config.position_size * config.entry_price, self.equity
        )
        if not can_open:
            self.audit_logger.log_signal(config, config.entry_price, False, reason, 
                                       abs(config.entry_price - config.stop_price) * config.position_size * 100,
                                       risk_pct)
            return False
        
        can_open, reason = self.risk_manager.check_per_trade_risk(config, self.equity)
        if not can_open:
            self.audit_logger.log_signal(config, config.entry_price, False, reason,
                                       abs(config.entry_price - config.stop_price) * config.position_size * 100,
                                       risk_at_stop / self.equity * 100 if self.equity > 0 else 0)
            return False
        
        spec = self.symbol_resolver.get_symbol_info(config.symbol)
        fill = self.order_router.send_order(config, spec)
        
        if fill.success:
            self.open_positions[config.symbol] = {
                'entry_price': fill.price,
                'stop_price': config.stop_price,
                'take_profit': config.take_profit,
                'position_size': fill.volume,
                'entry_time': config.entry_time,
                'max_hold_hours': config.max_hold_hours,
                'entry_equity': self.equity,
                'mt5_ticket': fill.ticket,
            }
            self.audit_logger.log_fill(fill, config, config.entry_price)
            return True
        return False

equity = 100000
kill_switch_file = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')

risk_manager = RiskManager(
    max_daily_loss_pct=0.02, max_weekly_loss_pct=0.50,
    max_monthly_loss_pct=0.50, max_drawdown_pct=0.15,
    max_position_pct=0.30, max_risk_per_trade_pct=0.01,
    kill_switch_file=os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json'),
)
risk_manager.reset_daily(equity)
risk_manager.peak_equity = equity
risk_manager.current_equity = equity

sizing_config = SizingConfig(target_vol=0.15, max_leverage=3.0, min_leverage=0.01, kelly_fraction=0.5)
sizer = VolScaledSizer(sizing_config, garch_variant='garch')

mock_mt5 = Mock()
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.ORDER_FILLING_FOK = 0

mock_account = Mock()
mock_account.login = 476944496
mock_account.trade_mode = 0
mock_account.balance = 100000.0
mock_account.equity = 100000.0
mock_account.currency = 'USD'
mock_account.leverage = 2000
mock_mt5.account_info.return_value = mock_account

mock_symbol = Mock()
mock_symbol.name = 'XAUUSDm'
mock_symbol.trade_contract_size = 100.0
mock_symbol.volume_min = 0.01
mock_symbol.volume_max = 200.0
mock_symbol.volume_step = 0.01
mock_symbol.digits = 3
mock_symbol.point = 0.001
mock_symbol.spread = 260
mock_symbol.bid = 4414.36
mock_symbol.ask = 4414.62
mock_symbol.visible = True
mock_symbol.trade_tick_size = 0.001
mock_symbol.trade_tick_value = 1.0
mock_symbol.swap_long = -1.5
mock_symbol.swap_short = -0.5
mock_symbol.margin_initial = 1000.0
mock_symbol.margin_maintenance = 500.0
mock_symbol.session_deals = 0
mock_symbol.session_buy_orders = 0
mock_symbol.session_sell_orders = 0
mock_symbol.time = 1704067200

mock_mt5.symbol_info.return_value = mock_symbol
mock_mt5.symbol_info_tick.return_value = Mock(bid=4414.36, ask=4414.62)
mock_mt5.order_send.return_value = Mock(
    retcode=10009,
    ticket=123456789,
    order=987654321,
    volume=0.5,
    price=4414.62,
    sl=4400.0,
    tp=4450.0,
    comment='MARS_1_100000'
)
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.ORDER_FILLING_FOK = 0

executor = MockMT5Executor(equity, risk_manager, sizer, mock_mt5)

# Test config
import pandas as pd
config = TradeConfig(
    symbol='XAUUSDm', signal=1, entry_price=4414.62, stop_price=4390.0,
    take_profit=4470.0, position_size=0.4, max_hold_hours=24,
    risk_pct=0.01, entry_time=pd.Timestamp('2024-01-01 10:00:00', tz='UTC')
)

success = executor.open_position(config)
print(f'Success: {success}')

# Check audit log
import sqlite3
conn = sqlite3.connect(os.path.join(tempfile.gettempdir(), 'mt5_audit.db'))
cursor = conn.cursor()

cursor.execute('SELECT * FROM signals WHERE signal = 1')
signals = cursor.fetchall()
print(f'Signals count: {len(signals)}')
if signals:
    print(f'First signal: {signals[0]}')

cursor.execute('SELECT * FROM fills')
fills = cursor.fetchall()
print(f'Fills count: {len(fills)}')
if fills:
    print(f'First fill: {fills[0]}')

cursor.execute('SELECT * FROM risk_decisions')
decisions = cursor.fetchall()
print(f'Decisions count: {len(decisions)}')
if decisions:
    print(f'First decision: {decisions[0]}')

conn.close()