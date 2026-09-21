"""
Tests for Manual SL/TP Modification Detection and Reconciliation.
"""
import pytest
import os
import tempfile
import sqlite3
import pandas as pd
from unittest.mock import Mock, MagicMock, patch
import sys

# Ensure we can import from mars
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from mars.apps.trading.mt5_executor import (
    MT5Executor, MT5AuditLogger, MT5Config, MT5ConnectionManager,
    MT5SymbolResolver, MT5OrderRouter
)
from mars.apps.trading.system.vol_scaled_system import (
    RiskManager,
    VolScaledSizer,
    TradeConfig,
)


class TestManualModificationDetection:
    """Test suite for manual SL/TP modification detection and reconciliation."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures with mocked MT5."""
        # Create temp audit database
        self.tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.audit_db = self.tmp_db.name
        self.tmp_db.close()
        
        # Mock MT5 module
        self.mock_mt5 = MagicMock()
        self.mock_mt5.TRADE_RETCODE_DONE = 10009
        self.mock_mt5.TRADE_ACTION_DEAL = 1
        self.mock_mt5.TRADE_ACTION_SLTP = 2
        self.mock_mt5.ORDER_TYPE_BUY = 0
        self.mock_mt5.ORDER_TYPE_SELL = 1
        self.mock_mt5.ORDER_FILLING_FOK = 2
        self.mock_mt5.ORDER_TIME_GTC = 0
        self.mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        self.mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        self.mock_mt5.ORDER_TYPE_BUY_STOP = 4
        self.mock_mt5.ORDER_TYPE_SELL_STOP = 5
        
        # Patch MT5
        self.patcher = patch('mars.apps.trading.mt5_executor.mt5', self.mock_mt5)
        self.patcher.start()
        
        # Patch time.sleep to speed up tests
        patch3 = patch('time.sleep', lambda x: None)
        patch3.start()
        
        # Mock account info
        self.mock_mt5.account_info.return_value = Mock(
            login=476944496,
            balance=500.0,
            equity=500.0,
            margin=0.0,
            free_margin=500.0,
            margin_level=0.0,
            currency="USD",
            name="Demo Account",
            server="MetaQuotes-Demo",
            trade_mode=0,
            leverage=100,
            limit_orders=200,
            margin_so_mode=0,
            trade_allowed=True,
            trade_expert=True,
        )
        
        # Mock symbol info
        self.mock_mt5.symbol_info.return_value = Mock(
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            digits=2,
            spread=20,
            bid=4414.36,
            ask=4414.62,
            point_value=1.0,
            margin_initial=1000.0,
            margin_maintenance=500.0,
            session_volume_limit=0,
        )
        
        # Mock symbol_info_tick
        self.mock_mt5.symbol_info_tick.return_value = Mock(
            bid=4414.36,
            ask=4414.62,
            last=4414.49,
            volume=0,
            time=0,
            flags=0,
        )
        
        # Mock positions_get to return empty by default
        self.mock_mt5.positions_get.return_value = ()
        
        # Mock order_send success
        self.mock_mt5.order_send.return_value = Mock(
            retcode=10009,
            deal=123456789,
            order=987654321,
            volume=0.5,
            price=4414.36,
            comment="MARS_OPEN"
        )
        
        # Mock symbol_select
        self.mock_mt5.symbol_select.return_value = True
        
        # Mock orders_get
        self.mock_mt5.orders_get.return_value = ()
        
        # Mock history_deals_get
        self.mock_mt5.history_deals_get.return_value = ()
        
        # Create executor with temp audit DB
        self.executor = MT5Executor(
            equity=500.0,
            risk_manager=None,  # Will set after
            mt5_config=MT5Config(
                login=476944496,
                password="test_password",
                server="MetaQuotes-Demo",
                timeout=60000,
                portable=False,
            ),
            audit_db_path=self.audit_db,
        )
        
        # Create risk manager
        self.risk_manager = RiskManager(
            kill_switch_file=tempfile.NamedTemporaryFile(suffix='.txt', delete=False).name,
        )
        self.risk_manager.select_tier_for_equity(500.0)
        self.executor.risk_manager = self.risk_manager
        self.executor.equity = 500.0
        
        # Replace audit logger with one using our temp DB
        self.executor.audit_logger = MT5AuditLogger(db_path=self.audit_db)
        
        yield
        
        # Cleanup
        self.patcher.stop()
        patch3.stop()
        # Close audit logger to release WAL locks
        if hasattr(self.executor, 'audit_logger') and self.executor.audit_logger:
            self.executor.audit_logger.close()
        if os.path.exists(self.audit_db):
            try:
                os.unlink(self.audit_db)
            except PermissionError:
                pass  # Windows WAL mode may keep lock briefly
    
    def _create_mock_position(self, symbol="XAUUSDm", ticket=12345678, 
                              entry_price=4414.62, sl=4400.0, tp=4450.0,
                              volume=0.5, is_long=True, magic=123456):
        """Create a mock MT5 position object."""
        pos = Mock()
        pos.ticket = ticket
        pos.symbol = symbol
        pos.type = 0 if is_long else 1  # 0=buy, 1=sell
        pos.volume = volume
        pos.price_open = entry_price
        pos.sl = sl
        pos.tp = tp
        pos.price_current = entry_price
        pos.profit = 0.0
        pos.swap = 0.0
        pos.commission = 0.0
        pos.magic = magic
        pos.comment = "MARS_OPEN"
        pos.time = 0
        pos.time_update = 0
        pos.time_msc = 0
        pos.reason = 0
        pos.external_id = ""
        return pos
    
    def _add_test_position(self, symbol="XAUUSDm", ticket=12345678,
                           entry_price=4414.62, sl=4400.0, tp=4450.0,
                           position_size=0.01, is_long=True):
        """Add a test position to executor and risk manager."""
        import pandas as pd
        # Add to executor
        self.executor.open_positions[symbol] = {
            "mt5_ticket": ticket,
            "symbol": symbol,
            "entry_price": entry_price,
            "stop_price": sl,
            "take_profit": tp,
            "position_size": position_size,
            "is_long": is_long,
            "magic": 123456,
            "entry_time": pd.Timestamp.now(),
        }
        
        # Add to risk manager
        if is_long:
            risk_at_stop = (entry_price - sl) * position_size * 100  # $/pip * pips
        else:
            risk_at_stop = (sl - entry_price) * position_size * 100
        
        self.risk_manager.current_positions[symbol] = {
            "risk_at_stop": risk_at_stop,
            "entry_time": pd.Timestamp.now(),
            "is_min_lot_override": False,
        }
        self.risk_manager.total_open_risk = risk_at_stop
        
        # Set up mock position
        mock_pos = self._create_mock_position(
            symbol=symbol, ticket=ticket, entry_price=entry_price, sl=sl, tp=tp, 
            volume=position_size, is_long=is_long
        )
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        return mock_pos

    def test_detect_manual_sl_change_only(self):
        """Test detection of manual SL modification only."""
        self._add_test_position(sl=4400.0)
        
        # Mock MT5 returns position with different SL (tightened, risk REDUCED)
        # Old: (4414.62 - 4400) * 0.01 * 100 = $14.62 = 2.92%
        # New: (4414.62 - 4405) * 0.01 * 100 = $9.62 = 1.92% (under 3% cap)
        mock_pos = self._create_mock_position(sl=4405.0)  # Changed from 4400 to 4405 (tighter)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 1
        mod = modifications[0]
        assert mod["ticket"] == 12345678
        assert mod["symbol"] == "XAUUSDm"
        assert mod["old_sl"] == 4400.0
        assert mod["new_sl"] == 4405.0
        assert mod["old_tp"] == 4450.0
        assert mod["new_tp"] == 4450.0  # TP unchanged
        assert mod["exceeds_per_trade_cap"] is False
        assert mod["action_taken"] == "ALERT_ONLY"
    
    def test_detect_manual_tp_change_only(self):
        """Test detection of manual TP modification only."""
        self._add_test_position(tp=4450.0)
        
        # Mock MT5 returns position with different TP
        mock_pos = self._create_mock_position(tp=4460.0)  # Changed from 4450 to 4460
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 1
        mod = modifications[0]
        assert mod["old_tp"] == 4450.0
        assert mod["new_tp"] == 4460.0
        assert mod["old_sl"] == 4400.0
        assert mod["new_sl"] == 4400.0  # SL unchanged
    
    def test_detect_both_sl_tp_change(self):
        """Test detection of both SL and TP changes."""
        self._add_test_position(sl=4400.0, tp=4450.0)
        
        # Mock MT5 returns position with both changed
        mock_pos = self._create_mock_position(sl=4390.0, tp=4460.0)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 1
        mod = modifications[0]
        assert mod["old_sl"] == 4400.0
        assert mod["new_sl"] == 4390.0
        assert mod["old_tp"] == 4450.0
        assert mod["new_tp"] == 4460.0
    
    def test_no_detection_when_no_change(self):
        """Test no detection when SL/TP unchanged."""
        self._add_test_position(sl=4400.0, tp=4450.0)
        
        # Mock MT5 returns position with same SL/TP
        mock_pos = self._create_mock_position(sl=4400.0, tp=4450.0)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 0
    
    def test_no_detection_for_unknown_symbol(self):
        """Test no detection for positions not tracked by system."""
        # Mock MT5 returns a position we don't track
        mock_pos = self._create_mock_position(symbol="EURUSDm", ticket=99999999)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 0
    
    def test_no_detection_for_non_magic_positions(self):
        """Test no detection for positions without our magic number."""
        self._add_test_position()
        
        # Mock MT5 returns position with different magic number
        mock_pos = self._create_mock_position(magic=999999)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 0
    
    def test_reconciliation_alert_only(self):
        """Test reconciliation when risk is within caps (ALERT_ONLY)."""
        self._add_test_position(sl=4400.0)
        
        # Small SL change that stays under 3% cap
        # Old: (4414.62 - 4400.0) * 0.01 * 100 = $14.62 = 2.92%
        # New: (4414.62 - 4405.0) * 0.01 * 100 = $9.62 = 1.92%
        mock_pos = self._create_mock_position(sl=4405.0)  # ~$9.62 risk = 1.92%
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        self.executor._reconcile_manual_modifications(modifications)
        
        # Verify internal tracking updated
        assert self.executor.open_positions["XAUUSDm"]["stop_price"] == 4405.0
        
        # Verify risk manager updated
        assert abs(self.risk_manager.total_open_risk - 9.62) < 0.1
        assert abs(self.risk_manager.current_positions["XAUUSDm"]["risk_at_stop"] - 9.62) < 0.1
        
        # Verify audit log
        conn = sqlite3.connect(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manual_modifications")
        mods = cursor.fetchall()
        conn.close()
        
        assert len(mods) == 1
        # manual_modifications columns: 0=id, 1=timestamp, 2=ticket, 3=symbol, 4=old_sl, 5=new_sl, 6=old_tp, 7=new_tp,
        # 8=old_risk_usd, 9=new_risk_usd, 10=old_risk_pct, 11=new_risk_pct,
        # 12=tier_risk_cap_pct, 13=aggregate_cap_pct, 14=total_open_risk_before,
        # 15=total_open_risk_after, 16=exceeds_per_trade_cap, 17=exceeds_aggregate_cap,
        # 18=action_taken, 19=equity, 20=kill_switch_active
        assert mods[0][18] == "ALERT_ONLY"  # action_taken at index 18
    
    def test_reconciliation_auto_close_over_per_trade_cap(self):
        """Test auto-close when manual SL change exceeds per-trade risk cap."""
        # Position with 2.92% risk (SL at 4400 = $14.62 = 2.92%)
        self._add_test_position(sl=4400.0)
        
        # Manual change to wider SL = 4399
        # Risk: (4414.62 - 4399) * 0.01 * 100 = 15.62 * 1 = $15.62 = 3.12% > 3% cap
        mock_pos = self._create_mock_position(sl=4399.0)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        # Mock close order success
        self.mock_mt5.order_send.return_value = Mock(
            retcode=10009, deal=123456789, order=987654321,
            volume=0.01, price=4414.36, comment="MARS_CLOSE_manual_mod_over_cap"
        )
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        # Should detect over cap
        assert len(modifications) == 1
        assert modifications[0]["exceeds_per_trade_cap"] is True
        assert modifications[0]["action_taken"] == "AUTO_CLOSE_POSITION"
        
        # Run reconciliation
        self.executor._reconcile_manual_modifications(modifications)
        
        # Position should be closed (removed from open_positions)
        assert "XAUUSDm" not in self.executor.open_positions
        
        # Risk should be removed from risk manager
        assert self.risk_manager.total_open_risk == 0
        
        # Verify audit log
        conn = sqlite3.connect(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manual_modifications")
        mods = cursor.fetchall()
        conn.close()
        
        assert len(mods) == 1
        # action_taken at index 18
        assert mods[0][18] == "AUTO_CLOSE_POSITION"
    
    def test_reconciliation_auto_close_over_aggregate_cap(self):
        """Test auto-close when manual SL change exceeds aggregate concurrent risk cap (3%)."""
        # Add first position at 1.5% risk ($7.50) - SL at 4407.12 = (4414.62-4407.12)*0.01*100 = $7.50
        self._add_test_position(symbol="XAUUSDm", ticket=11111111, sl=4407.12)
        pos1_risk = 7.50
        
        # Add second position at 1.5% risk ($7.50) - total = 3.0% ($15.00) = exactly at 3% aggregate cap
        self._add_test_position(symbol="EURUSDm", ticket=22222222, sl=4407.12)
        pos2_risk = 7.50
        
        # Total risk = $15.00 = 3.0% (exactly at 3% aggregate cap)
        # Need to manually set risk manager since _add_test_position overwrites total_open_risk
        self.risk_manager.current_positions["XAUUSDm"]["risk_at_stop"] = pos1_risk
        self.risk_manager.current_positions["EURUSDm"] = {
            "risk_at_stop": pos2_risk,
            "entry_time": pd.Timestamp.now(),
            "is_min_lot_override": False,
        }
        self.risk_manager.total_open_risk = pos1_risk + pos2_risk  # $15.00
        
        # Set up mocks for both positions
        mock_pos1 = self._create_mock_position(symbol="XAUUSDm", ticket=11111111, sl=4407.12)
        mock_pos2 = self._create_mock_position(symbol="EURUSDm", ticket=22222222, sl=4407.12)
        self.mock_mt5.positions_get.return_value = (mock_pos1, mock_pos2)
        
        # Now modify first position SL wider to push aggregate over 3% cap
        # Change XAUUSDm (11111111) to SL 4402.12 = $12.50 (2.5%)
        # New total = 12.50 + 7.50 = $20.00 = 4.0% > 3% cap
        mock_pos1_modified = self._create_mock_position(symbol="XAUUSDm", ticket=11111111, sl=4402.12)
        self.mock_mt5.positions_get.return_value = (mock_pos1_modified, mock_pos2)
        
        # Update executor positions (old tracked SL)
        self.executor.open_positions["XAUUSDm"]["stop_price"] = 4407.12
        
        self.mock_mt5.order_send.return_value = Mock(
            retcode=10009, deal=123456789, order=987654321,
            volume=0.01, price=4414.36, comment="MARS_CLOSE_manual_mod_over_cap"
        )
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        # Should detect aggregate over cap
        assert len(modifications) == 1
        mod = modifications[0]
        assert mod["exceeds_aggregate_cap"] is True
        assert mod["action_taken"] == "AUTO_CLOSE_POSITION"
        
        # Run reconciliation
        self.executor._reconcile_manual_modifications(modifications)
        
        # Position should be closed
        assert "XAUUSDm" not in self.executor.open_positions
        
        # Verify audit log
        conn = sqlite3.connect(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manual_modifications")
        mods = cursor.fetchall()
        conn.close()
        
        assert len(mods) == 1
        assert mods[0][18] == "AUTO_CLOSE_POSITION"
    
    def test_reconciliation_logs_to_manual_modifications_table(self):
        """Test that reconciliation logs to manual_modifications table with all fields."""
        self._add_test_position(sl=4400.0, tp=4450.0)
        
        # Small change that stays under 3% cap (ALERT_ONLY)
        mock_pos = self._create_mock_position(sl=4405.0, tp=4460.0)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        self.executor._reconcile_manual_modifications(modifications)
        
        conn = sqlite3.connect(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manual_modifications")
        mods = cursor.fetchall()
        conn.close()
        
        assert len(mods) == 1
        mod = mods[0]
        
        # Check all fields are populated (by index)
        # 0=id, 1=timestamp, 2=ticket, 3=symbol, 4=old_sl, 5=new_sl, 6=old_tp, 7=new_tp,
        # 8=old_risk_usd, 9=new_risk_usd, 10=old_risk_pct, 11=new_risk_pct,
        # 12=tier_risk_cap_pct, 13=aggregate_cap_pct, 14=total_open_risk_before,
        # 15=total_open_risk_after, 16=exceeds_per_trade_cap, 17=exceeds_aggregate_cap,
        # 18=action_taken, 19=equity, 20=kill_switch_active
        assert mod[2] == 12345678  # ticket
        assert mod[3] == "XAUUSDm"  # symbol
        assert mod[4] == 4400.0  # old_sl
        assert mod[5] == 4405.0  # new_sl
        assert mod[6] == 4450.0  # old_tp
        assert mod[7] == 4460.0  # new_tp
        assert mod[16] == 0  # exceeds_per_trade_cap (stored as int)
        assert mod[17] == 0  # exceeds_aggregate_cap (stored as int)
        assert mod[18] == "ALERT_ONLY"  # action_taken
    
    def test_reconciliation_also_logs_to_risk_events(self):
        """Test that reconciliation also logs MANUAL_MODIFICATION_DETECTED to risk_events."""
        self._add_test_position(sl=4400.0)
        
        mock_pos = self._create_mock_position(sl=4390.0)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        self.executor._reconcile_manual_modifications(modifications)
        
        conn = sqlite3.connect(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM risk_events WHERE event_type = 'MANUAL_MODIFICATION_DETECTED'")
        events = cursor.fetchall()
        conn.close()
        
        assert len(events) == 1
        # risk_events columns: 0=id, 1=timestamp, 2=event_type, 3=details, 4=equity, 5=drawdown_pct, 6=daily_pnl, 7=kill_switch_active
        assert events[0][2] == "MANUAL_MODIFICATION_DETECTED"
        assert "ticket=12345678" in events[0][3]  # details at index 3
    
    def test_detection_in_poll_cycle(self):
        """Test that detection runs within poll cycle."""
        self._add_test_position(sl=4400.0)
        
        # Simulate a polling cycle
        mock_pos = self._create_mock_position(sl=4390.0)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        # Call the internal detection method directly
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        # Should detect within one cycle
        assert len(modifications) == 1
        assert modifications[0]["old_sl"] == 4400.0
        assert modifications[0]["new_sl"] == 4390.0
    
    def test_multiple_modifications_detected_in_one_cycle(self):
        """Test multiple manual modifications detected in single polling cycle."""
        # Add two positions
        self._add_test_position(symbol="XAUUSDm", ticket=11111111, sl=4400.0)
        
        # Add second position
        self.executor.open_positions["EURUSDm"] = {
            "ticket": 22222222,
            "symbol": "EURUSDm",
            "entry_price": 1.0850,
            "stop_price": 1.0800,
            "take_profit": 1.0950,
            "position_size": 1.0,
            "is_long": True,
            "magic": 123456,
        }
        
        mock_pos1 = self._create_mock_position(symbol="XAUUSDm", ticket=11111111, sl=4390.0)
        mock_pos2 = self._create_mock_position(symbol="EURUSDm", ticket=22222222, sl=1.0790)
        self.mock_mt5.positions_get.return_value = (mock_pos1, mock_pos2)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 2
        symbols = {m["symbol"] for m in modifications}
        assert symbols == {"XAUUSDm", "EURUSDm"}
    
    def test_short_position_sl_calculation(self):
        """Test SL risk calculation for short positions."""
        self._add_test_position(symbol="XAUUSDm", ticket=11111111, 
                               entry_price=4414.62, sl=4430.0, tp=4380.0,
                               position_size=0.5, is_long=False)
        
        # For short: risk = (sl - entry) * size * 100
        # Old: (4430.0 - 4414.62) * 0.5 * 100 = 15.38 * 50 = $769
        # New: (4440.0 - 4414.62) * 0.5 * 100 = 25.38 * 50 = $1269
        mock_pos = self._create_mock_position(symbol="XAUUSDm", ticket=11111111,
                                              entry_price=4414.62, sl=4440.0, tp=4380.0,
                                              volume=0.5, is_long=False)
        self.mock_mt5.positions_get.return_value = (mock_pos,)
        
        modifications = self.executor._detect_manual_sl_tp_changes()
        
        assert len(modifications) == 1
        mod = modifications[0]
        assert mod["old_risk_usd"] == pytest.approx(769.0, abs=1)
        assert mod["new_risk_usd"] == pytest.approx(1269.0, abs=1)


class TestManualModificationAuditLogger:
    """Test the audit logger manual modifications table."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.audit_db = self.tmp_db.name
        self.tmp_db.close()
        
        self.logger = MT5AuditLogger(db_path=self.audit_db)
        
        yield
        
        # Force close any open connections on Windows
        import sqlite3
        try:
            conn = sqlite3.connect(self.audit_db)
            conn.close()
        except:
            pass
        if os.path.exists(self.audit_db):
            try:
                os.unlink(self.audit_db)
            except PermissionError:
                pass  # Windows may still hold a lock
    
    def test_manual_modifications_table_created(self):
        """Test that manual_modifications table is created on init."""
        conn = sqlite3.connect(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='manual_modifications'")
        table = cursor.fetchone()
        conn.close()
        
        assert table is not None
    
    def test_log_manual_modification(self):
        """Test logging a manual modification event."""
        self.logger.log_manual_modification(
            ticket=12345678,
            symbol="XAUUSDm",
            old_sl=4400.0,
            new_sl=4390.0,
            old_tp=4450.0,
            new_tp=4460.0,
            old_risk_usd=14.62,
            new_risk_usd=24.62,
            old_risk_pct=0.02924,
            new_risk_pct=0.04924,
            tier_risk_cap_pct=0.03,
            aggregate_cap_pct=0.03,
            total_open_risk_before=14.62,
            total_open_risk_after=24.62,
            exceeds_per_trade_cap=False,
            exceeds_aggregate_cap=False,
            action_taken="ALERT_ONLY",
            equity=500.0,
            kill_switch_active=False,
        )
        
        conn = sqlite3.connect(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manual_modifications")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        row = rows[0]
        assert row[2] == 12345678  # ticket
        assert row[3] == "XAUUSDm"  # symbol
        assert row[4] == 4400.0  # old_sl
        assert row[5] == 4390.0  # new_sl
        assert row[18] == "ALERT_ONLY"  # action_taken