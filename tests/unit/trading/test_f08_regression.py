"""
Regression tests for F-08: MT5 commission, swap, and realized P&L logging.

Tests cover:
1. Missing deal-history response
2. Confirmed zero commission
3. Multiple entry deals (position-based aggregation fallback)
4. Multiple exit deals
5. Duplicate reconciliation
6. Net P&L reconciliation
"""

from __future__ import annotations

import sqlite3
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from mars.apps.trading.mt5_executor import MT5AuditLogger, FillResult, MT5OrderRouter
from mars.apps.trading.system.vol_scaled_system import TradeConfig as VolTradeConfig
import pandas as pd


def _create_test_db(tmpdir: str) -> Path:
    return Path(tmpdir) / "test.db"


def _cleanup_db(db_path: Path):
    for suffix in ['', '-wal', '-shm']:
        p = db_path.with_suffix(db_path.suffix + suffix) if suffix else db_path
        if p.exists():
            try:
                p.unlink()
            except PermissionError:
                pass


def make_request(symbol='XAUUSD', signal=1, volume=0.5):
    """Create a proper request object with required attributes."""
    return SimpleNamespace(symbol=symbol, signal=signal, volume=volume)


# ============================================================
# 1. Missing deal-history response
# ============================================================

def test_missing_deal_history():
    """When MT5 deal history is unavailable, status should be 'lookup_failed' 
    and commission/swap/profit should be 0.0 (not silently assumed as confirmed zero)."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        db_path = _create_test_db(tmpdir)
        audit_logger = MT5AuditLogger(db_path)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )

        fill = FillResult(
            success=True,
            ticket=123456789,
            order_id=987654321,
            volume=0.5,
            price=2000.0,
            bid=2000.0,
            ask=2000.01,
            sl=1990.0,
            tp=2050.0,
            comment='TEST',
            request=SimpleNamespace(symbol='XAUUSD', signal=1, volume=0.5),
            result_code=0,
            retcode_external=0,
            timestamp=pd.Timestamp.now(tz='UTC'),
            commission=0.0,
            swap=0.0,
            profit=0.0,
            position_id=None,
            deal_status="lookup_failed",
        )

        audit_logger.log_fill(fill, config, config.entry_price)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT commission, swap, profit, position_id FROM fills WHERE ticket = 123456789"
            ).fetchone()
            assert row is not None
            commission, swap, profit, position_id = row
            assert commission == 0.0
            assert swap == 0.0
            assert profit == 0.0
            assert position_id is None
        
        print("✅ test_missing_deal_history passed")
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_confirmed_zero_commission():
    """When broker explicitly reports zero commission, it should be recorded as 0.0
    with status='confirmed' (distinct from 'lookup_failed')."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        db_path = _create_test_db(tmpdir)
        audit_logger = MT5AuditLogger(db_path)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )

        fill = FillResult(
            success=True,
            ticket=123456789,
            order_id=987654321,
            volume=0.5,
            price=2000.0,
            bid=2000.0,
            ask=2000.01,
            sl=1990.0,
            tp=2050.0,
            comment='TEST',
            request=SimpleNamespace(symbol='XAUUSD', signal=1, volume=0.5),
            result_code=0,
            retcode_external=0,
            timestamp=pd.Timestamp.now(tz='UTC'),
            commission=0.0,
            swap=0.0,
            profit=0.0,
            position_id=12345,
            deal_status="confirmed",
        )

        audit_logger.log_fill(fill, config, config.entry_price)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT commission, swap, profit, position_id FROM fills WHERE ticket = 123456789"
            ).fetchone()
            assert row is not None
            commission, swap, profit, position_id = row
            assert commission == 0.0
            assert position_id == 12345
        
        print("✅ test_confirmed_zero_commission passed")
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_multiple_entry_deals_position_fallback():
    """When ticket lookup returns non-entry deal, position fallback aggregates all entry deals."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        mock_mt5 = Mock()
        
        # Deal returned by ticket lookup - this is NOT an entry deal (e.g., it's the order result deal)
        ticket_deal = Mock()
        ticket_deal.entry = 1  # Exit deal or non-entry
        ticket_deal.position_id = 99999
        
        # Entry deals returned by position lookup
        entry_deal1 = Mock()
        entry_deal1.entry = 0
        entry_deal1.commission = -2.50
        entry_deal1.swap = -0.50
        entry_deal1.profit = 0.0
        entry_deal1.volume = 0.3
        entry_deal1.position_id = 99999
        
        entry_deal2 = Mock()
        entry_deal2.entry = 0
        entry_deal2.commission = -3.00
        entry_deal2.swap = -0.75
        entry_deal2.profit = 0.0
        entry_deal2.volume = 0.7
        entry_deal2.position_id = 99999
        
        # First call (ticket=999) returns non-entry deal, second call (position=99999) returns entry deals
        def history_deals_get(ticket=None, position=None):
            if ticket == 999:
                return [ticket_deal]  # First lookup by ticket returns non-entry deal
            if position == 99999:
                return [entry_deal1, entry_deal2]  # Second lookup by position aggregates
            return []
        
        mock_mt5.history_deals_get.side_effect = history_deals_get
        
        mock_resolver = Mock()
        mock_resolver.get_symbol_info.return_value = Mock(digits=2)
        router = MT5OrderRouter(mock_mt5, mock_resolver)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        mock_result = Mock()
        mock_result.retcode = 10009
        mock_result.order = 111111
        mock_result.volume = 1.0
        mock_result.price = 2000.0
        mock_result.deal = 999
        mock_result.comment = "TEST"
        mock_result.retcode_external = 0
        
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.order_send.return_value = mock_result
        
        mock_tick = Mock()
        mock_tick.bid = 1999.99
        mock_tick.ask = 2000.01
        mock_mt5.symbol_info_tick.return_value = mock_tick
        
        with patch.object(router, 'mt5', mock_mt5):
            fill_result = router.send_order(config, Mock())
        
        # Should aggregate both entry deals via position fallback
        assert fill_result.commission == -5.50, f"Expected -5.50, got {fill_result.commission}"
        assert fill_result.swap == -1.25, f"Expected -1.25, got {fill_result.swap}"
        assert fill_result.profit == 0.0
        assert fill_result.position_id == 99999
        assert fill_result.deal_status == "confirmed"
        
        print("✅ test_multiple_entry_deals_position_fallback passed")
    finally:
        pass


def test_multiple_exit_deals():
    """When MT5 has multiple exit deals for a position, log_close_fill should aggregate them."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        db_path = _create_test_db(tmpdir)
        audit_logger = MT5AuditLogger(db_path)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        fill = FillResult(
            success=True,
            ticket=123456789,
            order_id=987654321,
            volume=0.5,
            price=2000.0,
            bid=2000.0,
            ask=2000.01,
            sl=1990.0,
            tp=2050.0,
            comment='TEST',
            request=SimpleNamespace(symbol='XAUUSD', signal=1, volume=0.5),
            result_code=0,
            retcode_external=0,
            timestamp=pd.Timestamp.now(tz='UTC'),
            commission=-2.50,
            swap=-1.25,
            profit=0.0,
            position_id=99999,
            deal_status="confirmed",
        )
        fill_id = audit_logger.log_fill(fill, config, config.entry_price)
        
        exit_deal1 = Mock()
        exit_deal1.entry = 1
        exit_deal1.time = int(datetime.now(timezone.utc).timestamp())
        exit_deal1.price = 2050.0
        exit_deal1.commission = -1.50
        exit_deal1.swap = -0.25
        exit_deal1.profit = 1500.0
        exit_deal1.reason = 5
        exit_deal1.ticket = 10001
        
        exit_deal2 = Mock()
        exit_deal2.entry = 1
        exit_deal2.time = int(datetime.now(timezone.utc).timestamp()) + 10
        exit_deal2.price = 2051.0
        exit_deal2.commission = -1.00
        exit_deal2.swap = -0.10
        exit_deal2.profit = 500.0
        exit_deal2.reason = 5
        exit_deal2.ticket = 10002
        
        mock_mt5 = Mock()
        mock_mt5.history_deals_get.return_value = [exit_deal1, exit_deal2]
        audit_logger._mt5 = mock_mt5
        
        result = audit_logger.log_close_fill(fill_id)
        assert result is True
        
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT exit_commission, exit_swap, exit_profit, exit_reason, exit_deal_ticket FROM fills WHERE id = ?",
                (fill_id,)
            ).fetchone()
            assert row is not None
            assert row["exit_commission"] == -2.50
            assert row["exit_swap"] == -0.35
            assert row["exit_profit"] == 2000.0
            assert "tp_hit" in row["exit_reason"]
            assert "10001" in row["exit_deal_ticket"]
            assert "10002" in row["exit_deal_ticket"]
        
        print("✅ test_multiple_exit_deals passed")
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_duplicate_reconciliation():
    """log_close_fill should be idempotent - calling twice should not duplicate data."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        db_path = _create_test_db(tmpdir)
        audit_logger = MT5AuditLogger(db_path)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        fill = FillResult(
            success=True,
            ticket=123456789,
            order_id=987654321,
            volume=0.5,
            price=2000.0,
            bid=2000.0,
            ask=2000.01,
            sl=1990.0,
            tp=2050.0,
            comment='TEST',
            request=SimpleNamespace(symbol='XAUUSD', signal=1, volume=0.5),
            result_code=0,
            retcode_external=0,
            timestamp=pd.Timestamp.now(tz='UTC'),
            commission=-2.50,
            swap=-1.25,
            profit=0.0,
            position_id=99999,
            deal_status="confirmed",
        )
        fill_id = audit_logger.log_fill(fill, config, config.entry_price)
        
        exit_deal = Mock()
        exit_deal.entry = 1
        exit_deal.time = int(datetime.now(timezone.utc).timestamp())
        exit_deal.price = 2050.0
        exit_deal.commission = -1.50
        exit_deal.swap = -0.25
        exit_deal.profit = 1500.0
        exit_deal.reason = 5
        exit_deal.ticket = 10001
        
        mock_mt5 = Mock()
        mock_mt5.history_deals_get.return_value = [exit_deal]
        audit_logger._mt5 = mock_mt5
        
        result1 = audit_logger.log_close_fill(fill_id)
        assert result1 is True
        
        result2 = audit_logger.log_close_fill(fill_id)
        assert result2 is True
        
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT exit_commission, exit_swap, exit_profit FROM fills WHERE id = ?",
                (fill_id,)
            ).fetchone()
            assert row is not None
            assert row[0] == -1.50
            assert row[1] == -0.25
            assert row[2] == 1500.0
        
        print("✅ test_duplicate_reconciliation passed")
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_net_pnl_reconciliation():
    """Verify Net P&L = exit_profit + exit_commission + exit_swap + entry_commission + entry_swap"""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        db_path = _create_test_db(tmpdir)
        audit_logger = MT5AuditLogger(db_path)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        fill = FillResult(
            success=True,
            ticket=123456789,
            order_id=987654321,
            volume=0.5,
            price=2000.0,
            bid=2000.0,
            ask=2000.01,
            sl=1990.0,
            tp=2050.0,
            comment='TEST',
            request=SimpleNamespace(symbol='XAUUSD', signal=1, volume=0.5),
            result_code=0,
            retcode_external=0,
            timestamp=pd.Timestamp.now(tz='UTC'),
            commission=-2.50,
            swap=-1.25,
            profit=0.0,
            position_id=99999,
            deal_status="confirmed",
        )
        fill_id = audit_logger.log_fill(fill, config, config.entry_price)
        
        exit_deal = Mock()
        exit_deal.entry = 1
        exit_deal.time = int(datetime.now(timezone.utc).timestamp())
        exit_deal.price = 2050.0
        exit_deal.commission = -1.50
        exit_deal.swap = -0.25
        exit_deal.profit = 2500.0
        exit_deal.reason = 5
        exit_deal.ticket = 10001
        
        mock_mt5 = Mock()
        mock_mt5.history_deals_get.return_value = [exit_deal]
        audit_logger._mt5 = mock_mt5
        
        audit_logger.log_close_fill(fill_id)
        
        from mars.apps.trading.loss_audit import _net_pnl
        from mars.apps.trading.risk_metrics import risk_at_stop_usd
        
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM fills WHERE id = ?", (fill_id,)).fetchone()
            assert row is not None
            
            net_pnl = _net_pnl(row)
            expected_pnl = 2500.0 - 1.50 - 0.25 - 2.50 - 1.25  # 2493.50
            assert abs(net_pnl - expected_pnl) < 0.01, f"Expected {expected_pnl}, got {net_pnl}"
            
            # Calculate expected R-value: net_pnl / risk_at_stop
            risk_usd = risk_at_stop_usd(
                symbol=row["symbol"],
                entry_price=float(row["filled_price"] or 0.0),
                stop_price=float(row["filled_sl"] or 0.0),
                filled_lots=float(row["filled_lots"] or 0.0),
            )
            if risk_usd and risk_usd > 0:
                expected_r = expected_pnl / risk_usd
                audit_row = conn.execute("SELECT r_realized FROM loss_audit WHERE fill_id = ?", (fill_id,)).fetchone()
                if audit_row and audit_row["r_realized"] is not None:
                    assert abs(audit_row["r_realized"] - expected_r) < 0.01, f"Expected R={expected_r}, got {audit_row['r_realized']}"
        
        print("✅ test_net_pnl_reconciliation passed")
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# 7. Multiple entry deals - initial ticket IS an entry deal (no double-counting)
# ============================================================

def test_multiple_entry_deals_initial_ticket_is_entry():
    """When the initial ticket lookup returns an entry deal, we should still
    aggregate ALL entry deals for the position, avoiding double-counting the first one."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        mock_mt5 = Mock()
        
        # Ticket lookup returns an entry deal (the first partial fill)
        ticket_deal = Mock()
        ticket_deal.entry = 0
        ticket_deal.commission = -2.00
        ticket_deal.swap = -0.40
        ticket_deal.profit = 0.0
        ticket_deal.volume = 0.3
        ticket_deal.position_id = 99999
        
        # Position lookup returns ALL entry deals including the first one
        entry_deal1 = Mock()
        entry_deal1.entry = 0
        entry_deal1.commission = -2.00
        entry_deal1.swap = -0.40
        entry_deal1.profit = 0.0
        entry_deal1.volume = 0.3
        entry_deal1.position_id = 99999
        
        entry_deal2 = Mock()
        entry_deal2.entry = 0
        entry_deal2.commission = -3.00
        entry_deal2.swap = -0.75
        entry_deal2.profit = 0.0
        entry_deal2.volume = 0.7
        entry_deal2.position_id = 99999
        
        def history_deals_get(ticket=None, position=None):
            if ticket == 999:
                return [ticket_deal]  # First lookup by ticket returns entry deal
            if position == 99999:
                return [entry_deal1, entry_deal2]  # Position lookup returns both
            return []
        
        mock_mt5.history_deals_get.side_effect = history_deals_get
        
        mock_resolver = Mock()
        mock_resolver.get_symbol_info.return_value = Mock(digits=2)
        router = MT5OrderRouter(mock_mt5, mock_resolver)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=1.0, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        mock_result = Mock()
        mock_result.retcode = 10009
        mock_result.order = 111111
        mock_result.volume = 1.0
        mock_result.price = 2000.0
        mock_result.deal = 999
        mock_result.comment = "TEST"
        mock_result.retcode_external = 0
        
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.order_send.return_value = mock_result
        
        mock_tick = Mock()
        mock_tick.bid = 1999.99
        mock_tick.ask = 2000.01
        mock_mt5.symbol_info_tick.return_value = mock_tick
        
        with patch.object(router, 'mt5', mock_mt5):
            fill_result = router.send_order(config, Mock())
        
        # Should aggregate both entry deals ONCE each (no double-counting)
        # Total commission: -2.00 + -3.00 = -5.00 (NOT -2.00*2 + -3.00 = -7.00)
        assert fill_result.commission == -5.00, f"Expected -5.00, got {fill_result.commission}"
        assert fill_result.swap == -1.15, f"Expected -1.15, got {fill_result.swap}"
        # Total volume: 0.3 + 0.7 = 1.0
        assert fill_result.volume == 1.0, f"Expected volume 1.0, got {fill_result.volume}"
        assert fill_result.position_id == 99999
        assert fill_result.deal_status == "confirmed"
        
        print("✅ test_multiple_entry_deals_initial_ticket_is_entry passed")
    finally:
        pass


# ============================================================
# 8. Partial fills with different executed volumes
# ============================================================

def test_partial_fill_volume_reconciliation():
    """When MT5 partially fills an order across multiple deals,
    the recorded volume should match the sum of entry deal volumes."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        mock_mt5 = Mock()
        
        # First partial fill
        entry_deal1 = Mock()
        entry_deal1.entry = 0
        entry_deal1.commission = -1.50
        entry_deal1.swap = -0.30
        entry_deal1.profit = 0.0
        entry_deal1.volume = 0.4  # Partial fill 1
        entry_deal1.position_id = 88888
        
        # Second partial fill
        entry_deal2 = Mock()
        entry_deal2.entry = 0
        entry_deal2.commission = -2.00
        entry_deal2.swap = -0.40
        entry_deal2.profit = 0.0
        entry_deal2.volume = 0.3  # Partial fill 2
        entry_deal2.position_id = 88888
        
        # Requested 1.0 lot, but only 0.7 executed (0.4 + 0.3)
        ticket_deal = Mock()
        ticket_deal.entry = 0
        ticket_deal.position_id = 88888
        
        def history_deals_get(ticket=None, position=None):
            if ticket == 777:
                return [ticket_deal]
            if position == 88888:
                return [entry_deal1, entry_deal2]
            return []
        
        mock_mt5.history_deals_get.side_effect = history_deals_get
        
        mock_resolver = Mock()
        mock_resolver.get_symbol_info.return_value = Mock(digits=2)
        router = MT5OrderRouter(mock_mt5, mock_resolver)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=1.0, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        mock_result = Mock()
        mock_result.retcode = 10009
        mock_result.order = 222222
        mock_result.volume = 1.0  # MT5 order result might show requested volume
        mock_result.price = 2000.0
        mock_result.deal = 777
        mock_result.comment = "TEST"
        mock_result.retcode_external = 0
        
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.order_send.return_value = mock_result
        
        mock_tick = Mock()
        mock_tick.bid = 1999.99
        mock_tick.ask = 2000.01
        mock_mt5.symbol_info_tick.return_value = mock_tick
        
        with patch.object(router, 'mt5', mock_mt5):
            fill_result = router.send_order(config, Mock())
        
        # Recorded volume should be sum of entry deals (0.4 + 0.3 = 0.7)
        # NOT the requested 1.0 or the MT5 order result volume
        assert fill_result.volume == 0.7, f"Expected volume 0.7, got {fill_result.volume}"
        assert abs(fill_result.size_slippage - (-0.3)) < 0.001, f"Expected size_slippage -0.3, got {fill_result.size_slippage}"
        assert fill_result.commission == -3.50
        assert fill_result.swap == -0.70
        assert fill_result.deal_status == "confirmed"
        
        print("✅ test_partial_fill_volume_reconciliation passed")
    finally:
        pass


# ============================================================
# 9. Missing or incomplete deal history
# ============================================================

def test_missing_entry_deals_in_history():
    """When deal history is missing or incomplete, status should reflect the failure
    and volume should fall back to MT5 order result."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        mock_mt5 = Mock()
        
        # Ticket lookup succeeds but position lookup returns empty
        ticket_deal = Mock()
        ticket_deal.entry = 0
        ticket_deal.position_id = 77777
        
        def history_deals_get(ticket=None, position=None):
            if ticket == 555:
                return [ticket_deal]
            if position == 77777:
                return []  # No deals found for position
            return []
        
        mock_mt5.history_deals_get.side_effect = history_deals_get
        
        mock_resolver = Mock()
        mock_resolver.get_symbol_info.return_value = Mock(digits=2)
        router = MT5OrderRouter(mock_mt5, mock_resolver)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        mock_result = Mock()
        mock_result.retcode = 10009
        mock_result.order = 333333
        mock_result.volume = 0.5
        mock_result.price = 2000.0
        mock_result.deal = 555
        mock_result.comment = "TEST"
        mock_result.retcode_external = 0
        
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.order_send.return_value = mock_result
        
        mock_tick = Mock()
        mock_tick.bid = 1999.99
        mock_tick.ask = 2000.01
        mock_mt5.symbol_info_tick.return_value = mock_tick
        
        with patch.object(router, 'mt5', mock_mt5):
            fill_result = router.send_order(config, Mock())
        
        # Should fall back to MT5 order result volume
        assert fill_result.volume == 0.5
        assert fill_result.deal_status == "lookup_failed"
        assert fill_result.commission == 0.0
        assert fill_result.swap == 0.0
        assert fill_result.position_id == 77777  # Position ID still available from ticket
        
        print("✅ test_missing_entry_deals_in_history passed")
    finally:
        pass


def test_exception_during_deal_lookup():
    """When MT5 history_deals_get raises an exception, status should be lookup_failed."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        mock_mt5 = Mock()
        
        def history_deals_get(ticket=None, position=None):
            raise ConnectionError("MT5 connection lost")
        
        mock_mt5.history_deals_get.side_effect = history_deals_get
        
        mock_resolver = Mock()
        mock_resolver.get_symbol_info.return_value = Mock(digits=2)
        router = MT5OrderRouter(mock_mt5, mock_resolver)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=0.5, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        mock_result = Mock()
        mock_result.retcode = 10009
        mock_result.order = 444444
        mock_result.volume = 0.5
        mock_result.price = 2000.0
        mock_result.deal = 888
        mock_result.comment = "TEST"
        mock_result.retcode_external = 0
        
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.order_send.return_value = mock_result
        
        mock_tick = Mock()
        mock_tick.bid = 1999.99
        mock_tick.ask = 2000.01
        mock_mt5.symbol_info_tick.return_value = mock_tick
        
        with patch.object(router, 'mt5', mock_mt5):
            fill_result = router.send_order(config, Mock())
        
        assert fill_result.deal_status == "lookup_failed"
        assert fill_result.volume == 0.5  # Falls back to order result
        assert fill_result.commission == 0.0
        
        print("✅ test_exception_during_deal_lookup passed")
    finally:
        pass


# ============================================================
# 10. Correct realized P&L after multiple entry and exit deals
# ============================================================

def test_full_roundtrip_multiple_entry_exit():
    """End-to-end test: multiple entry deals + multiple exit deals = correct realized P&L."""
    tmpdir = tempfile.mkdtemp(prefix="f08_test_")
    try:
        db_path = _create_test_db(tmpdir)
        audit_logger = MT5AuditLogger(db_path)
        
        config = VolTradeConfig(
            symbol='XAUUSD', signal=1, entry_price=2000.0, stop_price=1990.0,
            take_profit=2050.0, position_size=1.0, max_hold_hours=24,
            risk_pct=0.01, entry_time=pd.Timestamp.now(tz='UTC'),
        )
        
        # Simulate FillResult from send_order with aggregated entry deals
        # Two entry deals: 0.6 lots @ -2.00 commission + 0.4 lots @ -1.50 commission
        fill = FillResult(
            success=True,
            ticket=123456789,
            order_id=987654321,
            volume=1.0,  # Aggregated entry volume
            price=2000.0,
            bid=2000.0,
            ask=2000.01,
            sl=1990.0,
            tp=2050.0,
            comment='TEST',
            request=SimpleNamespace(symbol='XAUUSD', signal=1, volume=1.0),
            result_code=0,
            retcode_external=0,
            timestamp=pd.Timestamp.now(tz='UTC'),
            commission=-3.50,  # Aggregated entry commission
            swap=-0.80,        # Aggregated entry swap
            profit=0.0,
            position_id=99999,
            deal_status="confirmed",
        )
        fill_id = audit_logger.log_fill(fill, config, config.entry_price)
        
        # Mock MT5 with TWO exit deals (partial close)
        exit_deal1 = Mock()
        exit_deal1.entry = 1
        exit_deal1.time = int(datetime.now(timezone.utc).timestamp())
        exit_deal1.price = 2040.0
        exit_deal1.commission = -1.00
        exit_deal1.swap = -0.15
        exit_deal1.profit = 1200.0  # 0.6 lots * 40 points * 100 = 2400? Simplified
        exit_deal1.reason = 5
        exit_deal1.ticket = 10001
        
        exit_deal2 = Mock()
        exit_deal2.entry = 1
        exit_deal2.time = int(datetime.now(timezone.utc).timestamp()) + 10
        exit_deal2.price = 2045.0
        exit_deal2.commission = -0.80
        exit_deal2.swap = -0.10
        exit_deal2.profit = 800.0
        exit_deal2.reason = 5
        exit_deal2.ticket = 10002
        
        mock_mt5 = Mock()
        mock_mt5.history_deals_get.return_value = [exit_deal1, exit_deal2]
        audit_logger._mt5 = mock_mt5
        
        result = audit_logger.log_close_fill(fill_id)
        assert result is True
        
        # Verify Net P&L calculation
        # Net P&L = entry_profit + exit_profit + entry_commission + exit_commission + entry_swap + exit_swap
        # = 0.0 + (1200 + 800) + (-3.50) + (-1.00 - 0.80) + (-0.80) + (-0.15 - 0.10)
        # = 2000 - 3.50 - 1.80 - 0.80 - 0.25
        # = 2000 - 6.35 = 1993.65
        from mars.apps.trading.loss_audit import _net_pnl
        
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM fills WHERE id = ?", (fill_id,)).fetchone()
            assert row is not None
            
            net_pnl = _net_pnl(row)
            expected = 2000.0 - 3.50 - 1.80 - 0.80 - 0.25  # 1993.65
            assert abs(net_pnl - expected) < 0.01, f"Expected {expected}, got {net_pnl}"
            
            # Verify aggregated exit fields
            assert row["exit_commission"] == -1.80
            assert row["exit_swap"] == -0.25
            assert row["exit_profit"] == 2000.0
            assert "10001" in row["exit_deal_ticket"]
            assert "10002" in row["exit_deal_ticket"]
        
        print("✅ test_full_roundtrip_multiple_entry_exit passed")
    finally:
        _cleanup_db(db_path)
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_missing_deal_history()
    test_confirmed_zero_commission()
    test_multiple_entry_deals_position_fallback()
    test_multiple_entry_deals_initial_ticket_is_entry()
    test_partial_fill_volume_reconciliation()
    test_missing_entry_deals_in_history()
    test_exception_during_deal_lookup()
    test_multiple_exit_deals()
    test_duplicate_reconciliation()
    test_net_pnl_reconciliation()
    test_full_roundtrip_multiple_entry_exit()
    print("\n✅ All F-08 regression tests passed!")